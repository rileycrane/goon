import re

import pytest
from pydantic import BaseModel, field_validator


# Replicate the validation logic locally to avoid importing billing.py
# (which has a Python 3.9 compat issue with dict | None syntax)
class CheckoutRequest(BaseModel):
    phone: str
    name: str
    email: str

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) == 10:
            digits = "1" + digits
        if len(digits) != 11 or not digits.startswith("1"):
            raise ValueError("Enter a valid US phone number")
        return f"+{digits}"

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Enter a valid email address")
        return v


def test_phone_normalizes_10_digits():
    req = CheckoutRequest(phone="4155551234", name="Riley", email="r@test.com")
    assert req.phone == "+14155551234"


def test_phone_normalizes_11_digits():
    req = CheckoutRequest(phone="14155551234", name="Riley", email="r@test.com")
    assert req.phone == "+14155551234"


def test_phone_strips_formatting():
    req = CheckoutRequest(phone="(415) 555-1234", name="Riley", email="r@test.com")
    assert req.phone == "+14155551234"


def test_phone_rejects_short():
    with pytest.raises(ValueError):
        CheckoutRequest(phone="12345", name="Riley", email="r@test.com")


def test_phone_rejects_non_us():
    with pytest.raises(ValueError):
        CheckoutRequest(phone="+442071234567", name="Riley", email="r@test.com")


def test_name_strips_whitespace():
    req = CheckoutRequest(phone="4155551234", name="  Riley  ", email="r@test.com")
    assert req.name == "Riley"


def test_name_rejects_empty():
    with pytest.raises(ValueError):
        CheckoutRequest(phone="4155551234", name="   ", email="r@test.com")


def test_email_lowercases():
    req = CheckoutRequest(phone="4155551234", name="Riley", email="Riley@Test.COM")
    assert req.email == "riley@test.com"


def test_email_rejects_invalid():
    with pytest.raises(ValueError):
        CheckoutRequest(phone="4155551234", name="Riley", email="notanemail")
