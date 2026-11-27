# SPDX-License-Identifier: Apache-2.0
"""``phonesimulator devices``: this Mac's iOS simulators, the real devices connected to it and its Android emulators and
phones, and which a project uses.

``phonesimulator devices prune`` deletes the simulators PhoneSimulator made that nothing runs and that hold no app -- every
one nothing runs, with ``--all`` -- and forgets them (`core.cleanup`); ``--dry-run`` only says which. While the daemon
runs, it is asked, since it owns the memory of what was made and knows what it runs; otherwise the memory is read here.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

from phonesimulator.cli.context import CliContext
from phonesimulator.core.cleanup import prune
from phonesimulator.core.devices import JsonDeviceMemory
from phonesimulator.mcp.launcher import NOTHING, OTHER, DaemonUnavailable, ensure_daemon, impostor
from phonesimulator.platform.simctl import Simctl, SimctlError

PRUNE = "/api/v1/admin/devices/prune"
#: Deleting a simulator can take simctl seconds, and there may be dozens.
PRUNE_TIMEOUT_S = 600.0

SCOPE_HELP = "for this scope, instead of this folder's project"


def register(commands: Any) -> None:
    command = commands.add_parser(
        "devices", help="list this Mac's simulators, real devices and Android devices, or choose one"
    )
    command.add_argument("--scope", help=SCOPE_HELP)
    actions = command.add_subparsers(dest="action", metavar="ACTION")
    listing = actions.add_parser("list", help="list the devices a project could use (the default)")
    choosing = actions.add_parser("choose", help="use this device for a project from now on")
    choosing.add_argument("udid")
    pruning = actions.add_parser(
        "prune", help="delete the simulators PhoneSimulator made that nothing runs and that hold no app"
    )
    pruning.add_argument("--all", action="store_true", help="delete those that hold apps too")
    pruning.add_argument("--dry-run", action="store_true", help="say what would be deleted, deleting nothing")
    for action in (listing, choosing):
        # Also taken after the action; left unset when it is not given there, so one given before the action stands.
        action.add_argument("--scope", default=argparse.SUPPRESS, help=SCOPE_HELP)
    command.set_defaults(handler=run, action="list")


def run(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.action == "prune":
        return run_prune(args, ctx)
    scope = ctx.scope(args.scope)
    client = ctx.client()
    ensure_daemon(client, ctx.start_daemon)
    base = f"/api/v1/scopes/{scope.id}"
    if args.action == "choose":
        client.put(f"{base}/device", {"udid": args.udid})
        ctx.say(f"{scope.label} uses {args.udid} from now on")
        return 0
    listed = client.get(f"{base}/devices")["devices"]
    if not listed:
        ctx.say("no iOS simulators, real devices or Android devices are available on this Mac")
    for device in listed:
        made = "  (made by PhoneSimulator)" if device["created"] else ""
        # A real device's kind, connection and what stands in its way come last, after what a simulator has always had.
        how = _kind(device)
        why = f"  ({device['detail']})" if device.get("detail") else ""
        ctx.say(f"{device['udid']}  {device['runtime']}  {device['name']}  {device['state']}{made}{how}{why}")
    return 0


def _kind(device: dict[str, Any]) -> str:
    """What a device is, when it is not a simulator: a real iPhone and how it is connected, or an Android device."""
    kind, connection = device.get("kind"), device.get("connection")
    if kind == "physical":
        return f"  real device, {connection or 'not connected'}"
    if kind == "android":
        return f"  Android phone, {connection}" if connection else "  Android emulator"
    return ""


def run_prune(args: argparse.Namespace, ctx: CliContext) -> int:
    """Prune through the daemon while it runs, else here, from the memory it would read."""
    client = ctx.client()
    found = client.probe()
    if found == OTHER:
        raise DaemonUnavailable(impostor(client.url))
    if found == NOTHING:
        try:
            pruned = [entry.as_json() for entry in asyncio.run(_prune_here(args, ctx))]
        except SimctlError as exc:
            ctx.complain(f"phonesimulator: {exc}")
            return 1
    else:
        answer = client.admin("POST", PRUNE, {"all": args.all, "dry_run": args.dry_run}, timeout=PRUNE_TIMEOUT_S)
        pruned = answer["devices"]
    for line in prune_lines(pruned, dry_run=args.dry_run):
        ctx.say(line)
    return 1 if any(entry.get("error") for entry in pruned) else 0


async def _prune_here(args: argparse.Namespace, ctx: CliContext) -> list[Any]:
    developer_dir = ctx.config().get(ctx.scope(args.scope)).developer_dir
    return await prune(
        Simctl(ctx.xcrun, developer_dir=developer_dir),
        JsonDeviceMemory(ctx.state.devices_file()),
        running=(),
        everything=args.all,
        dry_run=args.dry_run,
        env=ctx.env,
        home=ctx.home,
    )


def size_text(size: int) -> str:
    """How much space, as a person reads it."""
    return f"{size / 1e9:.1f} GB" if size >= 100_000_000 else f"{round(size / 1e6)} MB"


def prune_lines(pruned: Sequence[Mapping[str, Any]], *, dry_run: bool) -> list[str]:
    """What pruning did, or would do, to each simulator PhoneSimulator made, then how much it freed."""
    if not pruned:
        return ["no simulator PhoneSimulator made is left: nothing to delete"]
    doing = "would delete" if dry_run else "deleted"
    lines: list[str] = []
    count = freed = 0
    for entry in pruned:
        label = f"{entry['name']} ({entry['udid']})"
        if entry.get("error"):
            lines.append(f"could not delete {label}: {entry['error']}")
        elif entry.get("kept"):
            lines.append(f"kept {label}: {entry['kept']}")
        else:
            count += 1
            freed += int(entry["size"])
            lines.append(f"{doing} {label}, {size_text(int(entry['size']))}")
    lines.append(
        f"{doing} {count} simulator{'' if count == 1 else 's'}, "
        f"{'which would free' if dry_run else 'freeing'} {size_text(freed)}"
    )
    return lines
