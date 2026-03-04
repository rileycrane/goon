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
- `docs/changelog.md` — Living changelog of integration testing fixes and production hardening
- `docs/production-setup-guide.md` — Full setup guide: accounts, deployment, DNS, backups

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
│   │   ├── llm.py                 # LLM client with automatic model fallback
│   │   ├── judge.py               # Request classifier (sessions/requests model)
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

## Current Status (as of 2026-03-04)

**Deployed to production on Railway.** Live at `https://api.holdplz.ai`.
Currently in **integration testing** — the full circuit (SMS → payment →
call → webhook → SMS result) is being debugged end-to-end.

See `docs/changelog.md` for detailed bug-by-bug progress.

### What's working
- SMS send/receive via Twilio
- Stripe payment flow (both $9.99/mo subscription and $1/request Payment Links)
- User registration via web + SMS consent
- Orchestrator + resolution ladder (cache → places → web → call)
- Outbound calls via Vapi (call is placed, voice agent talks)
- Admin dashboard + CLI
- LLM model fallback (Haiku → Sonnet cascade)
- Memory system (per-user markdown files + JSONL logs)
- Sessions/requests data model + LLM judge

### What's being tested
- **Vapi webhook delivery** — `serverMessages` fix deployed, awaiting confirmation
  that `end-of-call-report` arrives and triggers SMS result to user
- **Full circuit**: text request → call → result SMS (blocked on webhook fix)

### What needs to happen next
1. Confirm Vapi webhooks arrive (test another call)
2. Get the full circuit working end-to-end reliably
3. Polish voice prompts based on transcript review
4. Stress test with multiple concurrent users
5. Invite friends for v0 validation

## CLI (`scripts/cli.py`)

Production management tool. Requires `ADMIN_PASSWORD` and `HOLDPLZ_API_URL` env vars.

```bash
# Set up (add to shell profile for convenience)
export HOLDPLZ_API_URL=https://api.holdplz.ai
export ADMIN_PASSWORD=mUdvop-0rovpa-fiztev
# Or just source .env which has both

# System status
python3 scripts/cli.py status

# User management
python3 scripts/cli.py user ls
python3 scripts/cli.py user show +16177179860
python3 scripts/cli.py user seed +16177179860 --name Riley
python3 scripts/cli.py user delete +16177179860

# Call management
python3 scripts/cli.py calls +16177179860 ls
python3 scripts/cli.py calls +16177179860 transcript 1

# Manually trigger a call (bypasses payment gate)
python3 scripts/cli.py calls +16177179860 trigger \
  --business-name "Riley's Pizza" \
  --business-phone "+13308868676" \
  --task "Make a reservation for 2 at 7pm" \
  --task-type reservation

# Replay a message through orchestrator (bypasses payment gate, sends SMS)
python3 scripts/cli.py calls +16177179860 replay \
  "Call Riley's Pizza and make a reservation for 2 at 7pm"

# Memory inspection
python3 scripts/cli.py memory +16177179860 show
python3 scripts/cli.py memory +16177179860 conversations --by-business

# Business intelligence
python3 scripts/cli.py biz ls
python3 scripts/cli.py biz show <place_id>

# Failures
python3 scripts/cli.py failures ls --unresolved
python3 scripts/cli.py failures summary
```

## Deployment

```bash
# Deploy to Railway (manual, not auto-deploy from GitHub)
railway up --detach

# Check logs
railway logs

# Check deploy status
railway status
```

The local `.env` file has dev/local credentials. Railway has separate production
credentials (set via `railway variables`). Notable difference: `VAPI_API_KEY`
differs between local and production (different Vapi accounts).

## Coding Standards

- Python 3.12+, async/await everywhere
- Type hints on all function signatures
- Each service module is self-contained with a clean function interface
- Use aiosqlite for database, aiofiles for file I/O, httpx for HTTP clients
- Tests with pytest + pytest-asyncio
- Commits should be atomic — one logical change per commit
- No emoji anywhere in code or SMS output
- All LLM calls go through `app/services/llm.py` for automatic model fallback