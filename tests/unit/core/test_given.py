# SPDX-License-Identifier: Apache-2.0
"""Logins handed to the daemon by ``simtrail login``: kept for one scope and app, taken once, dropped when late."""

from __future__ import annotations

import asyncio

from simtrail.core.given import GIVEN, GIVEN_MAX, GIVEN_S, GivenLogins, GivenSource
from simtrail.platform.passwords import Credentials
from simtrail.testing.fakes import ManualClock


def test_a_login_given_is_taken_once_for_its_scope_and_app_and_reveals_what_was_given() -> None:
    given = GivenLogins(clock=ManualClock())
    key = given.give("tp-1", "com.example.notes", "Example", Credentials("ann@example.com", "pw"))
    assert given.take("tp-2", "com.example.notes", key) is None, "another scope"
    assert given.take("tp-1", "com.example.other", key) is None, "another app"
    taken = given.take("tp-1", "com.example.notes", key)
    assert taken is not None and (taken.source, taken.title, taken.username) == (GIVEN, "Example", "ann@example.com")
    assert taken.urls == ("com.example.notes",) and taken.ref == key
    revealed = asyncio.run(taken.reveal())
    assert (revealed.username, revealed.password) == ("ann@example.com", "pw")
    assert given.take("tp-1", "com.example.notes", key) is None, "taken once"
    assert asyncio.run(GivenSource(taken).logins("com.example.notes")) == [taken]


def test_a_login_nobody_takes_is_dropped_and_forgotten_and_only_a_few_wait_at_once() -> None:
    clock = ManualClock()
    given = GivenLogins(clock=clock)
    late = Credentials("ann@example.com", "pw")
    key = given.give("tp-1", "app", "", late)
    clock.now += GIVEN_S
    assert given.take("tp-1", "app", key) is None and late.password == "", "dropped, its values emptied"
    first = Credentials("a", "1")
    keys = [given.give("tp-1", "app", "", first)]
    for _ in range(GIVEN_MAX):
        clock.now += 1
        keys.append(given.give("tp-1", "app", "", Credentials("b", "2")))
    assert given.take("tp-1", "app", keys[0]) is None and first.password == "", "the oldest made room"
    assert given.take("tp-1", "app", keys[-1]) is not None
