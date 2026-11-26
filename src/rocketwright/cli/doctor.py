# SPDX-License-Identifier: Apache-2.0
"""``rocketwright doctor``: check this Mac for Rocketwright (`doctor.checks`), ending with a real tap unless
``--no-tap``.

Exits 0 when all is well, 2 when something only warned and 1 when something failed. ``--json`` is what a compatibility
report asks for.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from rocketwright.cli.context import CliContext
from rocketwright.cli.wda import in_use
from rocketwright.connectors.registry import ConnectorContext
from rocketwright.core.devices import JsonDeviceMemory
from rocketwright.core.runtime import Runtime
from rocketwright.daemon.policy import ConfigPolicy
from rocketwright.doctor.checks import DoctorContext
from rocketwright.doctor.tap import TAP_SCOPE
from rocketwright.host_copy import HostCopy
from rocketwright.platform.simctl import Simctl


def register(commands: Any) -> None:
    command = commands.add_parser("doctor", help="check this Mac for what Rocketwright needs")
    command.add_argument("--json", action="store_true", help="print the report as JSON")
    command.add_argument("--no-tap", action="store_true", help="skip the real test tap on a simulator")
    command.add_argument("--device", help="the simulator (UDID) to tap, instead of a booted one")
    command.set_defaults(handler=run)


def run(args: argparse.Namespace, ctx: CliContext) -> int:
    return asyncio.run(_diagnose(args, ctx))


async def _diagnose(args: argparse.Namespace, ctx: CliContext) -> int:
    source = ctx.config()
    state = ctx.state
    copy = HostCopy()

    def simctl_for(developer_dir: str) -> Simctl:
        return Simctl(ctx.xcrun, developer_dir=developer_dir)

    registry = ctx.registry(ConnectorContext(state=state, copy=copy, simctl_for=simctl_for))
    runtime = None
    if not args.no_tap:
        policy = ConfigPolicy(source, ctx.tokens(), state)
        runtime = Runtime.build(
            config=source,
            state=state,
            memory=JsonDeviceMemory(state.devices_file()),
            policy=policy,
            copy=copy,
            registry=registry,
            xcrun=ctx.xcrun,
        )
    doctor = DoctorContext(
        config=source.get(TAP_SCOPE),
        registry=registry,
        runtime=runtime,
        device=args.device,
        run=ctx.run,
        xcrun=ctx.xcrun,
        env=ctx.env,
        run_dir=state.run_dir(),
        folder=ctx.cwd,
        config_file=source.path,
        touch_now=lambda: in_use(ctx),
        log_dir=state.log_dir(),
        **ctx.doctor_android(),
    )
    try:
        report = await ctx.diagnose(doctor)
    finally:
        if runtime is not None:
            await runtime.close()
    ctx.say(json.dumps(report.to_dict(), indent=2) if args.json else report.text())
    return report.exit_code
