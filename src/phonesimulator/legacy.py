# SPDX-License-Identifier: Apache-2.0
"""What an install from before a rename left, taken up as PhoneSimulator starts. It was Simtrail until 3.11, and
Rocketwright for 3.12.0 and 3.12.1 -- a name its browser sibling carries now.

* **The environment.** A ``SIMTRAIL_*`` variable stands for its ``PHONESIMULATOR_*`` one when that is not set, so an
  MCP client's configuration, a shell profile or a CI job written for Simtrail goes on working. A ``ROCKETWRIGHT_*``
  variable is not taken up: that prefix is the browser tool's.
* **The folders.** ``~/Library/Application Support/<old name>`` (settings, remembered devices, tokens, the helper),
  ``~/Library/Logs/<old name>`` and ``~/.<old name>`` become PhoneSimulator's, moved in one rename each -- what they
  hold is untouched. Where Simtrail's was, a link is left, so a process of that install still running finds its files;
  none is left where Rocketwright's was, since that place is the browser tool's to use. A link Simtrail's move to
  Rocketwright left is pointed at PhoneSimulator's folder. A folder is moved only when PhoneSimulator has none yet,
  and never when its environment variable names another place.

The ``simtrail`` command stays, as another name for ``phonesimulator`` (``pyproject.toml``).
"""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path

OLD_PREFIX = "SIMTRAIL_"
NEW_PREFIX = "PHONESIMULATOR_"

#: An old folder, PhoneSimulator's, the variable that moves it elsewhere, and whether a link is left where it was.
OldFolder = tuple[Path, Path, str, bool]


def adopt_environment(env: MutableMapping[str, str]) -> list[str]:
    """Give each ``SIMTRAIL_*`` variable's value to its ``PHONESIMULATOR_*`` one, where that is not set. Answers the
    new names given a value."""
    adopted: list[str] = []
    for name, value in list(env.items()):
        if name.startswith(OLD_PREFIX):
            new = NEW_PREFIX + name.removeprefix(OLD_PREFIX)
            if new not in env:
                env[new] = value
                adopted.append(new)
    return sorted(adopted)


def old_folders(home: Path) -> list[OldFolder]:
    """Each folder an old install kept, where PhoneSimulator keeps it now, the variable that moves it elsewhere, and
    whether a link is left behind -- the latest name first, since that is where an install's files are."""
    support = home / "Library" / "Application Support"
    logs = home / "Library" / "Logs"
    places = [
        (support, "{}", "PhoneSimulator", "PHONESIMULATOR_STATE_DIR"),
        (logs, "{}", "PhoneSimulator", "PHONESIMULATOR_LOG_DIR"),
        (home, ".{}", "phonesimulator", "PHONESIMULATOR_RUN_DIR"),
    ]
    found: list[OldFolder] = []
    for old_name, link in (("Rocketwright", False), ("Simtrail", True)):
        for parent, shape, new_name, variable in places:
            old = shape.format(old_name if shape == "{}" else old_name.lower())
            found.append((parent / old, parent / shape.format(new_name), variable, link))
    return found


def move_folders(home: Path, env: MutableMapping[str, str]) -> tuple[list[tuple[Path, Path]], list[str]]:
    """Move each folder an old install left to PhoneSimulator's place. Answers what moved, and what could not be, said
    for a person."""
    moved: list[tuple[Path, Path]] = []
    problems: list[str] = []
    for old, new, variable, link in old_folders(home):
        if env.get(variable, "").strip():
            continue
        if old.is_symlink():
            problems.extend(_pointed_again(old, new) if link else [])
            continue
        if not old.is_dir() or new.exists():
            continue
        try:
            old.rename(new)
        except OSError as exc:
            problems.append(f"could not move {old} to {new}: {exc.strerror or exc}")
            continue
        moved.append((old, new))
        if link:
            try:
                old.symlink_to(new, target_is_directory=True)
            except OSError as exc:
                problems.append(f"moved {old} to {new}, but could not leave a link where it was: {exc.strerror or exc}")
    return moved, problems


def _pointed_again(link: Path, new: Path) -> list[str]:
    """Point a link an earlier move left at PhoneSimulator's folder, once that exists and the link leads nowhere any
    more -- Simtrail's, left pointing at Rocketwright's folder, which has just moved. Answers what could not be done."""
    if link.exists() or not new.is_dir():
        return []
    try:
        link.unlink()
        link.symlink_to(new, target_is_directory=True)
    except OSError as exc:
        return [f"could not point the link {link} at {new}: {exc.strerror or exc}"]
    return []


def adopt(env: MutableMapping[str, str], home: Path) -> list[str]:
    """Take up what an old install left: its environment first -- a variable may move a folder -- then its folders.
    Answers what could not be done."""
    adopt_environment(env)
    _, problems = move_folders(home, env)
    return problems
