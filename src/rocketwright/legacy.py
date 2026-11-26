# SPDX-License-Identifier: Apache-2.0
"""What an install from before the rename to Rocketwright (Simtrail, 3.11 and earlier) left, taken up as it starts.

* **The environment.** A ``SIMTRAIL_*`` variable stands for its ``ROCKETWRIGHT_*`` one when that is not set, so an MCP
  client's configuration, a shell profile or a CI job written for Simtrail goes on working.
* **The folders.** ``~/Library/Application Support/Simtrail`` (settings, remembered devices, tokens, the helper),
  ``~/Library/Logs/Simtrail`` and ``~/.simtrail`` become Rocketwright's, moved in one rename each -- what they hold is
  untouched -- with a link left where each was, so a process of the old install still running finds its files. A folder
  is moved only when Rocketwright has none yet, and never when its environment variable names another place.

The ``simtrail`` command stays, as another name for ``rocketwright`` (``pyproject.toml``).
"""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path

OLD_PREFIX = "SIMTRAIL_"
NEW_PREFIX = "ROCKETWRIGHT_"


def adopt_environment(env: MutableMapping[str, str]) -> list[str]:
    """Give each ``SIMTRAIL_*`` variable's value to its ``ROCKETWRIGHT_*`` one, where that is not set. Answers the new
    names given a value."""
    adopted: list[str] = []
    for name, value in list(env.items()):
        if name.startswith(OLD_PREFIX):
            new = NEW_PREFIX + name.removeprefix(OLD_PREFIX)
            if new not in env:
                env[new] = value
                adopted.append(new)
    return sorted(adopted)


def old_folders(home: Path) -> list[tuple[Path, Path, str]]:
    """Each folder the old install kept, where Rocketwright keeps it now, and the variable that moves it elsewhere."""
    support = home / "Library" / "Application Support"
    return [
        (support / "Simtrail", support / "Rocketwright", "ROCKETWRIGHT_STATE_DIR"),
        (home / "Library" / "Logs" / "Simtrail", home / "Library" / "Logs" / "Rocketwright", "ROCKETWRIGHT_LOG_DIR"),
        (home / ".simtrail", home / ".rocketwright", "ROCKETWRIGHT_RUN_DIR"),
    ]  # fmt: skip


def move_folders(home: Path, env: MutableMapping[str, str]) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Move each folder the old install left to Rocketwright's place, leaving a link where it was. Answers what moved,
    and what could not be, said for a person."""
    moved: list[tuple[Path, Path]] = []
    problems: list[str] = []
    for old, new, variable in old_folders(home):
        if env.get(variable, "").strip() or old.is_symlink() or not old.is_dir() or new.exists():
            continue
        try:
            old.rename(new)
        except OSError as exc:
            problems.append(f"could not move {old} to {new}: {exc.strerror or exc}")
            continue
        try:
            old.symlink_to(new, target_is_directory=True)
        except OSError as exc:
            problems.append(f"moved {old} to {new}, but could not leave a link where it was: {exc.strerror or exc}")
        moved.append((old, new))
    return moved, problems


def adopt(env: MutableMapping[str, str], home: Path) -> list[str]:
    """Take up what the old install left: its environment first -- a variable may move a folder -- then its folders.
    Answers what could not be done."""
    adopt_environment(env)
    _, problems = move_folders(home, env)
    return problems
