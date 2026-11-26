# SPDX-License-Identifier: Apache-2.0
"""A scope's simulator attached ahead of its agent's first call (`DeviceManager.warm`): only one already booted, once,
holding nothing for any agent -- never booting, creating, ending another, or touching a real or Android device."""

from __future__ import annotations

from pathlib import Path

from rocketwright.core.backends import DeviceBackend
from rocketwright.core.instance import READY, STOPPED
from rocketwright.protocol import DeviceKind
from rocketwright.storage.claims import Claims
from rocketwright.testing.fakes import (
    BOOTED_UDID,
    EMULATOR_UDID,
    PHONE_UDID,
    FakeAndroidBackend,
    FakeConnector,
    FakePhoneBackend,
    fixture_udid,
)
from rocketwright.testing.rig import DeviceRig, scope

SHUTDOWN_UDID = fixture_udid("iPhone 17 Pro Max")
TP1, TP2 = scope("tp-1"), scope("tp-2")


def created_or_booted(rig: DeviceRig) -> list[tuple[str, ...]]:
    return [argv for argv in rig.argv() if argv[:2] in {("simctl", "create"), ("simctl", "boot")}]


async def test_a_booted_simulator_is_attached_in_the_background_once_and_held_for_nobody(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    rig.config.set(idle_minutes=5)
    rig.manager.directory.memory.choose(TP1, False, BOOTED_UDID)
    assert await rig.manager.warm(TP1) == ("warming", None)
    instance = rig.manager.instance(TP1)
    assert instance is not None and instance.udid == BOOTED_UDID and instance.task is not None
    await instance.task
    assert instance.state == READY and rig.idb.attached == [BOOTED_UDID] and not instance.booted_by_us
    assert await rig.manager.warm(TP1) == ("running", None), "asked again, nothing more is done"
    assert rig.idb.attached == [BOOTED_UDID] and rig.manager.instances() == [instance]
    assert await rig.manager.ensure(TP1) is instance, "the agent's first call finds it attached"
    assert not rig.manager.in_use(instance), "no agent holds it"
    rig.clock.now += 5 * 60
    assert await rig.manager.reap() == [BOOTED_UDID], "left unused, it idles out like any other"
    assert instance.state == STOPPED and ("simctl", "shutdown", BOOTED_UDID) not in rig.argv()
    assert created_or_booted(rig) == []


async def test_nothing_is_booted_or_created_to_warm_up(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    assert await rig.manager.warm(TP1) == ("skipped", "the scope has no device yet")
    rig.manager.directory.memory.choose(TP1, False, SHUTDOWN_UDID)
    assert await rig.manager.warm(TP1) == ("skipped", "the simulator is not booted")
    assert rig.manager.instances() == [] and created_or_booted(rig) == []


async def test_a_real_or_android_device_is_never_touched_to_warm_up(tmp_path: Path) -> None:
    phone = FakeConnector("phone", kinds=frozenset({"physical"}))
    android = FakeConnector("android", kinds=frozenset({"android"}))
    rig = DeviceRig(tmp_path, phones=FakePhoneBackend(), phone=phone, androids=FakeAndroidBackend(), android=android)
    rig.config.set(real_devices=True, android=True)
    rig.manager.directory.memory.choose(TP1, False, PHONE_UDID)
    rig.manager.directory.memory.choose(TP2, False, EMULATOR_UDID)
    for each in (TP1, TP2):
        assert await rig.manager.warm(each) == ("skipped", "the scope's device is not a simulator")
    assert rig.manager.instances() == [] and phone.attached == [] and android.attached == []
    simulators: dict[DeviceKind, DeviceBackend] = {"simulator": FakePhoneBackend()}
    rig.manager.backends = simulators
    rig.manager.directory.memory.choose(TP1, False, BOOTED_UDID)
    assert await rig.manager.warm(TP1) == ("skipped", "the scope's device is not a simulator"), "nor another backend"


async def test_warm_up_is_off_with_its_setting_or_the_agent_tools(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    rig.manager.directory.memory.choose(TP1, False, BOOTED_UDID)
    off = ("skipped", "agent.warm_up or agent.tools is off")
    rig.config.set(agent_warm_up=False)
    assert await rig.manager.warm(TP1) == off
    rig.config.set(agent_warm_up=True, agent_tools=False)
    assert await rig.manager.warm(TP1) == off
    rig.config.set(agent_tools=True, enabled=False)
    assert await rig.manager.warm(TP1) == ("skipped", "the scope cannot have a simulator now")
    assert rig.manager.instances() == [] and rig.xcrun.calls == []


async def test_warm_up_never_ends_another_device_nor_takes_one_another_process_drives(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    rig.config.set(max_booted=1)
    rig.manager.directory.memory.choose(TP1, False, SHUTDOWN_UDID)
    first = await rig.up("tp-1")
    rig.manager.directory.memory.choose(TP2, False, BOOTED_UDID)
    assert await rig.manager.warm(TP2) == ("skipped", "as many devices run as device.max_booted allows")
    assert first.state == READY and rig.manager.instance(TP2) is None
    await rig.manager.stop(TP1)
    rig.alive_pids.add(9999)

    async def started(pid: int) -> str | None:
        return f"started-{pid}"

    other = Claims(tmp_path / "claims", owner="Host", pid=9999, pid_alive=lambda pid: True, start_time=started)
    await other.acquire(BOOTED_UDID)
    assert await rig.manager.warm(TP2) == ("skipped", "another process drives the simulator")
    assert rig.manager.instance(TP2) is None


async def test_a_simulator_another_scope_runs_is_left_for_the_first_call_to_join(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    rig.manager.directory.memory.choose(TP1, False, BOOTED_UDID)
    running = await rig.up("tp-1")
    rig.manager.directory.memory.choose(TP2, False, BOOTED_UDID)
    assert await rig.manager.warm(TP2) == ("running", None)
    assert running.scopes == {"tp-1"} and rig.idb.attached == [BOOTED_UDID]


async def test_a_simulator_that_cannot_be_listed_is_skipped_saying_why(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    rig.manager.directory.memory.choose(TP1, False, BOOTED_UDID)
    rig.xcrun.on("simctl", "list", "devices", "-j", rc=1, err="simctl broke")
    outcome, reason = await rig.manager.warm(TP1)
    assert outcome == "skipped" and reason is not None and "simctl broke" in reason
    assert rig.manager.instances() == []
