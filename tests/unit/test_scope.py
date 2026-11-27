# SPDX-License-Identifier: Apache-2.0
"""Scopes: ids that are safe in a URL and a file name, and one per project folder."""

from __future__ import annotations

from pathlib import Path

import pytest

from phonesimulator.scope import LABEL_MAX, STANDALONE_GROUP, InvalidScope, Scope, project_name


def test_a_scope_takes_a_url_safe_id_a_group_and_a_one_line_label() -> None:
    scope = Scope(id="ws:alpha:tp-1", group="alpha", label="alpha · tp-1")
    assert (scope.id, scope.group, scope.label) == ("ws:alpha:tp-1", "alpha", "alpha · tp-1")
    assert Scope.named("demo") == Scope(id="demo", group=STANDALONE_GROUP, label="demo")
    assert Scope.named("demo", group="team").group == "team"


@pytest.mark.parametrize(
    ("scope_id", "group", "label", "says"),
    [
        ("", "local", "x", "scope id"),
        ("-flag", "local", "x", "scope id"),
        ("a/b", "local", "x", "scope id"),
        ("a" * 129, "local", "x", "scope id"),
        ("ok", "has space", "x", "scope group"),
        ("ok", "local", "two\nlines", "one line"),
        ("ok", "local", "x" * (LABEL_MAX + 1), "one line"),
    ],
)
def test_what_cannot_be_used_is_refused(scope_id: str, group: str, label: str, says: str) -> None:
    with pytest.raises(InvalidScope, match=says):
        Scope(id=scope_id, group=group, label=label)


def test_a_folder_is_one_scope_by_its_real_path_whatever_it_is_called(tmp_path: Path) -> None:
    project = tmp_path / "My App (iOS)"
    project.mkdir()
    link = tmp_path / "link"
    link.symlink_to(project)
    scope = Scope.for_folder(project)
    assert scope.id.startswith("project-My-App-iOS-") and len(scope.id.rsplit("-", 1)[1]) == 8
    assert scope.label == "My App (iOS)" and scope.group == STANDALONE_GROUP
    assert Scope.for_folder(link) == scope
    other = tmp_path / "elsewhere" / "My App (iOS)"
    other.mkdir(parents=True)
    assert Scope.for_folder(other).id != scope.id


def test_a_folder_whose_name_has_nothing_usable_still_gets_a_scope(tmp_path: Path) -> None:
    odd = tmp_path / "🙂🙂"
    odd.mkdir()
    assert Scope.for_folder(odd).id.startswith("project-project-")
    assert Scope.for_folder(Path("/")).label == "Root"


def test_a_folders_label_is_its_projects_name_and_a_worktrees_is_its_repositorys(tmp_path: Path) -> None:
    repository = tmp_path / "Notes"
    (repository / ".git" / "worktrees" / "fix-login").mkdir(parents=True)
    worktree = tmp_path / "worktrees" / "fix-login"
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {repository / '.git' / 'worktrees' / 'fix-login'}\n")
    plain = Scope.for_folder(repository)
    copy = Scope.for_folder(worktree)
    assert (plain.label, copy.label) == ("Notes", "Notes")
    assert copy.id.startswith("project-fix-login-"), "the id keeps the folder's own name: devices are remembered by it"
    relative = tmp_path / "Notes" / "nested"
    relative.mkdir()
    (relative / ".git").write_text("gitdir: ../.git/worktrees/fix-login\n")
    assert project_name(relative) == "Notes"


@pytest.mark.parametrize("marker", ["gitdir: /somewhere/else/.git", "not a gitdir line", None])
def test_a_folder_that_is_not_a_worktree_is_called_by_its_own_name(tmp_path: Path, marker: str | None) -> None:
    folder = tmp_path / "app"
    folder.mkdir()
    if marker is not None:
        (folder / ".git").write_text(marker)
    assert project_name(folder) == "App"
    assert project_name(Path("/")) == "Root"


def test_an_unreadable_git_file_leaves_the_folders_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "app"
    folder.mkdir()
    (folder / ".git").write_text("gitdir: x")

    def refuse(self: Path, encoding: str = "") -> str:
        raise PermissionError("no")

    monkeypatch.setattr(Path, "read_text", refuse)
    assert project_name(folder) == "App"


def test_a_folder_inside_a_repository_is_called_by_the_repository_and_its_own_name(tmp_path: Path) -> None:
    repository = tmp_path / "courly"
    (repository / ".git").mkdir(parents=True)
    app = repository / "mobile"
    app.mkdir()
    assert (project_name(repository), project_name(app)) == ("Courly", "Courly · Mobile")
    worktree = tmp_path / "worktrees" / "flutter-mobile"
    (worktree / "mobile").mkdir(parents=True)
    (repository / ".git" / "worktrees" / "flutter-mobile").mkdir(parents=True)
    (worktree / ".git").write_text(f"gitdir: {repository / '.git' / 'worktrees' / 'flutter-mobile'}\n")
    assert project_name(worktree / "mobile") == "Courly · Mobile"


def test_a_name_in_lower_case_reads_with_a_capital_and_one_that_mixes_cases_is_kept(tmp_path: Path) -> None:
    for name, shown in (
        ("courly", "Courly"),
        ("Sociomator", "Sociomator"),
        ("iOS-app", "iOS-app"),
        ("my app", "My app"),
    ):
        folder = tmp_path / name
        folder.mkdir()
        assert project_name(folder) == shown
