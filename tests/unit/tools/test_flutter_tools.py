# SPDX-License-Identifier: Apache-2.0
"""The build tools on a Flutter app: flutter builds it and Simtrail installs and launches it, its tests run, and
`sim_flutter` keeps it running for hot reloads -- stopped when the agent's connection ends, when its scope may no
longer build, and when Simtrail stops."""

from __future__ import annotations

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

import pytest

from simtrail.build.flutter import FlutterToolchain
from simtrail.build.flutter_run import FlutterSessions
from simtrail.build.source import Source
from simtrail.build.xcodebuild import BuildRunner
from simtrail.core.actions import AgentActions
from simtrail.core.runtime import Runtime
from simtrail.platform.flutter import FlutterSdk
from simtrail.seams import Caller
from simtrail.testing.fakes import fixture, made, no_wait
from simtrail.testing.flutter import (
    COMPILE_ERROR,
    IOS_ID,
    SDK,
    FakeFlutter,
    FakeFlutterRun,
    Play,
    Reload,
    flutter_project,
)
from simtrail.testing.rig import DeviceRig, scope
from simtrail.testing.vision import FakeTextRecognizer
from simtrail.tools.context import ToolContext
from simtrail.tools.registry import ToolRegistry
from simtrail.tools.results import Result

CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude · groceries")
REGISTRY = ToolRegistry()


def said(result: Result) -> str:
    return str(result["content"][0]["text"])


class FlutterRig:
    def __init__(self, tmp_path: Path) -> None:
        self.sim = DeviceRig(tmp_path)
        self.sim.xcrun.on("simctl", "launch", out=f"{IOS_ID}: 81234\n")
        self.folder = flutter_project(tmp_path / "groceries")
        self.flutter = FakeFlutter()
        self.run = FakeFlutterRun()
        self.sessions = FlutterSessions()
        self.sdk: FlutterSdk | None = SDK
        self.toolchain = FlutterToolchain(
            self.sessions,
            self.serial_of,
            find=lambda configured: self.sdk,
            start=self.flutter,
            open_run=self.run,
            xcrun=self.sim.xcrun,
            signal_group=self.signal,
        )
        self.runner = BuildRunner(
            self.sim.state,
            xcrun=self.sim.xcrun,
            source=self.source,
            signal_group=self.signal,
            projects=(self.toolchain,),
        )
        self.actions = AgentActions(self.sim.manager, self.sim.config, clock=self.sim.clock, sleep=no_wait)

    async def serial_of(self, udid: str) -> str:
        return "emulator-5554"

    def signal(self, pid: int, sig: int) -> None:
        (self.run if pid >= 7000 else self.flutter).signal(pid, sig)

    async def source(self, folder: Path) -> Source:
        return Source(f"source {folder} · main @ 1a2b3c4", "1a2b3c4d" * 5)

    def context(self, **changes: Any) -> ToolContext:
        config = dataclasses.replace(self.sim.config.get(CALLER.scope), build_tools=True)
        ctx = ToolContext(
            manager=self.sim.manager,
            actions=self.actions,
            caller=CALLER,
            config=config,
            sleep=no_wait,
            builds=self.runner,
            folder=self.folder,
            shells_allowed=True,
            flutter=self.sessions,
        )
        return dataclasses.replace(ctx, **changes)

    async def call(self, name: str, arguments: dict[str, Any], **changes: Any) -> Result:
        return await REGISTRY.call(name, arguments, self.context(**changes))


@pytest.fixture
def rig(tmp_path: Path) -> FlutterRig:
    return FlutterRig(tmp_path)


async def test_a_flutter_app_is_built_by_flutter_then_installed_and_launched_on_the_simulator(rig: FlutterRig) -> None:
    rig.flutter.then(Play(app=IOS_ID))
    answer = await rig.call("sim_build_run", {"dart_defines": {"API_URL": "https://staging.example.com"}})
    lines = said(answer).splitlines()
    assert answer["isError"] is False and lines[:3] == [
        "build ok · groceries (debug) · 0s · 0 errors, 0 warnings",
        "installed Runner.app",
        f"launched {IOS_ID} (pid 81234)",
    ]
    assert rig.flutter.calls[0].args[:4] == ("build", "ios", "--simulator", "--debug")
    assert any(args[1] == "install" and made(1) in args for args in rig.sim.argv())


async def test_a_flutter_build_of_another_app_than_the_expected_one_is_not_installed(rig: FlutterRig) -> None:
    rig.sim.config.set(build_expected_bundle_id="dev.example.notes")
    rig.flutter.then(Play(app=IOS_ID))
    lines = said(await rig.call("sim_build_run", {})).splitlines()
    assert lines[1].startswith(f"not launched: groceries (debug) builds {IOS_ID}, not dev.example.notes")
    refused = await rig.call("sim_flutter", {"action": "run"})
    assert refused["isError"] and "not dev.example.notes, the app build.expected_bundle_id names" in said(refused)


async def test_flutter_unit_tests_and_integration_tests_answer_their_counts(rig: FlutterRig) -> None:
    rig.flutter.then(Play(rc=1, results=fixture("flutter-unit-results.json")))
    answer = await rig.call("sim_test", {})
    assert answer["isError"] and said(answer).startswith("test FAILED · groceries (debug) · 2 passed, 1 failed")
    rig.flutter.then(Play(results=fixture("flutter-integration-results.json")))
    await rig.call("sim_test", {"integration": True, "flavor": "dev"})
    assert rig.flutter.calls[1].args[:4] == ("test", "integration_test", "-d", made(1))
    refused = await rig.call("sim_test", {"integration": "yes"})
    assert said(refused) == "integration is true or false"


async def test_sim_flutter_runs_the_app_reloads_it_restarts_it_and_stops_it(rig: FlutterRig) -> None:
    started = await rig.call("sim_flutter", {"action": "run", "configuration": "release"})
    assert started["isError"] is False and said(started).startswith("run ok · groceries (debug)")
    assert started["structuredContent"]["kind"] == "run" and started["structuredContent"]["launched"] is True
    status = await rig.call("sim_flutter", {"action": "status"})
    assert said(status).startswith(f"groceries (debug) is running on the device (b1), from {rig.folder}")
    assert status["structuredContent"] == {"running": True, "started": True, "build_id": "b1"}
    reloaded = await rig.call("sim_flutter", {"action": "hot_reload"})
    assert said(reloaded) == "hot reload ok · groceries (debug) · 0s · Reloaded 1 of 865 libraries"
    assert reloaded["structuredContent"] == {"ok": True, "errors": 0, "seconds": 0.0}
    rig.run.reloads.append(Reload(errors=COMPILE_ERROR))
    failed = await rig.call("sim_flutter", {"action": "hot_reload"})
    assert failed["isError"] and said(failed).splitlines() == [
        "hot reload FAILED · groceries (debug) · 0s · DevFS synchronization failed",
        "error lib/main.dart:133:46 Expected an identifier, but got ','.",
        "the app keeps the code it had: fix what failed, save, and call again",
    ]
    restarted = await rig.call("sim_flutter", {"action": "hot_restart"})
    assert said(restarted) == "hot restart ok · groceries (debug) · 0s"
    rig.run.reloads.append(Reload(silent=True))
    session = rig.sessions.sessions()[0]
    session._request_timeout_s = 0.01
    lost = await rig.call("sim_flutter", {"action": "hot_reload"})
    assert said(lost) == "hot reload failed: no answer to app.restart within 0s"
    stopped = await rig.call("sim_flutter", {"action": "stop"})
    assert said(stopped).splitlines()[0] == "groceries (debug) stopped; flutter run has ended"
    assert said(await rig.call("sim_flutter", {"action": "hot_reload"})) == (
        "no Flutter app runs on your device from sim_flutter run: start one with action run"
    )


async def test_a_flutter_run_that_ended_by_itself_says_so(rig: FlutterRig) -> None:
    await rig.call("sim_flutter", {"action": "run"})
    session = rig.sessions.sessions()[0]
    assert isinstance(session.process.pid, int)
    session.process.finish(1)
    await asyncio.wait_for(session.ended.wait(), 5)
    status = await rig.call("sim_flutter", {"action": "status"})
    assert "is not running: the app's flutter run stopped (exit code 1)" in said(status)
    assert status["structuredContent"]["running"] is False
    reload = await rig.call("sim_flutter", {"action": "hot_restart"})
    assert said(reload).startswith("the app's flutter run stopped (exit code 1)")
    assert said(reload).endswith("; start it again with action run")
    stopped = await rig.call("sim_flutter", {"action": "stop"})
    assert said(stopped).startswith("groceries (debug) was not running; flutter run has ended")


async def test_sim_flutter_is_refused_what_it_cannot_do(rig: FlutterRig, tmp_path: Path) -> None:
    assert said(await rig.call("sim_flutter", {"action": "launch"})) == (
        "action is one of run, hot_reload, hot_restart, stop, status"
    )
    assert "destination is for sim_test" in said(await rig.call("sim_flutter", {"action": "run", "destination": {}}))
    assert said(await rig.call("sim_flutter", {"action": "status"}, flutter=None)).startswith(
        "no Flutter app runs on your device"
    )
    assert said(await rig.call("sim_flutter", {"action": "status"}, shells_allowed=False)).startswith(
        "A build runs commands, and this project does not allow them"
    )
    (tmp_path / "Notes").mkdir()
    refused = await rig.call("sim_flutter", {"action": "run"}, folder=tmp_path / "Notes")
    assert "holds no Flutter app" in said(refused) and refused["isError"]


def runtime_over(sim: DeviceRig, rig: FlutterRig) -> Runtime:
    runtime = Runtime.build(
        config=sim.config,
        state=sim.state,
        memory=sim.memory,
        policy=sim.policy,
        copy=sim.copy,
        registry=sim.registry,
        claims=sim.claims,
        builds=rig.runner,
        xcrun=sim.xcrun,
        vision=FakeTextRecognizer(),
        clock=sim.clock,
        sleep=no_wait,
        platform="darwin",
    )
    return dataclasses.replace(runtime, flutter=rig.sessions)


async def test_the_runtime_stops_an_agents_flutter_apps_when_it_goes_or_may_no_longer_build(rig: FlutterRig) -> None:
    rig.sim.config.set(build_tools=True)
    runtime = runtime_over(rig.sim, rig)
    assert isinstance(
        Runtime.build(config=rig.sim.config, state=rig.sim.state, memory=rig.sim.memory, policy=rig.sim.policy).flutter,
        FlutterSessions,
    )
    await rig.call("sim_flutter", {"action": "run"})
    (session,) = rig.sessions.sessions()
    assert session.owner == "agent-1"
    runtime.let_go("agent-2")
    await runtime.stop_builds_not_allowed()
    assert session.alive
    runtime.let_go("agent-1")
    await asyncio.sleep(0.05)
    assert not session.alive
    await rig.call("sim_flutter", {"action": "run"})
    (session,) = rig.sessions.sessions()
    await runtime.stop_builds_not_allowed("another-group")
    assert session.alive
    rig.sim.policy.shells = False
    await runtime.stop_builds_not_allowed()
    assert not session.alive and rig.sessions.sessions() == []
    rig.sim.policy.shells = True
    await rig.call("sim_flutter", {"action": "run"})
    (session,) = rig.sessions.sessions()
    await runtime.close()
    assert not session.alive


async def test_the_flutter_tool_is_listed_with_the_build_tools() -> None:
    from simtrail.config.model import SimConfig

    names = [
        tool["name"] for tool in REGISTRY.manifest(dataclasses.replace(SimConfig.defaults(), build_tools=True))["tools"]
    ]
    assert names[-3:] == ["sim_build_run", "sim_test", "sim_flutter"]
    instructions = REGISTRY.manifest(dataclasses.replace(SimConfig.defaults(), build_tools=True))["instructions"]
    assert "sim_flutter run keeps it running" in instructions
