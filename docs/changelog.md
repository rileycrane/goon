# Hold Plz Changelog

Living document tracking changes during integration testing and production hardening.

---

## 2026-03-04 — Integration Testing Session

### Vapi Webhook Delivery (CRITICAL)

**Problem**: After a successful outbound call, Vapi never sent the `end-of-call-report` webhook back to our server. The user completed the call but never got an SMS with the result.

**Root causes found & fixed**:
1. **Missing `serverMessages`** — Vapi requires an explicit `serverMessages` array on the assistant config to know which events to deliver. Without it, no webhooks are sent to `server.url`. Added `["end-of-call-report", "status-update", "tool-calls"]` to both outbound call config (`calls.py`) and inbound assistant-request (`vapi_events.py`).
2. **Flat `serverUrl` vs nested `server.url`** — Vapi's API accepts `server: {"url": "..."}` (nested object). The old code used flat `serverUrl` which Vapi silently ignores on newer API versions. Fixed in `calls.py`.
3. **Cloudflare blocking Vapi webhooks (403)** — After fixing #1 and #2, Vapi started sending webhooks but got 403 from Cloudflare (which proxies `api.holdplz.ai`). Cloudflare's bot protection/WAF was rejecting Vapi's automated POST requests. **Fix**: Set `VAPI_SERVER_URL` env var to Railway's direct domain (`https://holdplz-production-production.up.railway.app/vapi/events`) which bypasses Cloudflare entirely. All other traffic (user-facing, Twilio, Stripe) still goes through `api.holdplz.ai`.
3. **Inbound assistant-request still used old format** — `vapi_events.py` line 164 was still returning `serverUrl` (flat) for inbound calls. Fixed to nested format + serverMessages.
4. **Different Vapi API keys** — Local `.env` had a dev Vapi key (`d983d2c5...`), Railway production had a different key (`9533a934...`). All API queries during debugging were hitting the wrong account. The March 2 calls that "worked" were using ngrok locally, not production.

**Files**: `app/services/calls.py`, `app/routes/vapi_events.py`

**Status**: Fix deployed. Awaiting next test call to confirm webhook delivery.

---

### Stripe Payment → Call Flow (CRITICAL)

**Problem**: User goes through full payment flow (web signup → SMS consent → text request → paywall → Stripe payment) but no call is ever made.

**Root causes found & fixed**:

1. **LLM stripping `client_reference_id` from Stripe URLs** — The orchestrator passes payment URLs with `?client_reference_id=+1234567890` to Claude, but the LLM "cleans up" the URL by removing query parameters. Added `_fix_payment_urls()` post-processor in `orchestrator.py` that re-injects the parameter on any `buy.stripe.com` URL in LLM output.

2. **No phone match on Stripe webhook** — `client_reference_id` was null (because of #1), `metadata.goon_phone` was empty (Payment Links don't carry metadata), `customer` was null (one-time Payment Links). Added fallback chain in `billing.py`: metadata → client_ref → email match → recent payment-link SMS match.

3. **Welcome message and re-trigger were coupled** — `_send_welcome_message` in `stripe.py` had both the LLM welcome text AND the re-trigger of the paywalled request in the same try block. When the LLM returned 529 (overloaded), the exception killed both. **Fixed by splitting into two independent async tasks**: `_send_welcome_sms` and `_retrigger_paywalled_request`.

4. **Payment method gate blocking post-payment calls** — Pay-per-request ($1) users pay via Payment Link (one-time charge, no saved card). But `verify_payment_method()` checks for a saved card on the Stripe customer. Added `skip_payment_gate` parameter for re-triggers, and `_has_recent_payment()` fallback that checks if the user's subscription was activated in the last 30 minutes.

5. **`call_plan` reported even on failure** — The orchestrator set `call_plan` (which triggers "Calling X now" response) whenever the tool result didn't contain "Tool error", which missed payment gate messages. Fixed to only set when result contains "Call initiated".

**Files**: `app/services/orchestrator.py`, `app/services/billing.py`, `app/routes/stripe.py`

---

### LLM Model Fallback

**Problem**: Anthropic Haiku returning 529 (overloaded) caused welcome messages, judge classifications, and request categorization to silently fail.

**Solution**: New `app/services/llm.py` module with automatic model fallback:
- `tier="standard"` tries Haiku → Sonnet (for cheap calls: judge, welcome, categorize)
- `tier="premium"` tries Sonnet → Haiku (for orchestrator, call summarization)
- Returns `None` if all models fail — callers handle with static fallbacks
- Stubs out future OpenAI provider fallback structure

All LLM call sites updated:
- `orchestrator.py` — main tool loop
- `judge.py` — classify_message, categorize_request
- `stripe.py` — welcome message generation
- `vapi_events.py` — call transcript summarization

**Files**: `app/services/llm.py` (new), `app/services/orchestrator.py`, `app/services/judge.py`, `app/routes/stripe.py`, `app/routes/vapi_events.py`

---

### CLI Manual Call Trigger

**Problem**: When the automated flow fails at any point, there's no way to manually pick up where it left off.

**Solution**: Two new admin endpoints + CLI commands:

| Endpoint | CLI Command | Purpose |
|----------|------------|---------|
| `POST /admin/trigger-call` | `calls <phone> trigger --business-name X --business-phone Y --task Z` | Directly initiate a Vapi call, bypasses all payment gates |
| `POST /admin/replay` | `calls <phone> replay "message text"` | Replay a message through the orchestrator with payment gate bypassed, sends SMS |

**Files**: `app/routes/admin.py`, `scripts/cli.py`

---

### Logging Visibility

**Problem**: All application logs were invisible in Railway. Only uvicorn access logs appeared.

**Root cause**: No `logging.basicConfig()` in `app/main.py`. Python defaults to WARNING level, suppressing all INFO/ERROR/EXCEPTION output.

**Fix**: Added `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")` at the top of `main.py`.

---

### FK Constraint on User Delete

**Problem**: Admin user delete failed because `request_messages` references `message_log`, but `message_log` was being deleted first.

**Fix**: Delete in correct FK order in `admin.py`: request_messages → requests → sessions → message_log → call_log → scheduled_tasks → users.

---

### Voice Agent Identity

**Problem**: When the voice agent called businesses, it said its name was "the customer" and gave the Hold Plz Twilio number for callbacks.

**Fix**: Updated `build_call_prompt()` in `calls.py` to accept `user_phone` parameter. Uses customer's actual phone for callbacks, handles missing name by giving phone number instead of "the customer".

---

## Commits (2026-03-04)

```
20cfcc8 feat: LLM model fallback, payment flow hardening, CLI call trigger
a1ffb50 fix: add serverMessages to Vapi assistant config for webhook delivery
950f29b fix: use server.url (nested object) not serverUrl for Vapi webhooks
82c0f70 fix: add serverMessages to Vapi payload, use customer phone + name
6b557e1 fix: skip payment method gate when re-triggering after fresh payment
d162e64 fix: configure logging.basicConfig(INFO)
8eb9576 fix: only report 'Calling now' when call actually succeeds
a873003 fix: re-trigger paywalled request through orchestrator after payment
1b048fc fix: delete user in FK order
79e19f7 fix: stripe checkout phone matching + payment URL post-processing
8e24bac fix: stripe webhook crash on plan_type column, phone normalization
0484f74 feat: sessions/requests model, LLM judge, request taxonomy, billing, admin views
505fdcd feat: dual payment plans -- $9.99/mo basic + $1/request pay-per-use
```

---

## Known Issues / Open Items

- **Vapi webhook delivery**: Fix deployed (`serverMessages` added), awaiting confirmation on next test call
- **Stale pricing in soul prompt**: Was $19.99, updated to $9.99/$1. Check all prompts for stale pricing.
- **Test suite**: 5 pre-existing test errors in `test_sms_webhook.py` (mock patching issue), 1 in `test_calls.py` (expected delay mismatch). Not caused by recent changes.
- **Railway deploy error logs**: User reported "a lot" of error logs on deploy. Need to review on next deploy.
- **Local vs production env divergence**: Local `.env` has different VAPI_API_KEY than Railway. Should align or document clearly.
