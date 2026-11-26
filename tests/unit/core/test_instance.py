# SPDX-License-Identifier: Apache-2.0
"""A running device as a viewer is told about it, and when it may be shut down."""

from __future__ import annotations

from rocketwright.connectors.base import Capability, DeviceSession
from rocketwright.core.instance import BOOTING, READY, STOPPED, DeviceInstance
from rocketwright.scope import Scope
from rocketwright.testing.fakes import SCREEN, FakeEngine


def instance(**changes: object) -> DeviceInstance:
    values: dict[str, object] = {
        "udid": "U",
        "name": "iPhone 17 Pro",
        "runtime": "iOS 26.5",
        "owner": Scope(id="demo", group="team", label="demo"),
        "developer_dir": "",
        "scopes": {"demo"},
        "created": False,
        "connector": "idb",
        "capabilities": frozenset({Capability.SCREENSHOT}),
        "since": 10.0,
        **changes,
    }
    return DeviceInstance(**values)  # type: ignore[arg-type]


def test_a_device_describes_its_state_and_screen_as_the_protocol_does() -> None:
    booting = instance()
    assert booting.state == BOOTING and booting.live and booting.group == "team"
    assert booting.describe(10.25) == {
        "udid": "U",
        "name": "iPhone 17 Pro",
        "runtime": "iOS 26.5",
        "state": "booting",
        "reason": None,
        "since_ms": 250,
        "viewers": 0,
        "projects": ["demo"],
        "busy": None,
        "created": False,
        "booted_by_us": False,
        "screen": None,
        "app_hierarchy": None,
        "kind": "simulator",
        "connection": None,
        "buttons": [],
        "recording": None,
        "appearance": None,
        "orientation": "portrait",
    }
    iphone = instance(kind="physical", connection="usb")
    assert (iphone.describe(10.25)["kind"], iphone.describe(10.25)["connection"]) == ("physical", "usb")
    ready = instance(state=READY, screen=SCREEN)
    assert ready.describe(9.0)["since_ms"] == 0
    assert ready.describe(10.0)["screen"] == {
        "points": {"w": 402, "h": 874},
        "pixels": {"w": 1206, "h": 2622},
        "scale": 3.0,
    }
    assert not instance(state=STOPPED).live
    attached = instance(state=READY, screen=SCREEN)
    attached.session = DeviceSession("fake", frozenset({Capability.INPUT_BUTTON}), FakeEngine(), buttons=("back",))
    assert attached.describe(10.0)["buttons"] == ["back"]


def test_only_what_rocketwright_booted_or_made_may_be_shut_down() -> None:
    assert not instance().may_shut_down
    assert instance(booted_by_us=True).may_shut_down and instance(created=True).may_shut_down


def test_a_device_names_every_project_using_it_once_and_sorted() -> None:
    shared = instance()
    shared.members["b"] = Scope(id="b", group="team", label="Courly")
    shared.members["c"] = Scope(id="c", group="team", label="Courly")
    assert shared.describe(10.0)["projects"] == ["Courly", "demo"]
