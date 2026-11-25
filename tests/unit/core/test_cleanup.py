# SPDX-License-Identifier: Apache-2.0
"""Deleting the simulators Simtrail made once nobody needs them: by the reaper as ``device.delete_created`` allows,
and by ``simtrail devices prune`` -- never one a person made or picked, one another scope remembers, or one running."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pytest

from simtrail.core.cleanup import NO_FOLDER, RUNNING, Pruned, holding, prune
from simtrail.core.devices import CreatedDevices, JsonDeviceMemory
from simtrail.core.manager import SimulatorUnavailable
from simtrail.platform.device_data import devices_dir
from simtrail.platform.simctl import Simctl, SimctlError
from simtrail.scope import Scope
from simtrail.seams import DeviceMemory
from simtrail.testing.fakes import BOOTED_UDID, FakeXcrun, MemoryStateStore, fixture_udid, made
from simtrail.testing.rig import DeviceRig, scope

SHUTDOWN_UDID = fixture_udid("iPhone 17 Pro Max")
TP1, TP2 = scope("tp-1"), scope("tp-2")


def folder(udid: str, *apps: str, root: Path | None = None) -> Path:
    """A simulator's folder on the Mac, holding these apps a person installed."""
    device = (root or devices_dir(os.environ)) / udid
    (device / "data" / "Library").mkdir(parents=True, exist_ok=True)
    (device / "device.plist").write_bytes(b"x" * 1000)
    for index, app in enumerate(apps):
        bundle = device / "data" / "Containers" / "Bundle" / "Application" / f"B{index}" / f"{app}.app"
        bundle.mkdir(parents=True)
        (bundle / "Info.plist").write_bytes(b"y" * 500)
    return device


def deleted(rig: DeviceRig) -> list[str]:
    return [args[2] for args in rig.argv() if args[:2] == ("simctl", "delete")]


def idle_rig(tmp_path: Path, **settings: object) -> DeviceRig:
    rig = DeviceRig(tmp_path)
    rig.config.set(idle_minutes=5, **settings)
    return rig


async def reaped(rig: DeviceRig) -> list[str]:
    rig.clock.now += 5 * 60
    return await rig.manager.reap()


# -- the reaper --------------------------------------------------------------------------------------------------------


async def test_an_empty_simulator_simtrail_made_is_deleted_once_idle_and_forgotten_so_the_next_call_makes_another(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = idle_rig(tmp_path)
    instance = await rig.up()
    folder(instance.udid)
    caplog.set_level(logging.INFO)
    assert await reaped(rig) == [instance.udid]
    assert ("simctl", "shutdown", instance.udid) in rig.argv() and deleted(rig) == [instance.udid]
    assert rig.memory.all_created() == set() and rig.memory.assigned(TP1, False) is None
    assert "deleted the simulator Simtrail · alpha · tp-1 Simtrail made, idle (device.delete_created = empty)" in (
        caplog.text
    )
    again = await rig.up()
    assert again.udid == made(2) and again.created


async def test_one_holding_an_app_is_kept_while_empty_ones_only_go_and_deleted_when_idle_ones_go(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = idle_rig(tmp_path)
    instance = await rig.up()
    folder(instance.udid, "Demo", "Notes")
    caplog.set_level(logging.INFO)
    await reaped(rig)
    assert deleted(rig) == [] and rig.memory.all_created() == {instance.udid}
    assert "kept the simulator Simtrail · alpha · tp-1 Simtrail made: it holds Demo.app, Notes.app" in caplog.text
    rig.config.set(delete_created="idle")
    assert (await rig.up()).udid == instance.udid
    await reaped(rig)
    assert deleted(rig) == [instance.udid] and rig.memory.all_created() == set()


async def test_one_whose_folder_is_not_found_is_kept_as_its_apps_cannot_be_told(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = idle_rig(tmp_path)
    instance = await rig.up()
    caplog.set_level(logging.INFO)
    await reaped(rig)
    assert deleted(rig) == [] and rig.memory.all_created() == {instance.udid}
    assert "its folder was not found" in caplog.text


async def test_a_simulator_a_person_picked_is_never_deleted_even_when_idle_ones_go(tmp_path: Path) -> None:
    rig = idle_rig(tmp_path, delete_created="idle")
    rig.memory.choose(TP1, False, SHUTDOWN_UDID)
    instance = await rig.up()
    folder(instance.udid)
    assert instance.booted_by_us and not instance.created
    assert await reaped(rig) == [SHUTDOWN_UDID]
    assert ("simctl", "shutdown", SHUTDOWN_UDID) in rig.argv() and deleted(rig) == []
    assert rig.memory.assigned(TP1, False) == SHUTDOWN_UDID


@pytest.mark.parametrize("settings", [{"delete_created": "never"}, {"shutdown_on_idle": False}])
async def test_nothing_is_deleted_when_the_settings_keep_it_or_leave_idle_devices_running(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    rig = idle_rig(tmp_path, **settings)
    instance = await rig.up()
    folder(instance.udid)
    assert await reaped(rig) == [instance.udid]
    assert deleted(rig) == [] and rig.memory.all_created() == {instance.udid}


async def test_one_another_scope_still_remembers_as_its_own_is_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = idle_rig(tmp_path)
    instance = await rig.up()
    folder(instance.udid)
    rig.memory.choose(TP2, False, instance.udid)
    caplog.set_level(logging.INFO)
    await reaped(rig)
    assert deleted(rig) == [] and rig.memory.holders(instance.udid) == {"tp-1", "tp-2"}
    assert "kept the simulator Simtrail · alpha · tp-1 Simtrail made: tp-2 still use it" in caplog.text


async def test_a_group_shares_one_it_remembers_as_the_groups_and_that_is_deleted_too(tmp_path: Path) -> None:
    rig = idle_rig(tmp_path, device_mode="shared")
    instance = await rig.up("tp-1")
    await rig.up("tp-2")
    folder(instance.udid)
    assert rig.memory.holders(instance.udid) == {"group:alpha"}
    await reaped(rig)
    assert deleted(rig) == [instance.udid] and rig.memory.holders(instance.udid) == set()


async def test_a_deletion_that_fails_is_logged_the_reaper_goes_on_and_the_memory_is_kept(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = idle_rig(tmp_path)
    rig.xcrun.on("simctl", "delete", rc=1, err="Unable to delete a device in the current state: Booted")
    instance = await rig.up()
    folder(instance.udid)
    assert await reaped(rig) == [instance.udid]
    assert deleted(rig) == [instance.udid]
    assert rig.memory.all_created() == {instance.udid} and rig.memory.assigned(TP1, False) == instance.udid
    assert f"could not delete the simulator {instance.udid} Simtrail made" in caplog.text
    assert "Unable to delete" in caplog.text


class HostMemory:
    """A host's own `DeviceMemory`, which cannot list nor forget what Simtrail made."""

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


async def test_under_a_hosts_memory_that_cannot_forget_nothing_is_deleted_and_pruning_is_refused(
    tmp_path: Path,
) -> None:
    rig = idle_rig(tmp_path, delete_created="idle")
    host: DeviceMemory = HostMemory(rig.memory)
    assert not isinstance(host, CreatedDevices) and isinstance(rig.memory, CreatedDevices)
    rig.manager.directory.memory = host
    instance = await rig.up()
    folder(instance.udid)
    await reaped(rig)
    assert deleted(rig) == [] and rig.memory.all_created() == {instance.udid}
    with pytest.raises(SimulatorUnavailable, match="cannot list the simulators Simtrail made"):
        await rig.manager.prune(everything=False, dry_run=True)


# -- pruning -----------------------------------------------------------------------------------------------------------


async def test_the_daemon_prunes_what_it_does_not_run_and_keeps_what_it_runs(tmp_path: Path) -> None:
    rig = DeviceRig(tmp_path)
    running = await rig.up("tp-1")
    rig.memory.remember_created(TP2, False, SHUTDOWN_UDID)
    folder(SHUTDOWN_UDID)
    found = await rig.manager.prune(everything=False, dry_run=False)
    assert [(entry.udid, entry.deleted, entry.kept) for entry in found] == sorted(
        [(running.udid, False, RUNNING), (SHUTDOWN_UDID, True, None)]
    )
    assert deleted(rig) == [SHUTDOWN_UDID] and rig.memory.all_created() == {running.udid}


def lister(devices: dict[str, list[dict[str, object]]]) -> FakeXcrun:
    return FakeXcrun().on("simctl", "list", "devices", "-j", out=json.dumps({"devices": devices}))


UDIDS = [f"{n:08d}-0000-4000-8000-000000000000" for n in range(1, 7)]


def entry(udid: str, name: str, state: str = "Shutdown") -> dict[str, object]:
    return {"udid": udid, "name": name, "state": state, "isAvailable": True, "deviceTypeIdentifier": "t.phone"}


async def test_prune_deletes_empty_ones_keeps_the_rest_saying_why_and_all_takes_those_with_apps_too(
    tmp_path: Path,
) -> None:
    root = tmp_path / "devices"
    env = {"SIMTRAIL_SIMULATOR_DEVICES_DIR": str(root)}
    memory = JsonDeviceMemory(MemoryStateStore(tmp_path).devices_file())
    empty, apps, booted, elsewhere, _gone, failing = UDIDS
    for index, udid in enumerate(UDIDS):
        memory.remember_created(Scope.named(f"s{index}"), False, udid)
    memory.choose(Scope.named("person"), False, BOOTED_UDID)
    folder(empty, root=root)
    folder(apps, "Demo", root=root)
    folder(booted, root=root)
    folder(failing, root=root)
    xcrun = lister(
        {
            "iOS 26.5": [
                entry(empty, "Simtrail · a"),
                entry(apps, "Simtrail · b"),
                entry(booted, "Simtrail · c", "Booted"),
                entry(elsewhere, "Simtrail · d"),
                entry(failing, "Simtrail · f"),
                entry(BOOTED_UDID, "iPhone 17 Pro", "Booted"),
            ]
        }
    ).on("simctl", "delete", failing, rc=1, err="it would not go")
    simctl = Simctl(xcrun)

    dry = await prune(simctl, memory, running=(), everything=False, dry_run=True, env=env)
    assert not any(args[1] == "delete" for args in xcrun.argv()) and memory.all_created() == set(UDIDS)
    size = 1000
    assert dry == [
        Pruned(empty, "Simtrail · a", (), size, False),
        Pruned(apps, "Simtrail · b", ("Demo.app",), size + 500, False, holding(1)),
        Pruned(booted, "Simtrail · c", (), 0, False, "it is not shut down (Booted)"),
        Pruned(elsewhere, "Simtrail · d", (), 0, False, NO_FOLDER),
        Pruned(failing, "Simtrail · f", (), size, False),
    ]

    done = await prune(simctl, memory, running=(), everything=False, dry_run=False, env=env)
    assert [(found.udid, found.deleted, found.error) for found in done if found.kept is None] == [
        (empty, True, None),
        (failing, False, "simctl delete: it would not go"),
    ]
    assert memory.all_created() == {apps, booted, elsewhere, failing}, "the gone one is forgotten, unsaid"
    assert memory.holders(BOOTED_UDID) == {"person"}

    everything = await prune(simctl, memory, running=(), everything=True, dry_run=False, env=env)
    assert [found.udid for found in everything if found.deleted] == [apps]
    assert everything[0].as_json() == {
        "udid": apps,
        "name": "Simtrail · b",
        "apps": ["Demo.app"],
        "size": size + 500,
        "deleted": True,
        "kept": None,
        "error": None,
    }
    assert holding(2) == "it holds 2 apps (--all deletes it too)"


# -- the memory --------------------------------------------------------------------------------------------------------


def test_the_memory_says_who_remembers_a_device_and_forgets_one_deleted_everywhere(tmp_path: Path) -> None:
    file = MemoryStateStore(tmp_path).devices_file()
    memory = JsonDeviceMemory(file)
    memory.remember_created(TP1, False, made(1))
    memory.remember_created(TP1, True, made(2))
    memory.choose(TP2, False, made(1))
    assert memory.all_created() == {made(1), made(2)}
    assert memory.holders(made(1)) == {"tp-1", "tp-2"} and memory.holders(made(2)) == {"group:alpha"}
    memory.forget_created(made(1))
    assert memory.all_created() == {made(2)} and memory.holders(made(1)) == set()
    assert memory.assigned(TP1, False) is None and memory.assigned(TP1, True) == made(2)
    file.write_text(file.read_text() + "\n")
    written = file.read_text()
    memory.forget_created(BOOTED_UDID)
    assert file.read_text() == written, "nothing to forget writes nothing"


async def test_a_listing_that_fails_is_raised_to_the_asker(tmp_path: Path) -> None:
    memory = JsonDeviceMemory(MemoryStateStore(tmp_path).devices_file())
    failing = Simctl(FakeXcrun().on("simctl", "list", rc=1, err="CoreSimulator is broken"))
    with pytest.raises(SimctlError, match="CoreSimulator is broken"):
        await prune(failing, memory, running=(), everything=False, dry_run=False, env={})
