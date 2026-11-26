# SPDX-License-Identifier: Apache-2.0
"""How text reaches a device: typed as key presses, or put on its pasteboard and pasted.

Both a viewer's text and an agent's ``type`` step come here, so they arrive the same way. Measured on iOS 26.5 and
27.0 with a probe app (#27):

* **Pasting** keeps every character exactly, but iOS 26 asks "Allow Paste" first, and iOS 27 refuses the paste
  silently -- the pasteboard holds the text and Cmd+V arrives, yet nothing appears.
* **Typing keys** works on both without a prompt, and needs no permission. A key goes through the Mac's keyboard
  layout, so each character is typed with the key that layout has for it -- AZERTY's, QWERTZ's, a US keyboard's
  (`platform/keyboard.py`) -- and iOS applies the keyboard's own habits as it would for a person: smart punctuation
  turns ``'`` into ``’`` and ``--`` into ``—`` in a field that allows it. Neither iOS autocorrected or capitalized what
  was typed on the hardware keyboard.

So ``device.typing`` decides, per scope:

* ``auto`` (the default) types the text when the Mac's layout has a key for every character -- read from the layout
  itself, or a US keyboard's on a US or ABC layout whose keys could not be read -- and pastes it otherwise: an emoji,
  an accent typed with a dead key;
* ``keys`` always types with a US keyboard's keys -- for a US-shaped layout Rocketwright cannot read -- and pastes the
  rest;
* ``paste`` always pastes, for text that must arrive character for character, on iOS 26 and earlier.

On iOS 16 to 26 the "Allow Paste" prompt a simulator shows for Rocketwright's own paste names where the text comes from,
``CoreSimulatorBridge`` -- the simulator's pasteboard bridge, whatever the system's language -- so it is told from any
other alert, and allowed (`paste_prompt_allow`): left alone, it hides the screen and the text never arrives.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from rocketwright.core import gestures
from rocketwright.perception.snapshot import Element
from rocketwright.platform.keyboard import KeyboardRead

#: The first iOS that refuses a paste Rocketwright sends, without asking the person.
PASTE_REFUSED_FROM = 27
#: The first iOS that asks the person to Allow Paste from another app.
PASTE_ASKED_FROM = 16
#: What the simulator's paste prompt names as where the text comes from, in every language.
PASTE_SOURCE = "CoreSimulatorBridge"
#: The prompt's button that allows the paste, in the languages it was read in (lower case). Its other button refuses.
ALLOW_PASTE = frozenset(
    {
        "allow paste",
        "autoriser le collage",
        "einsetzen erlauben",
        "permitir pegar",
        "consenti incolla",
        "plakken toestaan",
        "permitir colar",
    }
)

_IOS = re.compile(r"\AiOS (?P<major>\d+)")


@dataclass(frozen=True)
class TextEntry:
    """The events that enter the text, the text to put on the pasteboard first -- "" when it is typed -- and why it
    is pasted, said so an agent can tell what to change; when a character had no key, the keyboard it had none on,
    so a password's answer can say so without naming the character."""

    events: list[gestures.Timed]
    pasted: str = ""
    why_pasted: str = ""
    keyless_on: str = ""


async def text_entry(text: str, typing: str, keyboard: KeyboardRead) -> TextEntry:
    """How `text` goes in, under the scope's ``device.typing``. The Mac's layout is only asked about when it decides."""
    if typing == "paste":
        return TextEntry(gestures.paste(), text, "device.typing says to paste")
    if typing == "keys":
        layout, keys = gestures.US_KEYS, "a US keyboard"
    else:
        board = await keyboard()
        if board.keys is not None:
            layout, keys = board.keys, f"the Mac's {board.layout} layout"
        elif board.us:
            layout, keys = gestures.US_KEYS, "a US keyboard"
        else:
            return TextEntry(gestures.paste(), text, "the Mac's keyboard layout could not be read")
    events = gestures.typed(text, layout)
    if events is not None:
        return TextEntry(events)
    keyless = next(character for character in text if character != "\n" and character not in layout)
    return TextEntry(gestures.paste(), text, f"{keyless!r} has no key on {keys}", keys)


def paste_refused(runtime: str) -> bool:
    """Whether a device on this runtime -- ``iOS 27.0`` -- refuses a paste it did not ask for."""
    match = _IOS.match(runtime)
    return match is not None and int(match.group("major")) >= PASTE_REFUSED_FROM


def paste_asked(runtime: str) -> bool:
    """Whether a device on this runtime -- ``iOS 26.5`` -- may ask to Allow Paste rather than take or refuse it."""
    match = _IOS.match(runtime)
    return match is not None and PASTE_ASKED_FROM <= int(match.group("major")) < PASTE_REFUSED_FROM


def _said(element: Element) -> tuple[str, ...]:
    """An element's whole label and value -- never cut, as its line may be."""
    return element.says or (element.label, element.value or "")


def names_bridge(element: Element) -> bool:
    """Whether an element says the simulator's pasteboard bridge is where a paste comes from."""
    return any(PASTE_SOURCE in text for text in _said(element))


def paste_prompt_allow(elements: Sequence[Element]) -> Element | None:
    """The button that allows Rocketwright's paste, when the screen shows the prompt asking for it: an alert naming
    `PASTE_SOURCE`, with its allow button by name -- else, of its two buttons, the second, as iOS lays them out
    (Don't Allow first). None when no such prompt is on the screen."""
    if not any(names_bridge(element) for element in elements if element.kind != "button"):
        return None
    buttons = [element for element in elements if element.kind == "button"]
    named = [button for button in buttons if " ".join(_said(button)[0].split()).casefold() in ALLOW_PASTE]
    if named:
        return named[0]
    return buttons[1] if len(buttons) == 2 else None
