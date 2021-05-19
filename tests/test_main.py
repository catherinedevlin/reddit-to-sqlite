import json
import pathlib
from unittest.mock import create_autospec, patch

import praw
import pytest
import sqlite_utils

from reddit_to_sqlite import main


def test_interpret_target():

    (saver, user) = main.interpret_target("u/r2d2")
    assert saver == main.save_user
    assert user == "r2d2"

    (saver, subreddit) = main.interpret_target("r/starwars")
    assert saver == main.save_subreddit
    assert subreddit == "starwars"

    with pytest.raises(AssertionError):
        main.interpret_target("deathstar")

    with pytest.raises(AssertionError):
        main.interpret_target("x/darthvader")


def test_legalize_already_legal():

    assert main.legalize("cows") == "cows"
    assert main.legalize(22) == 22


subreddit = create_autospec(praw.models.reddit.subreddit.Subreddit)
subreddit.__str__.return_value = "MadeMeSmile"


def test_legalize_illegal():
    assert main.legalize(subreddit) == "MadeMeSmile"


class FakePost:
    def __init__(self):
        self.__foo__ = "bar"
        self.subreddit = subreddit
        self.title = "blah blah blah"
        self.score = 22


def test_saveable():
    expected = {"subreddit": "MadeMeSmile", "score": 22, "title": "blah blah blah"}
    assert main.saveable(FakePost()) == expected
