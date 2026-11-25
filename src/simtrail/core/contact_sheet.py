# SPDX-License-Identifier: Apache-2.0
"""A contact sheet: several screenshots side by side in one picture, each captioned, to compare at a glance.

`sim_matrix` lays its screenshots out a row per device and a column per appearance. Each is scaled to one height,
keeping its shape, so an iPad beside an iPhone is as tall and wider; its caption goes under it. Pillow -- which Simtrail
already decodes screenshots with -- draws it, with its own font, so nothing is read from the Mac's fonts.
"""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

#: How tall each screenshot is drawn, in pixels, and the room around it and its caption.
CELL_HEIGHT = 480
GAP = 16
CAPTION_HEIGHT = 28
FONT_SIZE = 15
#: The most characters of a caption: a longer one is cut with "…".
CAPTION_MAX = 48
BACKGROUND = (244, 244, 245)
INK = (24, 24, 27)
QUALITY = 85


@dataclass(frozen=True)
class Cell:
    """One screenshot on the sheet, as the JPEG it was taken as, and what is written under it."""

    jpeg: bytes
    caption: str


@dataclass(frozen=True)
class Sheet:
    jpeg: bytes
    width: int
    height: int


def _caption(caption: str) -> str:
    flat = " ".join(caption.split())
    return flat if len(flat) <= CAPTION_MAX else flat[: CAPTION_MAX - 1].rstrip() + "…"


def contact_sheet(cells: Sequence[Cell], columns: int) -> Sheet:
    """The cells laid out `columns` to a row, in order, each scaled to `CELL_HEIGHT` and captioned, as a JPEG."""
    if not cells or columns < 1:
        raise ValueError("a contact sheet needs at least one cell and one column")
    pictures = []
    for cell in cells:
        with Image.open(io.BytesIO(cell.jpeg)) as opened:
            picture = opened.convert("RGB")
        width = max(1, round(picture.width * CELL_HEIGHT / picture.height))
        pictures.append(picture.resize((width, CELL_HEIGHT), Image.Resampling.LANCZOS))
    rows = math.ceil(len(cells) / columns)
    widest = max(picture.width for picture in pictures)
    cell_width = widest + GAP
    cell_height = CELL_HEIGHT + CAPTION_HEIGHT + GAP
    sheet = Image.new("RGB", (GAP + cell_width * min(columns, len(cells)), GAP + cell_height * rows), BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=FONT_SIZE)
    for index, (cell, picture) in enumerate(zip(cells, pictures, strict=True)):
        row, column = divmod(index, columns)
        left = GAP + column * cell_width + (widest - picture.width) // 2
        top = GAP + row * cell_height
        sheet.paste(picture, (left, top))
        draw.text((GAP + column * cell_width, top + CELL_HEIGHT + 6), _caption(cell.caption), fill=INK, font=font)
    out = io.BytesIO()
    sheet.save(out, format="JPEG", quality=QUALITY)
    return Sheet(out.getvalue(), sheet.width, sheet.height)
