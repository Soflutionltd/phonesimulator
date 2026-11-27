# SPDX-License-Identifier: Apache-2.0
"""Fail if Xcode's or Android's tools, idb_companion or the native helper are named anywhere they could be started.

PhoneSimulator runs real programs: ``xcrun`` (simctl, xcodebuild, xcresulttool) boots devices, installs apps and builds
whatever project an agent points it at, and ``idb_companion`` and PhoneSimulator's own ``phonesimulator-helper`` stream
a device's screen and take its touches. The promises around them -- an argv and never a shell, a timeout that reaps, off
meaning stopped, no helper left behind -- hold only while one module owns each:

* `phonesimulator/platform/` runs xcrun, names the simctl subcommands, compiles Swift helpers (`platform.swift`),
  builds Swift packages (`platform.swiftpm`), reads a build folder's git checkout (`platform.git`) and signs a
  stamped simulator app again (`platform.codesign`);
* `phonesimulator/connectors/idb/companion.py` finds and starts idb_companion;
* `phonesimulator/connectors/native/helper.py` finds and starts phonesimulator-helper;
* `phonesimulator/build/xcodebuild.py` names the xcodebuild and xcresulttool calls, and `phonesimulator/build/wda.py`
  WebDriverAgent's;
* `phonesimulator/platform/` also runs adb, the Android emulator and Java (`platform.adb`, `platform.emulator`,
  `platform.java`), and `phonesimulator/build/gradle.py` runs a project's Gradle wrapper;
* `phonesimulator/platform/flutter.py` starts flutter, for a Flutter app's builds, tests and runs;
* `phonesimulator/connectors/simctl/` is the connector named after simctl;
* `phonesimulator/testing/` names them to refuse them (`guards`) and to play them (`fakes`).

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
    "phonesimulator-helper",
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
    # The password managers' CLIs, which reveal passwords: run only by `platform.passwords`.
    "op",
    "bw",
)

ALLOWED = (
    "src/phonesimulator/platform/",
    "src/phonesimulator/connectors/idb/companion.py",
    "src/phonesimulator/connectors/native/helper.py",
    "src/phonesimulator/build/xcodebuild.py",
    "src/phonesimulator/build/gradle.py",
    "src/phonesimulator/build/wda.py",
    "src/phonesimulator/connectors/simctl/",
    "src/phonesimulator/testing/",
)

SCAN_DIRS = ("src", "examples", "benchmarks")


def offenders() -> list[tuple[str, int, str]]:
    found = _containment.offenders(REPO_ROOT, SCAN_DIRS, ALLOWED, PROGRAMS)
    mac = _containment.offenders(
        REPO_ROOT,
        SCAN_DIRS,
        ("src/phonesimulator/platform/macos.py", "src/phonesimulator/testing/"),
        ("open", "osascript", "lsappinfo", "defaults", "pbpaste"),
    )
    simulator_commands = _containment.offenders(
        REPO_ROOT,
        SCAN_DIRS,
        (
            "src/phonesimulator/platform/macos.py",
            "src/phonesimulator/platform/simctl.py",
            "src/phonesimulator/testing/",
        ),
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
        "\nRun xcrun, simctl, swiftc and git through phonesimulator/platform/, start idb_companion only through "
        "phonesimulator/connectors/idb/companion.py and phonesimulator-helper only through "
        "phonesimulator/connectors/native/helper.py, run adb, the emulator, Java and flutter through "
        "phonesimulator/platform/, and "
        "build through phonesimulator/build/xcodebuild.py or phonesimulator/build/gradle.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
