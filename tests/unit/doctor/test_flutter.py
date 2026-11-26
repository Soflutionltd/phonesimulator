# SPDX-License-Identifier: Apache-2.0
"""The doctor's Flutter check: the flutter command a Flutter app would be built with, and its version."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from rocketwright.config.model import SimConfig
from rocketwright.connectors.registry import ConnectorRegistry
from rocketwright.doctor.checks import CHECKS, DoctorContext
from rocketwright.doctor.flutter import INSTALL, check_flutter
from rocketwright.doctor.report import CheckResult
from rocketwright.platform.flutter import FlutterSdk

SDK = FlutterSdk(Path("/opt/homebrew/share/flutter/bin/flutter"), "PATH")


def context(
    sdk: FlutterSdk | None, version: str | None = "3.47.5 (Dart 3.13.4)", configured: str = ""
) -> DoctorContext:
    def find(path: str, env: Mapping[str, str]) -> FlutterSdk | None:
        assert path == configured and env == {"PATH": "/usr/bin"}
        return sdk

    async def said(found: FlutterSdk) -> str | None:
        return version

    return DoctorContext(
        config=SimConfig.defaults().with_values(flutter_path=configured),
        registry=ConnectorRegistry([]),
        env={"PATH": "/usr/bin"},
        flutter=find,
        flutter_version=said,
    )


async def test_the_flutter_found_is_shown_with_its_version_and_where_it_was_found() -> None:
    assert await check_flutter(context(SDK)) == CheckResult(
        "flutter", "ok", "Flutter 3.47.5 (Dart 3.13.4) at /opt/homebrew/share/flutter/bin/flutter (PATH)"
    )
    assert "flutter" in [check.name for check in CHECKS]


async def test_no_flutter_is_said_and_one_the_settings_name_that_is_not_there_warns() -> None:
    found = await check_flutter(context(None))
    assert found.status == "ok" and found.detail.startswith("none found (build.flutter_path, PATH, /opt/homebrew")
    assert found.detail.endswith("only a Flutter app needs one") and found.fix == INSTALL
    assert await check_flutter(context(None, configured="/opt/flutter")) == CheckResult(
        "flutter", "warn", "build.flutter_path names /opt/flutter, which is not a flutter", INSTALL
    )
    assert await check_flutter(context(SDK, version=None)) == CheckResult(
        "flutter", "warn", "/opt/homebrew/share/flutter/bin/flutter (PATH) did not say its version", INSTALL
    )
