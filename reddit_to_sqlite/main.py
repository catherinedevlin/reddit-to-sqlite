import sqlite3
import typing
from pathlib import Path

import praw
import sqlite_utils
import typer

from .reddit_instance import get_auth, reddit_instance

app = typer.Typer()


def save_user(db, reddit: praw.Reddit, username: str, limit: int):
    """Saves newest posts and comments by a user"""

    user = reddit.redditor(username)
    db["posts"].upsert_all(
        (saveable(s) for s in user.submissions.new(limit=limit)),
        pk="id",
        alter=True,
    )

    db["comments"].upsert_all(
        (saveable(s) for s in user.comments.new(limit=limit)),
        pk="id",
        alter=True,
    )


def save_subreddit(db, reddit: praw.Reddit, subreddit_name: str, limit: int):
    """Saves newest posts and comments in a subreddit"""

    subreddit = reddit.subreddit(subreddit_name)
    db["posts"].upsert_all(
        (saveable(s) for s in subreddit.new(limit=limit)), pk="id", alter=True
    )

    db["comments"].upsert_all(
        (saveable(s) for s in subreddit.comments(limit=limit)),
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


@app.command()
def main(
    target: str,
    auth: Path = Path("~/.config/reddit-to-sqlite.json"),
    db: Path = Path("reddit.sqlite"),
    limit: int = 500,
):
    """Load posts and comments from Reddit to sqlite

    :param target: user (u/username) or subreddit (r/subreddit) to capture
    :type target: str, required
    :param auth: file to get/save Reddit credentials
                 defaults to "~/.config/reddit-to-sqlite.json")
    :type auth: Path, optional
    :param db: sqlite file name/path to save into, defaults to "reddit.sqlite"
    :type auth: Path, optional
    :param limit: Maximum number of submissions to retrieve
    :type auth: int, optional
    """
    reddit = reddit_instance(get_auth(auth.expanduser()))
    saver, save_me = interpret_target(target)
    database = sqlite_utils.Database(db.expanduser())
    saver(database, reddit, save_me, limit=limit)
    ITEM_VIEW_DEF = (Path(__file__).parent / "view_def.sql").read_text()
    database.create_view("items", ITEM_VIEW_DEF, replace=True)
    try:
        db["dogs"].enable_fts(
            ["name", "twitter"], tokenize="porter", create_triggers=True
        )
    except sqlite3.OperationalError as exc:
        # happens if it is already there
        print(exc)

    # todo: use suggest_column_types to deal with undoable types (skip or force into string)


if __name__ == "__main__":
    app()
