# SPDX-License-Identifier: Apache-2.0
"""A contact sheet: screenshots side by side, each scaled to one height and captioned."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from simtrail.core.contact_sheet import CAPTION_MAX, CELL_HEIGHT, GAP, Cell, _caption, contact_sheet


def jpeg(width: int, height: int) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(out, format="JPEG")
    return out.getvalue()


def test_cells_are_laid_out_a_row_at_a_time_each_as_tall_as_the_others() -> None:
    phone, tablet = Cell(jpeg(402, 874), "iPhone · light"), Cell(jpeg(1032, 1376), "iPad · dark")
    sheet = contact_sheet([phone, tablet, phone], 2)
    widest = round(1032 * CELL_HEIGHT / 1376)
    assert (sheet.width, sheet.height) == (GAP + (widest + GAP) * 2, GAP + (CELL_HEIGHT + 28 + GAP) * 2)
    with Image.open(io.BytesIO(sheet.jpeg)) as picture:
        assert picture.format == "JPEG" and picture.size == (sheet.width, sheet.height)
    single = contact_sheet([phone], 2)
    assert single.width == GAP + round(402 * CELL_HEIGHT / 874) + GAP, "one cell is as wide as itself"


def test_a_long_caption_is_cut_and_an_empty_sheet_is_refused() -> None:
    long = _caption("iPhone 17 Pro Max " * 10)
    assert len(long) == CAPTION_MAX and long.endswith("…")
    assert _caption("  iPad   · dark ") == "iPad · dark"
    with pytest.raises(ValueError, match="at least one cell"):
        contact_sheet([], 2)
