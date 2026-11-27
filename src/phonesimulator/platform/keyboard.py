# SPDX-License-Identifier: Apache-2.0
"""Which key types each character on the Mac's keyboard layout -- AZERTY, QWERTZ, US -- so text is typed, not pasted.

A key PhoneSimulator presses on a simulator goes through the simulator's keyboard layout, which follows the Mac's
current input source: with a French layout chosen, the key a US keyboard has "q" on types "a", and with a Ukrainian one
the keys for "wifi" type "цшаш". So the keys are found for the layout in use: macOS says which virtual key, with Shift
or Option, types each character (`platform/keymap.py`, run as a program of its own), and each virtual key is the HID key
a simulator is sent for it (`VIRTUAL_TO_HID`). What a layout types is read once for each layout and kept; the layout
itself is read at every typing, since a person switches layouts as they go.

The layout is read with ``defaults``, which asks the preferences daemon rather than a file it may not have written
yet. A layout that cannot be read, or whose keys cannot be, has no keys here: `core/text_entry.py` then types only on
a US or ABC layout, as before, and pastes otherwise.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from phonesimulator.platform import process
from phonesimulator.platform.macos import LAYOUT_QUERY as LAYOUT_QUERY
from phonesimulator.platform.macos import keyboard_layout

logger = logging.getLogger(__name__)

#: The Mac keyboard layouts whose keys are where a US keyboard's are, by input source id.
US_LAYOUTS = frozenset({"com.apple.keylayout.ABC", "com.apple.keylayout.US"})
#: The program that reads a layout's keys, run with this Python.
KEYMAP_PROGRAM = Path(__file__).with_name("keymap.py")
#: Carbon's modifier bits as `platform/keymap.py` prints them.
SHIFT_BIT, OPTION_BIT = 0x02, 0x08

#: Each Mac virtual key that types text, as the HID usage id a simulator is sent for it: the HID key macOS maps to
#: that virtual key, so the layout makes of it what it makes of the Mac's own key.
VIRTUAL_TO_HID = {
    0: 4, 1: 22, 2: 7, 3: 9, 4: 11, 5: 10, 6: 29, 7: 27, 8: 6, 9: 25, 10: 100, 11: 5, 12: 20, 13: 26, 14: 8, 15: 21,
    16: 28, 17: 23, 18: 30, 19: 31, 20: 32, 21: 33, 22: 35, 23: 34, 24: 46, 25: 38, 26: 36, 27: 45, 28: 37, 29: 39,
    30: 48, 31: 18, 32: 24, 33: 47, 34: 12, 35: 19, 37: 15, 38: 13, 39: 52, 40: 14, 41: 51, 42: 49, 43: 54, 44: 56,
    45: 17, 46: 16, 47: 55, 49: 44, 50: 53,
}  # fmt: skip

#: A character's key: its HID usage id, and whether Shift and Option are held for it.
Key = tuple[int, bool, bool]
LayoutKeys = Mapping[str, Key]


@dataclass(frozen=True)
class MacKeyboard:
    """The Mac's keyboard layout, by input source id -- None when it cannot be read -- and the key for each character
    it types, when they could be read."""

    layout: str | None
    keys: LayoutKeys | None

    @property
    def us(self) -> bool:
        return self.layout in US_LAYOUTS


#: The Mac's keyboard as it is now; `MacKeyboards`, or a fake.
KeyboardRead = Callable[[], Awaitable[MacKeyboard]]


def parse_keys(out: str) -> LayoutKeys | None:
    """What `platform/keymap.py` printed, as each character's HID key and modifiers; None when it is not readable."""
    try:
        table: object = json.loads(out)
        if not isinstance(table, dict):
            return None
        keys: dict[str, Key] = {}
        for character, (virtual, modifiers) in table.items():
            usage = VIRTUAL_TO_HID.get(int(virtual))
            if usage is not None and isinstance(character, str) and len(character) == 1:
                keys[character] = (usage, bool(int(modifiers) & SHIFT_BIT), bool(int(modifiers) & OPTION_BIT))
        return keys or None
    except (ValueError, TypeError):
        return None


class MacKeyboards:
    """The Mac's keyboard, read at each typing, with each layout's keys read once and kept."""

    def __init__(self, run: process.Runner = process.run) -> None:
        self._run = run
        self._known: dict[str, LayoutKeys | None] = {}

    async def __call__(self) -> MacKeyboard:
        code, out = await keyboard_layout(self._run)
        layout = out.strip() if code == 0 else ""
        if not layout:
            return MacKeyboard(None, None)
        if layout not in self._known:
            self._known[layout] = await self._read(layout)
        return MacKeyboard(layout, self._known[layout])

    async def _read(self, layout: str) -> LayoutKeys | None:
        code, out = await self._run((sys.executable, "-I", str(KEYMAP_PROGRAM)))
        keys = parse_keys(out) if code == 0 else None
        if keys is None:
            logger.warning("could not read which keys the %s layout types (exit %s): its text is pasted", layout, code)
        return keys


#: The Mac's keyboard for every daemon that is given no other.
MAC_KEYBOARD = MacKeyboards()
