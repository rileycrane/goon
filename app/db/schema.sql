CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,                -- phone number (E.164)
    phone TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    stripe_customer_id TEXT,
    subscription_status TEXT NOT NULL DEFAULT 'trial',
    -- valid: trial | active | past_due | canceled
    trial_ends_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    allowlisted BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    direction TEXT NOT NULL,              -- in | out
    body TEXT,
    twilio_sid TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS call_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    vapi_call_id TEXT,
    business_name TEXT,
    business_phone TEXT,
    place_id TEXT,
    task TEXT,
    task_type TEXT,
    status TEXT NOT NULL DEFAULT 'in_progress',
    result TEXT,
    transcript TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    retry_after TIMESTAMP,
    duration_seconds INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    message TEXT,
    trigger TEXT,
    due_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    business_name TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    question TEXT,
    answer TEXT NOT NULL,
    source TEXT NOT NULL,
    verified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    confidence REAL DEFAULT 1.0,
    UNIQUE(place_id, fact_type)
);

CREATE TABLE IF NOT EXISTS phone_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    phone TEXT NOT NULL,
    call_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
    last_outcome TEXT,
    last_attempt TIMESTAMP,
    is_local BOOLEAN DEFAULT TRUE,
    UNIQUE(place_id, phone)
);

CREATE TABLE IF NOT EXISTS ivr_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    phone TEXT NOT NULL,
    menu_structure TEXT,
    last_updated TIMESTAMP,
    UNIQUE(place_id, phone)
);

CREATE TABLE IF NOT EXISTS unregistered_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    body TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
