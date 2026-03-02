#!/usr/bin/env python3
"""Seed a user into the Goon database.

Usage:
    python scripts/seed_user.py +14155551234 "Riley"

    # Or via railway run for production:
    railway run python scripts/seed_user.py +14155551234 "Riley"
"""

from __future__ import annotations

import os
import sqlite3
import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: seed_user.py <phone_e164> [name]")
        print("Example: seed_user.py +14155551234 Riley")
        sys.exit(1)

    phone = sys.argv[1]
    name = sys.argv[2] if len(sys.argv) > 2 else None

    if not phone.startswith("+"):
        print(f"Error: phone must be E.164 format (e.g. +14155551234), got: {phone}")
        sys.exit(1)

    db_url = os.getenv("DATABASE_URL", "sqlite:///data/goon.db")
    db_path = db_url.replace("sqlite:///", "")

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")

    # Ensure table exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            phone TEXT UNIQUE NOT NULL,
            name TEXT,
            email TEXT,
            stripe_customer_id TEXT,
            subscription_status TEXT NOT NULL DEFAULT 'trial',
            trial_ends_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            allowlisted BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)

    conn.execute(
        """INSERT INTO users (id, phone, name, subscription_status, allowlisted)
           VALUES (?, ?, ?, 'active', TRUE)
           ON CONFLICT(id) DO UPDATE SET
               name = excluded.name,
               subscription_status = 'active',
               allowlisted = TRUE""",
        (phone, phone, name),
    )
    conn.commit()
    conn.close()

    print(f"Seeded user: {phone} ({name or 'no name'}) — active, allowlisted")


if __name__ == "__main__":
    main()
