import json
import platform
import typing
from pathlib import Path

import praw
import sqlite_utils
import typer

from reddit_to_sqlite import __version__

app = typer.Typer()


def get_auth(auth_path: Path) -> dict[str, str]:

    if auth_path.exists():
        return json.loads(auth_path.read_text())

    data = {}
    for field in ("client_id", "client_secret", "username", "password"):
        data[field] = input(f"{field} > ")

    auth_path.parent.mkdir(exist_ok=True)
    auth_path.write_text(json.dumps(data, indent=2))
    return data


def reddit_instance(auth_data: dict[str, str]) -> praw.Reddit:

    author = "catherinedevlin"
    qualified_name = "com.github/catherinedevlin/reddit-to-sqlite"

    auth_data["user_agent"] = (
        f"{platform.platform()}:{qualified_name}:v{__version__}" f" (by /u/{author})"
    )
    return praw.Reddit(**auth_data)


def user_submissions(reddit: praw.Reddit, username: str, limit: int = 5):

    user = reddit.redditor(username)
    return user.submissions.new(limit=limit)


def subreddit_submissions(reddit: praw.Reddit, subreddit_name: str, limit: int = 50):
    pass


def reddit_ref_to_string(val):
    if isinstance(val, praw.models.reddit.base.RedditBase):
        return str(val)
    return val


def cleaned_submission(submission: dict) -> dict:
    return {
        k: reddit_ref_to_string(v)
        for k, v in submission.__dict__.items()
        if not k.startswith("_")
    }


def interpret_target(raw_target: str) -> tuple[typing.Callable, str]:

    HELP = "Target must be u/username or r/subreddit"
    GETTERS = {"u": user_submissions, "r": subreddit_submissions}

    assert "/" in raw_target, HELP
    raw_target = raw_target.lower()
    pieces = raw_target.split("/")
    assert pieces[-2] in GETTERS, HELP
    return GETTERS[pieces[-2]], pieces[-1]


@app.command()
def main(
    target: str,
    auth: Path = Path("~/.config/reddit-to-sqlite.json"),
    db: Path = Path("reddit.sqlite"),
):
    """Load posts and comments from Reddit to sqlite

    :param target: user (u/username) or subreddit (r/subreddit) to capture
    :type target: str, required
    :param auth: file to get/save Reddit credentials, defaults to "~/.config/reddit-to-sqlite.json")
    :type auth: Path, optional
    :param db: sqlite file name/path to save into, defaults to "reddit.sqlite"
    :type auth: Path, optional
    """
    typer.echo(f"{target=} {auth=} {db=}")
    reddit = reddit_instance(get_auth(auth.expanduser()))
    submissions_function, save_me = interpret_target(target)
    typer.echo(f"{submissions_function=} {save_me=}")
    data = submissions_function(reddit, save_me)
    database = sqlite_utils.Database(db)
    breakpoint()
    clean_data = (cleaned_submission(d) for d in data)
    database["submissions"].upsert_all(
        clean_data,
        pk="id",
        # column_order = [],
    )


if __name__ == "__main__":
    app()
