# SPDX-License-Identifier: Apache-2.0
"""One-shot codes and the viewer sessions they buy, agents' leases, a person's pauses, and what a standalone scope may
do."""

from __future__ import annotations

import logging
import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

from phonesimulator.build.xcodebuild import DERIVED_DATA
from phonesimulator.daemon.lease import LEASE_S, Leases
from phonesimulator.daemon.passes import CODE_TTL_S, SETTINGS_TTL_S, VIEWER_TTL_S, OneShotCodes, Pass, ViewerSessions
from phonesimulator.daemon.pauses import PAUSE_MAX_S, Pauses
from phonesimulator.daemon.policy import ConfigPolicy
from phonesimulator.daemon.tokens import TokenStore
from phonesimulator.scope import Scope
from phonesimulator.testing.fakes import ManualClock, MemoryStateStore, StaticConfig


def test_a_code_opens_its_scope_once_and_only_within_its_minute() -> None:
    clock = ManualClock()
    codes = OneShotCodes(clock=clock)
    first = codes.mint("tp-1")
    assert codes.redeem(first) == Pass("tp-1", "viewer") and codes.redeem(first) is None
    late = codes.mint("tp-1")
    clock.advance(CODE_TTL_S)
    assert codes.redeem(late) is None and codes.redeem("never-made") is None
    kept = codes.mint("tp-2")
    clock.advance(CODE_TTL_S / 2)
    codes.mint("tp-3")
    assert codes.redeem(kept) == Pass("tp-2", "viewer")
    assert codes.redeem(codes.mint("tp-4", "settings")) == Pass("tp-4", "settings")


def test_a_settings_session_says_so_and_lasts_an_hour_not_the_twelve_a_viewer_does() -> None:
    clock = ManualClock()
    viewers = ViewerSessions(clock=clock)
    settings, embed, viewer = viewers.open("tp-1", "settings"), viewers.open("tp-1", "embed"), viewers.open("tp-1")
    assert viewers.session(settings) == Pass("tp-1", "settings") and viewers.session(embed) == Pass("tp-1", "embed")
    clock.advance(SETTINGS_TTL_S)
    assert viewers.session(settings) is None and viewers.scope_of(viewer) == "tp-1"
    assert SETTINGS_TTL_S < VIEWER_TTL_S


def test_a_viewer_token_is_for_its_scope_until_it_expires() -> None:
    clock = ManualClock()
    viewers = ViewerSessions(clock=clock)
    token = viewers.open("tp-1")
    assert viewers.scope_of(token) == "tp-1" and viewers.scope_of(None) is None and viewers.scope_of("forged") is None
    clock.advance(VIEWER_TTL_S)
    fresh = viewers.open("tp-2")
    assert viewers.scope_of(token) is None and viewers.scope_of(fresh) == "tp-2"


def test_a_page_s_session_outlives_a_restart_of_its_daemon_until_it_expires_as_it_would_have(tmp_path: Path) -> None:
    path, wall = tmp_path / "state" / "viewer-sessions.json", ManualClock(1_000_000.0)
    before = ViewerSessions(clock=ManualClock(), path=path, wall=wall)
    viewer, settings = before.open("tp-1"), before.open("tp-1", "settings")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    kept = path.read_text(encoding="utf-8")
    assert viewer not in kept and settings not in kept, "only a session's digest is kept"
    wall.advance(SETTINGS_TTL_S)
    # A new daemon: another monotonic clock, the same state folder.
    after = ViewerSessions(clock=ManualClock(50.0), path=path, wall=wall)
    assert after.session(viewer) == Pass("tp-1", "viewer") and after.session(settings) is None
    assert ViewerSessions(path=None).session(viewer) is None
    wall.advance(VIEWER_TTL_S - SETTINGS_TTL_S)
    assert ViewerSessions(clock=ManualClock(), path=path, wall=wall).session(viewer) is None


def test_a_clock_set_back_does_not_stretch_a_kept_session_and_signing_out_ends_every_one(tmp_path: Path) -> None:
    path, clock, wall = tmp_path / "viewer-sessions.json", ManualClock(), ManualClock(1_000_000.0)
    token = ViewerSessions(clock=clock, path=path, wall=wall).open("tp-1", "settings")
    wall.advance(-10 * SETTINGS_TTL_S)
    again = ViewerSessions(clock=clock, path=path, wall=wall)
    clock.advance(SETTINGS_TTL_S)
    assert again.session(token) is None
    other = again.open("tp-2")
    assert again.end_all() == 1 and again.session(other) is None
    assert ViewerSessions(clock=clock, path=path, wall=wall).session(other) is None


@pytest.mark.parametrize(
    "kept",
    ["not json", "{}", '{"sessions": []}', '{"sessions": {"d": [1, "tp-1", "root"]}}', '{"sessions": {"d": [1, 2]}}'],
)
def test_a_sessions_file_that_cannot_be_read_lets_no_page_in(
    tmp_path: Path, kept: str, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "viewer-sessions.json"
    path.write_text(kept, encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        sessions = ViewerSessions(path=path)
    assert sessions.end_all() == 0 and "could not be read" in caplog.text


def test_a_session_still_opens_when_its_file_cannot_be_written(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_text("a file where the folder should be", encoding="utf-8")
    sessions = ViewerSessions(path=blocked / "viewer-sessions.json")
    with caplog.at_level(logging.WARNING):
        token = sessions.open("tp-1")
    assert sessions.scope_of(token) == "tp-1" and "could not be written" in caplog.text


@dataclass
class Held:
    udid: str = "U"
    group: str = "local"
    scopes: tuple[str, ...] = ("tp-1",)


def test_a_lease_holds_a_scopes_device_until_it_runs_out_or_every_holder_lets_go() -> None:
    clock = ManualClock()
    leases = Leases(clock=clock)
    assert not leases.in_use(Held())
    assert leases.renew("tp-1", "t1") == clock.now + LEASE_S
    assert leases.held("tp-1") and leases.in_use(Held(scopes=("tp-9", "tp-1"))) and not leases.held("tp-9")
    clock.advance(LEASE_S - 1)
    leases.renew("tp-1", "t1")
    clock.advance(LEASE_S - 1)
    assert leases.held("tp-1")
    clock.advance(2)
    assert not leases.held("tp-1")
    leases.renew("tp-1", "t1")
    leases.renew("tp-1", "t2")
    leases.release("tp-1", "t1")
    assert leases.held("tp-1")
    leases.release("tp-1", "t2")
    leases.release("tp-1", "nobody")
    assert not leases.held("tp-1")


def test_a_lease_is_logged_as_it_starts_lapses_and_is_let_go_and_never_for_each_renewal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="phonesimulator.daemon.lease")
    clock = ManualClock()
    leases = Leases(clock=clock)
    for _ in range(3):
        leases.renew("tp-1", "t1")
        clock.advance(LEASE_S / 3)
    leases.renew("tp-2", "t1")
    leases.renew("tp-2", "t2")
    assert caplog.text.count("an agent holds tp-1 now (token t1)") == 1
    assert leases.holders() == {"tp-1": {"t1"}, "tp-2": {"t1", "t2"}}
    clock.advance(LEASE_S * 2 / 3)
    assert leases.scopes() == {"tp-2"}, "pruned as it is asked"
    assert "the agent lease on tp-1 lapsed (token t1)" in caplog.text
    leases.release_holder("t1")
    assert leases.holders() == {"tp-2": {"t2"}} and "the agent holding tp-2 let it go (token t1)" in caplog.text
    leases.renew("tp-1", "t1")
    assert caplog.text.count("an agent holds tp-1 now (token t1)") == 2, "held again after it lapsed"


def test_a_pause_holds_agents_off_a_scopes_device_until_it_is_lifted_or_runs_out_and_never_for_longer() -> None:
    clock = ManualClock()
    pauses = Pauses(clock=clock)
    assert not pauses.paused(Held()) and pauses.left("tp-1") == 0 and not pauses.lift("tp-1")
    assert pauses.hold("tp-1", 30) == 30
    assert pauses.paused(Held(scopes=("tp-9", "tp-1"))) and not pauses.paused(Held(scopes=("tp-9",)))
    clock.advance(20)
    assert pauses.left("tp-1") == 10
    pauses.hold("tp-1", 30)
    clock.advance(20)
    assert pauses.paused(Held()), "set again, it holds from then"
    clock.advance(10)
    assert not pauses.paused(Held()) and pauses.left("tp-1") == 0, "run out, it lifts by itself"
    assert pauses.hold("tp-1", PAUSE_MAX_S * 10) == PAUSE_MAX_S, "never longer than the most one holds"
    assert pauses.lift("tp-1") and not pauses.paused(Held())
    pauses.hold("tp-2", 1)
    clock.advance(1)
    assert not pauses.lift("tp-2"), "one that ran out was not holding"


def test_a_standalone_scope_installs_from_its_tokens_folders_and_runs_commands_while_build_tools_are_on(
    tmp_path: Path,
) -> None:
    config = StaticConfig()
    tokens = TokenStore(tmp_path / "secrets")
    state = MemoryStateStore(tmp_path)
    policy = ConfigPolicy(config, tokens, state)
    demo = Scope.named("demo")
    assert policy.area_enabled(demo) and not policy.shells_allowed(demo) and policy.build_folder(demo) is None
    assert policy.install_roots(demo) == (state.derived_data(demo), DERIVED_DATA)
    tokens.create("agent", ["demo"], roots=["/Users/me/Notes", "/Users/me/Kit"])
    config.set(build_tools=True)
    assert policy.shells_allowed(demo) and policy.build_folder(demo) == Path("/Users/me/Notes")
    assert policy.install_roots(demo) == (
        Path("/Users/me/Notes"),
        Path("/Users/me/Kit"),
        state.derived_data(demo),
        DERIVED_DATA,
    )
