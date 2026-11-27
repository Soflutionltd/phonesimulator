# SPDX-License-Identifier: Apache-2.0
"""Deleting the simulators PhoneSimulator made, once nobody needs them.

A scope with no device is given a blank simulator PhoneSimulator makes (`core.devices`); each takes 1.5-3.5 GB on disk,
and most are left empty once the agent is done. Two things delete them, and only them -- never a simulator a person made
or picked, a real device or an Android emulator:

* the reaper, as it ends a device left idle and shuts it down (`DeviceManager.reap`), when ``device.delete_created``
  allows: ``empty`` (the default) deletes one that holds no app anybody installed, ``idle`` deletes it whatever it
  holds, ``never`` keeps it. One another scope still remembers as its own is kept;
* ``phonesimulator devices prune``, once, for those already left: every one PhoneSimulator made that is not running and
  holds no app -- or, with ``--all``, every one not running -- through the daemon when it runs (it owns the memory),
  else directly.

Neither ever deletes a template new simulators are copied from (``device.templates``): it is never a scope's device,
so the reaper never ends it, and pruning passes it over -- ``--all`` too. Delete one in Xcode or with ``xcrun simctl
delete``; PhoneSimulator forgets it and makes another when it next needs one.

A device deleted is forgotten -- no longer made by PhoneSimulator, nor any scope's -- so the scope's next call makes a
fresh one. A deletion that fails is logged and remembered as it was: the device is still there, and still
PhoneSimulator's.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from phonesimulator.core.devices import CreatedDevices, DeviceTemplates
from phonesimulator.platform.device_data import folder_size, user_apps
from phonesimulator.platform.simctl import Simctl, SimctlError

logger = logging.getLogger(__name__)

#: Why a simulator PhoneSimulator made is kept by ``phonesimulator devices prune``.
RUNNING = "PhoneSimulator is running it"
#: The one state in which a simulator nothing runs may be deleted.
SHUTDOWN = "Shutdown"
NO_FOLDER = "its folder is not in Xcode's default device set, so what it holds cannot be told"


@dataclass(frozen=True)
class Pruned:
    """A simulator PhoneSimulator made, as pruning found it: deleted, to be deleted (a dry run), or kept and why."""

    udid: str
    name: str
    #: The apps installed on it, by their bundle's name.
    apps: tuple[str, ...]
    #: How many bytes its folder held: what deleting it frees.
    size: int
    deleted: bool
    #: Why it was kept; None for one deleted or to be.
    kept: str | None = None
    #: Why deleting it failed, when it did; it is then still there, and still remembered as PhoneSimulator's.
    error: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "udid": self.udid,
            "name": self.name,
            "apps": list(self.apps),
            "size": self.size,
            "deleted": self.deleted,
            "kept": self.kept,
            "error": self.error,
        }


def holding(count: int) -> str:
    """Why a simulator that holds apps is kept."""
    return f"it holds {count} app{'' if count == 1 else 's'} (--all deletes it too)"


async def delete(simctl: Simctl, memory: CreatedDevices, udid: str) -> str | None:
    """Delete a simulator PhoneSimulator made and forget it. Answers why it could not be, and then remembers it as it
    was."""
    try:
        await simctl.delete(udid)
    except SimctlError as exc:
        logger.warning("could not delete the simulator %s PhoneSimulator made: %s", udid, exc)
        return str(exc)
    memory.forget_created(udid)
    return None


async def prune(
    simctl: Simctl,
    memory: CreatedDevices,
    *,
    running: Collection[str],
    everything: bool,
    dry_run: bool,
    env: Mapping[str, str],
    home: Path | None = None,
) -> list[Pruned]:
    """Delete the simulators PhoneSimulator made that nothing runs -- PhoneSimulator, or a person who booted one -- and
    that hold no app, or every such one with `everything`. A `dry_run` deletes nothing and forgets nothing. One simctl
    no longer lists is forgotten, unsaid. Answers each one found, by UDID."""
    listed = {device.udid: device for device in await simctl.devices()}
    # A template new simulators are copied from is never pruned, --all or not (`core.devices`).
    templates = memory.all_templates() if isinstance(memory, DeviceTemplates) else set()
    found: list[Pruned] = []
    for udid in sorted(memory.all_created() - templates):
        device = listed.get(udid)
        if device is None:
            if not dry_run:
                memory.forget_created(udid)
            continue
        if udid in running or device.state != SHUTDOWN:
            why = RUNNING if udid in running else f"it is not shut down ({device.state})"
            found.append(Pruned(udid, device.name, (), 0, False, why))
            continue
        apps = user_apps(udid, env=env, home=home)
        if apps is None:
            found.append(Pruned(udid, device.name, (), 0, False, NO_FOLDER))
            continue
        size = folder_size(udid, env=env, home=home)
        if apps and not everything:
            found.append(Pruned(udid, device.name, tuple(apps), size, False, holding(len(apps))))
            continue
        failed = None if dry_run else await delete(simctl, memory, udid)
        found.append(Pruned(udid, device.name, tuple(apps), size, not dry_run and failed is None, error=failed))
    return found
