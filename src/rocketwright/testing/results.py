# SPDX-License-Identifier: Apache-2.0
"""What a test reads of a tool's structured content: its fields, once its ``text`` is checked to be the answer's
text."""

from __future__ import annotations

from typing import Any


def structured(result: dict[str, Any]) -> dict[str, Any]:
    """The structured content of a tool's answer without its ``text`` -- asserted first to be the answer's text, as
    every structured answer carries it."""
    data = dict(result["structuredContent"])
    said = "\n".join(block["text"] for block in result["content"] if block.get("type") == "text")
    assert data.pop("text") == said, "the structured content carries the answer's text"
    return data
