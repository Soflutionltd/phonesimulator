# SPDX-License-Identifier: Apache-2.0
"""``flutter run --machine`` kept running for an agent, so a change reaches the device by a hot reload.

`sim_flutter run` starts ``flutter run --machine -d <device>`` (`flutter.FlutterToolchain`), as a run of
`runner.Runner` like a build: one at a time in a DerivedData folder, the device busy until the app has started. From
then on it is a `FlutterSession`: Rocketwright keeps the process and speaks to it in the Flutter daemon's protocol --
one JSON array a line each way, measured with Flutter 3.47:

    → [{"id": 1, "method": "app.restart", "params": {"appId": "…", "fullRestart": false, "pause": false}}]
    ← [{"event": "app.started", "params": {"appId": "…"}}]
    ← [{"id": 1, "result": {"code": 0, "message": "Reloaded 1 of 865 libraries"}}]

A hot reload whose code does not compile answers ``code`` 1, ``DevFS synchronization failed``, and the compiler's
errors are what flutter wrote on stderr meanwhile (`flutter_log.compile_errors`). Everything flutter says, plain lines
and JSON alike, is appended to the run's log.

A session is its device's: one at a time on each -- a new run, or a build installed there, stops the one before -- and
it belongs to the agent that started it. It is stopped when that agent's connection ends (`Runtime.let_go`), when its
scope may no longer build, and when Rocketwright stops: flutter is asked to stop the app (``app.stop``), then its
process group is ended if it has not gone.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import signal
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rocketwright.build.flutter_log import compile_errors
from rocketwright.build.xcresult import Issue
from rocketwright.platform.process import signal_group as signal_process_group
from rocketwright.scope import Scope

#: How long a hot reload or restart may take before it is given up on.
REQUEST_TIMEOUT_S = 120.0
#: How long flutter is given to stop the app and exit, before its process group is ended.
STOP_WAIT_S = 10.0
#: How many of flutter's last plain lines are kept, to say why a run or a reload failed.
RECENT_LINES = 400
#: How long a reload that failed waits for the compiler's errors, which flutter writes on stderr, another pipe than
#: its answer's.
SETTLE_S = 0.3


class SessionGone(Exception):
    """The session's flutter stopped, or did not answer in time."""


@dataclass(frozen=True)
class Reload:
    """What a hot reload or restart answered."""

    ok: bool
    message: str
    errors: tuple[Issue, ...]
    seconds: float


class FlutterSession:
    """One ``flutter run --machine`` and the app it runs on a device."""

    def __init__(
        self,
        process: Any,
        *,
        scope: Scope,
        udid: str,
        folder: Path,
        log_path: Path,
        label: str,
        build_id: str,
        owner: str = "",
        clock: Callable[[], float] = time.monotonic,
        signal_group: Callable[[int, int], None] = signal_process_group,
        stop_wait_s: float = STOP_WAIT_S,
        request_timeout_s: float = REQUEST_TIMEOUT_S,
        settle_s: float = SETTLE_S,
    ) -> None:
        self.process = process
        self.scope = scope
        self.udid = udid
        self.folder = folder
        self.log_path = log_path
        self.label = label
        self.build_id = build_id
        #: The agent connection that started it, stopped with it.
        self.owner = owner
        self.app_id: str | None = None
        self.started = asyncio.Event()
        self.ended = asyncio.Event()
        self._clock = clock
        self._signal = signal_group
        self._stop_wait_s = stop_wait_s
        self._request_timeout_s = request_timeout_s
        self._settle_s = settle_s
        #: How many plain lines flutter has said, kept or not.
        self._heard = 0
        self._ids = itertools.count(1)
        self._waiting: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._recent: deque[str] = deque(maxlen=RECENT_LINES)
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []

    def begin(self) -> None:
        """Start hearing flutter."""
        loop = asyncio.get_running_loop()
        self._tasks = [
            loop.create_task(self._hear(self.process.stdout, json_lines=True)),
            loop.create_task(self._hear(self.process.stderr, json_lines=False)),
        ]

    @property
    def alive(self) -> bool:
        return not self.ended.is_set() and self.process.returncode is None

    def recent(self) -> list[str]:
        """flutter's last plain lines, oldest first."""
        return list(self._recent)

    def _note(self, line: str) -> None:
        self._recent.append(line)
        self._heard += 1

    def _since(self, heard: int) -> list[str]:
        """The plain lines flutter said after it had said `heard`, as many as are kept."""
        new = min(self._heard - heard, len(self._recent))
        return list(self._recent)[len(self._recent) - new :] if new else []

    def _log(self, line: str) -> None:
        with contextlib.suppress(OSError), open(self.log_path, "a", encoding="utf-8") as log:
            log.write(line + "\n")

    async def _hear(self, stream: Any, *, json_lines: bool) -> None:
        while True:
            try:
                raw = await stream.readline()
            except ValueError:
                # A line longer than the stream's limit: nothing in it is one of the daemon's messages.
                continue
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            self._log(line)
            if json_lines and line.startswith("[{") and line.endswith("}]"):
                self._messages(line)
            else:
                self._note(line)
        if json_lines:
            await self._gone()

    def _messages(self, line: str) -> None:
        try:
            messages = json.loads(line)
        except ValueError:
            self._note(line)
            return
        for message in messages if isinstance(messages, list) else []:
            if isinstance(message, dict):
                self._message(message)

    def _message(self, message: dict[str, Any]) -> None:
        event, params = message.get("event"), message.get("params")
        params = params if isinstance(params, dict) else {}
        if event == "app.start" and isinstance(params.get("appId"), str):
            self.app_id = params["appId"]
        elif event == "app.started":
            self.started.set()
        elif event == "daemon.logMessage" and params.get("level") == "error":
            self._note(str(params.get("message") or ""))
        elif event == "app.log" and params.get("error") is True:
            self._note(str(params["log"]) if "log" in params else "")
        ident = message.get("id")
        waiting = self._waiting.pop(ident, None) if isinstance(ident, int) else None
        if waiting is not None and not waiting.done():
            waiting.set_result(message)

    async def _gone(self) -> None:
        """flutter closed its output: it has stopped, and every request waiting is answered so."""
        with contextlib.suppress(Exception):
            await self.process.wait()
        self.ended.set()
        for waiting in self._waiting.values():
            if not waiting.done():
                waiting.set_exception(SessionGone(self.why_gone()))
        self._waiting.clear()

    def why_gone(self) -> str:
        last = next((line for line in reversed(self._recent) if line.strip()), "")
        said = f": {last.strip()}" if last else ""
        return f"the app's flutter run stopped (exit code {self.process.returncode}){said}"

    async def request(self, method: str, params: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        """Send one request and answer flutter's answer -- or `SessionGone`."""
        if not self.alive:
            raise SessionGone(self.why_gone())
        ident = next(self._ids)
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiting[ident] = future
        line = json.dumps([{"id": ident, "method": method, "params": params}]) + "\n"
        try:
            self.process.stdin.write(line.encode())
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            self._waiting.pop(ident, None)
            raise SessionGone(self.why_gone()) from exc
        try:
            return await asyncio.wait_for(future, timeout_s)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            self._waiting.pop(ident, None)
            raise SessionGone(f"no answer to {method} within {round(timeout_s)}s") from exc

    async def reload(self, *, full: bool) -> Reload:
        """A hot reload -- or, `full`, a hot restart -- and the compile errors it met."""
        async with self._lock:
            if self.app_id is None or not self.started.is_set():
                raise SessionGone("the app has not started yet")
            began, heard = self._clock(), self._heard
            answer = await self.request(
                "app.restart",
                {"appId": self.app_id, "fullRestart": full, "pause": False},
                self._request_timeout_s,
            )
            took = round(self._clock() - began, 1)
            result = answer.get("result")
            ok = isinstance(result, dict) and result.get("code") == 0
            if not ok:
                await asyncio.sleep(self._settle_s)
            errors = tuple(compile_errors(self._since(heard)))
        if not isinstance(result, dict):
            return Reload(False, str(answer.get("error") or "refused"), errors, took)
        return Reload(ok, str(result.get("message") or ""), errors, took)

    async def stop(self) -> None:
        """Stop the app and flutter: asked first, then its process group ended."""
        if self.alive and self.app_id is not None:
            with contextlib.suppress(SessionGone):
                await self.request("app.stop", {"appId": self.app_id}, self._stop_wait_s)
        if self.process.returncode is None:
            with contextlib.suppress(Exception):
                self.process.stdin.close()
            await self._end()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _end(self) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                await asyncio.wait_for(asyncio.shield(self.ended.wait()), self._stop_wait_s)
                return
            except (asyncio.TimeoutError, TimeoutError):
                self._signal(self.process.pid, sig)
        with contextlib.suppress(asyncio.TimeoutError, TimeoutError):
            await asyncio.wait_for(self.ended.wait(), self._stop_wait_s)


class StartingRun:
    """A session as `runner.Runner` sees a run's process: it ends when the app has started -- answering 0 -- or when
    flutter stopped before it did, answering its exit code. Ending it ends flutter's process group."""

    def __init__(self, session: FlutterSession) -> None:
        self.session = session
        self.returncode: int | None = None

    @property
    def pid(self) -> int:
        return int(self.session.process.pid)

    async def wait(self) -> int:
        started = asyncio.ensure_future(self.session.started.wait())
        ended = asyncio.ensure_future(self.session.ended.wait())
        try:
            await asyncio.wait({started, ended}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            started.cancel()
            ended.cancel()
        if self.returncode is None:
            code = self.session.process.returncode
            self.returncode = 0 if self.session.started.is_set() and self.session.alive else (code or 1)
        return self.returncode


class FlutterSessions:
    """Every device's running Flutter app, for one process."""

    def __init__(self) -> None:
        self._by_device: dict[str, FlutterSession] = {}
        self._stopping: set[asyncio.Task[int]] = set()

    def add(self, session: FlutterSession) -> None:
        self._by_device[session.udid] = session

    def on(self, scope_id: str, udid: str) -> FlutterSession | None:
        """The session a scope has on a device -- running or ended, until another replaces it."""
        session = self._by_device.get(udid)
        return session if session is not None and session.scope.id == scope_id else None

    def sessions(self) -> list[FlutterSession]:
        return list(self._by_device.values())

    async def stop(self, session: FlutterSession) -> None:
        if self._by_device.get(session.udid) is session:
            del self._by_device[session.udid]
        await session.stop()

    async def stop_device(self, udid: str) -> bool:
        """Stop the session on a device, whoever started it. Answers whether one was running."""
        session = self._by_device.get(udid)
        if session is None:
            return False
        running = session.alive
        await self.stop(session)
        return running

    async def stop_where(self, chosen: Callable[[FlutterSession], bool]) -> int:
        """Stop every session `chosen` picks. Answers how many."""
        picked = [session for session in self.sessions() if chosen(session)]
        for session in picked:
            await self.stop(session)
        return len(picked)

    def let_go(self, key: str) -> None:
        """An agent's connection ended: the sessions it started are stopped, in the background."""
        picked = [session for session in self.sessions() if session.owner == key]
        if not picked:
            return
        task = asyncio.get_running_loop().create_task(self.stop_where(lambda session: session.owner == key))
        self._stopping.add(task)
        task.add_done_callback(self._stopping.discard)

    async def shutdown(self) -> None:
        await self.stop_where(lambda session: True)
        for task in list(self._stopping):
            with contextlib.suppress(asyncio.CancelledError):
                await task
