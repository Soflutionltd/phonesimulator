# SPDX-License-Identifier: Apache-2.0
"""The password managers `sim_login` reads a saved login from: 1Password's CLI, Bitwarden's, the macOS Keychain, or a
program of the person's own that prints logins as JSON -- run here, and nowhere else.

**What is listed holds no secret.** A source first lists its logins -- an id, a title, the vault, the username and
the websites or apps saved with each -- and only the one chosen is revealed, once, for the fill (`Login.reveal`).
1Password's list says nothing secret; Bitwarden's and a command's carry passwords, which are dropped as the list is
read, so what is kept between calls (1Password's list, for `LIST_TTL_S`) never holds one.

**Every vault is searched**: no vault is named, so each source lists every login its CLI can reach.

**Nothing secret travels in an argv, an environment variable or a log.** A login is asked for by its id; a revealed
password comes back on the CLI's standard output, read into this process and nowhere else. What a CLI writes to its
standard error -- why it failed -- is kept to its first line, which never holds a secret a CLI was asked to reveal.

1Password's CLI reaches the vaults through the 1Password app's integration: the app asks the person to approve with
Touch ID, so a call may wait for them, `login.timeout` at most.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from phonesimulator.platform.process import kill_and_reap

#: The CLIs' names, and where Homebrew puts them when the daemon's PATH does not reach there.
ONEPASSWORD = "op"
BITWARDEN = "bw"
#: macOS's Keychain CLI, always at this path.
SECURITY = "/usr/bin/security"
#: What ``security find-generic-password`` answers when no password is saved under the service.
NOT_IN_KEYCHAIN = 44
HOMEBREW_BINS = ("/opt/homebrew/bin", "/usr/local/bin")
#: How long 1Password's list of logins -- which holds nothing secret -- is used again before it is read anew.
LIST_TTL_S = 600.0
#: The most of a CLI's output read: a vault's list as JSON.
OUTPUT_MAX = 32 << 20
#: The longest a reason a CLI gave for failing is said.
REASON_MAX = 200


class PasswordSourceError(Exception):
    """A password manager could not be asked: not installed, locked, refused, or it answered nothing readable."""


@dataclass(frozen=True)
class Ran:
    """What a CLI answered: its exit code, its standard output, and the first line of its standard error."""

    code: int
    out: str
    reason: str = ""


#: How a CLI is run: an argv and a timeout in, what it answered out -- `run`, or a test's stand-in.
Run = Callable[[Sequence[str], float], Awaitable[Ran]]


async def run(argv: Sequence[str], timeout: float) -> Ran:
    """Run a password manager's CLI, read what it prints, and end it when it outlasts `timeout`. Never raises: a CLI
    that cannot start answers 127, and one that took too long 124."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=OUTPUT_MAX,
        )
    except OSError as exc:
        return Ran(127, "", exc.strerror or "it could not be started")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, TimeoutError):
        await kill_and_reap(proc)
        return Ran(124, "", f"it did not answer within {timeout:g}s")
    reason = next((line.strip() for line in err.decode(errors="replace").splitlines() if line.strip()), "")
    return Ran(proc.returncode or 0, out.decode(errors="replace"), reason[:REASON_MAX])


def find_program(
    name: str,
    configured: str,
    *,
    which: Callable[[str], str | None] = shutil.which,
    runnable: Callable[[str], bool] = lambda path: os.access(path, os.X_OK),
) -> str | None:
    """The CLI to run: the one the settings name, else the one on PATH, else Homebrew's; None when there is none."""
    if configured:
        return configured if runnable(configured) else None
    found = which(name)
    if found:
        return found
    return next((path for folder in HOMEBREW_BINS if runnable(path := str(Path(folder) / name))), None)


class Credentials:
    """A revealed login: what is typed. Never printed whole -- its repr says nothing -- and emptied once used."""

    __slots__ = ("password", "totp", "username")

    def __init__(self, username: str, password: str, totp: str = "") -> None:
        self.username = username
        self.password = password
        self.totp = totp

    def __repr__(self) -> str:
        return "Credentials(<hidden>)"

    def forget(self) -> None:
        """Drop the values, so nothing here keeps them once they are typed."""
        self.username = self.password = self.totp = ""


Reveal = Callable[[], Awaitable[Credentials]]


@dataclass(frozen=True)
class Login:
    """A login a source holds, described by what is not secret; `reveal` asks the source for its values."""

    source: str
    #: The id the source knows it by.
    ref: str
    title: str
    username: str
    #: Where it is kept: a 1Password vault's name, ``Bitwarden``, or the command's path.
    where: str
    #: The websites and apps saved with it, as saved: ``https://example.com``, ``android://com.example``.
    urls: tuple[str, ...]
    reveal: Reveal = field(repr=False, compare=False)


class Source:
    """A password manager, asked for the logins it holds."""

    kind: str

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        """The logins it holds -- for a command, those it gives for `target` -- with nothing secret in them."""
        raise NotImplementedError


def _json(ran: Ran, what: str) -> Any:
    """A CLI's output read as JSON, or why it cannot be."""
    if ran.code != 0:
        raise PasswordSourceError(f"{what} failed: {ran.reason or f'it exited with {ran.code}'}")
    try:
        return json.loads(ran.out or "null")
    except ValueError:
        raise PasswordSourceError(f"{what} did not answer JSON") from None


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


class OnePassword(Source):
    """1Password, through its CLI and the 1Password app's integration: every vault the account reaches."""

    kind = "1password"

    def __init__(
        self, program: str, *, timeout: float, run: Run = run, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._program, self._timeout, self._run, self._clock = program, timeout, run, clock
        self._listed: tuple[float, list[Login]] | None = None

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        if self._listed is not None and not fresh and self._clock() - self._listed[0] < LIST_TTL_S:
            return self._listed[1]
        argv = (self._program, "item", "list", "--categories", "Login", "--format", "json")
        listed = _json(await self._run(argv, self._timeout), "1Password's item list")
        if not isinstance(listed, list):
            raise PasswordSourceError("1Password's item list is not a list")
        found = [login for item in listed if (login := self._login(item)) is not None]
        self._listed = (self._clock(), found)
        return found

    def _login(self, item: object) -> Login | None:
        if not isinstance(item, dict) or not _text(item.get("id")):
            return None
        vault = item.get("vault") if isinstance(item.get("vault"), dict) else {}
        assert isinstance(vault, dict)
        urls = item.get("urls") if isinstance(item.get("urls"), list) else []
        assert isinstance(urls, list)
        ref, vault_id = _text(item["id"]), _text(vault.get("id"))

        async def reveal() -> Credentials:
            argv = [self._program, "item", "get", ref, "--reveal", "--format", "json"]
            if vault_id:
                argv[4:4] = ["--vault", vault_id]
            got = _json(await self._run(argv, self._timeout), "1Password's item get")
            fields = got.get("fields") if isinstance(got, dict) else None
            fields = [one for one in fields if isinstance(one, dict)] if isinstance(fields, list) else []
            by_purpose = {_text(one.get("purpose")): _text(one.get("value")) for one in fields}
            totp = next((_text(one.get("totp")) for one in fields if one.get("type") == "OTP"), "")
            return Credentials(by_purpose.get("USERNAME", ""), by_purpose.get("PASSWORD", ""), totp)

        return Login(
            source=self.kind,
            ref=ref,
            title=_text(item.get("title")),
            username=_text(item.get("additional_information")),
            where=f"1Password vault {_text(vault.get('name')) or vault_id or '?'}",
            urls=tuple(_text(url.get("href")) for url in urls if isinstance(url, dict) and _text(url.get("href"))),
            reveal=reveal,
        )


class Bitwarden(Source):
    """Bitwarden, through its CLI, unlocked by the person (``BW_SESSION`` in the daemon's environment)."""

    kind = "bitwarden"

    def __init__(self, program: str, *, timeout: float, run: Run = run) -> None:
        self._program, self._timeout, self._run = program, timeout, run

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        # Its list carries every password: read here, kept by none of what is returned, and never kept between calls.
        listed = _json(await self._run((self._program, "list", "items"), self._timeout), "Bitwarden's list items")
        if not isinstance(listed, list):
            raise PasswordSourceError("Bitwarden's list items is not a list")
        found = [login for item in listed if (login := self._login(item)) is not None]
        del listed
        return found

    def _login(self, item: object) -> Login | None:
        if not isinstance(item, dict) or item.get("type") != 1 or not isinstance(item.get("login"), dict):
            return None
        ref, login = _text(item.get("id")), item["login"]
        if not ref:
            return None
        uris = login.get("uris") if isinstance(login.get("uris"), list) else []
        assert isinstance(uris, list)

        async def reveal() -> Credentials:
            got = _json(await self._run((self._program, "get", "item", ref), self._timeout), "Bitwarden's get item")
            saved = got.get("login") if isinstance(got, dict) and isinstance(got.get("login"), dict) else {}
            assert isinstance(saved, dict)
            totp = ""
            if _text(saved.get("totp")):
                ran = await self._run((self._program, "get", "totp", ref), self._timeout)
                if ran.code != 0:
                    raise PasswordSourceError(f"Bitwarden's get totp failed: {ran.reason or ran.code}")
                totp = ran.out.strip()
            return Credentials(_text(saved.get("username")), _text(saved.get("password")), totp)

        return Login(
            source=self.kind,
            ref=ref,
            title=_text(item.get("name")),
            username=_text(login.get("username")),
            where="Bitwarden",
            urls=tuple(_text(uri.get("uri")) for uri in uris if isinstance(uri, dict) and _text(uri.get("uri"))),
            reveal=reveal,
        )


class Command(Source):
    """A program of the person's own, run with the app or website as its one argument, that prints the logins for
    it as JSON: a list of ``{"id", "title", "username", "password", "totp", "url"}`` -- or one of them."""

    kind = "command"

    def __init__(self, program: str, *, timeout: float, run: Run = run) -> None:
        self._program, self._timeout, self._run = program, timeout, run

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        printed = _json(await self._run((self._program, target), self._timeout), self._program)
        if printed is None:
            # Nothing printed: no login for it.
            return []
        entries = printed if isinstance(printed, list) else [printed] if isinstance(printed, dict) else None
        if entries is None:
            raise PasswordSourceError(f"{self._program} printed neither a login nor a list of them")
        found = [self._login(index, entry) for index, entry in enumerate(entries, start=1) if isinstance(entry, dict)]
        del printed, entries
        return found

    def _login(self, index: int, entry: dict[str, Any]) -> Login:
        # The values are kept only by this login's reveal, for the call that asked: a command's list is not kept.
        credentials = (_text(entry.get("username")), _text(entry.get("password")), _text(entry.get("totp")))
        urls = entry.get("urls") if isinstance(entry.get("urls"), list) else [entry.get("url")]
        assert isinstance(urls, list)

        async def reveal() -> Credentials:
            return Credentials(*credentials)

        return Login(
            source=self.kind,
            ref=_text(entry.get("id")) or str(index),
            title=_text(entry.get("title")) or credentials[0],
            username=credentials[0],
            where=self._program,
            urls=tuple(url for url in (_text(one) for one in urls) if url),
            reveal=reveal,
        )


def _attribute(listing: str, name: str) -> str:
    """One attribute of what ``security find-generic-password`` prints about an item: ``"acct"<blob>="ann@…"``."""
    marker = f'"{name}"<blob>="'
    for line in listing.splitlines():
        start = line.find(marker)
        if start >= 0 and line.rstrip().endswith('"'):
            return line[start + len(marker) : line.rstrip().rfind('"')]
    return ""


class Keychain(Source):
    """The macOS Keychain: a generic password saved with the app -- its bundle id or website -- as its service and the
    account's username as its account (``security add-generic-password -s com.example.notes -a ann@example.com -w``).
    A login is found by its service alone, and its password read only to be typed. Reached only by a process that may
    run ``security``: ``phonesimulator login`` in your terminal, not a daemon started inside a sandbox that forbids it."""

    kind = "keychain"

    def __init__(self, *, timeout: float, run: Run = run, program: str = SECURITY) -> None:
        self._timeout = timeout
        self._run = run
        self._program = program

    async def logins(self, target: str, *, fresh: bool = False) -> list[Login]:
        ran = await self._run((self._program, "find-generic-password", "-s", target), self._timeout)
        if ran.code == NOT_IN_KEYCHAIN:
            return []
        if ran.code != 0:
            raise PasswordSourceError(f"the Keychain could not be read: {ran.reason or f'exit {ran.code}'}")
        account = _attribute(ran.out, "acct")
        title = _attribute(ran.out, "labl") or target

        async def reveal() -> Credentials:
            argv = (self._program, "find-generic-password", "-s", target, "-a", account, "-w")
            got = await self._run(argv, self._timeout)
            if got.code != 0:
                raise PasswordSourceError(f"the Keychain did not give the password: {got.reason or f'exit {got.code}'}")
            return Credentials(account, got.out.removesuffix("\n"))

        return [Login(self.kind, f"{target}/{account}", title, account, "Keychain", (target,), reveal)]


def sources(
    entries: Sequence[str],
    *,
    onepassword_path: str = "",
    bitwarden_path: str = "",
    timeout: float,
    run: Run = run,
    find: Callable[[str, str], str | None] = find_program,
) -> list[Source]:
    """The sources ``login.sources`` names, in its order. A CLI that is not installed is refused, saying so."""
    found: list[Source] = []
    for entry in entries:
        if entry == "1password":
            program = find(ONEPASSWORD, onepassword_path)
            if program is None:
                raise PasswordSourceError(
                    "1Password's CLI was not found: install it (brew install 1password-cli), turn on Integrate with "
                    "1Password CLI in the 1Password app's Developer settings, or set login.onepassword_path"
                )
            found.append(OnePassword(program, timeout=timeout, run=run))
        elif entry == "bitwarden":
            program = find(BITWARDEN, bitwarden_path)
            if program is None:
                raise PasswordSourceError(
                    "Bitwarden's CLI was not found: install it (brew install bitwarden-cli) or set login.bitwarden_path"
                )
            found.append(Bitwarden(program, timeout=timeout, run=run))
        elif entry == "keychain":
            found.append(Keychain(timeout=timeout, run=run))
        else:
            found.append(Command(entry.removeprefix("command:"), timeout=timeout, run=run))
    return found


def host_of(url: str) -> str:
    """The host a saved website names, lower-cased; an app id saved as ``android://com.example`` gives its id."""
    text = url.strip()
    try:
        host = urlsplit(text if "://" in text else f"https://{text}").hostname
    except ValueError:
        return ""
    return (host or "").lower().rstrip(".")
