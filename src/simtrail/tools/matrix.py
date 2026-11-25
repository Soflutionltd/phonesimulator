# SPDX-License-Identifier: Apache-2.0
"""`sim_matrix`: the same screen on several devices, in light and dark, captured in one call and laid out on one sheet.

Each device is a UDID, as `sim_device list` shows it, or a preset found among the devices listed: ``small_iphone`` and
``large_iphone`` -- the simulators whose names say so, an iPhone SE, mini or ``e`` first, a Pro Max or Plus first --
``ipad`` and ``android``, an emulator. A preset prefers a booted device, then the newest runtime, and two never pick
the same one. A device another live agent works on or drives is skipped, saying who, unless the call says ``steal:
true``; the agent's own device stays its own, and the others are used for this call alone (`ready_device`).

On each device the text size is set when asked, then for each appearance: the appearance set through the device's
change ledger (`core.device_changes`), the app launched afresh when a ``bundle_id`` is given, a saved flow played when
one is named (`tools.flow.play`, with ``variables`` and ``confirm`` as `sim_flow run` takes them), and the screen
captured. Then the device gets back the appearance and text size it had -- read before the first change -- and the
answer says what could not be read, and so was left as the matrix set it.

Every screenshot is saved as a JPEG in one folder -- ``save_to``, inside a folder `sim_screenshot` may save to, else a
new ``matrix-<time>`` folder in the recording folder -- with a contact sheet beside them, ``contact-sheet.jpg``: a row
per device, a column per appearance, each captioned (`core.contact_sheet`). The answer is a line per screenshot, a line
per device skipped and why, and where the sheet is; ``return_image: true`` sends the sheet too.
"""

from __future__ import annotations

import asyncio
import base64
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simtrail.connectors.base import Capability, ConnectorError
from simtrail.core.actions import SCREENSHOT_WIDTH, ActionError
from simtrail.core.contact_sheet import Cell, contact_sheet
from simtrail.core.control import DisplayState
from simtrail.core.device_changes import Changes
from simtrail.core.flows import Flow, FlowRefused
from simtrail.core.instance import DeviceInstance
from simtrail.core.manager import SimulatorUnavailable
from simtrail.core.recordings import default_folder
from simtrail.core.refusals import ObserveGuard
from simtrail.platform.errors import DeviceControlError
from simtrail.platform.simctl import CONTENT_SIZES
from simtrail.protocol import DeviceChoice
from simtrail.storage.private import ensure_private_dir, write_atomic
from simtrail.tools.app import bundle_of
from simtrail.tools.context import ToolContext, flag_arg, make_tool, ready_device, require, whole_arg
from simtrail.tools.flow import guard_of, play, variable_values
from simtrail.tools.results import Result, ToolRefused
from simtrail.tools.schemas import MATRIX_DEVICES_MAX, MATRIX_PRESETS, SAVE_TO_MAX
from simtrail.tools.screenshot import places

APPEARANCES = ("light", "dark")
SHEET = "contact-sheet.jpg"
_SLUG = re.compile(r"[^a-z0-9]+")
#: Words in an iPhone's name, from the smallest kind to the largest.
_SMALL = re.compile(r"\b(SE|mini)\b|\d+e\b")
_LARGE = ("Max", "Plus", "Air", "Pro")


@dataclass
class Device:
    """A device the matrix captures: as listed, and what was asked for it."""

    asked: str
    choice: DeviceChoice


@dataclass
class Outcome:
    """What the matrix did: each screenshot, each device skipped and why, and notes for the answer."""

    shots: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    cells: list[Cell] = field(default_factory=list)


def _asked(value: object) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MATRIX_DEVICES_MAX
        or not all(isinstance(item, str) and 0 < len(item) <= 64 for item in value)
    ):
        raise ToolRefused(
            f"devices is a list of 1 to {MATRIX_DEVICES_MAX} UDIDs from sim_device list, or presets: "
            f"{', '.join(MATRIX_PRESETS)}"
        )
    return list(dict.fromkeys(value))


def _appearances(value: object) -> list[str]:
    if value is None:
        return list(APPEARANCES)
    if not isinstance(value, list) or not value or not all(item in APPEARANCES for item in value):
        raise ToolRefused("appearances is a list of light, dark or both")
    return list(dict.fromkeys(value))


def _runtime(choice: DeviceChoice) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", choice["runtime"]))


def _size_rank(name: str) -> int:
    """Where an iPhone's name puts it among the sizes, 0 the smallest."""
    if _SMALL.search(name):
        return 0
    found = [index for index, word in enumerate(_LARGE) if re.search(rf"\b{word}\b", name)]
    return len(_LARGE) + 1 - min(found) if found else 1


def _fits(preset: str, choice: DeviceChoice) -> bool:
    if preset == "android":
        return choice["kind"] == "android" and choice["connection"] is None
    family = "iPad" if preset == "ipad" else "iPhone"
    return choice["kind"] == "simulator" and choice["name"].startswith(family)


def _pick(preset: str, listed: Sequence[DeviceChoice], taken: set[str]) -> DeviceChoice | None:
    """The device a preset names among those listed and not yet taken: by size for an iPhone, then a booted one, the
    newest runtime and the name."""
    found = [choice for choice in listed if choice["usable"] and choice["udid"] not in taken and _fits(preset, choice)]
    if not found:
        return None

    def rank(choice: DeviceChoice) -> tuple[Any, ...]:
        size = _size_rank(choice["name"])
        by_size = -size if preset == "large_iphone" else size if preset == "small_iphone" else 0
        newest = tuple(-part for part in _runtime(choice))
        return (by_size, choice["state"] != "Booted", newest, choice["name"])

    return min(found, key=rank)


def resolve(asked: Sequence[str], listed: Sequence[DeviceChoice]) -> tuple[list[Device], list[dict[str, str]]]:
    """The devices each entry names, in order, and those that name none, with why."""
    found: list[Device] = []
    skipped: list[dict[str, str]] = []
    by_udid = {choice["udid"]: choice for choice in listed}
    # A device named by its UDID is never also what a preset picks.
    named = {item for item in asked if item in by_udid}
    taken: set[str] = set()
    for item in asked:
        if item in MATRIX_PRESETS:
            choice = _pick(item, listed, taken | named)
            if choice is None:
                skipped.append({"device": item, "reason": "no device here fits it that is not already in the matrix"})
                continue
        elif item in by_udid:
            choice = by_udid[item]
            if not choice["usable"]:
                skipped.append({"device": choice["name"], "reason": "it cannot be used now"})
                continue
        else:
            skipped.append({"device": item, "reason": "not a preset, nor a UDID sim_device list shows"})
            continue
        taken.add(choice["udid"])
        found.append(Device(item, choice))
    return found, skipped


def _folder(value: object, ctx: ToolContext) -> Path:
    """Where the screenshots go: `save_to`, inside a folder a screenshot may be saved to, else a new folder in the
    recording folder named for when the matrix ran."""
    if value is None:
        base = default_folder(ctx.config) / f"matrix-{time.strftime('%Y%m%d-%H%M%S')}"
        folder, nth = base, 1
        while folder.exists():
            nth += 1
            folder = base.with_name(f"{base.name}-{nth}")
        return folder
    if not isinstance(value, str) or not value.strip() or len(value) > SAVE_TO_MAX or "\x00" in value:
        raise ToolRefused(f"save_to is a folder name or path of at most {SAVE_TO_MAX} characters")
    allowed = places(ctx)
    asked = Path(value).expanduser()
    real = (asked if asked.is_absolute() else allowed[0] / asked).resolve()
    if not any(real.is_relative_to(place.resolve()) for place in allowed):
        raise ToolRefused(f"save_to must be inside {', '.join(str(place) for place in allowed)}: {value} is not")
    if real.exists() and not real.is_dir():
        raise ToolRefused(f"save_to names a file, {real}: name a folder")
    return real


def _occupied(ctx: ToolContext, udid: str) -> str | None:
    """Who else drives or works on a device, as a reason to skip it; None when nobody does."""
    running = ctx.manager.running(udid)
    holder = ctx.drivers.holder(ctx.caller, running) if ctx.drivers is not None and running is not None else None
    if holder is not None:
        return f"{holder.title} drives it; steal: true takes it over, only when the person asked for it"
    others = ctx.others_on(udid)
    if others:
        return f"{others[0].title} works on it; steal: true takes it over, only when the person asked for it"
    return None


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")[:48] or "device"


@dataclass(frozen=True)
class Plan:
    """What the matrix does on each device."""

    appearances: list[str]
    size: str | None
    bundle: str | None
    flow: Flow | None
    values: dict[str, str]
    guard: ObserveGuard | None
    width: int
    folder: Path


async def run(args: dict[str, Any], ctx: ToolContext) -> Result:
    asked = _asked(args.get("devices"))
    size = args.get("text_size")
    if size is not None and size not in CONTENT_SIZES:
        raise ToolRefused(f"text_size is one of {', '.join(CONTENT_SIZES)}")
    bundle = bundle_of(args["bundle_id"]) if args.get("bundle_id") is not None else None
    flow = _flow(args, ctx)
    plan = Plan(
        appearances=_appearances(args.get("appearances")),
        size=size,
        bundle=bundle,
        flow=flow,
        values=variable_values(args.get("variables"), flow) if flow is not None else {},
        guard=guard_of(args, ctx),
        width=whole_arg(args.get("width"), ctx.config.screenshot_width, SCREENSHOT_WIDTH, "width"),
        folder=_folder(args.get("save_to"), ctx),
    )
    steal = flag_arg(args.get("steal"), "steal")
    return_image = flag_arg(args.get("return_image"), "return_image")
    try:
        listed = await ctx.manager.devices(ctx.scope)
    except SimulatorUnavailable as exc:
        raise ToolRefused(str(exc)) from exc
    devices, skipped = resolve(asked, listed)
    outcome = Outcome(skipped=skipped)
    for number, device in enumerate(devices, start=1):
        occupied = None if steal else _occupied(ctx, device.choice["udid"])
        if occupied is not None:
            outcome.skipped.append({"device": device.choice["name"], "reason": occupied})
            continue
        try:
            await _capture(number, device, plan, ctx, outcome)
        except ToolRefused as exc:
            outcome.skipped.append({"device": device.choice["name"], "reason": str(exc)})
    return await _answer(outcome, plan, return_image)


def _flow(args: dict[str, Any], ctx: ToolContext) -> Flow | None:
    name = args.get("flow")
    if name is None:
        if args.get("variables") is not None:
            raise ToolRefused("variables go with a flow: name the flow to play")
        return None
    if ctx.flows is None:
        raise ToolRefused("flows are not kept here")
    try:
        return ctx.flows.load(ctx.scope, name)
    except FlowRefused as exc:
        raise ToolRefused(str(exc)) from exc


def _needs(plan: Plan) -> list[Capability]:
    needs = [Capability.SCREENSHOT, Capability.APPEARANCE]
    needs += [Capability.ACCESSIBILITY] if plan.size is not None else []
    needs += [Capability.APP_LAUNCH] if plan.bundle is not None else []
    needs += [Capability.INPUT_TOUCH] if plan.flow is not None else []
    return needs


async def _capture(number: int, device: Device, plan: Plan, ctx: ToolContext, outcome: Outcome) -> None:
    """Capture one device in each appearance, then give it back the look it had."""
    instance = await ready_device(ctx, device.choice["udid"])
    if instance.busy:
        raise ToolRefused(f"the device is busy: {instance.busy}")
    require(ctx, instance, _needs(plan), "sim_matrix")
    taken = ctx.drivers.take(ctx.caller, instance, exclusive=False, steal=True) if ctx.drivers is not None else ""
    if taken:
        outcome.notes.append(f"{instance.name}: {taken}")
    try:
        control = ctx.manager.control(instance)
        try:
            before = await control.display(instance.udid)
        except DeviceControlError:
            before = DisplayState()
        changes = ctx.manager.changes(instance)
        try:
            if plan.size is not None:
                await changes.text_size(plan.size)
            for mode in plan.appearances:
                await changes.appearance(mode)
                if plan.bundle is not None:
                    await control.launch(instance.udid, plan.bundle, (), terminate_running=True)
                note = ""
                if plan.flow is not None:
                    played = await play(plan.flow, plan.values, instance, ctx, guard=plan.guard, snapshot="none")
                    if played.failed or played.unmet:
                        last = played.text.splitlines()[-1]
                        note = f"the flow {plan.flow.name} did not finish: {last}"
                if not await ctx.actions.settled(instance, ctx.caller, ctx.config.snapshot_max_elements):
                    note = "; ".join(filter(None, (note, "the screen was still moving when it was captured")))
                await _shoot(number, mode, plan, ctx, outcome, instance, note)
        except (DeviceControlError, ActionError, ConnectorError) as exc:
            raise ToolRefused(f"stopped on it: {exc}") from exc
        finally:
            outcome.notes += await _put_back(instance.name, before, plan, changes)
    finally:
        if ctx.drivers is not None:
            ctx.drivers.done(ctx.caller, instance)


async def _shoot(
    number: int, mode: str, plan: Plan, ctx: ToolContext, outcome: Outcome, instance: DeviceInstance, note: str
) -> None:
    """Take one screenshot and save it, named for its device and appearance."""
    name = instance.name
    shot = (await ctx.actions.screenshots(instance, ctx.caller, width=plan.width))[0]
    sized = f"-{plan.size}" if plan.size is not None else ""
    path = plan.folder / f"{number:02d}-{_slug(name)}-{mode}{sized}.jpg"
    try:
        await asyncio.to_thread(_write, path, shot.jpeg)
    except OSError as exc:
        raise ToolRefused(f"could not save to {path}: {exc.strerror or exc}") from exc
    caption = " · ".join(part for part in (name, mode, plan.size) if part)
    outcome.cells.append(Cell(shot.jpeg, caption))
    outcome.shots.append(
        {
            "device": name,
            "udid": instance.udid,
            "appearance": mode,
            "path": str(path),
            **({"note": note} if note else {}),
        }
    )


def _write(path: Path, data: bytes) -> None:
    ensure_private_dir(path.parent)
    write_atomic(path, data, mode=0o600)


async def _put_back(name: str, before: DisplayState, plan: Plan, changes: Changes) -> list[str]:
    """Give the device back the appearance and text size it had, saying what could not be."""
    notes = []
    restores: list[tuple[str, str | None, str, Callable[[str], Awaitable[object]]]] = [
        ("appearance", before.appearance, plan.appearances[-1], changes.appearance)
    ]
    if plan.size is not None:
        restores.append(("text size", before.text_size, plan.size, changes.text_size))
    for what, was, now, put in restores:
        if was is None:
            notes.append(f"{name}: its {what} could not be read before, so it is left {now}")
        elif was != now:
            try:
                await put(was)
            except DeviceControlError as exc:
                notes.append(f"{name}: its {what} could not be put back to {was}: {exc}")
    return notes


async def _answer(outcome: Outcome, plan: Plan, return_image: bool) -> Result:
    lines = [
        f"{shot['device']} · {shot['appearance']} · {shot['path']}" + (f" · {shot['note']}" if "note" in shot else "")
        for shot in outcome.shots
    ]
    lines += [f"skipped {skip['device']}: {skip['reason']}" for skip in outcome.skipped]
    lines += [f"note: {note}" for note in outcome.notes]
    data: dict[str, Any] = {
        "folder": str(plan.folder),
        "sheet": None,
        "shots": outcome.shots,
        "skipped": outcome.skipped,
    }
    if not outcome.cells:
        lines.insert(0, "no screenshot was taken")
        return {"content": [{"type": "text", "text": "\n".join(lines)}], "isError": True, "structuredContent": data}
    path = plan.folder / SHEET
    try:
        sheet = contact_sheet(outcome.cells, len(plan.appearances))
        await asyncio.to_thread(_write, path, sheet.jpeg)
    except OSError as exc:
        lines.append(f"the contact sheet could not be made: {exc}")
        return {"content": [{"type": "text", "text": "\n".join(lines)}], "isError": False, "structuredContent": data}
    data["sheet"] = str(path)
    lines.append(f"contact sheet: {path} · {sheet.width}x{sheet.height}px · {len(outcome.cells)} screenshots")
    content: list[dict[str, Any]] = [{"type": "text", "text": "\n".join(lines)}]
    if return_image:
        content.append(
            {"type": "image", "data": base64.b64encode(sheet.jpeg).decode("ascii"), "mimeType": "image/jpeg"}
        )
    return {"content": content, "isError": False, "structuredContent": data}


TOOL = make_tool("sim_matrix", (Capability.SCREENSHOT,), run)
