# SPDX-License-Identifier: Apache-2.0
"""What an install from before a rename (Simtrail, then Rocketwright) left: its variables and its folders, taken up as
it starts."""

from __future__ import annotations

from pathlib import Path

import pytest

from phonesimulator import legacy
from phonesimulator.cli.main import main


def test_an_old_variable_stands_for_its_new_one_unless_that_is_set() -> None:
    env = {"SIMTRAIL_STATE_DIR": "/old", "SIMTRAIL_STREAM_FPS": "30", "PHONESIMULATOR_STREAM_FPS": "12", "PATH": "/bin"}
    assert legacy.adopt_environment(env) == ["PHONESIMULATOR_STATE_DIR"]
    assert env["PHONESIMULATOR_STATE_DIR"] == "/old" and env["PHONESIMULATOR_STREAM_FPS"] == "12"


def test_the_old_folders_move_with_a_link_left_where_each_was(tmp_path: Path) -> None:
    state = tmp_path / "Library" / "Application Support" / "Simtrail"
    (state / "helper").mkdir(parents=True)
    (state / "devices.json").write_text("{}")
    (tmp_path / ".simtrail").mkdir()
    moved, problems = legacy.move_folders(tmp_path, {})
    new_state = tmp_path / "Library" / "Application Support" / "PhoneSimulator"
    assert problems == [] and moved == [(state, new_state), (tmp_path / ".simtrail", tmp_path / ".phonesimulator")]
    assert (new_state / "devices.json").read_text() == "{}"
    assert state.is_symlink() and state.resolve() == new_state.resolve(), "a process of the old install finds its files"
    assert legacy.move_folders(tmp_path, {}) == ([], []), "once moved, nothing is moved again"


def test_a_folder_is_left_where_phonesimulator_has_one_or_its_variable_names_another_place(tmp_path: Path) -> None:
    logs = tmp_path / "Library" / "Logs"
    (logs / "Simtrail").mkdir(parents=True)
    (logs / "PhoneSimulator").mkdir()
    state = tmp_path / "Library" / "Application Support" / "Simtrail"
    state.mkdir(parents=True)
    moved, _ = legacy.move_folders(tmp_path, {"PHONESIMULATOR_STATE_DIR": "/elsewhere"})
    assert moved == [] and state.is_dir() and not state.is_symlink() and (logs / "Simtrail").is_dir()


def test_a_folder_that_cannot_be_moved_or_linked_is_said(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".simtrail").mkdir()

    def refuse(self: Path, target: Path, target_is_directory: bool = False) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "symlink_to", refuse)
    moved, problems = legacy.move_folders(tmp_path, {})
    assert moved == [(tmp_path / ".simtrail", tmp_path / ".phonesimulator")]
    assert problems == [f"moved {tmp_path / '.simtrail'} to {tmp_path / '.phonesimulator'}, but could not leave a link "
                        "where it was: Permission denied"]  # fmt: skip

    (tmp_path / "Library" / "Logs" / "Simtrail").mkdir(parents=True)

    def no_rename(self: Path, target: Path) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "rename", no_rename)
    _, problems = legacy.move_folders(tmp_path, {})
    logs = tmp_path / "Library" / "Logs"
    assert problems == [f"could not move {logs / 'Simtrail'} to {logs / 'PhoneSimulator'}: Permission denied"]


def test_run_as_a_program_it_takes_up_the_old_install_first_and_says_what_it_could_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[object] = []

    def adopt(env: object, home: Path) -> list[str]:
        seen.append(home)
        return ["could not move a to b: no"]

    monkeypatch.setattr(legacy, "adopt", adopt)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(SystemExit) as ended:
        main(["--version"])
    assert ended.value.code == 0 and seen == [tmp_path]
    assert "phonesimulator: could not move a to b: no" in capsys.readouterr().err


def test_adopt_reads_the_environment_before_it_moves_anything(tmp_path: Path) -> None:
    (tmp_path / ".simtrail").mkdir()
    env = {"SIMTRAIL_RUN_DIR": str(tmp_path / "run")}
    assert legacy.adopt(env, tmp_path) == []
    assert env["PHONESIMULATOR_RUN_DIR"] == str(tmp_path / "run")
    assert (tmp_path / ".simtrail").is_dir() and not (tmp_path / ".phonesimulator").exists()


def test_rocketwrights_folders_move_with_no_link_left_and_simtrails_link_follows(tmp_path: Path) -> None:
    support = tmp_path / "Library" / "Application Support"
    (support / "Rocketwright").mkdir(parents=True)
    (support / "Rocketwright" / "devices.json").write_text("{}")
    (support / "Simtrail").symlink_to(support / "Rocketwright", target_is_directory=True)
    (tmp_path / ".rocketwright").mkdir()
    moved, problems = legacy.move_folders(tmp_path, {})
    new = support / "PhoneSimulator"
    assert problems == [] and moved == [
        (support / "Rocketwright", new),
        (tmp_path / ".rocketwright", tmp_path / ".phonesimulator"),
    ]
    assert not (support / "Rocketwright").exists() and not (support / "Rocketwright").is_symlink()
    assert not (tmp_path / ".rocketwright").exists(), "that place is the browser tool's now"
    assert (support / "Simtrail").resolve() == new.resolve() and (new / "devices.json").read_text() == "{}"
    assert legacy.move_folders(tmp_path, {}) == ([], [])


def test_a_rocketwright_variable_is_not_taken_up_and_a_link_that_cannot_follow_is_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {"ROCKETWRIGHT_STATE_DIR": "/browser"}
    assert legacy.adopt_environment(env) == [] and "PHONESIMULATOR_STATE_DIR" not in env
    logs = tmp_path / "Library" / "Logs"
    (logs / "PhoneSimulator").mkdir(parents=True)
    (logs / "Simtrail").symlink_to(logs / "Rocketwright", target_is_directory=True)

    def refuse(self: Path, target: Path, target_is_directory: bool = False) -> None:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "symlink_to", refuse)
    _, problems = legacy.move_folders(tmp_path, {})
    assert problems == [f"could not point the link {logs / 'Simtrail'} at {logs / 'PhoneSimulator'}: Permission denied"]
