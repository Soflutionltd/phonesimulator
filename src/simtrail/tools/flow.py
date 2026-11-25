# SPDX-License-Identifier: Apache-2.0
"""`sim_flow`: a walkthrough saved once under a name and played again in one call, on whichever device the agent has.

``save`` keeps steps and a wait exactly as `sim_act` takes them -- or ``batches`` of them, each waiting for its own
screen -- with a description, in the scope's flows (`core.flows`). Each ref the steps name must be one this agent has
been given on its device, on any screen of this session, and what it named is kept beside it, so the flow can find the
element again later, by another agent. A step that types into a secure field -- a ref or a point on one, or the field
being edited -- must type variables alone, ``{{password}}``: a secret is never kept. ``list``, ``show`` and ``delete``
read and remove what is kept.

``run`` plays a flow through `sim_act`'s own path (`AgentActions.perform`): the same checks of every step, the same
observe mode, which ``confirm: true`` passes for this call, and the same one-agent-at-a-time hold on the device, which
the runtime keeps for ``run`` as for `sim_act` (`core.drivers`). Its steps go in calls of at most `MAX_STEPS`, and a
step that names a ref begins a call of its own: the screen is read just before it, and the element its ref named found
there -- waited for up to `FIND_S`, as a screen that is still opening takes a moment. Variables are given their values
by ``variables``; one missing, or given and not used, refuses the run before anything plays. What the run answers --
each step ok or error, numbered in the flow, then what changed on screen -- says a variable's value as its name, so a
password typed is not repeated back -- and a value typed into a secure field is said as ``••••`` wherever the agent
is shown at work, and masked in every answer after, as `sim_act` masks it. The run stops at the first step that
fails or wait not met, saying which.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from simtrail.connectors.base import Capability
from simtrail.core.actions import TYPE_MAX, ActionError
from simtrail.core.flows import (
    DESCRIPTION_MAX,
    Flow,
    FlowRefused,
    FlowStore,
    Target,
    batches_of,
    only_variables,
    pieces,
    refs_of,
    target_of,
    with_refs,
    with_values,
)
from simtrail.core.instance import DeviceInstance
from simtrail.core.refusals import ObserveGuard
from simtrail.perception.snapshot import Element, Snapshot
from simtrail.tools.act import hide_typed
from simtrail.tools.context import ToolContext, flag_arg, make_tool, ready_device
from simtrail.tools.results import SHUT_DOWN, Result, ToolRefused, text

ACTIONS = ("save", "list", "show", "delete", "run")
#: How long a run looks for the element a ref named before it says it is not there, and how often it reads meanwhile.
FIND_S = 5.0
FIND_POLL_S = 0.5
#: The shortest value a run's answer says by its variable's name rather than as typed: shorter ones are too likely to
#: be part of other words.
REDACTED_MIN = 3


def _store(ctx: ToolContext) -> FlowStore:
    if ctx.flows is None:
        raise ToolRefused("flows are not kept here")
    return ctx.flows


async def run(args: dict[str, Any], ctx: ToolContext) -> Result:
    action = args.get("action")
    if action not in ACTIONS:
        raise ToolRefused(f"action is one of {', '.join(ACTIONS)}")
    store = _store(ctx)
    try:
        if action == "list":
            return text(_listing(store, ctx))
        if action == "show":
            flow = store.load(ctx.scope, args.get("name"))
            return text(json.dumps(flow.to_json(), indent=2, ensure_ascii=False), data=flow.to_json())
        if action == "delete":
            name = args.get("name")
            if not store.delete(ctx.scope, name):
                raise ToolRefused(f"no flow is named {name}; sim_flow list names those kept")
            return text(f"deleted the flow {name}")
        if action == "save":
            return _save(args, ctx, store)
        return await _run(args, ctx, store)
    except FlowRefused as exc:
        raise ToolRefused(str(exc)) from exc


def _listing(store: FlowStore, ctx: ToolContext) -> str:
    lines = []
    for flow in store.listing(ctx.scope):
        if isinstance(flow, str):
            lines.append(f"cannot be read: {flow}")
            continue
        count = len(flow.steps)
        needs = f" · variables {', '.join(flow.variables)}" if flow.variables else ""
        said = f" · {flow.description}" if flow.description else ""
        lines.append(f"{flow.name} · {count} step{'s' if count != 1 else ''}{needs}{said}")
    return "\n".join(lines) or f"no flows kept yet in {store.folder(ctx.scope)}; sim_flow save keeps one"


def _save(args: dict[str, Any], ctx: ToolContext, store: FlowStore) -> Result:
    name = args.get("name")
    path = store.path(ctx.scope, name)
    assert isinstance(name, str), "a name a path is made of is text"
    description = args.get("description", "")
    if not isinstance(description, str) or len(description) > DESCRIPTION_MAX:
        raise ToolRefused(f"description is text of at most {DESCRIPTION_MAX} characters")
    replace = flag_arg(args.get("replace"), "replace")
    batches = batches_of(args)
    steps = [step for batch in batches for step in batch.steps]
    instance = ctx.instance()
    targets = _targets(steps, instance, ctx)
    _refuse_secrets(steps, instance, ctx)
    flow = Flow(name, description, tuple(batches), targets)
    replaced = path.exists()
    path = store.save(ctx.scope, flow, replace=replace)
    needs = f"; run it with variables {', '.join(flow.variables)}" if flow.variables else ""
    verb = "replaced" if replaced else "saved"
    return text(f"{verb} the flow {name}: {len(steps)} step{'s' if len(steps) != 1 else ''} · {path}{needs}")


def _targets(steps: Sequence[dict[str, Any]], instance: DeviceInstance | None, ctx: ToolContext) -> dict[str, Target]:
    """What each ref the steps name named for this agent, refusing a ref it has not been given on its device."""
    found: dict[str, Target] = {}
    for number, step in enumerate(steps, start=1):
        for ref in refs_of(step):
            element = ctx.actions.seen(instance, ctx.caller, ref) if instance is not None else None
            if element is None:
                raise ToolRefused(
                    f"step {number}: {ref} is not a ref you were given on your device: take sim_snapshot of the "
                    "screen it is on first, or give a point"
                )
            found.setdefault(ref, Target.of(element))
    return found


def _refuse_secrets(steps: Sequence[dict[str, Any]], instance: DeviceInstance | None, ctx: ToolContext) -> None:
    """Refuse a step that types text of its own into a secure field: the field a ref or a point names, or -- for typing
    with no ``into`` -- the one the last touch landed on, else the one being edited when the agent last looked."""
    last = ctx.actions.last_look(instance, ctx.caller) if instance is not None else None
    focused = next((e for e in last.elements if "editing" in e.flags), None) if last is not None else None
    for number, step in enumerate(steps, start=1):
        target = target_of(step)
        if target is not None:
            focused = _element(target, instance, last, ctx)
        if "type" not in step or focused is None or focused.kind != "secure" or only_variables(step["type"]):
            continue
        named = f' "{focused.label}"' if focused.label else ""
        raise ToolRefused(
            f"step {number} types into a secure field{named}: type a variable there alone, such as "
            '"{{password}}", and give its value to sim_flow run -- a flow never keeps a secret'
        )


def _element(target: Any, instance: DeviceInstance | None, last: Snapshot | None, ctx: ToolContext) -> Element | None:
    """The element a ref or a point lands on, as this agent saw it; None when it cannot be told."""
    if isinstance(target, str):
        return ctx.actions.seen(instance, ctx.caller, target) if instance is not None else None
    under = last.at(float(target[0]), float(target[1])) if last is not None else []
    return under[0] if under else None


def variable_values(given: object, flow: Flow) -> dict[str, str]:
    """The value of each variable the flow types, refusing one missing, one it does not use, or one that is not
    text."""
    if given is None:
        given = {}
    if not isinstance(given, dict):
        raise ToolRefused('variables is an object of names and their text, such as {"email": "test@example.com"}')
    needed = flow.variables
    missing = [name for name in needed if name not in given]
    if missing:
        raise ToolRefused(
            f"the flow {flow.name} types {', '.join('{{' + name + '}}' for name in missing)}: give "
            f"{'its value' if len(missing) == 1 else 'their values'} in variables; nothing was played"
        )
    unused = sorted(set(given) - set(needed))
    if unused:
        raise ToolRefused(f"the flow {flow.name} does not use {', '.join(unused)}; nothing was played")
    for name in needed:
        value = given[name]
        if not isinstance(value, str) or not 0 < len(value) <= TYPE_MAX or "\x00" in value:
            raise ToolRefused(f"variables: {name} is text of 1 to {TYPE_MAX} characters")
    return {name: given[name] for name in needed}


@dataclass(frozen=True)
class Played:
    """What playing a flow did: its answer, whether a step failed or a wait was not met, and how far it got."""

    text: str
    failed: bool = False
    unmet: bool = False
    completed_steps: int = 0
    failed_step: int | None = None
    #: Whether the failed step may have played part of itself before it failed: never when it was not found.
    may_have_run: bool = False


def guard_of(args: Mapping[str, Any], ctx: ToolContext) -> ObserveGuard | None:
    """What observe mode keeps this call off, unless it says ``confirm: true``."""
    return ObserveGuard.of(
        ctx.config.agent_observe,
        ctx.config.agent_observe_words,
        confirmed=flag_arg(args.get("confirm"), "confirm"),
        languages=ctx.config.agent_observe_languages,
    )


async def _run(args: dict[str, Any], ctx: ToolContext, store: FlowStore) -> Result:
    flow = store.load(ctx.scope, args.get("name"))
    values = variable_values(args.get("variables"), flow)
    snapshot = args.get("snapshot", "diff")
    if snapshot not in ("diff", "full", "none"):
        raise ToolRefused("snapshot is diff, full or none")
    guard = guard_of(args, ctx)
    instance = await ready_device(ctx)
    played = await play(flow, values, instance, ctx, guard=guard, snapshot=snapshot)
    answer = played.text
    if played.failed and played.may_have_run and await ctx.manager.gone(ctx.scope, ctx.udid):
        answer += "\n" + SHUT_DOWN
    return text(
        answer,
        error=played.failed or played.unmet,
        data={
            "flow": flow.name,
            "steps": len(flow.steps),
            "completed_steps": played.completed_steps,
            "failed_step": played.failed_step,
            "failed_step_may_have_run": played.may_have_run,
            "wait_met": None if played.failed else not played.unmet,
        },
    )


async def play(
    flow: Flow,
    values: Mapping[str, str],
    instance: DeviceInstance,
    ctx: ToolContext,
    *,
    guard: ObserveGuard | None,
    snapshot: str = "diff",
) -> Played:
    """Play a flow's steps on the device as `sim_act` plays them -- in calls of at most `MAX_STEPS`, a step that names
    a ref in a call of its own once its element is found -- stopping at the first step that fails or wait not met."""
    total = len(flow.steps)
    lines = [f"flow {flow.name} · {total} step{'s' if total != 1 else ''}"]
    done = 0
    for index, batch in enumerate(flow.batches):
        steps = [with_values(step, values) for step in batch.steps]
        parts = pieces(steps)
        for number, part in enumerate(parts):
            last = number == len(parts) - 1
            final = last and index == len(flow.batches) - 1
            refs = refs_of(part[0])
            if refs:
                found = await _find(refs, flow.targets, instance, ctx)
                if isinstance(found, str):
                    lines.append(f"error step {done + 1}: {found}")
                    return _stopped(lines, values, done, total, failed=True)
                part = [with_refs(part[0], found), *part[1:]]
            try:
                acted = await ctx.actions.perform(
                    instance,
                    ctx.caller,
                    part,
                    wait=batch.wait if last else None,
                    snapshot=snapshot if final else "none",
                    cursor=ctx.config.agent_cursor,
                    lead_ms=ctx.config.cursor_lead_ms,
                    max_elements=ctx.config.snapshot_max_elements,
                    guard=guard,
                )
            except ActionError as exc:
                lines.append(f"error step {done + 1}: {exc}")
                return _stopped(lines, values, done, total, failed=True, may_have_run=exc.__cause__ is not None)
            hide_typed(ctx, acted.secrets)
            lines += [_numbered(line, done) for line in acted.text.splitlines()]
            if acted.failed:
                return _stopped(lines, values, done + acted.completed_steps, total, failed=True, may_have_run=True)
            done += len(part)
            if acted.unmet:
                return _stopped(lines, values, done, total, unmet=True)
    return Played(_redacted("\n".join(lines), values), completed_steps=done)


def _stopped(
    lines: list[str],
    values: Mapping[str, str],
    done: int,
    total: int,
    *,
    failed: bool = False,
    unmet: bool = False,
    may_have_run: bool = False,
) -> Played:
    """A run that stopped: at the step after the `done` ones when one failed, else after them, at their wait."""
    at = done + 1 if failed else done
    why = "it failed" if failed else "its wait was not met"
    lines.append(f"stopped at step {at} of {total}: {why}, and the steps after it were not played")
    return Played(
        _redacted("\n".join(lines), values),
        failed=failed,
        unmet=unmet,
        completed_steps=done,
        failed_step=at if failed else None,
        may_have_run=may_have_run,
    )


def _numbered(line: str, done: int) -> str:
    """A line of a call's answer, its step numbered as in the whole flow."""
    return re.sub(r"\Aerror step (\d+)", lambda match: f"error step {int(match.group(1)) + done}", line)


def _redacted(said: str, values: Mapping[str, str]) -> str:
    """The answer with each variable's value said as its name, the longest first, so one inside another is not cut."""
    for name, value in sorted(values.items(), key=lambda item: -len(item[1])):
        if len(value) >= REDACTED_MIN:
            said = said.replace(value, "{{" + name + "}}")
    return said


async def _find(
    refs: Sequence[str], targets: Mapping[str, Target], instance: DeviceInstance, ctx: ToolContext
) -> dict[str, str] | str:
    """The ref each saved ref's element has on the screen now, read again until all are there or `FIND_S` has passed
    -- or, when one is not, why."""
    reads = round(FIND_S / FIND_POLL_S)
    for attempt in range(reads + 1):
        if attempt:
            await ctx.sleep(FIND_POLL_S)
        try:
            screen = await ctx.actions.read(instance, ctx.caller, ctx.config.snapshot_max_elements)
        except ActionError as exc:
            return f"the screen could not be read: {exc}"
        found: dict[str, str] = {}
        for ref in refs:
            element = targets[ref].find(screen)
            if element is not None and element.ref is not None:
                found[ref] = element.ref
        if len(found) == len(refs):
            return found
    missing = next(ref for ref in refs if ref not in found)
    return (
        f"{missing} ({targets[missing].describe()}) is not on screen after {FIND_S:g}s (#{screen.digest[:4]}); "
        "sim_snapshot shows what is"
    )


TOOL = make_tool("sim_flow", (Capability.INPUT_TOUCH,), run)
