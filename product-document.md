# Goon — Product Document

> Your AI that does the thing so you don't have to.

**Version**: 0.1 — February 28, 2026
**Author**: Riley Crane
**Status**: Pre-build

---

## What Is Goon

Goon is a personal AI concierge you interact with via a single phone number. You text it or call it. It answers questions about businesses, calls businesses on your behalf using an AI voice agent, makes reservations, checks availability, remembers your preferences, and gets smarter with every interaction. No app to download. No humans in the loop.

**The lineage**: Goon is a spiritual successor to TalkTo, a startup I co-founded in 2010 with Stuart Levinson. TalkTo let you text any business in America and get a text response — powered by a human call center that would phone the business on your behalf. We launched at TechCrunch Disrupt, raised $3M from Matrix Partners, were acquired by Path in 2014. The core thesis — that people prefer texting over calling, and that an intermediary can broker those interactions — was right. What killed it was the cost of humans. In 2026, AI replaces the entire call center.

**The form factor**: SMS + voice, same number. That's it. The user texts a question ("Does Delfina have a table for 2 tonight at 7?"). Goon answers — either from cached data, Google Places, web search, or by placing an actual AI voice call to the business. Results come back as a text.

---

## Who Is It For (Right Now)

Me. This is a personal prototype. The architecture supports multiple users and there's a subscription/billing system in the plan, but v0 is a tool I build for myself and a handful of friends to validate that the experience works. The north star is: **I should be able to offload any local-business errand to Goon and trust that it will either handle it or tell me it can't.**

---

## Core Experience

### The Happy Path

```
Me: Does Delfina have a table for 2 tonight at 7?

Goon: Checking... Delfina is open til 10 tonight. I don't see
      online reservations — want me to call them?

Me: Yeah

Goon: Calling now. Back in a few.

[2 minutes later]

Goon: Delfina has a table for 2 at 7:30 (nothing at 7).
      Name is Riley. Want me to confirm?

Me: Do it

Goon: Done. Delfina, tonight, 7:30, table for 2 under Riley.
```

### What Makes It Work

1. **It doesn't call when it doesn't need to.** Most questions can be answered from Google Places or a web search. Calling is a last resort, or used when the task requires human interaction (reservations, appointments, availability checks). This was the original TalkTo's biggest lesson — they cut their auto-answer categories from 12 to 4 in production because most questions don't need a phone call.

2. **It remembers everything.** Every interaction updates a persistent profile. Goon knows my name, my default party size, my preferred dinner time, my allergies, my regular businesses, my patterns ("usually books dinner on Friday mornings"). This is the moat the original TalkTo never had — they had no persistent user model.

3. **It sounds human when it calls.** The AI voice agent doesn't say "I'm calling on behalf of a customer." It says "Hi, I'd like to make a reservation for two tonight around 7." The original TalkTo learned that any "on behalf of" framing triggers telemarketer defenses.

4. **It handles failure gracefully.** When a call fails (busy, voicemail, wrong number, IVR maze, hostile employee), it tells me what happened and offers a plan: retry, try online instead, or give me the number so I can call myself.

5. **It nudges me at the right time.** Not speculatively ("is there anything to say today?" — expensive and annoying) but from concrete triggers: scheduled followups, pattern matches ("it's Friday and you usually book dinner"), overdue recurring services ("haircut cycle is 6 weeks, you're at 7").

---

## System Components

Goon decomposes into **9 independent components**. Each can be built, tested, and iterated on in isolation. They communicate through well-defined interfaces (function calls, database tables, webhooks).

This decomposition is designed for parallel agent execution. Each component is a self-contained unit of work with clear inputs, outputs, and no shared mutable state with other components during development.

---

### Component 1: SMS Gateway

**What it does**: Receives SMS from Twilio, authenticates the sender, dispatches to the orchestrator, sends responses back.

**Inputs**: Twilio webhook POST (From, Body, MessageSid)

**Outputs**: SMS response to sender

**Key behaviors**:
- Allowlist check: only registered phone numbers get processed
- Unregistered senders get routed to the leads handler (Component 9)
- Subscription check: inactive users get a renewal nudge
- SMS segment math: target 160 chars (GSM 7-bit). No emoji — forces unicode encoding which halves segment capacity to 70 chars. Split at sentence boundaries if >160.
- Acknowledge Twilio immediately, process async

**External dependencies**: Twilio API

**Internal dependencies**: Calls Orchestrator (Component 3). Calls Auth (Component 8 — user lookup, subscription check). Calls Leads (Component 9 — for unregistered senders).

**Data owned**: `message_log` table (append-only log of all inbound/outbound SMS)

**Key technical decision**: Use GSM 7-bit encoding exclusively (no emoji). This was an obsession of the original TalkTo — their templates were all sub-160 chars. At scale, this halves SMS costs.

---

### Component 2: Voice Inbound

**What it does**: When a user calls the Goon number, a conversational AI agent answers and can do everything the SMS interface does — answer questions, look things up, initiate calls to businesses.

**Inputs**: Incoming phone call (Twilio voice webhook → Vapi)

**Outputs**: Voice conversation with user

**Key behaviors**:
- Twilio forwards voice calls to Vapi's SIP endpoint
- Vapi runs a conversational assistant with access to the same tools as the SMS orchestrator
- User memory is injected into the Vapi assistant's system prompt at call start
- The voice agent can trigger outbound calls to businesses mid-conversation

**External dependencies**: Twilio (voice routing), Vapi.ai (conversational AI)

**Internal dependencies**: Shares tools with Orchestrator (Component 3). Reads user memory (Component 6).

**Key technical decision**: Vapi over PersonaPlex for voice. PersonaPlex (NVIDIA's full-duplex model) has better voice quality (~170ms latency, interruption handling) but it's a model, not a telephony platform. You'd need to self-host on an A100 GPU and build your own SIP bridge, audio streaming, codec transcoding, DTMF handling, and call control. Vapi abstracts all of this: native Twilio integration, built-in tool calling, call recording, transcription, webhook callbacks. ~$0.10-0.15/min all-in. PersonaPlex is a good v2 optimization if we want to self-host for cost or quality.

---

### Component 3: Orchestrator (The Brain)

**What it does**: Takes a user message + their memory + the business fact cache, decides how to answer, and returns a response. This is where the Resolution Ladder lives.

**Inputs**: User message (string), user memory (profile + recent history), active tasks

**Outputs**: Response text, optional action (call_business, schedule_followup), memory updates

**Key behaviors — The Resolution Ladder**:

This is the single most important architectural decision. It's a priority cascade — try the cheapest/fastest option first, escalate only when necessary:

```
1. CACHE (~free, <50ms)
   Do we have a cached, unexpired answer for this business + question type?
   → Yes: respond immediately
   → No: step 2

2. GOOGLE PLACES (~$0.002, ~200ms)
   Can structured data answer this? Hours, address, phone, ratings,
   takeout/delivery, reservable, open_now.
   → Yes: respond + cache the fact
   → No: step 3

3. WEB SEARCH (~$0.01, ~1-3s)
   Can we find it online? Menus, pricing, reviews, specials.
   → Yes: respond + cache the fact
   → No: step 4

4. PRE-CALL CHECKS (free, <200ms)
   Before committing to a phone call:
   - Is the business open right now? (don't call closed businesses)
   - Is the phone number trustworthy? (check score from past calls)
   - Is this a chain? (corporate numbers ≠ local store)
   - Should we confirm details with the user first? (for reservations/appointments)

5. AI VOICE CALL (~$0.10-0.20/min, ~2-5 min)
   Call the business. Handle IVR, hold, voicemail, wrong number.
   → Success: respond + cache the fact
   → Failure: retry strategy per failure type
```

**Why this matters**: The original TalkTo's biggest cost was human agents calling businesses. Their auto-answer system (RoboQuery) could only handle 4 exact-match query types in production. With modern tools, we can answer 80%+ of questions without ever dialing. At $0.10+/min for Vapi vs $0.002 for a Places API call, this saves real money even at prototype scale.

**Implementation**: The resolution ladder is encoded in two places: (a) the LLM system prompt (explicit instruction to follow the cascade), and (b) the tool ordering (tools listed from cheapest to most expensive, with descriptions that reinforce the ladder).

**External dependencies**: Anthropic Claude API (claude-sonnet-4-5)

**Internal dependencies**: All tool components (4, 5, 6, 7). Produces memory updates consumed by Component 6.

**Data owned**: None directly (orchestration is stateless; state lives in memory, cache, and call log)

**Key technical decision**: Python/FastAPI over Node/Express. The domain is data-heavy, not I/O-heavy. Async tool-calling loops are cleaner with Python asyncio + anthropic SDK. If we ever want local NLP as a pre-filter, the ML ecosystem is vastly better. The original TalkTo was Django/Python for the same reasons.

---

### Component 4: Business Intelligence (Fact Cache + Google Places + Web Search)

**What it does**: Provides business information from three sources at three price/speed tiers. Caches everything learned for future use.

**Sub-components**:

**4a. Fact Cache**
- Stores every business fact learned from any source (Places, web, phone calls)
- Schema: `(place_id, fact_type, question, answer, source, verified_at, expires_at, confidence)`
- Expiry by source: Google hours = 7 days, web menu = 14 days, phone-verified = 30 days
- Confidence scoring: phone call = 1.0, Google Places = 0.8, web search = 0.6
- **Key lesson from original TalkTo**: Their entire RoboQuery auto-answer system existed to cache exactly this. If user A asks about Delfina's hours and we call, then I ask the same thing next week, we should answer from cache.

**4b. Google Places Integration**
- Search by name + location → get place_id, then fetch details
- Essential fields: name, phone, address, lat/lng, opening_hours (structured by day + open_now), types, website, business_status
- Valuable fields: price_level, rating, takeout/delivery/dine_in, reservable
- **Key insight from codebase review**: The original TalkTo used 15+ data sources (SimpleGeo, Factual, Locu, Foursquare, CityGrid, Yelp, Bing...) with manual entity crosswalk between them. All now dead or irrelevant. Google Place IDs are the canonical identifier. No crosswalk needed.

**4c. Web Search**
- Tavily API (or equivalent) for finding info not in structured APIs
- Menus, specific pricing, specials, events, detailed reviews
- Results cached as business facts

**Inputs**: Business name, question type, optional location

**Outputs**: Answer string + source attribution, or null (escalate to call)

**Data owned**: `business_facts` table, `ivr_maps` table

---

### Component 5: Voice Outbound (Calling Businesses)

**What it does**: Places AI voice calls to businesses on the user's behalf. Handles the full lifecycle: pre-call checks, call execution, outcome classification, result delivery, retry scheduling.

**Sub-components**:

**5a. Pre-Call Check**
- Is business open now? (Google Places `open_now`)
- Is phone number reliable? (check `phone_scores` — 2+ failures = flag)
- Is this a chain? (corporate numbers route to call centers, not local stores)
- If closed: "They close at 9. Want me to call tomorrow morning?" + schedule followup

**5b. Call Execution**
- Vapi outbound call API with custom system prompt per call
- The system prompt is the most critical piece of this component
- First message sounds like a human caller, NOT "on behalf of"
- Task-specific prompts for: information queries, reservations, appointments, availability checks, custom requests
- IVR navigation instructions (press 0, say "representative", capture info from IVR announcements)
- Hold timeout: 90 seconds max
- Voicemail: hang up (don't leave message), schedule retry
- Max call duration: 180 seconds

**5c. Outcome Classification**
- Classifies every call result into: `success`, `busy`, `no_answer`, `voicemail`, `wrong_number`, `hung_up`, `timeout`, `ivr_stuck`, `hostile`
- Each outcome triggers a different user message and retry strategy
- **Key insight from original TalkTo**: Their robotcall module tracked `is_ivr`, `is_success`, `fail_reason`, `employee_answered_with_question` as separate fields. IVR was the #1 failure mode. Wrong numbers were #2.

**5d. Retry System**
- Busy → retry in 5 min
- No answer → retry in 10 min
- Voicemail → retry in 30 min (or user can say "try online instead")
- Wrong number → blacklist number, ask user or search for alternate
- Max 2 retries per call, then give up gracefully with the business phone number
- Retries tracked in `call_log` with `retry_count` and `retry_after`
- Cron job checks for pending retries every 5 minutes

**5e. Result Delivery**
- On success: summarize transcript into SMS-length result, text user
- Store transcript, summary, and outcome in call_log
- Cache the answer as a business fact (Component 4a)

**Inputs**: Call plan (business name, phone, task, task type, user details)

**Outputs**: SMS to user with result (async, via webhook)

**External dependencies**: Vapi.ai (outbound calls, recording, transcription)

**Data owned**: `call_log` table, `phone_scores` table

**Key insight**: The call prompts need to be living documents. Every failed call teaches us something. The original TalkTo's most battle-tested code was error handling for business calls.

---

### Component 6: Memory & Personal OS

**What it does**: Maintains a persistent, evolving profile for each user. Every interaction makes Goon smarter about that person.

**Storage format**: Markdown file per user (`profile.md`) + JSONL conversation log + JSON task list.

**Why markdown**: LLM-readable AND LLM-writable. The agent can read the profile as context and write updates back to it. No ORM, no schema migration, no impedance mismatch. Inspired by OpenClaw/Pi — simple files that an agent can reason about directly.

**What's in the profile**:
- Identity: name, phone, location
- Preferences: food, timing, party size, communication style
- Regular businesses: name, phone, frequency, typical patterns
- Patterns: recurring behaviors ("books dinner Friday mornings", "haircut every 6 weeks")
- Recent context: last few interactions, active tasks

**Memory update flow**:
1. LLM reads profile as part of system prompt
2. During conversation, LLM calls `update_memory` tool with new facts
3. A secondary LLM call merges updates into the existing profile.md
4. Rules: preserve existing info, only overwrite on contradiction, note emerging patterns

**Conversation history strategy**:
- Store last 20 messages in memory
- Include last 5 in LLM context (for immediate continuity)
- Also include last interaction with the specific business being discussed (for topic continuity)
- **Key insight from codebase review**: The original TalkTo's Discussion model tracked per-business conversation threads. 10 generic recent messages may miss relevant business-specific context from 3 days ago.

**Inputs**: Conversation events, call results, LLM-generated updates

**Outputs**: Formatted memory for system prompt injection

**Data owned**: User data directory (`/data/users/{phone}/`)

---

### Component 7: Proactive Intelligence

**What it does**: Sends timely, useful nudges based on concrete triggers — not speculation.

**Critical design decision**: Do NOT run an LLM call for every user every morning to ask "anything to say?" That costs $0.03-0.05/user/day and trains users to ignore messages when it guesses wrong. Instead:

**Trigger computation is deterministic** (no LLM):
- Scheduled followups that are due (from `scheduled_tasks` table)
- Pattern matches against today's context (e.g., "it's Friday" + profile says "usually books dinner Friday")
- Overdue recurring services (profile says "haircut every 6 weeks, last: date X")
- Pending call retries that are due

**Message composition uses LLM** (but only when triggered):
- Given the trigger(s) and user profile, compose a short, warm SMS
- Under 160 chars, no emoji, one action per message
- If no triggers fire → no message. Silence is fine.

**Inputs**: User profiles, scheduled_tasks table, call_log (retries), current date/time

**Outputs**: SMS messages (only when triggered)

**Runs on**: Cron — proactive checks at 8am daily, retry checks every 5 minutes

---

### Component 8: Subscription & Billing

**What it does**: Registration, authentication, subscription management.

**Flow**:
1. User visits `getgoon.com` → enters phone + email + name
2. Stripe Checkout ($19.99/month)
3. On success: create user record, add to allowlist, send welcome SMS
4. Stripe webhooks update subscription status (active, past_due, canceled)
5. Canceled users stop getting processed but data is retained

**States**: `trial` → `active` → `past_due` → `canceled` (+ `allowlisted` override for testers)

**Data owned**: `users` table (id, phone, name, email, stripe_customer_id, subscription_status, trial_ends_at, allowlisted)

**Frontend**: Simple Next.js app — landing page, signup flow, billing management. Optional: memory dashboard where users can view/edit their profile.md.

**External dependencies**: Stripe (checkout, subscriptions, webhooks)

---

### Component 9: Leads & Growth Engine

**What it does**: Handles unregistered users who text the number. Logs their attempts, sends warm teaser responses, and re-engages warm leads.

**Unregistered user flow**:
1. Log the attempt (phone, message, timestamp)
2. First-time: warm teaser that partially answers their question + signup link
3. Repeat visitor (2-3x): more specific teaser referencing what they've been asking
4. Persistent (4+x): direct signup push ("You've texted 5 times — seems like you need a Goon")

**Re-engagement** (weekly cron):
- Find leads who texted 2+ times in the last 7 days but didn't sign up
- Compose a personalized follow-up referencing what they were trying to do
- Under 160 chars, warm, not salesy

**Admin dashboard**:
- Who's texting, what they're asking, how often
- Conversion funnel: unregistered → teaser → signup
- Useful for understanding demand and common use cases

**Data owned**: `unregistered_attempts` table

---

## Component Dependency Map

```
                    ┌─────────────┐
                    │  1. SMS      │
                    │  Gateway     │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌──────────┐
     │ 8. Auth    │ │ 3. Orch-  │ │ 9. Leads │
     │ & Billing  │ │ estrator  │ │ Engine   │
     └────────────┘ └─────┬─────┘ └──────────┘
                          │
           ┌──────────────┼──────────────┐
           │              │              │
           ▼              ▼              ▼
    ┌────────────┐ ┌───────────┐ ┌────────────┐
    │ 4. Business│ │ 5. Voice  │ │ 6. Memory  │
    │ Intel      │ │ Outbound  │ │ & Profile  │
    └────────────┘ └───────────┘ └────────────┘
                                       │
                                       ▼
                                ┌────────────┐
                                │ 7. Proactive│
                                │ Intel      │
                                └────────────┘

    ┌────────────┐
    │ 2. Voice   │  (standalone — Twilio routes to Vapi,
    │ Inbound    │   shares tools with Orchestrator)
    └────────────┘
```

---

## Parallelization Strategy (Gas Town)

These components are designed to be built in parallel by independent agents. Here's how to sling them at a Gas Town rig:

### Fully Independent (can start immediately, zero dependencies on other components)

| Component | Why it's independent | Interface contract |
|---|---|---|
| **4a. Fact Cache** | Pure data layer — SQLite table + read/write functions | `check_cache(biz, type) → str`, `store_fact(...)` |
| **4b. Google Places** | External API wrapper | `search_places(query, location) → PlaceResult` |
| **4c. Web Search** | External API wrapper | `search_web(query) → str` |
| **6. Memory** | File I/O — reads/writes markdown + JSONL | `load_memory(user_id) → Memory`, `update_memory(...)` |
| **8. Auth & Billing** | Stripe + DB — no runtime deps on other components | `get_user(phone) → User`, `is_active(user) → bool` |
| **9. Leads Engine** | Self-contained unregistered user handling | `handle_unregistered(phone, body)` |

**Six agents can start building these right now.** Each produces a module with a clean function interface. No shared state during development.

### Depends on Externals Only (can start after account setup)

| Component | Dependency | Setup needed |
|---|---|---|
| **1. SMS Gateway** | Twilio account + number | Buy number, configure webhook URL |
| **2. Voice Inbound** | Twilio + Vapi account | Import number into Vapi, configure assistant |
| **5. Voice Outbound** | Vapi account | Same Vapi setup as Voice Inbound |

### Integration Layer (needs other components)

| Component | What it integrates | When to build |
|---|---|---|
| **3. Orchestrator** | Wires together: SMS input → resolution ladder (4a, 4b, 4c) → voice call (5) → memory (6) → SMS output (1) | After components 4, 5, 6 have stable interfaces |
| **7. Proactive** | Reads memory (6), writes SMS (1), reads call_log (5) | After components 1, 5, 6 are working |

### Suggested Gas Town Convoy Plan

```
CONVOY 1 (parallel, day 1-3): "The Foundation"
├── Agent A: Component 4a — Fact Cache (SQLite schema + CRUD)
├── Agent B: Component 4b — Google Places wrapper
├── Agent C: Component 4c — Web Search wrapper
├── Agent D: Component 6 — Memory system (profile.md + JSONL)
├── Agent E: Component 8 — Auth & Billing (users table + Stripe)
└── Agent F: Component 9 — Leads Engine

CONVOY 2 (parallel, day 2-4): "The Pipes"
├── Agent G: Component 1 — SMS Gateway (Twilio webhook + send)
├── Agent H: Component 5 — Voice Outbound (Vapi integration + prompts)
└── Agent I: Component 2 — Voice Inbound (Vapi assistant config)

CONVOY 3 (sequential, day 4-6): "The Brain"
└── Agent J: Component 3 — Orchestrator
    (wires everything together, implements resolution ladder,
     tool loop, system prompt)

CONVOY 4 (after brain works, day 6-8): "Intelligence"
├── Agent K: Component 7 — Proactive Intelligence
└── Agent L: Component 5d — Retry System (cron + call_log)

CONVOY 5 (after core works, day 8-10): "Polish"
├── Agent M: Error handling & graceful degradation
├── Agent N: Next.js registration site (getgoon.com)
└── Agent O: Admin dashboard
```

---

## Key Technical Decisions (The Ones That Matter)

Most implementation details are straightforward. These are the ones where the choice has significant consequences:

### 1. Vapi for voice (not PersonaPlex, not Retell, not Bland, not building our own)

**Why Vapi**: Native Twilio integration. Outbound call API (critical — we need to place calls programmatically). Built-in tool calling (voice agent can look things up mid-call). Custom persona prompts. Call recording + transcription. Webhook callbacks for call events. ~$0.10-0.15/min all-in.

**Why not PersonaPlex**: Better voice quality but it's a model, not a platform. Self-hosting on A100 ($2-3/hr) + building SIP bridge + audio streaming + codec transcoding + DTMF + call control = weeks of infra work before you make your first call.

**Why not build our own**: Twilio + Deepgram + Claude + ElevenLabs could be wired together, but you'd be rebuilding what Vapi already abstracts: turn-taking, interruption handling, silence detection, barge-in, endpointing. Not worth it for a prototype.

### 2. Python/FastAPI (not Node/Express)

**Why**: Async tool-calling loops are cleaner with asyncio + anthropic SDK. Data pipeline work (caching, memory, analytics) is more natural in Python. If we add local NLP later, Python ML ecosystem is incomparably better. The original TalkTo was Django/Python for the same reasons.

### 3. Claude Sonnet 4.5 (not GPT-4o, not Opus, not Haiku)

**Why Sonnet**: Best balance of quality/speed/cost for this use case. The orchestrator makes 2-5 tool calls per user message — Sonnet handles the agentic loop well. Opus is overkill for "should I call or search?" decisions. Haiku is too weak for nuanced call prompt generation.

### 4. SMS-first, no app (not WhatsApp, not iMessage, not a web app)

**Why SMS**: Universal. No download. No account creation. Works on every phone. The original TalkTo was an iOS app — distribution was a constant struggle. SMS eliminates that entirely. The tradeoff: limited rich media (no images, no links in iMessage style). For v0, that's fine — the interface is text in, text out.

**Why not WhatsApp**: Would work great internationally but adds complexity (WhatsApp Business API, separate number management). Good v2 for international expansion.

### 5. Markdown files for memory (not a database, not vector store)

**Why**: LLM-readable AND LLM-writable. No serialization layer. The agent reads the profile as a markdown string in the system prompt and writes updates back as markdown. Zero impedance mismatch. For a single-digit user prototype, file I/O on local disk is simpler and more debuggable than a database. You can `cat profile.md` to see exactly what Goon knows about you.

**Why not vector store**: We're not doing RAG over thousands of documents. We're loading a single ~1KB profile into context. Vector search adds complexity with no benefit at this scale.

### 6. No emoji in SMS (GSM 7-bit only)

**Why**: SMS encoding is binary — GSM 7-bit gives you 160 chars per segment. Any unicode character (including emoji) forces UCS-2 encoding, which cuts segment capacity to 70 chars. A single emoji in a 150-char message turns it from 1 segment ($0.0079) into 3 segments ($0.0237). At scale, this is a 3x cost difference. The original TalkTo was obsessive about this. Goon uses text equivalents: `[done]` instead of ✅, `[call]` instead of 📞.

---

## Success Criteria

### For v0 (personal prototype)

- [ ] I can text the number and get useful answers about local businesses
- [ ] It can call a restaurant and make a reservation on my behalf
- [ ] It remembers my preferences across conversations
- [ ] When a call fails, it tells me why and offers alternatives
- [ ] It nudges me about things I regularly do (Friday dinner, haircut)
- [ ] 80%+ of my questions are answered without placing a phone call

### For v1 (friends & early users)

- [ ] Someone can sign up at getgoon.com and start texting within 2 minutes
- [ ] Subscription billing works end-to-end
- [ ] Unregistered texters get teaser responses that drive signups
- [ ] All-in cost per active user is under $10/month

---

## What This Document Does NOT Cover

- **Implementation details** — see `goon-blueprint.md` for the full technical spec with code samples, database schemas, and API integration details.
- **Pricing strategy** — $19.99/month is a starting point. Needs validation.
- **Marketing / launch plan** — not relevant until the thing works.
- **Legal / compliance** — TCPA, FCC regulations on automated calling, Twilio acceptable use. Needs review before any user-facing launch.
- **International expansion** — WhatsApp integration, non-US business directories, multilingual voice agents. All v2+.

---

## Appendix: The Original TalkTo Lessons That Shaped This Design

| Lesson | How it manifests in Goon |
|---|---|
| Most questions don't need a phone call | Resolution Ladder — 5-step cascade, call is last resort |
| Human agents are the cost center | AI voice agents via Vapi replace the entire call center |
| Auto-answer was too brittle (4 exact-match categories) | LLM handles any natural language question |
| IVR is the #1 call failure mode | Vapi prompt includes IVR navigation + IVR map storage |
| Wrong numbers are #2 | Phone scoring system deprioritizes after 2+ failures |
| "On behalf of" triggers telemarketer defenses | Voice agent sounds like a regular human caller |
| No persistent user model = no personalization | Memory system with evolving markdown profiles |
| 15 data sources with manual crosswalk | Google Places API as single canonical source |
| SMS templates were sub-160 chars | GSM 7-bit only, no emoji, target 160 chars |
| App distribution was a constant struggle | SMS-native, zero friction, no download |
| Monetization was uncertain | Simple subscription model |
| Response time transparency builds trust | "Calling now. Back in a few." |
| "Time saved" framing drives retention | Post-call: "Saved you a 5-min phone call" |

---

*Goon: your AI that does the thing so you don't have to.*