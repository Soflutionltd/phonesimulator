# SPDX-License-Identifier: Apache-2.0
"""How text reaches a device: typed with the keys the Mac's layout has for it, else pasted."""

from __future__ import annotations

import pytest

from simtrail.core import gestures
from simtrail.core.text_entry import paste_asked, paste_prompt_allow, paste_refused, text_entry
from simtrail.perception.snapshot import Element
from simtrail.platform.keyboard import LayoutKeys
from simtrail.testing.fakes import FakeKeyboard

#: A few of AZERTY's keys, as HID keys: a where a US keyboard has q, é alone, { with Option.
AZERTY: LayoutKeys = {"a": (20, False, False), "z": (26, False, False), "é": (31, False, False), "{": (34, False, True)}


async def test_auto_types_with_the_macs_own_layout_where_it_has_every_key() -> None:
    keyboard = FakeKeyboard(keys=AZERTY)
    typed = await text_entry("azé{", "auto", keyboard)
    assert typed.events == gestures.typed("azé{", AZERTY) and typed.pasted == "" and keyboard.asked == 1
    events = [(event.code, event.phase) for _, event in typed.events]
    assert events[:2] == [(20, "down"), (20, "up")] and (gestures.OPTION_KEY, "down") in events
    pasted = await text_entry("café", "auto", keyboard)
    assert (pasted.events, pasted.pasted) == (gestures.paste(), "café")
    assert pasted.why_pasted == "'c' has no key on the Mac's com.apple.keylayout.French layout"


async def test_auto_types_with_a_us_keyboard_on_a_us_layout_whose_keys_were_not_read_and_pastes_on_another() -> None:
    us, other = FakeKeyboard(us=True), FakeKeyboard(us=False)
    typed = await text_entry("Hi!", "auto", us)
    assert typed.events == gestures.typed("Hi!") and typed.pasted == "" and us.asked == 1
    pasted = await text_entry("Hi!", "auto", other)
    assert pasted.events == gestures.paste() and pasted.pasted == "Hi!" and other.asked == 1
    assert (typed.why_pasted, pasted.why_pasted) == ("", "the Mac's keyboard layout could not be read")


async def test_keys_types_without_asking_and_paste_pastes_without_asking() -> None:
    keyboard = FakeKeyboard(us=False)
    assert (await text_entry("wifi", "keys", keyboard)).events == gestures.typed("wifi")
    pasted = await text_entry("wifi", "paste", keyboard)
    assert (pasted.pasted, pasted.why_pasted) == ("wifi", "device.typing says to paste")
    assert keyboard.asked == 0


@pytest.mark.parametrize("typing", ["auto", "keys"])
async def test_text_with_a_character_no_key_types_is_pasted_whole(typing: str) -> None:
    keyboard = FakeKeyboard(us=True)
    entry = await text_entry("café 😀", typing, keyboard)
    assert (entry.events, entry.pasted) == (gestures.paste(), "café 😀")
    assert entry.why_pasted == "'é' has no key on a US keyboard"


async def test_a_new_line_is_return_on_any_layout() -> None:
    entry = await text_entry("a\na", "auto", FakeKeyboard(keys=AZERTY))
    assert entry.events == gestures.typed("a\na", AZERTY) and entry.pasted == ""


@pytest.mark.parametrize(
    ("runtime", "refused"),
    [
        ("iOS 27.0", True),
        ("iOS 28.1", True),
        ("iOS 26.5", False),
        ("iOS 18.6", False),
        ("watchOS 27.0", False),
        ("", False),
    ],
)
def test_a_paste_is_refused_without_asking_from_ios_27(runtime: str, refused: bool) -> None:
    assert paste_refused(runtime) is refused


def test_ios_16_to_26_ask_to_allow_a_paste_and_no_other_runtime_does() -> None:
    assert [paste_asked(runtime) for runtime in ("iOS 15.5", "iOS 16.0", "iOS 26.5", "iOS 27.0", "Android 16")] == [
        False,
        True,
        True,
        False,
        False,
    ]


def _element(kind: str, label: str) -> Element:
    return Element(None, kind, label, None, 0, 0)


def test_the_paste_prompt_is_known_by_the_pasteboard_bridge_it_names_and_its_allow_button_found() -> None:
    message = _element("text", "« Notes » souhaite coller un élément depuis « CoreSimulatorBridge »")
    refuse, allow = _element("button", "Ne pas autoriser le collage"), _element("button", "Autoriser  le collage")
    assert paste_prompt_allow([message, refuse, allow]) is allow, "by its name, however it is spaced"
    unknown = [message, _element("button", "いいえ"), _element("button", "はい")]
    assert paste_prompt_allow(unknown) is unknown[2], "else the second of its two buttons"
    assert paste_prompt_allow([*unknown, _element("button", "あとで")]) is None, "never a guess among three"
    other = [_element("text", "Allow Notes to use your location?"), _element("button", "Allow Paste")]
    assert paste_prompt_allow(other) is None, "another alert is left alone"
    named = [_element("button", "CoreSimulatorBridge"), refuse, allow]
    assert paste_prompt_allow(named) is None, "only a message naming the bridge makes the prompt"
