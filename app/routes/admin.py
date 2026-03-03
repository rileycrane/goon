"""Admin dashboard — user management, lead review, system health."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.db.database import db
from app.services.auth import get_signups_enabled, set_signups_enabled

router = APIRouter()


def _check_admin(password: str | None) -> None:
    if not settings.admin_password or password != settings.admin_password:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.get("/")
async def admin_dashboard() -> dict:
    """Admin dashboard overview."""
    return {"status": "ok"}


class SeedUserRequest(BaseModel):
    phone: str
    name: str | None = None
    allowlisted: bool = True


@router.post("/seed-user")
async def seed_user(
    body: SeedUserRequest,
    x_admin_password: str | None = Header(None),
) -> dict:
    """Seed or update a user in the database."""
    _check_admin(x_admin_password)
    await db.execute(
        """INSERT INTO users (id, phone, name, subscription_status, allowlisted)
           VALUES (?, ?, ?, 'active', ?)
           ON CONFLICT(id) DO UPDATE SET
               name = excluded.name,
               subscription_status = 'active',
               allowlisted = excluded.allowlisted""",
        (body.phone, body.phone, body.name, body.allowlisted),
    )
    return {"status": "ok", "phone": body.phone, "name": body.name}


@router.get("/calls")
async def list_calls(
    x_admin_password: str | None = Header(None),
) -> dict:
    """List recent calls for debugging."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        "SELECT * FROM call_log ORDER BY created_at DESC LIMIT 10"
    )
    return {"calls": rows}


@router.get("/messages")
async def list_messages(
    x_admin_password: str | None = Header(None),
) -> dict:
    """List recent messages for debugging."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        "SELECT * FROM message_log ORDER BY created_at DESC LIMIT 20"
    )
    return {"messages": rows}


class SignupsToggle(BaseModel):
    enabled: bool


@router.post("/settings/signups")
async def toggle_signups(
    body: SignupsToggle,
    x_admin_password: str | None = Header(None),
) -> dict:
    """Toggle signups_enabled setting (runtime, stored in DB)."""
    _check_admin(x_admin_password)
    await set_signups_enabled(body.enabled)
    return {"status": "ok", "signups_enabled": body.enabled}


@router.get("/settings/signups")
async def get_signups_status(
    x_admin_password: str | None = Header(None),
) -> dict:
    """Get current signups_enabled status."""
    _check_admin(x_admin_password)
    enabled = await get_signups_enabled()
    return {"signups_enabled": enabled}


@router.get("/users")
async def list_users(
    x_admin_password: str | None = Header(None),
) -> dict:
    """List all users with tier, message count, call count."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        """SELECT id, phone, name, subscription_status, allowlisted,
                  free_messages_used, calls_used_this_period, created_at
           FROM users ORDER BY created_at DESC"""
    )
    return {"users": rows}


class AllowlistToggle(BaseModel):
    allowlisted: bool


@router.post("/users/{phone}/allowlist")
async def toggle_allowlist(
    phone: str,
    body: AllowlistToggle,
    x_admin_password: str | None = Header(None),
) -> dict:
    """Toggle allowlist status for a user."""
    _check_admin(x_admin_password)
    await db.execute(
        "UPDATE users SET allowlisted = ? WHERE phone = ?",
        [body.allowlisted, phone],
    )
    return {"status": "ok", "phone": phone, "allowlisted": body.allowlisted}
