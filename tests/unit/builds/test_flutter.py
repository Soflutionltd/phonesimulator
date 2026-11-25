# SPDX-License-Identifier: Apache-2.0
"""Building, testing and running a Flutter app with flutter, for a simulator or an Android device, answered as an
Xcode build is."""

from __future__ import annotations

import asyncio
import json
import plistlib
import signal
import stat
import time
from pathlib import Path
from typing import Any

import pytest

from simtrail.build.flutter import (
    DEFINES_FILE,
    RESULTS_FILE,
    FlutterToolchain,
    is_flutter_project,
    project_ids,
    project_name,
)
from simtrail.build.flutter_run import FlutterSessions
from simtrail.build.runner import Build, BuildRefused, Runner
from simtrail.build.source import Source
from simtrail.build.stamp import APK_STAMP, SHA_KEY
from simtrail.platform.adb import AdbError
from simtrail.platform.flutter import FlutterSdk
from simtrail.platform.java import Jdk
from simtrail.platform.xcrun import XcrunResult
from simtrail.testing.fakes import MemoryStateStore, fixture
from simtrail.testing.flutter import (
    ANDROID_ID,
    COMPILE_ERROR,
    IOS_ID,
    SDK,
    FakeFlutter,
    FakeFlutterRun,
    Play,
    flutter_project,
)
from simtrail.testing.rig import scope

SCOPE = scope("topic-1", "ws")
SIMULATOR = "8592C53F-15E4-41BC-BE49-D19F08BE74BE"
EMULATOR = "avd-Pixel-9-fa39dd"
PHONE = "adb-R58M12ABC-9b1e04"
DEVELOPER = "/Applications/Xcode.app/Contents/Developer"
ANDROID_SDK = "/Users/dev/Library/Android/sdk"
JDK = Jdk(Path("/opt/jdk"), "android.java_home")


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.folder = flutter_project(tmp_path / "groceries")
        self.flutter = FakeFlutter()
        self.run = FakeFlutterRun()
        self.sessions = FlutterSessions()
        self.sdk: FlutterSdk | None = SDK
        self.asked: list[str] = []
        self.jdk: Jdk | None = JDK
        self.reachable = True
        self.commit: str | None = "c" * 40
        self.resigned: list[tuple[str, ...]] = []
        #: What looking for the JDK, or reading the source, raises instead of answering.
        self.jdk_error: BaseException | None = None
        self.source_error: BaseException | None = None
        #: Set once the source is being read, which then waits to be cancelled.
        self.reading: asyncio.Event | None = None
        self.toolchain = FlutterToolchain(
            self.sessions,
            self.serial_of,
            find=self.find,
            start=self.flutter,
            open_run=self.run,
            jdk=self.find_jdk,
            xcrun=self.xcrun,
            # Its own clock too: a build's time is said, and real time would make it 0.1s on a busy machine.
            clock=lambda: 100.0,
            signal_group=self.signal,
        )
        self.runner = Runner(
            MemoryStateStore(tmp_path),
            {},
            clock=lambda: 100.0,
            wall=lambda: 0.0,
            signal_group=self.signal,
            stop_grace_s=0.01,
            source=self.read_source,
            projects=(self.toolchain,),
        )

    def find(self, configured: str) -> FlutterSdk | None:
        self.asked.append(configured)
        return self.sdk

    async def find_jdk(self, configured: str) -> Jdk | None:
        if self.jdk_error is not None:
            raise self.jdk_error
        return self.jdk

    async def serial_of(self, udid: str) -> str:
        if not self.reachable:
            raise AdbError(f"{udid} is not running or not reachable through adb now")
        return "emulator-5554"

    async def xcrun(self, *args: str, timeout: float, developer_dir: str = "") -> XcrunResult:
        self.resigned.append(args)
        return XcrunResult(0, "", "")

    def signal(self, pid: int, sig: int) -> None:
        (self.run if pid >= 7000 else self.flutter).signal(pid, sig)

    async def read_source(self, folder: Path) -> Source:
        if self.source_error is not None:
            raise self.source_error
        if self.reading is not None:
            self.reading.set()
            await asyncio.Event().wait()
        return Source(f"source {folder} · main @ {(self.commit or 'none')[:8]}", self.commit)

    async def begin(self, kind: str = "build", **options: Any) -> Build:
        udid = options.pop("udid", SIMULATOR)
        return await self.runner.start(
            options.pop("scope", SCOPE),
            kind=kind,
            folder=options.pop("folder", self.folder),
            udid=udid,
            developer_dir=options.pop("developer_dir", ANDROID_SDK if udid.startswith(("avd-", "adb-")) else DEVELOPER),
            timeout_s=options.pop("timeout_s", 60),
            device_kind=options.pop("device_kind", "android" if udid.startswith(("avd-", "adb-")) else "simulator"),
            **options,
        )

    async def answer(self, kind: str = "build", **options: Any) -> tuple[Build, list[str]]:
        build = await self.begin(kind, **options)
        said = await self.runner.result(SCOPE.id, build.id, 5)
        return build, said.splitlines()

    def args(self) -> list[tuple[str, ...]]:
        return [call.args for call in self.flutter.calls]

    def defines_left(self) -> list[str]:
        """Every dart-defines file still on disk, and every run prepared that was not launched."""
        files = self.runner.derived_data(SCOPE).parent.parent.rglob(DEFINES_FILE)
        return [*(path.name for path in files), *self.toolchain._plans]


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


# -- which project ---------------------------------------------------------------------------------------------------


def test_a_flutter_app_is_a_pubspec_that_depends_on_flutter(tmp_path: Path) -> None:
    assert not is_flutter_project(tmp_path)
    (tmp_path / "pubspec.yaml").write_text("name: tool\ndependencies:\n  path: ^1.9.0\n")
    assert not is_flutter_project(tmp_path) and project_name(tmp_path) == "tool"
    flutter_project(tmp_path, "notes")
    assert is_flutter_project(tmp_path) and project_name(tmp_path) == "notes"
    (tmp_path / "pubspec.yaml").write_text("dependencies:\n  flutter: # the SDK\n    sdk: flutter\n")
    assert is_flutter_project(tmp_path) and project_name(tmp_path) == tmp_path.name


def test_the_app_ids_a_project_names_leave_its_tests_out(tmp_path: Path) -> None:
    flutter_project(tmp_path)
    assert project_ids(tmp_path, "simulator") == {IOS_ID}
    assert project_ids(tmp_path, "android") == {ANDROID_ID}
    (tmp_path / "android/app/build.gradle.kts").unlink()
    (tmp_path / "android/app/build.gradle").write_text("defaultConfig {\n  applicationId 'dev.example.old'\n}\n")
    assert project_ids(tmp_path, "android") == {"dev.example.old"}


def test_a_pubspec_far_too_large_is_not_read(tmp_path: Path) -> None:
    flutter_project(tmp_path)
    (tmp_path / "pubspec.yaml").write_text("dependencies:\n  flutter:\n    sdk: flutter\n" + "#" * (1024 * 1024))
    assert not is_flutter_project(tmp_path)


# -- builds ----------------------------------------------------------------------------------------------------------


async def test_a_simulator_build_is_flutters_and_its_app_is_read_from_what_it_built(rig: Rig) -> None:
    rig.flutter.then(Play(app=IOS_ID))
    build, said = await rig.answer(flutter_path="/opt/flutter", dart_defines={"API_URL": "https://x.test"})
    assert said[0] == "build ok · groceries (debug) · 0s · 0 errors, 0 warnings" and rig.asked == ["/opt/flutter"]
    (call,) = rig.flutter.calls
    assert call.args[:4] == ("build", "ios", "--simulator", "--debug") and call.folder == rig.folder
    assert call.args[4] == f"--dart-define-from-file={build.bundle / DEFINES_FILE}"
    assert call.defines == {"API_URL": "https://x.test"} and call.env == {"DEVELOPER_DIR": DEVELOPER}
    # The values were in a file only while flutter ran, and never on its command line.
    assert not (build.bundle / DEFINES_FILE).exists() and "https://x.test" not in " ".join(call.args)
    assert build.app == rig.folder / "build/ios/iphonesimulator/Runner.app" and build.bundle_id == IOS_ID
    assert (build.state, build.project.args) == ("succeeded", ("pubspec", str(rig.folder / "pubspec.yaml")))


async def test_an_android_build_is_an_apk_with_the_sdk_and_jdk_and_its_package_from_agps_metadata(rig: Rig) -> None:
    rig.flutter.then(Play(app=ANDROID_ID))
    build, said = await rig.answer(udid=EMULATOR, configuration="Release", flavor="dev")
    assert said[0].startswith("build ok · groceries, flavor dev (release)")
    assert rig.args() == [("build", "apk", "--release", "--flavor", "dev")]
    assert rig.flutter.calls[0].env == {"ANDROID_HOME": ANDROID_SDK, "JAVA_HOME": "/opt/jdk"}
    # The metadata names the debug variant: a release build of the dev flavor left none of its own.
    assert build.app is None
    rig.jdk = None
    rig.flutter.then(Play(app=ANDROID_ID))
    build, _ = await rig.answer(udid=EMULATOR, developer_dir="")
    assert build.app == rig.folder / "build/app/outputs/apk/debug/app-debug.apk" and build.bundle_id == ANDROID_ID
    assert rig.flutter.calls[1].env == {}


async def test_a_build_that_does_not_compile_answers_with_its_errors(rig: Rig) -> None:
    rig.flutter.then(Play(rc=1, log=fixture("flutter-build-ios-error.log")))
    build, said = await rig.answer(warnings=True)
    assert said[:3] == [
        "build FAILED · groceries (debug) · 0s · 1 error, 1 warning",
        "error lib/screens/list_screen.dart:96:35 Member not found: 'nope'.",
        "warning lib/screens/list_screen.dart:12:8 Operand of null-aware operation '?.' has type 'String' which "
        "excludes null.",
    ]
    assert build.state == "failed" and build.app is None


async def test_a_simulator_build_whose_app_cannot_be_read_installs_nothing(rig: Rig) -> None:
    build, _ = await rig.answer()
    assert build.state == "succeeded" and build.app is None
    app = rig.folder / "build/ios/iphonesimulator/Runner.app"
    app.mkdir(parents=True)
    (app / "Info.plist").write_bytes(plistlib.dumps(["not", "a", "dictionary"]))
    build, _ = await rig.answer()
    assert build.app is None


# -- what is refused -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("options", "refused"),
    [
        ({"device_kind": "physical", "udid": "00008150-000C59982620401C"}, "built here for an iOS simulator or"),
        ({"scheme": "Runner"}, "scheme names Xcode's"),
        ({"workspace": "ios/Runner.xcworkspace"}, "workspace names Xcode's"),
        ({"configuration": "Staging"}, "configuration is a Flutter build mode"),
        ({"configuration": 3}, "configuration is a Flutter build mode"),
        ({"configuration": "release"}, "an iOS simulator runs only a debug build"),
        ({"flavor": "no flavor"}, "flavor names one of the app's flavors"),
        ({"dart_defines": {"1BAD": "x"}}, "dart_defines is at most 50 names"),
        ({"dart_defines": {"OK": 1}}, "dart_defines is at most 50 names"),
        ({"dart_defines": ["A=1"]}, "dart_defines is at most 50 names"),
        ({"integration": True}, "integration and only_testing are for sim_test"),
    ],
)
async def test_a_build_flutter_cannot_make_is_refused_before_it_starts(
    rig: Rig, options: dict[str, Any], refused: str
) -> None:
    with pytest.raises(BuildRefused, match=refused):
        await rig.begin(**options)
    assert rig.flutter.calls == []


@pytest.mark.parametrize(
    ("kind", "options", "refused"),
    [
        ("test", {"retries": 1}, "run once each: leave retries out"),
        ("test", {"skip_testing": ["test/list_test.dart"]}, "not left out by name"),
        ("test", {"test_plan": "Smoke"}, "test_plan names Xcode's"),
        ("test", {"configuration": "profile"}, "tests run in a debug build"),
        ("test", {"only_testing": ["test/missing_test.dart"]}, "is not a test file or folder of this Flutter app"),
        ("test", {"only_testing": ["../elsewhere"]}, "is not a test file or folder of this Flutter app"),
        ("test", {"only_testing": "test"}, "only_testing is a list of at most 50 tests"),
        ("run", {"configuration": "profile"}, "a hot reload needs a debug build"),
    ],
)
async def test_a_test_run_or_a_run_flutter_cannot_make_is_refused(
    rig: Rig, kind: str, options: dict[str, Any], refused: str
) -> None:
    with pytest.raises(BuildRefused, match=refused):
        await rig.begin(kind, **options)


async def test_without_a_flutter_command_nothing_is_started(rig: Rig) -> None:
    rig.sdk = None
    with pytest.raises(BuildRefused, match=r"no flutter command was found \(looked in build.flutter_path, PATH, "):
        await rig.begin()


async def test_a_flutter_that_cannot_be_started_leaves_no_dart_defines(rig: Rig) -> None:
    rig.flutter.start_error = OSError("no such file")
    with pytest.raises(BuildRefused, match="flutter could not be started: no such file"):
        await rig.begin(dart_defines={"TOKEN": "t"})
    assert list(rig.runner.derived_data(SCOPE).parent.parent.rglob(DEFINES_FILE)) == []
    rig.run.start_error = OSError("gone")
    with pytest.raises(BuildRefused, match="flutter could not be started: gone"):
        await rig.begin("run", dart_defines={"TOKEN": "t"})
    assert list(rig.runner.derived_data(SCOPE).parent.parent.rglob(DEFINES_FILE)) == []


async def test_a_run_that_fails_while_it_is_prepared_leaves_no_dart_defines(rig: Rig) -> None:
    rig.jdk_error = RuntimeError("the JDK could not be looked for")
    with pytest.raises(RuntimeError, match="the JDK could not be looked for"):
        await rig.begin(udid=EMULATOR, dart_defines={"TOKEN": "t"})
    assert rig.defines_left() == []


async def test_a_run_whose_source_cannot_be_read_leaves_no_dart_defines(rig: Rig) -> None:
    rig.source_error = RuntimeError("git answered nothing readable")
    with pytest.raises(RuntimeError, match="git answered nothing readable"):
        await rig.begin(dart_defines={"TOKEN": "t"})
    assert rig.defines_left() == [] and rig.flutter.calls == []


async def test_a_run_cancelled_before_flutter_starts_leaves_no_dart_defines(rig: Rig) -> None:
    rig.reading = asyncio.Event()
    starting = asyncio.ensure_future(rig.begin(dart_defines={"TOKEN": "t"}))
    await rig.reading.wait()
    assert rig.defines_left() == [DEFINES_FILE, "b1"], "written and its run prepared, while the source is read"
    starting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await starting
    assert rig.defines_left() == [] and rig.flutter.calls == []
    rig.reading = None
    assert (await rig.answer(dart_defines={"TOKEN": "t"}))[0].state == "succeeded", "the next run is not held up"


async def test_dart_defines_that_cannot_be_written_whole_are_not_left_in_part(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(value: object, file: Any) -> None:
        file.write('{"TOKEN": ')
        raise OSError("no space left on device")

    monkeypatch.setattr("simtrail.build.flutter.json.dump", full)
    with pytest.raises(OSError, match="no space left on device"):
        await rig.begin(dart_defines={"TOKEN": "t"})
    assert rig.defines_left() == []


@pytest.mark.parametrize("kind", ["build", "run"])
async def test_a_run_that_fails_as_it_is_launched_leaves_no_dart_defines(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    async def stop_device(udid: str) -> bool:
        raise RuntimeError("the app running there could not be stopped")

    monkeypatch.setattr(rig.sessions, "stop_device", stop_device)
    with pytest.raises(RuntimeError, match="could not be stopped"):
        await rig.begin(kind, dart_defines={"TOKEN": "t"})
    assert rig.defines_left() == [] and rig.flutter.calls == [] and rig.run.calls == []


@pytest.mark.parametrize("left", ["a file others can read", "a link to another file"])
async def test_dart_defines_are_written_anew_for_this_user_alone_whatever_was_there(
    rig: Rig, tmp_path: Path, left: str
) -> None:
    store = MemoryStateStore(tmp_path)
    base = store.ensure_dir(store.builds_dir(SCOPE)) / f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(0.0))}-b1"
    base.mkdir()
    other = tmp_path / "someone-elses.json"
    other.write_text("theirs")
    other.chmod(0o644)
    if left == "a link to another file":
        (base / DEFINES_FILE).symlink_to(other)
    else:
        (base / DEFINES_FILE).write_text("{}")
        (base / DEFINES_FILE).chmod(0o644)
    rig.flutter.then(Play(hold=True))
    build = await rig.begin(dart_defines={"TOKEN": "t"})
    written = build.bundle / DEFINES_FILE
    assert build.bundle == base and not written.is_symlink()
    assert stat.S_IMODE(written.stat().st_mode) == 0o600 and json.loads(written.read_text()) == {"TOKEN": "t"}
    assert other.read_text() == "theirs", "what a link named is left as it was"
    assert (await rig.runner.result(SCOPE.id, build.id, 0)).startswith("build b1 still running")
    await rig.runner.cancel(SCOPE.id)
    assert rig.defines_left() == []


async def test_a_build_that_runs_too_long_is_ended_and_its_dart_defines_go_with_it(rig: Rig) -> None:
    rig.flutter.then(Play(hold=True))
    build = await rig.begin(timeout_s=0.01, dart_defines={"TOKEN": "t"})
    said = await rig.runner.result(SCOPE.id, build.id, 5)
    assert said.startswith("build b1 was stopped after 0s") and rig.flutter.signals[0] == (6000, signal.SIGTERM)
    assert not (build.bundle / DEFINES_FILE).exists()


async def test_a_run_cancelled_as_soon_as_it_starts_is_ended_and_frees_its_folder(rig: Rig) -> None:
    rig.flutter.then(Play(hold=True))
    build = await rig.begin(dart_defines={"TOKEN": "t"})
    # Nothing awaited since: the task watching the run has not taken its first step.
    assert await rig.runner.cancel(SCOPE.id) is True
    assert rig.flutter.signals == [(6000, signal.SIGTERM)] and rig.runner.runs() == []
    assert build.state == "cancelled" and rig.defines_left() == []
    assert (await rig.runner.result(SCOPE.id, build.id, 0)).startswith("build b1 was cancelled")
    assert (await rig.answer())[0].state == "succeeded", "the folder is free for the next run"


async def test_flavor_dart_defines_and_integration_are_for_a_flutter_app_only(rig: Rig, tmp_path: Path) -> None:
    other = tmp_path / "Notes"
    other.mkdir()
    with pytest.raises(BuildRefused, match=r"flavor, integration are for a Flutter app, and .*Notes holds none"):
        await rig.begin("test", folder=other, flavor="dev", integration=True)
    with pytest.raises(BuildRefused, match=r"dart_defines is for a Flutter app"):
        await rig.begin(folder=other, dart_defines={"A": "1"})
    with pytest.raises(BuildRefused, match=r"holds no Flutter app .* which is what sim_flutter runs"):
        await rig.begin("run", folder=other)
    with pytest.raises(BuildRefused, match="nothing here builds for this simulator device"):
        await rig.begin(folder=other)


async def test_a_run_that_installs_another_app_than_the_expected_one_is_refused(rig: Rig) -> None:
    with pytest.raises(BuildRefused, match=f"iOS project names {IOS_ID}, not dev.example.notes, the app"):
        await rig.begin("run", expected_bundle_id="dev.example.notes")
    with pytest.raises(BuildRefused, match=f"Android app names {ANDROID_ID}, not dev.example.notes"):
        await rig.begin("test", integration=True, udid=EMULATOR, expected_bundle_id="dev.example.notes")
    (rig.folder / "android/app/build.gradle.kts").unlink()
    with pytest.raises(BuildRefused, match="Android app names no app id, not"):
        await rig.begin("run", udid=EMULATOR, expected_bundle_id="dev.example.notes")
    # Unit tests install nothing; a run of the expected app starts.
    rig.flutter.then(Play(results=fixture("flutter-unit-results.json")))
    await rig.answer("test", expected_bundle_id="dev.example.notes")
    _, said = await rig.answer("run", expected_bundle_id=IOS_ID)
    assert said[0].startswith("run ok")


# -- tests -----------------------------------------------------------------------------------------------------------


async def test_unit_tests_run_on_the_mac_and_answer_with_their_counts_and_failures(rig: Rig) -> None:
    rig.flutter.then(Play(rc=1, results=fixture("flutter-unit-results.json")))
    build, said = await rig.answer("test", only_testing=["test/list_test.dart"], flavor="dev")
    assert rig.args() == [
        ("test", "test/list_test.dart", "--file-reporter", f"json:{build.bundle / RESULTS_FILE}", "--flavor", "dev")
    ]
    assert said[:2] == [
        "test FAILED · groceries, flavor dev (debug) · 2 passed, 1 failed, 1 skipped · 0s",
        "fail adds an item test/list_test.dart:24 Expected: empty",
    ]
    assert build.state == "failed" and build.only == ("test/list_test.dart",)


async def test_a_test_run_with_no_tests_or_none_that_built_says_so(rig: Rig) -> None:
    build, said = await rig.answer("test")
    assert said[0] == "test ok · groceries (debug) · 0 passed, 0 failed, 0 skipped · 0s" and build.state == "succeeded"
    rig.flutter.then(Play(rc=1, log="test/list_test.dart:3:1: Error: Expected ';' after this.\n"))
    build, said = await rig.answer("test")
    assert said[:2] == [
        "test FAILED · groceries (debug) · the tests did not build · 0s · 1 error, 0 warnings",
        "error test/list_test.dart:3:1 Expected ';' after this.",
    ]
    assert build.state == "failed"


async def test_tests_that_passed_in_a_run_that_failed_say_why_it_failed(rig: Rig) -> None:
    passed = "\n".join(line for line in fixture("flutter-unit-results.json").splitlines() if '"testID":4' not in line)
    rig.flutter.then(Play(rc=1, results=passed, log="Error: Unable to install the app.\n"))
    build, said = await rig.answer("test")
    assert said[1] == "error Unable to install the app." and build.state == "failed"
    rig.flutter.then(Play(results=passed))
    build, said = await rig.answer("test")
    assert (
        said[0].startswith("test ok · groceries (debug) · 2 passed, 0 failed, 1 skipped") and build.state == "succeeded"
    )


async def test_integration_tests_run_on_the_device_and_keep_the_app_installed(rig: Rig) -> None:
    rig.flutter.then(Play(results=fixture("flutter-integration-results.json")))
    _, said = await rig.answer("test", integration=True)
    assert rig.args()[0][:5] == ("test", "integration_test", "-d", SIMULATOR, "--no-uninstall")
    assert said[1].startswith("fail adds an item from the first screen /Users/dev/groceries/integration_test/app_test")
    rig.flutter.then(Play(results=fixture("flutter-integration-results.json")))
    await rig.answer("test", integration=True, udid=EMULATOR, only_testing=["integration_test/app_test.dart"])
    assert rig.args()[1][:4] == ("test", "integration_test/app_test.dart", "-d", "emulator-5554")
    rig.reachable = False
    with pytest.raises(BuildRefused, match="the app runs only on a running device: avd-Pixel-9-fa39dd is not running"):
        await rig.begin("test", integration=True, udid=EMULATOR)


# -- runs ------------------------------------------------------------------------------------------------------------


async def test_a_run_answers_once_the_app_has_started_and_keeps_it_running_for_its_agent(rig: Rig) -> None:
    build, said = await rig.answer("run", owner="agent-1", dart_defines={"A": "1"})
    assert said[0] == (
        "run ok · groceries (debug) · 0s · the app runs on the device: sim_flutter hot_reload or hot_restart puts "
        "your saved changes on it, stop ends it"
    )
    (call,) = rig.run.calls
    assert call.args[:5] == ("run", "--machine", "-d", SIMULATOR, "--debug") and call.defines == {"A": "1"}
    assert (build.state, build.installed, build.launched) == ("succeeded", True, True)
    session = rig.sessions.on(SCOPE.id, SIMULATOR)
    assert session is not None and session.alive and session.owner == "agent-1" and session.build_id == build.id
    assert not (build.bundle / DEFINES_FILE).exists()
    # A build installed on the device replaces the app the run keeps.
    rig.flutter.then(Play(app=IOS_ID))
    await rig.answer()
    assert not session.alive and rig.sessions.on(SCOPE.id, SIMULATOR) is None
    assert rig.run.requests[-1]["method"] == "app.stop"


async def test_a_run_on_an_android_device_names_it_by_its_serial(rig: Rig) -> None:
    await rig.answer("run", udid=EMULATOR)
    assert rig.run.calls[0].args[:4] == ("run", "--machine", "-d", "emulator-5554")
    assert rig.run.calls[0].env == {"ANDROID_HOME": ANDROID_SDK, "JAVA_HOME": "/opt/jdk"}


async def test_a_run_that_does_not_build_answers_with_the_compilers_errors(rig: Rig) -> None:
    rig.run.starts, rig.run.build_errors = False, COMPILE_ERROR
    build, said = await rig.answer("run")
    assert said[:2] == [
        "run FAILED · groceries (debug) · 0s · 1 error, 0 warnings",
        "error lib/main.dart:133:46 Expected an identifier, but got ','.",
    ]
    assert build.state == "failed" and not build.launched


async def test_a_run_still_building_after_its_timeout_is_ended(rig: Rig) -> None:
    rig.run.starts_at_once = False
    build = await rig.begin("run", timeout_s=0.05)
    said = await rig.runner.result(SCOPE.id, build.id, 5)
    assert said.startswith("run b1 was stopped after 0s")
    assert rig.run.signals == [(7000, signal.SIGTERM)]
    session = rig.sessions.on(SCOPE.id, SIMULATOR)
    assert session is not None and not session.alive


# -- stamps ----------------------------------------------------------------------------------------------------------


async def test_a_simulator_app_is_stamped_with_its_commit_into_a_copy(rig: Rig) -> None:
    rig.flutter.then(Play(app=IOS_ID))
    build, _ = await rig.answer()
    app, said = await rig.runner.stamped(build)
    assert said == f"stamped {'c' * 7} into its Info.plist ({SHA_KEY})"
    assert plistlib.loads((app / "Info.plist").read_bytes())[SHA_KEY] == "c" * 40
    signed = build.app
    assert signed is not None
    (signed / "_CodeSignature").mkdir()
    app, said = await rig.runner.stamped(build)
    assert said.startswith("stamped") and rig.resigned and rig.resigned[0][0] == "codesign"
    (signed / "Info.plist").write_bytes(plistlib.dumps(["no"]))
    app, said = await rig.runner.stamped(build)
    assert app == signed and said == "not stamped: Runner.app's Info.plist is not a dictionary"
    rig.commit = None
    rig.flutter.then(Play(app=IOS_ID))
    build, _ = await rig.answer()
    assert (await rig.runner.stamped(build))[1] == f"not stamped: git named no commit for {rig.folder}"


async def test_an_apk_is_stamped_beside_it_on_an_emulator_and_never_on_a_phone(rig: Rig) -> None:
    rig.flutter.then(Play(app=ANDROID_ID))
    build, _ = await rig.answer(udid=EMULATOR)
    folder, said = await rig.runner.stamped(build)
    assert said.startswith("stamped cccccc") and json.loads((folder / APK_STAMP).read_text())["package"] == ANDROID_ID
    assert build.app is not None
    build.app.unlink()
    folder, said = await rig.runner.stamped(build)
    assert said.startswith("not stamped: app-debug.apk could not be copied and stamped")
    rig.flutter.then(Play(app=ANDROID_ID))
    build, _ = await rig.answer(udid=PHONE)
    assert (await rig.runner.stamped(build))[1] == (
        "not stamped: Simtrail writes nothing to an Android phone but the app it installs"
    )


async def test_a_build_whose_log_is_gone_is_read_from_nothing(rig: Rig) -> None:
    rig.flutter.then(Play(hold=True))
    build = await rig.begin()
    build.log.unlink()
    rig.flutter.processes[0].finish(0)
    assert (await rig.runner.result(SCOPE.id, build.id, 5)).startswith("build ok") and build.app is None


async def test_two_runs_on_one_device_are_not_started_at_once(rig: Rig) -> None:
    rig.flutter.then(Play(hold=True))
    first = await rig.begin()
    with pytest.raises(BuildRefused, match="build b1 is still running here"):
        await rig.begin("test")
    rig.flutter.processes[0].finish(0)
    await asyncio.wait_for(rig.runner.result(SCOPE.id, first.id, 5), 5)
