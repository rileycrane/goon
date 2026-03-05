# Decisions & History Log

**Purpose**: Prevent going in circles. Every session MUST read this file before
making changes. Update it after every significant decision, fix, or failed approach.

---

## Active Blockers

None.

---

## Completed Fixes

### 2026-03-04: Vapi webhook delivery (FIXED)

Outbound calls worked (Vapi places the call, voice agent talks, call completes)
but the `end-of-call-report` webhook never hit `/vapi/events`. User never got
the SMS result.

**What failed along the way:**

1. **Flat `serverUrl` key** — Vapi silently ignores it. Fixed to nested
   `server: { url: "..." }` format in `calls.py`.

2. **Missing `serverMessages`** — Without this array, Vapi doesn't send any
   webhooks to `server.url`. Fixed by adding
   `["end-of-call-report", "status-update", "tool-calls"]`.

3. **Cloudflare Page Rule** — Created a Page Rule to disable bot checks on
   `api.holdplz.ai/vapi/*`. Did NOT fix it. Cloudflare's Bot Fight Mode
   (free plan) overrides Page Rules and still returned 403 to Vapi's POSTs.

**Root cause**: Cloudflare Bot Fight Mode blocks Vapi's server-to-server POST
requests with 403. Page Rules cannot override this on the free Cloudflare plan.
Curling the endpoint manually returns 200, but Vapi's specific IP/fingerprint
gets blocked.

**Fix that worked**: Railway direct domain
(`holdplz-production-production.up.railway.app/vapi/events`) as `VAPI_SERVER_URL`.
This bypasses Cloudflare entirely. The earlier attempt to use this domain failed
because `serverMessages` was missing and `serverUrl` was flat — those bugs masked
the fact that the domain itself was fine.

**Current config:**
- `VAPI_SERVER_URL` on Railway = `https://holdplz-production-production.up.railway.app/vapi/events`
- Both outbound (`calls.py`) and inbound (`vapi_events.py`) use `settings.vapi_server_url`
- All other traffic (Twilio, Stripe, user-facing) still goes through `api.holdplz.ai` / Cloudflare

**Confirmed working**: 2026-03-04 ~18:30. CLI trigger -> call -> webhook -> SMS result delivered.

---

## Completed Fixes

### 2026-03-04: Post-payment loop (FIXED)

**Problem**: User pays via Stripe Payment Link, gets paywalled again on next message.

**Root causes & fixes applied:**
1. `_has_recent_payment()` queried nonexistent `updated_at` column → crash →
   returned `False`. **Fix**: Deleted `_has_recent_payment()` entirely; not needed.
2. `_retrigger_paywalled_request()` replayed "Y" (consent reply) instead of
   the actual business request. **Fix**: Walk messages past the paywall outbound,
   skip short replies (< 5 chars).
3. Payment gate checked `verify_payment_method()` which fails for Payment Links
   (no saved card). **Fix**: Re-fetch user from DB, check
   `subscription_status == 'active'` instead. Simple and reliable.
4. Added `updated_at` column to schema + migration for future use, but do NOT
   reference it in queries until confirmed the migration has run on production.

**Commits**: `65986fe`, `cb59603`

### 2026-03-04: Database migration gotcha (LEARNED)

**Lesson**: SQLite migrations run at app startup (`database.py:_migrate()`), but
production may not pick them up immediately. `CREATE TABLE IF NOT EXISTS` does NOT
add new columns to existing tables. The `ALTER TABLE ADD COLUMN` migration handles
this, but there can be timing issues. **Rule: never reference a new column in
application code on the same deploy that adds the migration. Give it one deploy
cycle to be safe, or make the code tolerate the column's absence.**

---

## Architecture Decisions

### Payment gating strategy

The payment gate for `call_business` works by:
1. Re-fetching user from DB (catches Stripe webhook updates mid-request)
2. Checking `subscription_status == 'active'` OR `allowlisted == True`
3. Free tier users see payment links via `_execute_tool` gating (not the call gate)

Do NOT use `verify_payment_method()` for gating — Payment Links don't save cards.
`verify_payment_method` is only useful for billing/charging after the fact.

### Stripe phone matching

Payment Links don't carry `client_reference_id` reliably (LLM strips query params,
though `_fix_payment_urls()` tries to re-inject). Fallback chain in `billing.py`:
metadata → client_ref → email match → recent payment-link SMS match.

### Vapi server URL

`VAPI_SERVER_URL` env var on Railway = `https://holdplz-production-production.up.railway.app/vapi/events`.
Bypasses Cloudflare (Bot Fight Mode blocks Vapi). All other traffic still uses `api.holdplz.ai`.

### Local vs production env

- Different `VAPI_API_KEY` (different Vapi accounts)
- Same `BASE_URL` (`https://api.holdplz.ai`)
- Production DB is persistent volume at `/data/goon.db`
