"""Redaction: what is replaced, what is counted, what is kept."""

from __future__ import annotations

import pytest

from llmdata.privacy import known_names, redact


@pytest.mark.chapter(15)
def test_claim_note_loses_caller_details() -> None:
    note = (
        "Caller Dev Ingram (+44 7700 900271, dev.ingram@example.com)"
        " reported a leak under CLM-00007 on POL-00042; excess £350."
    )
    text, found = redact(note, known_names("record", None, note))
    assert text == (
        "Caller [NAME] ([PHONE], [EMAIL]) reported a leak under"
        " CLM-00007 on POL-00042; excess £350."
    )
    assert found == {"name": 1, "phone": 1, "email": 1}


@pytest.mark.chapter(15)
@pytest.mark.parametrize(
    "number", ["07700 900123", "+447700900123", "+44 7700 900 123"]
)
def test_uk_mobile_formats(number: str) -> None:
    assert redact(f"Call me on {number}.", set())[0] == (
        "Call me on [PHONE]."
    )


@pytest.mark.chapter(15)
def test_redaction_is_idempotent() -> None:
    once, _ = redact("Farid Hollis, 07700 900797", {"Farid Hollis"})
    twice, found = redact(once, {"Farid Hollis"})
    assert (twice, found) == (once, {})
