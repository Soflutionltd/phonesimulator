# SPDX-License-Identifier: Apache-2.0
"""What a Flutter build, run or test run said, read as `xcresult` says an Xcode build's and test run's.

**A build or a hot reload that does not compile** is read from what flutter printed -- it writes no result file -- for
the Dart compiler's errors and warnings (measured with Flutter 3.47; fixtures in
`rocketwright/testing/fixtures/flutter-*`):

    lib/main.dart:133:46: Error: Expected an identifier, but got ','.

Xcode's errors in an iOS build are flutter's ``Error (Xcode): …`` lines, and a failure none of those explain is said by
Gradle's ``* What went wrong:`` section in an Android build, else flutter's own last ``Error:`` line.

**Tests** are read from the JSON file ``flutter test --file-reporter json:<file>`` writes -- one event a line, the
test package's JSON reporter: ``testStart`` names a test and where it is, ``error`` says why it failed, and
``testDone`` says how it ended. Each test file is first loaded as a hidden test of its own, counted only when it fails:
a test file that does not compile fails there, before any of its tests.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlsplit

from rocketwright.build.gradle_log import what_went_wrong
from rocketwright.build.xcresult import LISTED_MAX, MESSAGE_MAX, BuildSummary, Failure, Issue, SuiteSummary

#: The Dart compiler's errors and warnings, from the folder flutter runs in.
#: An iOS build passes them on inside Xcode's output, indented.
_DART = re.compile(r"^[ \t]*(\S[^:\n]*?\.dart):(\d+):(\d+): (Error|Warning): (.+)$", re.M)
#: Xcode's errors in an iOS build, as flutter passes them on.
_XCODE = re.compile(r"^Error \(Xcode\): (.+)$", re.M)
#: flutter's own account of why it stopped.
_FLUTTER = re.compile(r"^(?:Error|Exception): (.+)$|^(Encountered error while building for \w+\.)$", re.M)
#: The largest result file read: a run's results are kilobytes; a file far larger is not one.
FILE_MAX = 8 * 1024 * 1024
#: A test file's own frame in a failure's stack or its account of it: ``file:///…/app_test.dart:30:5``,
#: ``test/app_test.dart 30:5``, or ``file:///…/app_test.dart line 30``.
_FRAME = re.compile(r"(?:file://)?((?:/|\b[\w.-]+/)[^\s():]*_test\.dart)(?::(\d+):\d+| (\d+):\d+| line (\d+))")
#: What a widget test's failure printed: its headline, and the expectation it did not meet.
_THROWN = re.compile(r"^The following (.+) was thrown")
_EXPECTED = re.compile(r"^\s*(Expected|Actual|Which): (.+)$")
#: What a failure that was printed says in its own error event.
_SEE_ABOVE = "See exception logs above"


def _short(text: str) -> str:
    value = " ".join(text.split())
    return value if len(value) <= MESSAGE_MAX else value[: MESSAGE_MAX - 1] + "…"


def read_log(log: str, *, succeeded: bool, seconds: float | None) -> BuildSummary:
    """The errors and warnings what flutter printed holds, each where it is in the project."""
    issues = [
        Issue(kind.lower(), _short(message), file, int(line), int(column))
        for file, line, column, kind, message in _DART.findall(log)
    ]
    issues += [Issue("error", _short(message)) for message in _XCODE.findall(log)]
    # flutter prints the compiler's errors again in its own summary: each is said once.
    issues = list(dict.fromkeys(issues))
    errors = [issue for issue in issues if issue.kind == "error"]
    warnings = [issue for issue in issues if issue.kind == "warning"]
    if not succeeded and not errors:
        wrong = what_went_wrong(log)
        said = " ".join(wrong) if wrong else next((a or b for a, b in reversed(_FLUTTER.findall(log))), "")
        errors = [Issue("error", _short(said or "the Flutter build failed; the log says why"))]
    return BuildSummary(
        succeeded=succeeded,
        errors=tuple(errors[:LISTED_MAX]),
        warnings=tuple(warnings[:LISTED_MAX]),
        error_count=len(errors),
        warning_count=len(warnings),
        seconds=seconds,
    )


def compile_errors(lines: Iterable[str]) -> list[Issue]:
    """The Dart compiler's errors among lines flutter printed during a hot reload."""
    return [issue for issue in read_log("\n".join(lines), succeeded=True, seconds=None).errors]


@dataclass
class _Test:
    name: str
    file: str | None
    line: int | None
    hidden: bool = False
    result: str = ""
    skipped: bool = False
    errors: list[str] = field(default_factory=list)
    #: What it printed: a widget test prints its failure, and says only that it did in its error.
    printed: list[str] = field(default_factory=list)


def _path(url: object) -> str | None:
    if not isinstance(url, str) or not url:
        return None
    return unquote(urlsplit(url).path) if url.startswith("file://") else url


def _place(test: _Test) -> tuple[str | None, int | None]:
    """Where a failure happened: the test file's own frame in its stack, else where the test is declared."""
    for said in (*test.errors, *test.printed):
        found = _FRAME.search(said)
        if found:
            line = next(group for group in found.groups()[1:] if group)
            return found.group(1), int(line)
    return test.file, test.line


def _message(test: _Test) -> str:
    """Why a test failed: its error, or -- for a widget test's, which says to look above -- what it printed."""
    first = next((error.strip().splitlines()[0] for error in test.errors if error.strip()), "")
    if first and _SEE_ABOVE not in first:
        return first
    thrown = next((found.group(1) for line in test.printed if (found := _THROWN.match(line))), "")
    expected = [
        f"{found.group(1)}: {found.group(2).strip()}" for line in test.printed if (found := _EXPECTED.match(line))
    ]
    said = "; ".join([*([thrown] if thrown else []), *expected])
    return said or first or test.result


def _events(text: str) -> list[dict[str, object]]:
    events = []
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _number(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_tests(path: Path, seconds: float | None) -> SuiteSummary | None:
    """What a test run's JSON reporter file says -- None when it wrote none, or no test ran."""
    try:
        if path.stat().st_size > FILE_MAX:
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    tests: dict[int, _Test] = {}
    suites: dict[int, str] = {}
    for event in _events(text):
        kind = event.get("type")
        if kind == "testStart" and isinstance(event.get("test"), dict):
            test = event["test"]
            assert isinstance(test, dict)
            ident = _number(test.get("id"))
            if ident is None:
                continue
            url = test.get("root_url") or test.get("url")
            line = _number(test.get("root_line")) or _number(test.get("line"))
            # A widget test is declared inside flutter_test, which is no place to look: its file is its suite's.
            if not isinstance(url, str) or url.startswith("package:"):
                url, line = suites.get(_number(test.get("suiteID")) or 0), None
            tests[ident] = _Test(str(test.get("name") or ""), _path(url), line)
            continue
        if kind == "suite" and isinstance(event.get("suite"), dict):
            suite = event["suite"]
            assert isinstance(suite, dict)
            ident = _number(suite.get("id"))
            if ident is not None and isinstance(suite.get("path"), str):
                suites[ident] = suite["path"]
            continue
        test_id = _number(event.get("testID"))
        found = tests.get(test_id) if test_id is not None else None
        if found is None:
            continue
        if kind == "error":
            found.errors.append(f"{event.get('error') or ''}\n{event.get('stackTrace') or ''}")
        elif kind == "print":
            found.printed.append(str(event.get("message") or ""))
        elif kind == "testDone":
            found.result = str(event.get("result") or "")
            found.hidden = event.get("hidden") is True
            found.skipped = event.get("skipped") is True
    ended = [test for test in tests.values() if test.result]
    failed = [test for test in ended if test.result != "success"]
    shown = [test for test in ended if not test.hidden]
    if not shown and not failed:
        return None
    failures = []
    for test in failed[:LISTED_MAX]:
        file, line = _place(test)
        failures.append(Failure(test.name, _short(_message(test)), file, line))
    skipped = sum(1 for test in shown if test.skipped and test.result == "success")
    passed = sum(1 for test in shown if test.result == "success") - skipped
    return SuiteSummary(
        passed=not failed,
        passed_count=passed,
        failed_count=len(failed),
        skipped_count=skipped,
        failures=tuple(failures),
        seconds=seconds,
    )
