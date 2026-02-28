# Goon — Integration Test Harness

## Addendum to Product Document

> Test the full SMS → agent → voice call → response circuit without calling real businesses.

---

## The Problem

You can't validate the end-to-end experience by calling Pizzeria Delfina 50 times while debugging. You need a controlled loop where:

1. You text Goon from your phone
2. Goon decides it needs to call a business
3. The "business" is your other phone (or a test number you control)
4. You answer as the business, have a conversation with the AI voice agent
5. Goon texts you back with the result

This means you're playing two roles simultaneously: **the customer** (texting Goon) and **the business employee** (answering Goon's call). Same person, two phone numbers.

---

## Test Business Registry

A simple config file that defines fake businesses Goon knows about. These bypass Google Places entirely — the orchestrator checks this registry first.

```python
# app/config/test_businesses.py

TEST_BUSINESSES = {
    "riley's pizza": {
        "name": "Riley's Pizza",
        "phone": "+14155559999",         # YOUR second phone number
        "place_id": "test_rileys_pizza",
        "address": "123 Test St, Palo Alto, CA",
        "category": "restaurant",
        "hours": "11am-10pm daily",
        "open_now": True,                 # always open for testing
        "attributes": {
            "reservable": True,
            "takeout": True,
            "delivery": False,
            "dine_in": True
        },
        "cached_facts": {
            "hours": "11am-10pm, 7 days a week",
            "menu": "Margherita $14, Pepperoni $16, Sicilian $18, Calzone $15"
        }
    },
    "test barbershop": {
        "name": "Test Barbershop",
        "phone": "+14155559999",         # same number — you answer as different businesses
        "place_id": "test_barbershop",
        "address": "456 Test Ave, Palo Alto, CA",
        "category": "barber",
        "hours": "9am-6pm Tue-Sat",
        "open_now": True,
        "attributes": {
            "reservable": True
        },
        "cached_facts": {
            "hours": "Tuesday through Saturday, 9am to 6pm"
        }
    }
}

# Set this in .env — when True, test businesses are checked before Google Places
ENABLE_TEST_BUSINESSES = True
```

### How It Plugs Into the Resolution Ladder

The test registry inserts at Step 0 — before the fact cache:

```
STEP 0 (test mode only): Check test business registry
  → Match on business name (fuzzy)
  → If matched:
    → For cached_facts: return immediately (tests cache path)
    → For everything else: use the test business phone number
      (tests the full call path)
  → If not matched: proceed to normal resolution ladder
```

In the orchestrator, this is a simple check:

```python
# In the search_places tool handler:
if ENABLE_TEST_BUSINESSES:
    test_biz = match_test_business(query)
    if test_biz:
        return format_test_business_as_places_result(test_biz)

# In the pre_call_check:
if ENABLE_TEST_BUSINESSES and place_id.startswith("test_"):
    return {"ok": True, "issues": []}  # skip open_now and phone score checks
```

---

## Test Scenarios (The Validation Circuit)

### Scenario 1: Text → Cached Answer (no call)

**Tests**: SMS gateway, orchestrator, fact cache, memory

```
You (from your phone):
  "What time does Riley's Pizza close?"

Expected Goon response:
  "Riley's Pizza is open 11am-10pm, 7 days a week."

What happens:
  1. SMS arrives at webhook
  2. Orchestrator loads your memory
  3. check_cache("riley's pizza", "hours") → hits test business cached_facts
  4. Returns answer, no call needed
  5. SMS sent back

Validates:
  ✓ Twilio webhook receives and responds
  ✓ User auth works
  ✓ Orchestrator runs resolution ladder
  ✓ Cache lookup works
  ✓ SMS response sends
```

### Scenario 2: Text → Google Places Answer (no call)

**Tests**: SMS gateway, orchestrator, Google Places integration

```
You:
  "What time does Whole Foods on Middlefield close?"

Expected:
  Real answer from Google Places API (e.g. "Whole Foods on
  Middlefield closes at 10pm tonight.")

What happens:
  1. Not in test registry → normal resolution ladder
  2. check_cache → miss
  3. search_places("Whole Foods Middlefield Palo Alto") → hit
  4. Returns hours from Google Places
  5. Stores in fact cache for next time

Validates:
  ✓ Google Places API integration
  ✓ Fact caching on successful lookup
  ✓ Falls through cache miss correctly
```

### Scenario 3: Text → Voice Call → Result (THE FULL CIRCUIT)

**Tests**: Everything. This is the critical test.

**Setup**: Have a second phone nearby (or use your phone — Goon texts you on one number and calls you on another).

```
You (texting from your main phone):
  "Can you book me a table at Riley's Pizza for 2 tonight at 7?"

Goon:
  "Calling Riley's Pizza now. Back in a few."

[Your second phone rings — it's the Goon number]
[You answer, pretending to be Riley's Pizza]

Vapi voice agent:
  "Hi, I'd like to make a reservation for two tonight
   around 7. Do you have anything available?"

You (as the restaurant):
  "Let me check... yes, we have a table at 7:15. Name?"

Vapi:
  "Riley."

You:
  "Got it. Riley, party of 2, tonight at 7:15."

Vapi:
  "Just to confirm — 7:15, two people, under Riley. Perfect,
   thanks so much!"

[Call ends]

[Your main phone buzzes — SMS from Goon]

Goon:
  "Riley's Pizza confirmed: tonight 7:15, 2 people, under Riley."

Validates:
  ✓ Orchestrator correctly decides to call (reservation requires a call)
  ✓ Pre-call check passes (test business always open)
  ✓ Vapi outbound call initiates
  ✓ Voice agent delivers correct first message
  ✓ Voice agent handles natural conversation
  ✓ Call completion webhook fires
  ✓ Transcript summarization works
  ✓ Result SMS sent to user
  ✓ Memory updated with reservation details
  ✓ Fact cached (reservation policy for Riley's Pizza)
```

### Scenario 4: Text → Call Fails → Retry

**Tests**: Failure handling, retry system

**Setup**: Don't answer your second phone when Goon calls.

```
You:
  "Is Riley's Pizza doing any specials tonight?"

Goon:
  "I don't see specials online. Calling Riley's Pizza to ask."

[Your second phone rings — don't answer]

[After ~30 seconds]

Goon:
  "No answer at Riley's Pizza. I'll try again in 10 min."

[10 minutes later, your second phone rings again]
[This time, answer it]

Vapi:
  "Hi, quick question — do you have any specials tonight?"

You:
  "Yeah, half-price Margheritas on Tuesdays."

Vapi:
  "Half-price Margheritas on Tuesdays, great. Thanks!"

Goon:
  "Riley's Pizza: half-price Margheritas on Tuesdays."

Validates:
  ✓ No-answer detection
  ✓ User notification of failure
  ✓ Retry scheduling (10 min delay)
  ✓ Retry cron picks up pending retry
  ✓ Second attempt succeeds
  ✓ Result delivered after retry
```

### Scenario 5: Voice Inbound → Conversation → Call-Out

**Tests**: Voice inbound (user calls Goon), tool use in voice, outbound call from voice session

```
You (call the Goon number from your main phone):

Goon (voice):
  "Hey Riley, what can I do for you?"

You:
  "Can you check if Riley's Pizza can do a party of 6 on Saturday?"

Goon:
  "Let me call them and find out. I'll text you when I have an answer."

[Goon hangs up your call, then calls your second phone]

[You answer as the restaurant, handle the conversation]

[Your main phone gets a text]

Goon:
  "Riley's Pizza can do 6 on Saturday. They said 6:30 or 8pm.
   Which one?"

Validates:
  ✓ Vapi inbound assistant works
  ✓ User memory loaded into voice session
  ✓ Voice agent triggers outbound call
  ✓ Handoff from voice → async SMS result
```

### Scenario 6: Memory Persistence

**Tests**: Memory system across sessions

```
Session 1:
  You: "I'm allergic to shellfish, remember that"
  Goon: "Got it — shellfish allergy noted."

Session 2 (hours later):
  You: "What should I order at Riley's Pizza?"
  Goon: "Their Margherita and Calzone are good bets.
         Skipping anything with shellfish since you're allergic."

Validates:
  ✓ update_memory tool fires
  ✓ profile.md updated with allergy
  ✓ Memory persists across sessions
  ✓ Memory influences future responses
```

### Scenario 7: Proactive Nudge

**Tests**: Proactive intelligence trigger system

**Setup**: Seed your profile.md with a pattern and a scheduled task.

```
# In profile.md:
## Patterns
- Dinner reservations: usually asks Friday morning for that evening

# In scheduled_tasks:
{"message": "Your haircut is overdue", "trigger": "6-week cycle",
 "due_at": "<today>", "status": "pending"}

[Goon's 8am cron runs]

You receive:
  "Hey Riley — haircut's overdue. Want me to call the barbershop?"

Validates:
  ✓ Proactive cron fires
  ✓ Scheduled task trigger detected
  ✓ LLM composes appropriate message
  ✓ SMS sent without user initiating
```

---

## Phone Number Setup for Testing

You need **2 phone numbers** you can use simultaneously:

| Number | Role | How |
|---|---|---|
| **Your main phone** | The customer. Texts and calls Goon. | Your real phone number. |
| **Your test business phone** | Answers calls from Goon as "the restaurant" etc. | Options below. |

### Options for the second number

**Easiest: Google Voice** (free)
- Go to voice.google.com, get a free number
- Rings on your phone via the Google Voice app
- Set this as the phone number in `TEST_BUSINESSES`
- You'll see Goon's call come in on Google Voice, answer it as "the business"

**Also easy: iPad / old phone**
- If you have an iPad or old iPhone, put a spare SIM or eSIM in it
- Or use WhatsApp with a Google Voice number on the iPad
- Physical separation helps — you're playing two roles

**For automated testing: Twilio test number**
- Buy a second Twilio number
- Write a simple TwiML app that answers and plays along
- Or use Twilio's `<Record>` to capture what the voice agent says

---

## Test Mode Configuration

```bash
# .env additions for test mode
ENABLE_TEST_BUSINESSES=true
TEST_BUSINESS_PHONE=+14155559999    # your Google Voice / second number
TEST_MODE_LOG_VERBOSE=true           # log full LLM prompts and tool calls
```

### Test mode behaviors

When `ENABLE_TEST_BUSINESSES=true`:
- Test businesses are checked before Google Places in the resolution ladder
- Pre-call checks are relaxed for test businesses (skip open_now, skip phone score)
- Verbose logging shows the full decision chain (which step of the ladder was used, which tools were called, what the LLM decided)
- Call recordings are saved locally (not just in Vapi)

When `ENABLE_TEST_BUSINESSES=false`:
- Normal production behavior
- Test businesses are invisible

---

## Build Order (Updated — Test Harness First)

The original build order started with "SMS Echo." This revision puts the test harness into Phase 0 so you have a validation circuit from day 1.

```
Phase 0: SMS Echo + Test Harness (Day 1)
  ├── Buy Twilio number
  ├── Set up Google Voice for test business number
  ├── FastAPI server with SMS webhook
  ├── Hardcode your phone as allowed sender
  ├── Create test_businesses.py config
  ├── Pipe SMS → Claude → response (basic, no tools yet)
  ├── Deploy to Railway
  └── TEST: text the number, get a response

Phase 1: Memory (Day 2-3)
  ├── Memory system (profile.md + conversations.jsonl)
  ├── update_memory tool
  ├── Bootstrap your profile.md
  └── TEST Scenario 6: memory persistence across sessions

Phase 2: Resolution Ladder (Day 3-5)
  ├── Fact cache (SQLite + CRUD)
  ├── Google Places integration
  ├── Web search integration
  ├── Wire test business cached_facts into resolution ladder
  ├── TEST Scenario 1: cached answer from test business
  └── TEST Scenario 2: Google Places answer from real business

Phase 3: Voice Outbound (Day 5-8)
  ├── Vapi setup, import Twilio number
  ├── pre_call_check + call_business tools
  ├── Vapi webhook for call completion
  ├── Call outcome classification
  ├── TEST Scenario 3: FULL CIRCUIT — text → call your test phone → result
  └── TEST Scenario 4: don't answer → retry → answer → result

Phase 4: Voice Inbound (Day 8-9)
  ├── Twilio voice → Vapi routing
  ├── Vapi inbound assistant with tools
  └── TEST Scenario 5: call Goon → it calls test business → texts result

Phase 5: Proactive (Day 9-11)
  ├── Scheduled tasks + triggers
  ├── Proactive cron
  ├── Seed profile with test pattern + task
  └── TEST Scenario 7: proactive nudge fires

Phase 6+: Billing, leads, polish (Day 11+)
  └── (unchanged from main product doc)
```

---

## The "Riley's Pizza" Integration Test Script

A single script that runs all scenarios in sequence, with human prompts for the voice call parts:

```python
# scripts/integration_test.py
"""
Goon Integration Test — run from your laptop while holding two phones.

Prerequisites:
  - Goon server running and deployed
  - GOON_NUMBER set in .env
  - TEST_BUSINESS_PHONE set to your Google Voice number
  - Your main phone ready to text
  - Your test phone (Google Voice) ready to receive calls

This script guides you through each scenario step by step.
"""

import time

def main():
    print("=" * 60)
    print("GOON INTEGRATION TEST")
    print("=" * 60)
    print()
    print(f"Goon number: {GOON_NUMBER}")
    print(f"Test business phone: {TEST_BUSINESS_PHONE}")
    print(f"Your phone: {YOUR_PHONE}")
    print()

    # Scenario 1: Cached answer
    print("--- SCENARIO 1: Cached Answer ---")
    print("From your phone, text Goon:")
    print('  "What time does Riley\'s Pizza close?"')
    print()
    input("Press Enter after you've sent the text and received a response...")
    print("Expected: An answer about hours (11am-10pm) with NO call.")
    result = input("Did it work? (y/n): ")
    log_result("scenario_1_cached_answer", result)
    print()

    # Scenario 2: Google Places
    print("--- SCENARIO 2: Google Places ---")
    print("From your phone, text Goon:")
    print('  "What time does Whole Foods on Middlefield close?"')
    print()
    input("Press Enter after response...")
    result = input("Did you get real hours from Google Places? (y/n): ")
    log_result("scenario_2_google_places", result)
    print()

    # Scenario 3: Full circuit
    print("--- SCENARIO 3: FULL CIRCUIT (the big one) ---")
    print("From your phone, text Goon:")
    print('  "Book me a table at Riley\'s Pizza for 2 tonight at 7"')
    print()
    print("Goon should text back that it's calling.")
    print("Your TEST PHONE (Google Voice) should ring.")
    print("ANSWER IT. Pretend you're the restaurant.")
    print("  - The AI will ask for a reservation")
    print("  - Confirm a time, ask for the name, confirm the booking")
    print()
    input("Press Enter after the call ends and you get a result text...")
    result = input("Did the full circuit work? (y/n): ")
    log_result("scenario_3_full_circuit", result)
    print()

    # Scenario 4: Retry
    print("--- SCENARIO 4: Call Failure + Retry ---")
    print("From your phone, text Goon:")
    print('  "Does Riley\'s Pizza have any specials tonight?"')
    print()
    print("When your test phone rings, DO NOT ANSWER.")
    print("Wait for Goon to text you about the failure.")
    print("Then wait for the retry (should be ~10 min).")
    print("When it rings again, ANSWER and give a specials list.")
    print()
    input("Press Enter after retry succeeds and you get the result...")
    result = input("Did retry work? (y/n): ")
    log_result("scenario_4_retry", result)
    print()

    # Scenario 5: Voice inbound
    print("--- SCENARIO 5: Voice Inbound ---")
    print("CALL the Goon number from your main phone.")
    print("Ask: 'Can Riley's Pizza do a party of 6 Saturday?'")
    print("Goon should say it'll call and text you the result.")
    print("Answer your test phone when it rings.")
    print()
    input("Press Enter after you get the result text...")
    result = input("Did voice inbound → outbound → SMS result work? (y/n): ")
    log_result("scenario_5_voice_inbound", result)
    print()

    # Scenario 6: Memory
    print("--- SCENARIO 6: Memory ---")
    print("Text Goon: 'Remember I'm allergic to shellfish'")
    input("Press Enter after confirmation...")
    print("Now text: 'What should I get at Riley\\'s Pizza?'")
    input("Press Enter after response...")
    result = input("Did it mention avoiding shellfish? (y/n): ")
    log_result("scenario_6_memory", result)
    print()

    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {status}: {name}")

results = {}
def log_result(name, result):
    results[name] = result.lower() == 'y'

if __name__ == "__main__":
    main()
```

---

## Summary

The test harness gives you:

1. **A fake business registry** that bypasses Google Places so you control the whole circuit
2. **Your Google Voice number** as "the business" — you answer and play the role
3. **7 test scenarios** that validate every component and integration point
4. **A guided test script** that walks you through each scenario with your phones in hand
5. **Verbose test-mode logging** so you can see exactly what the orchestrator decided and why

The most important test is **Scenario 3** — the full circuit where you text a reservation request, Goon calls your test phone, you have a real conversation with the AI voice agent, and the result comes back as a text. When that works, you know the core product works.