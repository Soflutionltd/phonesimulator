# SPDX-License-Identifier: Apache-2.0
"""flutter for tests: a Flutter app's files, a build or test run that writes what flutter would, and a ``flutter run
--machine`` that speaks the Flutter daemon's protocol.

`flutter_project` lays out an app's shape; `FakeFlutter` is a `flutter.FlutterStarter` and `FakeFlutterRun` a
`flutter.RunOpener`. What they write and say is what Flutter 3.47 wrote and said (``fixtures/flutter-*``).
"""

from __future__ import annotations

import asyncio
import json
import plistlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rocketwright.platform.flutter import FlutterSdk
from rocketwright.testing.fakes import FakeProcess, fixture

#: The app ids the example app's projects name.
IOS_ID = "dev.rocketwright.groceries"
ANDROID_ID = "dev.rocketwright.groceries"
SDK = FlutterSdk(Path("/opt/homebrew/share/flutter/bin/flutter"), "PATH")
#: What a hot reload whose code does not compile prints on stderr, as Flutter 3.47 did.
COMPILE_ERROR = (
    "lib/main.dart:133:46: Error: Expected an identifier, but got ','.",
    "Try inserting an identifier before ','.",
    "      child: Text(Labels.retry +, style: labelStyle),",
    "                               ^",
)


def flutter_project(
    folder: Path, name: str = "groceries", *, ios_id: str = IOS_ID, android_id: str = ANDROID_ID
) -> Path:
    """A Flutter app in `folder`: its pubspec, its iOS and Android projects naming their app ids, and a test of each
    kind."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "pubspec.yaml").write_text(
        f"name: {name}\nenvironment:\n  sdk: ^3.9.0\n\ndependencies:\n  flutter:\n    sdk: flutter\n\n"
        "dev_dependencies:\n  flutter_test:\n    sdk: flutter\n\nflutter:\n  uses-material-design: true\n"
    )
    project = folder / "ios" / "Runner.xcodeproj"
    project.mkdir(parents=True, exist_ok=True)
    (project / "project.pbxproj").write_text(
        f"PRODUCT_BUNDLE_IDENTIFIER = {ios_id};\nPRODUCT_BUNDLE_IDENTIFIER = {ios_id}.RunnerTests;\n"
    )
    app = folder / "android" / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "build.gradle.kts").write_text(f'android {{\n    defaultConfig {{\n        applicationId = "{android_id}"\n')
    for path in ("test/list_test.dart", "integration_test/app_test.dart", "lib/main.dart"):
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_text("void main() {}\n")
    return folder


@dataclass
class Play:
    """What one flutter build or test run does."""

    rc: int = 0
    log: str = ""
    #: Writes the app a build makes: a simulator app with this bundle id, or an APK with its metadata.
    app: str | None = None
    #: What the tests' JSON reporter writes; None when no test ran.
    results: str | None = None
    #: Keeps running until a test finishes it, or it is ended.
    hold: bool = False


@dataclass(frozen=True)
class FlutterCall:
    args: tuple[str, ...]
    folder: Path
    log_path: Path | None
    env: dict[str, str]
    #: The dart-defines file the call named, read as it started -- it is deleted once flutter is done.
    defines: dict[str, str] | None = None


def _defines(args: Sequence[str]) -> dict[str, str] | None:
    named = next((arg.split("=", 1)[1] for arg in args if arg.startswith("--dart-define-from-file=")), None)
    return None if named is None else dict(json.loads(Path(named).read_text()))


@dataclass
class FakeFlutter:
    """Plays ``flutter build`` and ``flutter test``: each call does the next `Play` queued with `then`, else succeeds
    quietly."""

    calls: list[FlutterCall] = field(default_factory=list)
    processes: list[FakeProcess] = field(default_factory=list)
    signals: list[tuple[int, int]] = field(default_factory=list)
    start_error: OSError | None = None
    _plays: list[Play] = field(default_factory=list)

    def then(self, play: Play) -> FakeFlutter:
        self._plays.append(play)
        return self

    async def __call__(
        self, sdk: FlutterSdk, args: Sequence[str], *, folder: Path, log_path: Path, env: Mapping[str, str]
    ) -> FakeProcess:
        if self.start_error is not None:
            raise self.start_error
        self.calls.append(FlutterCall(tuple(args), folder, log_path, dict(env), _defines(args)))
        play = self._plays.pop(0) if self._plays else Play()
        if play.app is not None and "apk" in args:
            outputs = folder / "build/app/outputs/apk/debug"
            outputs.mkdir(parents=True, exist_ok=True)
            (outputs / "app-debug.apk").write_bytes(b"APK")
            metadata = json.loads(fixture("gradle-output-metadata.json"))
            metadata["applicationId"] = play.app
            (outputs / "output-metadata.json").write_text(json.dumps(metadata))
        elif play.app is not None:
            app = folder / "build/ios/iphonesimulator/Runner.app"
            app.mkdir(parents=True, exist_ok=True)
            (app / "Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": play.app}))
            play.log += "✓ Built build/ios/iphonesimulator/Runner.app\n"
        if play.results is not None:
            reporter = args[list(args).index("--file-reporter") + 1].removeprefix("json:")
            Path(reporter).write_text(play.results)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(play.log)
        process = FakeProcess(6000 + len(self.processes))
        self.processes.append(process)
        if not play.hold:
            process.finish(play.rc)
        return process

    def signal(self, pid: int, sig: int) -> None:
        self.signals.append((pid, sig))
        next(process for process in self.processes if process.pid == pid).finish(-sig)


@dataclass
class Reload:
    """What one hot reload or restart answers."""

    #: The compiler's lines flutter prints on stderr first; with any, the reload fails as a compile error does.
    errors: tuple[str, ...] = ()
    message: str = "Reloaded 1 of 865 libraries"
    #: Answers nothing at all.
    silent: bool = False
    #: Answers with an error instead of a result.
    refused: str = ""


class _Stdin:
    def __init__(self, process: FakeRunProcess) -> None:
        self.process = process
        self.closed = False
        self.buffer = b""

    def write(self, data: bytes) -> None:
        if self.closed or self.process.returncode is not None:
            raise BrokenPipeError("flutter has stopped")
        self.buffer += data
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            for message in json.loads(line):
                self.process.run.receive(self.process, message)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True


class FakeRunProcess:
    """A ``flutter run --machine``: what it says is fed to its stdout and stderr as it would say it."""

    def __init__(self, run: FakeFlutterRun, pid: int) -> None:
        self.run = run
        self.pid = pid
        self.returncode: int | None = None
        self.stdin = _Stdin(self)
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()

    def say(self, *messages: Mapping[str, Any]) -> None:
        self.stdout.feed_data(json.dumps(list(messages)).encode() + b"\n")

    def line(self, text: str) -> None:
        self.stdout.feed_data(text.encode() + b"\n")

    def complain(self, *lines: str) -> None:
        for text in lines:
            self.stderr.feed_data(text.encode() + b"\n")

    def finish(self, rc: int = 0) -> None:
        if self.returncode is not None:
            return
        self.returncode = rc
        self.stdout.feed_eof()
        self.stderr.feed_eof()

    async def wait(self) -> int:
        while self.returncode is None:
            await asyncio.sleep(0)
        return self.returncode


APP_ID = "41ac4f0c-6ebe-4a52-9a2e-369ca2ff6674"


@dataclass
class FakeFlutterRun:
    """Plays ``flutter run --machine``: it builds, starts the app -- or fails to, saying `build_errors` -- then answers
    each hot reload with the next `Reload` queued, and stops when asked."""

    calls: list[FlutterCall] = field(default_factory=list)
    processes: list[FakeRunProcess] = field(default_factory=list)
    signals: list[tuple[int, int]] = field(default_factory=list)
    start_error: OSError | None = None
    #: Whether the app starts; when not, these lines are said on stderr and flutter exits 1.
    starts: bool = True
    build_errors: tuple[str, ...] = ()
    #: Whether it answers app.stop; when not, it has to be ended.
    stops: bool = True
    #: Whether the app starts as soon as flutter does, or only once `start` is called.
    starts_at_once: bool = True
    reloads: list[Reload] = field(default_factory=list)
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(
        self, sdk: FlutterSdk, args: Sequence[str], *, folder: Path, env: Mapping[str, str]
    ) -> FakeRunProcess:
        if self.start_error is not None:
            raise self.start_error
        self.calls.append(FlutterCall(tuple(args), folder, None, dict(env), _defines(args)))
        process = FakeRunProcess(self, 7000 + len(self.processes))
        self.processes.append(process)
        process.line("Resolving dependencies...")
        process.say({"event": "daemon.connected", "params": {"version": "0.6.1", "pid": process.pid}})
        process.say({"event": "app.start", "params": {"appId": APP_ID, "directory": str(folder)}})
        process.line("Launching lib/main.dart on iPhone 17 in debug mode...")
        if not self.starts:
            process.complain(*self.build_errors)
            process.finish(1)
        elif self.starts_at_once:
            self.start(process)
        return process

    def start(self, process: FakeRunProcess) -> None:
        process.say({"event": "app.started", "params": {"appId": APP_ID}})

    def receive(self, process: FakeRunProcess, message: dict[str, Any]) -> None:
        self.requests.append(message)
        method, ident = message.get("method"), message.get("id")
        if method == "app.stop":
            if self.stops:
                process.line("Application finished.")
                process.say({"id": ident, "result": True}, {"event": "app.stop", "params": {"appId": APP_ID}})
                process.finish(0)
            return
        play = self.reloads.pop(0) if self.reloads else Reload()
        if play.silent:
            return
        if play.refused:
            process.say({"id": ident, "error": play.refused})
            return
        process.complain(*play.errors)
        if play.errors:
            process.say({"id": ident, "result": {"code": 1, "message": "DevFS synchronization failed"}})
            return
        full = message.get("params", {}).get("fullRestart")
        process.line("Restarted application in 241ms." if full else f"{play.message} in 167ms.")
        process.say({"id": ident, "result": {"code": 0, "message": "" if full else play.message}})

    def signal(self, pid: int, sig: int) -> None:
        self.signals.append((pid, sig))
        next(process for process in self.processes if process.pid == pid).finish(-sig)
