import json
import platform
from pathlib import Path

import praw
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


@app.command()
def main(
    auth: Path = typer.Option(
        Path("~/.config/reddit-to-sqlite.json"),
        help="File to store Reddit credentials in",
    ),
    subreddit: str = typer.Option("", help="Subreddit whose entries to save"),
    user: str = typer.Option("", help="Reddit username whose entries to save"),
):
    typer.echo(f"{auth=} {subreddit=} {user=}")
    reddit = reddit_instance(get_auth(auth.expanduser()))


if __name__ == "__main__":
    app()
