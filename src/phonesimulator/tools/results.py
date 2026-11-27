# SPDX-License-Identifier: Apache-2.0
"""A tool's answer, shaped as MCP's: content blocks, and whether it is an error.

Text first: an image is sent only when one was asked for, because an image costs an agent far more than the lines that
say what is on the screen (`perception.snapshot`).
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from typing import Any

Result = dict[str, Any]
#: What a call on a device shut down outside PhoneSimulator answers, instead of what the device's tool said of it.
SHUT_DOWN = "The device is shut down. sim_device boot starts it."


class ToolRefused(Exception):
    """A call a tool will not make, said so the agent knows what to do instead."""


def text(value: str, *, error: bool = False, data: dict[str, Any] | None = None) -> Result:
    """A tool's answer as text -- and, with `data`, as structured content too. That structured content carries the text
    as well (``text``): a client that shows only the structured part when there is one -- Claude Code does -- would
    otherwise lose what the text says, the screen after the steps among it, and call again to see it."""
    result: Result = {"content": [{"type": "text", "text": value}], "isError": error}
    if data is not None:
        result["structuredContent"] = data if _says_only(value, data) else {**data, "text": value}
    return result


def _says_only(value: str, data: dict[str, Any]) -> bool:
    """Whether the text is the structured content itself, as JSON -- a flow shown -- so carrying it twice says
    nothing."""
    try:
        return bool(json.loads(value) == data)
    except ValueError:
        return False


def images(caption: str, jpegs: Sequence[bytes]) -> Result:
    """A caption, then each JPEG."""
    blocks = [
        {"type": "image", "data": base64.b64encode(jpeg).decode("ascii"), "mimeType": "image/jpeg"} for jpeg in jpegs
    ]
    return {"content": [{"type": "text", "text": caption}, *blocks], "isError": False}
