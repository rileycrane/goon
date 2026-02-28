-- Goon DB Schema
-- All table definitions for the Goon AI concierge

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,              -- phone number
    phone TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    stripe_customer_id TEXT,
    subscription_status TEXT DEFAULT 'trial',  -- trial | active | past_due | canceled
    trial_ends_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    allowlisted BOOLEAN DEFAULT FALSE  -- manual override for testers
);

CREATE TABLE IF NOT EXISTS message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    direction TEXT,                     -- in | out
    body TEXT,
    twilio_sid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    status TEXT DEFAULT 'in_progress',  -- in_progress | success | failed | retry_pending
    result TEXT,
    transcript TEXT,
    retry_count INTEGER DEFAULT 0,
    retry_after TIMESTAMP,
    duration_seconds INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    business_name TEXT NOT NULL,
    fact_type TEXT NOT NULL,       -- hours, menu, pricing, reservation_policy, etc.
    question TEXT,                  -- original question that produced this fact
    answer TEXT NOT NULL,
    source TEXT NOT NULL,           -- google_places, web_search, phone_call
    verified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    confidence REAL DEFAULT 1.0,   -- 1.0 for phone-verified, 0.8 for google, 0.6 for web
    UNIQUE(place_id, fact_type)
);

CREATE TABLE IF NOT EXISTS phone_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    phone TEXT NOT NULL,
    call_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    last_outcome TEXT,             -- success, voicemail, ivr, wrong_number, disconnected, busy, hostile
    last_attempt TIMESTAMP,
    is_local BOOLEAN DEFAULT TRUE, -- local vs corporate/chain number
    UNIQUE(place_id, phone)
);

CREATE TABLE IF NOT EXISTS ivr_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    phone TEXT NOT NULL,
    menu_structure TEXT,           -- JSON: {"1": "hours", "2": "reservations", "0": "operator"}
    last_updated TIMESTAMP,
    UNIQUE(place_id, phone)
);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    message TEXT,
    trigger TEXT,                       -- why this task exists
    due_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'pending',      -- pending | fired | canceled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS unregistered_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    body TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_message_log_user ON message_log(user_id);
CREATE INDEX IF NOT EXISTS idx_message_log_created ON message_log(created_at);
CREATE INDEX IF NOT EXISTS idx_call_log_user ON call_log(user_id);
CREATE INDEX IF NOT EXISTS idx_call_log_status ON call_log(status);
CREATE INDEX IF NOT EXISTS idx_business_facts_lookup ON business_facts(business_name, fact_type);
CREATE INDEX IF NOT EXISTS idx_business_facts_expiry ON business_facts(expires_at);
CREATE INDEX IF NOT EXISTS idx_phone_scores_lookup ON phone_scores(place_id, phone);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_due ON scheduled_tasks(due_at, status);
CREATE INDEX IF NOT EXISTS idx_unregistered_phone ON unregistered_attempts(phone);
