"""Async SQLite database wrapper for Goon."""
from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"
DEFAULT_DB_PATH = Path(__file__).parents[2] / "data" / "goon.db"


async def get_db() -> aiosqlite.Connection:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DEFAULT_DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        schema = SCHEMA_PATH.read_text()
        await db.executescript(schema)
        await db.commit()
    finally:
        await db.close()


class Database:
    """Async SQLite wrapper with connection pooling."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        """Open connection and initialize schema."""
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA foreign_keys=ON")
            await self._init_schema()
        except Exception:
            logger.exception("Failed to connect to database at %s", self.db_path)
            raise

    async def _init_schema(self) -> None:
        """Run schema.sql to create tables."""
        try:
            schema = SCHEMA_PATH.read_text()
            await self._conn.executescript(schema)
        except Exception:
            logger.exception("Failed to initialize database schema")
            raise

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            self._conn = None

    def _ensure_connected(self) -> None:
        """Raise if the database connection is not initialized."""
        if self._conn is None:
            raise RuntimeError("Database not connected. Call db.connect() first.")

    async def execute(self, sql: str, params: list | None = None) -> int:
        """Execute a write query. Returns lastrowid."""
        self._ensure_connected()
        cursor = await self._conn.execute(sql, params or [])
        await self._conn.commit()
        return cursor.lastrowid

    async def fetch_one(self, sql: str, params: list | None = None) -> dict | None:
        """Fetch a single row as a dict."""
        self._ensure_connected()
        cursor = await self._conn.execute(sql, params or [])
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: list | None = None) -> list[dict]:
        """Fetch all rows as a list of dicts."""
        self._ensure_connected()
        cursor = await self._conn.execute(sql, params or [])
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def execute_many(self, sql: str, params_list: list[list]) -> None:
        """Execute a query with multiple parameter sets."""
        self._ensure_connected()
        await self._conn.executemany(sql, params_list)
        await self._conn.commit()


# Module-level singleton — use DATABASE_URL env var if set
def _db_path_from_env() -> str:
    import os
    url = os.getenv("DATABASE_URL", "")
    if url.startswith("sqlite://"):
        # sqlite:///data/goon.db -> /data/goon.db
        return url.removeprefix("sqlite://")
    return str(DEFAULT_DB_PATH)


db = Database(_db_path_from_env())
