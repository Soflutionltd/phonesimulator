# SPDX-License-Identifier: Apache-2.0
"""Flows as kept: their batches checked as sim_act checks a call, their refs found again, and their files read back."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from simtrail.core.actions import MAX_STEPS
from simtrail.core.flows import (
    BATCHES_MAX,
    STEPS_MAX,
    VARIABLES_MAX,
    Flow,
    FlowRefused,
    FlowStore,
    Target,
    batches_of,
    flows_folder,
    only_variables,
    pieces,
    refs_of,
    with_refs,
    with_values,
)
from simtrail.perception.snapshot import Element, Snapshot
from simtrail.testing.fakes import MemoryStateStore
from simtrail.testing.rig import scope

SCOPE = scope("tp-1")


def refused(args: dict[str, Any]) -> str:
    with pytest.raises(FlowRefused) as caught:
        batches_of(args)
    return str(caught.value)


def test_a_flow_s_batches_are_checked_as_sim_act_checks_a_call() -> None:
    assert refused({"steps": [{"tap": [1, 1]}], "batches": []}) == "give steps (and wait) or batches, not both"
    assert refused({"batches": "x"}) == f"batches is a list of 1 to {BATCHES_MAX} batches"
    assert refused({"batches": [{"steps": [{"tap": [1, 1]}], "then": 1}]}).startswith("batch 1 is {")
    assert refused({"batches": [{"steps": []}]}) == "batch 1: steps is a list of one or more steps"
    assert refused({"steps": [{"tap": [1, 1]}], "wait": "Saved"}) == (
        "the flow: a wait is an object, as sim_act takes it"
    )
    long = {"batches": [{"steps": [{"press": "home"}] * 60}] * 4}
    assert refused(long) == f"a flow holds at most {STEPS_MAX} steps; this one has 240"
    typed = [{"type": f"{{{{v{index}}}}}"} for index in range(VARIABLES_MAX + 1)]
    assert refused({"steps": typed}) == f"a flow uses at most {VARIABLES_MAX} variables; this one uses 21"
    assert len(batches_of({"steps": [{"press": "home"}] * (MAX_STEPS + 1)})[0].steps) == MAX_STEPS + 1


def test_every_target_a_step_holds_is_found_and_replaced() -> None:
    step = {"swipe": {"from": "e1", "to": [3, 4]}}
    assert refs_of(step) == ["e1"] and with_refs(step, {"e1": "e7"}) == {"swipe": {"from": "e7", "to": [3, 4]}}
    assert refs_of({"scroll": {"at": "e2", "dx": 0, "dy": 9}}) == ["e2"]
    assert refs_of({"drag": {"path": ["e3", [1, 2], "e3"]}}) == ["e3"]
    assert with_refs({"drag": {"path": ["e3", "e4"]}}, {"e3": "e9"}) == {"drag": {"path": ["e9", "e4"]}}
    assert with_values({"press": "home"}, {}) == {"press": "home"}
    assert with_values({"type": "{{ a }}-{{b}}"}, {"a": "1", "b": "2"}) == {"type": "1-2"}
    assert only_variables("{{a}} {{b}}") and not only_variables("plain") and not only_variables("x{{a}}")


def test_a_step_that_names_a_ref_begins_a_call_and_no_call_holds_more_than_max_steps() -> None:
    keys = [{"press": "home"}] * (MAX_STEPS + 3)
    assert [len(part) for part in pieces(keys)] == [MAX_STEPS, 3]
    mixed = [{"press": "home"}, {"tap": "e1"}, {"press": "home"}, {"tap": [1, 1]}]
    assert [len(part) for part in pieces(mixed)] == [1, 3]


def _element(ref: str, kind: str, label: str, x: float, y: float) -> Element:
    return Element(ref, kind, label, None, x, y)


def test_a_target_is_found_by_what_it_said_nearest_where_it_was() -> None:
    target = Target("button", "Add", "", 100, 100)
    screen = Snapshot(
        "h",
        (
            _element("e1", "button", "Add", 100, 700),
            _element("e2", "button", "Add", 100, 120),
            _element("e3", "cell", "Remove", 100, 100),
        ),
        "d",
        {},
        4,
    )
    found = target.find(screen)
    assert found is not None and found.ref == "e2"
    segment = Target("button", "Week", "", 10, 10)
    selected = Snapshot("h", (_element("e5", "segments", "Week", 10, 10),), "d", {}, 6)
    found = segment.find(selected)
    assert found is not None and found.ref == "e5", "read as another kind, it is still the one it named"
    assert Target("button", "Gone", "", 0, 0).find(screen) is None
    assert Target("text", "", "", 0, 0).describe() == "text"


def _document(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "simtrail_flow": 1,
        "batches": [{"steps": [{"tap": "e1"}]}],
        "targets": {"e1": {"kind": "button", "label": "Add", "identifier": "", "x": 1, "y": 2}},
    }
    return {**document, **changes}


@pytest.mark.parametrize(
    ("document", "said"),
    [
        ([], "f is not a flow this Simtrail reads (simtrail_flow 1)"),
        (_document(simtrail_flow=2), "f is not a flow this Simtrail reads (simtrail_flow 1)"),
        (_document(description=4), "f: description is text"),
        (_document(targets=[]), "f: targets is an object of refs"),
        (_document(targets={"e1": "Add"}), "f: a target is an object"),
        (_document(targets={"e1": {"kind": "button", "x": True, "y": 2}}), "f: a target has a kind, a label, an"),
        (_document(targets={}), "f: e1 has no target saved with it"),
        (_document(batches=None), "f: the flow: steps is a list of one or more steps"),
    ],
)
def test_a_flow_file_that_cannot_be_played_is_refused_saying_why(document: object, said: str) -> None:
    with pytest.raises(FlowRefused) as caught:
        Flow.from_json(document, "f")
    assert str(caught.value).startswith(said)


def test_flows_are_kept_beside_the_scope_s_builds_one_file_each(tmp_path: Path) -> None:
    state = MemoryStateStore(tmp_path)
    store = FlowStore(flows_folder(state))
    assert store.folder(SCOPE) == tmp_path / "state" / "flows" / "tp-1"
    assert list(store.listing(SCOPE)) == []
    flow = Flow.from_json(_document(), "add")
    path = store.save(SCOPE, flow, replace=False)
    assert json.loads(path.read_text(encoding="utf-8"))["name"] == "add"
    assert [kept.name for kept in store.listing(SCOPE) if isinstance(kept, Flow)] == ["add"]
    (path.parent / "odd.json").write_text(json.dumps({"simtrail_flow": 9}), encoding="utf-8")
    assert "odd is not a flow" in next(kept for kept in store.listing(SCOPE) if isinstance(kept, str))
    path.unlink()
    path.mkdir()
    with pytest.raises(FlowRefused, match="add could not be read"):
        store.load(SCOPE, "add")
