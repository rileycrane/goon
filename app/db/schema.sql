-- Hold Plz DB Schema
-- All table definitions for the Hold Plz AI concierge

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,              -- phone number (E.164)
    phone TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    stripe_customer_id TEXT,
    subscription_status TEXT NOT NULL DEFAULT 'free',
    -- valid: free | trial | active | past_due | canceled
    trial_ends_at TIMESTAMP,
    free_messages_used INTEGER NOT NULL DEFAULT 0,
    calls_used_this_period INTEGER NOT NULL DEFAULT 0,
    billing_period_start TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    allowlisted BOOLEAN NOT NULL DEFAULT FALSE  -- manual override for testers
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
    status TEXT NOT NULL DEFAULT 'in_progress',  -- in_progress | success | failed | retry_pending
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
    trigger TEXT,                       -- why this task exists
    due_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | fired | canceled
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    call_count INTEGER NOT NULL DEFAULT 0,
    success_count INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS unregistered_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    body TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS waitlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS phone_start_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS business_profiles (
    place_id TEXT PRIMARY KEY,
    business_name TEXT NOT NULL,
    lat REAL,
    lng REAL,
    address TEXT,
    phone TEXT,
    total_calls INTEGER NOT NULL DEFAULT 0,
    successful_calls INTEGER NOT NULL DEFAULT 0,
    total_queries INTEGER NOT NULL DEFAULT 0,
    avg_hold_time_seconds REAL,
    avg_call_duration_seconds REAL,
    known_contacts TEXT,       -- JSON: [{"name": "Maria", "role": "host"}]
    busy_patterns TEXT,        -- JSON
    notes TEXT,                -- LLM-generated insights
    first_seen TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS failure_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    call_log_id INTEGER REFERENCES call_log(id),
    failure_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    business_name TEXT,
    place_id TEXT,
    description TEXT NOT NULL,
    context TEXT,              -- JSON blob
    resolved BOOLEAN NOT NULL DEFAULT FALSE,
    resolution_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_waitlist_email ON waitlist(email);
CREATE INDEX IF NOT EXISTS idx_message_log_user ON message_log(user_id);
CREATE INDEX IF NOT EXISTS idx_message_log_created ON message_log(created_at);
CREATE INDEX IF NOT EXISTS idx_call_log_user ON call_log(user_id);
CREATE INDEX IF NOT EXISTS idx_call_log_status ON call_log(status);
CREATE INDEX IF NOT EXISTS idx_business_facts_lookup ON business_facts(business_name, fact_type);
CREATE INDEX IF NOT EXISTS idx_business_facts_expiry ON business_facts(expires_at);
CREATE INDEX IF NOT EXISTS idx_phone_scores_lookup ON phone_scores(place_id, phone);
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_due ON scheduled_tasks(due_at, status);
CREATE INDEX IF NOT EXISTS idx_unregistered_phone ON unregistered_attempts(phone);
CREATE INDEX IF NOT EXISTS idx_unregistered_created ON unregistered_attempts(created_at);
CREATE INDEX IF NOT EXISTS idx_phone_start_phone ON phone_start_attempts(phone);
CREATE INDEX IF NOT EXISTS idx_business_profiles_name ON business_profiles(business_name);
CREATE INDEX IF NOT EXISTS idx_failure_log_type ON failure_log(failure_type);
CREATE INDEX IF NOT EXISTS idx_failure_log_severity ON failure_log(severity);
CREATE INDEX IF NOT EXISTS idx_failure_log_created ON failure_log(created_at);
CREATE INDEX IF NOT EXISTS idx_failure_log_resolved ON failure_log(resolved);
CREATE INDEX IF NOT EXISTS idx_call_log_place_id ON call_log(place_id);
CREATE INDEX IF NOT EXISTS idx_call_log_business ON call_log(business_name);
