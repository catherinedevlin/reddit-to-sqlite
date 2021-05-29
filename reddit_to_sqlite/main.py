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

LOGGER = logging.getLogger(__name__)

from .reddit_instance import get_auth, reddit_instance

LIMIT = 10
app = typer.Typer()


def query_val(db, qry: str) -> Optional[int]:
    try:
        curs = db.execute(qry)
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return None
        raise
    return curs.fetchone()[0]


def latest_from_user_utc(db, table_name: str, username: str) -> Optional[int]:

    qry = f"select max(created_utc) from {table_name} where author = '{username}'"
    return query_val(db, qry)


def created_since(row, target_sec_utc: Optional[int]) -> bool:

    return (not target_sec_utc) or (row.created_utc >= target_sec_utc)


def save_user(db, reddit: praw.Reddit, username: str, overlap_sec: int):
    """Saves newest posts and comments by a user"""

    user = reddit.redditor(username)
    latest_post_utc = latest_from_user_utc(db=db, table_name="posts", username=username)
    get_since = latest_post_utc and (latest_post_utc - overlap_sec)
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
    LOGGER.info(f"Getting comments by {username} since timestamp {latest_comment_utc}")
    _takewhile = partial(created_since, target_sec_utc=latest_comment_utc)

    db["comments"].upsert_all(
        (saveable(s) for s in takewhile(_takewhile, user.comments.new(limit=LIMIT))),
        pk="id",
        alter=True,
    )


def latest_post_in_subreddit_utc(db, subreddit: str) -> Optional[int]:

    qry = f"select max(created_utc) from posts where subreddit = '{subreddit}'"
    return query_val(db, qry)


def save_subreddit(db, reddit: praw.Reddit, subreddit_name: str, overlap_sec: int):

    subreddit = reddit.subreddit(subreddit_name)
    latest_post_utc = latest_post_in_subreddit_utc(db=db, subreddit=subreddit)
    get_since = latest_post_utc and (latest_post_utc - overlap_sec)
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


def saveable(item: praw.models.reddit.base.RedditBase) -> dict:
    """Generate a saveable dict from an instance"""

    return {k: legalize(v) for k, v in item.__dict__.items() if not k.startswith("_")}


def interpret_target(raw_target: str) -> tuple[typing.Callable, str]:
    """Determine saving function and target string from input target"""

    HELP = "Target must be u/username or r/subreddit"
    SAVERS = {"u": save_user, "r": save_subreddit}

    assert "/" in raw_target, HELP
    raw_target = raw_target.lower()
    pieces = raw_target.split("/")
    assert pieces[-2] in SAVERS, HELP
    return SAVERS[pieces[-2]], pieces[-1]


def get_start_epoch(raw: str) -> float:
    if raw:
        try:
            days = int(raw)
            assert days > 0, "start_date must be 1 or more days"
            result = date.today() - timedelta(days=days)
        except ValueError:
            result = date.fromisoformat(raw)
    else:
        result = date.today() - timedelta(days=365)
    return time.mktime(result.timetuple())


SECONDS_IN_DAY = 60 * 60 * 24


def setup_fts(db):

    try:
        db["posts"].enable_fts(
            ["title", "selftext"], tokenize="porter", create_triggers=True
        )
    except sqlite3.OperationalError as exc:
        LOGGER.info("While setting up full-text search:")
        LOGGER.info(exc)
    try:
        db["comments"].enable_fts(
            [
                "body",
            ],
            tokenize="porter",
            create_triggers=True,
        )
    except sqlite3.OperationalError as exc:
        LOGGER.info("While setting up full-text search:")
        LOGGER.info(exc)


@app.command()
def main(
    target: str,
    auth: Path = Path("~/.config/reddit-to-sqlite.json"),
    db: Path = Path("reddit.sqlite"),
    overlap: int = 10,
):
    """Load posts and comments from Reddit to sqlite

    :param target: user (u/username) or subreddit (r/subreddit) to capture
    :type target: str, required
    :param auth: file to get/save Reddit credentials
                 defaults to "~/.config/reddit-to-sqlite.json")
    :type auth: Path, optional
    :param db: sqlite file name/path to save into, defaults to "reddit.sqlite"
    :type auth: Path, optional
    :param start: how far back to go; number of days, or YYYY-MM-DD
    :type start_date: str, optional

    """
    reddit = reddit_instance(get_auth(auth.expanduser()))
    saver, save_me = interpret_target(target)
    database = sqlite_utils.Database(db.expanduser())
    saver(database, reddit, save_me, overlap_sec=overlap * SECONDS_IN_DAY)
    ITEM_VIEW_DEF = (Path(__file__).parent / "view_def.sql").read_text()
    database.create_view("items", ITEM_VIEW_DEF, replace=True)
    setup_fts(database)


if __name__ == "__main__":
    app()
