# SPDX-License-Identifier: Apache-2.0
"""What `sim_login` typed reads ``••••`` in every later answer -- and the mask keeps no value to do it."""

from __future__ import annotations

from rocketwright.core.masking import CODE_S, MASK, PASSWORD_S, SecretMask

PASSWORD = "p@ss word/1"


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_a_value_hidden_is_masked_wherever_it_appears_raw_or_url_encoded() -> None:
    mask = SecretMask()
    assert mask.text(PASSWORD) == PASSWORD, "nothing is masked before anything is hidden"
    mask.hide(PASSWORD, PASSWORD_S)
    assert mask.text(f"value={PASSWORD}; again {PASSWORD}") == f"value={MASK}; again {MASK}"
    assert mask.text("?p=p%40ss%20word%2F1&x") == f"?p={MASK}&x"
    assert mask.text(PASSWORD + PASSWORD) == MASK, "one run of masked text reads as one mask"
    assert mask.text("p@ss word/") == "p@ss word/"


def test_the_mask_keeps_digests_never_the_value() -> None:
    mask = SecretMask()
    mask.hide(PASSWORD, PASSWORD_S)
    kept = repr(vars(mask))
    assert PASSWORD not in kept and "p%40ss" not in kept


def test_a_code_is_masked_for_minutes_and_a_password_for_hours_and_short_values_never() -> None:
    clock = Clock()
    mask = SecretMask(clock)
    mask.hide("123456", CODE_S)
    mask.hide(PASSWORD, PASSWORD_S)
    mask.hide("abc", PASSWORD_S)
    assert mask.text("123456 abc") == f"{MASK} abc"
    clock.now += CODE_S + 1
    assert mask.text(f"123456 {PASSWORD}") == f"123456 {MASK}"
    clock.now += PASSWORD_S
    assert not mask.holding and mask.text(PASSWORD) == PASSWORD
    mask.hide("123456", CODE_S)
    mask.hide("123456", 1.0)
    clock.now += 2
    assert mask.text("123456") == MASK, "hiding a value again never shortens its time"


def test_a_tools_answer_is_masked_in_its_text_and_its_structured_content_and_its_images_are_left() -> None:
    mask = SecretMask()
    answer = {
        "content": [
            {"type": "text", "text": f"field ={PASSWORD}"},
            {"type": "image", "data": PASSWORD, "mimeType": "image/jpeg"},
        ],
        "isError": False,
        "structuredContent": {"lines": [PASSWORD, 3, {"deep": PASSWORD}], "ok": True},
    }
    assert mask.result(answer) is answer, "nothing is copied while nothing is masked"
    mask.hide(PASSWORD, PASSWORD_S)
    masked = mask.result(answer)
    assert masked["content"][0]["text"] == f"field ={MASK}" and masked["content"][1] == answer["content"][1]
    assert masked["structuredContent"] == {"lines": [MASK, 3, {"deep": MASK}], "ok": True}
    assert mask.result({"content": [], "isError": True}) == {"content": [], "isError": True}
