# SPDX-License-Identifier: Apache-2.0
"""Which saved login is for an app, and which login is chosen -- `core.login`, apart from a device."""

from __future__ import annotations

import pytest

from phonesimulator.core.login import LISTED_MAX, LoginRefused, Wanted, choose, label, site_of
from phonesimulator.platform.passwords import Credentials, Login, PasswordSourceError, Source


async def nothing() -> Credentials:
    raise AssertionError("never revealed")


def saved(ref: str, *urls: str, username: str = "ann") -> Login:
    return Login("command", ref, f"Login {ref}", username, "/bin/logins", urls, nothing)


class Listed(Source):
    kind = "command"

    def __init__(self, *logins: Login, failing: bool = False) -> None:
        self.found, self.failing = list(logins), failing

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        if self.failing:
            raise PasswordSourceError("it is locked")
        return self.found


@pytest.mark.parametrize(
    ("host", "site"),
    [
        ("accounts.example.com", "example.com"),
        ("Example.COM.", "example.com"),
        ("shop.example.co.uk", "example.co.uk"),
        ("localhost", "localhost"),
        ("127.0.0.1", "127.0.0.1"),
        ("io.uk", "io.uk"),
    ],
)
def test_a_site_is_its_registrable_domain(host: str, site: str) -> None:
    assert site_of(host) == site


def test_an_app_matches_by_its_site_its_id_or_the_site_its_id_reverses() -> None:
    notes = Wanted.of("com.example.notes")
    assert notes.matches(saved("1", "https://www.example.com/login"))
    assert notes.matches(saved("2", "android://com.example.notes"))
    assert notes.matches(saved("3", "com.example.notes"))
    assert not notes.matches(saved("4", "https://example.org"))
    assert not notes.matches(saved("5"))
    website = Wanted.of("https://accounts.example.com/sign-in")
    assert website.ids == frozenset() and website.matches(saved("6", "example.com"))


async def test_a_source_that_fails_is_named_in_the_refusal() -> None:
    with pytest.raises(LoginRefused, match="command: it is locked"):
        await choose([Listed(failing=True)], "example.com", account=None, item=None)


async def test_the_first_source_with_a_login_is_used_and_a_long_list_is_cut() -> None:
    first, second = Listed(), Listed(saved("x", "example.com"))
    assert (await choose([first, second], "example.com", account=None, item=None)).ref == "x"
    many = Listed(*(saved(str(index), "example.com") for index in range(LISTED_MAX + 2)))
    with pytest.raises(LoginRefused, match=f"id {LISTED_MAX - 1}\\) and 2 more$"):
        await choose([many], "example.com", account=None, item=None)


def test_a_login_is_named_with_or_without_its_username() -> None:
    login = saved("7", username="")
    assert label(login) == '"Login 7" (/bin/logins, id 7)'
    assert label(saved("8"), username=False) == '"Login 8" (/bin/logins, id 8)'
