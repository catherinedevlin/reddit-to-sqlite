import logging
import sqlite3
import time
import typing
from datetime import date, timedelta
from functools import partial
from itertools import takewhile
from pathlib import Path
from typing import Optional

import praw
import sqlite_utils
import typer

from .reddit_instance import get_auth, reddit_instance

LIMIT = 1000
SECONDS_IN_DAY = 60 * 60 * 24
LOGGER = logging.getLogger(__name__)
app = typer.Typer()


def query_val(db, qry: str) -> Optional[int]:
    "Safely get a single value using `qry`"
    try:
        curs = db.execute(qry)
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return None
        raise
    result = curs.fetchone()
    LOGGER.debug(f"{qry=} {result=}")
    return result[0]


def latest_from_user_utc(db, table_name: str, username: str) -> Optional[int]:

    qry = f"select max(created_utc) from {table_name} where author = '{username}'"
    return query_val(db, qry)


def created_since(row, target_sec_utc: Optional[int]) -> bool:

    result = (not target_sec_utc) or (row.created_utc >= target_sec_utc)
    LOGGER.debug(f"{row.id=} {row.created_utc=} >= {target_sec_utc=}? {result}")
    return result


def save_user(
    db,
    reddit: praw.Reddit,
    username: str,
    post_reload_sec: int,
    comment_reload_sec: int,
) -> None:

    user = reddit.redditor(username)
    latest_post_utc = latest_from_user_utc(db=db, table_name="posts", username=username)
    get_since = latest_post_utc and (latest_post_utc - post_reload_sec)
    LOGGER.info(f"Getting posts by {username} since timestamp {get_since}")
    _takewhile = partial(created_since, target_sec_utc=get_since)

    db["posts"].upsert_all(
        (saveable(s) for s in takewhile(_takewhile, user.submissions.new(limit=LIMIT))),
        pk="id",
        alter=True,
    )

    latest_comment_utc = latest_from_user_utc(
        db=db, table_name="comments", username=username
    )
    get_since = latest_post_utc and (latest_post_utc - comment_reload_sec)
    LOGGER.info(f"Getting comments by {username} since timestamp {get_since}")
    _takewhile = partial(created_since, target_sec_utc=get_since)

    db["comments"].upsert_all(
        (saveable(s) for s in takewhile(_takewhile, user.comments.new(limit=LIMIT))),
        pk="id",
        alter=True,
    )


def latest_post_in_subreddit_utc(db, subreddit: str) -> Optional[int]:

    qry = f"select max(created_utc) from posts where subreddit = '{subreddit}'"
    return query_val(db, qry)


def save_subreddit(
    db,
    reddit: praw.Reddit,
    subreddit_name: str,
    post_reload_sec: int,
    comment_reload_sec: int,
) -> None:

    subreddit = reddit.subreddit(subreddit_name)
    latest_post_utc = latest_post_in_subreddit_utc(db=db, subreddit=subreddit)
    get_since = latest_post_utc and (latest_post_utc - post_reload_sec)
    LOGGER.info(f"Getting posts in {subreddit} since timestamp {get_since}")
    _takewhile = partial(created_since, target_sec_utc=get_since)
    for post in takewhile(_takewhile, subreddit.new(limit=LIMIT)):
        LOGGER.debug(f"Post id {post.id}")
        db["posts"].upsert(saveable(post), pk="id", alter=True)
        post.comments.replace_more()
        db["comments"].upsert_all(
            (saveable(c) for c in post.comments.list()),
            pk="id",
            alter=True,
        )


def legalize(val):
    """Convert `val` to a form that can be saved in sqlite"""

    if isinstance(val, praw.models.reddit.base.RedditBase):
        return str(val)
    return val


def _parent_ids_interpreted(dct: dict[str, typing.Any]) -> dict[str, typing.Any]:

    if not dct.get('parent_id'):
        return dct 
    
    prefix = dct['parent_id'][:3]
    dct['parent_clean_id'] = dct['parent_id'][3:]
    if prefix == 't1_':
        dct['parent_comment_id'] = dct['parent_clean_id']
    elif prefix == 't3_':
        dct['parent_post_id'] = dct['parent_clean_id']
    return dct

def saveable(item: praw.models.reddit.base.RedditBase) -> dict[str, typing.Any]:

    """Generate a saveable dict from an instance"""

    result = {k: legalize(v) for k, v in item.__dict__.items() if not k.startswith("_")}
    return _parent_ids_interpreted(result) 


def interpret_target(raw_target: str) -> tuple[typing.Callable, str]:
    """Determine saving function and target string from input target"""

    HELP = "Target must be u/username or r/subreddit"
    SAVERS = {"u": save_user, "r": save_subreddit}

    assert "/" in raw_target, HELP
    raw_target = raw_target.lower()
    pieces = raw_target.split("/")
    assert pieces[-2] in SAVERS, HELP
    return SAVERS[pieces[-2]], pieces[-1]

def create_index(db, tbl, col):
    try:
        db[tbl].create_index([col], if_not_exists=True)
    except sqlite3.OperationalError as exc:
        LOGGER.warn(f"Error indexing {tbl}.{col}: {exc}")

def create_fts_index(db, tbl, cols):
    try:
        db[tbl].enable_fts(
            cols, tokenize="porter", create_triggers=True
        )
    except sqlite3.OperationalError as exc:
        LOGGER.info(f"While setting up full-text search on {tbl}.{cols}:")
        LOGGER.info(exc)
 


def setup_ddl(db):

    for tbl in ("posts", "comments"):
        for col in ("author", "created_utc", "subreddit", "score", "removed"):
            create_index(db, tbl, col)
    for col in ("parent_clean_id", "parent_comment_id", "parent_post_id"):
        create_index(db, 'comments', col)

    create_fts_index(db, 'posts', ['title', 'selftext']) 
    create_fts_index(db, 'comments', ['body', ]) 


def set_loglevel(verbosity: int):

    verbosity = min(verbosity, 2)
    LEVELS = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    LOGGER.setLevel(LEVELS[verbosity])
    LOGGER.addHandler(logging.StreamHandler())


@app.command()
def main(
    target: str = typer.Argument(str, help="u/username or r/subreddit to collect"),
    auth: Path = typer.Option(
        Path("~/.config/reddit-to-sqlite.json"),
        help="File to retrieve/save Reddit auth",
    ),
    db: Path = typer.Option(Path("reddit.db"), help="database file"),
    post_reload: int = typer.Option(7, help="Age of posts to reload (days)"),
    comment_reload: int = typer.Option(7, help="Age of posts to reload (days)"),
    verbose: int = typer.Option(0, "--verbose", "-v", count=True, help="More logging"),
):
    """Load posts and comments from Reddit to sqlite."""
    set_loglevel(verbosity=verbose)
    reddit = reddit_instance(get_auth(auth.expanduser()))
    saver, save_me = interpret_target(target)
    database = sqlite_utils.Database(db.expanduser())
    saver(
        database,
        reddit,
        save_me,
        post_reload_sec=post_reload * SECONDS_IN_DAY,
        comment_reload_sec=comment_reload * SECONDS_IN_DAY,
    ),
    ITEM_VIEW_DEF = (Path(__file__).parent / "view_def.sql").read_text()
    database.create_view("items", ITEM_VIEW_DEF, replace=True)
    setup_ddl(database)


if __name__ == "__main__":
    app()
