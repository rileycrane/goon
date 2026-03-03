import logging
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.db.database import db
from app.services.auth import create_free_user, get_signups_enabled, get_user
from app.services.billing import create_checkout_session
from app.services.sms import send_sms

logger = logging.getLogger(__name__)

router = APIRouter()


class PhoneStartRequest(BaseModel):
    phone: str

    @field_validator("phone")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        digits = re.sub(r"\D", "", v)
        if len(digits) == 10:
            digits = "1" + digits
        if len(digits) != 11 or not digits.startswith("1"):
            raise ValueError("Enter a valid US phone number")
        return f"+{digits}"


@router.post("/start")
async def start_via_phone(req: PhoneStartRequest):
    """Landing page submits phone number. Creates free user + sends first SMS."""
    signups_on = await get_signups_enabled()

    if signups_on:
        existing = await get_user(req.phone)
        if existing:
            return {"status": "ok", "message": "already_registered"}

        await create_free_user(req.phone)
        await send_sms(
            req.phone,
            "Hey, this is Hold Plz. I look up info and call businesses "
            "so you don't have to. You've got 10 free messages -- go ahead, "
            "ask me something.",
        )
        return {"status": "ok", "message": "sms_sent"}
    else:
        # Signups disabled — log attempt
        try:
            await db.execute(
                "INSERT INTO phone_start_attempts (phone) VALUES (?)",
                [req.phone],
            )
        except Exception:
            logger.exception("Failed to log phone start attempt")
        await send_sms(
            req.phone,
            "Hold Plz isn't open to new users right now. "
            "We'll text you when there's a spot.",
        )
        return {"status": "ok", "message": "waitlisted"}


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


class WaitlistRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def email_valid(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Enter a valid email address")
        return v


@router.post("/waitlist")
async def join_waitlist(req: WaitlistRequest):
    """Add an email to the waitlist."""
    try:
        await db.execute(
            "INSERT INTO waitlist (email) VALUES (?) ON CONFLICT(email) DO NOTHING",
            [req.email],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok"}
