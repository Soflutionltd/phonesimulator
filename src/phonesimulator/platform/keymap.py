# SPDX-License-Identifier: Apache-2.0
"""Which key, and which of Shift and Option, types each character in the Mac's current keyboard layout.

Run as a program of its own (`platform/keyboard.py` starts it), never imported by the daemon: the Text Input Sources
calls it makes belong on a process's main thread, and a fault in them ends this short process, not the daemon. It
prints one JSON object, each character to ``[virtual key, modifiers]`` -- modifiers 0, 2 for Shift, 8 for Option, 10
for both, as Carbon counts them -- or ``{}`` when the layout has no Unicode table (an input method). A dead key, that
types nothing until the next key, is left out: text with its character is pasted.

The standard library alone: ``ctypes`` over Carbon's ``UCKeyTranslate``, the call macOS itself types with.
"""

from __future__ import annotations

import ctypes
import ctypes.util
import json
import sys
from collections.abc import Callable
from typing import Any

#: The keys of a Mac keyboard that type text, by virtual key code: every letter, digit and punctuation key and space.
TEXT_KEYS = range(0, 51)
#: Carbon's modifier states, shifted down by 8 as `UCKeyTranslate` takes them: none, Shift, Option, both.
MODIFIERS = (0, 0x02, 0x08, 0x0A)
_KEY_DOWN = 0

#: What one key types with some modifiers held: its characters, and whether it is a dead key waiting for the next.
Translate = Callable[[int, int], tuple[str, bool]]


def keys_from(translate: Translate) -> dict[str, list[int]]:
    """Each character one key types alone, and the fewest modifiers that type it -- dead keys, and keys that type
    several characters or none printable, left out."""
    found: dict[str, list[int]] = {}
    for modifiers in MODIFIERS:
        for key in TEXT_KEYS:
            chars, dead = translate(key, modifiers)
            if not dead and len(chars) == 1 and chars.isprintable():
                found.setdefault(chars, [key, modifiers])
    return found


def _carbon() -> tuple[Any, Any, Any]:
    """Carbon and CoreFoundation, typed for the calls made here, and the Unicode key layout property's name."""
    carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))
    foundation = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    carbon.TISCopyCurrentKeyboardLayoutInputSource.restype = ctypes.c_void_p
    carbon.TISGetInputSourceProperty.restype = ctypes.c_void_p
    carbon.TISGetInputSourceProperty.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    carbon.LMGetKbdType.restype = ctypes.c_uint8
    carbon.UCKeyTranslate.restype = ctypes.c_int32
    carbon.UCKeyTranslate.argtypes = [
        ctypes.c_void_p, ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32), ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
        ctypes.POINTER(ctypes.c_uint16),
    ]  # fmt: skip
    foundation.CFDataGetBytePtr.restype = ctypes.c_void_p
    foundation.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
    foundation.CFRelease.argtypes = [ctypes.c_void_p]
    return carbon, foundation, ctypes.c_void_p.in_dll(carbon, "kTISPropertyUnicodeKeyLayoutData")


def layout_keys(libraries: Callable[[], tuple[Any, Any, Any]] = _carbon) -> dict[str, list[int]]:
    """`keys_from` the Mac's current keyboard layout, or ``{}`` when it has no Unicode table."""
    carbon, foundation, unicode_table = libraries()
    source = carbon.TISCopyCurrentKeyboardLayoutInputSource()
    if not source:
        return {}
    try:
        data = carbon.TISGetInputSourceProperty(source, unicode_table)
        if not data:
            return {}
        layout = foundation.CFDataGetBytePtr(data)
        keyboard_type = carbon.LMGetKbdType()

        def translate(key: int, modifiers: int) -> tuple[str, bool]:
            dead = ctypes.c_uint32(0)
            length = ctypes.c_ulong(0)
            chars = (ctypes.c_uint16 * 4)()
            failed = carbon.UCKeyTranslate(
                layout, key, _KEY_DOWN, modifiers, keyboard_type, 0,
                ctypes.byref(dead), len(chars), ctypes.byref(length), chars,
            )  # fmt: skip
            if failed:
                return "", False
            return "".join(chr(chars[index]) for index in range(length.value)), bool(dead.value)

        return keys_from(translate)
    finally:
        foundation.CFRelease(source)


if __name__ == "__main__":
    json.dump(layout_keys(), sys.stdout, ensure_ascii=False)
