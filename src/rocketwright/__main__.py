# SPDX-License-Identifier: Apache-2.0
"""``python -m rocketwright``: the same as the ``rocketwright`` command."""

from rocketwright.cli.main import main

if __name__ == "__main__":  # pragma: no cover - run as a module
    raise SystemExit(main())
