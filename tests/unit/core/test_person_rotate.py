# SPDX-License-Identifier: Apache-2.0
"""A person turning a simulator from a viewer: Rotate Left and Rotate Right turn it a quarter through the same path an
agent's `sim_device rotate` takes, and every screen watching is told which way it now stands."""

from __future__ import annotations

from pathlib import Path

import pytest

from simtrail.connectors.base import Capability, ConnectorError, Screen
from simtrail.core.actions import AgentActions
from simtrail.core.manager import TURNS
from simtrail.core.screen_input import Command, PersonInput, translate
from simtrail.seams import Caller
from simtrail.testing.fakes import FULL_CONTROL, FakeConnector, FakeEngine
from simtrail.testing.rig import DeviceRig, scope

TURNABLE = FULL_CONTROL | {Capability.ROTATE}
CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude Code")
SCREEN = Screen(1206, 2622, 402, 874, 3.0)


def turnable(folder: Path, capabilities: frozenset[Capability] = TURNABLE) -> tuple[DeviceRig, FakeEngine]:
    engine = FakeEngine()
    return DeviceRig(folder, idb=FakeConnector("native", engine=engine, capabilities=capabilities)), engine


@pytest.mark.parametrize(
    ("message", "command"),
    [
        ({"type": "rotate", "direction": "left"}, Command("rotate", name="left")),
        ({"type": "rotate", "direction": "right"}, Command("rotate", name="right")),
        ({"type": "rotate", "direction": "up"}, None),
        ({"type": "rotate"}, None),
    ],
)
def test_a_rotate_message_is_read_only_with_a_direction_it_knows(message: object, command: Command | None) -> None:
    assert translate(message, SCREEN) == command


async def test_rotate_right_walks_the_four_ways_clockwise_and_left_walks_them_back(tmp_path: Path) -> None:
    rig, engine = turnable(tmp_path)
    instance = await rig.up()
    events = instance.events.subscribe()
    assert instance.describe(0)["orientation"] == "portrait"
    for _ in TURNS:
        await rig.manager.rotate_by(instance, "right")
    assert engine.turns == ["landscape_left", "portrait_upside_down", "landscape_right", "portrait"]
    await rig.manager.rotate_by(instance, "left")
    assert engine.turns[-1] == "landscape_right" and instance.turned == "landscape_right"
    told = [events.get_nowait() for _ in range(events.qsize())]
    assert [event["orientation"] for event in told if event["type"] == "status"] == [
        "landscape_left", "portrait_upside_down", "landscape_right", "portrait", "landscape_right",
    ]  # fmt: skip


async def test_a_device_whose_connector_cannot_turn_it_is_refused_and_left_as_it_was(tmp_path: Path) -> None:
    rig, engine = turnable(tmp_path, FULL_CONTROL)
    instance = await rig.up()
    with pytest.raises(ConnectorError, match="cannot turn it"):
        await rig.manager.rotate_by(instance, "left")
    assert engine.turns == [] and instance.turned == "portrait"


async def test_a_real_device_is_turned_in_the_hand(tmp_path: Path) -> None:
    rig, engine = turnable(tmp_path)
    instance = await rig.up()
    instance.kind = "physical"
    with pytest.raises(ConnectorError, match="turned in the hand"):
        await rig.manager.rotate_by(instance, "right")
    assert engine.turns == []


async def test_a_person_turning_the_device_goes_through_their_input_and_counts_as_their_touch(tmp_path: Path) -> None:
    rig, engine = turnable(tmp_path)
    instance = await rig.up()
    turned: list[str] = []
    touched: list[bool] = []

    async def rotate(direction: str) -> None:
        turned.append(direction)
        await rig.manager.rotate_by(instance, direction)

    person = PersonInput(None, rig.manager.changes(instance), on_touch=lambda: touched.append(True), rotate=rotate)
    await person.run(Command("rotate", name="left"))
    assert turned == ["left"] and touched == [True] and engine.turns == ["landscape_right"]
    with pytest.raises(ConnectorError, match="cannot be turned from here"):
        await PersonInput(None, rig.manager.changes(instance)).run(Command("rotate", name="left"))


async def test_an_agent_turning_the_device_tells_the_viewers_too(tmp_path: Path) -> None:
    rig, _engine = turnable(tmp_path)
    instance = await rig.up()

    async def sleep(seconds: float) -> None:
        rig.clock.advance(seconds)

    actions = AgentActions(rig.manager, rig.config, clock=rig.clock, sleep=sleep)
    await actions.rotate(instance, CALLER, "landscape_left")
    assert instance.describe(0)["orientation"] == "landscape_left"
