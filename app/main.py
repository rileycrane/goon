from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import db, init_db
from app.routes.stripe import router as stripe_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await db.connect()
    yield
    await db.close()


app = FastAPI(title="Goon", lifespan=lifespan)

app.include_router(stripe_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
