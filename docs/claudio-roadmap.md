# Claudio — Product Roadmap

## Phase 0: Stabilization (This Week)
*Get the current build to "works reliably" status.*

### P0-1: Fix Test Suite
- Fix all Python 3.9 type syntax issues (use `from __future__ import annotations`)
- Fix test fixture issues on main
- Get CI green

### P0-2: Voice Quality & Naturalness
- Add natural pause after "Hello" before speaking (silence buffer in first message)
- Remove robotic confirmation behavior — when host confirms, just say thanks and hang up
- Fix end-of-call voice change (Vapi's canned goodbye vs TTS goodbye)
- Tune system prompt for natural conversation flow: don't over-confirm, don't repeat info back
- Test and iterate on system prompt using controlled calls to your own phone

### P0-3: AI Disclosure & Recording
- Add disclosure to the call opening: "This call may be recorded for quality purposes" (or state-specific two-party consent language)
- Research state-by-state recording consent laws (California = two-party consent)
- Add recording toggle per call in Vapi payload

### P0-4: Call Reliability Fixes
- Duplicate call prevention (don't call same business if call already in_progress)
- Test business routing: check before search_places, not inside it
- Vapi webhook follow-up: ensure call_log status updates reliably to 'success'
- Add logging around full callback flow

### P0-5: System Prompt Worldview v1
- Build a "soul document" for the voice agent — personality, values, boundaries
- Borrow from OpenClaw's model: agent treats the customer as a guest in their life
- Never shares private info, never abuses the system
- Test prompt iterations by having it call you through different scenarios

---

## Phase 1: Dental Appointment MVP (Weeks 2-3)
*First real vertical use case: booking a dental appointment.*

### P1-1: Customer Profile System
- Per-customer profile (profile.md or structured JSON) that builds over time
- Collect preferences conversationally: scheduling availability, insurance info, preferred providers
- Profile fields: name, phone, preferred times, insurance provider, allergies/medical notes
- Customer can view/edit their profile (future: via SMS commands or web dashboard)

### P1-2: Business Category Intelligence
- Business type templates: restaurant, dentist, salon, doctor, etc.
- Each category knows what info is needed for a successful call (e.g., dentist needs: patient name, DOB, insurance, reason for visit, preferred times)
- Pre-flight check: if we don't have required info, text the customer to collect it BEFORE calling
- Store learned info per-business AND per-category in the fact cache

### P1-3: Mid-Call Customer Consultation
- If the AI agent needs info during a call (e.g., "which dates work for you?"), it can:
  1. Ask the business to hold
  2. Text the customer with the options
  3. Wait for the customer's reply
  4. Resume the call with the answer
- This is the killer feature — async human-in-the-loop during live calls

### P1-4: IVR Learning System
- Record and learn phone tree structures per business
- Store IVR maps in fact cache (which button goes where)
- On repeat calls, navigate the IVR automatically using stored maps
- Track which businesses answer, which are IVR-only, which are hostile

### P1-5: Phone Score & Business Verification
- Score phone numbers: does this number answer? How long to reach a human?
- Business verification pre-call: is this a real business? Is the number legit?
- Prevent prank calls: validate that the target is a real business (Google Places verification)
- Block calling non-business numbers entirely

---

## Phase 2: Safety, Guards & Intelligence (Weeks 3-4)
*Make it production-safe and smart.*

### P2-1: Input Guardrails
- Content filter on incoming messages: block harassment, illegal requests, pranks
- The assistant has personality: "Hey, that's not something I can help with. Try a different approach."
- Rate limiting per user: max calls per day, max messages per hour
- Blocklist for numbers that abuse the system

### P2-2: Gated Rollout Controls
- Allowlist mode: only registered/invited users can use the full pipeline
- Unknown numbers get a simple static response (no LLM, no cost): "Claudio is in private beta. Visit claudio.com to request access."
- Admin controls to add/remove users from allowlist
- Dashboard showing active users, message volume, cost per user

### P2-3: Business Call Intelligence
- Track call outcomes per business over time
- Learn: which businesses answer, what hours they answer, average hold time
- Build IVR maps automatically from call transcripts
- Flag businesses that are hostile or unreachable
- Per-business call frequency limits (don't call same place 100 times)

### P2-4: Retry System Improvements
- Smart retry with backoff (already built — tune it)
- Different strategies per failure type: busy → retry in 5min, voicemail → retry in 30min, hostile → don't retry
- Scheduling via Temporal or similar: "call back at 9am tomorrow when they open"

### P2-5: Follow-ups & Reminders
- "Your reservation at Flour+Water is in 2 hours"
- "Your dental appointment is tomorrow at 10am — need to reschedule?"
- Proactive nudges based on stored context
- Temporal/cron-based scheduling for future actions

---

## Phase 3: Conversation Model & Memory (Weeks 4-5)
*Multi-thread conversations and persistent learning.*

### P3-1: Conversation Threading
- One customer can have multiple active "threads" (e.g., restaurant search + dentist booking)
- Each inbound message is routed to the right thread based on context
- Customer can manage threads: "what's the status of my dentist appointment?"
- Anticipate future group messaging (multiple participants per thread)

### P3-2: Memory System (OpenClaw-inspired)
- Agent builds and maintains a memory file per customer
- Memory updates after every interaction (preferences, past requests, outcomes)
- Agent learns about itself: what works, what doesn't, common patterns
- Memory is the customer's — private, never shared, they control what's stored
- Structured as: profile (static facts) + journal (interaction log) + learnings (patterns)

### P3-3: Call Transcript Review System
- Store all transcripts (already doing this)
- Dashboard to review conversations
- Flag calls that went poorly for human review
- Use reviews to improve system prompt and IVR maps
- Meta-learning: what makes a successful call vs a failed one?

---

## Phase 4: Business Setup & Viral Growth (Weeks 5-8)
*Turn it into a real business.*

### P4-1: Business Infrastructure
- Register LLC
- Get a business domain (claudio.ai, getclaudio.com, etc.)
- Set up business email (not personal Gmail)
- Business bank account + credit card for expenses
- Move all service accounts (Twilio, Vapi, Stripe, Anthropic) to business accounts
- Separate expense tracking from personal

### P4-2: Subscription & Unit Economics
- Finalize pricing model (already have Stripe set up with $19.99/month)
- Build unit economics dashboard: cost per call, cost per user, revenue per user
- Track: Twilio SMS costs, Vapi minutes, Anthropic API tokens, Google Places calls
- Model break-even point and margins
- Consider tiered pricing: basic (X calls/month) vs pro (unlimited)

### P4-3: Viral Loop & Referral System
- Research best controlled-rollout viral loops (Dropbox model, etc.)
- Referral incentive: "Invite a friend, both get a free month"
- Gated rollout: each user gets N invite codes
- Waitlist with priority based on referrals
- Track viral coefficient (K-factor)
- MIT Red Balloon style: reward chains, not just direct referrals
  - Person who invites gets credit
  - Person who invited THEM gets smaller credit
  - Creates incentive to recruit good recruiters

### P4-4: Registration Site & Onboarding
- Landing page explaining the product
- Waitlist signup with referral tracking
- Stripe checkout for paid users
- Onboarding flow: register phone, set preferences, first test message

---

## Phase 5: Future Features (Weeks 8+)
*Ideas to revisit later — not now.*

### P5-1: IVR Passthrough Mode
- Navigate the phone tree automatically, then patch the human customer through
- "I got through to a human at the dentist's office — connecting you now"
- Three-way call or warm transfer

### P5-2: Compute-on-Behalf
- Agent can spin up compute (like OpenClaw) on the customer's behalf
- Customer authorizes spending, agent estimates cost, executes
- Use cases: research, price comparison, booking optimization

### P5-3: Lower Latency Models
- Test smaller/faster models for voice (Haiku for voice, Sonnet for orchestration)
- Measure latency vs quality tradeoff
- Consider local models for pre-processing

### P5-4: Secure Data Handling
- End-to-end encryption for sensitive data (insurance info, medical records)
- Data only decrypted on the Vapi side, not stored in LLM context
- SOC2 / HIPAA considerations for healthcare vertical

### P5-5: Multi-Business Dashboard
- Business-facing product: businesses opt-in to receive AI calls
- Preferred business directory (faster, cheaper calls)
- Business analytics: how many AI calls they receive, outcomes

---

## Legal Considerations

### TalkTo History
- Research any non-compete, IP assignment, or lingering obligations from TalkTo
- TalkTo was acquired and shut down ~16 years ago — most obligations likely expired
- Get a quick legal review to confirm clean slate
- Key questions: do you own any residual IP? Are there any non-compete clauses still active?

### Side Project at Block
- Review Block's employee handbook / IP policy re: side projects
- Most tech companies require disclosure of side projects
- Key question: does Block claim ownership of employee side projects?
- Typical safe harbor: project is unrelated to employer's business, built on personal time, using personal equipment
- Consider disclosing to your manager or legal team proactively
- Cash App ≠ AI concierge, but both touch payments (Stripe) — get clarity

### Involving Your Wife
- If she's managing the business: add her to the LLC as a member/partner
- Consider: who owns what, decision-making authority, tax implications
- Simple operating agreement covers this

### Regulatory
- TCPA compliance for SMS (already need A2P 10DLC registration)
- Two-party consent states for call recording
- FTC guidelines on AI disclosure in calls
- Terms of service + privacy policy for the product

---

## For the Mayor

Tell the Mayor:

1. Fix P0-1 through P0-4 immediately (test suite, voice quality, disclosure, reliability)
2. Then P1-1 and P1-2 (customer profiles + business category intelligence)  
3. File new beads for each numbered item in Phase 0 and Phase 1
4. Everything Phase 2+ is future — don't build it yet, just be aware of the direction

The guiding principle: make the dental appointment use case work perfectly end-to-end, 
then expand from there.
