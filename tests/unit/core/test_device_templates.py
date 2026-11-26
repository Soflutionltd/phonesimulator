# SPDX-License-Identifier: Apache-2.0
"""Simulator templates (``device.templates``): a new device is copied from one booted once, rather than created blank
-- the first of a runtime and type created as before while its template is prepared in the background, within
``device.max_booted``, never failing anything. A template is nobody's device, never offered, never deleted."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import pytest

from simtrail.config.model import SimConfig
from simtrail.core.cleanup import prune
from simtrail.core.devices import (
    DeviceDirectory,
    DeviceTemplates,
    JsonDeviceMemory,
    Template,
    template_name,
)
from simtrail.core.manager import SimulatorUnavailable
from simtrail.platform.simctl import DeviceType, Runtime, Simctl, SimctlError
from simtrail.platform.xcrun import XcrunResult
from simtrail.scope import Scope
from simtrail.testing.fakes import MemoryStateStore, made
from simtrail.testing.rig import DeviceRig, scope

RUNTIME = "com.apple.CoreSimulator.SimRuntime.iOS-26-5"
PHONE = "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro"
TEMPLATE_NAME = "Simtrail · template · iPhone 17 Pro · iOS 26.5"
TP1, TP2, TP3 = scope("tp-1"), scope("tp-2"), scope("tp-3")


def rig_with_templates(tmp_path: Path, **settings: object) -> DeviceRig:
    rig = DeviceRig(tmp_path)
    rig.config.set(device_templates=True, **settings)
    return rig


def listed(rig: DeviceRig, udid: str) -> dict[str, object] | None:
    return next((e for entries in rig.devices["devices"].values() for e in entries if e["udid"] == udid), None)


def state(rig: DeviceRig, udid: str) -> object:
    entry = listed(rig, udid)
    return None if entry is None else entry["state"]


def remove(rig: DeviceRig, udid: str) -> None:
    for entries in rig.devices["devices"].values():
        entries[:] = [entry for entry in entries if entry["udid"] != udid]


def calls(rig: DeviceRig, start: int = 0) -> list[tuple[str, ...]]:
    """What simctl was asked to do since `start`, listings left out."""
    return [args[1:4] for args in rig.argv()[start:] if args[0] == "simctl" and args[1] != "list"]


async def test_the_first_device_is_created_blank_and_its_template_prepared_in_the_background(tmp_path: Path) -> None:
    rig = rig_with_templates(tmp_path)
    instance = await rig.up()
    assert instance.udid == made(1) and instance.created
    await rig.manager.directory.settle()
    template = made(2)
    assert calls(rig)[0] == ("create", "Simtrail · alpha · tp-1", PHONE), "the device first, created blank"
    assert [args for args in calls(rig) if TEMPLATE_NAME in args or template in args] == [
        ("create", TEMPLATE_NAME, PHONE),
        ("boot", template),
        ("bootstatus", template, "-b"),
        ("shutdown", template),
    ]
    assert rig.memory.template(RUNTIME, PHONE) == Template(template, ready=True)
    assert state(rig, template) == "Shutdown"
    assert template not in rig.memory.all_created() and rig.memory.all_templates() == {template}
    stored = json.loads((tmp_path / "state" / "devices.json").read_text())
    assert stored["templates"] == {f"{RUNTIME}|{PHONE}": {"udid": template, "ready": True, "used": rig.wall.now}}


async def test_the_next_device_is_copied_from_the_template_and_remembered_as_made(tmp_path: Path) -> None:
    rig = rig_with_templates(tmp_path)
    await rig.up()
    await rig.manager.directory.settle()
    start = len(rig.argv())
    second = await rig.up("tp-2")
    assert second.udid == made(3) and second.created and second.name == "Simtrail · alpha · tp-2"
    assert ("clone", made(2), "Simtrail · alpha · tp-2") in calls(rig, start)
    assert not any(args[0] == "create" for args in calls(rig, start)), "nothing created blank"
    assert rig.memory.all_created() == {made(1), made(3)} and rig.memory.assigned(TP2, False) == made(3)
    assert rig.memory.holders(made(2)) == set()


async def test_a_template_is_never_offered_nor_chosen_nor_deleted(tmp_path: Path) -> None:
    rig = rig_with_templates(tmp_path, idle_minutes=5, delete_created="idle")
    first = await rig.up()
    await rig.manager.directory.settle()
    template = made(2)
    offered = {choice["udid"] for choice in await rig.manager.devices(TP1)}
    assert first.udid in offered and template not in offered
    with pytest.raises(SimulatorUnavailable) as refused:
        await rig.manager.choose(TP1, template)
    assert refused.value.status == 404 and rig.memory.holders(template) == set()
    rig.clock.now += 5 * 60
    assert await rig.manager.reap() == [first.udid]
    deleted = [args[2] for args in rig.argv() if args[:2] == ("simctl", "delete")]
    assert deleted == [first.udid], "the idle clean-up deletes the device, never the template"
    # Even remembered as made -- by a hand-edited file -- a template is passed over by pruning, --all too.
    stored = tmp_path / "state" / "devices.json"
    data = json.loads(stored.read_text())
    stored.write_text(json.dumps({**data, "created": [template]}))
    pruned = await rig.manager.prune(everything=True, dry_run=False)
    assert pruned == [] and listed(rig, template) is not None
    assert rig.memory.all_templates() == {template}


async def test_a_template_gone_or_unavailable_is_forgotten_and_the_device_created_and_another_template_made(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    rig = rig_with_templates(tmp_path)
    await rig.up()
    await rig.manager.directory.settle()
    remove(rig, made(2))
    second = await rig.up("tp-2")
    assert second.udid == made(3), "created blank, not copied"
    assert f"forgot the simulator template {made(2)}: it is no longer listed" in caplog.text
    await rig.manager.directory.settle()
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(4), ready=True)
    entry = listed(rig, made(4))
    assert entry is not None
    entry["isAvailable"] = False
    third = await rig.up("tp-3")
    assert third.udid == made(5) and f"forgot the simulator template {made(4)}: it is not available" in caplog.text
    await rig.manager.directory.settle()
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(6), ready=True)


async def test_with_templates_off_every_device_is_created_and_none_prepared(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    assert rig.config.config.device_templates is False
    await rig.up()
    await rig.up("tp-2")
    await rig.manager.directory.settle()
    assert [args[0] for args in calls(rig) if args[0] in ("create", "clone")] == ["create", "create"]
    assert rig.memory.all_templates() == set() and "templates" not in json.loads(
        (tmp_path / "state" / "devices.json").read_text()
    )


async def test_a_template_that_will_not_boot_is_logged_shut_down_and_made_again_next_time(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = rig_with_templates(tmp_path)
    rig.xcrun.on("simctl", "bootstatus", made(2), rc=1, err="Unable to boot: the runtime is broken")
    first = await rig.up()
    await rig.manager.directory.settle()
    assert first.state == "ready", "a template's failure breaks nothing"
    assert "could not prepare the simulator template for iPhone 17 Pro on iOS 26.5" in caplog.text
    assert "the runtime is broken" in caplog.text
    assert ("simctl", "shutdown", made(2)) in rig.argv(), "left shut down, not booted"
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(2), ready=False)
    start = len(rig.argv())
    rig.xcrun.on("simctl", "bootstatus", rc=0)
    second = await rig.up("tp-2")
    assert second.udid == made(3), "an unready template is not copied"
    await rig.manager.directory.settle()
    assert ("boot", made(2)) in calls(rig, start) and not any(args == ("create", TEMPLATE_NAME, PHONE)
                                                               for args in calls(rig, start))  # fmt: skip
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(2), ready=True)


async def test_a_template_is_not_booted_past_max_booted_and_is_tried_again_by_the_reaper(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    rig = rig_with_templates(tmp_path, max_booted=1, idle_minutes=5, delete_created="never")
    first = await rig.up()
    await rig.manager.directory.settle()
    assert ("simctl", "boot", made(2)) not in rig.argv()
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(2), ready=False)
    assert "left the simulator template for iPhone 17 Pro on iOS 26.5 unbooted: 1 simulators run" in caplog.text
    rig.clock.now += 5 * 60
    assert await rig.manager.reap() == [first.udid]
    await rig.manager.directory.settle()
    assert ("simctl", "boot", made(2)) in rig.argv()
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(2), ready=True)
    await rig.manager.reap()
    await rig.manager.directory.settle()
    assert rig.argv().count(("simctl", "boot", made(2))) == 1, "nothing left to try again"


async def test_a_template_another_process_prepared_meanwhile_is_not_booted_again(tmp_path: Path) -> None:
    rig = rig_with_templates(tmp_path, max_booted=1)
    await rig.up()
    await rig.manager.directory.settle()
    rig.memory.remember_template(RUNTIME, PHONE, made(2), ready=True)
    rig.manager.directory.retry_templates()
    await rig.manager.directory.settle()
    assert ("simctl", "boot", made(2)) not in rig.argv()


async def test_a_template_that_cannot_be_copied_or_is_running_leaves_the_device_created_blank(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    rig = rig_with_templates(tmp_path)
    await rig.up()
    await rig.manager.directory.settle()
    rig.set_state(made(2), "Booted")
    second = await rig.up("tp-2")
    assert second.udid == made(3) and ("simctl", "clone", made(2), "Simtrail · alpha · tp-2") not in rig.argv()
    assert f"the template {TEMPLATE_NAME} is not shut down (Booted)" in caplog.text
    rig.set_state(made(2), "Shutdown")
    rig.xcrun.on("simctl", "clone", rc=1, err="Unable to clone: disk full")
    third = await rig.up("tp-3")
    assert third.udid == made(4) and f"could not copy the template {TEMPLATE_NAME}" in caplog.text
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(2), ready=True), "kept: it is still there"


async def test_one_preparation_at_a_time_and_closing_stops_it_shut_down(tmp_path: Path) -> None:
    rig = rig_with_templates(tmp_path)
    gate = asyncio.Event()
    inner = rig.xcrun

    async def slow(
        *args: str,
        timeout: float = 30.0,
        developer_dir: str = "",
        input_data: bytes | None = None,
        cwd: Path | str | None = None,
    ) -> XcrunResult:
        if args[:2] == ("simctl", "bootstatus") and args[2] == made(2):
            await gate.wait()
        return await inner(*args, timeout=timeout, developer_dir=developer_dir, input_data=input_data, cwd=cwd)

    directory = rig.manager.directory
    simctl = Simctl(slow)
    config = rig.config.config
    first = await directory.resolve(simctl, TP1, config)
    for _ in range(5):
        await asyncio.sleep(0)
    assert ("simctl", "boot", made(2)) in rig.argv() and directory.running() == set()
    second = await directory.resolve(simctl, TP2, config)
    assert (first.udid, second.udid) == (made(1), made(3)), "created blank while the template boots"
    assert rig.argv().count(("simctl", "create", TEMPLATE_NAME, PHONE, RUNTIME)) == 1, "one preparation"
    await directory.close()
    assert ("simctl", "shutdown", made(2)) in rig.argv() and state(rig, made(2)) == "Shutdown"
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(2), ready=False)
    await directory.close()


def test_template_memory_reads_what_it_can_and_keeps_the_rest(tmp_path: Path) -> None:
    memory = JsonDeviceMemory(MemoryStateStore(tmp_path).devices_file())
    assert isinstance(memory, DeviceTemplates)
    assert memory.template(RUNTIME, PHONE) is None and memory.all_templates() == set()
    memory.remember_template(RUNTIME, PHONE, made(9), ready=False)
    memory.remember_created(TP1, False, made(1))
    memory.forget_created(made(1))
    assert memory.template(RUNTIME, PHONE) == Template(made(9), ready=False), "forgetting a device keeps templates"
    memory.forget_template(made(8))
    memory.forget_template(made(9))
    assert memory.all_templates() == set()
    stored = tmp_path / "state" / "devices.json"
    stored.write_text(json.dumps({"templates": {"a|b": {"udid": made(7), "ready": "yes"}, "c|d": ["x"], "e|f": {}}}))
    assert memory.template("a", "b") == Template(made(7), ready=False) and memory.all_templates() == {made(7)}
    stored.write_text(json.dumps({"templates": ["x"]}))
    assert memory.all_templates() == set()
    kind = DeviceType(PHONE, "iPhone 17 Pro", "iPhone")
    runtime = Runtime(RUNTIME, "iOS 26.5", "26.5", "iOS", True, (kind,))
    assert template_name("Host", kind, runtime) == "Host · template · iPhone 17 Pro · iOS 26.5"


class PlainMemory:
    """A host's own `DeviceMemory`, which cannot remember templates."""

    def __init__(self, inner: JsonDeviceMemory) -> None:
        self._inner = inner

    def assigned(self, scope: Scope, shared: bool) -> str | None:
        return self._inner.assigned(scope, shared)

    def created(self, scope: Scope) -> set[str]:
        return self._inner.created(scope)

    def choose(self, scope: Scope, shared: bool, udid: str) -> None:
        self._inner.choose(scope, shared, udid)

    def forget(self, scope: Scope, shared: bool) -> str | None:
        return self._inner.forget(scope, shared)

    def remember_created(self, scope: Scope, shared: bool, udid: str) -> None:
        self._inner.remember_created(scope, shared, udid)


async def test_under_a_memory_that_cannot_remember_templates_every_device_is_created(tmp_path: Path) -> None:
    rig = rig_with_templates(tmp_path)
    plain = PlainMemory(rig.memory)
    assert not isinstance(plain, DeviceTemplates)
    directory = DeviceDirectory(plain)
    simctl = Simctl(rig.xcrun)
    config = SimConfig.defaults()
    assert config.device_templates is True
    await directory.resolve(simctl, TP1, config)
    await directory.resolve(simctl, TP2, config)
    await directory.settle()
    assert [args[0] for args in calls(rig) if args[0] in ("create", "clone")] == ["create", "create"]
    assert directory.templates() == set()
    pruned = await prune(simctl, rig.memory, running=(), everything=True, dry_run=True, env={}, home=tmp_path)
    assert {entry.udid for entry in pruned} == {made(1), made(2)}


async def test_the_rigs_simctl_refuses_to_copy_a_device_it_does_not_have_or_that_is_running(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    simctl = Simctl(rig.xcrun)
    with pytest.raises(SimctlError, match="Invalid device"):
        await simctl.clone(made(42), "copy")
    created = await simctl.create("source", PHONE, RUNTIME)
    rig.set_state(created, "Booted")
    with pytest.raises(SimctlError, match="current state: Booted"):
        await simctl.clone(created, "copy")


# -- expiry (device.template_days) ------------------------------------------------------------------------------------

DAY = 86400


def deleted(rig: DeviceRig) -> list[str]:
    return [args[2] for args in rig.argv() if args[:2] == ("simctl", "delete")]


async def test_a_template_no_device_was_copied_from_for_its_days_is_deleted_and_made_again_on_demand(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    rig = rig_with_templates(tmp_path, idle_minutes=240, template_keep="")
    await rig.up()
    await rig.manager.directory.settle()
    template = made(2)
    made_at = rig.wall.now
    assert rig.memory.templates_used() == {template: made_at}, "its making is its first use"
    rig.wall.advance(20 * DAY)
    await rig.up("tp-2")
    assert rig.memory.templates_used() == {template: made_at + 20 * DAY}, "a copy dates it again"
    rig.wall.advance(29 * DAY)
    await rig.manager.reap()
    assert deleted(rig) == [] and rig.memory.all_templates() == {template}
    rig.wall.advance(DAY)
    await rig.manager.reap()
    assert deleted(rig) == [template] and rig.memory.all_templates() == set()
    assert f"deleted the simulator template {template}: no device was copied from it for 30 days" in caplog.text
    remove(rig, template)
    # Asked for again, it is made again: the device created blank meanwhile.
    third = await rig.up("tp-3")
    await rig.manager.directory.settle()
    assert ("create", TEMPLATE_NAME, PHONE) in calls(rig) and third.created
    assert rig.memory.template(RUNTIME, PHONE) == Template(made(5), ready=True)


async def test_templates_are_kept_at_zero_days_and_while_no_device_runs_to_read_the_setting_from(
    tmp_path: Path,
) -> None:
    rig = rig_with_templates(tmp_path, template_days=0, idle_minutes=240)
    await rig.up()
    await rig.manager.directory.settle()
    rig.wall.advance(400 * DAY)
    await rig.manager.reap()
    assert deleted(rig) == [] and rig.memory.all_templates() == {made(2)}
    rig.config.set(template_days=30)
    await rig.manager.stop(TP1)
    rig.clock.advance(1)
    await rig.manager.reap()
    assert deleted(rig) == [], "no device's settings to go by: never the defaults"


async def test_a_template_never_dated_is_dated_first_and_one_simctl_cannot_delete_is_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = rig_with_templates(tmp_path)
    directory = DeviceDirectory(rig.memory, wall=rig.wall)
    simctl = Simctl(rig.xcrun)
    config = SimConfig.defaults().overlay({"template_keep": ""})
    rig.memory.remember_template(RUNTIME, PHONE, "OLD", ready=True)
    assert rig.memory.templates_used() == {"OLD": None}, "a file from before templates were dated"
    assert await directory.expire_templates(simctl, config) == []
    assert rig.memory.templates_used() == {"OLD": rig.wall.now}
    rig.wall.advance(31 * DAY)
    rig.xcrun.on("simctl", "delete", rc=1, err="Unable to delete: busy")
    assert await directory.expire_templates(simctl, config) == []
    assert rig.memory.all_templates() == {"OLD"} and "could not delete the simulator template OLD" in caplog.text


async def test_a_template_being_booted_or_under_a_memory_that_does_not_date_them_is_never_deleted(
    tmp_path: Path,
) -> None:
    rig = rig_with_templates(tmp_path)
    simctl = Simctl(rig.xcrun)
    config = SimConfig.defaults()
    rig.memory.remember_template(RUNTIME, PHONE, "BOOTING", ready=False)
    rig.memory.template_used("BOOTING", rig.wall.now - 90 * DAY)
    directory = DeviceDirectory(rig.memory, wall=rig.wall)
    directory._booting.add("BOOTING")
    assert await directory.expire_templates(simctl, config) == []
    plain = DeviceDirectory(PlainMemory(rig.memory), wall=rig.wall)
    assert await plain.expire_templates(simctl, config) == []
    assert deleted(rig) == []


def test_a_templates_date_is_kept_when_it_is_remembered_again_and_dropped_for_another(tmp_path: Path) -> None:
    memory = JsonDeviceMemory(tmp_path / "devices.json")
    memory.remember_template(RUNTIME, PHONE, "T1", ready=False)
    memory.template_used("T1", 5.0)
    memory.remember_template(RUNTIME, PHONE, "T1", ready=True)
    assert memory.templates_used() == {"T1": 5.0}
    memory.remember_template(RUNTIME, PHONE, "T2", ready=False)
    assert memory.templates_used() == {"T2": None}


async def test_the_kept_device_types_template_is_made_ahead_never_deleted_and_made_again_when_gone(
    tmp_path: Path,
) -> None:
    rig = rig_with_templates(tmp_path, idle_minutes=240)
    assert rig.config.get(TP1).template_keep == "iPhone 17 Pro", "the default keeps the iPhone 17 Pro"
    directory = rig.manager.directory
    simctl = Simctl(rig.xcrun)
    config = rig.config.get(TP1)
    await directory.keep_templates(simctl, config)
    await directory.settle()
    template = rig.memory.template(RUNTIME, PHONE)
    assert template is not None and template.ready, "made ahead, with no device asked for"
    rig.wall.advance(400 * DAY)
    assert await directory.expire_templates(simctl, config) == []
    assert rig.memory.all_templates() == {template.udid}, "never deleted, however long unused"
    await directory.keep_templates(simctl, config)
    await directory.settle()
    assert rig.memory.template(RUNTIME, PHONE) == template, "one ready is left as it is"
    remove(rig, template.udid)
    await directory.keep_templates(simctl, config)
    await directory.settle()
    again = rig.memory.template(RUNTIME, PHONE)
    assert again is not None and again.ready and again.udid != template.udid, "made again when it went away"


async def test_the_reaper_keeps_the_kept_template_and_names_the_newest_ios_does_not_run_are_passed_over(
    tmp_path: Path,
) -> None:
    rig = rig_with_templates(tmp_path, idle_minutes=240, template_keep="iPhone 17 Pro, Galaxy S30")
    await rig.up()
    await rig.manager.directory.settle()
    rig.wall.advance(400 * DAY)
    await rig.manager.reap()
    await rig.manager.directory.settle()
    assert deleted(rig) == [] and rig.memory.template(RUNTIME, PHONE) is not None
    rig.config.set(device_templates=False)
    await rig.manager.directory.keep_templates(Simctl(rig.xcrun), rig.config.get(TP1))
    assert not rig.manager.directory._preparing, "nothing is made while templates are off"
