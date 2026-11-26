# SPDX-License-Identifier: Apache-2.0
"""Text an agent types into a secure field with `sim_act` is a password: the step's line, the viewers' events -- the
caption beside its pointer and what it is doing -- the macOS overlay and every answer after say ``••••``, never it."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from simtrail.connectors.base import ConnectorError
from simtrail.core.actions import AgentActions
from simtrail.core.instance import DeviceInstance
from simtrail.seams import Caller
from simtrail.testing.fakes import no_wait
from simtrail.testing.rig import DeviceRig, scope
from simtrail.tools.context import ToolContext
from simtrail.tools.registry import ToolRegistry
from simtrail.tools.results import Result

CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude · notes")
PASSWORD = "S3cr3t-hunter"


def _element(kind: str, label: str, y: float, **more: Any) -> dict[str, Any]:
    return {"type": kind, "label": label, "frame": {"x": 16, "y": y, "width": 370, "height": 44}, **more}


#: e1 the e-mail field, e2 the password field, e3 the button.
LOGIN = {
    "elements": [
        _element("TextField", "Email", 100),
        _element("SecureTextField", "Password", 160),
        _element("Button", "Sign in", 220),
    ]
}


class Rigged:
    def __init__(self, tmp_path: Path, document: dict[str, Any] = LOGIN) -> None:
        self.rig = DeviceRig(tmp_path)
        self.rig.idb.engine.document = document
        self.registry = ToolRegistry()
        self.ctx = ToolContext(
            manager=self.rig.manager,
            actions=AgentActions(self.rig.manager, self.rig.config, clock=self.rig.clock, sleep=no_wait),
            caller=CALLER,
            config=self.rig.config.get(CALLER.scope),
            copy=self.rig.copy,
            sleep=no_wait,
        )

    async def up(self) -> DeviceInstance:
        return await self.rig.up()

    async def call(self, name: str, arguments: dict[str, Any]) -> Result:
        return await self.registry.call(name, arguments, self.ctx)


def said(result: Result) -> str:
    return str(result["content"][0]["text"])


def drained(instance: DeviceInstance, events: Any) -> list[dict[str, Any]]:
    return [events.get_nowait() for _ in range(events.qsize())]


def typed(published: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [event for event in published if event.get("gesture", {}).get("kind") == "type"]


@pytest.mark.parametrize(
    "steps",
    [
        [{"type": PASSWORD, "into": "e2"}],
        [{"type": PASSWORD, "into": [201, 182]}],
        [{"tap": "e2"}, {"type": PASSWORD}],
    ],
    ids=["a ref", "a point", "the field last tapped"],
)
async def test_text_typed_into_a_secure_field_is_never_shown(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, steps: list[dict[str, Any]]
) -> None:
    caplog.set_level(logging.DEBUG)
    r = Rigged(tmp_path)
    instance = await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    events = instance.events.subscribe()
    answer = await r.call("sim_act", {"steps": steps, "snapshot": "none"})
    assert answer["isError"] is False, said(answer)
    assert 'type "••••"' in said(answer)
    published = drained(instance, events)
    assert [event["caption"] for event in typed(published)] == ["••••"]
    assert [event["activity"] for event in typed(published)] == ["Typing “••••”"]
    told = json.dumps([answer, published], ensure_ascii=False)
    assert PASSWORD not in told and PASSWORD not in caplog.text
    assert r.rig.idb.engine.hid_events, "the password still reached the device"


async def test_the_field_being_edited_when_the_agent_last_looked_counts_as_where_text_goes(tmp_path: Path) -> None:
    editing = {"elements": [_element("SecureTextField", "Password", 160, traits=["IsEditing"])]}
    r = Rigged(tmp_path, editing)
    instance = await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    events = instance.events.subscribe()
    answer = await r.call("sim_act", {"steps": [{"type": PASSWORD}], "snapshot": "none"})
    assert said(answer).startswith('ok type "••••"')
    assert PASSWORD not in json.dumps(drained(instance, events), ensure_ascii=False)


async def test_text_typed_into_an_ordinary_field_is_still_shown(tmp_path: Path) -> None:
    r = Rigged(tmp_path)
    instance = await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    events = instance.events.subscribe()
    answer = await r.call("sim_act", {"steps": [{"tap": "e2"}, {"type": "ann@example.com", "into": "e1"}]})
    assert 'ok type "ann@example.com" into e1 "Email"' in said(answer)
    assert [event["caption"] for event in typed(drained(instance, events))] == ["ann@example.com"]


async def test_a_password_typed_once_is_masked_in_every_answer_after(tmp_path: Path) -> None:
    r = Rigged(tmp_path)
    await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    await r.call("sim_act", {"steps": [{"type": PASSWORD, "into": "e2"}], "snapshot": "none"})
    # The app shows it back -- its eye tapped -- and the agent reads the screen.
    r.rig.idb.engine.document = {"elements": [_element("TextField", "Password", 160, value=PASSWORD)]}
    looked = await r.call("sim_snapshot", {"mode": "full"})
    assert PASSWORD not in said(looked) and "••••" in said(looked)


async def test_a_character_with_no_key_is_not_named_when_the_text_is_a_password(tmp_path: Path) -> None:
    r = Rigged(tmp_path)
    instance = await r.up()
    instance.runtime = "iOS 27.0"
    r.rig.keyboard.us = True
    await r.call("sim_snapshot", {"mode": "full"})
    answer = await r.call("sim_act", {"steps": [{"type": "pässwörd", "into": "e2"}], "snapshot": "none"})
    assert "pasted, since one of its characters has no key on a US keyboard" in said(answer), said(answer)
    assert "'ä'" not in said(answer) and "pässwörd" not in said(answer)


def test_a_context_with_no_mask_hides_nothing_and_does_not_fail(tmp_path: Path) -> None:
    from simtrail.tools.act import hide_typed

    r = Rigged(tmp_path)
    assert r.ctx.secrets is None, "only the registry gives a call its mask"
    hide_typed(r.ctx, (PASSWORD,))


# -- a call that ends with the password half typed ---------------------------------------------------------------------


def stopping_midway(monkeypatch: pytest.MonkeyPatch, engine: Any, then: Exception | asyncio.Event) -> None:
    """Make the device take two of a gesture's events, then fail with `then` -- or wait for ever, once it is set."""

    async def hid(events: Any) -> None:
        taken = 0
        async for event in events:
            engine.hid_events.append(event)
            taken += 1
            if taken == 2 and isinstance(then, Exception):
                raise then
            if taken == 2:
                then.set()
                await asyncio.Event().wait()

    monkeypatch.setattr(engine, "hid", hid)


async def shown_back(r: Rigged) -> str:
    """What the agent reads once the app shows the password in clear, as a field does when its eye is tapped."""
    r.rig.idb.engine.document = {"elements": [_element("TextField", "Password", 160, value=PASSWORD)]}
    return said(await r.call("sim_snapshot", {"mode": "full"}))


async def test_a_password_whose_typing_failed_midway_is_masked_in_every_answer_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = Rigged(tmp_path)
    await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    engine = r.rig.idb.engine
    stopping_midway(monkeypatch, engine, ConnectorError("the device went away"))
    answer = await r.call("sim_act", {"steps": [{"type": PASSWORD, "into": "e2"}], "snapshot": "none"})
    assert answer["isError"] is True and 'error step 1: type "••••" into e2' in said(answer)
    assert len(engine.hid_events) == 2, "part of it reached the device"
    monkeypatch.undo()
    looked = await shown_back(r)
    assert PASSWORD not in looked and "••••" in looked


async def test_a_password_whose_typing_was_cancelled_midway_is_masked_in_every_answer_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = Rigged(tmp_path)
    await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    engine = r.rig.idb.engine
    typing = asyncio.Event()
    stopping_midway(monkeypatch, engine, typing)
    steps = [{"type": PASSWORD, "into": "e2"}]
    calling = asyncio.ensure_future(r.call("sim_act", {"steps": steps, "snapshot": "none"}))
    await typing.wait()
    calling.cancel()
    with pytest.raises(asyncio.CancelledError):
        await calling
    monkeypatch.undo()
    looked = await shown_back(r)
    assert PASSWORD not in looked and "••••" in looked


# -- a password struck one key at a time -------------------------------------------------------------------------------


async def test_characters_struck_one_key_at_a_time_into_a_secure_field_are_never_shown(tmp_path: Path) -> None:
    r = Rigged(tmp_path)
    instance = await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    events = instance.events.subscribe()
    struck = " ".join(PASSWORD)
    answer = await r.call("sim_act", {"steps": [{"tap": "e2"}, {"keys": struck}, {"press": "x"}], "snapshot": "none"})
    assert answer["isError"] is False, said(answer)
    assert "ok keys ••••" in said(answer) and "ok press ••••" in said(answer)
    published = drained(instance, events)
    captions = [event["caption"] for event in published if event.get("gesture", {}).get("kind") in ("keys", "press")]
    assert captions == ["••••", "••••"]
    told = json.dumps([answer, published], ensure_ascii=False)
    assert struck not in told and PASSWORD not in told and "press x" not in told
    looked = await shown_back(r)
    assert PASSWORD not in looked and "••••" in looked, "what the keys typed is masked after, as typed text is"


async def test_a_shortcut_in_a_secure_field_and_keys_in_an_ordinary_one_are_still_said(tmp_path: Path) -> None:
    r = Rigged(tmp_path)
    await r.up()
    await r.call("sim_snapshot", {"mode": "full"})
    steps = [{"tap": "e2"}, {"keys": "cmd+a"}, {"press": "delete"}, {"tap": "e1"}, {"keys": "a n n"}, {"press": "x"}]
    answer = await r.call("sim_act", {"steps": steps, "snapshot": "none"})
    assert answer["isError"] is False, said(answer)
    for line in ("ok keys cmd+a", "ok press delete", "ok keys a n n", "ok press x"):
        assert line in said(answer)
