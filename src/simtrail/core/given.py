# SPDX-License-Identifier: Apache-2.0
"""Logins handed to the daemon for one `sim_login`, by ``simtrail login``.

`sim_login` asks a password manager from the daemon (`platform.passwords`). A daemon started from inside a sandbox --
an MCP client that runs its servers under a macOS sandbox profile, say -- inherits it, and the profile may forbid what
the password manager's CLI needs: the Keychain, its settings folder. ``simtrail login`` asks the password manager
outside it, in the person's own terminal, and hands the login it chose to the daemon here, over the admin route only
the person can call. `sim_login` then types it as it types any other (``source: "given"``), so nothing differs for the
app: the same fields found, the same masking.

A login given is kept in memory only, never on disk, for one scope and one app; it is taken once -- typed or not --
and dropped after `GIVEN_S` if nobody takes it. Its id is a random token the agent never sees: an agent calling
`sim_login` with ``source: "given"`` reaches a login only with the id ``simtrail login`` passed itself.
"""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from simtrail.platform.passwords import Credentials, Login, Source

#: How long a login given waits to be taken, in seconds.
GIVEN_S = 120.0
#: The most logins waiting at once: each is one ``simtrail login`` under way.
GIVEN_MAX = 8
#: What `sim_login` calls the source of a login given.
GIVEN = "given"


@dataclass
class _Waiting:
    scope_id: str
    app: str
    title: str
    credentials: Credentials = field(repr=False)
    until: float


class GivenLogins:
    """The logins ``simtrail login`` handed over, each waiting to be taken once."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._waiting: dict[str, _Waiting] = {}

    def _drop_late(self) -> None:
        now = self._clock()
        for late in [key for key, waiting in self._waiting.items() if waiting.until <= now]:
            self._waiting.pop(late).credentials.forget()

    def give(self, scope_id: str, app: str, title: str, credentials: Credentials) -> str:
        """Keep a login for this scope and app until it is taken or `GIVEN_S` passes: answers the id to take it by."""
        self._drop_late()
        while len(self._waiting) >= GIVEN_MAX:
            oldest = min(self._waiting, key=lambda key: self._waiting[key].until)
            self._waiting.pop(oldest).credentials.forget()
        key = secrets.token_urlsafe(18)
        self._waiting[key] = _Waiting(scope_id, app, title, credentials, self._clock() + GIVEN_S)
        return key

    def take(self, scope_id: str, app: str, key: str) -> Login | None:
        """The login given under this id for this scope and app, as a `Login` that reveals it once -- or None. Taken,
        it is no longer kept here, whether or not it is typed."""
        self._drop_late()
        waiting = self._waiting.get(key)
        if waiting is None or waiting.scope_id != scope_id or waiting.app != app:
            return None
        del self._waiting[key]
        credentials = waiting.credentials

        async def reveal() -> Credentials:
            return credentials

        return Login(GIVEN, key, waiting.title, credentials.username, "simtrail login", (app,), reveal)


class GivenSource(Source):
    """The one login a `sim_login` call took from `GivenLogins`, asked as any password manager is."""

    kind = GIVEN

    def __init__(self, login: Login) -> None:
        self._login = login

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        return [self._login]
