"""Yurtdisi numaralari: normalize, dogrulama, WhatsApp bicimi ve giris akisi."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.risk_score import is_valid_mobile, normalize_phone
from app.models import Customer
from app.services.messaging import to_whatsapp_number
from tests.test_book_for_other import book, client, data_of, error_of, fake_sender, login  # noqa: F401


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Turkiye: mevcut saklama bicimi degismedi
        ("+90 555 111 22 33", "5551112233"),
        ("0090 555 111 22 33", "5551112233"),
        ("+90 0555 111 22 33", "5551112233"),
        ("0555 111 22 33", "5551112233"),
        ("5551112233", "5551112233"),
        # Yurtdisi
        ("+44 7911 123456", "+447911123456"),
        ("0044 7911 123456", "+447911123456"),
        ("+49 (151) 2345-6789", "+4915123456789"),
        ("+1 415 555 2671", "+14155552671"),
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "phone, ok",
    [
        ("5551112233", True),
        ("+447911123456", True),
        ("+14155552671", True),
        ("4551112233", False),  # Turkiye'de cep numarasi 5 ile baslar
        ("555111223", False),
        ("+44", False),
        ("+0447911123456", False),
        ("+1234567890123456", False),  # E.164 en fazla 15 hane
    ],
)
def test_is_valid_mobile(phone, ok):
    assert is_valid_mobile(phone) is ok


def test_international_number_whatsapp_format():
    assert to_whatsapp_number("+447911123456") == "447911123456"
    assert to_whatsapp_number("5551112233") == "905551112233"


def test_international_customer_can_verify_and_book(client, salon, fake_sender, db):
    customer = login(client, "+44 7911 123456")["customer"]
    assert customer["phone"] == "+447911123456"
    # Kod WhatsApp'a ulke koduyla gitti.
    assert any(phone == "+447911123456" for phone, _ in fake_sender.sent)
    data_of(book(client, salon))
    assert db.scalar(select(Customer.id).where(Customer.phone == "+447911123456"))


def test_invalid_international_number_rejected(client):
    error = error_of(client.post("/api/auth/otp/send", json={"phone": "+44"}))
    assert error["code"] == "VALIDATION"


def test_booking_for_international_beneficiary(client, salon, fake_sender, db):
    login(client, "5321010000")
    beneficiary = {"firstName": "Anna", "phone": "+49 151 23456789"}
    data_of(book(client, salon, beneficiary=beneficiary))
    assert db.scalar(select(Customer.first_name).where(Customer.phone == "+4915123456789")) == "Anna"
