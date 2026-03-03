# Hold Plz -- System Architecture & Operations Guide

> We make the calls you don't want to.

**Version**: 1.0 -- March 3, 2026
**Status**: Feature-complete, pre-deployment

---

## What Is Hold Plz

Hold Plz is a personal AI concierge you interact with via SMS and phone calls. You text or call a single phone number. It answers questions about businesses, calls businesses on your behalf using an AI voice agent, makes reservations, and remembers your preferences. No app, no humans in the loop.

The system is a spiritual successor to TalkTo (TechCrunch Disrupt 2010, acquired by Path 2014). The core thesis -- people prefer texting over calling, and an intermediary can broker those interactions -- is the same. What's different: AI replaces the entire call center.

---

## End-to-End Sequence Diagram

This diagram traces every major path through the system, including memory, failure tracking, scheduling, business intelligence, and the billing paywall.

```
                           HOLD PLZ — FULL SYSTEM SEQUENCE
 ═══════════════════════════════════════════════════════════════════════════

 USER                  TWILIO         FASTAPI SERVER              EXTERNAL
  |                      |                 |                         |
  |  SMS "Book me a      |                 |                         |
  |  table at Delfina    |                 |                         |
  |  for 2 at 7"         |                 |                         |
  |--------------------->|  POST /sms/     |                         |
  |                      |  webhook        |                         |
  |                      |---------------->|                         |
  |                      |                 |                         |
  |                      |   200 (empty    |                         |
  |                      |   TwiML)        |                         |
  |                      |<----------------|                         |
  |                      |                 |                         |
  |                      |        [ASYNC PROCESSING BEGINS]          |
  |                      |                 |                         |
  |                      |         1. AUTH CHECK                     |
  |                      |         ┌───────┴────────┐                |
  |                      |         │ get_user(phone) │                |
  |                      |         │ get_user_tier() │                |
  |                      |         └───────┬────────┘                |
  |                      |                 |                         |
  |                      |         ┌───────┴──────────────┐          |
  |                      |         │ TIER ROUTING          │          |
  |                      |         │                       │          |
  |                      |         │ active → orchestrator │          |
  |                      |         │ free   → orchestrator │ ←── NEW: no message-count gate
  |                      |         │ none   → "resubscribe"│          |
  |                      |         └───────┬──────────────┘          |
  |                      |                 |                         |
  |                      |         2. ORCHESTRATOR                   |
  |                      |         ┌───────┴──────────────────────┐  |
  |                      |         │ a. Load user record           │  |
  |                      |         │ b. Load memory (USER.md,      │  |
  |                      |         │    MEMORY.md, conversations,  │  |
  |                      |         │    tasks)                     │  |
  |                      |         │ c. Build business context     │  |  ←── NEW: world model
  |                      |         │    (query business_profiles   │  |       injected into prompt
  |                      |         │     for known businesses)     │  |
  |                      |         │ d. Build system prompt        │  |
  |                      |         │    (soul + ladder + memory    │  |
  |                      |         │     + context + biz intel)    │  |
  |                      |         │ e. Start Claude tool loop     │  |
  |                      |         └───────┬──────────────────────┘  |
  |                      |                 |                         |
  |                      |         3. TOOL LOOP (up to 10 rounds)   |
  |                      |         ┌───────┴──────────────────────┐  |
  |                      |         │                               │  |
  |                      |         │  Claude sees ALL 7 tools:     │  |
  |                      |         │  check_cache, search_places,  │  |
  |                      |         │  search_web, pre_call_check,  │  |
  |                      |         │  call_business, update_memory,│  |
  |                      |         │  schedule_followup            │  |
  |                      |         │                               │  |
  |                      |         └───────┬──────────────────────┘  |
  |                      |                 |                         |
  |                      |        RESOLUTION LADDER EXECUTION        |
  |                      |                 |                         |
  |                      |    ┌────────────┼────────────┐            |
  |                      |    ▼            ▼            ▼            |
  |                      |  STEP 1      STEP 2       STEP 3         |
  |                      | check_cache  search_places search_web    |
  |                      |    |            |            |            |
  |                      |    |            |            |            |
  |                      |    ▼            ▼            ▼            |
  |                      |  SQLite      Google       Tavily         |
  |                      |  business_   Places       API            |
  |                      |  facts       API v2                      |
  |                      |    |            |            |            |
  |                      |    |         [store_fact ────────────┐    |
  |                      |    |          + ensure_               |    |
  |                      |    |          business_profile]       |    |
  |                      |    |                                  |    |
  |                      |    └────────────┬─────────────────────┘   |
  |                      |                 |                         |
  |                      |         IF ANSWER FOUND:                  |
  |                      |         → Claude responds                 |
  |                      |         → skip to MEMORY step             |
  |                      |                 |                         |
  |                      |         IF CALL NEEDED:                   |
  |                      |                 |                         |
  |                      |    ┌────────────┴────────────┐            |
  |                      |    ▼                         ▼            |
  |                      |  STEP 4                    STEP 4b        |
  |                      | pre_call_check            (FREE TIER)     |
  |                      |    |                      PAYWALL GATE    |
  |                      |    |                         |            |
  |                      |    |               ┌─────────┴──────┐     |
  |                      |    |               │ Send payment   │     |
  |                      |    |               │ link via SMS   │     |  ←── NEW: call-intent paywall
  |                      |    |               │ Return soft    │     |
  |                      |    |               │ upgrade msg    │     |
  |                      |    |               └────────────────┘     |
  |                      |    |                                      |
  |                      |    ├── OK → proceed to call               |
  |                      |    ├── CLOSED → queue for opening  ───────┼──── NEW: scheduler
  |                      |    │   (scheduled_tasks table,            |
  |                      |    │    fires 15min after open)           |
  |                      |    └── FAILED → report issues             |
  |                      |                 |                         |
  |                      |         STEP 5: call_business             |
  |                      |         ┌───────┴──────────────────────┐  |
  |                      |         │ a. Check call quota           │  |
  |                      |         │ b. Check duplicate call       │  |
  |                      |         │ c. Build voice prompt (soul   │  |
  |                      |         │    + task + IVR map + details)│  |
  |                      |         │ d. POST to Vapi API           │  |
  |                      |         │ e. Insert call_log row        │  |
  |                      |         │ f. Increment call count       │  |
  |                      |         └───────┬──────────────────────┘  |
  |                      |                 |                    ┌─────┴─────┐
  | "Calling Delfina     |                 |                    │  Vapi.ai  │
  |  now. Back in a few" |                 |                    │  (AI      │
  |<---------------------|<----------------|                    │  voice    │
  |                      |                 |                    │  agent)   │
  |                      |                 |                    │           │
  |                      |                 |                    │ calls ──> │ BUSINESS
  |                      |                 |                    │ Delfina   │ PHONE
  |                      |                 |                    │           │
  |                      |                 |                    │ "Table    │
  |                      |                 |                    │  for 2 at │
  |                      |                 |                    │  7:30"    │
  |                      |                 |                    └─────┬─────┘
  |                      |                 |                          |
  |                      |         POST /vapi/events                 |
  |                      |         (end-of-call-report)              |
  |                      |                 |<────────────────────────|
  |                      |                 |                         |
  |                      |         4. CALL RESULT PROCESSING         |
  |                      |         ┌───────┴──────────────────────┐  |
  |                      |         │ a. Classify outcome           │  |
  |                      |         │    (success/failure taxonomy) │  |
  |                      |         │ b. Update phone_scores        │  |
  |                      |         │ c. IF SUCCESS:                │  |
  |                      |         │    - LLM summarize transcript │  |  → Anthropic API
  |                      |         │    - SMS result to user       │  |
  |                      |         │    - Cache fact               │  |
  |                      |         │    - Append to conversations  │  |
  |                      |         │    - Update call_log          │  |
  |                      |         │    - ensure_business_profile  │  |  ←── NEW
  |                      |         │    - increment_business_calls │  |  ←── NEW
  |                      |         │    - extract_call_intelligence│  |  ←── NEW (background)
  |                      |         │      (contacts, hold time,    │  |
  |                      |         │       IVR map, busy patterns) │  |
  |                      |         │ d. IF FAILURE:                │  |
  |                      |         │    - Classify reason           │  |
  |                      |         │    - Compute retry delay       │  |  ←── NEW: exponential backoff
  |                      |         │      (base * 2^n + jitter)    │  |
  |                      |         │    - Schedule retry            │  |
  |                      |         │    - SMS failure msg to user   │  |
  |                      |         │    - log_failure()             │  |  ←── NEW
  |                      |         │    - ensure_business_profile   │  |  ←── NEW
  |                      |         │    - increment_business_calls  │  |  ←── NEW
  |                      |         └───────┬──────────────────────┘  |
  |                      |                 |                         |
  | "Delfina has a       |                 |                         |
  |  table for 2 at 7:30"|                 |                         |
  |<---------------------|<----------------|                         |
  |                      |                 |                         |
  |                      |         5. MEMORY PERSISTENCE             |
  |                      |         ┌───────┴──────────────────────┐  |
  |                      |         │ a. Append to conversations.   │  |
  |                      |         │    jsonl (in + out)            │  |
  |                      |         │ b. Append daily log            │  |
  |                      |         │    (memory/YYYY-MM-DD.md)      │  |
  |                      |         │ c. Apply profile updates       │  |
  |                      |         │    (LLM merges into USER.md)   │  |
  |                      |         └──────────────────────────────┘  |
  |                      |                                           |
  |                      |                                           |
  |                      |   === BACKGROUND TASKS (periodic) ===     |
  |                      |                                           |
  |                      |   Every 5 min: process_retries()          |
  |                      |     → Re-initiate failed calls            |
  |                      |                                           |
  |                      |   Every 5 min: process_queued_calls() ─── NEW
  |                      |     → Fire calls queued for opening       |
  |                      |     → SMS "Calling X now, they opened"    |
  |                      |                                           |
  |                      |   Every 1 hr: run_proactive_checks()      |
  |                      |     → Compute triggers per user           |
  |                      |     → Free tier re-engagement             |
  |                      |     → Recurring service reminders         |
  |                      |     → Pattern-based suggestions           |
  |                      |     → Compose + send proactive SMS        |
  |                      |                                           |
  |                      |   (On demand): distill_memory()           |
  |                      |     → daily logs → MEMORY.md              |
  |                      |     → LLM distillation pass               |


  INBOUND VOICE CALL (separate path):

  USER                 TWILIO          FASTAPI           VAPI
   |                     |                |                |
   | Calls Hold Plz #   |                |                |
   |-------------------->| POST /voice/  |                |
   |                     | webhook       |                |
   |                     |-------------->|                |
   |                     |               |                |
   |                     |    Auth check → if authorized: |
   |                     |               |  POST to Vapi  |
   |                     |               |  (provider     |
   |                     |               |   bypass)      |
   |                     |               |--------------->|
   |                     |               |                |
   |                     |               |  TwiML to      |
   |                     |               |  bridge call   |
   |                     |<--------------|<---------------|
   |                     |               |                |
   |  Connected to Vapi  |               |                |
   |  voice assistant    |               |                |
   |  (personalized with |               |                |
   |   user memory)      |               |                |
   |<------------------->|<------------->|<-------------->|
   |                     |               |                |
   |                     |  POST /vapi/events             |
   |                     |  (assistant-request)           |
   |                     |               |<---------------|
   |                     |               |                |
   |                     |  Return assistant config       |
   |                     |  with user memory injected     |
   |                     |               |--------------->|
```

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           HOLD PLZ v1.0                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  INGRESS                    BRAIN                    EGRESS              │
│  ───────                    ─────                    ──────              │
│  /sms/webhook ──────┐                          ┌──→ send_sms()          │
│  /voice/webhook ────┤   ┌──────────────┐       │    (Twilio)            │
│  /vapi/events ──────┼──→│ Orchestrator │──────→┤                        │
│  /stripe/webhook ───┘   │ (Claude +    │       ├──→ Vapi API            │
│                         │  tool loop)  │       │    (outbound calls)    │
│                         └──────┬───────┘       │                        │
│                                │               └──→ Admin Dashboard     │
│                                │                    (Next.js)           │
│  TOOLS (resolution ladder)     │                                        │
│  ─────────────────────────     │    PERSISTENCE                         │
│  1. check_cache ───→ SQLite    │    ───────────                         │
│  2. search_places ─→ Google    │    SQLite DB (schema.sql)              │
│  3. search_web ────→ Tavily    │    ├── users                           │
│  4. pre_call_check             │    ├── message_log                     │
│  5. call_business ─→ Vapi      │    ├── call_log                        │
│  6. update_memory              │    ├── business_facts                   │
│  7. schedule_followup          │    ├── phone_scores                     │
│                                │    ├── ivr_maps                         │
│                                │    ├── scheduled_tasks                  │
│  BACKGROUND                    │    ├── business_profiles  ←── NEW      │
│  ──────────                    │    ├── failure_log         ←── NEW      │
│  process_retries (5m)          │    └── app_settings                    │
│  process_queued_calls (5m) NEW │                                        │
│  run_proactive_checks (1h)     │    User Files (data/users/{phone}/)    │
│  distill_memory (on demand)    │    ├── USER.md (soul/profile)          │
│                                │    ├── MEMORY.md (distilled memory)    │
│                                │    ├── conversations.jsonl              │
│                                │    ├── tasks.json                       │
│                                │    └── memory/YYYY-MM-DD.md (daily)    │
│                                │                                        │
│  ADMIN UI (web/app/admin/)     │    BILLING                             │
│  ─────────────────────────     │    ───────                             │
│  /admin         → overview     │    Stripe (subscriptions)              │
│  /admin/users   → user list    │    ├── Payment links (SMS paywall)     │
│  /admin/users/X → detail+soul  │    ├── Checkout sessions               │
│  /admin/businesses → biz list  │    └── Webhook (status sync)           │
│  /admin/businesses/X → detail  │                                        │
│  /admin/failures → error log   │                                        │
│                                │                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Recursive Feedback Loops

The system has several places where outputs feed back into future inputs. These are the compound-interest mechanisms that make Hold Plz get smarter over time.

### Loop 1: Call Outcome → Phone Score → Future Call Routing

```
call_business → Vapi call → outcome (success/fail)
  → update_phone_score (place_id, phone, outcome)
    → phone_scores table (call_count, success_count, last_outcome)
      → pre_call_check reads phone_scores
        → warns agent about unreliable numbers
          → agent chooses different number or skips call
```

**Effect**: After 2+ failures on a number, the system flags it. The agent sees "This number has failed 3 times. Last outcome: voicemail" and can decide to try a different approach. Bad numbers get deprioritized automatically.

### Loop 2: Call Transcript → Business Intelligence → Future Agent Context

```
call completes → transcript captured
  → extract_call_intelligence (LLM background task)
    → business_profiles updated:
      - known_contacts ("Maria, host")
      - avg_hold_time_seconds
      - busy_patterns
      - notes
    → ivr_maps updated (menu structure)
  → next time user asks about that business:
    → _build_business_context reads business_profiles
      → injected into system prompt
        → agent knows: "Last time Maria answered. Avg hold ~2min. Press 2 for reservations."
```

**Effect**: Every call makes the system smarter about a business. The agent starts with zero knowledge and gradually builds a dossier. After 3-4 calls to the same restaurant, it knows the host's name, the IVR menu, and how long holds typically last.

### Loop 3: Conversation → Memory → Future Personality

```
user message → orchestrator processes
  → LLM calls update_memory("preference", "Prefers outdoor seating")
    → apply_profile_updates (LLM merges into USER.md)
  → append_conversation (raw JSONL log)
  → append_daily_log (one-line summary)
  → (periodic) distill_memory
    → daily logs → LLM distillation → MEMORY.md
  → next message:
    → load_memory reads USER.md + MEMORY.md
      → injected into system prompt
        → agent knows preferences, patterns, history
```

**Effect**: The agent accumulates a mental model of each user. It starts generic ("# New User") and evolves into a detailed profile: dietary restrictions, regular businesses, party size defaults, scheduling patterns. This enables personalized behavior like "You usually book dinner for 2 -- same this time?" without the user repeating themselves.

### Loop 4: Failure → Failure Log → Retry → (Eventually) Success or Escalation

```
call fails → classify_call_outcome
  → log_failure (failure_log table)
    → handle_call_failure
      → compute_retry_delay (exponential: base * 2^n + jitter)
        → schedule_retry (call_log.retry_after)
          → process_retries (background, every 5m)
            → re-initiate call
              → success → result to user
              → failure again → higher delay, fewer retries remaining
                → after MAX_RETRIES: give up, give user the number
  → failure_log visible in admin dashboard
    → operator can see patterns (IVR failures up, business X always fails)
```

**Effect**: The system is persistent but not obnoxious. It retries with increasing delays, switching strategy if needed (busy → 5min, voicemail → 30min, no answer → 10min). After 3 attempts it gives up gracefully. The admin dashboard aggregates failure patterns into product roadmap signal.

### Loop 5: Cached Facts → Resolution Ladder Short-Circuit

```
first query about business → cache miss → Places/web/call
  → store_fact (business_facts, expiry timer, confidence score)
  → ensure_business_profile + increment_business_queries
  → second query about same business:
    → check_cache → HIT (skips Places, web, call entirely)
      → instant answer, zero API cost
      → still increments business_profiles.total_queries
```

**Effect**: The first time someone asks about a business, it might take 3-4 tool calls. The second time, it's a single cache lookup. Facts expire on a schedule (phone-verified: 7-30d, Google: 7-30d, web: 14d) so stale data is eventually refreshed.

### Loop 6: Scheduled Task → Proactive Outreach → User Engagement

```
user asks about business → agent creates schedule_followup
  OR: pre_call_check returns "closed"
    → queue_call_for_opening (scheduled_tasks, due_at = opening + 15m)

  → process_queued_calls (background, every 5m)
    → fire call when business opens
    → SMS "Calling X now -- they just opened"
    → result comes back via normal webhook path

  → run_proactive_checks (background, every 1h)
    → compute_triggers (deterministic: no LLM)
      - scheduled followups that are due
      - call retries that are due
      - profile pattern matches ("Friday dinner")
      - recurring service reminders ("haircut due")
      - free tier re-engagement (24-72h after paywall)
    → compose_proactive_message (LLM, only if triggers exist)
    → send SMS
```

**Effect**: The system is proactive, not just reactive. It queues calls for when businesses open, reminds users about recurring services, and nudges free users who went quiet. The trigger computation is deliberately non-LLM (pure SQL + pattern matching) to avoid speculative API costs.

### Loop 7: Free Tier → Call-Intent Paywall → Conversion → Full Access

```
free user texts → orchestrator gives all 7 tools to Claude
  → Claude reasons about calling (can see call_business tool)
    → attempts to use call_business or pre_call_check
      → _execute_tool: GATED_TOOLS check
        → send_payment_link (Stripe URL via SMS)
        → return soft message to LLM
          → LLM tells user about upgrade naturally
            → user texts "pay" → Stripe checkout
              → webhook → subscription_status = active
                → next message: full access, no gate
```

**Effect**: The paywall fires at the moment of highest intent -- when the user actually needs a call made. This is much higher-conversion than gating after N messages regardless of content. The agent can still demonstrate value with free tools (search, lookup, info) while the call tools create natural upgrade moments.

---

## Database Schema (Complete)

```sql
-- Core
users                   -- id (phone), tier, stripe, quotas, timestamps
message_log             -- every SMS in/out, with Twilio SID
call_log                -- every Vapi call, with transcript + result

-- Business Intelligence
business_facts          -- cached answers (place_id + fact_type unique)
phone_scores            -- per-number reliability (place_id + phone unique)
ivr_maps                -- known phone menus (place_id + phone unique)
business_profiles       -- aggregate business dossier (place_id PK)

-- Scheduling & Tasks
scheduled_tasks         -- future SMS, queued calls, triggers

-- System
failure_log             -- typed/severity-rated error tracking
app_settings            -- runtime toggles (signups_enabled, etc.)
unregistered_attempts   -- inbound SMS from unknown numbers
waitlist                -- email waitlist
phone_start_attempts    -- landing page phone submissions
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, async/await |
| LLM | Claude Sonnet 4.5 (claude-sonnet-4-5-20250929) |
| Telephony | Twilio (SMS + voice routing) |
| Voice AI | Vapi.ai (11Labs TTS, Deepgram STT, Claude brain) |
| Business data | Google Places API v2 |
| Web search | Tavily API |
| Payments | Stripe (subscriptions, payment links) |
| Database | SQLite + aiosqlite + Litestream replication |
| Frontend | Next.js 15, React 19, Tailwind 4 |
| User data | Markdown files + JSONL per user |
| Deployment | Docker, Railway |

---

## What to Explore Next (Priority Analysis)

### Tier 1: Critical Path (must work before real usage)

**1. Full Circuit Test (Gate 0)**
The single most important thing. Until a real SMS triggers a real Vapi call to a real phone and the result comes back, everything is theoretical. Set up Google Voice as a test business, run the integration test script, debug until it works end-to-end in under 3 minutes.

**2. Voice Prompt Tuning**
The voice agent's personality is the product. The first few real calls will reveal: Does the recording disclosure sound natural? Does the agent navigate IVRs? Does it hang up at the right time? Does it sound like a real caller? This requires iteration on `build_call_prompt` and `build_first_message` with real call transcripts.

**3. Error Recovery Under Real Conditions**
The retry/backoff logic is written but untested against real Vapi failure modes. Specific unknowns: What does Vapi send when a number is disconnected? What's the actual `endedReason` string for a busy signal? What happens when Vapi itself is down? These can only be answered with real calls.

### Tier 2: High Value (build confidence in the system)

**4. Memory Quality Loop**
The profile update mechanism (`apply_profile_updates`) uses an LLM to merge facts into USER.md. Does it produce good profiles after 20 interactions? Does it lose information? Does it hallucinate? Run a simulated conversation sequence and inspect the evolving profile.

**5. Business Intelligence Validation**
`extract_call_intelligence` parses transcripts for contacts, hold times, and IVR structure. Test with real transcripts: Does it correctly identify "Maria, hostess" from a restaurant call? Does it detect IVR menus? Bad extraction here means the world model fills with noise.

**6. Scheduling Reliability**
The closed-business queuing and exponential backoff are new. Edge cases: What if the business hours are wrong in Google Places? What if a queued call fires and the business is still closed? What if the retry delay exceeds the business's closing time?

### Tier 3: Product Refinement (after the basics work)

**7. Free-to-Paid Conversion Flow**
The call-intent paywall is the business model. Test: Does the payment link SMS arrive quickly? Does the Stripe webhook correctly upgrade the user? Does the next message after payment have full access? What happens if payment fails?

**8. Admin Dashboard Utility**
The dashboard is built but has no real data to display. Seed test data, then iterate on: Is the conversation grouping useful? Can you quickly diagnose a failed call? Do the failure summary cards surface real patterns?

**9. Proactive Intelligence Calibration**
The proactive system sends exactly 0 or 1 message per check cycle. Tune: Are the pattern matchers too aggressive? Is the LLM message composition natural? Do re-engagement messages feel helpful or spammy?

### Tier 4: Scale Preparation (not yet needed)

**10. Multi-User Concurrency**
SQLite + single-process works for a handful of users. At what point does it need PostgreSQL? WAL mode helps with concurrent reads, but write contention could be an issue with 50+ active users.

**11. Cost Monitoring**
Every Claude API call, Vapi call, Twilio message, and Google Places query has a cost. Build per-user cost tracking before the first paying customer.

**12. Transcript Search**
Full-text search across all call transcripts would be powerful for the admin dashboard. SQLite FTS5 is a natural fit.

---

## Testing Guide

### Prerequisites

```bash
# Python environment
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Environment variables (copy and fill in)
cp .env.example .env
# At minimum for unit tests: no real keys needed (all mocked)
# For integration tests: need real Twilio, Vapi, Anthropic, Google Places keys
```

### Unit Tests (172 tests, no real API calls)

```bash
# Run full suite
pytest tests/ -v

# Run by component
pytest tests/test_auth.py -v              # User auth, tier logic
pytest tests/test_billing.py -v           # Stripe checkout, subscriptions
pytest tests/test_cache.py -v             # Business fact cache, phone scores
pytest tests/test_calls.py -v             # Call initiation, retries, outcomes
pytest tests/test_database.py -v          # SQLite connection, migrations
pytest tests/test_memory.py -v            # Profile loading, memory distillation
pytest tests/test_places.py -v            # Google Places parsing, chains
pytest tests/test_proactive.py -v         # Trigger computation, scheduling
pytest tests/test_search.py -v            # Tavily web search
pytest tests/test_sms_webhook.py -v       # SMS ingestion, tier routing
pytest tests/test_voice.py -v             # Voice auth, Vapi call creation
pytest tests/test_vapi_events.py -v       # Call outcome handling
pytest tests/test_register.py -v          # Phone registration
pytest tests/test_leads.py -v             # Unregistered user handling
```

### Integration Test (Full Circuit -- requires real credentials)

```bash
# 1. Set up test environment
export ENABLE_TEST_BUSINESSES=true
export TEST_BUSINESS_PHONE="+1XXXXXXXXXX"  # Your Google Voice number

# 2. Start the server
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3. Run the integration script
python3 scripts/integration_test.py
```

**The full circuit test** (Gate 0):
1. Text "Book me a table at Riley's Pizza for 2 tonight at 7" to the Hold Plz number
2. System should text back "Calling now"
3. Your Google Voice number rings -- answer as the restaurant
4. Talk to the AI voice agent
5. System texts back the reservation details
6. Whole thing under 3 minutes

### Manual Test Scenarios

**Scenario 1: Resolution Ladder (no call needed)**
```
Text: "What time does Walgreens close?"
Expected: Answer from Google Places, no call made
Verify: check_cache called first, then search_places
```

**Scenario 2: Call-Intent Paywall (free tier)**
```
Setup: Create free user via /admin/seed-user
Text: "Call my dentist and schedule a cleaning"
Expected: Agent reasons about calling → payment link sent → warm upgrade message
Verify: No actual call initiated, SMS with Stripe link received
```

**Scenario 3: Successful Call (paid tier)**
```
Text: "Make a reservation at [test restaurant] for 2 at 7"
Expected: Pre-call check → call initiated → Vapi calls → result texted back
Verify: call_log entry, phone_scores updated, business_profiles populated
```

**Scenario 4: Failed Call with Retry**
```
Text: "Call [number that goes to voicemail]"
Expected: Call fails → "Got voicemail, trying again in 30 min"
Verify: call_log.status = retry_pending, failure_log entry created
Wait 30 min → verify retry fires automatically
```

**Scenario 5: Closed Business Scheduling**
```
Text: "Call [business] at 10pm (after they close)"
Expected: "They're closed. I'll call at [opening time] when they open."
Verify: scheduled_tasks row with trigger='closed_business_queue'
```

**Scenario 6: Memory Persistence**
```
Text 1: "I'm allergic to shellfish"
Text 2: (next day) "Find me a good seafood restaurant"
Expected: Agent remembers allergy, mentions it when suggesting restaurants
Verify: USER.md contains allergy info
```

**Scenario 7: Business Intelligence Accumulation**
```
Make 3 calls to the same business over several days
Verify in admin dashboard:
  - business_profiles has accurate counters
  - known_contacts populated from transcripts
  - avg_call_duration_seconds calculated
  - IVR map stored if phone tree detected
```

**Scenario 8: Admin Dashboard**
```
1. Navigate to /admin
2. Enter admin password
3. Verify: stats cards load, recent activity shows
4. Click user → verify soul (USER.md), memory (MEMORY.md) render
5. Click into conversations → verify business grouping works
6. Click call card → verify transcript loads on demand
7. Navigate to failures → verify failure entries visible with severity badges
```

### Verifying New Features

After implementation, run these specific checks:

```bash
# Phase 0: Call-intent paywall
# Create a free user and send a message requiring a call
curl -X POST http://localhost:8000/admin/seed-user \
  -H "Content-Type: application/json" \
  -H "X-Admin-Password: $ADMIN_PASSWORD" \
  -d '{"phone": "+15555550001", "name": "Test Free", "allowlisted": false}'
# Then text from that number asking to call a business
# Verify: payment link SMS sent, no actual call made

# Phase 1: Schema
# Verify new tables exist
sqlite3 data/goon.db ".tables" | grep -E "business_profiles|failure_log"

# Phase 2: Admin dashboard
# Start web dev server and navigate to /admin
cd web && npm run dev
# Open http://localhost:3000/admin

# Phase 3: Scheduling
# Check scheduled_tasks table after closed-business scenario
sqlite3 data/goon.db "SELECT * FROM scheduled_tasks WHERE trigger='closed_business_queue'"

# Phase 4: Business intelligence
# After a call completes, check:
sqlite3 data/goon.db "SELECT * FROM business_profiles"

# Phase 5: Failure tracking
# After a call fails, check:
sqlite3 data/goon.db "SELECT * FROM failure_log ORDER BY created_at DESC LIMIT 5"
```

---

## File Index

```
app/
  main.py                          FastAPI entry, lifespan, CORS, background tasks
  config/
    settings.py                    Environment variables → Settings dataclass
    test_businesses.py             Test fixture data
  db/
    schema.sql                     All CREATE TABLE + indexes
    database.py                    aiosqlite wrapper (Database class + singleton)
  routes/
    sms.py                         POST /sms/webhook (Twilio inbound SMS)
    voice.py                       POST /voice/webhook (Twilio inbound voice)
    vapi_events.py                 POST /vapi/events (Vapi call lifecycle)
    stripe.py                      POST /stripe/webhook (Stripe events)
    register.py                    POST /register/* (user onboarding)
    admin.py                       GET/POST /admin/* (17 endpoints)
  services/
    orchestrator.py                LLM tool loop + resolution ladder
    calls.py                       Vapi outbound calls + retries
    memory.py                      USER.md, MEMORY.md, conversations, tasks
    auth.py                        User lookup, tier, quotas
    billing.py                     Stripe checkout + subscriptions
    intelligence.py                Business world model + transcript extraction
    cache.py                       Business facts + phone scores + IVR maps
    places.py                      Google Places API v2
    search.py                      Tavily web search
    sms.py                         Twilio SMS sending (segment-aware)
    proactive.py                   Trigger computation + proactive outreach
    scheduler.py                   Closed-business queuing + backoff
    failures.py                    Failure logging (type + severity)
    leads.py                       Unregistered user teasers
  prompts/
    soul.py                        Soul document section extraction
    soul.md                        Full personality + guidelines

web/
  app/
    page.tsx                       Landing page
    layout.tsx                     Root layout (fonts, meta)
    globals.css                    Theme tokens + component styles
    signup/                        Checkout flow
    admin/                         Dashboard (layout + 6 pages + 5 components)
    components/                    Landing page components

docs/
  goon-product-document.md         Product vision + component plan
  goon-blueprint.md                Technical spec
  goon-integration-test-harness.md Test scenarios
  production-setup-guide.md        Deployment guide
  README.md                        This document

scripts/
  integration_test.py              Manual integration test runner
  seed_user.py                     Create test users

tests/                             15 test files, 172 tests
```
