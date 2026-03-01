"""Goon — FastAPI entry point."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import db, init_db
from app.routes import admin, sms, stripe, vapi_events, voice
from app.services.calls import process_retries

logger = logging.getLogger(__name__)

RETRY_INTERVAL_SECONDS = 300  # 5 minutes


async def _retry_loop() -> None:
    """Background loop that processes pending call retries every 5 minutes."""
    while True:
        await asyncio.sleep(RETRY_INTERVAL_SECONDS)
        try:
            count = await process_retries()
            if count > 0:
                logger.info("Processed %d pending retries", count)
        except Exception:
            logger.exception("Error in retry processing loop")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    await db.connect()
    retry_task = asyncio.create_task(_retry_loop())
    yield
    retry_task.cancel()
    try:
        await retry_task
    except asyncio.CancelledError:
        pass
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
