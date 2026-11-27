# SPDX-License-Identifier: Apache-2.0
"""`sim_snapshot`: the screen as short lines with refs, or what changed since the agent last looked."""

from __future__ import annotations

from typing import Any

from phonesimulator.connectors.base import Capability
from phonesimulator.tools.context import ToolContext, flag_arg, make_tool, ready_device
from phonesimulator.tools.results import Result, ToolRefused, text

#: The fewest and the most lines a call may ask for: the most is `agent.snapshot_max_elements`' own.
MAX_ELEMENTS = (1, 400)


def _max_elements(args: dict[str, Any], most: int) -> int:
    """How many lines a call asks for, within what its scope lists at most."""
    value = args.get("max_elements", most)
    low, high = MAX_ELEMENTS
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ToolRefused(f"max_elements must be a whole number from {low} to {high}")
    return min(value, most)


async def run(args: dict[str, Any], ctx: ToolContext) -> Result:
    mode = args.get("mode", "diff")
    if mode not in ("diff", "full"):
        raise ToolRefused("mode is diff or full")
    max_elements = _max_elements(args, ctx.config.snapshot_max_elements)
    keys = flag_arg(args.get("keys"), "keys")
    instance = await ready_device(ctx)
    said = await ctx.actions.snapshot(instance, ctx.caller, mode=mode, max_elements=max_elements, keys=keys)
    return text(said)


TOOL = make_tool("sim_snapshot", (Capability.ELEMENT_TREE,), run)
