# SPDX-License-Identifier: Apache-2.0
"""`sim_login`: an app signed in from a password manager whose values the agent never reads.

The password managers' CLIs are played (`FakeCli`): no test runs 1Password's or Bitwarden's, which the conftest guard
refuses (`testing.guards`).
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest

from simtrail.config.model import SimConfig
from simtrail.core.actions import AgentActions
from simtrail.core.activity import of_call
from simtrail.core.drivers import changes_device
from simtrail.core.given import GivenLogins
from simtrail.core.instance import DeviceInstance
from simtrail.platform import passwords
from simtrail.platform.passwords import Credentials, Ran
from simtrail.platform.xcrun import XcrunResult
from simtrail.protocol import Connection, DeviceKind, RecordingState
from simtrail.seams import Caller
from simtrail.testing.fakes import FakeConnector, FakeEngine, FakeKeyboard, no_wait
from simtrail.testing.rig import DeviceRig, scope
from simtrail.tools import login as login_tool
from simtrail.tools.context import ToolContext
from simtrail.tools.login import Logins, LoginToolProvider
from simtrail.tools.registry import DeviceToolProvider, ToolRegistry
from simtrail.tools.results import Result

CALLER = Caller(scope("tp-1"), key="agent-1", title="Claude · notes")
USERNAME = "ann@example.com"
PASSWORD = "S3cr3t Pa55/word!"
TOTP = "492817"
SECRETS = (PASSWORD, TOTP, quote(PASSWORD, safe=""))

OP_LIST = [
    {
        "id": "abc123",
        "title": "Example",
        "vault": {"id": "v1", "name": "Private"},
        "additional_information": USERNAME,
        "urls": [{"href": "https://accounts.example.com/login"}],
    },
    {
        "id": "def456",
        "title": "Example (Bob)",
        "vault": {"id": "v2", "name": "Shared"},
        "additional_information": "bob@example.com",
        "urls": [{"href": "https://www.example.com"}, {"label": "no href"}],
    },
    {
        "id": "ghi789",
        "title": "Elsewhere",
        "vault": {"id": "v1", "name": "Private"},
        "additional_information": USERNAME,
        "urls": [{"href": "https://elsewhere.org"}],
    },
    {"title": "no id"},
    "not an item",
]


def op_item(username: str = USERNAME, password: str = PASSWORD, totp: str = TOTP) -> str:
    fields: list[Any] = [
        {"id": "username", "purpose": "USERNAME", "value": username},
        {"id": "password", "purpose": "PASSWORD", "value": password},
        "not a field",
    ]
    if totp:
        fields.append({"id": "otp", "type": "OTP", "value": "otpauth://totp/x", "totp": totp})
    return json.dumps({"id": "abc123", "fields": fields})


class FakeCli:
    """Plays the password managers' CLIs: each argv answered by the longest prefix a test gave."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.answers: dict[tuple[str, ...], Ran] = {}

    def on(self, *prefix: str, out: Any = "", code: int = 0, reason: str = "") -> FakeCli:
        self.answers[prefix] = Ran(code, out if isinstance(out, str) else json.dumps(out), reason)
        return self

    async def __call__(self, argv: Sequence[str], timeout: float) -> Ran:
        self.calls.append(tuple(argv))
        words = tuple(argv)
        for size in range(len(words), 0, -1):
            if words[:size] in self.answers:
                return self.answers[words[:size]]
        raise AssertionError(f"no answer for {argv}")


def one_password(cli: FakeCli | None = None) -> FakeCli:
    cli = cli or FakeCli()
    cli.on("/bin/op", "item", "list", out=OP_LIST)
    cli.on("/bin/op", "item", "get", "abc123", out=op_item())
    return cli


def node(kind: str, label: str, y: int, value: str | None = None) -> dict[str, Any]:
    made: dict[str, Any] = {
        "type": kind,
        "label": label,
        "frame": {"x": 16, "y": y, "width": 370, "height": 44},
        "enabled": True,
    }
    if value is not None:
        made["value"] = value
    return made


def screen(*children: dict[str, Any]) -> dict[str, Any]:
    return {"elements": [{"type": "Application", "label": "Notes", "children": list(children)}]}


#: e1 the heading, e2 the e-mail field, e3 the password field, e4 the button.
SIGN_IN = screen(
    node("StaticText", "Welcome back", 80),
    node("TextField", "Email", 150),
    node("SecureTextField", "Password", 220),
    node("Button", "Sign In", 300),
)


def found_at(name: str, configured: str) -> str:
    return f"/bin/{name}"


class Rigged:
    def __init__(self, tmp_path: Path, cli: FakeCli, document: dict[str, Any] = SIGN_IN, *, us: bool = False) -> None:
        self.engine = FakeEngine(document=document)
        self.rig = DeviceRig(tmp_path, idb=FakeConnector("idb", engine=self.engine), keyboard=FakeKeyboard(us=us))
        self.rig.config.set(login_sources=("1password",))
        self.cli = cli
        self.registry = self.registry_finding(found_at)
        self.actions = AgentActions(self.rig.manager, self.rig.config, clock=self.rig.clock, sleep=no_wait)
        self.given: GivenLogins | None = None

    def registry_finding(self, find: Any) -> ToolRegistry:
        made = functools.partial(passwords.sources, run=self.cli, find=find)
        return ToolRegistry((DeviceToolProvider(), LoginToolProvider(Logins(made))))

    async def up(self) -> DeviceInstance:
        return await self.rig.up()

    async def call(self, name: str, arguments: dict[str, Any]) -> Result:
        ctx = ToolContext(
            manager=self.rig.manager,
            actions=self.actions,
            caller=CALLER,
            config=self.rig.config.get(CALLER.scope),
            copy=self.rig.copy,
            sleep=no_wait,
            given=self.given,
        )
        return await self.registry.call(name, arguments, ctx)

    async def login(self, **arguments: Any) -> Result:
        return await self.call("sim_login", {"app": "com.example.notes", **arguments})

    def pasted(self) -> list[bytes | None]:
        return [call.input_data for call in self.rig.xcrun.calls if call.args[1] == "pbcopy"]


def said(result: Result) -> str:
    return str(result["content"][0]["text"])


# -- a login, filled --------------------------------------------------------------------------------------------------


async def test_the_login_for_the_account_is_typed_into_its_fields_and_only_what_it_is_is_said(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    answer = await r.login(account="ANN@example.com ", submit=True)
    assert answer["isError"] is False, said(answer)
    assert said(answer) == (
        'Used the 1password login "Example" (ann@example.com, 1Password vault Private, id abc123): typed the '
        "username into e2, the password into e3, then pressed return. Call sim_snapshot to see what the app answered."
    )
    assert answer["structuredContent"] == {
        "source": "1password",
        "item": {"id": "abc123", "title": "Example", "where": "1Password vault Private"},
        "filled": ["username", "password"],
        "submitted": True,
    }
    # The Mac's keyboard is not US-shaped here, so each went in through the pasteboard, which is emptied after.
    assert r.pasted() == [USERNAME.encode(), PASSWORD.encode(), b""]
    # Asked by id, in the vault it is in: every vault was listed, none named.
    assert r.cli.calls == [
        ("/bin/op", "item", "list", "--categories", "Login", "--format", "json"),
        ("/bin/op", "item", "get", "abc123", "--vault", "v1", "--reveal", "--format", "json"),
    ]


async def test_where_the_keyboard_types_the_text_it_goes_in_as_keys_and_nothing_is_pasted(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password(), us=True)
    await r.up()
    answer = await r.login(account=USERNAME)
    assert answer["isError"] is False and "then pressed return" not in said(answer)
    assert r.pasted() == []
    assert any(event.kind == "key" for event in r.engine.hid_events)


async def test_no_value_reaches_an_answer_a_log_an_event_or_an_argv(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    r = Rigged(tmp_path, one_password())
    instance = await r.up()
    events = instance.events.subscribe()
    answers = [
        await r.login(account=USERNAME, submit=True),
        await r.login(account=USERNAME, code=True, field="e2"),
    ]
    # The app shows the password back -- its eye tapped -- and the code; and a later call fails on the password.
    r.engine.document = screen(
        node("TextField", "Email", 150, USERNAME),
        node("TextField", "Password", 220, PASSWORD),
        node("StaticText", f"Your code {TOTP} was sent; link ?p={quote(PASSWORD, safe='')}", 300),
    )
    answers += [
        await r.call("sim_snapshot", {"mode": "full"}),
        await r.call("sim_act", {"steps": [{"tap": "e3"}]}),
        await r.call("sim_act", {"steps": [{"type": PASSWORD, "into": "e99"}]}),
    ]
    published = [events.get_nowait() for _ in range(events.qsize())]
    assert any(event.get("caption") == "••••" for event in published), "the viewer is shown that something is typed"
    assert any(event.get("activity") == "Typing the password" for event in published)
    told = json.dumps([answers, published], ensure_ascii=False)
    for secret in SECRETS:
        assert secret not in told
        assert secret not in caplog.text
        assert all(secret not in " ".join(argv) for argv in r.cli.calls)
        assert all(secret not in " ".join(call.args) for call in r.rig.xcrun.calls)
    snapshot = said(answers[2])
    assert 'field "Password" ="••••"' in snapshot and 'text "Your code •••• was sent; link ?p=••••"' in snapshot


async def test_a_login_cancelled_while_it_is_typed_is_masked_in_every_answer_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = Rigged(tmp_path, one_password(), us=True)
    await r.up()
    typing = asyncio.Event()

    async def hid(events: Any) -> None:
        async for event in events:
            r.engine.hid_events.append(event)
            typing.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(r.engine, "hid", hid)
    signing_in = asyncio.ensure_future(r.login(account=USERNAME))
    await typing.wait()
    signing_in.cancel()
    with pytest.raises(asyncio.CancelledError):
        await signing_in
    monkeypatch.undo()
    r.engine.document = screen(node("StaticText", f"Your password is {PASSWORD}", 100))
    looked = said(await r.call("sim_snapshot", {"mode": "full"}))
    assert PASSWORD not in looked and "Your password is ••••" in looked


async def test_a_one_time_code_goes_into_the_field_named_or_the_one_that_reads_like_a_code(tmp_path: Path) -> None:
    code_screen = screen(node("StaticText", "Enter the code", 80), node("TextField", "Verification code", 150))
    r = Rigged(tmp_path, one_password(), code_screen)
    await r.up()
    answer = await r.login(account=USERNAME, code=True, submit=True)
    assert answer["isError"] is False, said(answer)
    assert said(answer).startswith('Used the 1password login "Example"') and "the one-time code into e2" in said(answer)
    assert answer["structuredContent"]["filled"] == ["one-time code"]
    assert r.pasted() == [TOTP.encode(), b""]
    refused = await r.login(account=USERNAME, code=True, field="e1")
    assert refused["isError"] is True and said(refused).startswith('e1 "Enter the code" is a text, not a field')


@pytest.mark.parametrize(
    ("document", "field", "refusal"),
    [
        (screen(node("TextField", "Email", 150)), None, "no password field is on screen"),
        (
            screen(node("SecureTextField", "Password", 150), node("SecureTextField", "Confirm", 220)),
            None,
            'several password fields are on screen (e1 "Password", e2 "Confirm"): pass field',
        ),
        (SIGN_IN, "e2", 'e2 "Email" is a field, not a secure field: a password is typed only where it is hidden'),
        (SIGN_IN, "e9", "e9 is not on screen now"),
    ],
)
async def test_a_password_goes_only_into_a_secure_field(
    tmp_path: Path, document: dict[str, Any], field: str | None, refusal: str
) -> None:
    r = Rigged(tmp_path, one_password(), document)
    await r.up()
    arguments: dict[str, Any] = {"account": USERNAME}
    if field is not None:
        arguments["field"] = field
    refused = await r.login(**arguments)
    assert refused["isError"] is True and refusal in said(refused)
    assert r.cli.calls == [], "the password manager is not asked while the screen has nowhere to put it"
    assert [event for event in r.engine.hid_events if event.kind != "touch"] == [] and r.pasted() == [], (
        "at most the field named is tapped, to give it the focus: nothing is typed"
    )


class Focusing(FakeEngine):
    """A Flutter app's sign-in screen: its password field says it is secure only once a touch gave it the focus."""

    def __init__(self, before: dict[str, Any], after: dict[str, Any]) -> None:
        super().__init__(document=before)
        self.after = after

    async def hid(self, events: Any) -> None:
        await super().hid(events)
        if any(event.kind == "touch" for event in self.hid_events):
            self.document = self.after


FLUTTER = screen(node("TextField", "Email", 150), node("TextField", "••••••••", 220), node("Button", "Sign In", 300))
FOCUSED = screen(
    node("TextField", "Email", 150), node("SecureTextField", "••••••••", 220), node("Button", "Sign In", 300)
)


@pytest.mark.parametrize("field", [None, "e2"])
async def test_a_password_field_secure_only_once_focused_is_tapped_then_filled(
    tmp_path: Path, field: str | None
) -> None:
    r = Rigged(tmp_path, one_password(), FLUTTER)
    r.engine = Focusing(FLUTTER, FOCUSED)
    r.rig = DeviceRig(tmp_path, idb=FakeConnector("idb", engine=r.engine), keyboard=FakeKeyboard(us=False))
    r.rig.config.set(login_sources=("1password",))
    r.actions = AgentActions(r.rig.manager, r.rig.config, clock=r.rig.clock, sleep=no_wait)
    await r.up()
    answer = await r.login(account=USERNAME, **({"field": field} if field else {}))
    assert answer["isError"] is False, said(answer)
    assert "the password into e" in said(answer) and PASSWORD.encode() in r.pasted()
    first = next(event for event in r.engine.hid_events if event.kind == "touch")
    assert (round(first.x), round(first.y)) == (201, 242), "the password's field was tapped first"


async def test_a_tapped_field_that_does_not_turn_secure_takes_no_password(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password(), FLUTTER)
    await r.up()
    refused = await r.login(account=USERNAME)
    assert refused["isError"] is True and "no password field is on screen" in said(refused)
    assert r.cli.calls == [] and r.pasted() == []
    beside = Rigged(tmp_path / "beside", one_password(), SIGN_IN)
    beside.engine = Focusing(SIGN_IN, SIGN_IN)
    beside.rig = DeviceRig(
        tmp_path / "beside", idb=FakeConnector("idb", engine=beside.engine), keyboard=FakeKeyboard(us=False)
    )
    beside.rig.config.set(login_sources=("1password",))
    beside.actions = AgentActions(beside.rig.manager, beside.rig.config, clock=beside.rig.clock, sleep=no_wait)
    await beside.up()
    named = await beside.login(account=USERNAME, field="e2")
    assert named["isError"] is True and 'e2 "Email" is a field, not a secure field' in said(named)
    assert beside.pasted() == [], "never into another secure field the screen happens to show"


async def test_the_field_named_is_used_when_several_are_secure(tmp_path: Path) -> None:
    document = screen(node("SecureTextField", "Password", 150), node("SecureTextField", "Confirm", 220))
    r = Rigged(tmp_path, one_password(), document)
    await r.up()
    answer = await r.login(account=USERNAME, field="e2")
    assert said(answer).split(": typed ")[1].startswith("the password into e2.")


@pytest.mark.parametrize(
    ("code_screen", "field", "refusal"),
    [
        (screen(node("TextField", "Name", 150)), None, "none read like one"),
        (
            screen(node("TextField", "SMS code", 150), node("TextField", "Authenticator code", 220)),
            None,
            'several (e1 "SMS code", e2 "Authenticator code") read like one',
        ),
        (screen(node("TextField", "Code", 150)), "e7", "e7 is not on screen now"),
    ],
)
async def test_a_code_field_that_cannot_be_told_is_refused(
    tmp_path: Path, code_screen: dict[str, Any], field: str | None, refusal: str
) -> None:
    r = Rigged(tmp_path, one_password(), code_screen)
    await r.up()
    arguments: dict[str, Any] = {"account": USERNAME, "code": True}
    if field is not None:
        arguments["field"] = field
    refused = await r.login(**arguments)
    assert refused["isError"] is True and refusal in said(refused)


# -- which login -----------------------------------------------------------------------------------------------------


async def test_a_login_for_another_account_is_never_used_even_when_it_is_the_only_one(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    refused = await r.login(account="carol@example.com")
    assert said(refused) == (
        "no saved login for carol@example.com on com.example.notes in 1password; nothing was typed. Found for other "
        'accounts: "Example" (1Password vault Private, id abc123); "Example (Bob)" (1Password vault Shared, id '
        "def456). Ask the person: never sign in with another account"
    )
    assert r.engine.hid_events == [] and all("get" not in argv for argv in r.cli.calls)


async def test_a_login_that_holds_another_username_once_revealed_is_refused_before_anything_is_typed(
    tmp_path: Path,
) -> None:
    cli = one_password()
    cli.on("/bin/op", "item", "get", "abc123", out=op_item(username="mallory@example.com"))
    r = Rigged(tmp_path, cli)
    await r.up()
    refused = await r.login(account=USERNAME)
    assert refused["isError"] is True
    assert said(refused).endswith("holds another username than ann@example.com; nothing was typed")
    assert r.engine.hid_events == [] and r.pasted() == []


async def test_several_logins_for_the_app_are_refused_with_their_ids_and_item_chooses(tmp_path: Path) -> None:
    cli = one_password()
    cli.on("/bin/op", "item", "get", "def456", out=op_item(username="bob@example.com"))
    r = Rigged(tmp_path, cli)
    await r.up()
    refused = await r.login()
    assert said(refused) == (
        'several saved logins match com.example.notes: pass item with the id of the one to use -- "Example" '
        '(ann@example.com, 1Password vault Private, id abc123); "Example (Bob)" (bob@example.com, 1Password vault '
        "Shared, id def456)"
    )
    chosen = await r.login(item="def456")
    assert chosen["structuredContent"]["item"]["id"] == "def456"
    by_title = await r.login(item="example (bob)")
    assert by_title["structuredContent"]["item"]["id"] == "def456"
    # The list is read once and kept: it holds nothing secret.
    assert [argv[2] for argv in cli.calls] == ["list", "get", "get"]


async def test_an_item_saved_for_another_app_is_refused(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    refused = await r.login(item="ghi789")
    assert said(refused) == (
        'the saved login "Elsewhere" (ann@example.com, 1Password vault Private, id ghi789) is for elsewhere.org, not '
        "com.example.notes; nothing was typed. Save com.example.notes with it in the password manager if it is the "
        "same account"
    )
    missing = await r.login(item="nope")
    assert said(missing) == "no saved login 'nope' for com.example.notes in 1password"


async def test_an_app_with_no_login_saved_says_how_to_save_one_and_reads_the_list_again_first(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    refused = await r.call("sim_login", {"app": "com.unknown.app"})
    assert said(refused).startswith("no saved login for com.unknown.app in 1password: save the app's website")
    assert [argv[2] for argv in r.cli.calls] == ["list", "list"], "a list kept from before is read again"


async def test_an_app_saved_by_its_id_or_by_a_website_matches(tmp_path: Path) -> None:
    cli = FakeCli().on(
        "/bin/op",
        "item",
        "list",
        out=[
            {"id": "a1", "title": "Android", "vault": {}, "urls": [{"href": "android://com.example.notes"}]},
            {"id": "w1", "title": "Web", "vault": {"id": "v"}, "urls": [{"href": "notes.example.co.uk"}]},
        ],
    )
    cli.on("/bin/op", "item", "get", "a1", out=op_item())
    cli.on("/bin/op", "item", "get", "w1", "--vault", "v", out=op_item())
    r = Rigged(tmp_path, cli)
    await r.up()
    by_id = await r.login()
    assert by_id["structuredContent"]["item"] == {"id": "a1", "title": "Android", "where": "1Password vault ?"}
    by_site = await r.call("sim_login", {"app": "https://login.example.co.uk/x"})
    assert by_site["structuredContent"]["item"]["id"] == "w1"


async def test_a_password_only_screen_that_shows_another_account_is_refused(tmp_path: Path) -> None:
    other = screen(node("StaticText", "Password for bob@example.com", 80), node("SecureTextField", "Password", 150))
    r = Rigged(tmp_path, one_password(), other)
    await r.up()
    refused = await r.login(account=USERNAME)
    assert said(refused) == (
        "the screen asks for the password of bob@example.com, and the saved login is another account; nothing was typed"
    )
    r.engine.document = screen(node("StaticText", f"Hi {USERNAME}", 80), node("SecureTextField", "Password", 150))
    answer = await r.login(account=USERNAME)
    assert answer["isError"] is False and answer["structuredContent"]["filled"] == ["password"]


async def test_a_username_field_that_already_holds_the_username_is_left_as_it_is(tmp_path: Path) -> None:
    filled = screen(node("TextField", "Email", 150, USERNAME.upper()), node("SecureTextField", "Password", 220))
    r = Rigged(tmp_path, one_password(), filled)
    await r.up()
    answer = await r.login(account=USERNAME)
    assert "typed the password into e2 (e1, the username's field, was left as it was)" in said(answer)
    assert r.pasted() == [PASSWORD.encode(), b""]


async def test_a_login_without_a_password_or_a_code_says_so(tmp_path: Path) -> None:
    cli = one_password()
    cli.on("/bin/op", "item", "get", "abc123", out=op_item(password="", totp=""))
    r = Rigged(tmp_path, cli)
    await r.up()
    assert said(await r.login(account=USERNAME)).endswith("id abc123) has no password")
    r.engine.document = screen(node("TextField", "One-time code", 150))
    no_code = await r.login(account=USERNAME, code=True)
    assert said(no_code).endswith("has no one-time code: ask the person for the code the app asks for")


# -- when it is refused -----------------------------------------------------------------------------------------------


async def test_it_is_off_until_a_source_is_named_and_refused_in_observe_mode(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    r.rig.config.set(login_sources=())
    assert said(await r.login()) == "sim_login is off: login.sources names no password manager"
    r.rig.config.set(login_sources=("1password",), agent_observe=True)
    refused = await r.login()
    assert refused["isError"] is True and said(refused).startswith("agents only observe here (agent.observe)")
    assert r.cli.calls == []


REAL: list[tuple[DeviceKind, Connection | None]] = [("physical", "usb"), ("android", "usb"), ("mac", None)]


def as_if(
    monkeypatch: pytest.MonkeyPatch, instance: DeviceInstance, kind: DeviceKind, connection: Connection | None
) -> None:
    """The device a call is given, made out to be another kind: the rig brings up simulators only."""
    instance.kind, instance.connection = kind, connection

    async def ready(ctx: ToolContext) -> DeviceInstance:
        return instance

    monkeypatch.setattr(login_tool, "ready_device", ready)


@pytest.mark.parametrize(("kind", "connection"), REAL)
async def test_a_real_device_or_a_mac_app_is_refused_unless_the_setting_allows_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: DeviceKind, connection: Connection | None
) -> None:
    # Typed as keys: the rig's control of its devices pastes onto simulators only.
    r = Rigged(tmp_path, one_password(), us=True)
    as_if(monkeypatch, await r.up(), kind, connection)
    refused = await r.login(account=USERNAME)
    assert said(refused).endswith(
        "is a real device or a macOS app, which holds real data: sim_login signs in only on simulators and emulators "
        "unless a person turns login.real_devices on"
    )
    assert r.cli.calls == []
    r.rig.config.set(login_real_devices=True)
    allowed = await r.login(account=USERNAME)
    # A macOS app is typed into through its window's input, which the rig's simulator session has none of.
    expected = "this session does not support window input" if kind == "mac" else "Used the 1password login"
    assert expected in said(allowed) and "real data" not in said(allowed)


async def test_an_emulator_on_this_mac_is_signed_in_like_a_simulator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r = Rigged(tmp_path, one_password(), us=True)
    as_if(monkeypatch, await r.up(), "android", None)
    answer = await r.login(account=USERNAME)
    assert answer["isError"] is False, said(answer)


class Recording:
    """A recording under way, as far as a sign-in asks."""

    def state(self, now: float) -> RecordingState:
        raise AssertionError("not asked")

    def agent(self, kind: str, points: Sequence[tuple[float, float]], duration: float, lead: float) -> None:
        raise AssertionError("nothing is drawn: nothing is typed")

    def person(self, phase: str, x: float, y: float) -> None:
        raise AssertionError("not asked")

    async def end(self) -> None:
        return None


async def test_a_recording_under_way_is_stopped_first(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    instance = await r.up()
    instance.recording = Recording()
    refused = await r.login(account=USERNAME)
    assert said(refused) == "the screen is being recorded: stop the recording (sim_record stop) before signing in"
    assert r.cli.calls == []


@pytest.mark.parametrize(
    ("arguments", "refusal"),
    [
        ({"app": ""}, "app is text of 1 to 255 characters"),
        ({"app": "x" * 256}, "app is text of 1 to 255 characters"),
        ({"account": "  "}, "account is text of 1 to 255 characters"),
        ({"item": 3}, "item is text of 1 to 255 characters"),
        ({"field": "e" * 17}, 'field is a ref from sim_snapshot, such as "e5"'),
        ({"code": "yes"}, "code is true or false"),
        ({"source": "keychain"}, "source is one of 1password, bitwarden, command, given"),
        ({"source": "bitwarden"}, "bitwarden is not in login.sources (1password)"),
    ],
)
async def test_arguments_asked_for_wrongly_are_refused(tmp_path: Path, arguments: dict[str, Any], refusal: str) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    answer = await r.call("sim_login", {"app": "com.example.notes", **arguments})
    assert answer["isError"] is True and said(answer) == refusal


async def test_a_source_named_is_the_only_one_asked(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    await r.up()
    answer = await r.login(account=USERNAME, source="1password")
    assert answer["isError"] is False, said(answer)


async def test_a_password_manager_that_fails_says_why_in_its_own_words(tmp_path: Path) -> None:
    cli = FakeCli().on("/bin/op", "item", "list", code=1, reason="[ERROR] authorization prompt dismissed")
    r = Rigged(tmp_path, cli)
    await r.up()
    refused = await r.login()
    assert said(refused) == "1password: 1Password's item list failed: [ERROR] authorization prompt dismissed"
    cli.on("/bin/op", "item", "list", out=OP_LIST).on("/bin/op", "item", "get", code=1, reason="timed out")
    revealed = await r.login(account=USERNAME)
    assert said(revealed) == "1password: 1Password's item get failed: timed out"


async def test_a_cli_that_is_not_installed_is_refused_with_how_to_install_it(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    r.registry = r.registry_finding(lambda name, configured: None)
    await r.up()
    refused = await r.login()
    assert said(refused).startswith("1Password's CLI was not found: install it (brew install 1password-cli)")


async def test_the_sources_are_made_again_only_when_their_settings_change(tmp_path: Path) -> None:
    made: list[tuple[str, ...]] = []

    def make(entries: tuple[str, ...], **_settings: Any) -> list[passwords.Source]:
        made.append(entries)
        return [passwords.Command(entry.removeprefix("command:"), timeout=1.0, run=FakeCli()) for entry in entries]

    logins = Logins(make)
    config = Rigged(tmp_path, FakeCli()).rig.config
    config.set(login_sources=("command:/bin/a",))
    first = logins.sources(config.get(CALLER.scope), None)
    assert logins.sources(config.get(CALLER.scope), "command") == first
    config.set(login_timeout=30)
    logins.sources(config.get(CALLER.scope), None)
    assert made == [("command:/bin/a",), ("command:/bin/a",)]


class ArgvText:
    """Text typed the way adb's ``input text`` types it: in a command line."""

    text_in_argv = True

    async def type(self, text: str) -> None:
        raise AssertionError("never typed")


async def test_typing_through_adbs_command_line_is_refused_before_anything_is_typed(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    instance = await r.up()
    assert instance.session is not None
    instance.session.text = ArgvText()
    refused = await r.login(account=USERNAME)
    assert said(refused).startswith("this device types text through adb's command line")
    assert r.engine.hid_events == []


async def test_a_paste_ios_refuses_and_a_pasteboard_that_cannot_be_emptied_are_said(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    instance = await r.up()
    instance.runtime = "iOS 27.0"
    pastes = iter(range(100))

    def paste(args: tuple[str, ...]) -> XcrunResult:
        third = next(pastes) == 2
        return XcrunResult(1 if third else 0, "", "refused" if third else "")

    r.rig.xcrun.on("simctl", "pbcopy", then=paste)
    answer = await r.login(account=USERNAME)
    assert "It was pasted, and iOS 27.0 refuses a paste it did not ask for" in said(answer)
    assert "The device's pasteboard could not be emptied after the paste" in said(answer)


async def test_a_device_busy_with_a_build_takes_no_login(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    instance = await r.up()
    instance.busy = "building"
    refused = await r.login(account=USERNAME)
    assert said(refused) == "the device is busy: building"
    assert r.pasted() == []


def test_sim_login_changes_the_device_and_says_it_is_signing_in() -> None:
    assert changes_device("sim_login", {"app": "x"}) is True
    assert of_call("sim_login", {}) == "Signing in"


def test_the_tool_is_offered_with_its_instructions_only_while_a_source_is_named() -> None:
    provider = LoginToolProvider()
    off = SimConfig.defaults()
    on = dataclasses.replace(off, login_sources=("1password",))
    assert not provider.offered(off) and provider.instructions(off) == ""
    assert provider.offered(on) and "sim_login" in provider.instructions(on)
    assert [tool.name for tool in provider.tools] == ["sim_login"]


async def test_a_login_with_no_username_types_only_the_password_and_leaves_the_username_field(tmp_path: Path) -> None:
    cli = one_password()
    cli.on("/bin/op", "item", "get", "abc123", out=op_item(username=""))
    r = Rigged(tmp_path, cli)
    await r.up()
    answer = await r.login(item="abc123")
    assert "typed the password into e3 (e2, the username's field, was left as it was)" in said(answer)
    assert r.pasted() == [PASSWORD.encode(), b""]


# -- a login handed over by simtrail login ---------------------------------------------------------------------------


async def test_a_login_handed_over_is_typed_once_without_asking_any_password_manager(tmp_path: Path) -> None:
    r = Rigged(tmp_path, one_password())
    r.rig.config.set(login_sources=())
    await r.up()
    given = GivenLogins()
    r.given = given
    item = given.give(CALLER.scope.id, "com.example.notes", "Example", Credentials(USERNAME, PASSWORD))
    answer = await r.login(source="given", item=item, account=USERNAME, submit=True)
    assert answer["isError"] is False, said(answer)
    assert said(answer).startswith('Used the given login "Example"') and PASSWORD.encode() in r.pasted()
    assert r.cli.calls == [], "no password manager was asked"
    again = await r.login(source="given", item=item, account=USERNAME)
    assert again["isError"] is True and "it was used or expired" in said(again), "taken once"
    other = given.give("tp-9", "com.example.notes", "Example", Credentials(USERNAME, PASSWORD))
    assert (await r.login(source="given", item=other))["isError"] is True, "for another scope"
    bare = await r.login(source="given")
    assert bare["isError"] is True and said(bare) == 'source "given" takes the item simtrail login handed over'
    off = await r.login(account=USERNAME)
    assert off["isError"] is True and "sim_login is off" in said(off), "an agent alone still needs login.sources"
