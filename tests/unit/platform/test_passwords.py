# SPDX-License-Identifier: Apache-2.0
"""The password managers `sim_login` reads: what each CLI is asked, what is kept of its answer, and how it fails.

No test runs a password manager: their CLIs are played (`FakeCli`), and `run` is tried on this Python alone.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from rocketwright.platform import passwords
from rocketwright.platform.passwords import (
    Bitwarden,
    Command,
    Credentials,
    Login,
    OnePassword,
    PasswordSourceError,
    Ran,
    find_program,
    host_of,
    run,
)

PASSWORD = "hunter2-but-longer"


class FakeCli:
    def __init__(self, *answers: tuple[tuple[str, ...], Ran]) -> None:
        self.answers = dict(answers)
        self.calls: list[tuple[str, ...]] = []
        self.timeouts: list[float] = []

    async def __call__(self, argv: Sequence[str], timeout: float) -> Ran:
        self.calls.append(tuple(argv))
        self.timeouts.append(timeout)
        return self.answers[tuple(argv)]


def ok(value: Any) -> Ran:
    return Ran(0, value if isinstance(value, str) else json.dumps(value))


def held(login: Login) -> str:
    """Everything a login keeps that is not its reveal, as text."""
    return repr(login) + json.dumps([login.source, login.ref, login.title, login.username, login.where, login.urls])


# -- 1Password --------------------------------------------------------------------------------------------------------


async def test_1password_lists_every_vault_once_in_a_while_and_reveals_one_item_by_id() -> None:
    listing = ("op", "item", "list", "--categories", "Login", "--format", "json")
    items = [{"id": "x1", "title": "Notes", "vault": "not a vault", "urls": "not a list"}]
    cli = FakeCli((listing, ok(items)), (("op", "item", "get", "x1", "--reveal", "--format", "json"), ok({})))
    now = [0.0]
    source = OnePassword("op", timeout=90.0, run=cli, clock=lambda: now[0])
    [login] = await source.logins("example.com")
    assert (login.ref, login.title, login.username, login.where, login.urls) == (
        "x1",
        "Notes",
        "",
        "1Password vault ?",
        (),
    )
    assert await source.logins("example.com") == [login]
    now[0] = passwords.LIST_TTL_S
    await source.logins("example.com")
    await source.logins("example.com", fresh=True)
    assert cli.calls.count(listing) == 3 and cli.timeouts[0] == 90.0
    revealed = await login.reveal()
    assert (revealed.username, revealed.password, revealed.totp) == ("", "", ""), "an item with no fields has none"


@pytest.mark.parametrize(
    ("answer", "refusal"),
    [
        (
            Ran(1, "", "[ERROR] account is not signed in"),
            "1Password's item list failed: [ERROR] account is not signed in",
        ),
        (Ran(6, ""), "1Password's item list failed: it exited with 6"),
        (Ran(0, "{oops"), "1Password's item list did not answer JSON"),
        (Ran(0, "{}"), "1Password's item list is not a list"),
    ],
)
async def test_1password_failing_says_why(answer: Ran, refusal: str) -> None:
    cli = FakeCli((("op", "item", "list", "--categories", "Login", "--format", "json"), answer))
    with pytest.raises(PasswordSourceError, match=re.escape(refusal)):
        await OnePassword("op", timeout=1.0, run=cli).logins("x")


# -- Bitwarden --------------------------------------------------------------------------------------------------------


async def test_bitwarden_keeps_nothing_secret_of_its_list_and_reveals_the_item_and_its_code() -> None:
    items = [
        {
            "id": "b1",
            "name": "Notes",
            "type": 1,
            "login": {"username": "ann", "password": PASSWORD, "totp": "otpauth://x", "uris": [{"uri": "example.com"}]},
        },
        {"id": "b2", "name": "Card", "type": 3, "card": {"number": "4111"}},
        {"id": "", "type": 1, "login": {}},
        {"id": "b3", "name": "Bare", "type": 1, "login": {"uris": "nope"}},
    ]
    cli = FakeCli(
        (("bw", "list", "items"), ok(items)),
        (("bw", "get", "item", "b1"), ok({"login": {"username": "ann", "password": PASSWORD, "totp": "otpauth://x"}})),
        (("bw", "get", "totp", "b1"), ok("123456\n")),
        (("bw", "get", "item", "b3"), ok({"login": {"username": "", "password": "p"}})),
    )
    source = Bitwarden("bw", timeout=5.0, run=cli)
    found = await source.logins("example.com")
    assert [(login.ref, login.urls) for login in found] == [("b1", ("example.com",)), ("b3", ())]
    assert all(PASSWORD not in held(login) for login in found)
    revealed = await found[0].reveal()
    assert (revealed.username, revealed.password, revealed.totp) == ("ann", PASSWORD, "123456")
    assert (await found[1].reveal()).totp == ""


async def test_bitwarden_locked_or_its_code_refused_says_why() -> None:
    cli = FakeCli((("bw", "list", "items"), Ran(1, "", "You are not logged in.")))
    with pytest.raises(PasswordSourceError, match=re.escape("Bitwarden's list items failed: You are not logged in.")):
        await Bitwarden("bw", timeout=5.0, run=cli).logins("x")
    cli.answers[("bw", "list", "items")] = ok({"not": "a list"})
    with pytest.raises(PasswordSourceError, match="is not a list"):
        await Bitwarden("bw", timeout=5.0, run=cli).logins("x")
    item = {"id": "b1", "name": "N", "type": 1, "login": {"totp": "x"}}
    cli.answers.update(
        {
            ("bw", "list", "items"): ok([item]),
            ("bw", "get", "item", "b1"): ok(item),
            ("bw", "get", "totp", "b1"): Ran(1, "", ""),
        }
    )
    [login] = await Bitwarden("bw", timeout=5.0, run=cli).logins("x")
    with pytest.raises(PasswordSourceError, match="Bitwarden's get totp failed: 1"):
        await login.reveal()


# -- a command --------------------------------------------------------------------------------------------------------


async def test_a_command_is_given_the_app_and_its_logins_keep_their_values_for_this_call_only() -> None:
    printed = [
        {"id": "c1", "title": "Notes", "username": "ann", "password": PASSWORD, "totp": "654321", "url": "example.com"},
        {"username": "bob", "password": "x", "urls": ["a.example.com", 3]},
        "skipped",
    ]
    cli = FakeCli((("/bin/logins", "com.example.notes"), ok(printed)))
    found = await Command("/bin/logins", timeout=5.0, run=cli).logins("com.example.notes")
    assert [(login.ref, login.title, login.where, login.urls) for login in found] == [
        ("c1", "Notes", "/bin/logins", ("example.com",)),
        ("2", "bob", "/bin/logins", ("a.example.com",)),
    ]
    assert all(PASSWORD not in held(login) for login in found)
    revealed = await found[0].reveal()
    assert (revealed.password, revealed.totp) == (PASSWORD, "654321")
    one = FakeCli((("/bin/logins", "x"), ok({"username": "solo", "password": "p"})))
    assert [login.username for login in await Command("/bin/logins", timeout=5.0, run=one).logins("x")] == ["solo"]


async def test_a_command_that_prints_no_login_is_refused() -> None:
    cli = FakeCli((("/bin/logins", "x"), ok("42")))
    with pytest.raises(PasswordSourceError, match="printed neither a login nor a list of them"):
        await Command("/bin/logins", timeout=5.0, run=cli).logins("x")
    assert await Command("/bin/logins", timeout=5.0, run=FakeCli((("/bin/logins", "x"), ok("")))).logins("x") == []


# -- which sources, and their CLIs ------------------------------------------------------------------------------------


def test_the_sources_are_made_in_order_and_a_missing_cli_is_said() -> None:
    made = passwords.sources(
        ("bitwarden", "command:/bin/logins", "1password"),
        timeout=9.0,
        find=lambda name, configured: f"/x/{name}",
    )
    assert [source.kind for source in made] == ["bitwarden", "command", "1password"]
    with pytest.raises(PasswordSourceError, match="Bitwarden's CLI was not found"):
        passwords.sources(("bitwarden",), timeout=9.0, find=lambda name, configured: None)


def test_a_cli_is_the_one_set_else_on_path_else_homebrews() -> None:
    assert find_program("op", "/custom/op", runnable=lambda path: True) == "/custom/op"
    assert find_program("op", "/custom/op", runnable=lambda path: False) is None
    assert find_program("op", "", which=lambda name: "/usr/bin/op", runnable=lambda path: False) == "/usr/bin/op"
    homebrew = find_program("op", "", which=lambda name: None, runnable=lambda path: path.startswith("/usr/local"))
    assert homebrew == "/usr/local/bin/op"
    assert find_program("op", "", which=lambda name: None, runnable=lambda path: False) is None


def test_credentials_never_print_their_values_and_are_emptied_once_used() -> None:
    credentials = Credentials("ann", PASSWORD, "123456")
    assert repr(credentials) == "Credentials(<hidden>)" and PASSWORD not in f"{credentials!r} {credentials}"
    credentials.forget()
    assert (credentials.username, credentials.password, credentials.totp) == ("", "", "")


def test_a_saved_website_or_app_is_read_for_its_host() -> None:
    assert host_of("https://Accounts.Example.com./login") == "accounts.example.com"
    assert host_of("android://com.example.notes") == "com.example.notes"
    assert host_of("example.com") == "example.com"
    assert host_of("http://[::1") == ""


# -- running a CLI ----------------------------------------------------------------------------------------------------


async def test_run_reads_what_a_program_prints_and_the_first_line_it_complains_with() -> None:
    script = "import sys; print('{\"a\": 1}'); sys.stderr.write('\\n  first problem\\nsecond\\n'); sys.exit(3)"
    ran = await run((sys.executable, "-c", script), 30.0)
    assert ran == Ran(3, '{"a": 1}\n', "first problem")


async def test_run_ends_a_program_that_outlasts_its_time_and_says_one_that_cannot_start() -> None:
    slow = await run((sys.executable, "-c", "import time; time.sleep(30)"), 0.2)
    assert slow == Ran(124, "", "it did not answer within 0.2s")
    missing = await run(("/nonexistent/password-cli",), 1.0)
    assert missing.code == 127 and missing.out == "" and missing.reason


# -- Keychain ---------------------------------------------------------------------------------------------------------

#: What ``security find-generic-password -s com.example.notes`` prints about an item (macOS 26), its password left out.
KEYCHAIN_ITEM = (
    'keychain: "/Users/ann/Library/Keychains/login.keychain-db"\n'
    "version: 512\n"
    'class: "genp"\n'
    "attributes:\n"
    '    "acct"<blob>="ann@example.com"\n'
    '    "labl"<blob>="Notes (test account)"\n'
    '    "svce"<blob>="com.example.notes"\n'
)


async def test_the_keychain_finds_a_login_by_the_app_it_is_saved_for_and_reads_its_password_only_to_type_it() -> None:
    find = ("/usr/bin/security", "find-generic-password", "-s", "com.example.notes")
    reveal = (*find, "-a", "ann@example.com", "-w")
    cli = FakeCli((find, ok(KEYCHAIN_ITEM)), (reveal, ok(PASSWORD + "\n")))
    (source,) = passwords.sources(["keychain"], timeout=30, run=cli)
    (login,) = await source.logins("com.example.notes")
    assert (login.source, login.title, login.username, login.where, login.urls) == (
        "keychain", "Notes (test account)", "ann@example.com", "Keychain", ("com.example.notes",),
    )  # fmt: skip
    assert PASSWORD not in held(login) and cli.calls == [find], "listed without its password"
    credentials = await login.reveal()
    assert (credentials.username, credentials.password) == ("ann@example.com", PASSWORD)
    assert cli.timeouts == [30, 30]


async def test_the_keychain_without_a_login_for_the_app_has_none_and_a_failure_says_why() -> None:
    find = ("/usr/bin/security", "find-generic-password", "-s", "com.example.mail")
    source = passwords.Keychain(timeout=5, run=FakeCli((find, Ran(44, "", "The specified item could not be found."))))
    assert await source.logins("com.example.mail") == []
    denied = passwords.Keychain(timeout=5, run=FakeCli((find, Ran(1, "", "Operation not permitted"))))
    with pytest.raises(PasswordSourceError, match="the Keychain could not be read: Operation not permitted"):
        await denied.logins("com.example.mail")
    bare = ("/usr/bin/security", "find-generic-password", "-s", "x")
    unnamed = '    "acct"<blob>="a"\n'
    gone = (*bare, "-a", "a", "-w")
    lost = passwords.Keychain(timeout=5, run=FakeCli((bare, ok(unnamed)), (gone, Ran(1, "", ""))))
    (login,) = await lost.logins("x")
    assert login.title == "x", "titled by its app when it has no label"
    with pytest.raises(PasswordSourceError, match="the Keychain did not give the password: exit 1"):
        await login.reveal()
    silent = passwords.Keychain(timeout=5, run=FakeCli((bare, Ran(2, "", ""))))
    with pytest.raises(PasswordSourceError, match="could not be read: exit 2"):
        await silent.logins("x")
