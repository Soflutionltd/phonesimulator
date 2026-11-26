# SPDX-License-Identifier: Apache-2.0
"""What each scope is called: kept in a private file beside the tokens, read again after a restart."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from simtrail.daemon import scope_names
from simtrail.daemon.scope_names import ScopeNames
from simtrail.scope import Scope


def test_a_name_is_kept_privately_and_read_again(tmp_path: Path) -> None:
    path = tmp_path / "scope-names.json"
    names = ScopeNames(path)
    names.remember("project-app-1a2b", "  Sociomator  ")
    assert names.name("project-app-1a2b") == "Sociomator"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert ScopeNames(path).name("project-app-1a2b") == "Sociomator"
    assert names.name("unknown") is None


@pytest.mark.parametrize("label", ["", "   ", "two\nlines" * 0 + "x" * 201, "project-app-1a2b"])
def test_a_name_that_is_no_label_or_is_the_id_is_not_kept(tmp_path: Path, label: str) -> None:
    names = ScopeNames(tmp_path / "scope-names.json")
    names.remember("project-app-1a2b", label)
    assert names.name("project-app-1a2b") is None and not (tmp_path / "scope-names.json").exists()


def test_an_unchanged_name_is_not_written_again_and_the_oldest_go_past_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scope_names, "NAMES_MAX", 2)
    path = tmp_path / "scope-names.json"
    names = ScopeNames(path)
    names.remember("a", "A")
    written = path.stat().st_mtime_ns
    names.remember("a", "A")
    assert path.stat().st_mtime_ns == written
    names.remember("b", "B")
    names.remember("c", "C")
    assert (names.name("a"), names.name("b"), names.name("c")) == (None, "B", "C")


@pytest.mark.parametrize(
    "content",
    ["not json", json.dumps({"other": {}}), json.dumps({"names": []}), json.dumps({"names": {"a": 3, "bad id": "X"}})],
)
def test_a_file_that_cannot_be_read_names_nothing(tmp_path: Path, content: str) -> None:
    path = tmp_path / "scope-names.json"
    path.write_text(content)
    names = ScopeNames(path)
    assert names.name("a") is None and names.name("bad id") is None


def test_without_a_file_names_are_kept_for_this_run_only() -> None:
    names = ScopeNames(None)
    names.remember("a", "A")
    assert names.name("a") == "A"


def test_folders_name_the_scopes_they_are_and_no_other(tmp_path: Path) -> None:
    folder = tmp_path / "Notes"
    folder.mkdir()
    names = ScopeNames(None)
    scope = Scope.for_folder(folder)
    names.remember_folders([scope.id, "other"], [str(folder), str(tmp_path / "Elsewhere"), "\x00bad"])
    assert names.name(scope.id) == "Notes" and names.name("other") is None
