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

## Coding Standards

- Python 3.12+, async/await everywhere
- Type hints on all function signatures
- Each service module is self-contained with a clean function interface
- Use aiosqlite for database, aiofiles for file I/O, httpx for HTTP clients
- Tests with pytest + pytest-asyncio
- Commits should be atomic — one logical change per commit
- No emoji anywhere in code or SMS output