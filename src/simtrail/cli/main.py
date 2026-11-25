# SPDX-License-Identifier: Apache-2.0
"""``simtrail``: mirror and drive the iOS Simulator from any agent or browser.

Each command is a module that registers its arguments and runs with a `CliContext`. A refusal a person can act on --
a setting, a scope, a token, the daemon -- is one line on stderr and exit status 1, never a traceback.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from simtrail._version import __version__
from simtrail.cli import (
    android,
    app_command,
    config_command,
    device_command,
    devices,
    doctor,
    helper,
    login,
    mcp,
    open_viewer,
    record,
    serve,
    settings_command,
    stop,
    tokens,
    tools,
    version,
    wda,
    xcode,
)
from simtrail.cli.context import CliContext
from simtrail.config.writer import ConfigError
from simtrail.daemon.tokens import TokenRefused
from simtrail.mcp.launcher import DaemonUnavailable
from simtrail.scope import InvalidScope

COMMANDS = (
    serve, mcp, login, open_viewer, stop, doctor, config_command, settings_command, devices, device_command, record,
    tokens, tools, xcode, helper, app_command, wda, android, version,
)  # fmt: skip
REFUSALS = (ConfigError, DaemonUnavailable, InvalidScope, TokenRefused)


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="simtrail",
        description="Mirror and drive the iOS Simulator from Claude Code, CLI agents and the browser.",
    )
    made.add_argument("--version", action="version", version=f"simtrail {__version__}")
    commands = made.add_subparsers(dest="command", metavar="COMMAND")
    for command in COMMANDS:
        command.register(commands)
    return made


def main(argv: Sequence[str] | None = None, *, ctx: CliContext | None = None) -> int:
    context = ctx or CliContext.from_process()
    made = parser()
    args = made.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        made.print_help(context.stdout)
        return 0
    try:
        return int(handler(args, context))
    except REFUSALS as exc:
        context.complain(f"simtrail: {exc}")
        return 1
