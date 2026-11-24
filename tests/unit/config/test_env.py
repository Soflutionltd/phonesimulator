# SPDX-License-Identifier: Apache-2.0
"""Settings from SIMTRAIL_* variables: parsed by each setting's rule, and a bad one reported, not used."""

from __future__ import annotations

from simtrail.config.env import from_env


def test_variables_are_parsed_by_their_setting() -> None:
    values, problems = from_env(
        {
            "SIMTRAIL_ENABLED": "no",
            "SIMTRAIL_STREAM_FPS": "60",
            "SIMTRAIL_SECURITY_ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:5173",
            "SIMTRAIL_CONNECTORS_PREFERRED": "simctl",
            "SIMTRAIL_STATE_DIR": "/not/a/setting",
            "PATH": "/usr/bin",
        }
    )
    assert values == {
        "enabled": False,
        "connector": "simctl",
        "stream_fps": 60,
        "allowed_origins": ("http://localhost:3000", "http://127.0.0.1:5173"),
    }
    assert problems == []


def test_a_variable_that_does_not_parse_or_is_refused_is_reported_and_left_out() -> None:
    values, problems = from_env(
        {"SIMTRAIL_STREAM_FPS": "fast", "SIMTRAIL_DEVICE_MAX_BOOTED": "99", "SIMTRAIL_AGENT_CURSOR": "maybe"}
    )
    assert values == {}
    assert problems == [
        "SIMTRAIL_DEVICE_MAX_BOOTED must be a whole number between 1 and 8",
        "SIMTRAIL_STREAM_FPS must be a whole number between 5 and 60",
        "SIMTRAIL_AGENT_CURSOR must be true or false",
    ]
