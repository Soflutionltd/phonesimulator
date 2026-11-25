# SPDX-License-Identifier: Apache-2.0
"""`sim_matrix`: one screen captured on several devices and appearances, laid out on one contact sheet, each device
given back the look it had -- and a device another agent holds left alone unless the call steals it."""

from __future__ import annotations

import asyncio
import base64
import dataclasses
import io
from pathlib import Path
from typing import Any, cast

from PIL import Image

from simtrail.connectors.base import Shot
from simtrail.core.actions import AgentActions
from simtrail.core.drivers import Drivers
from simtrail.core.flows import FlowStore
from simtrail.core.selections import Selections
from simtrail.protocol import DeviceChoice
from simtrail.seams import Caller
from simtrail.testing.fakes import FakeConnector
from simtrail.testing.rig import DeviceRig, scope
from simtrail.tools.context import ToolContext
from simtrail.tools.matrix import SHEET, resolve
from simtrail.tools.registry import ToolRegistry
from simtrail.tools.results import Result, text

CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude · notes")
OTHER = Caller(scope("tp-1"), key="agent-2", title="Codex")
REGISTRY = ToolRegistry()
SMALL = "2D961125-B1AB-402F-AABA-BE4B53837EF0"  # iPhone 17e, iOS 26.5
LARGE = "3AEF58CA-1341-4C5D-A09A-EEB4CCDA8BD5"  # iPhone 17 Pro Max, iOS 26.5
PRO = "D946616B-6E4F-4F5C-8C76-54FAD9B7D702"  # iPhone 17 Pro, booted
OLDER = "9F8B988D-A7DE-4B6E-A9FF-11C77C00F59F"  # iPhone 16 Pro, iOS 18.6


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (402, 874), (200, 30, 30)).save(out, format="JPEG")
    return out.getvalue()


def matrix_rig(tmp_path: Path, **kwargs: Any) -> DeviceRig:
    rig = DeviceRig(tmp_path, **kwargs)
    rig.config.set(recording_folder=str(tmp_path / "movies"))
    rig.idb.engine.shot = Shot(jpeg(), 402, 874)
    return rig


def tools(rig: DeviceRig, **changes: Any) -> ToolContext:
    async def sleep(seconds: float) -> None:
        rig.clock.advance(seconds)
        await asyncio.sleep(0)

    ctx = ToolContext(
        manager=rig.manager,
        actions=AgentActions(rig.manager, rig.config, clock=rig.clock, sleep=sleep),
        caller=CALLER,
        config=rig.config.get(CALLER.scope),
        copy=rig.copy,
        sleep=sleep,
        flows=FlowStore(lambda kept: rig.root / "flows" / kept.id),
        drivers=Drivers(rig.copy, clock=rig.clock),
    )
    return dataclasses.replace(ctx, **changes)


async def matrix(ctx: ToolContext, **arguments: Any) -> Result:
    return await REGISTRY.call("sim_matrix", {"save_to": "out", **arguments}, ctx)


def said(result: Result) -> list[str]:
    return str(result["content"][0]["text"]).splitlines()


async def test_each_device_is_captured_in_each_appearance_and_laid_out_on_one_sheet(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    for udid in (SMALL, LARGE):
        rig.xcrun.on("simctl", "ui", udid, "appearance", out="light\n")
        rig.xcrun.on("simctl", "ui", udid, "content_size", out="large\n")
    devices = ["small_iphone", "large_iphone"]
    result = await matrix(tools(rig), devices=devices, text_size="extra-large", return_image=True)
    out = tmp_path / "movies" / "out"
    lines = said(result)
    assert lines[:4] == [
        f"iPhone 17e · light · {out}/01-iphone-17e-light-extra-large.jpg",
        f"iPhone 17e · dark · {out}/01-iphone-17e-dark-extra-large.jpg",
        f"iPhone 17 Pro Max · light · {out}/02-iphone-17-pro-max-light-extra-large.jpg",
        f"iPhone 17 Pro Max · dark · {out}/02-iphone-17-pro-max-dark-extra-large.jpg",
    ]
    assert lines[4].startswith(f"contact sheet: {out / SHEET} · ") and lines[4].endswith(" · 4 screenshots")
    assert result["isError"] is False and result["structuredContent"]["sheet"] == str(out / SHEET)
    with Image.open(out / SHEET) as sheet:
        assert sheet.width < sheet.height, "two columns, two rows of tall screens"
    assert base64.b64decode(result["content"][1]["data"]) == (out / SHEET).read_bytes()
    argv = rig.argv()
    for udid in (SMALL, LARGE):
        asked = [args[3:] for args in argv if args[:3] == ("simctl", "ui", udid) and len(args) > 4]
        assert asked == [
            ("content_size", "extra-large"),
            ("appearance", "light"),
            ("appearance", "dark"),
            ("appearance", "light"),
            ("content_size", "large"),
        ], "the text size, each appearance, then the look it had"


async def test_a_variable_a_flow_types_into_a_secure_field_is_in_no_answer_and_no_event(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    field = {"x": 16, "width": 370, "height": 44}
    rig.idb.engine.document = {
        "elements": [
            {"type": "TextField", "label": "Email", "frame": {**field, "y": 100}},
            {"type": "SecureTextField", "label": "Password", "frame": {**field, "y": 160}},
        ]
    }
    ctx = tools(rig)
    await REGISTRY.call("sim_snapshot", {"mode": "full"}, ctx)
    steps = [{"type": "{{email}}", "into": "e1"}, {"type": "{{password}}", "into": "e2"}]
    saved = await REGISTRY.call("sim_flow", {"action": "save", "name": "sign-in", "steps": steps}, ctx)
    assert saved["isError"] is False, said(saved)
    # The device the matrix captures is brought up beside the agent's own: its events are heard once it is there.
    await matrix(ctx, devices=[PRO], appearances=["light"], save_to="before")
    instance = rig.manager.instance(CALLER.scope, PRO)
    assert instance is not None
    events = instance.events.subscribe()
    variables = {"email": "qa@example.com", "password": "matrix-s3cret"}
    played = await matrix(ctx, devices=[PRO], appearances=["light", "dark"], flow="sign-in", variables=variables)
    assert played["isError"] is False, said(played)
    assert [line.split(" · ")[1] for line in said(played)[:2]] == ["light", "dark"], "the flow finished on each"
    published = [events.get_nowait() for _ in range(events.qsize())]
    typed = [event["caption"] for event in published if event.get("gesture", {}).get("kind") == "type"]
    assert typed == ["qa@example.com", "••••"] * 2, "typed before each screenshot, the password never shown"
    assert "matrix-s3cret" not in repr([played, published])
    # The app shows it back later -- its eye tapped -- and the agent reads the screen: it is masked there too.
    rig.idb.engine.document = {
        "elements": [{"type": "StaticText", "label": "Your password is matrix-s3cret", "frame": {**field, "y": 100}}]
    }
    looked = await REGISTRY.call("sim_snapshot", {"mode": "full"}, ctx)
    assert "matrix-s3cret" not in repr(looked) and "Your password is ••••" in "\n".join(said(looked))


async def test_the_app_is_launched_afresh_and_a_flow_played_before_each_screenshot(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    ctx = tools(rig)
    await REGISTRY.call("sim_flow", {"action": "save", "name": "home", "steps": [{"press": "home"}]}, ctx)
    far = {"action": "save", "name": "far", "steps": [{"tap": [1, 9000]}, {"press": "home"}]}
    await REGISTRY.call("sim_flow", far, ctx)
    played = await matrix(ctx, devices=[PRO], appearances=["dark"], bundle_id="com.example.notes", flow="home")
    assert said(played)[0] == f"iPhone 17 Pro · dark · {tmp_path}/movies/out/01-iphone-17-pro-dark.jpg"
    assert ("simctl", "launch", "--terminate-running-process", PRO, "com.example.notes") in rig.argv()
    broken = await matrix(ctx, devices=[PRO], appearances=["light"], flow="far", save_to="again")
    line = said(broken)[0]
    assert line.startswith("iPhone 17 Pro · light · ") and line.endswith(
        "· the flow far did not finish: stopped at step 1 of 2: it failed, and the steps after it were not played"
    )
    assert broken["structuredContent"]["shots"][0]["note"].startswith("the flow far did not finish")


async def test_a_device_another_agent_holds_is_skipped_unless_the_call_steals_it(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    selections = Selections(rig.config, clock=rig.clock)
    ctx = tools(rig, selections=selections, per_agent=True)
    assert ctx.drivers is not None
    held = await rig.manager.ensure(CALLER.scope, LARGE)
    ctx.drivers.take(OTHER, held, exclusive=False, steal=False)
    selections.begin(OTHER)
    selections.bind(OTHER, SMALL)
    skipped = await matrix(ctx, devices=[LARGE, SMALL], appearances=["light"])
    assert said(skipped) == [
        "no screenshot was taken",
        "skipped iPhone 17 Pro Max: Codex drives it; steal: true takes it over, only when the person asked for it",
        "skipped iPhone 17e: Codex works on it; steal: true takes it over, only when the person asked for it",
    ]
    assert skipped["isError"] is True and skipped["structuredContent"]["sheet"] is None
    stolen = await matrix(ctx, devices=[LARGE], appearances=["light"], steal=True)
    assert stolen["isError"] is False and said(stolen)[1].startswith("note: iPhone 17 Pro Max: ")
    assert held.driver is not None and held.driver.key == CALLER.key
    assert selections.of(CALLER) is None, "the devices a matrix used do not become the agent's own"


async def test_what_cannot_be_captured_or_put_back_is_said_and_the_rest_goes_on(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    rig.xcrun.on("simctl", "ui", SMALL, "content_size", rc=1, err="no such option")
    rig.xcrun.on("simctl", "ui", LARGE, "appearance", out="dark\n")
    rig.xcrun.on("simctl", "ui", LARGE, "appearance", "light", rc=1, err="it would not turn")
    rig.xcrun.on("simctl", "ui", PRO, "appearance", out="light\n")
    rig.xcrun.on("simctl", "ui", PRO, "appearance", "light", rc=1, err="stuck dark")
    busy = await rig.manager.ensure(CALLER.scope, OLDER)
    busy.busy = "building (b1)"
    result = await matrix(tools(rig), devices=[SMALL, LARGE, PRO, OLDER, "ipad", "nope"], appearances=["dark"])
    lines = said(result)
    assert f"iPhone 17e · dark · {tmp_path}/movies/out/01-iphone-17e-dark.jpg" in lines
    assert f"iPhone 17 Pro Max · dark · {tmp_path}/movies/out/02-iphone-17-pro-max-dark.jpg" in lines
    assert "skipped iPhone 16 Pro: the device is busy: building (b1)" in lines
    assert "skipped ipad: no device here fits it that is not already in the matrix" in lines
    assert "skipped nope: not a preset, nor a UDID sim_device list shows" in lines
    assert "note: iPhone 17e: its appearance could not be read before, so it is left dark" in lines
    assert any(line.startswith("note: iPhone 17 Pro: its appearance could not be put back to light:") for line in lines)
    sheet = [line for line in lines if line.startswith("contact sheet:")]
    assert sheet and sheet[0].endswith(" · 3 screenshots")


async def test_a_failure_on_a_device_skips_it_after_giving_it_back_its_look(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    rig.xcrun.on("simctl", "ui", PRO, "appearance", out="light\n")
    rig.xcrun.on("simctl", "launch", rc=1, err="the app is not installed")
    result = await matrix(tools(rig), devices=[PRO], appearances=["dark"], bundle_id="com.example.notes")
    assert said(result)[1].startswith("skipped iPhone 17 Pro: stopped on it: ")
    assert ("simctl", "ui", PRO, "appearance", "light") in rig.argv(), "put back before it was skipped"


async def test_a_view_only_device_and_one_that_cannot_be_saved_to_are_skipped(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path, idb=FakeConnector("idb", available=False))
    ctx = tools(rig, drivers=None)
    await REGISTRY.call("sim_flow", {"action": "save", "name": "home", "steps": [{"press": "home"}]}, ctx)
    view_only = await matrix(ctx, devices=[PRO], appearances=["light"], flow="home")
    assert said(view_only)[1].startswith("skipped iPhone 17 Pro: sim_matrix needs input_touch")
    unread = await matrix(ctx, devices=[PRO], appearances=["light"], save_to="shots")
    assert unread["isError"] is False, "a device nobody is asked about is captured"
    rig = matrix_rig(tmp_path / "second")
    movies = tmp_path / "second" / "movies"
    movies.mkdir(parents=True)
    (movies / "out").write_text("a file", encoding="utf-8")
    assert await matrix(tools(rig), devices=[PRO]) == text(
        f"save_to names a file, {movies / 'out'}: name a folder", error=True
    )
    taken = movies / "taken" / "01-iphone-17-pro-light.jpg"
    taken.mkdir(parents=True)
    refused = await matrix(tools(rig), devices=[PRO], appearances=["light"], save_to="taken")
    assert said(refused)[1].startswith(f"skipped iPhone 17 Pro: could not save to {taken}")


async def test_a_screenshot_that_cannot_be_decoded_is_kept_without_a_sheet(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    rig.idb.engine.shot = Shot(b"not a jpeg", 402, 874)
    result = await matrix(tools(rig), devices=[PRO], appearances=["light"])
    assert result["isError"] is False and said(result)[-1].startswith("the contact sheet could not be made:")
    assert result["structuredContent"]["sheet"] is None


async def test_the_call_is_checked_before_any_device_is_touched(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    ctx = tools(rig)
    presets = "small_iphone, large_iphone, ipad, android"
    cases: list[tuple[dict[str, Any], str]] = [
        ({"devices": []}, f"devices is a list of 1 to 6 UDIDs from sim_device list, or presets: {presets}"),
        ({"devices": [PRO], "appearances": ["sepia"]}, "appearances is a list of light, dark or both"),
        ({"devices": [PRO], "text_size": "huge"}, "text_size is one of extra-small"),
        ({"devices": [PRO], "bundle_id": "not an id"}, "bundle_id must be an app's id"),
        ({"devices": [PRO], "variables": {"a": "b"}}, "variables go with a flow: name the flow to play"),
        ({"devices": [PRO], "flow": "none"}, "no flow is named none"),
        ({"devices": [PRO], "save_to": "/etc/x"}, "save_to must be inside"),
        ({"devices": [PRO], "save_to": ""}, "save_to is a folder name or path of at most 1024 characters"),
        ({"devices": [PRO], "steal": "yes"}, "steal is true or false"),
    ]
    for arguments, refused in cases:
        result = await REGISTRY.call("sim_matrix", arguments, ctx)
        assert result["isError"] is True and said(result)[0].startswith(refused), arguments
    no_flows = await REGISTRY.call("sim_matrix", {"devices": [PRO], "flow": "x"}, tools(rig, flows=None))
    assert no_flows == text("flows are not kept here", error=True)
    rig.config.set(enabled=False)
    off = await REGISTRY.call("sim_matrix", {"devices": [PRO]}, tools(rig))
    assert off["isError"] is True
    assert not [args for args in rig.argv() if args[:2] == ("simctl", "ui")]


async def test_without_save_to_each_matrix_gets_a_new_folder_of_its_own(tmp_path: Path) -> None:
    rig = matrix_rig(tmp_path)
    first = await REGISTRY.call("sim_matrix", {"devices": [PRO], "appearances": ["light"]}, tools(rig))
    second = await REGISTRY.call("sim_matrix", {"devices": [PRO], "appearances": ["light"]}, tools(rig))
    folders = {first["structuredContent"]["folder"], second["structuredContent"]["folder"]}
    assert len(folders) == 2 and all(Path(folder).parent == tmp_path / "movies" for folder in folders)
    assert all(Path(folder).name.startswith("matrix-") for folder in folders)


def _choice(udid: str, name: str, **more: Any) -> DeviceChoice:
    choice: dict[str, Any] = {
        "udid": udid,
        "name": name,
        "runtime": "iOS 26.5",
        "state": "Shutdown",
        "created": False,
        "kind": "simulator",
        "connection": None,
        "detail": None,
        "detail_code": None,
        "usable": True,
    }
    return cast(DeviceChoice, {**choice, **more})


def test_presets_pick_by_size_then_booted_then_the_newest_runtime() -> None:
    listed = [
        _choice("a", "iPhone 16 Pro Max", runtime="iOS 18.6"),
        _choice("b", "iPhone 17 Pro Max"),
        _choice("c", "iPhone 17 Plus", state="Booted"),
        _choice("d", "iPhone SE (3rd generation)"),
        _choice("e", "iPhone 17"),
        _choice("f", "iPad Pro 13-inch (M5)"),
        _choice("g", "iPad mini (A17 Pro)", usable=False),
        _choice("h", "Pixel 9", kind="android"),
        _choice("i", "Pixel 8", kind="android", connection="usb"),
    ]
    found, skipped = resolve(["large_iphone", "small_iphone", "ipad", "android", "large_iphone", "g"], listed)
    assert [device.choice["udid"] for device in found] == ["b", "d", "f", "h", "a"], "by size before the runtime"
    assert skipped == [{"device": "iPad mini (A17 Pro)", "reason": "it cannot be used now"}]
    found, _ = resolve(["small_iphone", "d"], listed)
    assert [device.choice["udid"] for device in found] == ["e", "d"], "a device named by its UDID is not picked"
