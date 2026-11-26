# SPDX-License-Identifier: Apache-2.0
"""What a Flutter build, hot reload and test run said, read as an Xcode build's and test run's are."""

from __future__ import annotations

from pathlib import Path

import pytest

from rocketwright.build import flutter_log
from rocketwright.build.flutter_log import compile_errors, read_log, read_tests
from rocketwright.build.xcresult import Failure, Issue, SuiteSummary
from rocketwright.testing.fakes import fixture
from rocketwright.testing.flutter import COMPILE_ERROR


def read(path: Path, seconds: float | None = None) -> SuiteSummary:
    summary = read_tests(path, seconds)
    assert summary is not None
    return summary


def test_an_ios_build_that_does_not_compile_names_the_dart_error_inside_xcodes_output() -> None:
    summary = read_log(fixture("flutter-build-ios-error.log"), succeeded=False, seconds=9.1)
    assert summary.errors == (Issue("error", "Member not found: 'nope'.", "lib/screens/list_screen.dart", 96, 35),)
    assert [warning.where(None) for warning in summary.warnings] == ["lib/screens/list_screen.dart:12:8"]
    assert (summary.error_count, summary.warning_count, summary.seconds) == (1, 1, 9.1)


def test_a_failure_no_compiler_explains_is_said_by_gradle_xcode_or_flutter_itself() -> None:
    gradle = "* What went wrong:\nExecution failed for task ':app:compileDebugKotlin'.\n> Compilation error\n\n* Try:\n"
    assert read_log(gradle, succeeded=False, seconds=None).errors[0].message == (
        "Execution failed for task ':app:compileDebugKotlin'. Compilation error"
    )
    xcode = 'Error (Xcode): Signing for "Runner" requires a development team.\n'
    assert read_log(xcode, succeeded=False, seconds=None).errors[0].message.startswith("Signing for")
    said = "Error: No pubspec.yaml file found.\nEncountered error while building for simulator.\n"
    assert read_log(said, succeeded=False, seconds=None).errors[0].message == (
        "Encountered error while building for simulator."
    )
    assert read_log("Error: No pubspec.yaml file found.\n", succeeded=False, seconds=None).errors[0].message == (
        "No pubspec.yaml file found."
    )
    assert read_log("", succeeded=False, seconds=None).errors[0].message == "the Flutter build failed; the log says why"
    assert read_log("", succeeded=True, seconds=None).errors == ()


def test_a_hot_reloads_compile_errors_are_read_from_what_flutter_printed() -> None:
    assert compile_errors(COMPILE_ERROR) == [
        Issue("error", "Expected an identifier, but got ','.", "lib/main.dart", 133, 46)
    ]
    assert compile_errors(["Reloaded 1 of 865 libraries in 167ms."]) == []


def test_unit_tests_are_counted_and_a_failure_is_placed_at_the_test_files_own_frame(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(fixture("flutter-unit-results.json"))
    summary = read(results, 1.2)
    assert not summary.passed
    assert (summary.passed_count, summary.failed_count, summary.skipped_count, summary.seconds) == (2, 1, 1, 1.2)
    assert summary.failures == (Failure("adds an item", "Expected: empty", "test/list_test.dart", 24),)


def test_a_widget_tests_printed_failure_is_its_message_and_its_suite_its_file(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(fixture("flutter-integration-results.json"))
    (failure,) = read(results).failures
    assert failure.message.startswith("TestFailure; Expected: exactly one matching candidate; Actual: _TextWidget")
    assert (failure.file, failure.line) == ("/Users/dev/groceries/integration_test/app_test.dart", 27)
    # Printed without a frame of the test file's own: it is placed in its suite's file.
    lines = fixture("flutter-integration-results.json").splitlines()
    results.write_text("\n".join(line for line in lines if "app_test.dart:27" not in line and "line 27" not in line))
    (failure,) = read(results).failures
    assert (failure.file, failure.line) == ("/Users/dev/groceries/integration_test/app_test.dart", None)


def test_a_test_file_that_does_not_load_fails_and_a_run_with_no_tests_says_none(tmp_path: Path) -> None:
    results = tmp_path / "results.json"
    results.write_text(
        '{"suite":{"id":0,"path":"/p/test/a_test.dart"},"type":"suite"}\n'
        '{"test":{"id":1,"name":"loading /p/test/a_test.dart","suiteID":0,"url":null},"type":"testStart"}\n'
        '{"testID":1,"error":"Failed to load: test/a_test.dart:3:1: Error: Expected \';\'.","stackTrace":"",'
        '"type":"error"}\n'
        '{"testID":1,"result":"error","hidden":true,"type":"testDone"}\nnot json\n[1]\n'
        '{"test":{"name":"no id"},"type":"testStart"}\n{"testID":9,"result":"success","type":"testDone"}\n'
        '{"suite":{"id":1},"type":"suite"}\n'
        '{"test":{"id":2,"name":"adds","suiteID":1,"url":"test/b_test.dart","line":4},"type":"testStart"}\n'
        '{"testID":2,"messageType":"skip","type":"messageX"}\n{"testID":2,"result":"success","type":"testDone"}\n'
        '{"test":{"id":3,"name":"of no suite","suiteID":5,"url":null},"type":"testStart"}\n'
        '{"testID":3,"result":"success","type":"testDone"}\n'
    )
    summary = read(results)
    assert (summary.passed_count, summary.failed_count) == (2, 1)
    assert (summary.failures[0].file, summary.failures[0].line) == ("test/a_test.dart", 3)
    results.write_text('{"type":"done","success":true}\n')
    assert read_tests(results, None) is None
    assert read_tests(tmp_path / "missing.json", None) is None


def test_a_result_file_far_too_large_is_not_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = tmp_path / "results.json"
    results.write_text(fixture("flutter-unit-results.json"))
    monkeypatch.setattr(flutter_log, "FILE_MAX", 10)
    assert read_tests(results, None) is None
