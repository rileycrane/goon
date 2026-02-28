-- Goon database schema

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
