# SPDX-License-Identifier: Apache-2.0
"""What a person calls each scope the daemon serves -- ``Sociomator``, not ``project-sociomator-e80a0c71``.

A scope reaches the daemon by its id alone; its label -- the project's name (`scope.project_name`) -- is told by what
knows the folder: ``rocketwright open`` names it as it asks for a login code, and an agent token made for folders names
each folder's. The daemon keeps them in ``scope-names.json`` (0600) beside its tokens, so a simulator it makes, a
tab's title and the settings panel read the project's name after a restart too. A scope never named is called by its
id, as before.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from rocketwright.scope import LABEL_MAX, InvalidScope, Scope
from rocketwright.storage.private import write_private

logger = logging.getLogger(__name__)

#: Where a daemon keeps its scopes' names, beside its tokens (`daemon.tokens`).
SCOPE_NAMES_FILE = "scope-names.json"
#: The most names kept: the scopes named last are kept, an old one is called by its id again.
NAMES_MAX = 500


class ScopeNames:
    """Each scope's name, by id, read once and written whenever one changes."""

    def __init__(self, path: Path | None) -> None:
        self._path = path
        self._names: dict[str, str] = self._read()

    def _read(self) -> dict[str, str]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            names = json.loads(self._path.read_text(encoding="utf-8"))["names"]
        except (OSError, ValueError, KeyError, TypeError):
            logger.warning("could not read the scopes' names in %s: they are called by their ids", self._path)
            return {}
        if not isinstance(names, dict):
            return {}
        return {str(key): value for key, value in names.items() if isinstance(value, str) and _fits(str(key), value)}

    def name(self, scope_id: str) -> str | None:
        """What the scope is called, when it was named."""
        return self._names.get(scope_id)

    def remember(self, scope_id: str, label: str) -> None:
        """Keep a scope's name; one that is no valid label, or is its id, is not kept."""
        label = " ".join(label.split())
        if label == scope_id or not _fits(scope_id, label) or self._names.get(scope_id) == label:
            return
        self._names.pop(scope_id, None)
        self._names[scope_id] = label
        while len(self._names) > NAMES_MAX:
            del self._names[next(iter(self._names))]
        if self._path is not None:
            write_private(self._path, json.dumps({"names": self._names}, ensure_ascii=False).encode("utf-8"))

    def remember_folders(self, scope_ids: Iterable[str], roots: Iterable[str]) -> None:
        """Name each scope among `scope_ids` that is one of the folders `roots`, by its project's name."""
        wanted = set(scope_ids)
        for root in roots:
            try:
                scope = Scope.for_folder(Path(root))
            except (OSError, ValueError):  # a path the system refuses, or that is no valid scope
                continue
            if scope.id in wanted:
                self.remember(scope.id, scope.label)


def _fits(scope_id: str, label: str) -> bool:
    try:
        Scope(scope_id, "local", label)
    except InvalidScope:
        return False
    return bool(label.strip()) and len(label) <= LABEL_MAX
