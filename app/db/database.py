import aiosqlite
from pathlib import Path

_DB_PATH = Path("data/goon.db")
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def get_db() -> aiosqlite.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(_DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    await db.execute("PRAGMA foreign_keys=ON")
    return db


async def init_db():
    db = await get_db()
    try:
        schema = _SCHEMA_PATH.read_text()
        await db.executescript(schema)
        await db.commit()
    finally:
        await db.close()


class Database:
    """Thin async wrapper around aiosqlite for use by services."""

    def __init__(self):
        self._db: aiosqlite.Connection | None = None

    async def connect(self):
        self._db = await get_db()

    async def close(self):
        if self._db:
            await self._db.close()
            self._db = None

    async def _ensure_connected(self):
        if self._db is None:
            await self.connect()

    async def execute(self, sql: str, params: list | None = None) -> aiosqlite.Cursor:
        await self._ensure_connected()
        assert self._db is not None
        cursor = await self._db.execute(sql, params or [])
        await self._db.commit()
        return cursor

    async def fetch_one(self, sql: str, params: list | None = None) -> dict | None:
        await self._ensure_connected()
        assert self._db is not None
        cursor = await self._db.execute(sql, params or [])
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    async def fetch_all(self, sql: str, params: list | None = None) -> list[dict]:
        await self._ensure_connected()
        assert self._db is not None
        cursor = await self._db.execute(sql, params or [])
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


db = Database()
