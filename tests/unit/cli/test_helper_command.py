# SPDX-License-Identifier: Apache-2.0
"""``phonesimulator helper``: which native helper is used and why not, and building one with Xcode -- without Xcode."""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from phonesimulator._version import __version__
from phonesimulator.cli.context import CliContext
from phonesimulator.cli.main import main
from phonesimulator.connectors.native.helper import PROGRAM, built_helper
from phonesimulator.platform.xcrun import XcrunResult
from phonesimulator.testing.fakes import FakeXcrun

THIS = json.dumps({"version": __version__, "wire": 1, "core_simulator": "1171.7"})
XCODE_27 = "/Applications/Xcode27.app/Contents/Developer"


class Here:
    """A terminal whose helper answers `versions` by path, with the Swift sources at `sources`."""

    def __init__(self, root: Path, *, sources: Path | None = None) -> None:
        self.root = root
        self.versions: dict[str, tuple[int, str]] = {}
        #: What each helper says of its permissions, by path; one with none cannot say.
        self.permissions: dict[str, tuple[int, str]] = {}
        #: What was opened with `open`, and what it answers.
        self.opened: list[tuple[str, ...]] = []
        self.open_answers: tuple[int, str] = (0, "")
        self.xcrun = FakeXcrun()
        self.out, self.err = io.StringIO(), io.StringIO()
        state = root / "state"
        self.built = built_helper(state / "helpers")
        self.installed = state / "helper" / PROGRAM
        (root / "config.toml").write_text(f'[device]\ndeveloper_dir = "{XCODE_27}"\n')
        self.ctx = CliContext(
            env={"PHONESIMULATOR_STATE_DIR": str(state), "PHONESIMULATOR_CONFIG": str(root / "config.toml")},
            cwd=root,
            stdout=self.out,
            stderr=self.err,
            stdin=io.StringIO(),
            home=root,
            run=self.run,
            xcrun=self.xcrun,
            helper_sources=lambda: sources,
        )

    async def run(self, argv: Sequence[str]) -> tuple[int, str]:
        asked = tuple(argv[1:])
        if argv[0] == "open":
            self.opened.append(asked)
            return self.open_answers
        if asked == ("version",):
            return self.versions.get(argv[0], (127, ""))
        if asked == ("permissions",):
            return self.permissions.get(argv[0], (1, ""))
        return (1, "")

    def __call__(self, *argv: str) -> int:
        return main(list(argv), ctx=self.ctx)

    def said(self) -> str:
        return self.out.getvalue()


def executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(0o755)
    return path


def test_status_without_a_helper_says_how_to_build_one(tmp_path: Path) -> None:
    here = Here(tmp_path, sources=tmp_path / "helper")
    assert here("helper") == 1
    said = here.said()
    assert "native helper: none" in said and "usable: no -- PhoneSimulator's native helper is not built" in said
    assert f"built for this version: {here.built} (not built)" in said
    assert f"installed at: {here.installed} (not installed)" in said
    assert f"Swift sources: {tmp_path / 'helper'}" in said


def test_status_names_the_installed_helper_and_its_version_as_text_or_json(tmp_path: Path) -> None:
    here = Here(tmp_path)
    executable(here.built)
    here.versions[str(here.installed)] = (0, THIS)
    assert here("helper", "status") == 0
    said = here.said()
    assert here.installed.read_bytes() == here.built.read_bytes(), "the built helper is installed at the one path"
    assert f"native helper: {here.installed} ({__version__}, wire 1, CoreSimulator 1171.7)" in said
    assert f"installed at: {here.installed}\n" in said
    assert "permissions:" not in said, "a helper that cannot say which it holds is not said to lack any"
    assert "usable: yes" in said and f"built for this version: {here.built}\n" in said
    assert "Swift sources: not in this install" in said
    here.out.truncate(0)
    here.out.seek(0)
    here.versions[str(here.installed)] = (0, json.dumps({"version": "0.9.0", "wire": 1}))
    assert here("helper", "status", "--json") == 1
    status = json.loads(here.said())
    assert status["installed"] == str(here.installed) and status["path"] == str(here.installed)
    assert status["version"] == "0.9.0" and status["usable"] is False and status["core_simulator"] is None
    assert "is version 0.9.0 (wire 1)" in status["reason"] and status["sources"] is None


def test_build_leaves_a_usable_helper_alone_unless_forced_and_needs_sources(tmp_path: Path) -> None:
    here = Here(tmp_path)
    executable(here.built)
    here.versions[str(here.built)] = (0, THIS)
    assert here("helper", "build") == 0 and "already built" in here.said() and here.xcrun.calls == []
    assert here("helper", "build", "--force") == 1
    assert "has no Swift sources for the native helper" in here.err.getvalue()


def products(folder: Path, *, with_helper: bool = True) -> FakeXcrun:
    def answer(args: tuple[str, ...]) -> XcrunResult:
        if args[-1] == "--show-bin-path":
            return XcrunResult(0, f"{folder}\n", "")
        if with_helper:
            executable(folder / PROGRAM)
        return XcrunResult(0, "Build complete!\n", "")

    return FakeXcrun().on("swift", "build", then=answer)


def test_build_builds_with_the_scopes_xcode_and_puts_the_helper_where_it_is_found(tmp_path: Path) -> None:
    here = Here(tmp_path, sources=tmp_path / "helper")
    here.ctx.xcrun = here.xcrun = products(tmp_path / "Products")
    here.versions[str(here.built)] = (0, THIS)
    assert here("helper", "build") == 0
    assert here.built.is_file() and here.built.stat().st_mode & 0o111
    assert here.xcrun.calls[0].developer_dir == XCODE_27
    assert f"from {tmp_path / 'helper'} with {XCODE_27}" in here.said()
    assert f"built the native helper at {here.built} (CoreSimulator 1171.7)" in here.said()


@pytest.mark.parametrize(
    ("setup", "complaint"),
    [
        ("fails", "did not build: error: no such module"),
        ("empty", "the build finished without a phonesimulator-helper"),
        ("old", "says version 0.9.0 (wire 1)"),
        ("silent", "says nothing readable"),
    ],
)
def test_build_that_does_not_give_a_usable_helper_says_why(tmp_path: Path, setup: str, complaint: str) -> None:
    here = Here(tmp_path, sources=tmp_path / "helper")
    if setup == "fails":
        here.ctx.xcrun = FakeXcrun().on("swift", "build", rc=1, err="error: no such module 'Foo'")
    else:
        here.ctx.xcrun = products(tmp_path / "Products", with_helper=setup != "empty")
    if setup == "old":
        here.versions[str(here.built)] = (0, json.dumps({"version": "0.9.0", "wire": 1}))
    assert here("helper", "build") == 1
    assert complaint in here.err.getvalue()


class Signing:
    """This Mac's signing as the command asks it: set up once, or refused."""

    def __init__(self, *, refuses: bool = False) -> None:
        self.refuses, self.made = refuses, False
        self.configured = ""

    def remember(self, identity: str) -> None:
        self.configured = identity

    def set_up(self) -> str:
        from phonesimulator.platform.local_signing import SigningError

        if self.refuses:
            raise SigningError("could not trust the certificate for code signing")
        self.made = True
        return "ABC123"

    def signer(self) -> str:
        return "local:ABC123" if self.made else ""

    def sign(self, binary: Path) -> None:
        binary.write_text(binary.read_text() + "# signed\n")


def test_sign_makes_this_macs_certificate_once_and_installs_the_helper_signed_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from phonesimulator.cli import helper as command

    signing = Signing()
    monkeypatch.setattr(command, "LocalSigning", lambda *_, **__: signing)
    here = Here(tmp_path)
    assert here("helper", "sign") == 0
    assert "signing with ABC123" in here.said() and "no helper to install yet" in here.said()
    executable(here.built)
    assert here("helper", "sign") == 0
    assert f"installed {here.installed}, signed with it" in here.said()
    assert here.installed.read_text().endswith("# signed\n")
    here.versions[str(here.installed)] = (0, THIS)
    here("helper", "status")
    assert "signed by: local:ABC123" in here.said()
    signing.refuses = True
    assert here("helper", "sign") == 1 and "could not trust the certificate" in here.err.getvalue()


def test_status_says_how_to_keep_a_grant_when_the_helper_is_signed_as_shipped(tmp_path: Path) -> None:
    here = Here(tmp_path)
    here("helper", "status")
    assert "signed by: as shipped -- run `phonesimulator helper sign` once" in here.said()


def test_sign_with_an_identity_of_yours_keeps_it_and_makes_no_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from phonesimulator.cli import helper as command

    signing = Signing()
    monkeypatch.setattr(command, "LocalSigning", lambda *_, **__: signing)
    here = Here(tmp_path)
    assert here("helper", "sign", "--identity", "Developer ID Application: A (TEAM)") == 0
    assert signing.configured == "Developer ID Application: A (TEAM)"
    assert not any("making this Mac's helper-signing certificate" in line for line in here.said())


def permissions(accessibility: bool, screen_recording: bool) -> tuple[int, str]:
    parts = [{"name": "accessibility", "ok": accessibility}, {"name": "screen_recording", "ok": screen_recording}]
    # The helper exits 1 while one is missing, as it does on a Mac.
    return (
        0 if accessibility and screen_recording else 1,
        json.dumps({"ok": accessibility and screen_recording, "parts": parts}),
    )


def test_status_says_which_permissions_the_helper_holds_and_where_to_allow_the_others(tmp_path: Path) -> None:
    here = Here(tmp_path)
    executable(here.built)
    here.versions[str(here.installed)] = (0, THIS)
    here.permissions[str(here.installed)] = permissions(True, False)
    assert here("helper", "status") == 0
    assert (
        "permissions: Accessibility allowed, Screen Recording not allowed -- allow the helper in System Settings > "
        "Privacy & Security > Screen Recording (`phonesimulator helper allow` opens them)"
    ) in here.said()
    here.out.truncate(0)
    here.out.seek(0)
    here.permissions[str(here.installed)] = permissions(True, True)
    assert here("helper", "status") == 0
    assert "permissions: Accessibility allowed, Screen Recording allowed\n" in here.said()
    here.out.truncate(0)
    here.out.seek(0)
    assert here("helper", "status", "--json") == 0
    assert json.loads(here.said())["permissions"] == {"accessibility": True, "screen_recording": True}
    here.permissions[str(here.installed)] = (0, "[]")
    here.out.truncate(0)
    here.out.seek(0)
    assert here("helper", "status", "--json") == 0
    assert json.loads(here.said())["permissions"] is None


def test_allow_opens_the_panes_of_the_permissions_missing_and_shows_the_helper(tmp_path: Path) -> None:
    here = Here(tmp_path)
    assert here("helper", "allow") == 1 and "no helper is installed yet" in here.err.getvalue()
    executable(here.built)
    here.versions[str(here.installed)] = (0, THIS)
    here("helper", "status")
    assert here("helper", "allow") == 1 and "did not say which permissions it holds" in here.err.getvalue()
    here.permissions[str(here.installed)] = permissions(False, False)
    here.out.truncate(0)
    here.out.seek(0)
    assert here("helper", "allow") == 0
    assert here.opened == [
        ("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",),
        ("x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",),
        ("-R", str(here.installed)),
    ]
    assert "opened Privacy & Security > Accessibility and Screen Recording" in here.said()
    here.opened.clear()
    here.permissions[str(here.installed)] = permissions(True, True)
    assert here("helper", "allow") == 0 and here.opened == []
    assert "already holds every permission" in here.said()
    here.permissions[str(here.installed)] = permissions(False, True)
    here.open_answers = (1, "LSOpenURLsWithRole() failed")
    assert here("helper", "allow") == 1 and "System Settings did not open: LSOpenURLsWithRole" in here.err.getvalue()
