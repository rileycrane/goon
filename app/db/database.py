"""SQLite async wrapper using aiosqlite."""

import aiosqlite
from pathlib import Path
from typing import Any

from app.config import DATABASE_PATH


class Database:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DATABASE_PATH
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(str(self.path))
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def init_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        schema = schema_path.read_text()
        await self._conn.executescript(schema)

    async def execute(self, query: str, params: list[Any] | None = None) -> aiosqlite.Cursor:
        cursor = await self._conn.execute(query, params or [])
        await self._conn.commit()
        return cursor

    async def fetch_one(self, query: str, params: list[Any] | None = None) -> dict | None:
        cursor = await self._conn.execute(query, params or [])
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, query: str, params: list[Any] | None = None) -> list[dict]:
        cursor = await self._conn.execute(query, params or [])
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# Module-level singleton
db = Database()
