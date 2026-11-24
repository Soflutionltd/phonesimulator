# SPDX-License-Identifier: Apache-2.0
"""Where a simulator keeps its data on the Mac.

Every simulator in Xcode's default device set has a folder of its own, ``~/Library/Developer/CoreSimulator/Devices/
<udid>/data``, which its apps see as ``SIMULATOR_SHARED_RESOURCES_DIRECTORY``. An app built with Simtrail's debug SDK
says there where it listens (`connectors.app`). Simtrail only uses the default set, so the folder is worked out rather
than asked of simctl, which would cost a program run on every snapshot.

``SIMTRAIL_SIMULATOR_DEVICES_DIR`` moves the devices folder, which is how tests keep away from the Mac's real one.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from simtrail.platform.simctl import is_udid

DEVICES_DIR_ENV = "SIMTRAIL_SIMULATOR_DEVICES_DIR"


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
