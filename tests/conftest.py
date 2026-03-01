import asyncio

import pytest
import pytest_asyncio

from app.db.database import Database


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_db(tmp_path):
    """Create a fresh in-memory-like SQLite database for each test."""
    from pathlib import Path

    db_path = tmp_path / "test.db"
    schema_path = Path(__file__).parent.parent / "app" / "db" / "schema.sql"

    import aiosqlite

    conn = await aiosqlite.connect(str(db_path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    schema = schema_path.read_text()
    await conn.executescript(schema)
    await conn.commit()

    test_database = Database()
    test_database._conn = conn

    yield test_database

    await conn.close()
