# SPDX-License-Identifier: Apache-2.0
"""A ``flutter run --machine`` kept running for an agent: hot reloads and restarts, their compile errors, and stopping
it -- asked first, ended if it does not go."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import pytest

from rocketwright.build.flutter_run import FlutterSession, FlutterSessions, SessionGone, StartingRun
from rocketwright.build.xcresult import Issue
from rocketwright.testing.flutter import APP_ID, COMPILE_ERROR, SDK, FakeFlutterRun, FakeRunProcess, Reload
from rocketwright.testing.rig import scope

SCOPE = scope("topic-1", "ws")
UDID = "8592C53F-15E4-41BC-BE49-D19F08BE74BE"


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.run = FakeFlutterRun()
        self.sessions = FlutterSessions()

    async def session(self, *, owner: str = "agent-1", udid: str = UDID, **options: float) -> FlutterSession:
        process = await self.run(SDK, ["run", "--machine"], folder=self.tmp_path, env={})
        session = FlutterSession(
            process,
            scope=SCOPE,
            udid=udid,
            folder=self.tmp_path,
            log_path=self.tmp_path / "run.log",
            label="groceries (debug)",
            build_id="b1",
            owner=owner,
            clock=lambda: 0.0,
            signal_group=self.run.signal,
            settle_s=0,
            **options,
        )
        session.begin()
        self.sessions.add(session)
        await asyncio.wait_for(StartingRun(session).wait(), 5)
        return session

    def process(self, session: FlutterSession) -> FakeRunProcess:
        assert isinstance(session.process, FakeRunProcess)
        return session.process


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    return Rig(tmp_path)


async def test_a_hot_reload_and_a_restart_answer_what_flutter_said(rig: Rig) -> None:
    session = await rig.session()
    assert session.alive and session.app_id == APP_ID and session.started.is_set()
    reload = await session.reload(full=False)
    assert (reload.ok, reload.message, reload.errors, reload.seconds) == (True, "Reloaded 1 of 865 libraries", (), 0.0)
    restart = await session.reload(full=True)
    assert restart.ok and restart.message == ""
    assert [request["params"]["fullRestart"] for request in rig.run.requests] == [False, True]
    assert rig.run.requests[0]["params"] == {"appId": APP_ID, "fullRestart": False, "pause": False}
    # Everything flutter said is in the run's log.
    log = (rig.tmp_path / "run.log").read_text()
    assert "Resolving dependencies..." in log and '"app.started"' in log and "Restarted application" in log
    await rig.sessions.shutdown()


async def test_a_reload_that_does_not_compile_answers_the_compilers_errors(rig: Rig) -> None:
    session = await rig.session()
    rig.run.reloads.append(Reload(errors=COMPILE_ERROR))
    reload = await session.reload(full=False)
    assert not reload.ok and reload.message == "DevFS synchronization failed"
    assert reload.errors == (Issue("error", "Expected an identifier, but got ','.", "lib/main.dart", 133, 46),)
    # The next one reads only what it caused.
    assert (await session.reload(full=False)).errors == ()
    rig.run.reloads.append(Reload(refused="app not found"))
    refused = await session.reload(full=False)
    assert (refused.ok, refused.message) == (False, "app not found")
    await rig.sessions.shutdown()


async def test_a_reload_not_answered_in_time_or_once_flutter_stopped_is_gone(rig: Rig) -> None:
    session = await rig.session(request_timeout_s=0.01)
    rig.run.reloads.append(Reload(silent=True))
    with pytest.raises(SessionGone, match=r"no answer to app\.restart within 0s"):
        await session.reload(full=False)
    process = rig.process(session)
    process.complain("Lost connection to device.")
    process.finish(1)
    await asyncio.wait_for(session.ended.wait(), 5)
    assert not session.alive
    assert session.why_gone() == "the app's flutter run stopped (exit code 1): Lost connection to device."
    with pytest.raises(SessionGone, match="exit code 1"):
        await session.reload(full=False)
    await rig.sessions.shutdown()


async def test_a_request_waiting_when_flutter_stops_is_answered_so(rig: Rig) -> None:
    session = await rig.session()
    rig.run.reloads.append(Reload(silent=True))
    waiting = asyncio.ensure_future(session.reload(full=True))
    await asyncio.sleep(0.01)
    process = rig.process(session)
    exited = asyncio.ensure_future(process.wait())
    await asyncio.sleep(0)
    process.finish(3)
    process.finish(4)
    with pytest.raises(SessionGone, match=r"stopped \(exit code 3\)"):
        await asyncio.wait_for(waiting, 5)
    assert await exited == 3


async def test_a_reload_given_up_on_is_not_answered_when_flutter_stops(rig: Rig) -> None:
    session = await rig.session()
    rig.run.reloads.append(Reload(silent=True))
    waiting = asyncio.ensure_future(session.reload(full=False))
    await asyncio.sleep(0.01)
    waiting.cancel()
    await asyncio.sleep(0.01)
    rig.process(session).finish(0)
    await asyncio.wait_for(session.ended.wait(), 5)
    assert waiting.cancelled()


async def test_shutting_down_waits_for_the_sessions_being_stopped(rig: Rig) -> None:
    session = await rig.session()
    rig.sessions.let_go("agent-1")
    await rig.sessions.shutdown()
    assert not session.alive


async def test_a_request_to_a_closed_pipe_is_gone(rig: Rig) -> None:
    session = await rig.session(stop_wait_s=0.01)
    rig.process(session).stdin.close()
    with pytest.raises(SessionGone, match="exit code None"):
        await session.request("app.restart", {}, 1)
    await rig.sessions.shutdown()


async def test_a_reload_before_the_app_started_is_refused(rig: Rig) -> None:
    rig.run.starts_at_once = False
    process = await rig.run(SDK, ["run"], folder=rig.tmp_path, env={})
    session = FlutterSession(
        process,
        scope=SCOPE,
        udid=UDID,
        folder=rig.tmp_path,
        log_path=rig.tmp_path / "run.log",
        label="x",
        build_id="b1",
    )
    session.begin()
    await asyncio.sleep(0.01)
    with pytest.raises(SessionGone, match="the app has not started yet"):
        await session.reload(full=False)
    await session.stop()


async def test_what_flutter_says_besides_its_answers_is_kept_to_say_why(rig: Rig) -> None:
    session = await rig.session()
    process = rig.process(session)
    process.line("[{not json}]")
    process.say({"event": "daemon.logMessage", "params": {"level": "error", "message": "Xcode build failed"}})
    process.say({"event": "app.log", "params": {"appId": APP_ID, "log": "Exception: boom", "error": True}})
    process.say({"event": "app.log", "params": {"appId": APP_ID, "error": True}})
    process.say({"event": "daemon.logMessage", "params": "odd"})
    process.line("[1]")
    process.stdout.feed_data(b'[{"id": "x"}, 3, {}]\n')
    await asyncio.sleep(0.01)
    assert session.recent()[-5:] == ["[{not json}]", "Xcode build failed", "Exception: boom", "", "[1]"]
    await rig.sessions.shutdown()


async def test_a_line_longer_than_the_limit_is_passed_over(rig: Rig) -> None:
    session = await rig.session()

    class Long:
        def __init__(self) -> None:
            self.calls = 0

        async def readline(self) -> bytes:
            self.calls += 1
            if self.calls == 1:
                raise ValueError("Separator is not found, and chunk exceed the limit")
            return b"" if self.calls > 2 else b"after\n"

    await session._hear(Long(), json_lines=False)
    assert session.recent()[-1] == "after"
    await rig.sessions.shutdown()


async def test_stopping_asks_flutter_first_and_ends_it_when_it_does_not_go(rig: Rig) -> None:
    session = await rig.session()
    await rig.sessions.stop(session)
    assert not session.alive and rig.run.signals == [] and rig.run.requests[-1]["method"] == "app.stop"
    rig.run.stops = False
    stubborn = await rig.session(stop_wait_s=0.01)
    await rig.sessions.stop(stubborn)
    assert rig.run.signals == [(7001, signal.SIGTERM)] and not stubborn.alive
    # Stopping one that already ended asks nothing.
    asked = len(rig.run.requests)
    await stubborn.stop()
    assert len(rig.run.requests) == asked


async def test_a_flutter_deaf_to_term_is_killed(rig: Rig) -> None:
    rig.run.stops = False
    session = await rig.session(stop_wait_s=0.01)
    process = rig.process(session)
    sent: list[int] = []

    def deaf(pid: int, sig: int) -> None:
        sent.append(sig)
        if sig == signal.SIGKILL:
            process.finish(-9)

    session._signal = deaf
    await session.stop()
    assert sent == [signal.SIGTERM, signal.SIGKILL] and not session.alive


async def test_a_session_is_its_devices_and_its_agents(rig: Rig) -> None:
    first = await rig.session(owner="agent-1")
    other = await rig.session(owner="agent-2", udid="8FEE44C1-95CC-4562-B16C-3B530412F87C")
    assert rig.sessions.on(SCOPE.id, UDID) is first and rig.sessions.on("tp-other", UDID) is None
    assert rig.sessions.on(SCOPE.id, "nowhere") is None
    assert await rig.sessions.stop_device("nowhere") is False
    rig.sessions.let_go("agent-3")
    rig.sessions.let_go("agent-1")
    await asyncio.sleep(0.05)
    assert not first.alive and other.alive and rig.sessions.sessions() == [other]
    assert await rig.sessions.stop_where(lambda session: session.owner == "agent-2") == 1
    # A session another replaced is still stopped, and is no longer the device's.
    replaced = await rig.session()
    rig.sessions.add(await rig.session())
    await rig.sessions.stop(replaced)
    assert rig.sessions.on(SCOPE.id, UDID) is not replaced
    assert await rig.sessions.stop_device(UDID) is True
    ended = await rig.session()
    rig.process(ended).finish(0)
    await asyncio.wait_for(ended.ended.wait(), 5)
    assert await rig.sessions.stop_device(UDID) is False


async def test_a_run_that_stopped_before_its_app_started_answers_its_exit_code(rig: Rig) -> None:
    rig.run.starts, rig.run.build_errors = False, COMPILE_ERROR
    process = await rig.run(SDK, ["run"], folder=rig.tmp_path, env={})
    session = FlutterSession(
        process,
        scope=SCOPE,
        udid=UDID,
        folder=rig.tmp_path,
        log_path=rig.tmp_path / "run.log",
        label="x",
        build_id="b1",
    )
    session.begin()
    starting = StartingRun(session)
    assert await asyncio.wait_for(starting.wait(), 5) == 1 and starting.pid == process.pid
    assert await starting.wait() == 1
    assert "lib/main.dart:133:46: Error: Expected an identifier, but got ','." in session.recent()
