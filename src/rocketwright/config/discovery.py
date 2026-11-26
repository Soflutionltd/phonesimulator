# SPDX-License-Identifier: Apache-2.0
"""Where a standalone install's config.toml is: ``ROCKETWRIGHT_CONFIG``, else in the Application Support folder."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from rocketwright.storage.app_support import state_dir

CONFIG_ENV = "ROCKETWRIGHT_CONFIG"
CONFIG_FILE = "config.toml"


def config_path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    env = os.environ if env is None else env
    explicit = env.get(CONFIG_ENV, "").strip()
    return Path(explicit).expanduser() if explicit else state_dir(env, home) / CONFIG_FILE
