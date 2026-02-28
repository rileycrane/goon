-- Goon database schema
-- Component 9: Leads Engine tables

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    phone TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    stripe_customer_id TEXT,
    subscription_status TEXT DEFAULT 'trial',
    trial_ends_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    allowlisted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS unregistered_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    body TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_unregistered_phone ON unregistered_attempts(phone);
CREATE INDEX IF NOT EXISTS idx_unregistered_created ON unregistered_attempts(created_at);

CREATE TABLE IF NOT EXISTS message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    direction TEXT,
    body TEXT,
    twilio_sid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
