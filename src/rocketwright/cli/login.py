# SPDX-License-Identifier: Apache-2.0
"""``rocketwright login``: sign the project's app in with a login from the person's password manager, asked from here.

`sim_login` asks the password manager from the daemon. Where the daemon runs inside a sandbox that forbids what the
password manager's CLI needs -- an MCP client that starts its servers under a macOS sandbox profile, say -- it cannot.
This command asks it in the person's own terminal instead: it finds the login as `sim_login` would (`core.login`), from
``login.sources`` or ``--source``, hands it to the daemon for one use (`core.given`), and has `sim_login` type it --
the same fields found, the password only into a secure field, masked in every answer. Nothing is printed but which
login was used and what was filled.

No value ever goes in a command line: the login is read from the password manager, and passed to the daemon in the
body of an admin request on this Mac.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from rocketwright.cli.context import CliContext
from rocketwright.cli.devices import SCOPE_HELP
from rocketwright.core import login
from rocketwright.core.given import GIVEN
from rocketwright.core.login import LoginRefused
from rocketwright.mcp.launcher import adopt_main_device, ensure_daemon
from rocketwright.platform import passwords
from rocketwright.platform.passwords import Credentials, Login, PasswordSourceError, Source

#: How long the daemon is given to find the fields and type the login.
CALL_TIMEOUT_S = 120.0


def register(commands: Any) -> None:
    command = commands.add_parser(
        "login", help="sign the project's app in with a login from your password manager, asked from this terminal"
    )
    command.add_argument("app", help="the website or the app's bundle id the login is saved for")
    command.add_argument("--account", help="the username or e-mail of the account; only a login for it is used")
    command.add_argument("--item", help="the id or title of the saved login, when several match")
    command.add_argument(
        "--source",
        action="append",
        default=[],
        help="where logins come from, as login.sources names them: 1password, bitwarden or command:/path; "
        "repeatable (default: login.sources)",
    )
    command.add_argument("--field", help="the ref of the password field, from sim_snapshot (default: the only one)")
    command.add_argument("--code", action="store_true", help="type the login's one-time code instead of its password")
    command.add_argument("--submit", action="store_true", help="press return once it is typed")
    command.add_argument("--scope", help=SCOPE_HELP)
    command.set_defaults(handler=run)


async def _found(sources: list[Source], args: argparse.Namespace) -> tuple[Login, Credentials]:
    chosen = await login.choose(sources, args.app, account=args.account, item=args.item)
    return chosen, await chosen.reveal()


def run(args: argparse.Namespace, ctx: CliContext) -> int:
    scope = ctx.scope(args.scope)
    config = ctx.config().get(scope)
    entries = tuple(args.source) or config.login_sources
    if not entries:
        ctx.complain(
            "rocketwright: name where logins come from: --source 1password (or bitwarden, or command:/path), or "
            "`rocketwright config set login.sources '[\"1password\"]'`"
        )
        return 2
    try:
        sources = passwords.sources(
            entries,
            onepassword_path=config.login_onepassword_path,
            bitwarden_path=config.login_bitwarden_path,
            timeout=float(config.login_timeout),
        )
        chosen, credentials = asyncio.run(_found(sources, args))
    except (LoginRefused, PasswordSourceError) as exc:
        ctx.complain(f"rocketwright: {exc}")
        return 1
    client = ctx.client()
    try:
        ensure_daemon(client, ctx.start_daemon)
        if args.scope is None:
            adopt_main_device(client, scope, ctx.cwd)
        handed = {
            "scope": scope.id,
            "app": args.app,
            "title": chosen.title,
            "username": credentials.username,
            "password": credentials.password,
            "totp": credentials.totp,
        }
        item = str(client.post("/api/v1/admin/logins", handed)["item"])
        handed.clear()
    finally:
        credentials.forget()
    asked: dict[str, Any] = {"app": args.app, "source": GIVEN, "item": item, "submit": args.submit, "code": args.code}
    if args.account:
        asked["account"] = args.account
    if args.field:
        asked["field"] = args.field
    token_id, token = client.mint_agent_token(scope.id, [], "rocketwright login")
    try:
        answer = client.call_tool(token, "sim_login", asked, timeout=CALL_TIMEOUT_S)
    finally:
        client.revoke(token_id)
    said = "\n".join(part.get("text", "") for part in answer.get("content") or [] if isinstance(part, dict))
    if answer.get("isError"):
        ctx.complain(f"rocketwright: {said}")
        return 1
    ctx.say(said)
    return 0
