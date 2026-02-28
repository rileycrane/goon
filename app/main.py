"""Goon — FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import db, init_db
from app.routes import admin, sms, stripe, vapi_events, voice


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="Goon", version="0.1.0", lifespan=lifespan)

app.include_router(sms.router, prefix="/sms", tags=["sms"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(vapi_events.router, prefix="/vapi", tags=["vapi"])
app.include_router(stripe.router, prefix="/stripe", tags=["stripe"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/health")
async def health():
    return {"status": "ok"}
