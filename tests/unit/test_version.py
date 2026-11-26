# SPDX-License-Identifier: Apache-2.0
import re

import rocketwright


def test_version_is_semantic() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[.-]?(?:a|b|rc|dev)\d+)?", rocketwright.__version__)
