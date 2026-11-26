# SPDX-License-Identifier: Apache-2.0
"""`sim_flow`: a walkthrough saved under a name, with what its refs named, and played again through sim_act's path --
by another agent too, with variables for what changes and what must never be kept."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
from pathlib import Path
from typing import Any

import pytest

from simtrail.connectors.base import ConnectorError
from simtrail.core.actions import MAX_STEPS, AgentActions
from simtrail.core.flows import FlowStore
from simtrail.seams import Caller
from simtrail.testing.fakes import no_wait
from simtrail.testing.results import structured
from simtrail.testing.rig import DeviceRig, scope
from simtrail.tools.context import ToolContext
from simtrail.tools.flow import FIND_S
from simtrail.tools.registry import ToolRegistry
from simtrail.tools.results import SHUT_DOWN, Result, text

CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude · notes")
OTHER = Caller(scope("tp-1"), key="agent-2", title="Codex")
REGISTRY = ToolRegistry()


def _frame(y: float) -> dict[str, float]:
    return {"x": 16, "y": y, "width": 370, "height": 44}


def _element(kind: str, label: str, y: float, **more: Any) -> dict[str, Any]:
    return {"type": kind, "label": label, "frame": _frame(y), **more}


LOGIN = {
    "elements": [
        _element("TextField", "Email", 100),
        _element("SecureTextField", "Password", 160),
        _element("Button", "Sign in", 220),
    ]
}
#: The same screen with a banner above it: an agent that reads it first gives its fields other refs.
BANNER = {"elements": [_element("Button", "What's new", 40), *LOGIN["elements"]]}
SIGN_IN = [{"type": "{{email}}", "into": "e1"}, {"type": "{{password}}", "into": "e2"}, {"tap": "e3"}]
SECRET = (
    'types into a secure field "Password": type a variable there alone, such as "{{password}}", and give its value '
    "to sim_flow run -- a flow never keeps a secret"
)


def tools(rig: DeviceRig, caller: Caller = CALLER, **changes: Any) -> ToolContext:
    async def sleep(seconds: float) -> None:
        # Waiting moves the rig's clock, so a wait not met gives up.
        rig.clock.advance(seconds)
        await asyncio.sleep(0)

    ctx = ToolContext(
        manager=rig.manager,
        actions=AgentActions(rig.manager, rig.config, clock=rig.clock, sleep=sleep),
        caller=caller,
        config=rig.config.get(caller.scope),
        copy=rig.copy,
        sleep=no_wait,
        flows=FlowStore(lambda kept: rig.root / "flows" / kept.id),
    )
    return dataclasses.replace(ctx, **changes)


async def call(ctx: ToolContext, name: str, arguments: object) -> Result:
    return await REGISTRY.call(name, arguments, ctx)


def said(result: Result) -> str:
    """What a call answered, with each step's time since the call began left out: waiting moves the clock."""
    return re.sub(r" \+\d+ms", "", str(result["content"][0]["text"]))


def login(rig: DeviceRig) -> DeviceRig:
    rig.idb.engine.document = LOGIN
    return rig


async def saved_sign_in(ctx: ToolContext) -> Result:
    await call(ctx, "sim_snapshot", {"mode": "full"})
    arguments = {"action": "save", "name": "sign-in", "description": "Sign in", "steps": SIGN_IN}
    return await call(ctx, "sim_flow", {**arguments, "wait": {"for": "Sign in"}})


def run_sign_in(email: str = "qa@example.com", password: str = "hunter22") -> dict[str, Any]:
    return {"action": "run", "name": "sign-in", "variables": {"email": email, "password": password}}


# -- saving -----------------------------------------------------------------------------------------------------------


async def test_a_flow_is_kept_as_a_readable_file_with_what_each_ref_named(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    saved = await saved_sign_in(ctx)
    path = tmp_path / "flows" / "tp-1" / "sign-in.json"
    assert saved == text(f"saved the flow sign-in: 3 steps · {path}; run it with variables email, password")
    written = path.read_text(encoding="utf-8")
    assert written.endswith("}\n") and '\n  "name": "sign-in",\n' in written, "two spaces of indent, a last line"
    document = json.loads(written)
    assert document["simtrail_flow"] == 1 and document["variables"] == ["email", "password"]
    assert document["batches"] == [{"steps": SIGN_IN, "wait": {"for": "Sign in"}}]
    password = {"kind": "secure", "label": "Password", "identifier": "", "x": 201.0, "y": 182.0}
    assert document["targets"]["e2"] == password
    again = {"action": "save", "name": "sign-in", "steps": [{"tap": "e3"}]}
    assert await call(ctx, "sim_flow", again) == text(
        "a flow named sign-in is already kept; pass replace: true to write over it", error=True
    )
    replaced = await call(ctx, "sim_flow", {**again, "replace": True})
    assert said(replaced) == f"replaced the flow sign-in: 1 step · {path}"


async def test_list_show_and_delete_read_and_remove_what_is_kept(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    folder = tmp_path / "flows" / "tp-1"
    assert said(await call(ctx, "sim_flow", {"action": "list"})) == (
        f"no flows kept yet in {folder}; sim_flow save keeps one"
    )
    await saved_sign_in(ctx)
    await call(ctx, "sim_flow", {"action": "save", "name": "home", "steps": [{"press": "home"}]})
    (folder / "broken.json").write_text("{", encoding="utf-8")
    listed = said(await call(ctx, "sim_flow", {"action": "list"})).splitlines()
    assert listed[0].startswith("cannot be read: broken could not be read:")
    assert listed[1:] == ["home · 1 step", "sign-in · 3 steps · variables email, password · Sign in"]
    shown = await call(ctx, "sim_flow", {"action": "show", "name": "sign-in"})
    assert json.loads(said(shown)) == shown["structuredContent"]
    assert shown["structuredContent"]["description"] == "Sign in"
    assert said(await call(ctx, "sim_flow", {"action": "delete", "name": "home"})) == "deleted the flow home"
    missing = text("no flow is named home; sim_flow list names those kept", error=True)
    assert await call(ctx, "sim_flow", {"action": "delete", "name": "home"}) == missing
    assert await call(ctx, "sim_flow", {"action": "show", "name": "home"}) == missing
    assert await call(ctx, "sim_flow", {"action": "show", "name": "../etc"}) == text(
        "name is 1 to 64 lowercase letters, digits, dashes and underscores, such as sign-in", error=True
    )
    assert await call(ctx, "sim_flow", {"action": "record"}) == text(
        "action is one of save, list, show, delete, run", error=True
    )
    assert await call(tools(rig, flows=None), "sim_flow", {"action": "list"}) == text(
        "flows are not kept here", error=True
    )


async def test_saving_refuses_what_could_not_be_played_again(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)

    async def save(**arguments: Any) -> str:
        result = await call(ctx, "sim_flow", {"action": "save", "name": "f", **arguments})
        assert result["isError"] is True
        return said(result)

    assert await save(steps=[{"tap": "e1"}]) == (
        "step 1: e1 is not a ref you were given on your device: take sim_snapshot of the screen it is on first, or "
        "give a point"
    ), "no device has been read yet"
    await call(ctx, "sim_snapshot", {})
    assert (await save(steps=[{"press": "home"}, {"tap": "e9"}])).startswith("step 2: e9 is not a ref you were given")
    assert (await save(steps=[{"tap": "e1", "ms": 3}])).startswith('the flow: step 1: tap does not take "ms"')
    many = [{"press": "home"}] * MAX_STEPS + [{"pause": -1}]
    assert (await save(steps=many)).startswith(f"the flow: step {MAX_STEPS + 1}: pause")
    assert (await save(steps=[{"tap": "e1"}], wait={"for": "x", "soon": 1})).startswith(
        "the flow: the wait is refused:"
    )
    assert await save(description=3, steps=[{"tap": "e1"}]) == "description is text of at most 500 characters"
    assert await save(steps=[{"tap": "e1"}], replace="yes") == "replace is true or false"


async def test_a_secret_typed_into_a_secure_field_is_never_kept(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    await call(ctx, "sim_snapshot", {})

    async def save(steps: list[dict[str, Any]]) -> Result:
        return await call(ctx, "sim_flow", {"action": "save", "name": "f", "steps": steps, "replace": True})

    assert await save([{"type": "hunter2", "into": "e2"}]) == text(f"step 1 {SECRET}", error=True)
    assert await save([{"type": "pw {{password}}", "into": [201, 182]}]) == text(f"step 1 {SECRET}", error=True)
    assert await save([{"tap": "e2"}, {"pause": 10}, {"type": "hunter2"}]) == text(f"step 3 {SECRET}", error=True)
    assert not (await save([{"type": " {{password}} ", "into": "e2"}]))["isError"]
    # The address is not secret, nor is what is typed on a point where nothing was read.
    assert not (await save([{"tap": "e1"}, {"type": "me@example.com"}, {"type": "x", "into": [5, 800]}]))["isError"]
    assert not (await save([{"tap": [10, 10]}, {"type": "x"}]))["isError"]
    # The field being edited when the agent last looked is where typing with no "into" goes.
    editing = _element("SecureTextField", "Password", 160, traits=["IsEditing"])
    rig.idb.engine.document = {"elements": [LOGIN["elements"][0], editing]}
    await call(ctx, "sim_snapshot", {})
    assert await save([{"type": "hunter2"}]) == text(f"step 1 {SECRET}", error=True)


async def test_points_and_keys_are_kept_without_a_device_read_first(tmp_path: Path) -> None:
    ctx = tools(DeviceRig(tmp_path))
    saved = await call(ctx, "sim_flow", {"action": "save", "name": "home", "steps": [{"tap": [10, 10]}, {"type": "x"}]})
    assert saved["isError"] is False


# -- playing ----------------------------------------------------------------------------------------------------------


async def test_another_agent_plays_a_flow_finding_each_element_again_and_never_repeating_a_secret(
    tmp_path: Path,
) -> None:
    rig = login(DeviceRig(tmp_path))
    await saved_sign_in(tools(rig))
    rig.idb.engine.document = BANNER
    played = await call(tools(rig, OTHER), "sim_flow", run_sign_in())
    assert said(played).splitlines()[:4] == [
        "flow sign-in · 3 steps",
        'ok type "{{email}}" into e2 "Email" (201,122)',
        'ok type "••••" into e3 "Password" (201,182)',
        'ok tap e4 "Sign in" (201,242)',
    ], "its refs on this agent's screen, the values said as their names, and a secure field's as nothing at all"
    assert "hunter22" not in said(played) and "qa@example.com" not in said(played)
    assert played["isError"] is False
    assert structured(played) == {
        "flow": "sign-in",
        "steps": 3,
        "completed_steps": 3,
        "failed_step": None,
        "failed_step_may_have_run": False,
        "wait_met": True,
    }
    assert rig.idb.engine.hid_events, "the steps reached the device"


async def test_a_variable_typed_into_a_secure_field_is_masked_in_every_event_and_every_answer_after(
    tmp_path: Path,
) -> None:
    rig = login(DeviceRig(tmp_path))
    await saved_sign_in(tools(rig))
    instance = await rig.up()
    events = instance.events.subscribe()
    ctx = tools(rig, OTHER)
    played = await call(ctx, "sim_flow", run_sign_in(password="hunter22"))
    assert played["isError"] is False, said(played)
    published = [events.get_nowait() for _ in range(events.qsize())]
    typed = [event for event in published if event.get("gesture", {}).get("kind") == "type"]
    assert [event["caption"] for event in typed] == ["qa@example.com", "••••"], "the e-mail is shown, the password not"
    assert "Typing “••••”" in [event["activity"] for event in typed]
    assert "hunter22" not in json.dumps(published, ensure_ascii=False)
    # The app shows it back later -- its eye tapped -- and the agent reads the screen: it is masked there too.
    rig.idb.engine.document = {"elements": [_element("StaticText", "Your password is hunter22", 100)]}
    looked = await call(ctx, "sim_snapshot", {"mode": "full"})
    assert "hunter22" not in said(looked) and "Your password is ••••" in said(looked)


async def test_a_secure_variable_whose_typing_failed_midway_is_masked_in_every_answer_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    await saved_sign_in(ctx)
    engine, gestures = rig.idb.engine, 0

    async def hid(events: Any) -> None:
        nonlocal gestures
        gestures += 1
        async for event in events:
            engine.hid_events.append(event)
            if gestures == 2:
                raise ConnectorError("the device went away")

    monkeypatch.setattr(engine, "hid", hid)
    played = await call(ctx, "sim_flow", run_sign_in(password="half-typed-pw"))
    assert played["isError"] is True and "error step 2" in said(played) and "half-typed-pw" not in said(played)
    monkeypatch.undo()
    # The part that reached the field is shown back -- its eye tapped -- and the agent reads the screen.
    engine.document = {"elements": [_element("StaticText", "Your password is half-typed-pw", 100)]}
    looked = await call(ctx, "sim_snapshot", {"mode": "full"})
    assert "half-typed-pw" not in said(looked) and "Your password is ••••" in said(looked)


async def test_a_run_needs_each_variable_and_no_other(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    await saved_sign_in(ctx)
    played = len(rig.idb.engine.hid_events)

    async def run(variables: object) -> Result:
        return await call(ctx, "sim_flow", {"action": "run", "name": "sign-in", "variables": variables})

    assert await run(None) == text(
        "the flow sign-in types {{email}}, {{password}}: give their values in variables; nothing was played", error=True
    )
    assert await run({"email": "a@b.co"}) == text(
        "the flow sign-in types {{password}}: give its value in variables; nothing was played", error=True
    )
    assert await run({"email": "a@b.co", "password": "x", "pin": "1"}) == text(
        "the flow sign-in does not use pin; nothing was played", error=True
    )
    assert await run({"email": "a@b.co", "password": ""}) == text(
        "variables: password is text of 1 to 2000 characters", error=True
    )
    assert await run(["a"]) == text(
        'variables is an object of names and their text, such as {"email": "test@example.com"}', error=True
    )
    assert await call(ctx, "sim_flow", {**run_sign_in(), "snapshot": "all"}) == text(
        "snapshot is diff, full or none", error=True
    )
    assert len(rig.idb.engine.hid_events) == played, "nothing was played"


async def test_a_run_stops_at_an_element_that_is_not_there_and_says_which_step(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    await saved_sign_in(ctx)
    rig.idb.engine.document = {"elements": LOGIN["elements"][:2]}
    played = await call(ctx, "sim_flow", run_sign_in())
    lines = said(played).splitlines()
    assert lines[-2].startswith(f'error step 3: e3 (button "Sign in") is not on screen after {FIND_S:g}s (#')
    assert lines[-1] == "stopped at step 3 of 3: it failed, and the steps after it were not played"
    assert played["isError"] is True and played["structuredContent"]["failed_step"] == 3
    assert played["structuredContent"]["completed_steps"] == 2
    assert played["structuredContent"]["failed_step_may_have_run"] is False


async def test_a_long_flow_is_played_in_calls_of_at_most_max_steps_and_numbered_whole(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    ctx = tools(rig)
    steps = [{"tap": [10, 10]}] * (MAX_STEPS + 2) + [{"tap": [10, 9000]}]
    saved = await call(ctx, "sim_flow", {"action": "save", "name": "long", "batches": [{"steps": steps}]})
    assert saved["isError"] is False
    played = await call(ctx, "sim_flow", {"action": "run", "name": "long", "snapshot": "none"})
    lines = said(played).splitlines()
    assert sum(line.startswith("ok tap (10,10)") for line in lines) == MAX_STEPS + 2
    assert lines[-2] == f"error step {MAX_STEPS + 3}: (10,9000) is off the 402x874pt screen"
    data = played["structuredContent"]
    assert data["completed_steps"] == MAX_STEPS + 2 and data["failed_step"] == MAX_STEPS + 3
    assert data["failed_step_may_have_run"] is True and data["wait_met"] is None
    instance = rig.manager.instance(CALLER.scope)
    assert instance is not None
    rig.set_state(instance.udid, "Shutdown")
    gone = await call(ctx, "sim_flow", {"action": "run", "name": "long", "snapshot": "none"})
    assert said(gone).endswith("\n" + SHUT_DOWN)


async def test_batches_each_wait_for_their_screen_and_a_wait_not_met_stops_the_run(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    ctx = tools(rig)
    batches = [
        {"steps": [{"press": "home"}], "wait": {"for": "General"}},
        {"steps": [{"press": "home"}], "wait": {"for": "Nowhere", "timeout_ms": 100}},
        {"steps": [{"press": "home"}]},
    ]
    await call(ctx, "sim_flow", {"action": "save", "name": "waits", "batches": batches})
    played = await call(ctx, "sim_flow", {"action": "run", "name": "waits"})
    lines = said(played).splitlines()
    assert lines[-1] == "stopped at step 2 of 3: its wait was not met, and the steps after it were not played"
    assert played["isError"] is True
    data = played["structuredContent"]
    assert data["completed_steps"] == 2 and data["wait_met"] is False and data["failed_step"] is None


async def test_a_run_keeps_observe_mode_unless_it_confirms_and_stops_on_a_busy_device(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    ctx = tools(rig)
    await call(ctx, "sim_snapshot", {})
    await call(ctx, "sim_flow", {"action": "save", "name": "general", "steps": [{"tap": "e2"}]})
    rig.config.set(agent_observe=True, agent_observe_words="general")
    ctx = dataclasses.replace(ctx, config=rig.config.get(CALLER.scope))
    general = {"action": "run", "name": "general", "snapshot": "none"}
    refused = await call(ctx, "sim_flow", general)
    assert refused["isError"] is True and 'error step 1: e2 "General" (201,319) looks like it changes' in said(refused)
    assert rig.idb.engine.hid_events == []
    confirmed = await call(ctx, "sim_flow", {**general, "confirm": True})
    assert said(confirmed).splitlines()[1] == 'ok tap e2 "General" (201,319), confirmed ("general")'
    assert await call(ctx, "sim_flow", {**general, "confirm": "yes"}) == text("confirm is true or false", error=True)
    instance = rig.manager.instance(CALLER.scope)
    assert instance is not None
    instance.busy = "building (b1)"
    busy = await call(ctx, "sim_flow", {**general, "confirm": True})
    assert said(busy).splitlines()[1] == "error step 1: the device is busy: building (b1)"
    assert busy["structuredContent"]["failed_step_may_have_run"] is False


async def test_a_screen_that_cannot_be_read_stops_the_run_before_the_step(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    ctx = tools(rig)
    await call(ctx, "sim_snapshot", {})
    await call(ctx, "sim_flow", {"action": "save", "name": "general", "steps": [{"tap": "e2"}]})
    rig.idb.engine.accessibility_errors = [ConnectorError("the companion did not answer")]
    played = await call(ctx, "sim_flow", {"action": "run", "name": "general", "snapshot": "none"})
    assert (
        said(played)
        .splitlines()[1]
        .startswith("error step 1: the screen could not be read: the companion did not answer")
    )
    assert played["structuredContent"]["failed_step_may_have_run"] is False


async def test_a_value_too_short_to_tell_from_other_words_is_said_as_typed(tmp_path: Path) -> None:
    rig = login(DeviceRig(tmp_path))
    ctx = tools(rig)
    await saved_sign_in(ctx)
    played = await call(ctx, "sim_flow", run_sign_in(email="ab", password="pw"))
    assert 'ok type "ab" into e1 "Email" (201,122)' in said(played).splitlines()
