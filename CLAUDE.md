# Goon

## What Is This

Goon is a personal AI concierge you interact with via SMS and phone calls.
You text or call a single phone number. It answers questions about businesses,
calls businesses on your behalf using an AI voice agent, makes reservations,
and remembers your preferences. No app, no humans in the loop.

## Architecture Docs (Read These First)

- `docs/goon-product-document.md` — Component decomposition, interfaces, convoy plan
- `docs/goon-blueprint.md` — Full technical spec with code, schemas, API details
- `docs/goon-integration-test-harness.md` — Test business setup, integration scenarios

## Tech Stack

- **Language**: Python 3.12+ / FastAPI
- **LLM**: Claude API (claude-sonnet-4-5-20250929)
- **Telephony**: Twilio (SMS + Voice)
- **Voice AI**: Vapi.ai (inbound + outbound calls)
- **Business Data**: Google Places API v2
- **Web Search**: Tavily API
- **Database**: SQLite (via aiosqlite)
- **Memory**: Markdown files per user + JSONL conversation logs
- **Billing**: Stripe
- **Frontend**: Next.js (registration site only)

## Project Structure
```
goon/
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Settings from env
│   ├── routes/
│   │   ├── sms.py                 # Twilio SMS webhook
│   │   ├── voice.py               # Twilio voice → Vapi routing
│   │   ├── vapi_events.py         # Vapi call event webhook
│   │   ├── stripe.py              # Stripe webhook
│   │   └── admin.py               # Admin dashboard
│   ├── services/
│   │   ├── orchestrator.py        # LLM orchestration + resolution ladder
│   │   ├── memory.py              # User memory read/write
│   │   ├── calls.py               # Outbound call management + retries
│   │   ├── cache.py               # Business fact cache
│   │   ├── places.py              # Google Places API
│   │   ├── search.py              # Web search (Tavily)
│   │   ├── sms.py                 # Twilio SMS (segment-aware)
│   │   ├── auth.py                # User auth + subscription check
│   │   ├── billing.py             # Stripe subscription management
│   │   ├── leads.py               # Unregistered user handling
│   │   └── proactive.py           # Trigger-based proactive outreach
│   └── db/
│       ├── schema.sql             # All table definitions
│       └── database.py            # SQLite async wrapper
├── web/                            # Next.js registration site
├── data/                           # User data (gitignored)
├── scripts/                        # Utility scripts
├── tests/                          # Test suite
└── docs/                           # Product doc, blueprint, test harness
```

## Key Design Principles

1. **Resolution Ladder**: Cache → Google Places → Web Search → Pre-Call Check → Voice Call. Always try the cheapest option first. Only call as a last resort.
2. **No emoji in SMS** — forces unicode, halves segment capacity from 160 to 70 chars.
3. **Voice agent sounds human** — no "on behalf of" framing, sound like a regular caller.
4. **Phone number scoring** — track call outcomes, deprioritize bad numbers after 2+ failures.
5. **Cache everything** — every fact learned gets stored with expiry timers.
6. **Test mode** — ENABLE_TEST_BUSINESSES flag routes fake businesses to your phone for testing.

## Current Status (as of 2026-03-01)

**All 10 components are built.** 43 commits, 172 passing tests. The codebase is
feature-complete for v0. We are at the **integration test gate** — the code is
written but has not been deployed or tested end-to-end with real services.

### What needs to happen next (in order):

#### Step 1: Fix deployment blockers
- `app/services/billing.py:47` uses `dict | None` syntax which fails on Python
  3.9 (system Python). Either fix the type hint or ensure the venv Python is used.
- Verify the full FastAPI app starts: `python3 -m uvicorn app.main:app`
- Confirm all service modules import cleanly together.

#### Step 2: Set up real credentials
- `.env` exists but needs real API keys populated:
  - Twilio: account SID, auth token, buy a phone number
  - Vapi: API key, phone number ID
  - Anthropic: API key
  - Google Places: API key
  - Tavily: API key (for web search)
  - Stripe: secret key, webhook secret (can defer to later)

#### Step 3: Deploy to Railway or Fly.io
- FastAPI server needs to be always-on for Twilio/Vapi webhooks
- SQLite + local user data directory on persistent disk
- Cost: ~$5-10/month

#### Step 4: Gate 0 — The Full Circuit Test (NOTHING ELSE UNTIL THIS WORKS)
- Set up Google Voice as the test business phone number
- Run `scripts/integration_test.py`
- The test: text "Book me a table at Riley's Pizza for 2 tonight at 7"
  - Goon texts back "Calling now"
  - Google Voice rings, you answer as the restaurant
  - Talk to the AI voice agent
  - Goon texts back the reservation details
  - Whole thing under 3 minutes
- Debug and iterate on voice prompts, retry logic, resolution ladder until this
  passes reliably.

#### Step 5: After the circuit works
- Polish: rate limiting, memory compaction, error alerting
- Connect registration site to live Stripe
- Seed yourself as allowlisted user, start using it for real
- Invite a few friends for v0 validation

### Component build status (all complete):
| # | Component | Tests |
|---|-----------|-------|
| 0 | Test Harness | integration_test.py |
| 1 | SMS Gateway | test_sms_webhook.py |
| 2 | Voice Inbound | test_voice.py |
| 3 | Orchestrator | (in test_sms_webhook) |
| 4 | Business Intel (cache/places/search) | test_cache, test_places, test_search |
| 5 | Voice Outbound | test_calls, test_vapi_events |
| 6 | Memory | test_memory |
| 7 | Proactive Intel | test_proactive |
| 8 | Auth & Billing | test_auth, test_billing (billing broken on 3.9) |
| 9 | Leads Engine | test_leads |
| 10 | Registration Site | Next.js in web/ |

## Coding Standards

- Python 3.12+, async/await everywhere
- Type hints on all function signatures
- Each service module is self-contained with a clean function interface
- Use aiosqlite for database, aiofiles for file I/O, httpx for HTTP clients
- Tests with pytest + pytest-asyncio
- Commits should be atomic — one logical change per commit
- No emoji anywhere in code or SMS output