# SPDX-License-Identifier: Apache-2.0
"""Building, testing and running a Flutter app, for an iOS simulator or an Android device.

A folder whose ``pubspec.yaml`` depends on flutter is a Flutter app: `runner.Runner` gives its runs to
`FlutterToolchain` whatever the device, rather than to xcodebuild or Gradle, which would find no project at its top.
Run in the project folder with the flutter command `platform.flutter` finds, measured with Flutter 3.47:

    flutter build ios --simulator --debug                                   sim_build_run, for a simulator
    flutter build apk --debug                                               sim_build_run, for an Android device
    flutter test [paths] --file-reporter json:<results>                     sim_test: unit and widget tests
    flutter test integration_test -d <device> --no-uninstall --file-reporter …     sim_test integration: true
    flutter run --machine -d <device> --debug                               sim_flutter run (`flutter_run`)

each with ``--flavor <flavor>`` and ``--dart-define-from-file <file>`` when the call names them. The values the Dart
code reads with ``String.fromEnvironment`` go in that file -- written only for the run, readable only by this user, and
deleted once flutter is done -- never on a command line, where any process on the Mac could read them.

**What it answers**: a build's app -- ``Runner.app``, whose bundle id is in its Info.plist, or the APK its output
metadata names (`gradle.built_app`) -- is installed and launched as an Xcode build's is (`provider`), held to
``build.expected_bundle_id``; a compile that fails is read from what flutter printed (`flutter_log.read_log`); tests
from the JSON file their reporter wrote (`flutter_log.read_tests`). A ``run`` answers once the app has started, and
stays running for the agent's hot reloads (`flutter_run.FlutterSession`).

**Which app a run installs**: ``flutter run`` and an integration test install the app themselves, so with
``build.expected_bundle_id`` set they are refused before they start when the project's own files -- the iOS project's
``PRODUCT_BUNDLE_IDENTIFIER``, the Android app's ``applicationId`` -- do not name it. An integration test keeps the app
installed after it (``--no-uninstall``): flutter would otherwise uninstall it, and everything it had on the device.

**What it does not build**: a real iPhone, or a Mac, which need signing Simtrail leaves to the person; ``scheme``,
``project``, ``workspace`` and ``test_plan`` name Xcode's and mean nothing here; flutter test has no retries and leaves
no test out by name.
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from simtrail.build import stamp
from simtrail.build.flutter_log import read_log, read_tests
from simtrail.build.flutter_run import FlutterSession, FlutterSessions, StartingRun
from simtrail.build.gradle import built_app
from simtrail.build.runner import Build, BuildRefused, Place, Project, Request, test_ids
from simtrail.build.xcresult import SuiteSummary, render_build, render_tests
from simtrail.host_copy import HostCopy
from simtrail.platform.codesign import resign_adhoc
from simtrail.platform.errors import DeviceControlError
from simtrail.platform.flutter import FlutterSdk, find_flutter, looked_in, open_flutter_run, start_flutter
from simtrail.platform.identifiers import PHONE_PREFIX, kind_of
from simtrail.platform.java import Jdk, find_jdk
from simtrail.platform.process import signal_group as signal_process_group
from simtrail.platform.xcrun import XcrunRunner, run_xcrun
from simtrail.scope import Scope
from simtrail.seams import StateStore

PUBSPEC = "pubspec.yaml"
#: A pubspec's dependency on Flutter itself: ``flutter:`` with ``sdk: flutter`` under it.
_DEPENDS = re.compile(r"^[ \t]+flutter:[ \t]*(?:#[^\n]*)?\n[ \t]+sdk:[ \t]*flutter\b", re.M)
_NAME = re.compile(r"^name:[ \t]*['\"]?([A-Za-z_]\w*)", re.M)
#: The largest pubspec read: a real one is a few kilobytes.
PUBSPEC_MAX = 1024 * 1024
MODES = ("debug", "profile", "release")
FLAVOR_MAX = 64
_FLAVOR = re.compile(rf"\A[A-Za-z][A-Za-z0-9_-]{{0,{FLAVOR_MAX - 1}}}\Z")
#: A ``--dart-define`` name, as ``String.fromEnvironment`` reads it.
_DEFINE = re.compile(r"\A[A-Za-z_][A-Za-z0-9_.]{0,127}\Z")
DEFINES_MAX = 50
DEFINE_VALUE_MAX = 4096
#: Where a run's dart-defines and its tests' results are kept, in its results folder.
DEFINES_FILE = "dart-defines.json"
RESULTS_FILE = "results.json"
#: The folders a project's tests are in, by kind.
UNIT_TESTS = "test"
INTEGRATION_TESTS = "integration_test"
#: Where flutter leaves a simulator build, unless its output names another.
IOS_APP = Path("build/ios/iphonesimulator/Runner.app")
_BUILT = re.compile(r"Built (\S+\.app)\b")
#: The Android app's build folder flutter uses, and the APK outputs AGP writes in it.
ANDROID_BUILD = Path("build/app")
ANDROID_OUTPUTS = Path("outputs/apk")
#: The app ids a project's own files name, for each platform.
_BUNDLE_ID = re.compile(r'PRODUCT_BUNDLE_IDENTIFIER = "?([A-Za-z0-9.-]+)"?;')
_APPLICATION_ID = re.compile(r"""applicationId\s*=?\s*["']([\w.]+)["']""")
IOS_PROJECT = Path("ios/Runner.xcodeproj/project.pbxproj")
ANDROID_APP_FILES = (Path("android/app/build.gradle.kts"), Path("android/app/build.gradle"))
_TEST_PATH_EXAMPLE = "test/login_test.dart, or integration_test/app_test.dart with integration"

SerialOf = Callable[[str], Awaitable[str]]


class FlutterStarter(Protocol):
    """How a flutter build or test run is started: `platform.flutter.start_flutter`, or a fake."""

    async def __call__(
        self, sdk: FlutterSdk, args: Sequence[str], *, folder: Path, log_path: Path, env: Mapping[str, str]
    ) -> Any: ...


class RunOpener(Protocol):
    """How ``flutter run --machine`` is started: `platform.flutter.open_flutter_run`, or a fake."""

    async def __call__(self, sdk: FlutterSdk, args: Sequence[str], *, folder: Path, env: Mapping[str, str]) -> Any: ...


def _read(path: Path, limit: int = PUBSPEC_MAX) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def is_flutter_project(folder: Path) -> bool:
    """Whether a folder holds a Flutter app: a ``pubspec.yaml`` that depends on flutter."""
    return bool(_DEPENDS.search(_read(folder / PUBSPEC)))


def project_name(folder: Path) -> str:
    """The name the pubspec gives the app, or its folder's."""
    found = _NAME.search(_read(folder / PUBSPEC))
    return found.group(1) if found else folder.name


def project_ids(folder: Path, device_kind: str) -> set[str]:
    """The app ids a Flutter project's own files name for a platform: the iOS app's bundle ids, its tests' left out;
    the Android app's ``applicationId``."""
    if device_kind == "android":
        return {found for path in ANDROID_APP_FILES for found in _APPLICATION_ID.findall(_read(folder / path))}
    named = _BUNDLE_ID.findall(_read(folder / IOS_PROJECT, 16 * PUBSPEC_MAX))
    return {found for found in named if not found.endswith("Tests")}


def _mode(configuration: object, device_kind: str, kind: str) -> str:
    """The build mode a call's ``configuration`` names: debug unless it says another a run of this kind can use."""
    if configuration is None:
        return "debug"
    if not isinstance(configuration, str) or configuration.lower() not in MODES:
        raise BuildRefused(
            f"configuration is a Flutter build mode, {', '.join(MODES)}, not {configuration!r} (name one with "
            "configuration, or change build.configuration)"
        )
    mode = configuration.lower()
    if mode != "debug" and kind == "run":
        raise BuildRefused("a hot reload needs a debug build: leave configuration out, or name debug")
    if mode != "debug" and kind == "test":
        raise BuildRefused("a Flutter app's tests run in a debug build: leave configuration out, or name debug")
    if mode != "debug" and device_kind == "simulator":
        raise BuildRefused("an iOS simulator runs only a debug build of a Flutter app: leave configuration out")
    return mode


def _flavor(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or not _FLAVOR.match(value):
        raise BuildRefused("flavor names one of the app's flavors, as flutter --flavor takes it: dev, staging")
    return value


def _define_value(value: object) -> bool:
    return isinstance(value, str) and len(value) <= DEFINE_VALUE_MAX and "\x00" not in value


def _defines(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not (
        isinstance(value, dict)
        and len(value) <= DEFINES_MAX
        and all(isinstance(name, str) and _DEFINE.match(name) for name in value)
        and all(_define_value(said) for said in value.values())
    ):
        raise BuildRefused(
            f"dart_defines is at most {DEFINES_MAX} names and their values, as the Dart code reads them with "
            f'String.fromEnvironment: {{"API_URL": "https://staging.example.com"}}; each value at most '
            f"{DEFINE_VALUE_MAX} characters"
        )
    return dict(value)


def _test_paths(values: object, folder: Path) -> list[str]:
    """The test files or folders a call's ``only_testing`` names, each inside the project."""
    paths = test_ids(values, "only_testing", _TEST_PATH_EXAMPLE)
    top = folder.resolve()
    for path in paths:
        found = (folder / path).resolve()
        if Path(path).is_absolute() or not found.is_relative_to(top) or not found.exists():
            raise BuildRefused(
                f"{path} is not a test file or folder of this Flutter app; only_testing names them from its folder: "
                f"{_TEST_PATH_EXAMPLE}"
            )
    return paths


def _write_defines(folder: Path, defines: Mapping[str, str]) -> Path:
    """The run's dart-defines in a file only this user can read."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / DEFINES_FILE
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(dict(defines), file)
    return path


def _discard(path: Path | None) -> None:
    if path is not None:
        path.unlink(missing_ok=True)


class FlutterProcess:
    """A flutter run as `runner.Runner` sees a process: timed, and its dart-defines deleted once it is done."""

    def __init__(self, process: Any, defines: Path | None, clock: Callable[[], float] = time.monotonic) -> None:
        self._process = process
        self._defines = defines
        self._clock = clock
        self._began = clock()
        self.seconds: float | None = None

    @property
    def pid(self) -> int:
        return int(self._process.pid)

    @property
    def returncode(self) -> int | None:
        code = self._process.returncode
        return None if code is None else int(code)

    async def wait(self) -> int:
        try:
            code = int(await self._process.wait())
        finally:
            _discard(self._defines)
            self._defines = None
        self.seconds = round(self._clock() - self._began, 1)
        return code


@dataclass(frozen=True)
class Plan:
    """How a prepared run is started."""

    sdk: FlutterSdk
    args: tuple[str, ...]
    defines: Path | None
    owner: str


class FlutterToolchain:
    """flutter, building, testing and running a Flutter app for a simulator or an Android device."""

    name = "flutter"

    def __init__(
        self,
        sessions: FlutterSessions,
        serial_of: SerialOf,
        *,
        find: Callable[[str], FlutterSdk | None] = find_flutter,
        start: FlutterStarter = start_flutter,
        open_run: RunOpener = open_flutter_run,
        jdk: Callable[[str], Awaitable[Jdk | None]] = find_jdk,
        xcrun: XcrunRunner = run_xcrun,
        copy: HostCopy | None = None,
        clock: Callable[[], float] = time.monotonic,
        signal_group: Callable[[int, int], None] = signal_process_group,
    ) -> None:
        self.sessions = sessions
        self._serial_of = serial_of
        self._find = find
        self._start = start
        self._open_run = open_run
        self._jdk = jdk
        self._xcrun = xcrun
        self._copy = copy or HostCopy()
        self._clock = clock
        self._signal = signal_group
        self._plans: dict[str, Plan] = {}

    def claims(self, folder: Path) -> bool:
        return is_flutter_project(folder)

    def _refuse_xcode_names(self, request: Request) -> None:
        for name, value in (
            ("scheme", request.scheme),
            ("project", request.project),
            ("workspace", request.workspace),
            ("test_plan", request.test_plan),
        ):
            if value is not None:
                raise BuildRefused(
                    f"{name} names Xcode's; a Flutter app is built from its pubspec.yaml, a flavor of it chosen with "
                    f"flavor, so leave {name} out"
                )
        if request.retries:
            raise BuildRefused("a Flutter app's tests run once each: leave retries out")
        if request.skip_testing is not None:
            raise BuildRefused(
                "a Flutter app's tests are not left out by name: name the files to run with only_testing"
            )
        if request.kind != "test" and (request.integration or request.only_testing is not None):
            raise BuildRefused("integration and only_testing are for sim_test")

    def _check_app(self, request: Request) -> None:
        """Refuse a run that installs the app when the project names another than ``build.expected_bundle_id``."""
        expected = request.expected_bundle_id
        installs = request.kind == "run" or (request.kind == "test" and request.integration)
        if not expected or not installs:
            return
        named = project_ids(request.folder, request.device_kind)
        if expected not in named:
            platform = "Android app" if request.device_kind == "android" else "iOS project"
            said = ", ".join(sorted(named)) or "no app id"
            raise BuildRefused(
                f"this Flutter app's {platform} names {said}, not {expected}, the app build.expected_bundle_id names, "
                "so nothing was started or installed: change build.expected_bundle_id, or build it with sim_build_run, "
                "which checks the app it built"
            )

    async def _env(self, request: Request) -> dict[str, str]:
        env: dict[str, str] = {}
        if request.device_kind == "android":
            if request.developer_dir:
                env["ANDROID_HOME"] = request.developer_dir
            jdk = await self._jdk(request.java_home)
            if jdk is not None:
                env["JAVA_HOME"] = str(jdk.home)
        elif request.developer_dir:
            env["DEVELOPER_DIR"] = request.developer_dir
        return env

    async def _device(self, request: Request) -> str:
        """The device as flutter's ``-d`` names it: a simulator's udid, an Android device's adb serial."""
        if request.device_kind != "android":
            return request.udid
        try:
            return await self._serial_of(request.udid)
        except DeviceControlError as exc:
            raise BuildRefused(f"the app runs only on a running device: {exc}") from exc

    async def prepare(self, scope: Scope, request: Request, place: Place, state: StateStore) -> Build:
        if request.device_kind not in ("simulator", "android"):
            raise BuildRefused(
                "a Flutter app is built here for an iOS simulator or an Android device; for a real iPhone or a Mac, "
                "build it from your shell with flutter, which signs it, then install it with sim_app"
            )
        self._refuse_xcode_names(request)
        mode = _mode(request.configuration, request.device_kind, request.kind)
        flavor = _flavor(request.flavor)
        defines = _defines(request.dart_defines)
        only = _test_paths(request.only_testing, request.folder) if request.kind == "test" else []
        sdk = self._find(request.flutter_path)
        if sdk is None:
            raise BuildRefused(
                f"no flutter command was found (looked in {looked_in()}): name it with build.flutter_path "
                f"({self._copy.settings}), or install Flutter"
            )
        self._check_app(request)
        on_device = request.kind == "run" or (request.kind == "test" and request.integration)
        device = await self._device(request) if on_device else ""
        defines_file = _write_defines(place.base, defines) if defines else None
        common = ["--flavor", flavor] if flavor else []
        if defines_file is not None:
            common.append(f"--dart-define-from-file={defines_file}")
        results = f"json:{place.base / RESULTS_FILE}"
        if request.kind == "build":
            target = ["apk"] if request.device_kind == "android" else ["ios", "--simulator"]
            args = ["build", *target, f"--{mode}", *common]
        elif request.kind == "run":
            args = ["run", "--machine", "-d", device, f"--{mode}", *common]
        elif request.integration:
            args = ["test", *(only or [INTEGRATION_TESTS]), "-d", device, "--no-uninstall"]
            args += ["--file-reporter", results, *common]
        else:
            args = ["test", *only, "--file-reporter", results, *common]
        place.base.mkdir(parents=True, exist_ok=True)
        name = project_name(request.folder)
        build = Build(
            id=place.build_id,
            scope=scope,
            kind=request.kind,
            project=Project("pubspec", request.folder / PUBSPEC),
            scheme=f"{name}, flavor {flavor}" if flavor else name,
            configuration=mode,
            udid=request.udid,
            developer_dir=request.developer_dir,
            folder=request.folder,
            derived=request.folder / "build",
            bundle=place.base,
            log=place.base.with_suffix(".log"),
            started=place.started,
            warnings=request.warnings,
            device=request.device,
            only=tuple(only),
            env=await self._env(request),
        )
        self._plans[build.id] = Plan(sdk, tuple(args), defines_file, request.owner)
        return build

    async def launch(self, build: Build, request: Request) -> Any:
        plan = self._plans.pop(build.id)
        if build.kind != "test" or request.integration:
            # What flutter installs replaces the app a session runs there.
            await self.sessions.stop_device(build.udid)
        try:
            if build.kind == "run":
                process = await self._open_run(plan.sdk, plan.args, folder=build.folder, env=build.env)
            else:
                process = await self._start(plan.sdk, plan.args, folder=build.folder, log_path=build.log, env=build.env)
        except OSError:
            _discard(plan.defines)
            raise
        if build.kind != "run":
            return FlutterProcess(process, plan.defines, self._clock)
        session = FlutterSession(
            process,
            scope=build.scope,
            udid=build.udid,
            folder=build.folder,
            log_path=build.log,
            label=build.label,
            build_id=build.id,
            owner=plan.owner,
            clock=self._clock,
            signal_group=self._signal,
        )
        session.begin()
        self.sessions.add(session)
        return FlutterProcess(StartingRun(session), plan.defines, self._clock)

    def _log(self, build: Build) -> str:
        try:
            return build.log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def _built(self, build: Build, log: str) -> tuple[Path, str] | None:
        """The app a build made and its id: the APK its output metadata names, or the simulator app flutter said it
        built, with its Info.plist's bundle id."""
        if kind_of(build.udid) == "android":
            flavor = build.scheme.split(", flavor ", 1)[1] if ", flavor " in build.scheme else ""
            variant = f"{flavor}{build.configuration.capitalize()}" if flavor else build.configuration
            return built_app(build.folder / ANDROID_BUILD, variant, outputs=ANDROID_OUTPUTS)
        said = _BUILT.findall(log)
        app = build.folder / (said[-1] if said else IOS_APP)
        try:
            info = plistlib.loads((app / "Info.plist").read_bytes())
        except (OSError, plistlib.InvalidFileException, ValueError):
            return None
        bundle_id = info.get("CFBundleIdentifier") if isinstance(info, dict) else None
        return (app, bundle_id) if isinstance(bundle_id, str) and bundle_id else None

    async def results(self, build: Build) -> list[str]:
        process = build.process
        code, seconds = process.returncode, process.seconds
        log = self._log(build)
        if build.kind == "build":
            summary = read_log(log, succeeded=code == 0, seconds=seconds)
            build.state = "succeeded" if summary.succeeded else "failed"
            if summary.succeeded:
                found = self._built(build, log)
                build.app, build.bundle_id = found if found is not None else (None, None)
            return render_build(summary, label=build.label, root=build.folder, warnings=build.warnings)
        if build.kind == "run":
            if code == 0:
                build.state, build.installed, build.launched = "succeeded", True, True
                took = f" · {seconds:g}s" if seconds is not None else ""
                return [
                    f"run ok · {build.label}{took} · the app runs on the device: sim_flutter hot_reload or hot_restart "
                    "puts your saved changes on it, stop ends it"
                ]
            build.state = "failed"
            summary = read_log(log, succeeded=False, seconds=seconds)
            return render_build(summary, label=build.label, root=build.folder, warnings=build.warnings, kind="run")
        build.state = "failed"
        tests = read_tests(build.bundle / RESULTS_FILE, seconds)
        if tests is None:
            if code == 0:
                build.state = "succeeded"
                return render_tests(SuiteSummary(True, 0, 0, 0, (), seconds), label=build.label, root=build.folder)
            summary = read_log(log, succeeded=False, seconds=seconds)
            return render_build(summary, label=build.label, root=build.folder, warnings=build.warnings, kind="test")
        lines = render_tests(tests, label=build.label, root=build.folder)
        if tests.passed and code != 0:
            # Every test passed, and flutter failed all the same: building for the device, or after the tests.
            lines += [f"error {error.message}" for error in read_log(log, succeeded=False, seconds=seconds).errors]
            return lines
        build.state = "succeeded" if tests.passed else "failed"
        return lines

    async def stamped(self, build: Build) -> tuple[Path, str]:
        """The app to install, with the commit it was built from (`stamp`) -- or as built, and why it carries none."""
        assert build.app is not None and build.bundle_id is not None, "only a build that made an app is installed"
        if build.udid.startswith(f"{PHONE_PREFIX}-"):
            return build.app, "not stamped: Simtrail writes nothing to an Android phone but the app it installs"
        if build.commit is None:
            return build.app, f"not stamped: git named no commit for {build.folder}"
        mark = stamp.Stamp(build.commit, build.dirty)
        if build.app.suffix == ".apk":
            try:
                folder = stamp.stamp_apk(build.app, mark, build.bundle_id)
            except stamp.StampRefused as exc:
                return build.app, f"not stamped: {exc}"
            return folder, f"stamped {stamp.described(mark)}, kept on the device beside the app (the APK is unchanged)"

        async def resign(app: Path) -> str | None:
            return await resign_adhoc(app, developer_dir=build.developer_dir, xcrun=self._xcrun)

        try:
            copy = await stamp.stamp_app(build.app, mark, resign)
        except stamp.StampRefused as exc:
            return build.app, f"not stamped: {exc}"
        return copy, f"stamped {stamp.described(mark)} into its Info.plist ({stamp.SHA_KEY})"
