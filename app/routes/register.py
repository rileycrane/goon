from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
import re

from app.services.billing import create_checkout_session

router = APIRouter()


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


@router.post("/checkout")
async def checkout(req: CheckoutRequest):
    """Create a Stripe Checkout session and return the URL."""
    try:
        url = await create_checkout_session(req.phone, req.name, req.email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"checkout_url": url}
