# SPDX-License-Identifier: Apache-2.0
"""Which simulator a scope uses, and remembering it.

``device.mode`` decides what is remembered: ``per_scope`` gives every scope a device of its own, so two scopes never tap
on each other's apps; ``shared`` gives a whole group one. The answer is kept by UDID in a host's `DeviceMemory` -- for a
standalone install, `JsonDeviceMemory`, a private file in PhoneSimulator's state folder -- so a scope finds its device
again after a restart, and a device a person picks stays picked.

A remembered device that no longer exists -- deleted in Xcode, its runtime removed -- is replaced the next time the
scope asks. A device PhoneSimulator made is listed as made. Only such a device is ever deleted: by the reaper once it
has ended it as idle, as ``device.delete_created`` allows, or by ``phonesimulator devices prune``. Either needs a memory
that can list and forget what PhoneSimulator made (`CreatedDevices`), as `JsonDeviceMemory` can; a host's own memory
without that keeps every device.

A new device is copied from a **template** while ``device.templates`` is on (`DeviceDirectory.resolve`): a simulator
PhoneSimulator made for one runtime and device type, booted once and shut down, so that a copy (``simctl clone``) skips
the first boot's setup and is ready in about half the time. A runtime and type with no template yet gets a blank device
as before, and its template is prepared in the background meanwhile -- never booted past ``device.max_booted``, and
never failing anything when it cannot be: it is tried again later. A template is never any scope's device, never
offered in a picker, and never deleted by the idle clean-up or ``phonesimulator devices prune``; one that went away --
deleted in Xcode, its runtime removed -- is forgotten and made again. Templates need a memory that can remember them
(`DeviceTemplates`), as `JsonDeviceMemory` can; a host's own memory without that creates every device blank.

A template is made only when a device of its runtime and type is asked for, and deleted once no device has been
copied from it for ``device.template_days`` (`DeviceDirectory.expire_templates`, which the reaper calls): one for a
runtime or a device type nobody uses any more does not stay on disk. The device types ``device.template_keep`` names
are the exception, on the newest iOS installed: their templates are made ahead of any demand, made again when they went
away, and never deleted (`DeviceDirectory.keep_templates`). That needs a memory that dates each template's
last use (`ExpiringTemplates`), as `JsonDeviceMemory` does; a template it has no date for is dated when first seen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from phonesimulator.config.model import SimConfig
from phonesimulator.host_copy import HostCopy
from phonesimulator.platform.errors import DeviceControlError
from phonesimulator.platform.simctl import Device, DeviceType, Runtime, Simctl, runtime_label
from phonesimulator.protocol import Connection, DeviceKind
from phonesimulator.scope import Scope
from phonesimulator.seams import DeviceMemory
from phonesimulator.storage.private import ensure_private_dir

logger = logging.getLogger(__name__)

#: How the device a group shares is remembered beside the ones scopes have of their own.
SHARED_PREFIX = "group:"
#: The one state in which a template can be copied.
SHUTDOWN = "Shutdown"
#: How long a template's first boot may take: it migrates data and can take minutes.
TEMPLATE_BOOT_TIMEOUT_S = 240.0


class NoDevice(Exception):
    """No device can be had for a scope, with why -- a status 409 carries to a viewer."""

    status = 409


@dataclass(frozen=True)
class DeviceRef:
    udid: str
    name: str
    runtime: str
    #: Whether PhoneSimulator made it (and so may delete it once nobody needs it).
    created: bool
    kind: DeviceKind = "simulator"
    #: How a real device reaches this Mac; None for a simulator.
    connection: Connection | None = None


def pick_runtime(runtimes: list[Runtime], wanted: str) -> Runtime | None:
    """The iOS runtime to use: the one named (by name or version), else the newest installed."""
    ios = [runtime for runtime in runtimes if runtime.available and runtime.platform == "iOS"]
    if wanted:
        ios = [runtime for runtime in ios if wanted in (runtime.name, runtime.version)]
    return max(ios, key=lambda runtime: runtime.version_key, default=None)


def pick_device_type(runtime: Runtime, wanted: str) -> DeviceType | None:
    """The device type to make: the one named, else the newest iPhone the runtime runs.

    simctl lists a runtime's device types newest first, so the first iPhone is the newest one.
    """
    if wanted:
        return next((kind for kind in runtime.device_types if kind.name == wanted), None)
    phones = [kind for kind in runtime.device_types if kind.product_family == "iPhone"]
    return next(iter(phones or runtime.device_types), None)


def kept_types(runtime: Runtime, names: str) -> list[DeviceType]:
    """The device types ``device.template_keep`` names -- separated by commas, as Xcode lists them -- that the runtime
    runs; a name it does not run is passed over."""
    wanted = [name.strip() for name in names.split(",") if name.strip()]
    return [kind for name in wanted if (kind := pick_device_type(runtime, name)) is not None]


def memory_keys(scope: Scope) -> frozenset[str]:
    """What a scope's device is remembered under in `JsonDeviceMemory`: its own id, or its group's, when shared."""
    return frozenset({scope.id, f"{SHARED_PREFIX}{scope.group}"})


@runtime_checkable
class CreatedDevices(Protocol):
    """A `DeviceMemory` that can also say who remembers a device PhoneSimulator made, and forget one deleted. Optional:
    a memory without it never has a device deleted."""

    def all_created(self) -> set[str]:
        """The UDIDs of every device PhoneSimulator made, whichever scope it was made for."""
        ...

    def holders(self, udid: str) -> set[str]:
        """What remembers this device as its own: scopes' ids, and groups' as ``group:<group>``."""
        ...

    def forget_created(self, udid: str) -> None:
        """Forget a device that was deleted: no longer made by PhoneSimulator, nor anybody's."""
        ...


@dataclass(frozen=True)
class Template:
    """A simulator PhoneSimulator made to copy new devices from, for one runtime and device type."""

    udid: str
    #: Whether it has been booted once and shut down, and so may be copied.
    ready: bool


@runtime_checkable
class DeviceTemplates(Protocol):
    """A `DeviceMemory` that can also remember the templates new simulators are copied from. Optional: under a memory
    without it, every new simulator is created blank."""

    def template(self, runtime_id: str, device_type_id: str) -> Template | None:
        """The template for this runtime and device type, ready or not."""
        ...

    def remember_template(self, runtime_id: str, device_type_id: str, udid: str, *, ready: bool) -> None:
        """Remember the template for this runtime and device type, in place of any other."""
        ...

    def forget_template(self, udid: str) -> None:
        """Forget a template that went away."""
        ...

    def all_templates(self) -> set[str]:
        """The UDIDs of every template, whatever its runtime and type."""
        ...


@runtime_checkable
class ExpiringTemplates(Protocol):
    """A `DeviceTemplates` that also dates each template's last use, so one left unused is deleted. Optional: under a
    memory without it, templates are kept."""

    def template_used(self, udid: str, at: float) -> None:
        """Date a template's last use -- a device copied from it, or its making -- as a wall-clock time."""
        ...

    def templates_used(self) -> dict[str, float | None]:
        """Each template's UDID, and when it was last used -- None when it was never dated."""
        ...


def template_name(prefix: str, kind: DeviceType, runtime: Runtime) -> str:
    """What a template is called in Xcode's list, so a person can tell it from a scope's device."""
    return f"{prefix} · template · {kind.name} · {runtime.name}"


def device_name(prefix: str, scope: Scope, shared: bool) -> str:
    """What a device PhoneSimulator makes is called in Xcode's list: the prefix, then the group it is shared by or the
    scope it is for."""
    return f"{prefix} · {scope.group if shared else scope.label}"


class JsonDeviceMemory:
    """The `DeviceMemory` PhoneSimulator ships: one private JSON file, holding every scope's device.

    It owns the file it reads, rather than asking a `StateStore` for it. A host that keeps this somewhere of its own
    -- a database row, a record per workspace -- passes its own `DeviceMemory` instead and needs none of this: that
    is why the path is here and not on the store every host must implement.
    """

    def __init__(self, file: Path, *, ensure: Callable[[Path], Path] = ensure_private_dir) -> None:
        self._file = file
        self._ensure = ensure

    @staticmethod
    def _key(scope: Scope, shared: bool) -> str:
        return f"{SHARED_PREFIX}{scope.group}" if shared else scope.id

    def _read_all(self) -> dict[str, Any]:
        try:
            data = json.loads(self._file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        scopes = data.get("scopes") if isinstance(data, dict) else None
        created = data.get("created") if isinstance(data, dict) else None
        templates = data.get("templates") if isinstance(data, dict) else None
        return {
            "scopes": {str(k): str(v) for k, v in scopes.items()} if isinstance(scopes, dict) else {},
            "created": sorted({str(u) for u in created}) if isinstance(created, list) else [],
            "templates": {
                str(key): {
                    "udid": str(entry["udid"]),
                    "ready": entry.get("ready") is True,
                    **({"used": float(entry["used"])} if isinstance(entry.get("used"), (int, float)) else {}),
                }
                for key, entry in templates.items()
                if isinstance(entry, dict) and "udid" in entry
            }
            if isinstance(templates, dict)
            else {},
        }

    @staticmethod
    def _template_key(runtime_id: str, device_type_id: str) -> str:
        return f"{runtime_id}|{device_type_id}"

    def _write_all(self, data: dict[str, Any]) -> None:
        folder = self._ensure(self._file.parent)
        temporary = folder / f".{self._file.name}.{os.getpid()}.tmp"
        # No templates is no key, so a file stays as it was before there were any.
        kept = {key: value for key, value in data.items() if key != "templates" or value}
        temporary.write_text(json.dumps(kept, indent=1, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self._file)

    def assigned(self, scope: Scope, shared: bool) -> str | None:
        found: str | None = self._read_all()["scopes"].get(self._key(scope, shared))
        return found

    def created(self, scope: Scope) -> set[str]:
        return set(self._read_all()["created"])

    def choose(self, scope: Scope, shared: bool, udid: str) -> None:
        data = self._read_all()
        data["scopes"][self._key(scope, shared)] = udid
        self._write_all(data)

    def forget(self, scope: Scope, shared: bool) -> str | None:
        data = self._read_all()
        udid: str | None = data["scopes"].pop(self._key(scope, shared), None)
        if udid is not None:
            self._write_all(data)
        return udid

    def remember_created(self, scope: Scope, shared: bool, udid: str) -> None:
        data = self._read_all()
        data["scopes"][self._key(scope, shared)] = udid
        data["created"] = sorted({*data["created"], udid})
        self._write_all(data)

    def all_created(self) -> set[str]:
        return set(self._read_all()["created"])

    def holders(self, udid: str) -> set[str]:
        return {key for key, held in self._read_all()["scopes"].items() if held == udid}

    def forget_created(self, udid: str) -> None:
        data = self._read_all()
        scopes = {key: held for key, held in data["scopes"].items() if held != udid}
        created = [made for made in data["created"] if made != udid]
        if scopes != data["scopes"] or created != data["created"]:
            self._write_all({**data, "scopes": scopes, "created": created})

    def template(self, runtime_id: str, device_type_id: str) -> Template | None:
        entry = self._read_all()["templates"].get(self._template_key(runtime_id, device_type_id))
        return None if entry is None else Template(entry["udid"], entry["ready"])

    def remember_template(self, runtime_id: str, device_type_id: str, udid: str, *, ready: bool) -> None:
        data = self._read_all()
        key = self._template_key(runtime_id, device_type_id)
        before = data["templates"].get(key, {})
        used = {"used": before["used"]} if before.get("udid") == udid and "used" in before else {}
        data["templates"][key] = {"udid": udid, "ready": ready, **used}
        self._write_all(data)

    def template_used(self, udid: str, at: float) -> None:
        data = self._read_all()
        for entry in data["templates"].values():
            if entry["udid"] == udid:
                entry["used"] = at
        self._write_all(data)

    def templates_used(self) -> dict[str, float | None]:
        return {entry["udid"]: entry.get("used") for entry in self._read_all()["templates"].values()}

    def forget_template(self, udid: str) -> None:
        data = self._read_all()
        templates = {key: entry for key, entry in data["templates"].items() if entry["udid"] != udid}
        if templates != data["templates"]:
            self._write_all({**data, "templates": templates})

    def all_templates(self) -> set[str]:
        return {entry["udid"] for entry in self._read_all()["templates"].values()}


#: A template's runtime and device type, by their identifiers.
TemplateKey = tuple[str, str]


class DeviceDirectory:
    """Every scope's device, and the templates new ones are copied from."""

    def __init__(
        self, memory: DeviceMemory, copy: HostCopy | None = None, *, wall: Callable[[], float] = time.time
    ) -> None:
        self.memory = memory
        self._copy = copy or HostCopy()
        #: The wall clock a template's last use is dated by: it outlives the daemon, unlike a monotonic one.
        self._wall = wall
        #: The simulators the host runs now, by UDID: a template is booted only while they leave room under
        #: ``device.max_booted``. `DeviceManager` points it at its own; nothing runs, by default.
        self.running: Callable[[], set[str]] = set
        #: The templates being prepared, by runtime and device type: one at a time for each.
        self._preparing: dict[TemplateKey, asyncio.Task[None]] = {}
        #: The templates being booted now, which count against ``device.max_booted`` too.
        self._booting: set[str] = set()
        #: The templates that could not be booted for want of room, with what preparing them again needs.
        self._waiting: dict[TemplateKey, tuple[Simctl, Runtime, DeviceType, SimConfig]] = {}

    def templates(self) -> set[str]:
        """The UDIDs of every template -- none, under a memory that cannot remember them."""
        return self.memory.all_templates() if isinstance(self.memory, DeviceTemplates) else set()

    async def resolve(self, simctl: Simctl, scope: Scope, config: SimConfig) -> DeviceRef:
        """The scope's device: the remembered one while it exists, else a new one, remembered."""
        shared = config.device_mode == "shared"
        remembered = self.memory.assigned(scope, shared)
        if remembered:
            device = next((d for d in await simctl.devices() if d.udid == remembered and d.available), None)
            if device is not None:
                created = device.udid in self.memory.created(scope)
                name = device.name
                # Only by a name a person reads -- a scope known by its id alone would undo another's name -- and
                # only a device this scope alone holds: two scopes sharing one would rename it back and forth.
                if created and scope.label != scope.id and self._held_alone(device.udid, scope):
                    name = await self._renamed(simctl, device, device_name(config.device_name_prefix, scope, shared))
                return DeviceRef(device.udid, name, runtime_label(device.runtime_id), created=created)
        runtime = pick_runtime(await simctl.runtimes(), config.runtime)
        if runtime is None:
            raise NoDevice(self._copy.no_runtime(config.runtime))
        kind = pick_device_type(runtime, config.device_type)
        if kind is None:
            raise NoDevice(
                f"{runtime.name} has no device type named {config.device_type!r}."
                if config.device_type
                else f"{runtime.name} runs no iPhone or iPad."
            )
        name = device_name(config.device_name_prefix, scope, shared)
        udid = await self._new_device(simctl, name, runtime, kind, config)
        self.memory.remember_created(scope, shared, udid)
        return DeviceRef(udid, name, runtime.name, created=True)

    def _held_alone(self, udid: str, scope: Scope) -> bool:
        """Whether no scope but this one remembers the device -- unknown, and so not, under a memory that cannot say."""
        return isinstance(self.memory, CreatedDevices) and self.memory.holders(udid) <= memory_keys(scope)

    async def _renamed(self, simctl: Simctl, device: Device, wanted: str) -> str:
        """The name of a device PhoneSimulator made, given the one it would make it with now when it has another -- as a
        project's name read from its folder replaces the id it was once called by. A rename simctl refuses leaves the
        old one; a device a person made is never asked about."""
        if device.name == wanted:
            return device.name
        try:
            await simctl.rename(device.udid, wanted)
        except DeviceControlError as exc:
            logger.warning("could not rename the simulator %s to %s: %s", device.name, wanted, exc)
            return device.name
        logger.info("renamed the simulator %s to %s", device.name, wanted)
        return wanted

    async def _new_device(
        self, simctl: Simctl, name: str, runtime: Runtime, kind: DeviceType, config: SimConfig
    ) -> str:
        """A new device: copied from its runtime and type's template when one is ready, else created blank -- and the
        template prepared in the background when there is none yet."""
        templates = self.memory if isinstance(self.memory, DeviceTemplates) and config.device_templates else None
        if templates is None:
            return await simctl.create(name, kind.identifier, runtime.identifier)
        key = (runtime.identifier, kind.identifier)
        template = templates.template(*key)
        source = await self._listed(simctl, templates, template) if template is not None else None
        if template is not None and template.ready and source is not None and key not in self._preparing:
            if source.state == SHUTDOWN:
                try:
                    copied = await simctl.clone(template.udid, name)
                    self._used(template.udid)
                    return copied
                except DeviceControlError as exc:
                    logger.warning("could not copy the template %s; creating a blank simulator: %s", source.name, exc)
                    return await simctl.create(name, kind.identifier, runtime.identifier)
            logger.info("the template %s is not shut down (%s); creating a blank simulator", source.name, source.state)
            return await simctl.create(name, kind.identifier, runtime.identifier)
        udid = await simctl.create(name, kind.identifier, runtime.identifier)
        self._prepare(simctl, runtime, kind, config, fresh=udid)
        return udid

    @staticmethod
    async def _listed(simctl: Simctl, templates: DeviceTemplates, template: Template) -> Device | None:
        """The template as simctl lists it -- or None, and forgotten, when it went away or cannot be used: deleted
        outside PhoneSimulator, its runtime removed."""
        device = next((d for d in await simctl.devices() if d.udid == template.udid), None)
        if device is not None and device.available:
            return device
        logger.info("forgot the simulator template %s: %s", template.udid,
                    "it is no longer listed" if device is None else "it is not available")  # fmt: skip
        templates.forget_template(template.udid)
        return None

    def _prepare(
        self, simctl: Simctl, runtime: Runtime, kind: DeviceType, config: SimConfig, *, fresh: str | None = None
    ) -> None:
        """Prepare the template for a runtime and device type in the background, unless one is being prepared."""
        key = (runtime.identifier, kind.identifier)
        if key in self._preparing:
            return
        self._waiting.pop(key, None)
        self._preparing[key] = asyncio.get_running_loop().create_task(
            self._prepared(simctl, runtime, kind, config, fresh)
        )

    def retry_templates(self) -> None:
        """Prepare again the templates that were left unbooted for want of room. The reaper asks, once a minute."""
        for simctl, runtime, kind, config in list(self._waiting.values()):
            self._prepare(simctl, runtime, kind, config)

    async def _prepared(
        self, simctl: Simctl, runtime: Runtime, kind: DeviceType, config: SimConfig, fresh: str | None
    ) -> None:
        key = (runtime.identifier, kind.identifier)
        try:
            await self._make_template(simctl, runtime, kind, config, fresh)
        except Exception as exc:  # A template is only a speed-up: nothing may fail for want of one.
            logger.warning("could not prepare the simulator template for %s on %s: %s", kind.name, runtime.name, exc)
        finally:
            self._preparing.pop(key, None)

    async def _make_template(
        self, simctl: Simctl, runtime: Runtime, kind: DeviceType, config: SimConfig, fresh: str | None
    ) -> None:
        """Create the template, or take the one left unbooted, boot it once, wait for it and shut it down."""
        templates = self.memory
        assert isinstance(templates, DeviceTemplates)
        found = templates.template(runtime.identifier, kind.identifier)
        listed = await self._listed(simctl, templates, found) if found is not None else None
        if found is None or listed is None:
            name = template_name(config.device_name_prefix, kind, runtime)
            udid = await simctl.create(name, kind.identifier, runtime.identifier)
            templates.remember_template(runtime.identifier, kind.identifier, udid, ready=False)
            self._used(udid)
        elif found.ready:
            return
        else:
            udid = found.udid
        busy = self.running() | self._booting | ({fresh} if fresh else set())
        if len(busy) + 1 > config.max_booted:
            logger.info(
                "left the simulator template for %s on %s unbooted: %d simulators run (device.max_booted = %d); it is "
                "tried again later",
                kind.name,
                runtime.name,
                len(busy),
                config.max_booted,
            )
            self._waiting[(runtime.identifier, kind.identifier)] = (simctl, runtime, kind, config)
            return
        self._booting.add(udid)
        try:
            await simctl.boot(udid)
            await simctl.bootstatus(udid, timeout=TEMPLATE_BOOT_TIMEOUT_S)
        finally:
            try:
                await simctl.shutdown(udid)
            finally:
                self._booting.discard(udid)
        templates.remember_template(runtime.identifier, kind.identifier, udid, ready=True)
        logger.info("prepared the simulator template for %s on %s", kind.name, runtime.name)

    def _used(self, udid: str) -> None:
        if isinstance(self.memory, ExpiringTemplates):
            self.memory.template_used(udid, self._wall())

    async def _kept(self, simctl: Simctl, config: SimConfig) -> tuple[Runtime, list[DeviceType]] | None:
        """The newest iOS installed and the device types ``device.template_keep`` names that it runs -- None when
        there is no iOS, or templates are off or cannot be remembered."""
        if not config.device_templates or not isinstance(self.memory, DeviceTemplates):
            return None
        runtime = pick_runtime(await simctl.runtimes(), "")
        return None if runtime is None else (runtime, kept_types(runtime, config.template_keep))

    async def keep_templates(self, simctl: Simctl, config: SimConfig) -> None:
        """Prepare, in the background, the template of each device type ``device.template_keep`` names on the newest
        iOS, when it has none ready -- within ``device.max_booted``, tried again by the reaper as for any other."""
        kept = await self._kept(simctl, config)
        if kept is None:
            return
        runtime, kinds = kept
        assert isinstance(self.memory, DeviceTemplates)
        for kind in kinds:
            template = self.memory.template(runtime.identifier, kind.identifier)
            listed = await self._listed(simctl, self.memory, template) if template is not None else None
            if template is None or listed is None or not template.ready:
                self._prepare(simctl, runtime, kind, config)

    async def expire_templates(self, simctl: Simctl, config: SimConfig) -> list[str]:
        """Delete each template no device has been copied from for ``device.template_days`` -- none while it is 0 --
        and forget it; one never dated is dated now, so its days start counting. A template ``device.template_keep``
        names on the newest iOS is never deleted, nor one being booted, nor one simctl cannot delete, tried again later.
        Answers the UDIDs deleted."""
        memory = self.memory
        if config.template_days <= 0 or not isinstance(memory, ExpiringTemplates):
            return []
        kept = await self._kept(simctl, config)
        keep: set[str] = set()
        if kept is not None:
            runtime, kinds = kept
            assert isinstance(memory, DeviceTemplates)
            for kind in kinds:
                template = memory.template(runtime.identifier, kind.identifier)
                if template is not None:
                    keep.add(template.udid)
        now = self._wall()
        deleted: list[str] = []
        for udid, used in memory.templates_used().items():
            if used is None:
                memory.template_used(udid, now)
                continue
            if udid in keep or udid in self._booting or now - used < config.template_days * 86400:
                continue
            try:
                await simctl.delete(udid)
            except DeviceControlError as exc:
                logger.warning("could not delete the simulator template %s, unused for %d days: %s", udid,
                               int((now - used) // 86400), exc)  # fmt: skip
                continue
            assert isinstance(memory, DeviceTemplates)
            memory.forget_template(udid)
            deleted.append(udid)
            logger.info("deleted the simulator template %s: no device was copied from it for %d days "
                        "(device.template_days)", udid, int((now - used) // 86400))  # fmt: skip
        return deleted

    async def settle(self) -> None:
        """Wait for every template being prepared."""
        while self._preparing:
            await asyncio.gather(*self._preparing.values(), return_exceptions=True)

    async def close(self) -> None:
        """Stop preparing templates: one left half-made is taken up again the next time."""
        tasks = list(self._preparing.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
