# SPDX-License-Identifier: Apache-2.0
"""Fail if Xcode's or Android's tools, idb_companion or the native helper are named anywhere they could be started.

Simtrail runs real programs: ``xcrun`` (simctl, xcodebuild, xcresulttool) boots devices, installs apps and builds
whatever project an agent points it at, and ``idb_companion`` and Simtrail's own ``simtrail-helper`` stream a
device's screen and take its touches. The promises around them -- an argv and never a shell, a timeout that reaps, off
meaning stopped, no helper left behind -- hold only while one module owns each:

* `simtrail/platform/` runs xcrun, names the simctl subcommands, compiles Swift helpers (`platform.swift`),
  builds Swift packages (`platform.swiftpm`), reads a build folder's git checkout (`platform.git`) and signs a
  stamped simulator app again (`platform.codesign`);
* `simtrail/connectors/idb/companion.py` finds and starts idb_companion;
* `simtrail/connectors/native/helper.py` finds and starts simtrail-helper;
* `simtrail/build/xcodebuild.py` names the xcodebuild and xcresulttool calls, and `simtrail/build/wda.py`
  WebDriverAgent's;
* `simtrail/platform/` also runs adb, the Android emulator and Java (`platform.adb`, `platform.emulator`,
  `platform.java`), and `simtrail/build/gradle.py` runs a project's Gradle wrapper;
* `simtrail/platform/flutter.py` starts flutter, for a Flutter app's builds, tests and runs;
* `simtrail/connectors/simctl/` is the connector named after simctl;
* `simtrail/testing/` names them to refuse them (`guards`) and to play them (`fakes`).

Anywhere else, a string that starts a command with one of them is refused (`_containment` says what starting a
command is). Run directly, or via `make lint`.
"""

from __future__ import annotations

import sys

import _containment
from _repo import REPO_ROOT

PROGRAMS = (
    "xcrun",
    "simctl",
    "devicectl",
    "xcodebuild",
    "xcresulttool",
    "idb_companion",
    "swiftc",
    "swift",
    "simtrail-helper",
    "git",
    "codesign",
    "adb",
    "emulator",
    "gradlew",
    "gradle",
    "flutter",
    "java",
    "open",
    "osascript",
    "lsappinfo",
    "log",
    "defaults",
    "pbcopy",
    "pbpaste",
)

ALLOWED = (
    "src/simtrail/platform/",
    "src/simtrail/connectors/idb/companion.py",
    "src/simtrail/connectors/native/helper.py",
    "src/simtrail/build/xcodebuild.py",
    "src/simtrail/build/gradle.py",
    "src/simtrail/build/wda.py",
    "src/simtrail/connectors/simctl/",
    "src/simtrail/testing/",
)

SCAN_DIRS = ("src", "examples", "benchmarks")


def offenders() -> list[tuple[str, int, str]]:
    found = _containment.offenders(REPO_ROOT, SCAN_DIRS, ALLOWED, PROGRAMS)
    mac = _containment.offenders(
        REPO_ROOT,
        SCAN_DIRS,
        ("src/simtrail/platform/macos.py", "src/simtrail/testing/"),
        ("open", "osascript", "lsappinfo", "defaults", "pbpaste"),
    )
    simulator_commands = _containment.offenders(
        REPO_ROOT,
        SCAN_DIRS,
        ("src/simtrail/platform/macos.py", "src/simtrail/platform/simctl.py", "src/simtrail/testing/"),
        ("log", "pbcopy"),
    )
    return sorted(set(found + mac + simulator_commands))


def main() -> int:
    found = offenders()
    if not found:
        print("containment ok: Xcode's tools and the device helpers are named only by the modules that run them")
        return 0
    print("an Xcode tool or a device helper is named outside the module that runs it:\n", file=sys.stderr)
    for rel, lineno, program in found:
        print(f"  {rel}:{lineno}: {program}", file=sys.stderr)
    print(
        "\nRun xcrun, simctl, swiftc and git through simtrail/platform/, start idb_companion only through "
        "simtrail/connectors/idb/companion.py and simtrail-helper only through "
        "simtrail/connectors/native/helper.py, run adb, the emulator, Java and flutter through simtrail/platform/, and "
        "build through simtrail/build/xcodebuild.py or simtrail/build/gradle.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
