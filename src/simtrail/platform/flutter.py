# SPDX-License-Identifier: Apache-2.0
"""The ``flutter`` command Simtrail builds, tests and runs a Flutter app with.

It is the one ``build.flutter_path`` names -- the command, or the SDK folder it is in -- else the one on Simtrail's own
``PATH``, else one where it is usually installed: Homebrew's (``/opt/homebrew/share/flutter/bin/flutter``) or a
person's own (``~/flutter/bin/flutter``, ``~/development/flutter/bin/flutter``). A daemon started by launchd or by a
host application often has a ``PATH`` without the folders a person's shell adds, which is why those places are looked
in too. A path the settings name that is not a ``flutter`` is that answer, None: a build with another Flutter than the
one a person named would not be the build they asked for.

Every call of flutter starts here: `start_flutter` for a build or a test run, its output appended to a log, and
`open_flutter_run` for ``flutter run --machine``, spoken to over its pipes. Each runs in a process group of its own,
so it is ended with everything it started -- xcodebuild, Gradle -- and with the folder flutter is in first on its
``PATH``, then the folders Homebrew puts CocoaPods and the rest in, which an iOS build of a plugin needs.
`flutter_version` asks it its version, for `simtrail doctor`.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simtrail.platform.process import Runner, run, spawn

FLUTTER = "flutter"
#: Where flutter is usually installed, when the settings name none and it is not on ``PATH``.
USUAL_PLACES = (
    Path("/opt/homebrew/share/flutter/bin/flutter"),
    Path("~/flutter/bin/flutter"),
    Path("~/development/flutter/bin/flutter"),
)
#: Folders a build's own tools -- CocoaPods, git -- are in, put on flutter's ``PATH`` after Simtrail's own.
TOOL_FOLDERS = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin")
#: How long ``flutter --version`` may take: a first call after an upgrade sets its own cache up.
VERSION_TIMEOUT_S = 60.0
#: The longest line ``flutter run --machine`` may say: an event naming a device is a kilobyte or two.
LINE_MAX = 1024 * 1024


@dataclass(frozen=True)
class FlutterSdk:
    """A flutter command on this Mac, and what named it."""

    path: Path
    #: ``build.flutter_path``, ``PATH``, or where it is usually installed.
    source: str


def _command(path: Path) -> Path | None:
    """The flutter command a path names: itself, or the ``bin/flutter`` of the SDK folder it is."""
    for candidate in (path, path / "bin" / FLUTTER):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def find_flutter(
    configured: str = "",
    env: Mapping[str, str] = os.environ,
    home: Path | None = None,
    *,
    places: Sequence[Path] = USUAL_PLACES,
) -> FlutterSdk | None:
    """The flutter these settings name, or the one on ``PATH``, or one where it is usually installed -- None when
    there is none."""
    if configured:
        named = _command(Path(configured).expanduser())
        return FlutterSdk(named, "build.flutter_path") if named is not None else None
    on_path = shutil.which(FLUTTER, path=env.get("PATH", ""))
    if on_path:
        return FlutterSdk(Path(on_path), "PATH")
    base = home or Path.home()
    for place in places:
        expanded = base / place.relative_to("~") if place.parts[:1] == ("~",) else place
        found = _command(expanded)
        if found is not None:
            return FlutterSdk(found, "its usual place")
    return None


def looked_in(places: Sequence[Path] = USUAL_PLACES) -> str:
    """Where `find_flutter` looks, as a refusal says it."""
    return "build.flutter_path, PATH, " + ", ".join(str(place) for place in places)


def flutter_env(sdk: FlutterSdk, env: Mapping[str, str]) -> dict[str, str]:
    """`env` with flutter's own folder first on ``PATH``, and the folders a build's tools are in after the rest."""
    folders = [str(sdk.path.parent), *env.get("PATH", "").split(os.pathsep)]
    folders += [folder for folder in TOOL_FOLDERS if folder not in folders]
    return {**env, "PATH": os.pathsep.join(folder for folder in dict.fromkeys(folders) if folder)}


async def start_flutter(
    sdk: FlutterSdk, args: Sequence[str], *, folder: Path, log_path: Path, env: Mapping[str, str]
) -> Any:
    """Start ``flutter <args>`` in `folder`, in its own process group, its output appended to `log_path`, with `env`
    added to Simtrail's environment."""
    return await spawn([str(sdk.path), *args], log_path, cwd=folder, env=flutter_env(sdk, {**os.environ, **env}))


async def open_flutter_run(sdk: FlutterSdk, args: Sequence[str], *, folder: Path, env: Mapping[str, str]) -> Any:
    """Start ``flutter <args>`` -- ``run --machine`` -- in `folder`, in its own process group, with pipes to speak to
    it and hear it."""
    return await asyncio.create_subprocess_exec(
        str(sdk.path),
        *args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        limit=LINE_MAX,
        cwd=str(folder),
        env=flutter_env(sdk, {**os.environ, **env}),
    )


async def flutter_version(sdk: FlutterSdk, *, runner: Runner | None = None) -> str | None:
    """The Flutter version a flutter command says it is, with its Dart's -- ``3.41.5 (Dart 3.11.5)`` -- or None when
    it does not answer."""
    if runner is None:
        rc, out = await run([str(sdk.path), "--version", "--machine"], timeout=VERSION_TIMEOUT_S)
    else:
        rc, out = await runner([str(sdk.path), "--version", "--machine"])
    # A first call after an upgrade says what it sets up before the JSON.
    start = out.find("{")
    if rc != 0 or start < 0:
        return None
    try:
        said = json.loads(out[start:])
    except ValueError:
        return None
    version = said.get("frameworkVersion") if isinstance(said, dict) else None
    if not isinstance(version, str) or not version:
        return None
    dart = said.get("dartSdkVersion")
    return f"{version} (Dart {dart})" if isinstance(dart, str) and dart else version
