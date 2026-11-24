# SPDX-License-Identifier: Apache-2.0
import re

import simtrail


def test_version_is_semantic() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.-]?(?:a|b|rc|dev)\d+)?", simtrail.__version__)
