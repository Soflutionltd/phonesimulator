# SPDX-License-Identifier: Apache-2.0
"""`sim_act`: a batch of steps played on the device, answered step by step and with what changed on screen -- and, when
a step failed because the device was shut down outside PhoneSimulator, saying so.

In a scope in observe mode (``agent.observe``), a step that would tap, long-press or type into an element that reads
like it changes something -- or swipe a list row sideways, drop onto such an element, or press return on a screen with
one -- is refused (`core.refusals.ObserveGuard`) unless this call says ``confirm: true``, which counts for this call
alone.

A call whose step failed, or whose wait was not met -- it gave up, could not read the screen, or was asked for wrongly
-- is an error, though the steps before stay played and the answer says which. ``allow_stale: true`` touches refs as
the agent's last snapshot has them, without reading the screen again when it may have changed out of sight
(`core.actions`). Text typed into a secure field is said as ``••••`` by the step's line and by everything that
shows the agent at work, and masked in every answer after. ``steal`` is read by the runtime, before the call gets
here (`core.drivers`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from phonesimulator.connectors.base import Capability
from phonesimulator.core.masking import PASSWORD_S
from phonesimulator.core.refusals import ObserveGuard
from phonesimulator.tools.context import ToolContext, flag_arg, make_tool, ready_device
from phonesimulator.tools.results import SHUT_DOWN, Result, ToolRefused, text


async def run(args: dict[str, Any], ctx: ToolContext) -> Result:
    snapshot = args.get("snapshot", "diff")
    if snapshot not in ("diff", "full", "none"):
        raise ToolRefused("snapshot is diff, full or none")
    confirmed = flag_arg(args.get("confirm"), "confirm")
    guard = ObserveGuard.of(
        ctx.config.agent_observe,
        ctx.config.agent_observe_words,
        confirmed=confirmed,
        languages=ctx.config.agent_observe_languages,
    )
    allow_stale = flag_arg(args.get("allow_stale"), "allow_stale")
    instance = await ready_device(ctx)
    acted = await ctx.actions.perform(
        instance,
        ctx.caller,
        args.get("steps"),
        wait=args.get("wait"),
        snapshot=snapshot,
        cursor=ctx.config.agent_cursor,
        lead_ms=ctx.config.cursor_lead_ms,
        max_elements=ctx.config.snapshot_max_elements,
        guard=guard,
        allow_stale=allow_stale,
        on_secret=hides_typed(ctx),
    )
    answer = acted.text
    if acted.failed and await ctx.manager.gone(ctx.scope, ctx.udid):
        answer += "\n" + SHUT_DOWN
    return text(
        answer,
        error=acted.failed or acted.unmet,
        data={
            "completed_steps": acted.completed_steps,
            "failed_step": acted.failed_step,
            # A connector can fail after delivering part of a gesture; never promise replay is safe.
            "failed_step_may_have_run": acted.failed,
            "wait_met": None if args.get("wait") is None or acted.failed else not acted.unmet,
        },
    )


def hide_typed(ctx: ToolContext, secrets: tuple[str, ...]) -> None:
    """Mask what the steps typed into secure fields in every answer from now on, as `sim_login`'s password is: a
    field that shows it back once its eye is tapped, or a log that writes it, then reads ``••••``."""
    if ctx.secrets is not None:
        for secret in secrets:
            ctx.secrets.hide(secret, PASSWORD_S)


def hides_typed(ctx: ToolContext) -> Callable[[str], None]:
    """What `AgentActions.perform` tells each secret before it types it, so it is masked even when the call is
    cancelled or fails with the text half typed."""
    return lambda secret: hide_typed(ctx, (secret,))


TOOL = make_tool("sim_act", (Capability.INPUT_TOUCH,), run)
