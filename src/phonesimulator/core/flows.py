# SPDX-License-Identifier: Apache-2.0
"""Flows: a walkthrough an agent saves once under a name and plays again in one call (`sim_flow`).

A flow is what `sim_act` takes -- its steps, and a wait after them -- or several such batches in a row, each waiting
for its own screen. It is kept as one JSON file per flow, ``<name>.json``, beside the scope's builds in its state
folder: ``<state>/flows/<scope>/``. The file is meant to be read, compared and committed like any other text: two
spaces of indent, keys in the order a person writes them, a line at the end.

A ref names an element only for the agent that was given it, and only on that device, so a flow keeps what each of its
refs named when it was saved -- the element's kind, label, identifier and where it was (`Target`) -- and plays it by
finding that element on the screen again (`Target.find`). A point and a key need nothing of the kind.

The text a ``type`` step types may hold variables, ``{{email}}``, given their values when the flow is played: that is
how a test account's address changes between runs, and how a password is typed without being kept. A step that types
into a secure field must type variables alone (`only_variables`), so a secret never reaches the file.
"""

from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from phonesimulator.core.actions import MAX_STEPS, ActionError, check_steps
from phonesimulator.perception.snapshot import Element, Snapshot
from phonesimulator.perception.wait import parse_wait
from phonesimulator.scope import Scope
from phonesimulator.seams import StateStore
from phonesimulator.storage.private import ensure_private_dir, write_atomic
from phonesimulator.validation import Invalid

#: The version of a flow's file, written in it: a later PhoneSimulator reads this one, and says so of one it cannot.
FORMAT = 1
#: The folder beside a scope's builds that holds its flows.
FOLDER = "flows"
NAME = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,63}\Z")
DESCRIPTION_MAX = 500
#: The most steps a flow may hold, all its batches together; each batch plays in calls of `MAX_STEPS`.
STEPS_MAX = 200
BATCHES_MAX = 20
#: A variable in a typed text: ``{{email}}``, with spaces inside the braces allowed.
VARIABLE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]{0,63})\s*\}\}")
VARIABLES_MAX = 20
#: The steps whose value is a target, a ref or a point.
TOUCHES = ("tap", "long_press", "right_click", "hover")


class FlowRefused(Exception):
    """A flow that cannot be saved, read or played as asked, said so the agent knows what to do instead."""


@dataclass(frozen=True)
class Target:
    """What a ref named when its flow was saved, so it can be found again on another screen, by another agent."""

    kind: str
    label: str
    identifier: str
    x: float
    y: float

    @classmethod
    def of(cls, element: Element) -> Target:
        return cls(element.kind, element.label, element.identifier, round(element.x, 1), round(element.y, 1))

    def describe(self) -> str:
        return f'{self.kind} "{self.label}"' if self.label else self.kind

    def find(self, snapshot: Snapshot) -> Element | None:
        """The element on this screen that is the one it named: the same kind, label and identifier -- or the same
        label and identifier read as another kind, as a segment is once selected -- the nearest to where it was when
        several are."""
        named = [e for e in snapshot.elements if e.ref is not None and (e.label, e.identifier) == self.key()]
        same = [element for element in named if element.kind == self.kind] or named
        if not same:
            return None
        return min(same, key=lambda element: math.hypot(element.x - self.x, element.y - self.y))

    def key(self) -> tuple[str, str]:
        return self.label, self.identifier

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "label": self.label, "identifier": self.identifier, "x": self.x, "y": self.y}

    @classmethod
    def from_json(cls, value: object) -> Target:
        if not isinstance(value, dict):
            raise FlowRefused("a target is an object")
        kind, label, identifier = value.get("kind"), value.get("label", ""), value.get("identifier", "")
        x, y = value.get("x"), value.get("y")
        texts = (kind, label, identifier)
        if not all(isinstance(text, str) for text in texts) or not _numbers(x, y):
            raise FlowRefused("a target has a kind, a label, an identifier, and x and y")
        assert isinstance(x, int | float) and isinstance(y, int | float)
        return cls(str(kind), str(label), str(identifier), float(x), float(y))


def _numbers(*values: object) -> bool:
    return all(isinstance(value, int | float) and not isinstance(value, bool) for value in values)


@dataclass(frozen=True)
class Batch:
    """Steps played as `sim_act` plays them, then a wait for their screen; None for no wait."""

    steps: tuple[dict[str, Any], ...]
    wait: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        return {"steps": list(self.steps), **({"wait": self.wait} if self.wait is not None else {})}


@dataclass(frozen=True)
class Flow:
    name: str
    description: str
    batches: tuple[Batch, ...]
    #: What each ref in its steps named when it was saved.
    targets: Mapping[str, Target]

    @property
    def steps(self) -> list[dict[str, Any]]:
        return [step for batch in self.batches for step in batch.steps]

    @property
    def variables(self) -> list[str]:
        """The variables its typed texts hold, in the order they first appear."""
        found = (name for step in self.steps if "type" in step for name in variables_in(step["type"]))
        return list(dict.fromkeys(found))

    def to_json(self) -> dict[str, Any]:
        return {
            "phonesimulator_flow": FORMAT,
            "name": self.name,
            "description": self.description,
            "variables": self.variables,
            "batches": [batch.to_json() for batch in self.batches],
            "targets": {ref: target.to_json() for ref, target in self.targets.items()},
        }

    @classmethod
    def from_json(cls, document: object, name: str) -> Flow:
        if not isinstance(document, dict) or document.get("phonesimulator_flow") != FORMAT:
            raise FlowRefused(f"{name} is not a flow this PhoneSimulator reads (phonesimulator_flow {FORMAT})")
        description = document.get("description", "")
        if not isinstance(description, str):
            raise FlowRefused(f"{name}: description is text")
        raw_targets = document.get("targets", {})
        if not isinstance(raw_targets, dict):
            raise FlowRefused(f"{name}: targets is an object of refs")
        try:
            batches = batches_of({"batches": document.get("batches")})
            targets = {str(ref): Target.from_json(value) for ref, value in raw_targets.items()}
        except FlowRefused as exc:
            raise FlowRefused(f"{name}: {exc}") from None
        flow = cls(name, description, tuple(batches), targets)
        unnamed = sorted({ref for step in flow.steps for ref in refs_of(step)} - targets.keys())
        if unnamed:
            raise FlowRefused(f"{name}: {', '.join(unnamed)} has no target saved with it")
        return flow


def variables_in(text: object) -> list[str]:
    return VARIABLE.findall(text) if isinstance(text, str) else []


def only_variables(text: str) -> bool:
    """Whether a typed text is variables alone, with nothing of its own to keep."""
    return bool(variables_in(text)) and not VARIABLE.sub("", text).strip()


def substituted(text: str, values: Mapping[str, str]) -> str:
    return VARIABLE.sub(lambda match: values[match.group(1)], text)


def _batch(value: object, where: str) -> Batch:
    if not isinstance(value, dict) or set(value) - {"steps", "wait"}:
        raise FlowRefused(f'{where} is {{"steps": [...], "wait": {{...}}}}, as sim_act takes them')
    steps, wait = value.get("steps"), value.get("wait")
    if not isinstance(steps, list) or not steps or not all(isinstance(step, dict) for step in steps):
        raise FlowRefused(f"{where}: steps is a list of one or more steps")
    for start in range(0, len(steps), MAX_STEPS):
        try:
            check_steps(steps[start : start + MAX_STEPS])
        except ActionError as exc:
            # A step's number within its call of `MAX_STEPS`, as check_steps says it, is its number in the batch.
            said = _renumbered(str(exc), start)
            raise FlowRefused(f"{where}: {said}") from None
    if wait is not None:
        if not isinstance(wait, dict):
            raise FlowRefused(f"{where}: a wait is an object, as sim_act takes it")
        try:
            parse_wait(wait)
        except Invalid as exc:
            raise FlowRefused(f"{where}: the wait is refused: {exc}") from None
    return Batch(tuple(copy.deepcopy(steps)), copy.deepcopy(wait))


def _renumbered(said: str, start: int) -> str:
    """What check_steps said of a step, numbered in its batch rather than in its call of `MAX_STEPS`."""
    match = re.match(r"step (\d+)", said)
    return f"step {int(match.group(1)) + start}{said[match.end() :]}" if match else said


def batches_of(args: Mapping[str, Any]) -> list[Batch]:
    """The batches a call gives: ``steps`` and ``wait`` as sim_act takes them, or ``batches`` of them -- each checked as
    sim_act checks a call's, and a flow's steps `STEPS_MAX` at most in all."""
    batches = args.get("batches")
    if batches is not None and ("steps" in args or "wait" in args):
        raise FlowRefused("give steps (and wait) or batches, not both")
    if batches is None:
        found = [_batch({key: args[key] for key in ("steps", "wait") if key in args}, "the flow")]
    elif not isinstance(batches, list) or not 1 <= len(batches) <= BATCHES_MAX:
        raise FlowRefused(f"batches is a list of 1 to {BATCHES_MAX} batches")
    else:
        found = [_batch(batch, f"batch {number}") for number, batch in enumerate(batches, start=1)]
    count = sum(len(batch.steps) for batch in found)
    if count > STEPS_MAX:
        raise FlowRefused(f"a flow holds at most {STEPS_MAX} steps; this one has {count}")
    names = {name for batch in found for step in batch.steps if "type" in step for name in variables_in(step["type"])}
    if len(names) > VARIABLES_MAX:
        raise FlowRefused(f"a flow uses at most {VARIABLES_MAX} variables; this one uses {len(names)}")
    return found


def _targets(step: Mapping[str, Any]) -> list[tuple[Any, Any]]:
    """Each place in a step that holds a target, as (the list or object holding it, its key or index)."""
    places: list[tuple[Any, Any]] = []
    for kind in TOUCHES:
        if kind in step:
            places.append((step, kind))
    if "type" in step and step.get("into") is not None:
        places.append((step, "into"))
    swipe = step.get("swipe")
    if isinstance(swipe, dict):
        places += [(swipe, key) for key in ("from", "to") if key in swipe]
    scroll = step.get("scroll")
    if isinstance(scroll, dict) and "at" in scroll:
        places.append((scroll, "at"))
    drag = step.get("drag")
    if isinstance(drag, dict) and isinstance(drag.get("path"), list):
        places += [(drag["path"], index) for index in range(len(drag["path"]))]
    return places


def refs_of(step: Mapping[str, Any]) -> list[str]:
    """The refs a step names, in order, each once."""
    found = [holder[key] for holder, key in _targets(step) if isinstance(holder[key], str)]
    return list(dict.fromkeys(found))


def target_of(step: Mapping[str, Any]) -> Any:
    """What a touch or a typing step lands on first -- a ref or a point -- or None for one that names nothing."""
    for kind in TOUCHES:
        if kind in step:
            return step[kind]
    return step.get("into") if "type" in step else None


def with_refs(step: Mapping[str, Any], refs: Mapping[str, str]) -> dict[str, Any]:
    """The step with each of its refs replaced by the one its element has on screen now."""
    changed = copy.deepcopy(dict(step))
    for holder, key in _targets(changed):
        if isinstance(holder[key], str) and holder[key] in refs:
            holder[key] = refs[holder[key]]
    return changed


def with_values(step: Mapping[str, Any], values: Mapping[str, str]) -> dict[str, Any]:
    """The step with each variable in its typed text replaced by its value."""
    changed = copy.deepcopy(dict(step))
    if isinstance(changed.get("type"), str):
        changed["type"] = substituted(changed["type"], values)
    return changed


def pieces(steps: Sequence[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """How a batch's steps are played: in calls of at most `MAX_STEPS`, and a step that names a ref begins a call of
    its own, so the screen it is found on is read just before it plays -- the steps before it may have changed it."""
    found: list[list[dict[str, Any]]] = []
    for start in range(0, len(steps), MAX_STEPS):
        for index, step in enumerate(steps[start : start + MAX_STEPS]):
            if index == 0 or refs_of(step):
                found.append([step])
            else:
                found[-1].append(step)
    return found


def flows_folder(state: StateStore) -> Callable[[Scope], Path]:
    """Where each scope's flows are kept: ``flows/<scope>`` in the state folder, beside its builds."""

    def folder(scope: Scope) -> Path:
        builds = state.builds_dir(scope)
        return builds.parent.parent / FOLDER / builds.name

    return folder


class FlowStore:
    """Each scope's flows, one JSON file each."""

    def __init__(self, folder_of: Callable[[Scope], Path]) -> None:
        self._folder_of = folder_of

    def folder(self, scope: Scope) -> Path:
        return self._folder_of(scope)

    def path(self, scope: Scope, name: object) -> Path:
        if not isinstance(name, str) or not NAME.match(name):
            raise FlowRefused("name is 1 to 64 lowercase letters, digits, dashes and underscores, such as sign-in")
        return self.folder(scope) / f"{name}.json"

    def save(self, scope: Scope, flow: Flow, *, replace: bool) -> Path:
        """Keep a flow, refusing to write over one of its name unless `replace`."""
        path = self.path(scope, flow.name)
        if path.exists() and not replace:
            raise FlowRefused(f"a flow named {flow.name} is already kept; pass replace: true to write over it")
        ensure_private_dir(path.parent)
        write_atomic(path, (json.dumps(flow.to_json(), indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        return path

    def load(self, scope: Scope, name: object) -> Flow:
        path = self.path(scope, name)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FlowRefused(f"no flow is named {name}; sim_flow list names those kept") from None
        except (OSError, ValueError) as exc:
            raise FlowRefused(f"{name} could not be read: {exc}") from None
        return Flow.from_json(document, path.stem)

    def listing(self, scope: Scope) -> Iterable[Flow | str]:
        """Each flow kept, by name -- or, for a file that cannot be read as one, why."""
        folder = self.folder(scope)
        for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
            try:
                yield self.load(scope, path.stem)
            except FlowRefused as exc:
                yield str(exc)

    def delete(self, scope: Scope, name: object) -> bool:
        path = self.path(scope, name)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True
