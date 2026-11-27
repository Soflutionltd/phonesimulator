# SPDX-License-Identifier: Apache-2.0
"""Where a simulator keeps its data on the Mac.

Every simulator in Xcode's default device set has a folder of its own, ``~/Library/Developer/CoreSimulator/Devices/
<udid>/data``, which its apps see as ``SIMULATOR_SHARED_RESOURCES_DIRECTORY``. An app built with PhoneSimulator's debug
SDK says there where it listens (`connectors.app`). PhoneSimulator only uses the default set, so the folder is worked
out rather than asked of simctl, which would cost a program run on every snapshot.

What a person installed on a simulator is kept in its folder too, under ``data/Containers/Bundle/Application``; the
system's own apps come with the runtime and are not there. So whether a simulator holds an app of anybody's can be read
while it is shut down, which simctl cannot answer (`user_apps`).

``PHONESIMULATOR_SIMULATOR_DEVICES_DIR`` moves the devices folder, which is how tests keep away from the Mac's real one.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from phonesimulator.platform.simctl import is_udid

DEVICES_DIR_ENV = "PHONESIMULATOR_SIMULATOR_DEVICES_DIR"


def devices_dir(env: Mapping[str, str], home: Path | None = None) -> Path:
    """The folder that holds every simulator of Xcode's default device set."""
    raw = env.get(DEVICES_DIR_ENV, "").strip()
    if raw:
        return Path(raw).expanduser()
    return (home if home is not None else Path.home()) / "Library" / "Developer" / "CoreSimulator" / "Devices"


def device_data_dir(udid: str, *, env: Mapping[str, str], home: Path | None = None) -> Path:
    """A simulator's data folder. Anything but a device id is refused, so no path can be made to reach elsewhere."""
    if not is_udid(udid):
        raise ValueError(f"not a simulator device id: {udid!r}")
    return devices_dir(env, home) / udid / "data"


def device_dir(udid: str, *, env: Mapping[str, str], home: Path | None = None) -> Path:
    """A simulator's own folder, its data and its settings. Anything but a device id is refused."""
    return device_data_dir(udid, env=env, home=home).parent


def user_apps(udid: str, *, env: Mapping[str, str], home: Path | None = None) -> list[str] | None:
    """The apps installed on a simulator -- by anybody, not the system's own -- by their bundle's name, sorted. None
    when it cannot be told: the simulator has no folder here -- another device set's, or one already gone."""
    folder = device_dir(udid, env=env, home=home)
    if not folder.is_dir():
        return None
    return sorted(app.name for app in (folder / "data" / "Containers" / "Bundle" / "Application").glob("*/*.app"))


def folder_size(udid: str, *, env: Mapping[str, str], home: Path | None = None) -> int:
    """How many bytes a simulator's folder holds -- what deleting it frees -- not following links; 0 without one."""
    total = 0
    for root, _, files in os.walk(device_dir(udid, env=env, home=home)):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                continue
    return total
