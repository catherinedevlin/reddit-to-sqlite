"""
Get a connection to the Reddit API
"""
import json
import platform
from pathlib import Path

import praw
import typer

from . import __version__


def get_auth(auth_path: Path) -> dict[str, str]:
    """Retrieves Reddit auth data from file, or prompts for it and saves it"""

    if auth_path.exists():
        return json.loads(auth_path.read_text())

    typer.echo("You will need your Reddit user login info")
    typer.echo("and a Reddit client id and secret;")
    typer.echo("See https://www.reddit.com/wiki/api")
    data = {}
    for field in ("client_id", "client_secret", "username", "password"):
        data[field] = input(f"{field} > ")

    auth_path.parent.mkdir(exist_ok=True)
    auth_path.write_text(json.dumps(data, indent=2))
    return data


def reddit_instance(auth_data: dict[str, str]) -> praw.Reddit:
    """Returns an instance of praw.Reddit"""

    author = "catherinedevlin"
    qualified_name = "com.github/catherinedevlin/reddit-to-sqlite"

    auth_data["user_agent"] = (
        f"{platform.platform()}:{qualified_name}:v{__version__}" f" (by /u/{author})"
    )
    return praw.Reddit(**auth_data)
