"""Admin dashboard — user management, lead review, system health."""

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.db.database import db

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
