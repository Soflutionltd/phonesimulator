# SPDX-License-Identifier: Apache-2.0
"""`sim_snapshot`'s keyboard: one line by default, each key when asked for with ``keys``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from phonesimulator.core.actions import AgentActions
from phonesimulator.seams import Caller
from phonesimulator.testing.fakes import no_wait
from phonesimulator.testing.rig import DeviceRig, scope
from phonesimulator.tools.context import ToolContext
from phonesimulator.tools.registry import ToolRegistry
from phonesimulator.tools.results import Result

CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude · notes")


def _element(kind: str, label: str, y: float) -> dict[str, Any]:
    return {"type": kind, "label": label, "frame": {"x": 16, "y": y, "width": 370, "height": 44}}


TYPING = {"elements": [_element("TextField", "Email", 100), _element("Key", "a", 600), _element("Key", "z", 650)]}


def tools(rig: DeviceRig) -> ToolContext:
    actions = AgentActions(rig.manager, rig.config, clock=rig.clock, sleep=no_wait)
    return ToolContext(manager=rig.manager, actions=actions, caller=CALLER, config=rig.config.get(CALLER.scope))


async def call(ctx: ToolContext, name: str, arguments: object) -> Result:
    return await ToolRegistry().call(name, arguments, ctx)


async def test_a_snapshot_says_the_keyboard_in_one_line_unless_keys_asks_for_each(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    rig.idb.engine.document = TYPING
    ctx = tools(rig)
    await rig.up()
    full = str((await call(ctx, "sim_snapshot", {"mode": "full"}))["content"][0]["text"])
    assert "[keyboard e2…e3: 2 keys a|z; sim_snapshot keys: true lists each]" in full and 'key "a"' not in full
    each = str((await call(ctx, "sim_snapshot", {"keys": True}))["content"][0]["text"])
    assert 'e2 key "a"' in each and 'e3 key "z"' in each, "listed whole even where a diff was asked for"
    refused = await call(ctx, "sim_snapshot", {"keys": "yes"})
    assert refused["isError"] is True and refused["content"][0]["text"] == "keys is true or false"
