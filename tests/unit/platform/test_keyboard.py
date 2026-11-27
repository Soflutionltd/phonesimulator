# SPDX-License-Identifier: Apache-2.0
"""Which key types each character on the Mac's layout: read once a layout, through a program of its own."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any

import pytest

from phonesimulator.platform import keymap
from phonesimulator.platform.keyboard import (
    KEYMAP_PROGRAM,
    LAYOUT_QUERY,
    US_LAYOUTS,
    VIRTUAL_TO_HID,
    MacKeyboard,
    MacKeyboards,
    parse_keys,
)
from phonesimulator.testing.guards import forbidden

FRENCH = "com.apple.keylayout.French-numerical"
#: What `platform/keymap.py` prints for a few of AZERTY's keys: q where a US keyboard has a, @ alone, { with Option.
AZERTY = {"a": [12, 0], "q": [0, 0], "A": [12, 2], "@": [10, 0], "<": [50, 0], "{": [23, 8], "|": [37, 10]}


class Mac:
    """The commands the keyboard asks the Mac for, answered as a test says."""

    def __init__(self, layout: tuple[int, str], keys: tuple[int, str] = (0, json.dumps(AZERTY))) -> None:
        self.layout, self.keys = layout, keys
        self.asked: list[Sequence[str]] = []

    async def __call__(self, argv: Sequence[str]) -> tuple[int, str]:
        self.asked.append(tuple(argv))
        return self.layout if tuple(argv) == LAYOUT_QUERY else self.keys


def test_a_layouts_keys_are_its_hid_keys_with_shift_and_option() -> None:
    keys = parse_keys(json.dumps(AZERTY))
    assert keys is not None
    assert keys["a"] == (20, False, False) and keys["q"] == (4, False, False) and keys["A"] == (20, True, False)
    assert keys["@"] == (100, False, False) and keys["<"] == (53, False, False)
    assert keys["{"] == (34, False, True) and keys["|"] == (15, True, True)


@pytest.mark.parametrize(
    "out",
    ["", "not json", "[]", json.dumps({"a": "x"}), json.dumps({"a": [99, 0]}), json.dumps({"ab": [0, 0]}), "{}"],
)
def test_what_cannot_be_read_as_keys_is_none(out: str) -> None:
    assert parse_keys(out) is None


async def test_a_layouts_keys_are_read_once_and_the_layout_at_every_typing() -> None:
    mac = Mac((0, FRENCH + "\n"))
    keyboard = MacKeyboards(mac)
    first = await keyboard()
    second = await keyboard()
    assert first == second and first.layout == FRENCH and not first.us
    assert first.keys is not None and first.keys["a"] == (20, False, False)
    program = (sys.executable, "-I", str(KEYMAP_PROGRAM))
    assert mac.asked == [LAYOUT_QUERY, program, LAYOUT_QUERY]


async def test_a_layout_whose_keys_cannot_be_read_has_none_and_is_not_asked_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    mac = Mac((0, "com.apple.keylayout.US\n"), keys=(1, "Traceback"))
    keyboard = MacKeyboards(mac)
    assert await keyboard() == MacKeyboard("com.apple.keylayout.US", None)
    assert (await keyboard()).us and len(mac.asked) == 3
    assert "could not read which keys the com.apple.keylayout.US layout types (exit 1)" in caplog.text


@pytest.mark.parametrize("layout", [(1, ""), (0, "\n")])
async def test_a_layout_that_cannot_be_read_has_no_keys_and_no_program_is_run(layout: tuple[int, str]) -> None:
    mac = Mac(layout)
    assert await MacKeyboards(mac)() == MacKeyboard(None, None)
    assert mac.asked == [LAYOUT_QUERY]


def test_every_text_key_has_a_hid_key_and_no_test_asks_the_real_mac() -> None:
    assert {"com.apple.keylayout.ABC", "com.apple.keylayout.US"} == US_LAYOUTS
    assert set(VIRTUAL_TO_HID) == set(keymap.TEXT_KEYS) - {36, 48}, "all but return and tab, which are not text"
    assert len(set(VIRTUAL_TO_HID.values())) == len(VIRTUAL_TO_HID)
    assert forbidden(LAYOUT_QUERY) == "defaults"


# -- the program ------------------------------------------------------------------------------------------------------


def test_each_character_keeps_the_key_with_the_fewest_modifiers_and_dead_keys_are_left_out() -> None:
    typed = {
        (12, 0): ("a", False), (12, 2): ("A", False), (0, 0): ("q", False), (0, 8): ("a", False),
        (33, 0): ("^", True), (40, 0): ("ab", False), (41, 0): ("\x7f", False),
    }  # fmt: skip
    found = keymap.keys_from(lambda key, modifiers: typed.get((key, modifiers), ("", False)))
    assert found == {"a": [12, 0], "A": [12, 2], "q": [0, 0]}


class FakeCarbon:
    """Carbon and CoreFoundation as `layout_keys` calls them, with a layout or not and a table or not."""

    def __init__(self, source: int, data: int) -> None:
        self.source, self.data = source, data
        self.released: list[int] = []

    def TISCopyCurrentKeyboardLayoutInputSource(self) -> int:
        return self.source

    def TISGetInputSourceProperty(self, source: int, name: object) -> int:
        return self.data

    def CFRelease(self, source: int) -> None:
        self.released.append(source)

    def CFDataGetBytePtr(self, data: int) -> int:
        return data

    def LMGetKbdType(self) -> int:
        return 40

    def UCKeyTranslate(self, *arguments: object) -> int:
        return -25340  # kUCOutputBufferTooSmallErr, or any failure: the key is not kept


@pytest.mark.parametrize(("source", "data", "released"), [(0, 0, []), (7, 0, [7]), (7, 8, [7])])
def test_a_layout_without_a_unicode_table_or_whose_keys_fail_has_no_keys(
    source: int, data: int, released: list[int]
) -> None:
    carbon = FakeCarbon(source, data)

    def libraries() -> tuple[Any, Any, Any]:
        return carbon, carbon, "kTISPropertyUnicodeKeyLayoutData"

    assert keymap.layout_keys(libraries) == {}
    assert carbon.released == released


@pytest.mark.skipif(sys.platform != "darwin", reason="Carbon is the Mac's")
def test_the_macs_own_layout_types_a_space_and_digits_with_one_key_each() -> None:
    # Read-only: the layout is asked what its keys type, and nothing is pressed.
    keys = keymap.layout_keys()
    assert keys[" "] == [49, 0]
    assert all(character in keys for character in "0123456789")
