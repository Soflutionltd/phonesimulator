# SPDX-License-Identifier: Apache-2.0
"""Which saved login signs an app in, and which of the screen's fields take it -- for `sim_login`.

**The login is the one for this app, and for the account asked for.** A login matches an app when one of the
websites or apps saved with it names the app: the same site as a website given (``accounts.example.com`` is
example.com), the app's bundle id or package name itself (``android://com.example.notes``), or the site its id is
the reverse of (``com.example.notes`` is example.com). With ``account`` -- the username or e-mail address of the
account the person named -- a login for any other account is never used, even when it is the only one; one that turns
out, once revealed, to hold another username is refused before anything is typed. Several logins matching, with no
``item`` to choose between them, is refused with each one's id: guessing would be a wrong password on someone's
account.

**Only a secure field takes a password.** The password goes into the field accessibility calls secure -- the one the
agent named, or the only one on screen -- and the username into the text field just before it, when there is one. A
one-time code (``code``) goes only into the field the agent names, or the one field on screen that reads like one. A
screen that asks for a password with no username field, but shows another account's address, is refused: the
password would be tried on that account.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from rocketwright.perception.snapshot import Element, Snapshot
from rocketwright.platform.passwords import Login, PasswordSourceError, Source, host_of

#: The kinds of snapshot line a username, and a one-time code, may be typed into.
TEXT_FIELD = "field"
SECURE_FIELD = "secure"
CODE_FIELDS = frozenset({TEXT_FIELD, SECURE_FIELD})
#: What a field for a one-time code reads like, by its label or identifier.
_CODE = re.compile(
    r"one[- ]?time|\botp\b|totp|\b2fa\b|\bmfa\b|verification|security code|\bcode\b|c[oó]digo|authenticat",
    re.IGNORECASE,
)
_ADDRESS = re.compile(r"[\w.%+-]+@[\w-]+(?:\.[\w-]+)+", re.UNICODE)
#: Second-level labels under which a country's sites are registered: example.co.uk is example's.
_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "gov", "gouv", "ac", "edu"})
#: The most logins a refusal lists.
LISTED_MAX = 8


class LoginRefused(Exception):
    """Why no login is used, or no field filled -- said so the agent can tell the person, or call again rightly."""


def site_of(host: str) -> str:
    """The registrable domain of a host, near enough to match a saved website: accounts.example.com is example.com."""
    name = host.strip().lower().rstrip(".")
    labels = name.split(".")
    if len(labels) < 2 or ":" in name or name.replace(".", "").isdigit():
        return name
    country = len(labels) > 2 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL
    return ".".join(labels[-3:] if country else labels[-2:])


@dataclass(frozen=True)
class Wanted:
    """The app or website a login is for: the sites it may be saved under, and the app ids it may be saved as."""

    sites: frozenset[str]
    ids: frozenset[str]

    @classmethod
    def of(cls, app: str) -> Wanted:
        text = app.strip().lower()
        sites = {site_of(host_of(text))}
        ids: set[str] = set()
        if "://" not in text and "/" not in text and "." in text:
            # A bundle id or package name: itself, and the site it is the reverse of.
            ids.add(text)
            sites.add(site_of(".".join(reversed(text.split(".")))))
        return cls(frozenset(site for site in sites if site), frozenset(ids))

    def matches(self, login: Login) -> bool:
        for url in login.urls:
            saved = url.strip().lower()
            host = host_of(saved)
            if saved in self.ids or host in self.ids or (host and site_of(host) in self.sites):
                return True
        return False


def label(login: Login, *, username: bool = True) -> str:
    """How a refusal or an answer names a login: its title, where it is kept and its id."""
    parts = [login.username] if username and login.username else []
    return f'"{login.title}" ({", ".join([*parts, login.where, f"id {login.ref}"])})'


def _listed(logins: Sequence[Login], *, username: bool = True) -> str:
    named = [label(login, username=username) for login in logins[:LISTED_MAX]]
    more = f" and {len(logins) - LISTED_MAX} more" if len(logins) > LISTED_MAX else ""
    return "; ".join(named) + more


def same_account(username: str, account: str) -> bool:
    return username.strip().casefold() == account.strip().casefold()


async def choose(sources: Sequence[Source], app: str, *, account: str | None, item: str | None) -> Login:
    """The login to sign `app` in with, from the first source that has one: the one `item` names, else the only one
    for the app -- for `account` alone when it is given."""
    wanted = Wanted.of(app)
    others: list[Login] = []
    for source in sources:
        try:
            found = await _matching(source, app, wanted, item)
        except PasswordSourceError as exc:
            raise LoginRefused(f"{source.kind}: {exc}") from None
        if account is not None:
            mine = [login for login in found if same_account(login.username, account)]
            others += [login for login in found if not same_account(login.username, account)]
            found = mine
        if len(found) > 1:
            raise LoginRefused(
                f"several saved logins match {app}: pass item with the id of the one to use -- {_listed(found)}"
            )
        if found:
            return found[0]
    tried = ", ".join(source.kind for source in sources)
    if account is not None:
        elsewhere = f" Found for other accounts: {_listed(others, username=False)}." if others else ""
        raise LoginRefused(
            f"no saved login for {account} on {app} in {tried}; nothing was typed.{elsewhere} Ask the person: never "
            "sign in with another account"
        )
    if item is not None:
        raise LoginRefused(f"no saved login {item!r} for {app} in {tried}")
    raise LoginRefused(
        f"no saved login for {app} in {tried}: save the app's website, or its bundle id as android://<id>, with the "
        "login in the password manager, or pass item"
    )


async def _matching(source: Source, app: str, wanted: Wanted, item: str | None) -> list[Login]:
    """The source's logins for the app -- the one `item` names, when it does, refused if it is for another app.
    A list kept from before that has none is read again, in case the login was saved since."""
    for fresh in (False, True):
        logins = await source.logins(app, fresh=fresh)
        if item is not None:
            named = [login for login in logins if login.ref == item or login.title.casefold() == item.casefold()]
            if named:
                here = [login for login in named if wanted.matches(login)]
                if not here:
                    saved = ", ".join(sorted({host_of(url) or url for url in named[0].urls})) or "no website or app"
                    raise LoginRefused(
                        f"the saved login {label(named[0])} is for {saved}, not {app}; nothing was typed. Save {app} "
                        "with it in the password manager if it is the same account"
                    )
                return here
        else:
            found = [login for login in logins if wanted.matches(login)]
            if found:
                return found
    return []


@dataclass(frozen=True)
class Form:
    """The fields a login goes into: the username's, when the screen has one, and the password's -- or the code's."""

    username: Element | None
    secret: Element


def _named(element: Element) -> str:
    return f'{element.ref} "{element.label}"' if element.label else str(element.ref)


def password_form(snapshot: Snapshot, field: str | None) -> Form:
    """The password field -- the one `field` names, which must be secure, else the only secure one on screen -- and
    the text field just before it, for the username."""
    elements = [element for element in snapshot.elements if element.ref is not None]
    if field is not None:
        secret = snapshot.element(field)
        if secret is None:
            raise LoginRefused(f"{field} is not on screen now; call sim_snapshot to see what is")
        if secret.kind != SECURE_FIELD:
            raise LoginRefused(
                f"{_named(secret)} is a {secret.kind}, not a secure field: a password is typed only where it is "
                "hidden as it is typed. Name the password field, or pass code: true for a one-time code's field"
            )
    else:
        secure = [element for element in elements if element.kind == SECURE_FIELD]
        if not secure:
            raise LoginRefused("no password field is on screen: open the sign-in form first, then call sim_login")
        if len(secure) > 1:
            named = ", ".join(_named(element) for element in secure)
            raise LoginRefused(f"several password fields are on screen ({named}): pass field with the one to fill")
        secret = secure[0]
    before = elements[: elements.index(secret)] if secret in elements else []
    username = next((element for element in reversed(before) if element.kind == TEXT_FIELD), None)
    return Form(username, secret)


def to_focus(snapshot: Snapshot, field: str | None) -> Element | None:
    """The text field to tap before a password form is looked for again, when none is secure yet: Flutter, for one,
    says its password field is secure only once it has the focus. The field named, when it is a plain text field; else,
    with no secure field on screen and two text fields or more, the last -- a password's comes after its username's.
    Tapping only focuses it: the password still goes nowhere but a field that then says it is secure."""
    if field is not None:
        named = snapshot.element(field)
        return named if named is not None and named.kind == TEXT_FIELD else None
    elements = [element for element in snapshot.elements if element.ref is not None]
    if any(element.kind == SECURE_FIELD for element in elements):
        return None
    texts = [element for element in elements if element.kind == TEXT_FIELD]
    return texts[-1] if len(texts) >= 2 else None


def code_form(snapshot: Snapshot, field: str | None) -> Form:
    """The field a one-time code goes into: the one `field` names, else the only one on screen that reads like one."""
    if field is not None:
        secret = snapshot.element(field)
        if secret is None:
            raise LoginRefused(f"{field} is not on screen now; call sim_snapshot to see what is")
        if secret.kind not in CODE_FIELDS:
            raise LoginRefused(f"{_named(secret)} is a {secret.kind}, not a field a code can be typed into")
        return Form(None, secret)
    codes = [
        element
        for element in snapshot.elements
        if element.ref is not None
        and element.kind in CODE_FIELDS
        and _CODE.search(f"{element.label} {element.identifier} {element.value or ''}")
    ]
    if len(codes) != 1:
        found = f"several ({', '.join(_named(element) for element in codes)})" if codes else "none"
        raise LoginRefused(f"pass field with the one-time code's field: {found} read like one")
    return Form(None, codes[0])


def accounts_shown(snapshot: Snapshot) -> set[str]:
    """The e-mail addresses the screen shows, lower-cased: which account a password-only step is for."""
    found: set[str] = set()
    for element in snapshot.elements:
        for text in (element.label, element.value or "", *element.says):
            found.update(address.casefold() for address in _ADDRESS.findall(text))
    return found


def check_shown(snapshot: Snapshot, username: str) -> None:
    """Refuse a password-only step that shows another address than the login's -- when the login's username is an
    address, which it can then be told from."""
    shown = accounts_shown(snapshot)
    if "@" in username and shown and username.strip().casefold() not in shown:
        listed = ", ".join(sorted(shown)[:3])
        raise LoginRefused(
            f"the screen asks for the password of {listed}, and the saved login is another account; nothing was typed"
        )
