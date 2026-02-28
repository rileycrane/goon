"""Admin dashboard — user management, lead review, system health."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def admin_dashboard() -> dict:
    """Admin dashboard overview."""
    # TODO: return user counts, recent messages, call stats
    return {"status": "ok"}
