# Goon

## Your AI that does the thing so you don't have to.

### Technical Blueprint — February 2026

> A single phone number you can text or call. It handles tasks, calls businesses on your behalf, remembers everything about you, and gets smarter with every interaction. No humans in the loop.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture](#2-architecture)
3. [The Resolution Ladder (Don't Call When You Don't Need To)](#3-the-resolution-ladder)
4. [SMS Gateway](#4-sms-gateway)
5. [LLM Orchestrator](#5-llm-orchestrator)
6. [Voice Agent: Calling Businesses](#6-voice-agent-calling-businesses)
7. [Business Intelligence Layer](#7-business-intelligence-layer)
8. [Memory & Personal OS](#8-memory--personal-os)
9. [Proactive Intelligence](#9-proactive-intelligence)
10. [Subscription & Billing](#10-subscription--billing)
11. [Leads & Growth Engine](#11-leads--growth-engine)
12. [Error Handling & Graceful Degradation](#12-error-handling--graceful-degradation)
13. [Infrastructure & Deployment](#13-infrastructure--deployment)
14. [Build Order](#14-build-order)
15. [Lessons Absorbed from Original TalkTo](#15-lessons-absorbed)

---

## 1. System Overview

### What It Does

You text (or call) a single phone number. An AI:

- **Answers questions** about businesses (hours, availability, pricing) — without calling if possible
- **Calls businesses on your behalf** using an AI voice agent when a call is actually needed
- **Executes tasks** — makes reservations, checks stock, schedules appointments
- **Remembers everything** — your preferences, past requests, patterns, your businesses
- **Proactively nudges** — based on concrete triggers, not speculation

### What's Different from Original TalkTo (2011)

| Original TalkTo (2011) | Goon (2026) |
|---|---|
| Human call center (~$2-5/call) | AI voice agent (~$0.10/call) |
| Auto-answer limited to 4 exact-match query types | LLM answers any natural language question |
| 15+ data sources, manual entity crosswalk | Google Places API + web search (always fresh) |
| Consumer app, App Store distribution | SMS-native, zero friction |
| No user memory beyond credits | Persistent personal OS per user |
| Business claiming/opt-in needed for direct response | AI calls any business, opted in or not |
| Scaling limited by agent headcount | Scaling limited by API costs (near-zero marginal) |
| Revenue from premium tier + purchase intent leads | Simple subscription |

### Design Principles (from 16 years of hindsight)

1. **Don't call when you don't need to.** The original TalkTo's most painful lesson: most questions don't need a phone call. Exhaust every cheaper/faster option first.
2. **Cache everything.** Every call result, every Google Places lookup, every fact learned. The original system's entire auto-answer engine existed to avoid repeat calls.
3. **Phone calls fail in specific, predictable ways.** IVRs, wrong numbers, hold times, hostile employees, seasonal hours, chain vs local. Handle each one explicitly.
4. **SMS is terse.** Target 160 chars (one segment). Avoid emoji (forces unicode, cuts segment to 70 chars). The original templates were obsessively short.
5. **The hard part is operational edge cases**, not the AI or the telephony.
6. **Sound like a human caller.** Don't say "on behalf of" — it triggers telemarketer defenses.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    PHONE NUMBER                          │
│              (Twilio — SMS + Voice)                      │
│         Accepts texts AND incoming calls                 │
└──────────┬──────────────────────┬───────────────────────┘
           │ SMS                  │ Voice Call
           ▼                     ▼
┌──────────────────┐   ┌──────────────────────────┐
│  SMS Gateway     │   │  Vapi Voice Agent         │
│  (Twilio webhook │   │  (inbound: user calls     │
│   → server)      │   │   the number to talk)     │
└────────┬─────────┘   └────────────┬──────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                   ORCHESTRATOR                           │
│                  (Python / FastAPI)                      │
│                                                          │
│  1. Authenticate sender (allowlist check)                │
│  2. Load user memory                                     │
│  3. Run RESOLUTION LADDER (cheapest → most expensive)    │
│  4. Send response via SMS                                │
│  5. Update memory + business fact cache                  │
└──┬──────────┬──────────┬──────────┬─────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌────────┐┌────────┐┌─────────┐┌──────────┐
│ Cached │││ Places ││ Web     ││ Voice    │
│ Facts  ││ + Open ││ Search  ││ Call-Out  │
│        ││ Hours  ││         ││ (Vapi)   │
└────────┘└────────┘└─────────┘└──────────┘
   FREE     ~$0.002    ~$0.01    ~$0.10+/min
   ◄──── RESOLUTION LADDER: try cheap first ────►
```

### Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Telephony** | Twilio (SMS + Voice) | Single number for both, webhook-driven, battle-tested |
| **Voice AI (inbound)** | Vapi.ai | User calls the number — conversational AI with tool use |
| **Voice AI (outbound)** | Vapi.ai | AI calls businesses — custom personas, Twilio SIP, call recording |
| **Server** | Python / FastAPI | Async orchestration, better ML ecosystem, data-heavy domain |
| **LLM** | Claude API (claude-sonnet-4-5) | Intent classification, response gen, task planning |
| **Web Search** | Tavily API (or Anthropic web_search) | Finding business info not in structured APIs |
| **Business Data** | Google Places API (v2) | Structured hours, phone, address, ratings, attributes |
| **Fact Cache** | SQLite (v0) → Postgres (v1) | Cached business answers, phone scores, call outcomes |
| **Memory** | Markdown files + SQLite metadata | User profiles, conversation history, patterns |
| **Hosting** | Railway / Fly.io (v0) → AWS (v1) | Always-on webhook endpoint |
| **Billing** | Stripe | Subscription management |
| **Frontend** | Simple Next.js app | Registration, billing, memory dashboard |

### Why Python over Node

The original TalkTo was Django/Python for good reason. This domain is data-heavy, not I/O-heavy:
- Async tool-calling loops are cleaner with Python asyncio + anthropic SDK
- Data pipeline work (caching, memory, scheduled tasks) is more Pythonic
- If we ever want local NLP as a pre-filter before hitting Claude, the ML ecosystem is vastly better
- SQLite + pandas for analytics

---

## 3. The Resolution Ladder

**This is the single most important architectural decision.** The original TalkTo learned the hard way that most questions don't need a phone call. Their production auto-answer list got cut from 12 categories to 4 because even cached answers were unreliable — but the instinct was right.

With modern tools, we can answer 80%+ of questions without ever dialing a number.

```
User question arrives
│
▼
┌─────────────────────────────────────────┐
│  STEP 1: Check Business Fact Cache      │
│  Cost: FREE                             │
│  Latency: <50ms                         │
│                                          │
│  Do we have a cached, unexpired answer   │
│  for this business + question type?      │
│                                          │
│  YES → Respond immediately               │
│  NO  → Step 2                            │
└─────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│  STEP 2: Google Places Structured Data  │
│  Cost: ~$0.002                          │
│  Latency: ~200ms                        │
│                                          │
│  Can Google Places answer this?          │
│  - Hours / open_now                      │
│  - Address / phone / website             │
│  - Ratings / price level                 │
│  - Takeout / delivery / dine-in          │
│  - Reservable                            │
│                                          │
│  YES → Respond + cache the fact          │
│  NO  → Step 3                            │
└─────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│  STEP 3: Web Search                     │
│  Cost: ~$0.01                           │
│  Latency: ~1-3sec                       │
│                                          │
│  Can we find the answer online?          │
│  - Menu on Yelp / website               │
│  - Pricing on website                   │
│  - Reviews mentioning the thing          │
│  - Specials / events                     │
│                                          │
│  YES → Respond + cache the fact          │
│  NO  → Step 4                            │
└─────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│  STEP 4: Pre-Call Checks                │
│  Before committing to a phone call:     │
│                                          │
│  □ Is the business open right now?       │
│    NO → "They close at 9. Want me to    │
│          call tomorrow morning?"         │
│                                          │
│  □ Is the phone number trustworthy?      │
│    Check phone_scores table.             │
│    2+ failures → try alt number or ask   │
│    user for the number.                  │
│                                          │
│  □ Is this a chain? (is_chain flag)      │
│    YES → Prefer local number over        │
│    corporate. Search "[chain] [city]     │
│    phone" if needed.                     │
│                                          │
│  □ Confirm with user before calling?     │
│    For expensive tasks (reservations)    │
│    → confirm details first.              │
│    For simple info → just call.          │
│                                          │
│  All checks pass → Step 5               │
└─────────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│  STEP 5: AI Voice Call (Vapi)           │
│  Cost: ~$0.10-0.20/min                  │
│  Latency: ~2-5 min                      │
│                                          │
│  Call the business. Handle IVR, hold,    │
│  voicemail, wrong number, hostile.       │
│                                          │
│  On success → Respond + cache the fact   │
│  On failure → Retry strategy (see §12)   │
└─────────────────────────────────────────┘
```

### Implementation

The resolution ladder is encoded in the LLM system prompt AND in the tool ordering:

```python
RESOLUTION_LADDER_INSTRUCTION = """
CRITICAL: Follow this resolution order. Do NOT skip to calling.

1. CACHE: Check business_facts cache first (use check_cache tool)
2. PLACES: Try Google Places for structured data (use search_places tool)
3. WEB: Try web search for the answer (use search_web tool)
4. PRE-CALL: If you must call, run pre_call_check first
5. CALL: Only as last resort, or when the task REQUIRES human interaction
   (reservation, appointment, custom order)

Tasks that ALWAYS require a call:
- Making a reservation or appointment
- Asking about specific item availability (not on website)
- Custom orders or special requests
- Anything requiring back-and-forth negotiation

Tasks that NEVER require a call:
- Hours, address, phone number, website
- Whether they offer takeout/delivery
- General ratings or price level
- Menu (usually findable online)
"""
```

---

## 4. SMS Gateway

### Twilio Setup

```bash
# Buy a number
twilio phone-numbers:buy:local --area-code 415

# Configure webhooks
twilio phone-numbers:update +1XXXXXXXXXX \
  --sms-url https://your-server.com/webhook/sms \
  --voice-url https://your-server.com/webhook/voice
```

### Webhook Handler

```python
# app/routes/sms.py
from fastapi import APIRouter, Request, Response
from app.services.auth import get_user, log_unregistered_attempt
from app.services.orchestrator import process_message
from app.services.memory import load_memory, update_memory
from app.services.sms import send_sms
from app.services.leads import handle_unregistered

router = APIRouter()

@router.post("/webhook/sms")
async def handle_sms(request: Request):
    form = await request.form()
    sender = form["From"]
    body = form["Body"]
    message_sid = form["MessageSid"]

    # 1. Auth: check allowlist
    user = await get_user(sender)
    if not user:
        await handle_unregistered(sender, body)
        return Response(content="<Response></Response>",
                       media_type="text/xml")

    # 2. Check subscription
    if not user.is_active:
        await send_sms(sender,
            "Your subscription is inactive. "
            "Renew at https://yourdomain.com/billing")
        return Response(content="<Response></Response>",
                       media_type="text/xml")

    # 3. Load memory
    memory = await load_memory(user.id)

    # 4. Process (resolution ladder lives here)
    result = await process_message(user, memory, body)

    # 5. Send response
    await send_sms(sender, result.text)

    # 6. Kick off async call if needed
    if result.action == "call_business":
        import asyncio
        asyncio.create_task(
            initiate_outbound_call(user, result.call_plan)
        )

    # 7. Update memory + fact cache
    await update_memory(user.id, body, result)

    return Response(content="<Response></Response>",
                   media_type="text/xml")
```

### SMS Sending (Segment-Aware)

```python
# app/services/sms.py
import re
from twilio.rest import Client

client = Client(TWILIO_SID, TWILIO_AUTH)
GSM_PATTERN = re.compile(r'^[\x00-\x7F]*$')

def calculate_segments(body: str) -> int:
    """SMS segment math. Unicode (emoji) halves capacity."""
    is_gsm = GSM_PATTERN.match(body) is not None
    if is_gsm:
        return 1 if len(body) <= 160 else -(-len(body) // 153)  # ceiling div
    else:
        return 1 if len(body) <= 70 else -(-len(body) // 67)

async def send_sms(to: str, body: str):
    """Send SMS, splitting if needed. Avoids emoji to stay in GSM encoding."""
    # Strip emoji to stay in GSM 7-bit (160 char segments vs 70)
    body = strip_emoji(body)

    if len(body) <= 160:
        await _send(to, body)
    elif len(body) <= 480:
        # 3 segments max for normal responses
        await _send(to, body)
    else:
        # Split at sentence boundaries
        chunks = split_at_sentences(body, max_chars=460)
        for chunk in chunks:
            await _send(to, chunk)

async def _send(to: str, body: str):
    client.messages.create(to=to, from_=GOON_NUMBER, body=body)

def strip_emoji(text: str) -> str:
    """Replace emoji with text equivalents."""
    replacements = {
        '\U0001f4de': '[call]',   # 📞
        '\u2705': '[done]',        # ✅
        '\u274c': '[x]',           # ❌
        '\U0001f551': '[time]',    # 🕑
    }
    for emoji, replacement in replacements.items():
        text = text.replace(emoji, replacement)
    # Strip any remaining non-GSM characters
    return text.encode('ascii', 'ignore').decode('ascii') if not GSM_PATTERN.match(text) else text
```

---

## 5. LLM Orchestrator

The brain. Takes user input + memory + fact cache, follows the resolution ladder.

```python
# app/services/orchestrator.py
import anthropic
from app.services.cache import check_cache, store_fact
from app.services.places import search_places
from app.services.search import search_web
from app.services.calls import pre_call_check, initiate_call
from app.services.memory import format_memory

client = anthropic.AsyncAnthropic()

TOOLS = [
    {
        "name": "check_cache",
        "description": "Check if we have a cached answer for this business + question. ALWAYS try this first.",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "fact_type": {"type": "string", "enum": [
                    "hours", "phone", "address", "menu", "pricing",
                    "reservation_policy", "availability", "attributes", "general"
                ]}
            },
            "required": ["business_name", "fact_type"]
        }
    },
    {
        "name": "search_places",
        "description": "Search Google Places for structured business data (hours, phone, address, ratings, attributes). Try this before web search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {"type": "string", "description": "City or address for location bias"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_web",
        "description": "Search the web for business info not available in Google Places (menus, specific pricing, specials, detailed reviews).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "pre_call_check",
        "description": "Run pre-call validation before calling a business. Checks: is business open now? Is phone number reliable? Is this a chain?",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "business_phone": {"type": "string"},
                "place_id": {"type": "string"}
            },
            "required": ["business_name", "business_phone"]
        }
    },
    {
        "name": "call_business",
        "description": "LAST RESORT. Initiate an AI voice call to a business. Only use after exhausting cache, places, and web search — OR when the task requires human interaction (reservation, appointment, custom order).",
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "business_phone": {"type": "string"},
                "task": {"type": "string", "description": "What to ask or do, stated naturally"},
                "task_type": {"type": "string", "enum": [
                    "information", "reservation", "appointment",
                    "availability_check", "custom_request"
                ]},
                "details": {"type": "object", "description": "Structured details (party_size, date, time, name, etc.)"}
            },
            "required": ["business_name", "business_phone", "task", "task_type"]
        }
    },
    {
        "name": "update_memory",
        "description": "Save a new fact or preference about the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": [
                    "preference", "fact", "routine",
                    "business_relationship", "task_result"
                ]},
                "content": {"type": "string"}
            },
            "required": ["category", "content"]
        }
    },
    {
        "name": "schedule_followup",
        "description": "Schedule a future SMS to the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "when": {"type": "string", "description": "ISO datetime or relative ('in 2 hours', 'tomorrow 9am')"},
                "trigger": {"type": "string", "description": "Why this followup exists (for proactive system)"}
            },
            "required": ["message", "when"]
        }
    }
]

def build_system_prompt(user, memory) -> str:
    return f"""You are Goon, a personal AI concierge accessible via SMS.
You are texting with {user.name} (phone: {user.phone}).
Today: {datetime.now().isoformat()}

{RESOLUTION_LADDER_INSTRUCTION}

## SMS Constraints
- Target 160 chars for simple answers (one SMS segment)
- Max 320 chars for detailed answers (two segments)
- Never use emoji (forces unicode encoding, halves SMS capacity)
- Be terse, warm, useful. Not robotic, not chatty.
- If a call is in progress, say so briefly: "Calling [business] now. Back in a few."

## User Memory
{memory.profile}

## Conversation History (last 5 + last interaction per active business)
{memory.formatted_recent}

## Active Tasks
{memory.active_tasks}

## Guidelines
- Confirm before calling for reservations/appointments (get details right)
- For simple info questions, just answer — don't ask permission to look it up
- Update memory when you learn something new about the user
- If the user's location matters and you don't know it, ask
- After a call completes, text the result concisely
- If a question is ambiguous, answer with what you have + ask for clarification
  (don't just ask — give them something useful immediately)
"""

async def process_message(user, memory, text: str):
    messages = [{"role": "user", "content": text}]
    system = build_system_prompt(user, memory)

    # Agentic loop: LLM decides which tools to call
    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=system,
            tools=TOOLS,
            messages=messages
        )

        # If no tool use, we have our final answer
        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            return OrchestratorResult(
                text="\n".join(text_blocks),
                memory_updates=extract_memory_updates(response),
                action=None
            )

        # Handle tool calls
        tool_results = []
        call_plan = None

        for block in response.content:
            if block.type == "tool_use":
                result = await execute_tool(block.name, block.input, user)

                # Special handling: if call_business was invoked, capture the plan
                if block.name == "call_business":
                    call_plan = block.input

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": str(result)
                })

        # Feed tool results back and continue loop
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # If a call was initiated, break — response comes async
        if call_plan:
            return OrchestratorResult(
                text=f"Calling {call_plan['business_name']} now. Back in a few.",
                memory_updates=extract_memory_updates(response),
                action="call_business",
                call_plan=call_plan
            )
```

---

## 6. Voice Agent: Calling Businesses

### Outbound Call via Vapi

```python
# app/services/calls.py
import vapi
from app.services.cache import get_phone_score, update_phone_score
from app.services.sms import send_sms
from app.db import db

vapi_client = vapi.Client(token=VAPI_API_KEY)

async def initiate_outbound_call(user, call_plan: dict):
    """Initiate Vapi outbound call. Returns immediately; result comes via webhook."""

    call = await vapi_client.calls.create(
        phone_number_id=VAPI_PHONE_NUMBER_ID,
        customer={"number": call_plan["business_phone"]},
        assistant={
            "model": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
                "messages": [{
                    "role": "system",
                    "content": build_call_prompt(call_plan, user)
                }]
            },
            "voice": {
                "provider": "11labs",
                "voiceId": "pNInz6obpgDQGcFmaJgB"  # natural, human-sounding
            },
            "firstMessage": build_first_message(call_plan),
            "endCallFunctionEnabled": True,
            "endCallMessage": "Thanks so much, have a great day!",
            "maxDurationSeconds": 180,
            "serverUrl": f"{BASE_URL}/webhook/vapi-events"
        }
    )

    # Store call record for tracking
    await db.execute("""
        INSERT INTO call_log (user_id, vapi_call_id, business_name,
            business_phone, task, task_type, place_id, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress')
    """, [user.id, call.id, call_plan["business_name"],
          call_plan["business_phone"], call_plan["task"],
          call_plan["task_type"], call_plan.get("place_id")])

    return call


def build_call_prompt(call_plan: dict, user) -> str:
    """
    Key lesson from original TalkTo: the first 3 seconds determine
    whether the employee hangs up. Sound like a regular human caller.
    Do NOT say "on behalf of" — it triggers telemarketer defenses.
    """

    base = f"""You are calling {call_plan['business_name']}.

## Your Task
{call_plan['task']}

## Rules
- Sound like a regular person calling. Be natural, friendly, efficient.
- Do NOT say "I'm calling on behalf of" or "I'm an AI" or "I'm an assistant"
- Just ask the question like a normal customer would
- Get straight to the point after a brief "hi"
- If they ask for a name, say "{user.name}"
- If they ask for a callback number, say "{GOON_NUMBER}"

## IVR / Phone Tree Navigation
If you reach an automated phone system:
1. Listen for "representative", "operator", or "speak to someone"
2. Common shortcuts: press 0, say "representative", say "agent"
3. If options are numbered, pick the most relevant
   (e.g., "press 2 for reservations")
4. If the IVR ITSELF answers your question (e.g., announces hours),
   capture that info — you don't need a human
5. If stuck in a loop after 30 seconds, hang up

## Hold
- If put on hold, wait up to 90 seconds
- After 90 seconds, hang up

## Edge Cases
- Voicemail: hang up (do not leave a message)
- Hostile/rude: "Sorry to bother you, thanks" → hang up
- Wrong number/disconnected: hang up immediately
- Employee needs clarification: rephrase your question with more context
- Complex answer (full menu, long list): capture key facts, don't need everything
- "We don't give that info over phone": thank them, hang up
- "Check our website": ask for the URL if you don't have it, hang up

## After Getting the Answer
- Confirm by repeating back: "Just to confirm, [answer]. Great, thanks!"
- Thank them and end the call
"""

    # Add task-specific instructions
    if call_plan["task_type"] == "reservation":
        details = call_plan.get("details", {})
        base += f"""
## Reservation-Specific
1. "Hi, I'd like to make a reservation."
2. Party size: {details.get('party_size', 'ask user')}
3. Date: {details.get('date', 'ask user')}
4. Time: {details.get('time', 'ask user')}
5. Name: {user.name}
6. If preferred time unavailable: ask what's available nearby and note it
   (do NOT book a different time without user confirmation)
7. Get confirmation number if they offer one
"""

    elif call_plan["task_type"] == "appointment":
        details = call_plan.get("details", {})
        base += f"""
## Appointment-Specific
1. "Hi, I'd like to schedule an appointment."
2. Service: {details.get('service', call_plan['task'])}
3. Preferred date/time: {details.get('date', 'flexible')} {details.get('time', 'flexible')}
4. Name: {user.name}
5. If they need a phone number: {GOON_NUMBER}
"""

    return base


def build_first_message(call_plan: dict) -> str:
    """
    Sound human. No "on behalf of" framing.
    The original TalkTo's intro ("calling impaired customer") was charming
    but told the business this wasn't a normal call.
    """
    task = call_plan["task"]

    if call_plan["task_type"] == "reservation":
        details = call_plan.get("details", {})
        return (f"Hi, I'd like to make a reservation for "
                f"{details.get('party_size', 'two')} "
                f"{details.get('date', 'tonight')} "
                f"around {details.get('time', '7')}. "
                f"Do you have anything available?")

    elif call_plan["task_type"] == "appointment":
        return f"Hi, I'm looking to schedule an appointment. {task}"

    elif call_plan["task_type"] == "availability_check":
        return f"Hi, quick question — {task}"

    else:
        return f"Hi, {task}"
```

### Call Completion Handler

```python
# app/routes/vapi_events.py
from fastapi import APIRouter, Request
from app.services.sms import send_sms
from app.services.cache import store_fact, update_phone_score
from app.services.memory import append_to_memory
from app.db import db

router = APIRouter()

@router.post("/webhook/vapi-events")
async def handle_vapi_event(request: Request):
    event = await request.json()
    msg_type = event.get("message", {}).get("type")

    if msg_type == "end-of-call-report":
        call_data = event["message"]["call"]
        call_id = call_data["id"]

        record = await db.fetch_one(
            "SELECT * FROM call_log WHERE vapi_call_id = ?", [call_id])
        if not record:
            return {"status": "ok"}

        transcript = event["message"].get("transcript", "")
        ended_reason = call_data.get("endedReason", "unknown")

        # Classify the outcome
        outcome = classify_call_outcome(ended_reason, transcript)

        # Update phone score
        await update_phone_score(
            record["place_id"],
            record["business_phone"],
            outcome
        )

        if outcome["success"]:
            # Summarize and text user
            summary = await summarize_call_result(
                transcript, record["task"])
            await send_sms(record["user_id"], summary)

            # Cache the fact
            await store_fact(
                place_id=record["place_id"],
                fact_type=record["task_type"],
                question=record["task"],
                answer=summary,
                source="phone_call"
            )

            # Update memory
            await append_to_memory(record["user_id"], {
                "type": "call_result",
                "business": record["business_name"],
                "task": record["task"],
                "result": summary,
                "timestamp": datetime.now().isoformat()
            })

            # Update call log
            await db.execute(
                "UPDATE call_log SET status='success', result=?, "
                "transcript=? WHERE vapi_call_id=?",
                [summary, transcript, call_id])

        else:
            # Handle failure — see §12
            await handle_call_failure(record, outcome)

    return {"status": "ok"}


def classify_call_outcome(ended_reason: str, transcript: str) -> dict:
    """
    Classify call outcome. Based on original TalkTo's failure taxonomy:
    busy, no_answer, ivr_stuck, voicemail, wrong_number,
    hostile, timeout, success
    """
    outcome = {"success": False, "reason": ended_reason, "retry": False}

    if ended_reason == "assistant-ended-call":
        # Agent chose to end — could be success or deliberate hangup
        if transcript and len(transcript) > 50:
            outcome["success"] = True
        else:
            outcome["reason"] = "no_useful_info"
            outcome["retry"] = True

    elif ended_reason == "customer-ended-call":
        # Business hung up
        if len(transcript) > 100:
            outcome["success"] = True  # They might have answered before hanging up
        else:
            outcome["reason"] = "hung_up"
            outcome["retry"] = True

    elif ended_reason in ("no-answer", "busy"):
        outcome["reason"] = ended_reason
        outcome["retry"] = True
        outcome["retry_delay_minutes"] = 10

    elif ended_reason == "voicemail":
        outcome["reason"] = "voicemail"
        outcome["retry"] = True
        outcome["retry_delay_minutes"] = 30

    elif ended_reason == "max-duration-reached":
        outcome["reason"] = "timeout"
        outcome["retry"] = False  # Probably stuck on hold

    return outcome
```

---

## 7. Business Intelligence Layer

### Fact Cache

Every answer learned — from Google Places, web search, or phone calls — gets cached.

```sql
-- app/db/schema.sql

CREATE TABLE business_facts (
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

-- Expiry defaults by source:
-- google_places hours: 7 days
-- google_places attributes: 30 days
-- web_search menu/pricing: 14 days
-- phone_call anything: 30 days
-- phone_call hours: 7 days (they change seasonally)

CREATE TABLE phone_scores (
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

-- After 2+ failures, try alternate number or ask user
-- After wrong_number, blacklist that number for this business

CREATE TABLE ivr_maps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT,
    phone TEXT NOT NULL,
    menu_structure TEXT,           -- JSON: {"1": "hours", "2": "reservations", "0": "operator"}
    last_updated TIMESTAMP,
    UNIQUE(place_id, phone)
);
```

### Fact Cache Operations

```python
# app/services/cache.py
from datetime import datetime, timedelta
from app.db import db

EXPIRY_DEFAULTS = {
    ("google_places", "hours"): timedelta(days=7),
    ("google_places", "attributes"): timedelta(days=30),
    ("web_search", "menu"): timedelta(days=14),
    ("web_search", "pricing"): timedelta(days=14),
    ("phone_call", "hours"): timedelta(days=7),
    ("phone_call", "reservation_policy"): timedelta(days=30),
    ("phone_call", "general"): timedelta(days=30),
}

async def check_cache(business_name: str, fact_type: str) -> str | None:
    """Check for unexpired cached fact."""
    row = await db.fetch_one("""
        SELECT answer, source, verified_at FROM business_facts
        WHERE business_name = ? AND fact_type = ?
        AND expires_at > ?
        ORDER BY confidence DESC, verified_at DESC
        LIMIT 1
    """, [business_name, fact_type, datetime.now()])

    if row:
        age = datetime.now() - row["verified_at"]
        return f"{row['answer']} (from {row['source']}, {age.days}d ago)"
    return None

async def store_fact(place_id: str, fact_type: str,
                     question: str, answer: str, source: str):
    """Store or update a business fact."""
    expiry = EXPIRY_DEFAULTS.get(
        (source, fact_type),
        timedelta(days=14)  # default
    )
    expires_at = datetime.now() + expiry
    confidence = {"phone_call": 1.0, "google_places": 0.8, "web_search": 0.6}.get(source, 0.5)

    await db.execute("""
        INSERT INTO business_facts (place_id, business_name, fact_type,
            question, answer, source, verified_at, expires_at, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(place_id, fact_type)
        DO UPDATE SET answer=?, source=?, verified_at=?, expires_at=?, confidence=?
    """, [place_id, "", fact_type, question, answer, source,
          datetime.now(), expires_at, confidence,
          answer, source, datetime.now(), expires_at, confidence])

async def update_phone_score(place_id: str, phone: str, outcome: dict):
    """Track phone number reliability."""
    success = 1 if outcome["success"] else 0
    await db.execute("""
        INSERT INTO phone_scores (place_id, phone, call_count, success_count,
            last_outcome, last_attempt)
        VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(place_id, phone)
        DO UPDATE SET
            call_count = call_count + 1,
            success_count = success_count + ?,
            last_outcome = ?,
            last_attempt = ?
    """, [place_id, phone, success, outcome["reason"], datetime.now(),
          success, outcome["reason"], datetime.now()])

async def get_phone_score(place_id: str, phone: str) -> dict | None:
    return await db.fetch_one(
        "SELECT * FROM phone_scores WHERE place_id = ? AND phone = ?",
        [place_id, phone])
```

### Pre-Call Check

```python
# app/services/calls.py (continued)

async def pre_call_check(business_name: str, business_phone: str,
                         place_id: str = None) -> dict:
    """Run all checks before committing to a phone call."""
    issues = []

    # 1. Is business open now?
    if place_id:
        places_data = await get_place_details(place_id)
        if places_data and not places_data.get("opening_hours", {}).get("open_now"):
            hours = format_hours(places_data.get("opening_hours", {}))
            issues.append({
                "type": "closed",
                "message": f"They appear to be closed right now. Hours: {hours}",
                "blocking": True
            })

    # 2. Phone number reliability
    score = await get_phone_score(place_id, business_phone)
    if score:
        if score["call_count"] >= 2 and score["success_count"] == 0:
            issues.append({
                "type": "bad_number",
                "message": f"This number has failed {score['call_count']} times "
                          f"(last: {score['last_outcome']}). Consider asking "
                          f"the user for the number or trying an alternate.",
                "blocking": True
            })
        elif score["last_outcome"] == "wrong_number":
            issues.append({
                "type": "wrong_number",
                "message": "This number was previously identified as wrong.",
                "blocking": True
            })

    # 3. Chain detection
    if place_id:
        places_data = places_data or await get_place_details(place_id)
        if is_chain_business(places_data):
            issues.append({
                "type": "chain",
                "message": "This appears to be a chain. The number may route "
                          "to corporate, not the local store.",
                "blocking": False
            })

    return {
        "ok": not any(i["blocking"] for i in issues),
        "issues": issues
    }
```

---

## 8. Memory & Personal OS

### Directory Structure

```
/data/users/
  +14155551234/
    profile.md          # Who they are, preferences, patterns
    conversations.jsonl  # Raw conversation log (append-only)
    calls.jsonl          # Outbound call records (append-only)
    tasks.json           # Active/pending tasks + scheduled followups
```

### profile.md (LLM-readable/writable)

```markdown
# Riley

## Basics
- Phone: +14155551234
- Location: Palo Alto, CA
- Registered: 2026-02-28

## Preferences
- Prefers text over voice for routine questions
- Likes Italian food, especially Sicilian
- Default party size: 2
- Prefers window seats
- Allergic to shellfish
- Communication style: terse, appreciates brevity

## Regular Businesses
- Pizzeria Delfina (415-xxx-xxxx) — ~2x/month, usually Friday
- Joe's Barbershop, University Ave — every ~6 weeks
- One Day Cleaners — pickup Thursdays

## Patterns
- Dinner reservations: usually asks Friday morning for that evening
- Preferred time slot: 7-8pm
- Haircut cycle: ~42 days (last: 2026-02-10, next due ~2026-03-24)

## Recent Context
- 2/28: Confirmed Delfina, 7:30pm, 2 people
- 2/25: Asked about flights to Sicily for April (not a Goon task, noted interest)
```

### Memory Read/Write

```python
# app/services/memory.py
import aiofiles
import json
from pathlib import Path
from datetime import datetime

USER_DATA_DIR = Path("/data/users")

class UserMemory:
    def __init__(self, profile: str, recent: list, active_tasks: list):
        self.profile = profile
        self.recent = recent
        self.active_tasks = active_tasks

    @property
    def formatted_recent(self) -> str:
        """Last 5 messages + last interaction per active business."""
        lines = []
        for m in self.recent[-5:]:
            direction = "You" if m["direction"] == "out" else "User"
            lines.append(f"[{m['timestamp'][:16]}] {direction}: {m['text'][:200]}")
        return "\n".join(lines)


async def load_memory(user_id: str) -> UserMemory:
    user_dir = USER_DATA_DIR / user_id

    # Profile
    profile_path = user_dir / "profile.md"
    try:
        async with aiofiles.open(profile_path, 'r') as f:
            profile = await f.read()
    except FileNotFoundError:
        profile = f"# New User\nPhone: {user_id}\nNo profile yet."

    # Recent conversations
    convos_path = user_dir / "conversations.jsonl"
    recent = []
    try:
        async with aiofiles.open(convos_path, 'r') as f:
            content = await f.read()
            recent = [json.loads(line) for line in content.strip().split('\n') if line]
    except FileNotFoundError:
        pass

    # Active tasks
    tasks_path = user_dir / "tasks.json"
    try:
        async with aiofiles.open(tasks_path, 'r') as f:
            tasks = json.loads(await f.read())
    except (FileNotFoundError, json.JSONDecodeError):
        tasks = []

    return UserMemory(profile, recent[-20:], tasks)


async def update_memory(user_id: str, user_message: str, result):
    """Append conversation + apply LLM-generated memory updates."""
    user_dir = USER_DATA_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat()

    # Append conversation
    async with aiofiles.open(user_dir / "conversations.jsonl", 'a') as f:
        await f.write(json.dumps({"timestamp": now, "direction": "in", "text": user_message}) + "\n")
        await f.write(json.dumps({"timestamp": now, "direction": "out", "text": result.text}) + "\n")

    # Apply memory updates (LLM rewrites relevant profile sections)
    if result.memory_updates:
        await apply_profile_updates(user_dir, result.memory_updates)


async def apply_profile_updates(user_dir: Path, updates: list):
    """Have the LLM merge new facts into the existing profile."""
    profile_path = user_dir / "profile.md"
    try:
        async with aiofiles.open(profile_path, 'r') as f:
            current = await f.read()
    except FileNotFoundError:
        current = ""

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""Current profile:

{current}

Apply these updates and return the complete updated profile.md:
{chr(10).join(f'- [{u["category"]}] {u["content"]}' for u in updates)}

Rules:
- Preserve all existing info unless explicitly contradicted
- Add new info to the appropriate section
- If a pattern emerges (e.g. 3rd time asking about Italian), note it
- Keep markdown format consistent
- Be concise — this is a reference doc, not prose

Return ONLY the updated markdown."""
        }]
    )

    async with aiofiles.open(profile_path, 'w') as f:
        await f.write(response.content[0].text)
```

---

## 9. Proactive Intelligence

**Key lesson from the codebase review:** Don't speculatively ask the LLM "is there anything to say?" every morning. That's expensive guessing ($0.03-0.05/user/day) and trains users to ignore your messages when it guesses wrong.

Instead: use structured triggers, then use the LLM only to compose the message.

```python
# app/services/proactive.py
from datetime import datetime, timedelta
from app.db import db
from app.services.memory import load_memory
from app.services.sms import send_sms

async def run_proactive_checks():
    """Run on cron. Only fires when there's a concrete trigger."""
    users = await db.fetch_all(
        "SELECT * FROM users WHERE subscription_status IN ('active', 'trial')")

    for user in users:
        triggers = await compute_triggers(user)
        if not triggers:
            continue

        # NOW use the LLM — but only to compose the message
        memory = await load_memory(user["id"])
        message = await compose_proactive_message(user, memory, triggers)

        if message:
            await send_sms(user["phone"], message)


async def compute_triggers(user) -> list:
    """Deterministic trigger computation. No LLM needed."""
    triggers = []
    now = datetime.now()

    # 1. Scheduled followups that are due
    tasks = await db.fetch_all("""
        SELECT * FROM scheduled_tasks
        WHERE user_id = ? AND due_at <= ? AND status = 'pending'
    """, [user["id"], now])
    for task in tasks:
        triggers.append({
            "type": "scheduled_followup",
            "detail": task["message"],
            "trigger": task["trigger"]
        })
        await db.execute(
            "UPDATE scheduled_tasks SET status='fired' WHERE id=?",
            [task["id"]])

    # 2. Pattern-based triggers (parsed from profile.md)
    memory = await load_memory(user["id"])
    profile = memory.profile

    # Friday morning + user usually books dinner
    if now.weekday() == 4 and now.hour < 12:
        if "usually Friday" in profile.lower() or "friday" in profile.lower():
            # Check if they already texted today about dinner
            recent_today = [m for m in memory.recent
                          if m["timestamp"][:10] == now.strftime("%Y-%m-%d")]
            if not any("dinner" in m["text"].lower() or
                      "reservation" in m["text"].lower()
                      for m in recent_today):
                triggers.append({
                    "type": "pattern_match",
                    "detail": "It's Friday — user typically books dinner"
                })

    # Recurring service due (haircut, cleaning, etc.)
    # Parse "next due ~YYYY-MM-DD" from profile
    import re
    due_matches = re.findall(r'next due ~(\d{4}-\d{2}-\d{2})', profile)
    for due_date_str in due_matches:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
        if due_date.date() <= now.date() <= (due_date + timedelta(days=3)).date():
            triggers.append({
                "type": "recurring_service_due",
                "detail": f"Recurring service due around {due_date_str}"
            })

    # 3. Pending call retries
    retries = await db.fetch_all("""
        SELECT * FROM call_log
        WHERE user_id = ? AND status = 'retry_pending'
        AND retry_after <= ?
    """, [user["id"], now])
    for retry in retries:
        triggers.append({
            "type": "call_retry",
            "detail": f"Retry call to {retry['business_name']}: {retry['task']}"
        })

    return triggers


async def compose_proactive_message(user, memory, triggers) -> str | None:
    """Use LLM to compose a natural message from triggers. Short call."""
    trigger_text = "\n".join(
        f"- [{t['type']}] {t['detail']}" for t in triggers)

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=200,
        messages=[{
            "role": "user",
            "content": f"""Compose a short SMS (under 160 chars) for {user['name']}.

Triggers:
{trigger_text}

User context:
{memory.profile[:500]}

Rules:
- Be warm and brief
- Ask if they want you to do something specific (call, book, check)
- One message, one action
- No emoji
- If multiple triggers, pick the most time-sensitive one

If the triggers don't warrant a message, respond with exactly: SKIP"""
        }]
    )

    text = response.content[0].text.strip()
    return None if text == "SKIP" else text
```

---

## 10. Subscription & Billing

### Database Schema

```sql
CREATE TABLE users (
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

CREATE TABLE message_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    direction TEXT,                     -- in | out
    body TEXT,
    twilio_sid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE call_log (
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

CREATE TABLE scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT REFERENCES users(id),
    message TEXT,
    trigger TEXT,                       -- why this task exists
    due_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'pending',      -- pending | fired | canceled
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE unregistered_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phone TEXT NOT NULL,
    body TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Registration Flow

```
User visits https://getgoon.com
  -> Enters phone number + email + name
  -> Stripe Checkout ($19.99/month)
  -> On success:
      -> Create user record (status = 'active')
      -> Send welcome SMS:
         "Hey [name], this is Goon. Text me when you
          need something done — restaurant reservations,
          business questions, anything. I'll handle it."
  -> On failure:
      -> User stays in unregistered_attempts if they've texted before
```

### Subscription Check

```python
# app/services/auth.py
from app.db import db
from datetime import datetime

async def get_user(phone: str):
    return await db.fetch_one(
        "SELECT * FROM users WHERE phone = ?", [phone])

def is_user_active(user: dict) -> bool:
    if user["allowlisted"]:
        return True
    if user["subscription_status"] == "active":
        return True
    if (user["subscription_status"] == "trial" and
        user["trial_ends_at"] and
        datetime.fromisoformat(user["trial_ends_at"]) > datetime.now()):
        return True
    return False
```

---

## 11. Leads & Growth Engine

### Unregistered User Handling

```python
# app/services/leads.py

async def handle_unregistered(phone: str, body: str):
    """Log attempt + send teaser response."""
    await db.execute(
        "INSERT INTO unregistered_attempts (phone, body) VALUES (?, ?)",
        [phone, body])

    # Count prior attempts
    count = await db.fetch_one(
        "SELECT COUNT(*) as n FROM unregistered_attempts WHERE phone = ?",
        [phone])

    if count["n"] == 1:
        # First time — warm welcome
        response = await compose_teaser(body, is_first=True)
    elif count["n"] <= 3:
        # Repeat visitor — more specific teaser
        response = await compose_teaser(body, is_first=False)
    else:
        # Persistent — direct signup push
        response = (f"You've texted {count['n']} times — looks like you "
                   f"could use a Goon. Sign up: https://getgoon.com")

    await send_sms(phone, response)


async def compose_teaser(body: str, is_first: bool) -> str:
    """Give a partial answer + signup nudge. Under 160 chars."""
    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=160,
        messages=[{
            "role": "user",
            "content": f"""Someone texted our service with: "{body}"

{'First time texter.' if is_first else 'Repeat texter.'}

Give a brief, helpful response that:
1. Acknowledges what they're asking
2. Gives a partial/teaser answer if possible
3. Mentions signup: https://getgoon.com

MUST be under 155 chars total. No emoji. Be warm, not salesy."""
        }]
    )
    return response.content[0].text


async def run_reengagement():
    """Weekly cron. Re-engage warm leads who've texted 2+ times."""
    warm_leads = await db.fetch_all("""
        SELECT phone, COUNT(*) as n,
               GROUP_CONCAT(body, ' | ') as messages
        FROM unregistered_attempts
        WHERE phone NOT IN (SELECT phone FROM users)
        GROUP BY phone
        HAVING n >= 2
        AND MAX(created_at) > datetime('now', '-7 days')
        AND MAX(created_at) < datetime('now', '-1 day')
    """)

    for lead in warm_leads:
        msg = await compose_reengagement(lead)
        await send_sms(lead["phone"], msg)
```

---

## 12. Error Handling & Graceful Degradation

### Call Failure → Retry Strategy

From the original TalkTo's failure taxonomy, each failure type gets a different response:

```python
# app/services/calls.py (continued)

async def handle_call_failure(record: dict, outcome: dict):
    """Route call failures to appropriate retry/response strategy."""
    user_id = record["user_id"]
    biz = record["business_name"]

    if outcome["reason"] == "busy":
        await send_sms(user_id, f"{biz}'s line is busy. Trying again in 5 min.")
        await schedule_retry(record, delay_minutes=5)

    elif outcome["reason"] == "no_answer":
        await send_sms(user_id,
            f"No answer at {biz}. I'll try again in 10 min.")
        await schedule_retry(record, delay_minutes=10)

    elif outcome["reason"] == "voicemail":
        await send_sms(user_id,
            f"Got voicemail at {biz}. I'll try again in 30 min, "
            f"or I can look online instead. Reply 'web' to skip the call.")
        await schedule_retry(record, delay_minutes=30)

    elif outcome["reason"] == "wrong_number":
        await send_sms(user_id,
            f"That number doesn't seem right for {biz}. "
            f"Do you have their number? Or I can look for another one.")
        # Blacklist this number for this business
        await db.execute(
            "UPDATE phone_scores SET last_outcome='wrong_number' "
            "WHERE place_id=? AND phone=?",
            [record["place_id"], record["business_phone"]])

    elif outcome["reason"] == "hung_up":
        if record.get("retry_count", 0) < 1:
            await send_sms(user_id,
                f"{biz} hung up. I'll try once more in a few minutes.")
            await schedule_retry(record, delay_minutes=15)
        else:
            await send_sms(user_id,
                f"Couldn't get through to {biz}. "
                f"You might need to call them directly at {record['business_phone']}.")

    elif outcome["reason"] == "timeout":
        await send_sms(user_id,
            f"Was on hold too long at {biz}. "
            f"Want me to try again later?")

    else:
        await send_sms(user_id,
            f"Had trouble reaching {biz}. "
            f"Want me to try again or look online instead?")

    # Update call log
    await db.execute(
        "UPDATE call_log SET status=? WHERE vapi_call_id=?",
        [f"failed_{outcome['reason']}", record["vapi_call_id"]])


async def schedule_retry(record: dict, delay_minutes: int):
    retry_count = record.get("retry_count", 0)
    if retry_count >= 2:
        # Max retries reached
        await send_sms(record["user_id"],
            f"Tried {record['business_name']} {retry_count + 1} times. "
            f"Giving up for now. Their number: {record['business_phone']}")
        return

    retry_after = datetime.now() + timedelta(minutes=delay_minutes)
    await db.execute("""
        UPDATE call_log SET status='retry_pending',
        retry_count=?, retry_after=?
        WHERE vapi_call_id=?
    """, [retry_count + 1, retry_after, record["vapi_call_id"]])
```

### Service Degradation

```python
# app/services/orchestrator.py (additions)

async def process_message_safe(user, memory, text: str):
    """Wrapper with graceful degradation."""
    try:
        return await process_message(user, memory, text)
    except anthropic.RateLimitError:
        return OrchestratorResult(
            text="Got it. Give me a moment — I'm a little busy right now.",
            action="retry",
            retry_delay=30
        )
    except anthropic.APIError:
        return OrchestratorResult(
            text="Having a brain glitch. Try again in a sec.",
            action=None
        )
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        return OrchestratorResult(
            text="Something went wrong on my end. Try again?",
            action=None
        )
```

---

## 13. Infrastructure & Deployment

### Prototype (Railway / Fly.io)

```
┌──────────────────────────────────┐
│      Railway.app / Fly.io         │
│                                    │
│  Python FastAPI Server             │
│  - Twilio SMS webhook              │
│  - Vapi event webhook              │
│  - Stripe webhook                  │
│  - APScheduler (cron jobs)         │
│                                    │
│  SQLite (single file)              │
│  User memory (local disk)          │
│                                    │
│  Cost: ~$5-10/month               │
└──────────────────────────────────┘
         +
┌──────────────────────────────────┐
│  External Services                │
│                                    │
│  Twilio    — $1/mo + usage        │
│  Vapi      — ~$0.10-0.15/min     │
│  Claude    — ~$0.002-0.01/call   │
│  Google Places — $0-200/mo        │
│  Stripe    — 2.9% + $0.30/txn    │
└──────────────────────────────────┘
```

### Cost Per User Per Month (moderate usage)

| Service | 100 texts, 5 calls | Notes |
|---|---|---|
| Twilio SMS (200 segments) | ~$1.50 | In + out |
| Vapi outbound (5 calls x 2 min) | ~$1.50 | Many calls avoided by resolution ladder |
| Claude API (~30 LLM calls) | ~$1.50 | Down from 50 — cache avoids redundant calls |
| Google Places (~20 lookups) | ~$0.40 | |
| Tavily web search (~10) | ~$0.50 | |
| Hosting | ~$2.00 | |
| **Total** | **~$7.40/user/month** | |

Subscription at $19.99/month = healthy margin, even with headroom for heavy users.

### Environment Variables

```bash
# .env
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
GOON_NUMBER=+1415XXXXXXX

VAPI_API_KEY=...
VAPI_PHONE_NUMBER_ID=...

ANTHROPIC_API_KEY=sk-ant-...

GOOGLE_PLACES_API_KEY=...
TAVILY_API_KEY=...

STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

DATABASE_URL=sqlite:///data/goon.db
USER_DATA_DIR=/data/users

ADMIN_PASSWORD=...
BASE_URL=https://getgoon.com
```

---

## 14. Build Order

### Phase 0: SMS Echo (Day 1)
- [ ] Buy Twilio number
- [ ] FastAPI server with SMS webhook
- [ ] Hardcode your phone number as only allowed sender
- [ ] Pipe incoming SMS -> Claude API -> response SMS
- [ ] Deploy to Railway
- [ ] **Test**: text the number, get a smart response

### Phase 1: Memory (Day 2-3)
- [ ] Create user data directory structure
- [ ] Implement `load_memory` / `update_memory`
- [ ] Add `update_memory` tool to LLM
- [ ] Bootstrap your `profile.md`
- [ ] **Test**: text preferences, verify they persist

### Phase 2: Resolution Ladder — Cache + Places + Web (Day 3-5)
- [ ] SQLite schema (business_facts, phone_scores)
- [ ] Google Places API integration (`search_places` tool)
- [ ] Web search integration (`search_web` tool)
- [ ] Fact cache read/write (`check_cache` tool)
- [ ] Wire resolution ladder instruction into system prompt
- [ ] **Test**: "What time does Whole Foods close?" -> answered from Places, no call

### Phase 3: Outbound Voice Calls (Day 5-8)
- [ ] Vapi account setup, import Twilio number
- [ ] `pre_call_check` tool implementation
- [ ] `call_business` tool + `initiate_outbound_call`
- [ ] Vapi webhook for call completion
- [ ] `classify_call_outcome` + `summarize_call_result`
- [ ] Call failure handling (busy, no answer, voicemail, wrong number)
- [ ] Phone score tracking
- [ ] **Test**: "Call Delfina and see if they have a table for 2 Friday at 7"

### Phase 4: Retry System (Day 8-9)
- [ ] `schedule_retry` implementation
- [ ] Retry cron job (check `retry_pending` calls every 5 min)
- [ ] IVR map storage (learn from call attempts)
- [ ] Max retry logic (2 attempts, then give up gracefully)
- [ ] **Test**: call a business that doesn't answer, verify retry + user notification

### Phase 5: Inbound Voice (Day 9-10)
- [ ] Configure Twilio voice webhook -> Vapi
- [ ] Create Vapi inbound assistant with tools
- [ ] **Test**: call the number, have a conversation, ask it to do something

### Phase 6: Proactive Intelligence (Day 10-12)
- [ ] Scheduled tasks table + followup tool
- [ ] `compute_triggers` (deterministic, no LLM)
- [ ] `compose_proactive_message` (LLM, but only when triggered)
- [ ] APScheduler cron: proactive checks at 8am, retry checks every 5 min
- [ ] **Test**: schedule a reminder, verify it fires. Wait for Friday dinner nudge.

### Phase 7: Registration & Billing (Day 12-16)
- [ ] Next.js landing page (getgoon.com)
- [ ] Stripe checkout integration
- [ ] Stripe webhook (subscription status updates)
- [ ] Allowlist management from DB
- [ ] Unregistered user handling (teaser responses)
- [ ] **Test**: full signup flow -> active -> text -> response

### Phase 8: Leads Engine (Day 16-18)
- [ ] Unregistered attempt logging + teaser responses
- [ ] Admin dashboard (who's texting, what are they asking)
- [ ] Re-engagement cron (weekly)
- [ ] **Test**: text from unknown number, verify teaser + logging

### Phase 9: Harden (Day 18-21)
- [ ] Graceful degradation (API failures, rate limits)
- [ ] Rate limiting per user (soft + hard thresholds)
- [ ] Memory compaction (prevent profile.md bloat)
- [ ] Conversation history rotation (keep 30 days active)
- [ ] Error alerting (PagerDuty / SMS to your personal number)
- [ ] Call cost tracking / budget alerts

---

## 15. Lessons Absorbed from Original TalkTo

Everything below was extracted from the legacy codebase review and plan analysis. These lessons are baked into the architecture above, documented here for context.

### What We Kept

1. **Resolution ladder** — Original: exact-match RoboQuery -> Yelp scrape -> human agent. Now: fact cache -> Google Places -> web search -> AI voice call. Same principle: exhaust cheap options first.

2. **Phone number scoring** — Original tracked `score`, `trend`, `last_success` per channel. We track `call_count`, `success_count`, `last_outcome` per phone number. Same concept, simpler schema.

3. **Ticket priority** — Original: paid (3) > new user (7) > takeout (9) > normal (11). Translates to queue priority for voice calls and proactive outreach.

4. **Rate limiting** — Original had daily/monthly caps with soft/hard thresholds. Still needed to prevent abuse.

5. **Response time transparency** — "Calling now. Back in a few." builds trust, just like original's "Fast Track, we're on it!"

6. **Discussion persistence** — Original's Discussion model (user <-> business conversation thread). We maintain this through conversation history + fact cache per business.

7. **Drip cadence** — Day 1/3/7 onboarding worked. Adapted for Goon's welcome flow.

8. **"Time saved" framing** — Original: "You just saved X minutes with TalkTo." Powerful retention messaging we should add post-launch.

### What We Killed

1. **15-source data pipeline** — SimpleGeo, Factual, Locu, Foursquare, CityGrid... all dead or irrelevant. Google Places is the canonical source now.

2. **Manual entity crosswalk** — Google Place IDs solve this.

3. **Exact-match auto-answer** — RoboQuery was `entity.roboquery_set.filter(question=query)`. LLMs understand natural language.

4. **XMPP/ejabberd presence** — No real-time business presence needed.

5. **Human agent workflow** — The entire workflow module, ticket system, agent dashboard. AI replaces all of it.

6. **Business claiming** — Irrelevant. AI calls whether business opted in or not.

7. **Credit-per-question billing** — Overcomplicated. Simple subscription.

8. **App distribution** — No app. SMS is the interface.

### Edge Cases We Internalized

From 3+ years of human agents calling businesses:

- **IVR is the #1 failure mode** — Vapi prompt includes IVR navigation instructions + we store IVR maps per business
- **Wrong numbers are #2** — Phone scoring system deprioritizes after 2+ failures
- **"On behalf of" triggers telemarketer defenses** — Vapi prompt sounds like a regular caller
- **Chain vs local numbers** — Pre-call check flags chains, prefers local numbers
- **Business closed when calling** — Pre-call check uses `open_now` from Google Places
- **Voicemail is useless** — Agent hangs up on voicemail, retries later
- **Employees need clarification** — Vapi prompt includes rephrase instructions
- **Seasonal hours change everything** — Short expiry on cached hours (7 days)

---

## File Structure

```
goon/
├── pyproject.toml
├── .env
├── app/
│   ├── main.py                    # FastAPI entry point
│   ├── config.py                  # Settings from env
│   ├── routes/
│   │   ├── sms.py                 # Twilio SMS webhook
│   │   ├── voice.py               # Twilio voice -> Vapi routing
│   │   ├── vapi_events.py         # Vapi call event webhook
│   │   ├── stripe.py              # Stripe webhook
│   │   └── admin.py               # Admin dashboard
│   ├── services/
│   │   ├── orchestrator.py        # LLM orchestration + tool loop
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
│       ├── database.py            # SQLite async wrapper
│       └── migrations/            # Schema changes
├── web/                            # Next.js registration site
│   ├── pages/
│   │   ├── index.tsx              # Landing page (getgoon.com)
│   │   ├── signup.tsx             # Registration + Stripe
│   │   ├── billing.tsx            # Subscription management
│   │   └── memory.tsx             # View/edit your memory (optional)
│   └── ...
├── data/                           # User data (gitignored)
│   ├── goon.db                    # SQLite database
│   └── users/
│       └── +14155551234/
│           ├── profile.md
│           ├── conversations.jsonl
│           ├── calls.jsonl
│           └── tasks.json
├── scripts/
│   ├── seed_user.py               # Manually add a test user
│   ├── run_proactive.py           # Manual proactive check
│   └── review_leads.py            # CLI for viewing leads
└── tests/
    ├── test_resolution_ladder.py  # Unit tests for routing logic
    ├── test_sms_segments.py       # SMS encoding/splitting tests
    └── test_call_outcomes.py      # Call failure classification tests
```

---

*Goon: your AI that does the thing so you don't have to.*
*Built on the bones of TalkTo (2010-2014) — same thesis, no humans required.*