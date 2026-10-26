"""Payment card data never reaches logs or transcripts in the clear.

Contract: the agent completes checkouts in the user's own Chrome (Mi Chrome) and may be handed a
CVV in chat; once text goes through ``redact_sensitive_text``, a card number that passes the
issuer-prefix + Luhn checks keeps only its last four digits and a labelled CVV/CVC is masked.
Order numbers, phone numbers and timestamps are left alone, and source files keep their test-card
fixtures like every other assignment pass.
"""

from __future__ import annotations

import pytest

from agent.redact import redact_sensitive_text


@pytest.fixture(autouse=True)
def _redaction_on(monkeypatch):
    monkeypatch.delenv("CLAWK_REDACT_SECRETS", raising=False)
    monkeypatch.setattr("agent.redact._REDACT_ENABLED", True)


@pytest.mark.parametrize(
    ("card", "last4"),
    [
        ("4242 4242 4242 4242", "4242"),  # Visa, spaced
        ("5555-5555-5555-4444", "4444"),  # Mastercard, dashed
        ("378282246310005", "0005"),  # Amex, bare
        ("6011111111111117", "1117"),  # Discover
    ],
)
def test_card_numbers_keep_only_their_last_four(card, last4):
    out = redact_sensitive_text(f"Pagué con la tarjeta {card}, gracias.")
    assert card not in out and f"****{last4}" in out


@pytest.mark.parametrize(
    ("text", "cvv"),
    [
        ("CVV: 123", "123"),
        ("cvc=4321", "4321"),
        ("código de seguridad 987", "987"),
        ("security code: 456", "456"),
        ('"cvv2": "789"', "789"),
    ],
)
def test_a_labelled_cvv_is_masked(text, cvv):
    out = redact_sensitive_text(f"El usuario me pasó el {text} para el pago")
    assert cvv not in out and "***" in out


@pytest.mark.parametrize(
    "text",
    [
        "Reserva VY-48213 confirmada, pedido 4242424242424241",  # fails Luhn
        "Llamá al +54 11 4123 4567",
        "timestamp 1729958400123",
        "Total: 1234 USD, vuelo 3456",
    ],
)
def test_order_numbers_phones_and_timestamps_are_left_alone(text):
    assert redact_sensitive_text(text) == text


def test_source_files_keep_their_test_card_fixtures():
    fixture = 'TEST_CARD = "4242 4242 4242 4242"  # cvv: 123\n'
    assert redact_sensitive_text(fixture, code_file=True) == fixture
