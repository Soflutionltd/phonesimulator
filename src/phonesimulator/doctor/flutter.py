# SPDX-License-Identifier: Apache-2.0
"""The doctor's check for Flutter apps: the flutter command a Flutter app would be built with, and its version.

Only a Flutter app needs one, so finding none is said, not warned of -- unless ``build.flutter_path`` names one that is
not there. Asking its version runs ``flutter --version``, which starts nothing else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from phonesimulator.doctor.report import CheckResult
from phonesimulator.platform.flutter import looked_in

if TYPE_CHECKING:
    from phonesimulator.doctor.checks import DoctorContext

NAME = "flutter"
INSTALL = "Install Flutter (brew install --cask flutter), or name it with build.flutter_path."


async def check_flutter(ctx: DoctorContext) -> CheckResult:
    configured = ctx.config.flutter_path
    sdk = ctx.flutter(configured, ctx.env)
    if sdk is None:
        if configured:
            return CheckResult(NAME, "warn", f"build.flutter_path names {configured}, which is not a flutter", INSTALL)
        return CheckResult(NAME, "ok", f"none found ({looked_in()}); only a Flutter app needs one", INSTALL)
    version = await ctx.flutter_version(sdk)
    if version is None:
        return CheckResult(NAME, "warn", f"{sdk.path} ({sdk.source}) did not say its version", INSTALL)
    return CheckResult(NAME, "ok", f"Flutter {version} at {sdk.path} ({sdk.source})")
