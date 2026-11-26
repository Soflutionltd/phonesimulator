# SPDX-License-Identifier: Apache-2.0
"""Keeping a password `sim_login` typed out of every answer an agent reads afterwards.

What `sim_login` types never reaches the agent through `sim_login` itself, but the device may say it back later: a
field that shows a password once its eye is tapped, an app that writes it to its log, a screen that echoes a one-time
code. So every tool's answer goes through `SecretMask.result` before the agent gets it, and anything `hide` was given
reads ``••••`` there.

**The mask holds no secret.** It keeps a keyed BLAKE2b digest of each value -- the key made afresh for each process,
never written anywhere -- and the value's length, and looks for the value by hashing each run of that many characters
of an answer. A dump of the daemon's memory finds the digests, which say nothing without the key and the value.

A password is masked for `PASSWORD_S`, a one-time code -- six digits that may well appear in a screen for another
reason later -- for `CODE_S`. A value shorter than `SHORTEST` is not masked: a three-letter run would match too much
of what a screen says, and no sign-in form takes such a password.
"""

from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

#: What a masked value reads as.
MASK = "••••"
#: How long a typed password, and a typed one-time code, stay masked.
PASSWORD_S = 12 * 3600.0
CODE_S = 180.0
#: The fewest characters a value masked has.
SHORTEST = 4
_DIGEST_SIZE = 16


class SecretMask:
    """The values typed for agents, as digests only, and answers with them masked."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._key = os.urandom(32)
        #: length -> digest -> until when it is masked.
        self._held: dict[int, dict[bytes, float]] = {}

    def _digest(self, value: str) -> bytes:
        return hashlib.blake2b(value.encode("utf-8"), key=self._key, digest_size=_DIGEST_SIZE).digest()

    def hide(self, value: str, seconds: float) -> None:
        """Mask `value` -- and its URL-encoded form, as a log may carry it -- for `seconds` from now."""
        until = self._clock() + seconds
        for form in {value, quote(value, safe="")}:
            if len(form) >= SHORTEST:
                held = self._held.setdefault(len(form), {})
                held[self._digest(form)] = max(until, held.get(self._digest(form), until))

    @property
    def holding(self) -> bool:
        """Whether any value is masked now."""
        self._expire()
        return bool(self._held)

    def _expire(self) -> None:
        now = self._clock()
        for length in list(self._held):
            kept = {digest: until for digest, until in self._held[length].items() if until > now}
            if kept:
                self._held[length] = kept
            else:
                del self._held[length]

    def text(self, said: str) -> str:
        """`said` with every masked value in it read as `MASK`."""
        if not self.holding:
            return said
        hidden = [False] * len(said)
        for length in sorted(self._held, reverse=True):
            digests = self._held[length]
            for start in range(len(said) - length + 1):
                if not hidden[start] and self._digest(said[start : start + length]) in digests:
                    hidden[start : start + length] = [True] * length
        if not any(hidden):
            return said
        parts: list[str] = []
        for index, character in enumerate(said):
            if not hidden[index]:
                parts.append(character)
            elif index == 0 or not hidden[index - 1]:
                parts.append(MASK)
        return "".join(parts)

    def value(self, value: Any) -> Any:
        """A tool's answer, or a part of it, with every text in it masked: text blocks, structured content, lists."""
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, dict):
            return {key: self.value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.value(item) for item in value]
        return value

    def result(self, result: dict[str, Any]) -> dict[str, Any]:
        """A tool's answer as the agent may read it. An image block's data is a picture, read by no one as text, and
        passed through as it is; so is any answer while nothing is masked."""
        if not self.holding:
            return result
        masked = dict(result)
        masked["content"] = [
            block if block.get("type") == "image" else self.value(block) for block in result.get("content", [])
        ]
        if "structuredContent" in result:
            masked["structuredContent"] = self.value(result["structuredContent"])
        return masked
