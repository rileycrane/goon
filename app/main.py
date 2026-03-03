"""Hold Plz -- FastAPI entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db.database import db, init_db
from app.routes import admin, register, sms, stripe, vapi_events, voice
from app.services.calls import process_retries
from app.services.proactive import run_proactive_checks

logger = logging.getLogger(__name__)

# Background task handles — cancelled on shutdown
_background_tasks: list[asyncio.Task] = []

PROACTIVE_CHECK_INTERVAL = 3600  # 1 hour (checks are idempotent; 8am logic is inside)
RETRY_CHECK_INTERVAL = 300  # 5 minutes


async def _periodic(coro_fn, interval: int, name: str) -> None:
    """Run an async function on a fixed interval, swallowing errors."""
    while True:
        try:
            await asyncio.sleep(interval)
            await coro_fn()
        except asyncio.CancelledError:
            break
        except Exception:
            logger.exception("Background task %s failed", name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    await init_db()
    await db.connect()

    # Start background schedulers
    _background_tasks.append(
        asyncio.create_task(
            _periodic(run_proactive_checks, PROACTIVE_CHECK_INTERVAL, "proactive"),
            name="proactive-scheduler",
        )
    )
    _background_tasks.append(
        asyncio.create_task(
            _periodic(process_retries, RETRY_CHECK_INTERVAL, "retries"),
            name="retry-scheduler",
        )
    )

    yield

    # Cancel background tasks
    for task in _background_tasks:
        task.cancel()
    await asyncio.gather(*_background_tasks, return_exceptions=True)
    _background_tasks.clear()

    await db.close()


app = FastAPI(title="Hold Plz", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.base_url,
        "http://localhost:3000",
        "https://www.holdplz.ai",
        "https://holdplz.ai",
    ],
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)

app.include_router(sms.router, prefix="/sms", tags=["sms"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(vapi_events.router, prefix="/vapi", tags=["vapi"])
app.include_router(stripe.router, prefix="/stripe", tags=["stripe"])
app.include_router(admin.router, prefix="/admin", tags=["admin"])
app.include_router(register.router, prefix="/register", tags=["register"])


@app.get("/health")
async def health():
    return {"status": "ok"}
