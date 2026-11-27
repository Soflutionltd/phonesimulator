# SPDX-License-Identifier: Apache-2.0
"""`sim_login`: an app signed in with a login from the person's password manager, which the agent never reads.

Offered while ``login.sources`` names a source (`platform.passwords`), tried in its order. The login is chosen and its
fields found by `core.login`, then typed by `AgentActions.type_hidden`, which never says what it types.

**The value never leaves PhoneSimulator.** The answer names the login used -- its title, where it is kept, its id -- and
which fields were filled, never a value; the agent's events say "Typing the password" and show ``••••``; nothing is
logged. Every later answer of every tool has the password and the code masked (`core.masking`), should the device show
or log them. The revealed values are dropped as soon as they are typed: CPython cannot wipe a string's memory, so they
are kept by nothing once the call returns, and the list of logins a source keeps between calls holds none.

**Refused** before the password manager is asked:

* in observe mode (``agent.observe``) -- a person signs in themselves there;
* on a real iPhone, iPad or Android phone, or in a macOS app, unless ``login.real_devices`` is on: they hold real data,
  where a simulator or an emulator holds what a developer made for it;
* while the device's screen is recorded, so a sign-in is not kept in a video;
* where the screen has no field the value may go into: a password only into a secure field.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from phonesimulator.config.model import SimConfig
from phonesimulator.connectors.base import Capability
from phonesimulator.core import login
from phonesimulator.core.actions import Hidden
from phonesimulator.core.given import GIVEN, GivenSource
from phonesimulator.core.instance import DeviceInstance
from phonesimulator.core.login import Form, LoginRefused
from phonesimulator.core.masking import CODE_S, PASSWORD_S
from phonesimulator.perception.snapshot import Snapshot
from phonesimulator.platform import passwords
from phonesimulator.platform.passwords import Credentials, Login, PasswordSourceError, Source
from phonesimulator.tools.context import Tool, ToolContext, flag_arg, make_tool, ready_device
from phonesimulator.tools.results import Result, ToolRefused, text
from phonesimulator.tools.schemas import LOGIN_INSTRUCTIONS, LOGIN_SOURCES, LOGIN_TEXT_MAX

#: The longest a ref may be.
REF_MAX = 16

_Key = tuple[tuple[str, ...], str, str, int]


def _text_arg(args: dict[str, Any], name: str, *, required: bool = False) -> str | None:
    value = args.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > LOGIN_TEXT_MAX or "\x00" in value:
        raise ToolRefused(f"{name} is text of 1 to {LOGIN_TEXT_MAX} characters")
    return value.strip()


def _ref_arg(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > REF_MAX:
        raise ToolRefused('field is a ref from sim_snapshot, such as "e5"')
    return value


def _real(instance: DeviceInstance) -> bool:
    """Whether the device holds real data: anything but a simulator, or an emulator on this Mac."""
    return not (instance.kind == "simulator" or (instance.kind == "android" and instance.connection is None))


class Logins:
    """The password managers `sim_login` asks, made once for each set of settings, so what one keeps between calls
    -- 1Password's list of logins, which holds nothing secret -- is used again."""

    def __init__(self, make: Callable[..., list[Source]] = passwords.sources) -> None:
        self._make = make
        self._made: dict[_Key, list[Source]] = {}

    def sources(self, config: SimConfig, only: str | None) -> list[Source]:
        key = (config.login_sources, config.login_onepassword_path, config.login_bitwarden_path, config.login_timeout)
        if key not in self._made:
            try:
                made = self._make(
                    config.login_sources,
                    onepassword_path=config.login_onepassword_path,
                    bitwarden_path=config.login_bitwarden_path,
                    timeout=float(config.login_timeout),
                )
            except PasswordSourceError as exc:
                raise ToolRefused(str(exc)) from None
            self._made = {key: made}
        made = self._made[key]
        if only is None:
            return made
        chosen = [source for source in made if source.kind == only]
        if not chosen:
            raise ToolRefused(f"{only} is not in login.sources ({', '.join(config.login_sources)})")
        return chosen

    async def run(self, args: dict[str, Any], ctx: ToolContext) -> Result:
        app = _text_arg(args, "app", required=True)
        assert app is not None
        account, item = _text_arg(args, "account"), _text_arg(args, "item")
        field = _ref_arg(args.get("field"))
        code, submit = flag_arg(args.get("code"), "code"), flag_arg(args.get("submit"), "submit")
        only = args.get("source")
        if only is not None and only not in LOGIN_SOURCES:
            raise ToolRefused(f"source is one of {', '.join(LOGIN_SOURCES)}")
        config = ctx.config
        given = only == GIVEN
        if given and item is None:
            raise ToolRefused('source "given" takes the item phonesimulator login handed over')
        if not given and not config.login_sources:
            raise ToolRefused("sim_login is off: login.sources names no password manager")
        if config.agent_observe:
            raise ToolRefused(
                "agents only observe here (agent.observe): sim_login is refused, and a person signs in themselves"
            )
        sources = [] if given else self.sources(config, only)
        instance = await ready_device(ctx)
        if _real(instance) and not config.login_real_devices:
            raise ToolRefused(
                f"{instance.name} is a real device or a macOS app, which holds real data: sim_login signs in only on "
                "simulators and emulators unless a person turns login.real_devices on"
            )
        if instance.recording is not None:
            raise ToolRefused("the screen is being recorded: stop the recording (sim_record stop) before signing in")
        snapshot = await ctx.actions.screen(instance, ctx.caller, max_elements=ctx.config.snapshot_max_elements)
        form, snapshot = await self._form(ctx, instance, snapshot, field, code=code)
        if given:
            taken = ctx.given.take(ctx.caller.scope.id, app, item) if ctx.given is not None and item else None
            if taken is None:
                raise ToolRefused(f"no login was handed over for {app} under that item, or it was used or expired")
            sources = [GivenSource(taken)]
        try:
            chosen = await login.choose(sources, app, account=account, item=item)
        except LoginRefused as exc:
            raise ToolRefused(str(exc)) from None
        filled = await self._fill(ctx, instance, chosen, form, snapshot, account=account, code=code, submit=submit)
        return self._answer(chosen, form, filled, submit=submit)

    @staticmethod
    async def _form(
        ctx: ToolContext, instance: DeviceInstance, snapshot: Snapshot, field: str | None, *, code: bool
    ) -> tuple[Form, Snapshot]:
        """The fields the login goes into -- after a tap on the password's field when no field is secure yet, as a
        Flutter app's is only once it has the focus (`login.to_focus`) -- and the screen they were found on."""
        try:
            return (login.code_form(snapshot, field) if code else login.password_form(snapshot, field)), snapshot
        except LoginRefused as exc:
            focus = None if code else login.to_focus(snapshot, field)
            if focus is None or focus.ref is None:
                raise ToolRefused(str(exc)) from None
            refused = str(exc)
        await ctx.actions.act(instance, ctx.caller, [{"tap": focus.ref}], snapshot="none")
        snapshot = await ctx.actions.screen(instance, ctx.caller, max_elements=ctx.config.snapshot_max_elements)
        # Only the field tapped, now secure, takes the password: never another one the screen happens to show.
        now = [
            element
            for element in snapshot.elements
            if element.ref is not None and element.kind == login.SECURE_FIELD and element.holds(focus.x, focus.y)
        ]
        if len(now) != 1 or now[0].ref is None:
            raise ToolRefused(refused)
        return login.password_form(snapshot, now[0].ref), snapshot

    async def _fill(
        self,
        ctx: ToolContext,
        instance: DeviceInstance,
        chosen: Login,
        form: Form,
        snapshot: Snapshot,
        *,
        account: str | None,
        code: bool,
        submit: bool,
    ) -> tuple[list[tuple[str, str]], str]:
        """Reveal the login, type it into the form's fields and forget it: which fields took what, by ref, and what
        the agent should know of how it went in."""
        assert ctx.secrets is not None, "the registry masks every answer"
        try:
            credentials = await chosen.reveal()
        except PasswordSourceError as exc:
            raise ToolRefused(f"{chosen.source}: {exc}") from None
        try:
            entries = self._entries(ctx, credentials, chosen, form, snapshot, account=account, code=code)
            typed = await ctx.actions.type_hidden(
                instance,
                ctx.caller,
                entries,
                submit=submit,
                lead_ms=ctx.config.cursor_lead_ms if ctx.config.agent_cursor else 0,
                max_elements=ctx.config.snapshot_max_elements,
            )
            filled = [(entry.what, entry.ref) for entry in entries]
            del entries
        finally:
            credentials.forget()
        notes = ""
        if typed.refused:
            notes += (
                f" It was pasted, and {instance.runtime} refuses a paste it did not ask for: check the field, or set "
                "device.typing to auto, which types with the Mac's own keyboard layout."
            )
        if typed.pasteboard_left:
            notes += " The device's pasteboard could not be emptied after the paste: copy something else on it."
        return filled, notes

    @staticmethod
    def _entries(
        ctx: ToolContext,
        credentials: Credentials,
        chosen: Login,
        form: Form,
        snapshot: Snapshot,
        *,
        account: str | None,
        code: bool,
    ) -> Sequence[Hidden]:
        """What to type where, refused before anything is typed when the login is not what was asked for."""
        assert ctx.secrets is not None
        named = login.label(chosen)
        if account is not None and not login.same_account(credentials.username, account):
            raise ToolRefused(f"the saved login {named} holds another username than {account}; nothing was typed")
        if code:
            if not credentials.totp:
                raise ToolRefused(
                    f"the saved login {named} has no one-time code: ask the person for the code the app asks for"
                )
            ctx.secrets.hide(credentials.totp, CODE_S)
            assert form.secret.ref is not None
            return [Hidden(form.secret.ref, credentials.totp, "one-time code")]
        if not credentials.password:
            raise ToolRefused(f"the saved login {named} has no password")
        ctx.secrets.hide(credentials.password, PASSWORD_S)
        entries: list[Hidden] = []
        username = credentials.username or chosen.username
        if form.username is not None and form.username.ref is not None and credentials.username:
            if not login.same_account(form.username.value or "", credentials.username):
                entries.append(Hidden(form.username.ref, credentials.username, "username"))
        elif form.username is None:
            try:
                login.check_shown(snapshot, username)
            except LoginRefused as exc:
                raise ToolRefused(str(exc)) from None
        assert form.secret.ref is not None
        entries.append(Hidden(form.secret.ref, credentials.password, "password"))
        return entries

    @staticmethod
    def _answer(chosen: Login, form: Form, filled: tuple[list[tuple[str, str]], str], *, submit: bool) -> Result:
        typed, notes = filled
        fields = ", ".join(f"the {what} into {ref}" for what, ref in typed)
        if form.username is not None and not any(what == "username" for what, _ref in typed):
            fields += f" ({form.username.ref}, the username's field, was left as it was)"
        then = ", then pressed return" if submit else ""
        said = f"Used the {chosen.source} login {login.label(chosen)}: typed {fields}{then}.{notes}"
        said += " Call sim_snapshot to see what the app answered."
        return text(
            said,
            data={
                "source": chosen.source,
                "item": {"id": chosen.ref, "title": chosen.title, "where": chosen.where},
                "filled": [what for what, _ref in typed],
                "submitted": submit,
            },
        )


class LoginToolProvider:
    """`sim_login`: offered while ``login.sources`` names a password manager."""

    def __init__(self, logins: Logins | None = None) -> None:
        self.logins = logins or Logins()
        self.tools: tuple[Tool, ...] = (make_tool("sim_login", (Capability.INPUT_TOUCH,), self.logins.run),)

    def offered(self, config: SimConfig) -> bool:
        return bool(config.login_sources)

    def instructions(self, config: SimConfig) -> str:
        return LOGIN_INSTRUCTIONS if config.login_sources else ""
