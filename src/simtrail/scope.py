# SPDX-License-Identifier: Apache-2.0
"""A scope: what devices, settings and agents are grouped by.

Simtrail knows nothing about the application embedding it. A standalone install makes one scope per project folder
(`Scope.for_folder`); a host application makes one for whatever it groups work by and hands Simtrail a `Scope`. A
device is kept per scope (``device.mode = "per_scope"``) or one per group (``"shared"``).

A scope's id is safe in a URL path segment and a file name: letters, digits and ``_ . : -``, starting with a letter or
digit, at most 128 characters. Its label is what a person reads -- in a tab's title, a simulator's name -- and for a
folder it is the project's name: a git worktree's is its repository's, not the worktree's own folder (`project_name`).
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

ID_PATTERN = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
LABEL_MAX = 200
#: The group every standalone scope belongs to: in ``shared`` device mode, all projects on the Mac share one device.
STANDALONE_GROUP = "local"


class InvalidScope(ValueError):
    """A scope id, group or label that cannot be used."""


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", text).strip("-._")
    return cleaned[:48] or "project"


def _one_line(text: str) -> str:
    return " ".join(text.split())[:LABEL_MAX]


def project_name(folder: Path) -> str:
    """What a person calls the project in `folder`: the folder's name -- or, for a git worktree, its repository's, so a
    worktree named after a branch reads as the project it is a copy of. Read from the worktree's ``.git`` file, which
    names ``<repository>/.git/worktrees/<name>``; no git is run."""
    marker = folder / ".git"
    try:
        text = marker.read_text(encoding="utf-8") if marker.is_file() else ""
    except OSError:
        text = ""
    if text.startswith("gitdir:"):
        gitdir = Path(os.path.normpath(folder / text.removeprefix("gitdir:").strip()))
        if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
            return gitdir.parents[2].name or folder.name
    return folder.name or "root"


@dataclass(frozen=True)
class Scope:
    id: str
    group: str
    label: str

    def __post_init__(self) -> None:
        for name in ("id", "group"):
            value = getattr(self, name)
            if not isinstance(value, str) or not ID_PATTERN.match(value):
                raise InvalidScope(
                    f"a scope {name} is 1 to 128 letters, digits, _ . : or -, starting with a letter or digit, "
                    f"not {value!r}"
                )
        if not isinstance(self.label, str) or len(self.label) > LABEL_MAX or any(c in self.label for c in "\n\r\x00"):
            raise InvalidScope(f"a scope label is one line of at most {LABEL_MAX} characters")

    @classmethod
    def named(cls, scope_id: str, *, group: str = STANDALONE_GROUP) -> Scope:
        """A scope a person named, such as ``simtrail open --scope demo``: its id is its label."""
        return cls(id=scope_id, group=group, label=scope_id)

    @classmethod
    def for_folder(cls, folder: Path) -> Scope:
        """A project folder's scope: its name and a short hash of its real path, so two folders with the same name
        are two scopes and a folder reached through a link is the same one."""
        real = folder.resolve()
        digest = hashlib.blake2b(str(real).encode("utf-8"), digest_size=4).hexdigest()
        name = real.name or "root"
        # The id keeps the folder's own name, as it always has: a device and its settings are remembered by it.
        return cls(id=f"project-{_slug(name)}-{digest}", group=STANDALONE_GROUP, label=_one_line(project_name(real)))
