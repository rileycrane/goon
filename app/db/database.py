"""Async SQLite database wrapper for Goon."""

import aiosqlite
from pathlib import Path

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_db_path: str = ""
_connection: aiosqlite.Connection | None = None


async def init(db_path: str = "data/goon.db") -> None:
    """Initialize the database connection and apply schema."""
    global _db_path, _connection
    _db_path = db_path
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _connection = await aiosqlite.connect(db_path)
    _connection.row_factory = aiosqlite.Row
    await _connection.execute("PRAGMA journal_mode=WAL")
    schema = _SCHEMA_PATH.read_text()
    await _connection.executescript(schema)
    await _connection.commit()


async def close() -> None:
    """Close the database connection."""
    global _connection
    if _connection:
        await _connection.close()
        _connection = None


def _conn() -> aiosqlite.Connection:
    if _connection is None:
        raise RuntimeError("Database not initialized. Call db.init() first.")
    return _connection


async def execute(sql: str, params: list | None = None) -> None:
    """Execute a write query."""
    conn = _conn()
    await conn.execute(sql, params or [])
    await conn.commit()


async def fetch_one(sql: str, params: list | None = None) -> dict | None:
    """Fetch a single row as a dict, or None."""
    conn = _conn()
    cursor = await conn.execute(sql, params or [])
    row = await cursor.fetchone()
    if row is None:
        return None
    return dict(row)


async def fetch_all(sql: str, params: list | None = None) -> list[dict]:
    """Fetch all rows as a list of dicts."""
    conn = _conn()
    cursor = await conn.execute(sql, params or [])
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]
