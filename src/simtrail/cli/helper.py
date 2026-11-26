# SPDX-License-Identifier: Apache-2.0
"""``simtrail helper``: the native helper this install runs.

* ``status`` says which helper the native connector would run -- the configured one, the one shipped in the wheel, or
  the one built for this version -- whether this Simtrail can use it, and where its Swift sources are;
* ``build`` builds it from those sources with the scope's Xcode, for this Mac, into Simtrail's state
  folder, where the native connector finds it. A release's wheel ships a built helper, so this is for a source
  checkout, an sdist, or a helper built again after Xcode changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from typing import Any

from simtrail._version import __version__
from simtrail.cli.context import CliContext
from simtrail.connectors.native import wire
from simtrail.connectors.native.helper import (
    PACKAGED,
    PROGRAM,
    HelperVersion,
    built_helper,
    helper_permissions,
    helper_version,
    install_helper,
    locate_helper,
)
from simtrail.host_copy import HostCopy
from simtrail.platform.local_signing import LocalSigning, SigningError
from simtrail.platform.macos import open_in_mac, show_in_finder
from simtrail.platform.swiftpm import build_package
from simtrail.storage.app_support import helpers_dir, installed_helper_dir, signing_dir
from simtrail.storage.private import ensure_private_dir


def register(commands: Any) -> None:
    command = commands.add_parser("helper", help="build the native helper, or say which one is used")
    actions = command.add_subparsers(dest="action", metavar="ACTION")
    status = actions.add_parser("status", help="say which native helper is used, and whether it can be")
    status.add_argument("--json", action="store_true", help="print it as JSON")
    status.add_argument("--scope", help="for this scope's settings, instead of this folder's project's")
    build = actions.add_parser("build", help="build the native helper with Xcode for this version of Simtrail")
    build.add_argument("--force", action="store_true", help="build it even when a usable one is already built")
    build.add_argument("--scope", help="build with this scope's Xcode, instead of this folder's project's")
    sign = actions.add_parser(
        "sign",
        help="sign the helper with a lasting identity, so Screen Recording and Accessibility granted to it are kept "
        "across upgrades: one you name, else this Mac's own certificate, made once (macOS asks for your password)",
    )
    sign.add_argument(
        "--identity",
        help='a code-signing identity of yours, such as "Developer ID Application: …", kept for every later install; '
        "an empty one goes back to this Mac's own certificate",
    )
    actions.add_parser(
        "allow",
        help="show where System Settings allows the helper (Accessibility, Screen Recording) and show the helper "
        "in the Finder, to drag it in; needed only to drive macOS apps",
    )
    command.set_defaults(handler=run, action="status", json=False, force=False, scope=None, signing=None, identity=None)


def run(args: argparse.Namespace, ctx: CliContext) -> int:
    if args.action == "sign":
        return _sign(args, ctx)
    if args.action == "allow":
        return asyncio.run(_allow(ctx))
    return asyncio.run(_build(args, ctx) if args.action == "build" else _status(args, ctx))


def _signing(args: argparse.Namespace, ctx: CliContext) -> LocalSigning:
    made: LocalSigning | None = getattr(args, "signing", None)
    return made if made is not None else LocalSigning(signing_dir(ctx.env, ctx.home), env=ctx.env)


def _sign(args: argparse.Namespace, ctx: CliContext) -> int:
    signing = _signing(args, ctx)
    if args.identity is not None:
        signing.remember(args.identity)
    if not signing.configured:
        ctx.say("making this Mac's helper-signing certificate; macOS asks for your password once to trust it")
    try:
        found = signing.set_up()
    except SigningError as exc:
        ctx.complain(f"simtrail: {exc}")
        return 1
    place = installed_helper_dir(ctx.env, ctx.home) / PROGRAM
    built = built_helper(helpers_dir(ctx.env, ctx.home))
    installed = install_helper((PACKAGED, built), place, signing)
    ctx.say(f"signing with {found}")
    if installed is None:
        ctx.say("no helper to install yet; the next one is signed with it")
        return 0
    ctx.say(
        f"installed {installed}, signed with it. Allow it once in System Settings > Privacy & Security > Screen "
        "Recording and > Accessibility (remove an earlier entry for it first); later versions keep that."
    )
    return 0


def _wanted() -> str:
    return f"version {__version__} (wire {wire.VERSION})"


async def _status(args: argparse.Namespace, ctx: CliContext) -> int:
    config = ctx.config().get(ctx.scope(args.scope))
    built = built_helper(helpers_dir(ctx.env, ctx.home))
    place = installed_helper_dir(ctx.env, ctx.home) / PROGRAM
    signing = _signing(args, ctx)
    installed = install_helper((PACKAGED, built), place, signing)

    async def version_of(binary: str) -> HelperVersion | None:
        return await helper_version(binary, ctx.run)

    shipped = (PACKAGED, built)
    found = await locate_helper(config.native_helper_path, (installed, *shipped) if installed else shipped, version_of)
    binary, version, usable = found.binary, found.version, found.usable
    reason = found.reason(HostCopy(), config.native_helper_path)
    sources = ctx.helper_sources()
    # Asked of the helper that runs, since a grant is kept for one signed program: none to ask when it cannot run.
    granted = await helper_permissions(binary, ctx.run) if binary and usable else None
    if args.json:
        ctx.say(json.dumps({
            "path": binary,
            "version": version.version if version else None,
            "wire": version.wire if version else None,
            "core_simulator": version.core_simulator if version else None,
            "usable": usable,
            "reason": reason,
            "built": str(built),
            "installed": str(place),
            "signed_by": signing.signer() or None,
            "permissions": granted,
            "sources": str(sources) if sources else None,
        }, indent=2))  # fmt: skip
    else:
        described = ""
        if version is not None:
            described = f" ({version.version}, wire {version.wire}, CoreSimulator {version.core_simulator})"
        ctx.say(f"native helper: {binary or 'none'}{described}")
        ctx.say("usable: yes" if usable else f"usable: no -- {reason}")
        ctx.say(f"built for this version: {built}" + ("" if built.is_file() else " (not built)"))
        ctx.say(f"installed at: {place}" + ("" if installed else " (not installed)"))
        if granted is not None:
            ctx.say(_permissions_line(granted))
        signer = signing.signer()
        ctx.say(
            f"signed by: {signer}"
            if signer
            else "signed by: as shipped -- run `simtrail helper sign` once so a permission granted to it is kept "
            "across upgrades"
        )
        ctx.say(f"Swift sources: {sources or 'not in this install'}")
    return 0 if usable else 1


#: What each permission is called in System Settings > Privacy & Security.
PERMISSION_PANES = {"accessibility": "Accessibility", "screen_recording": "Screen Recording"}


def _permissions_line(granted: dict[str, bool]) -> str:
    """Which permissions the helper holds, and where to allow the ones it lacks -- needed only to drive macOS apps."""
    named = {PERMISSION_PANES.get(name, name): ok for name, ok in granted.items()}
    held = ", ".join(f"{pane} {'allowed' if ok else 'not allowed'}" for pane, ok in named.items())
    missing = [pane for pane, ok in named.items() if not ok]
    if not missing:
        return f"permissions: {held}"
    where = " and ".join(missing)
    return (
        f"permissions: {held} -- allow the helper in System Settings > Privacy & Security > {where} "
        "(`simtrail helper allow` opens them); simulators need neither, macOS apps need both"
    )


#: Where System Settings shows each permission's list.
PERMISSION_URLS = {
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "screen_recording": "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
}


async def _allow(ctx: CliContext) -> int:
    """Open the panes of the permissions the installed helper lacks, and show it in the Finder: macOS lets only a person
    grant them, so this goes as far as it can and says what is left to do."""
    place = installed_helper_dir(ctx.env, ctx.home) / PROGRAM
    if not place.is_file():
        ctx.complain("simtrail: no helper is installed yet: run `simtrail helper status` (or `simtrail helper build`)")
        return 1
    granted = await helper_permissions(str(place), ctx.run)
    if granted is None:
        ctx.complain(f"simtrail: the helper at {place} did not say which permissions it holds")
        return 1
    missing = [name for name, ok in granted.items() if not ok]
    if not missing:
        ctx.say("the helper already holds every permission it needs")
        return 0
    for name in missing:
        code, out = await open_in_mac(PERMISSION_URLS.get(name, PERMISSION_URLS["accessibility"]), ctx.run)
        if code != 0:
            ctx.complain(f"simtrail: System Settings did not open: {out.strip()[:200]}")
            return 1
    await show_in_finder(place, ctx.run)
    panes = " and ".join(PERMISSION_PANES.get(name, name) for name in missing)
    ctx.say(
        f"opened Privacy & Security > {panes}, and showed the helper in the Finder: drag simtrail-helper into each "
        "list (or + and pick it), turn it on, then run `simtrail helper status` to check"
    )
    return 0


async def _build(args: argparse.Namespace, ctx: CliContext) -> int:
    config = ctx.config().get(ctx.scope(args.scope))
    helpers = helpers_dir(ctx.env, ctx.home)
    target = built_helper(helpers)
    if not args.force and target.is_file():
        version = await helper_version(str(target), ctx.run)
        if version is not None and version.usable:
            ctx.say(f"the native helper for this version is already built at {target} (--force builds it again)")
            return 0
    sources = ctx.helper_sources()
    if sources is None:
        ctx.complain("simtrail: this install has no Swift sources for the native helper to build")
        return 1
    xcode = config.developer_dir or "the Xcode xcode-select names"
    ctx.say(f"building the native helper from {sources} with {xcode}; a first build takes a minute or two")
    scratch = helpers / "native-build"
    built = await build_package(sources, scratch, developer_dir=config.developer_dir, xcrun=ctx.xcrun)
    if built.products is None:
        ctx.complain(f"simtrail: the native helper did not build: {built.failure}")
        return 1
    product = built.products / PROGRAM
    if not product.is_file():
        ctx.complain(f"simtrail: the build finished without a {PROGRAM} in {built.products}")
        return 1
    ensure_private_dir(target.parent)
    shutil.copy2(product, target)
    target.chmod(0o755)
    version = await helper_version(str(target), ctx.run)
    if version is None or not version.usable:
        said = "nothing readable" if version is None else f"version {version.version} (wire {version.wire})"
        ctx.complain(f"simtrail: the helper built at {target} says {said}, not {_wanted()}")
        return 1
    ctx.say(f"built the native helper at {target} (CoreSimulator {version.core_simulator or 'unknown'})")
    return 0
