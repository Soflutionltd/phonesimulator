# SPDX-License-Identifier: Apache-2.0
"""How a page gets in without a token in its URL: a one-shot code, spent for a viewer token the page holds.

``simtrail open`` asks the daemon, with the admin token, for a code for a scope and opens
``/viewer/<scope>#code=…``; a host's backend asks for an embed ticket and frames ``/embed/<scope>#ticket=…``. Either
is a `OneShotCodes` code: spent once, within `CODE_TTL_S`. It sits in the URL's fragment, which a browser never sends
to a server, so it reaches no log; the page posts it to ``/api/v1/auth/exchange`` and gets a viewer token for that
scope (`ViewerSessions`) that lives in the page's memory. The daemon keeps only its SHA-256 and its expiry -- in memory,
and in ``viewer-sessions.json`` (0600) beside its other credentials -- so an open page outlives a restart of the same
install, until its session expires as it would have or every page's is ended (``simtrail token sign-out``).

A code remembers what kind of session it opens, and so does the session: a ``viewer`` (``simtrail open``), an
``embed`` (a host's frame), or ``settings`` (``simtrail open --settings``), the one kind that may change settings --
for `SETTINGS_TTL_S`, not the twelve hours a viewer stays open.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal, NamedTuple, get_args

from simtrail.storage.private import write_private

logger = logging.getLogger(__name__)

#: Where a daemon keeps its pages' sessions, beside its tokens (`daemon.tokens`).
VIEWER_SESSIONS_FILE = "viewer-sessions.json"
CODE_TTL_S = 60.0
VIEWER_TTL_S = 12 * 3600.0
SETTINGS_TTL_S = 3600.0

SessionKind = Literal["viewer", "embed", "settings"]


class Pass(NamedTuple):
    """What a code or a session is for: a scope, and the kind of session."""

    scope_id: str
    kind: SessionKind


def ttl_of(kind: SessionKind) -> float:
    return SETTINGS_TTL_S if kind == "settings" else VIEWER_TTL_S


class OneShotCodes:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, ttl_s: float = CODE_TTL_S) -> None:
        self._clock = clock
        self._ttl_s = ttl_s
        self._codes: dict[str, tuple[float, Pass]] = {}

    def mint(self, scope_id: str, kind: SessionKind = "viewer") -> str:
        now = self._clock()
        self._codes = {code: entry for code, entry in self._codes.items() if entry[0] > now}
        code = secrets.token_urlsafe(24)
        self._codes[code] = (now + self._ttl_s, Pass(scope_id, kind))
        return code

    def redeem(self, code: str) -> Pass | None:
        """What a code opens, spending it -- or None for one that was never made, is spent or has expired."""
        entry = self._codes.pop(code, None)
        if entry is None or entry[0] <= self._clock():
            return None
        return entry[1]


class ViewerSessions:
    """Pages' sessions, each kept as its token's SHA-256, its scope and kind, and its expiry. Given a `path`, they are
    written there on each change -- the expiry as a time of day (`wall`) -- and read back when made, so a daemon
    started again on the same state folder lets its open pages in until their sessions would have expired anyway."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        path: Path | None = None,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._clock = clock
        self._path = path
        self._wall = wall
        self._tokens: dict[str, tuple[float, Pass]] = self._read()

    def _read(self) -> dict[str, tuple[float, Pass]]:
        if self._path is None or not self._path.exists():
            return {}
        try:
            entries = json.loads(self._path.read_text(encoding="utf-8"))["sessions"]
            now, left = self._clock(), {}
            for key, (expires_at, scope_id, kind) in entries.items():
                if kind not in get_args(SessionKind) or not isinstance(scope_id, str):
                    raise ValueError(kind)
                # Never longer than a new session of its kind: a clock set back does not stretch it.
                remaining = min(float(expires_at) - self._wall(), ttl_of(kind))
                if remaining > 0:
                    left[str(key)] = (now + remaining, Pass(scope_id, kind))
            return left
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            logger.warning("%s could not be read: each open page needs `simtrail open` again", self._path)
            return {}

    def _write(self) -> None:
        if self._path is None:
            return
        offset = self._wall() - self._clock()
        sessions = {key: [ends + offset, *found] for key, (ends, found) in self._tokens.items()}
        try:
            write_private(self._path, json.dumps({"sessions": sessions}).encode("utf-8"))
        except OSError as exc:
            logger.warning("%s could not be written (%s): open pages will not outlive a restart", self._path, exc)

    def _live(self) -> None:
        now = self._clock()
        self._tokens = {key: entry for key, entry in self._tokens.items() if entry[0] > now}

    def open(self, scope_id: str, kind: SessionKind = "viewer") -> str:
        self._live()
        token = secrets.token_urlsafe(32)
        self._tokens[_digest(token)] = (self._clock() + ttl_of(kind), Pass(scope_id, kind))
        self._write()
        return token

    def end_all(self) -> int:
        """End every page's session at once; answers how many were open."""
        self._live()
        ended = len(self._tokens)
        self._tokens = {}
        self._write()
        return ended

    def session(self, token: str | None) -> Pass | None:
        """The scope and kind a viewer token is for, or None."""
        entry = self._tokens.get(_digest(token)) if token else None
        if entry is None or entry[0] <= self._clock():
            return None
        return entry[1]

    def scope_of(self, token: str | None) -> str | None:
        """The scope a viewer token is for, or None."""
        found = self.session(token)
        return None if found is None else found.scope_id


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
