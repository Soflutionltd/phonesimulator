# SPDX-License-Identifier: Apache-2.0
"""A simulator's data folder: worked out, never asked for, and never outside the devices folder."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from simtrail.platform.device_data import DEVICES_DIR_ENV, device_data_dir, devices_dir, folder_size, user_apps

UDID = "7A4C5B2E-9E2B-4C43-9F3A-2D0C3F0B6E11"


def test_the_devices_folder_is_xcodes_default_set_unless_the_environment_moves_it(tmp_path: Path) -> None:
    assert devices_dir({}, home=tmp_path) == tmp_path / "Library" / "Developer" / "CoreSimulator" / "Devices"
    assert devices_dir({DEVICES_DIR_ENV: "  "}, home=tmp_path) == devices_dir({}, home=tmp_path)
    assert devices_dir({DEVICES_DIR_ENV: str(tmp_path / "devices")}) == tmp_path / "devices"
    assert devices_dir({DEVICES_DIR_ENV: "~/sims"}) == Path.home() / "sims"
    assert devices_dir({}).name == "Devices"


def test_a_devices_data_folder_is_its_own_under_the_devices_folder(tmp_path: Path) -> None:
    env = {DEVICES_DIR_ENV: str(tmp_path)}
    assert device_data_dir(UDID, env=env) == tmp_path / UDID / "data"
    assert device_data_dir(UDID, env={}, home=tmp_path) == devices_dir({}, home=tmp_path) / UDID / "data"


@pytest.mark.parametrize("udid", ["", "../7A4C5B2E-9E2B-4C43-9F3A-2D0C3F0B6E11", "booted", "7A4C5B2E/../x"])
def test_anything_but_a_device_id_is_refused(udid: str) -> None:
    with pytest.raises(ValueError, match="not a simulator device id"):
        device_data_dir(udid, env={})


def test_the_apps_a_person_installed_are_read_from_its_folder_and_none_without_one(tmp_path: Path) -> None:
    env = {DEVICES_DIR_ENV: str(tmp_path)}
    assert user_apps(UDID, env=env) is None
    assert folder_size(UDID, env=env) == 0
    (tmp_path / UDID / "data").mkdir(parents=True)
    assert user_apps(UDID, env=env) == []
    bundles = tmp_path / UDID / "data" / "Containers" / "Bundle" / "Application"
    for folder, app in (("B", "Zeta.app"), ("A", "Alpha.app")):
        (bundles / folder / app).mkdir(parents=True)
        (bundles / folder / app / "Info.plist").write_bytes(b"x" * 300)
    (bundles / "A" / "iTunesMetadata.plist").write_bytes(b"y" * 30)
    assert user_apps(UDID, env=env) == ["Alpha.app", "Zeta.app"]
    (tmp_path / UDID / "link").symlink_to("/")
    assert folder_size(UDID, env=env) == 630, "a link to a folder is not followed"


def test_a_file_gone_while_the_folder_is_measured_is_left_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = {DEVICES_DIR_ENV: str(tmp_path)}
    (tmp_path / UDID).mkdir()
    (tmp_path / UDID / "device.plist").write_bytes(b"x" * 10)

    def gone(path: str) -> os.stat_result:
        raise FileNotFoundError(path)

    monkeypatch.setattr(os, "lstat", gone)
    assert folder_size(UDID, env=env) == 0
