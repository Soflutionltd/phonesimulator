# SPDX-License-Identifier: Apache-2.0
"""``python -m simtrail``: the same as the ``simtrail`` command."""

from simtrail.cli.main import main

if __name__ == "__main__":  # pragma: no cover - run as a module
    raise SystemExit(main())
