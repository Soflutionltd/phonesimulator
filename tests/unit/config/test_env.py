# SPDX-License-Identifier: Apache-2.0
"""Settings from PHONESIMULATOR_* variables: parsed by each setting's rule, and a bad one reported, not used."""

from __future__ import annotations

from phonesimulator.config.env import from_env


def test_variables_are_parsed_by_their_setting() -> None:
    values, problems = from_env(
        {
            "PHONESIMULATOR_ENABLED": "no",
            "PHONESIMULATOR_STREAM_FPS": "60",
            "PHONESIMULATOR_SECURITY_ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:5173",
            "PHONESIMULATOR_CONNECTORS_PREFERRED": "simctl",
            "PHONESIMULATOR_STATE_DIR": "/not/a/setting",
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
            "PHONESIMULATOR_STREAM_FPS": "fast",
            "PHONESIMULATOR_DEVICE_MAX_BOOTED": "99",
            "PHONESIMULATOR_AGENT_CURSOR": "maybe",
        }
    )
    assert values == {}
    assert problems == [
        "PHONESIMULATOR_DEVICE_MAX_BOOTED must be a whole number between 1 and 8",
        "PHONESIMULATOR_STREAM_FPS must be a whole number between 5 and 60",
        "PHONESIMULATOR_AGENT_CURSOR must be true or false",
    ]
