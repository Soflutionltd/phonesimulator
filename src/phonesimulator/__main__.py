# SPDX-License-Identifier: Apache-2.0
"""``python -m phonesimulator``: the same as the ``phonesimulator`` command."""

from phonesimulator.cli.main import main

if __name__ == "__main__":  # pragma: no cover - run as a module
    raise SystemExit(main())
