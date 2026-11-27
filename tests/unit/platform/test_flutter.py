# SPDX-License-Identifier: Apache-2.0
"""Finding the flutter command, starting it with what a build needs on its PATH, and asking its version."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from phonesimulator.platform import flutter
from phonesimulator.platform.flutter import (
    FlutterSdk,
    find_flutter,
    flutter_env,
    flutter_version,
    looked_in,
    open_flutter_run,
    start_flutter,
)

SDK = FlutterSdk(Path("/sdk/flutter/bin/flutter"), "PATH")


def command(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_the_settings_name_the_command_or_its_sdk_and_nothing_else_is_used(tmp_path: Path) -> None:
    sdk = command(tmp_path / "sdk" / "bin" / "flutter")
    assert find_flutter(str(sdk), {}) == FlutterSdk(sdk, "build.flutter_path")
    assert find_flutter(str(tmp_path / "sdk"), {}) == FlutterSdk(sdk, "build.flutter_path")
    # A path that is no flutter is that answer, even with one on PATH.
    assert find_flutter(str(tmp_path / "nowhere"), {"PATH": str(sdk.parent)}) is None
    plain = tmp_path / "not-executable"
    plain.write_text("")
    assert find_flutter(str(plain), {}) is None


def test_path_comes_before_the_usual_places_and_none_is_none(tmp_path: Path) -> None:
    on_path = command(tmp_path / "bin" / "flutter")
    usual = command(tmp_path / "home" / "flutter" / "bin" / "flutter")
    places = (tmp_path / "opt" / "flutter", Path("~/flutter/bin/flutter"))
    assert find_flutter("", {"PATH": str(on_path.parent)}, tmp_path / "home", places=places) == FlutterSdk(
        on_path, "PATH"
    )
    assert find_flutter("", {"PATH": ""}, tmp_path / "home", places=places) == FlutterSdk(usual, "its usual place")
    assert find_flutter("", {}, tmp_path / "elsewhere", places=places) is None
    assert looked_in(places) == f"build.flutter_path, PATH, {tmp_path / 'opt' / 'flutter'}, ~/flutter/bin/flutter"


def test_flutter_runs_with_its_own_folder_first_and_the_build_tools_folders_after() -> None:
    env = flutter_env(SDK, {"PATH": "/usr/bin:/custom", "HOME": "/Users/dev"})
    assert env["HOME"] == "/Users/dev"
    assert env["PATH"].split(os.pathsep) == [
        "/sdk/flutter/bin",
        "/usr/bin",
        "/custom",
        "/opt/homebrew/bin",
        "/usr/local/bin",
        "/bin",
    ]
    assert flutter_env(SDK, {})["PATH"].startswith("/sdk/flutter/bin:")


async def test_its_version_is_read_from_what_it_says_after_setting_itself_up() -> None:
    answers: list[tuple[int, str]] = [
        (0, 'Downloading Material fonts...\n{"frameworkVersion": "3.47.5", "dartSdkVersion": "3.13.4"}'),
        (0, '{"frameworkVersion": "3.47.5"}'),
        (1, ""),
        (0, "no json"),
        (0, "{not json"),
        (0, '{"channel": "stable"}'),
        (0, "{}"),
    ]
    asked: list[Sequence[str]] = []

    async def runner(argv: Sequence[str]) -> tuple[int, str]:
        asked.append(argv)
        return answers.pop(0)

    said = [await flutter_version(SDK, runner=runner) for _ in range(7)]
    assert said == ["3.47.5 (Dart 3.13.4)", "3.47.5", None, None, None, None, None]
    assert asked[0] == ["/sdk/flutter/bin/flutter", "--version", "--machine"]


async def test_its_version_is_asked_with_a_long_enough_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Sequence[str], float]] = []

    async def run(argv: Sequence[str], *, timeout: float) -> tuple[int, str]:
        calls.append((argv, timeout))
        return 0, '{"frameworkVersion": "3.47.5"}'

    monkeypatch.setattr(flutter, "run", run)
    assert await flutter_version(SDK) == "3.47.5"
    assert calls == [(["/sdk/flutter/bin/flutter", "--version", "--machine"], flutter.VERSION_TIMEOUT_S)]


async def test_a_build_is_started_with_its_log_and_a_run_with_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spawned: list[tuple[list[str], Path, dict[str, Any]]] = []

    async def spawn(argv: list[str], log_path: Path, **options: Any) -> str:
        spawned.append((argv, log_path, options))
        return "process"

    opened: list[tuple[tuple[str, ...], dict[str, Any]]] = []

    async def create(*argv: str, **options: Any) -> str:
        opened.append((argv, options))
        return "run"

    monkeypatch.setattr(flutter, "spawn", spawn)
    monkeypatch.setattr(flutter.asyncio, "create_subprocess_exec", create)
    monkeypatch.setenv("PATH", "/usr/bin")
    started = await start_flutter(SDK, ["build", "apk"], folder=tmp_path, log_path=tmp_path / "b.log", env={"A": "1"})
    ((argv, log_path, options),) = spawned
    assert started == "process" and argv == ["/sdk/flutter/bin/flutter", "build", "apk"]
    assert log_path == tmp_path / "b.log" and options["cwd"] == tmp_path
    assert options["env"]["A"] == "1" and options["env"]["PATH"].startswith("/sdk/flutter/bin:/usr/bin")
    assert await open_flutter_run(SDK, ["run", "--machine"], folder=tmp_path, env={"B": "2"}) == "run"
    ((argv_run, run_options),) = opened
    assert argv_run == ("/sdk/flutter/bin/flutter", "run", "--machine")
    assert run_options["start_new_session"] and run_options["cwd"] == str(tmp_path)
    assert run_options["env"]["B"] == "2" and run_options["limit"] == flutter.LINE_MAX
