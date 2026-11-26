# SPDX-License-Identifier: Apache-2.0
"""Settings from ROCKETWRIGHT_* variables: parsed by each setting's rule, and a bad one reported, not used."""

from __future__ import annotations

from rocketwright.config.env import from_env


def test_variables_are_parsed_by_their_setting() -> None:
    values, problems = from_env(
        {
            "ROCKETWRIGHT_ENABLED": "no",
            "ROCKETWRIGHT_STREAM_FPS": "60",
            "ROCKETWRIGHT_SECURITY_ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:5173",
            "ROCKETWRIGHT_CONNECTORS_PREFERRED": "simctl",
            "ROCKETWRIGHT_STATE_DIR": "/not/a/setting",
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
        {
            "ROCKETWRIGHT_STREAM_FPS": "fast",
            "ROCKETWRIGHT_DEVICE_MAX_BOOTED": "99",
            "ROCKETWRIGHT_AGENT_CURSOR": "maybe",
        }
    )
    assert values == {}
    assert problems == [
        "ROCKETWRIGHT_DEVICE_MAX_BOOTED must be a whole number between 1 and 8",
        "ROCKETWRIGHT_STREAM_FPS must be a whole number between 5 and 60",
        "ROCKETWRIGHT_AGENT_CURSOR must be true or false",
    ]
