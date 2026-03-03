import React, { useState } from "react";

type Step = { from: number; to: number; label: string };
type Flow = { title: string; example: string; steps: Step[] };
type Actor = { id: number; label: string; sub: string; color: string; icon: string };

// ── Actors ──────────────────────────────────────────────────────────────
// Every box that can appear on a lifeline. Flows reference these by id.
const actors: Actor[] = [
  { id: 0,  label: "You",           sub: "(Phone)",        color: "#3b82f6", icon: "\uD83D\uDCF1" },
  { id: 1,  label: "Twilio",        sub: "(SMS/Voice)",    color: "#ef4444", icon: "\uD83D\uDCE1" },
  { id: 2,  label: "Orchestrator",  sub: "(The Brain)",    color: "#8b5cf6", icon: "\uD83E\uDDE0" },
  { id: 3,  label: "Fact Cache",    sub: "(SQLite)",       color: "#f59e0b", icon: "\uD83D\uDCBE" },
  { id: 4,  label: "Places",        sub: "(Google)",       color: "#10b981", icon: "\uD83D\uDCCD" },
  { id: 5,  label: "Google API",    sub: "",               color: "#6b7280", icon: "\u2601\uFE0F" },
  { id: 6,  label: "Claude LLM",    sub: "(Sonnet 4.5)",   color: "#ec4899", icon: "\uD83E\uDD16" },
  { id: 7,  label: "Calls",         sub: "(calls.py)",     color: "#f97316", icon: "\uD83D\uDCDE" },
  { id: 8,  label: "Vapi",          sub: "(Voice AI)",     color: "#14b8a6", icon: "\uD83D\uDDE3\uFE0F" },
  { id: 9,  label: "Business",      sub: "(Phone)",        color: "#78716c", icon: "\uD83C\uDF7D\uFE0F" },
  { id: 10, label: "Auth",          sub: "(auth.py)",      color: "#64748b", icon: "\uD83D\uDD10" },
  { id: 11, label: "Leads",         sub: "(leads.py)",     color: "#a855f7", icon: "\uD83D\uDCCA" },
  // ── v1 additions ───
  { id: 12, label: "Memory",        sub: "(USER/MEMORY.md)", color: "#06b6d4", icon: "\uD83D\uDCDD" },
  { id: 13, label: "Billing",       sub: "(Stripe)",       color: "#84cc16", icon: "\uD83D\uDCB3" },
  { id: 14, label: "Scheduler",     sub: "(scheduler.py)", color: "#d946ef", icon: "\u23F0" },
  { id: 15, label: "Biz Intel",     sub: "(intelligence)", color: "#f43f5e", icon: "\uD83C\uDF10" },
  { id: 16, label: "Failure Log",   sub: "(failures.py)",  color: "#dc2626", icon: "\u26A0\uFE0F" },
  { id: 17, label: "Web Search",    sub: "(Tavily)",       color: "#2563eb", icon: "\uD83D\uDD0D" },
  { id: 18, label: "Proactive",     sub: "(proactive.py)", color: "#7c3aed", icon: "\uD83D\uDCE8" },
  { id: 19, label: "Admin",         sub: "(dashboard)",    color: "#ea580c", icon: "\uD83D\uDDA5\uFE0F" },
];

// ── Flow categories for the tab groups ──────────────────────────────────
const flowCategories: Record<string, string[]> = {
  "Core Flows": ["sms_simple", "sms_call_full", "voice_inbound"],
  "Billing & Access": ["free_tier_paywall", "upgrade_flow"],
  "Intelligence": ["memory_loop", "biz_intel_loop"],
  "Reliability": ["call_failure_retry", "closed_biz_schedule", "proactive_outreach"],
  "Admin": ["admin_inspect"],
  "Legacy": ["unregistered"],
};

// ── Flows ───────────────────────────────────────────────────────────────
const flows: Record<string, Flow> = {

  // ╔══════════════════════════════════════════════════════════════════════
  // ║  CORE FLOWS
  // ╚══════════════════════════════════════════════════════════════════════

  sms_simple: {
    title: "Simple Question (No Call)",
    example: '"What are the hours for Blue Bottle Coffee?"',
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'What are the hours...'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook" },
      { from: 2,  to: 10, label: "get_user() + get_user_tier()" },
      { from: 10, to: 2,  label: "tier: active" },
      { from: 2,  to: 12, label: "load_memory(USER.md, MEMORY.md, convos)" },
      { from: 12, to: 2,  label: "profile + recent history" },
      { from: 2,  to: 15, label: "_build_business_context()" },
      { from: 15, to: 2,  label: "(no prior intel for this biz)" },
      { from: 2,  to: 6,  label: "build_system_prompt + Claude tool loop" },
      { from: 6,  to: 3,  label: "check_cache('Blue Bottle', 'hours')" },
      { from: 3,  to: 6,  label: "MISS (not cached)" },
      { from: 6,  to: 4,  label: "search_places('Blue Bottle Coffee')" },
      { from: 4,  to: 5,  label: "Places API v2 Text Search" },
      { from: 5,  to: 4,  label: "hours, address, phone, rating, lat/lng" },
      { from: 4,  to: 6,  label: "PlaceResult{hours: '6am-7pm'}" },
      { from: 6,  to: 3,  label: "store_fact(hours, 7d expiry, 0.8 conf)" },
      { from: 3,  to: 15, label: "ensure_business_profile + incr queries" },
      { from: 6,  to: 2,  label: "Claude: 'Blue Bottle is open 6am-7pm'" },
      { from: 2,  to: 1,  label: "send_sms(strip_emoji, segment-aware)" },
      { from: 1,  to: 0,  label: "SMS: 'Blue Bottle is open 6am-7pm today'" },
      { from: 2,  to: 12, label: "update_memory(convo + daily log)" },
    ],
  },

  sms_call_full: {
    title: "Call + Intelligence + Memory",
    example: '"Make a reservation for 2 at Flour+Water tonight at 7pm"',
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'Make a reservation...'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook" },
      { from: 2,  to: 10, label: "get_user() + tier check" },
      { from: 10, to: 2,  label: "tier: active (paid)" },
      { from: 2,  to: 12, label: "load_memory()" },
      { from: 12, to: 2,  label: "profile: 'prefers outdoor seating'" },
      { from: 2,  to: 15, label: "_build_business_context()" },
      { from: 15, to: 2,  label: "'Known: Maria (host), avg hold ~45s'" },
      { from: 2,  to: 6,  label: "build_system_prompt (soul+ladder+memory+biz)" },
      { from: 6,  to: 3,  label: "check_cache('Flour+Water', 'reservation')" },
      { from: 3,  to: 6,  label: "MISS" },
      { from: 6,  to: 4,  label: "search_places('Flour+Water SF')" },
      { from: 4,  to: 5,  label: "Places API lookup" },
      { from: 5,  to: 4,  label: "phone, open_now: true, place_id" },
      { from: 4,  to: 6,  label: "PlaceResult with phone number" },
      { from: 6,  to: 7,  label: "pre_call_check(phone, place_id)" },
      { from: 7,  to: 3,  label: "get_phone_score() — 3 calls, 2 success" },
      { from: 3,  to: 7,  label: "score OK, open now, not a chain" },
      { from: 7,  to: 6,  label: "Pre-call passed. OK to call." },
      { from: 6,  to: 7,  label: "call_business(task, details)" },
      { from: 7,  to: 7,  label: "check_duplicate_call → none" },
      { from: 7,  to: 8,  label: "POST Vapi /call (voice prompt + IVR map)" },
      { from: 2,  to: 1,  label: "SMS: 'Calling Flour+Water now.'" },
      { from: 1,  to: 0,  label: "SMS: interim status" },
      { from: 8,  to: 9,  label: "Vapi dials restaurant" },
      { from: 9,  to: 8,  label: "Restaurant answers" },
      { from: 8,  to: 9,  label: "'Hi, table for 2 at 7pm tonight'" },
      { from: 9,  to: 8,  label: "'7:30 works. Name?' 'Riley' 'Done!'" },
      { from: 8,  to: 2,  label: "POST /vapi/events (end-of-call-report)" },
      { from: 2,  to: 2,  label: "classify_call_outcome: SUCCESS" },
      { from: 2,  to: 3,  label: "update_phone_score(success)" },
      { from: 2,  to: 6,  label: "summarize_call_result(transcript)" },
      { from: 6,  to: 2,  label: "'Table for 2 at 7:30 under Riley'" },
      { from: 2,  to: 3,  label: "store_fact(reservation_policy, 30d)" },
      { from: 2,  to: 15, label: "ensure_business_profile + incr calls" },
      { from: 2,  to: 15, label: "extract_call_intelligence (background)" },
      { from: 15, to: 15, label: "LLM: contacts, hold_time, IVR, patterns" },
      { from: 15, to: 3,  label: "upsert business_profiles + ivr_maps" },
      { from: 2,  to: 12, label: "append_conversation (call result)" },
      { from: 2,  to: 12, label: "update_memory(convo + profile updates)" },
      { from: 2,  to: 1,  label: "send_sms(result)" },
      { from: 1,  to: 0,  label: "SMS: 'Reserved! 7:30, table for 2, Riley'" },
    ],
  },

  voice_inbound: {
    title: "Voice Inbound (User Calls)",
    example: "You call the Hold Plz number instead of texting",
    steps: [
      { from: 0,  to: 1,  label: "Calls Hold Plz number" },
      { from: 1,  to: 2,  label: "POST /voice/webhook" },
      { from: 2,  to: 10, label: "get_user(caller) + is_user_active()" },
      { from: 10, to: 2,  label: "authorized: true" },
      { from: 2,  to: 8,  label: "POST Vapi /call (provider bypass + TwiML)" },
      { from: 8,  to: 2,  label: "POST /vapi/events (assistant-request)" },
      { from: 2,  to: 12, label: "load_memory(caller)" },
      { from: 12, to: 2,  label: "profile + preferences" },
      { from: 2,  to: 8,  label: "Return assistant config w/ memory in prompt" },
      { from: 8,  to: 0,  label: "'Hey Riley, what can I help with?'" },
      { from: 0,  to: 8,  label: "'What time does Tartine close?'" },
      { from: 8,  to: 4,  label: "search_places('Tartine')" },
      { from: 4,  to: 5,  label: "Places API" },
      { from: 5,  to: 4,  label: "closes at 5pm" },
      { from: 4,  to: 8,  label: "PlaceResult" },
      { from: 8,  to: 0,  label: "'Tartine closes at 5pm today'" },
    ],
  },

  // ╔══════════════════════════════════════════════════════════════════════
  // ║  BILLING & ACCESS
  // ╚══════════════════════════════════════════════════════════════════════

  free_tier_paywall: {
    title: "Call-Intent Paywall (Free Tier)",
    example: 'Free user: "Call my dentist and schedule a cleaning"',
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'Call my dentist...'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook" },
      { from: 2,  to: 10, label: "get_user() + get_user_tier()" },
      { from: 10, to: 2,  label: "tier: free" },
      { from: 2,  to: 12, label: "load_memory()" },
      { from: 12, to: 2,  label: "profile (new user)" },
      { from: 2,  to: 6,  label: "Claude sees ALL 7 tools (including call)" },
      { from: 6,  to: 4,  label: "search_places('dentist near me')" },
      { from: 4,  to: 5,  label: "Places API" },
      { from: 5,  to: 4,  label: "Dr. Smith, +1555..., place_id" },
      { from: 4,  to: 6,  label: "PlaceResult" },
      { from: 6,  to: 2,  label: "Claude wants to use call_business" },
      { from: 2,  to: 2,  label: "_execute_tool: GATED check (is_free_tier)" },
      { from: 2,  to: 13, label: "send_payment_link(phone)" },
      { from: 13, to: 1,  label: "SMS: Stripe link ($19.99/mo)" },
      { from: 1,  to: 0,  label: "SMS: payment link" },
      { from: 2,  to: 6,  label: "Tool result: 'payment link sent'" },
      { from: 6,  to: 2,  label: "Claude: warm upgrade message" },
      { from: 2,  to: 1,  label: "send_sms(upgrade msg)" },
      { from: 1,  to: 0,  label: "SMS: 'I'd love to call them for you...'" },
      { from: 2,  to: 12, label: "update_memory(convo)" },
    ],
  },

  upgrade_flow: {
    title: "Payment + Upgrade",
    example: 'User texts "pay" or clicks payment link',
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'pay'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook" },
      { from: 2,  to: 2,  label: "UPGRADE_KEYWORDS match" },
      { from: 2,  to: 13, label: "send_payment_link(phone)" },
      { from: 13, to: 1,  label: "SMS: Stripe Payment Link URL" },
      { from: 1,  to: 0,  label: "SMS: link to upgrade" },
      { from: 0,  to: 13, label: "User completes Stripe Checkout" },
      { from: 13, to: 2,  label: "POST /stripe/webhook (checkout.completed)" },
      { from: 2,  to: 10, label: "update_subscription_status('active')" },
      { from: 2,  to: 10, label: "reset_call_count()" },
      { from: 2,  to: 1,  label: "SMS: 'You're all set!'" },
      { from: 1,  to: 0,  label: "SMS: welcome to paid plan" },
    ],
  },

  // ╔══════════════════════════════════════════════════════════════════════
  // ║  INTELLIGENCE LOOPS
  // ╚══════════════════════════════════════════════════════════════════════

  memory_loop: {
    title: "Memory Accumulation + Distillation",
    example: "How the system builds a mental model of each user",
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'I'm allergic to shellfish'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook → orchestrator" },
      { from: 2,  to: 6,  label: "Claude tool loop" },
      { from: 6,  to: 12, label: "update_memory('fact', 'allergic to shellfish')" },
      { from: 12, to: 12, label: "Append to memory_updates list" },
      { from: 6,  to: 2,  label: "Claude: 'Got it, noted.'" },
      { from: 2,  to: 1,  label: "send_sms(response)" },
      { from: 1,  to: 0,  label: "SMS: 'Got it, noted.'" },
      { from: 2,  to: 12, label: "append_conversation(in + out)" },
      { from: 2,  to: 12, label: "append_daily_log('Asked: allergic...')" },
      { from: 2,  to: 12, label: "apply_profile_updates (LLM merge)" },
      { from: 12, to: 6,  label: "LLM: merge new fact into USER.md" },
      { from: 6,  to: 12, label: "Updated USER.md with allergy section" },
      { from: 12, to: 12, label: "--- (hours later) distill_memory ---" },
      { from: 12, to: 6,  label: "LLM: daily logs → MEMORY.md" },
      { from: 6,  to: 12, label: "Curated long-term memory" },
      { from: 12, to: 12, label: "--- (next conversation) ---" },
      { from: 2,  to: 12, label: "load_memory() → profile + MEMORY.md" },
      { from: 12, to: 2,  label: "'Allergies: shellfish' in context" },
      { from: 2,  to: 6,  label: "System prompt now includes allergy" },
    ],
  },

  biz_intel_loop: {
    title: "Business World Model (Learning Loop)",
    example: "How the system builds knowledge about each business",
    steps: [
      { from: 8,  to: 2,  label: "POST /vapi/events (call ended: success)" },
      { from: 2,  to: 2,  label: "classify_call_outcome → success" },
      { from: 2,  to: 3,  label: "update_phone_score(place_id, success)" },
      { from: 2,  to: 15, label: "ensure_business_profile(place_id, name)" },
      { from: 15, to: 3,  label: "INSERT/UPDATE business_profiles" },
      { from: 2,  to: 15, label: "increment_business_calls(success=true)" },
      { from: 15, to: 3,  label: "total_calls++, successful_calls++" },
      { from: 2,  to: 15, label: "extract_call_intelligence (background)" },
      { from: 15, to: 6,  label: "LLM: parse transcript for intelligence" },
      { from: 6,  to: 15, label: "{contacts: [{Maria, host}], hold: 45s}" },
      { from: 15, to: 3,  label: "UPDATE business_profiles.known_contacts" },
      { from: 15, to: 3,  label: "UPDATE business_profiles.avg_hold_time" },
      { from: 15, to: 3,  label: "UPSERT ivr_maps (if IVR detected)" },
      { from: 15, to: 3,  label: "UPDATE business_profiles.notes" },
      { from: 15, to: 15, label: "--- (next query about this business) ---" },
      { from: 2,  to: 15, label: "_build_business_context(message)" },
      { from: 15, to: 3,  label: "SELECT * FROM business_profiles" },
      { from: 3,  to: 15, label: "contacts, hold_time, patterns, notes" },
      { from: 15, to: 2,  label: "'Known: Maria (host), hold ~45s, press 2'" },
      { from: 2,  to: 6,  label: "Injected into system prompt" },
    ],
  },

  // ╔══════════════════════════════════════════════════════════════════════
  // ║  RELIABILITY
  // ╚══════════════════════════════════════════════════════════════════════

  call_failure_retry: {
    title: "Call Failure + Exponential Backoff",
    example: "Business doesn't answer, system retries with increasing delays",
    steps: [
      { from: 8,  to: 2,  label: "POST /vapi/events (call ended: no-answer)" },
      { from: 2,  to: 2,  label: "classify_call_outcome → no_answer" },
      { from: 2,  to: 3,  label: "update_phone_score(no_answer)" },
      { from: 2,  to: 15, label: "ensure_business_profile + incr calls(fail)" },
      { from: 2,  to: 7,  label: "handle_call_failure(record, outcome)" },
      { from: 7,  to: 14, label: "compute_retry_delay(0, 'no_answer')" },
      { from: 14, to: 7,  label: "delay = 10 * 2^0 + jitter = ~12 min" },
      { from: 7,  to: 3,  label: "UPDATE call_log SET retry_pending, retry_after" },
      { from: 7,  to: 16, label: "log_failure('no_answer', severity: low)" },
      { from: 7,  to: 1,  label: "SMS: 'No answer. Trying again in 12 min.'" },
      { from: 1,  to: 0,  label: "SMS: retry notification" },
      { from: 14, to: 14, label: "--- (12 min later: process_retries) ---" },
      { from: 14, to: 7,  label: "SELECT retry_pending WHERE due" },
      { from: 7,  to: 8,  label: "initiate_outbound_call (retry #1)" },
      { from: 8,  to: 9,  label: "Vapi dials business again" },
      { from: 9,  to: 8,  label: "Still no answer" },
      { from: 8,  to: 2,  label: "end-of-call: no-answer again" },
      { from: 2,  to: 7,  label: "handle_call_failure (retry_count=1)" },
      { from: 7,  to: 14, label: "compute_retry_delay(1, 'no_answer')" },
      { from: 14, to: 7,  label: "delay = 10 * 2^1 + jitter = ~25 min" },
      { from: 7,  to: 16, label: "log_failure (2nd occurrence)" },
      { from: 7,  to: 1,  label: "SMS: 'Still no answer. Trying in 25 min.'" },
      { from: 1,  to: 0,  label: "SMS: 2nd retry notification" },
      { from: 14, to: 14, label: "--- (25 min later: final retry) ---" },
      { from: 7,  to: 8,  label: "initiate_outbound_call (retry #2)" },
      { from: 8,  to: 9,  label: "Vapi dials — still no answer" },
      { from: 2,  to: 7,  label: "handle_call_failure (retry_count=2, MAX)" },
      { from: 7,  to: 1,  label: "SMS: 'Tried 3 times. Their #: +1555...'" },
      { from: 1,  to: 0,  label: "SMS: giving up, here's the number" },
    ],
  },

  closed_biz_schedule: {
    title: "Closed Business Queuing",
    example: '"Call the dentist" at 9pm — queued for morning',
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'Call Dr. Smith to schedule cleaning'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook (9:15 PM)" },
      { from: 2,  to: 6,  label: "Claude tool loop" },
      { from: 6,  to: 4,  label: "search_places('Dr. Smith dentist')" },
      { from: 4,  to: 5,  label: "Places API" },
      { from: 5,  to: 4,  label: "phone, hours: 8am-5pm, CLOSED now" },
      { from: 4,  to: 6,  label: "PlaceResult" },
      { from: 6,  to: 7,  label: "pre_call_check()" },
      { from: 7,  to: 4,  label: "get_place_details → open_now: false" },
      { from: 7,  to: 6,  label: "FAILED: business closed" },
      { from: 6,  to: 14, label: "queue_call_for_opening()" },
      { from: 14, to: 3,  label: "INSERT scheduled_tasks (due: 8:15 AM)" },
      { from: 6,  to: 2,  label: "'Closed now. Queued call for 8:15 AM.'" },
      { from: 2,  to: 1,  label: "send_sms()" },
      { from: 1,  to: 0,  label: "SMS: 'They're closed. I'll call at 8:15 AM.'" },
      { from: 14, to: 14, label: "--- (next morning, 8:15 AM) ---" },
      { from: 14, to: 3,  label: "process_queued_calls: SELECT due tasks" },
      { from: 3,  to: 14, label: "task: call Dr. Smith" },
      { from: 14, to: 1,  label: "SMS: 'Calling Dr. Smith now — they opened.'" },
      { from: 1,  to: 0,  label: "SMS: calling notification" },
      { from: 14, to: 7,  label: "initiate_outbound_call()" },
      { from: 7,  to: 8,  label: "POST Vapi /call" },
      { from: 8,  to: 9,  label: "Vapi dials dentist" },
      { from: 9,  to: 8,  label: "'Next Tuesday at 2pm? Done.'" },
      { from: 8,  to: 2,  label: "end-of-call-report: success" },
      { from: 2,  to: 1,  label: "SMS: result" },
      { from: 1,  to: 0,  label: "SMS: 'Cleaning scheduled Tue 2pm'" },
    ],
  },

  proactive_outreach: {
    title: "Proactive Intelligence (Background)",
    example: "System detects patterns and reaches out unprompted",
    steps: [
      { from: 18, to: 18, label: "--- run_proactive_checks (every 1h) ---" },
      { from: 18, to: 3,  label: "SELECT users WHERE status IN (active, free)" },
      { from: 3,  to: 18, label: "user list" },
      { from: 18, to: 18, label: "compute_triggers(user) — deterministic, no LLM" },
      { from: 18, to: 3,  label: "Check: scheduled_tasks due?" },
      { from: 18, to: 3,  label: "Check: call_log retries due?" },
      { from: 18, to: 12, label: "Check: profile patterns? (Friday dinner)" },
      { from: 12, to: 18, label: "'friday' + 'dinner' in profile, it's Friday AM" },
      { from: 18, to: 6,  label: "compose_proactive_message(triggers)" },
      { from: 6,  to: 18, label: "'It's Friday -- want me to book dinner?'" },
      { from: 18, to: 1,  label: "send_sms(proactive message)" },
      { from: 1,  to: 0,  label: "SMS: 'It's Friday -- want me to book dinner?'" },
      { from: 18, to: 12, label: "append_conversation(proactive)" },
    ],
  },

  // ╔══════════════════════════════════════════════════════════════════════
  // ║  ADMIN
  // ╚══════════════════════════════════════════════════════════════════════

  admin_inspect: {
    title: "Admin Dashboard Inspection",
    example: "Operator inspects user, reads soul/memory, views call transcripts",
    steps: [
      { from: 19, to: 2,  label: "GET /admin/stats (X-Admin-Password)" },
      { from: 2,  to: 3,  label: "COUNT users, calls, messages, failures" },
      { from: 3,  to: 2,  label: "aggregated stats" },
      { from: 2,  to: 19, label: "{users: 12, calls: 47, failures: 3}" },
      { from: 19, to: 2,  label: "GET /admin/users" },
      { from: 2,  to: 3,  label: "SELECT users + msg/call counts" },
      { from: 3,  to: 19, label: "user list with stats" },
      { from: 19, to: 2,  label: "GET /admin/users/{phone}/profile" },
      { from: 2,  to: 12, label: "Read USER.md from disk" },
      { from: 12, to: 19, label: "USER.md (the agent's soul for this user)" },
      { from: 19, to: 2,  label: "GET /admin/users/{phone}/memory" },
      { from: 2,  to: 12, label: "Read MEMORY.md from disk" },
      { from: 12, to: 19, label: "MEMORY.md (distilled long-term memory)" },
      { from: 19, to: 2,  label: "GET /admin/users/{phone}/conversations/businesses" },
      { from: 2,  to: 12, label: "Read conversations.jsonl" },
      { from: 2,  to: 3,  label: "SELECT call_log for user" },
      { from: 3,  to: 2,  label: "call records with business names" },
      { from: 2,  to: 19, label: "Messages grouped by business + call cards" },
      { from: 19, to: 2,  label: "GET /admin/users/{phone}/calls/{id}/transcript" },
      { from: 2,  to: 3,  label: "SELECT transcript FROM call_log" },
      { from: 3,  to: 19, label: "Full call transcript" },
      { from: 19, to: 2,  label: "GET /admin/failures?severity=high" },
      { from: 2,  to: 16, label: "SELECT failure_log WHERE severity=high" },
      { from: 16, to: 19, label: "High-severity failures with context" },
      { from: 19, to: 2,  label: "POST /admin/failures/{id}/resolve" },
      { from: 2,  to: 16, label: "UPDATE failure_log SET resolved=true" },
    ],
  },

  // ╔══════════════════════════════════════════════════════════════════════
  // ║  LEGACY
  // ╚══════════════════════════════════════════════════════════════════════

  unregistered: {
    title: "Unregistered User (Signups On)",
    example: "New person texts the number for the first time",
    steps: [
      { from: 0,  to: 1,  label: "SMS: 'Hey, can you help me?'" },
      { from: 1,  to: 2,  label: "POST /sms/webhook" },
      { from: 2,  to: 10, label: "get_user(phone) → None" },
      { from: 10, to: 2,  label: "User not found" },
      { from: 2,  to: 10, label: "get_signups_enabled() → true" },
      { from: 10, to: 2,  label: "Signups on" },
      { from: 2,  to: 10, label: "create_free_user(phone)" },
      { from: 10, to: 3,  label: "INSERT INTO users (status=free)" },
      { from: 2,  to: 1,  label: "SMS: welcome message + 'ask me something'" },
      { from: 1,  to: 0,  label: "SMS: 'Hey, this is Hold Plz...'" },
      { from: 2,  to: 2,  label: "process first message (is_free_tier=true)" },
    ],
  },
};

// ── Component ───────────────────────────────────────────────────────────

export default function GoonSequenceDiagram() {
  const [activeFlow, setActiveFlow] = useState("sms_call_full");
  const [currentStep, setCurrentStep] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playInterval, setPlayInterval] = useState<ReturnType<typeof setInterval> | null>(null);

  const flow = flows[activeFlow];

  const usedActorIds = [...new Set(flow.steps.flatMap((s: Step) => [s.from, s.to]))];
  const usedActors = actors.filter((a) => usedActorIds.includes(a.id));

  const colWidth = 130;
  const totalWidth = Math.max(usedActors.length * colWidth, 700);
  const stepHeight = 46;
  const headerHeight = 100;
  const totalHeight = headerHeight + flow.steps.length * stepHeight + 60;

  const getX = (actorId: number) => {
    const idx = usedActors.findIndex((a) => a.id === actorId);
    return idx * colWidth + colWidth / 2;
  };

  const playAnimation = () => {
    if (playInterval) clearInterval(playInterval);
    setCurrentStep(-1);
    setIsPlaying(true);
    let step = 0;
    const interval = setInterval(() => {
      if (step >= flow.steps.length) {
        clearInterval(interval);
        setIsPlaying(false);
        setPlayInterval(null);
        return;
      }
      setCurrentStep(step);
      step++;
    }, 700);
    setPlayInterval(interval);
  };

  const reset = () => {
    if (playInterval) clearInterval(playInterval);
    setCurrentStep(-1);
    setIsPlaying(false);
    setPlayInterval(null);
  };

  const selectFlow = (key: string) => {
    if (playInterval) clearInterval(playInterval);
    setActiveFlow(key);
    setCurrentStep(-1);
    setIsPlaying(false);
    setPlayInterval(null);
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white p-4">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-1">
          Hold Plz — System Flow Diagrams
        </h1>
        <p className="text-gray-400 text-sm mb-6">
          Interactive sequence diagrams for every path through the system.
          Click a flow, then Play to animate step by step.
        </p>

        {/* ── Flow selector (grouped by category) ── */}
        <div className="mb-6 space-y-3">
          {Object.entries(flowCategories).map(([category, keys]) => (
            <div key={category} className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider w-28 flex-shrink-0">
                {category}
              </span>
              {keys.map((key) => (
                <button
                  key={key}
                  onClick={() => selectFlow(key)}
                  className={`px-3 py-1.5 rounded text-xs font-medium transition-colors ${
                    activeFlow === key
                      ? "bg-blue-600 text-white"
                      : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                  }`}
                >
                  {flows[key].title}
                </button>
              ))}
            </div>
          ))}
        </div>

        {/* ── Diagram ── */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 mb-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-lg font-semibold">{flow.title}</h2>
              <p className="text-gray-400 text-sm italic">{flow.example}</p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={playAnimation}
                disabled={isPlaying}
                className="px-3 py-1.5 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:text-gray-500 rounded text-sm font-medium transition-colors"
              >
                {"\u25B6"} Play
              </button>
              <button
                onClick={() => setCurrentStep(flow.steps.length - 1)}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors"
              >
                Show All
              </button>
              <button
                onClick={reset}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-sm font-medium transition-colors"
              >
                Reset
              </button>
            </div>
          </div>

          {/* Step counter */}
          <div className="text-xs text-gray-500 mb-2">
            {currentStep >= 0
              ? `Step ${currentStep + 1} of ${flow.steps.length}`
              : `${flow.steps.length} steps — click Play or Show All`}
          </div>

          <div className="overflow-x-auto">
            <svg width={totalWidth} height={totalHeight} className="mx-auto">
              {/* Actor headers + lifelines */}
              {usedActors.map((actor, i) => {
                const x = i * colWidth + colWidth / 2;
                const isActive =
                  currentStep >= 0 &&
                  (flow.steps[currentStep]?.from === actor.id ||
                    flow.steps[currentStep]?.to === actor.id);
                return (
                  <g key={actor.id}>
                    <rect
                      x={x - 52}
                      y={10}
                      width={104}
                      height={60}
                      rx={8}
                      fill={isActive ? actor.color + "33" : "#1f2937"}
                      stroke={isActive ? actor.color : "#374151"}
                      strokeWidth={isActive ? 2 : 1}
                    />
                    <text
                      x={x}
                      y={32}
                      textAnchor="middle"
                      className="text-lg"
                      fill="white"
                    >
                      {actor.icon}
                    </text>
                    <text
                      x={x}
                      y={50}
                      textAnchor="middle"
                      fontSize={10}
                      fontWeight="bold"
                      fill="white"
                    >
                      {actor.label}
                    </text>
                    <text
                      x={x}
                      y={62}
                      textAnchor="middle"
                      fontSize={8}
                      fill="#9ca3af"
                    >
                      {actor.sub}
                    </text>

                    <line
                      x1={x}
                      y1={75}
                      x2={x}
                      y2={totalHeight - 20}
                      stroke="#374151"
                      strokeWidth={1}
                      strokeDasharray="4 4"
                    />
                  </g>
                );
              })}

              {/* Arrows */}
              {flow.steps.map((step: Step, i: number) => {
                if (i > currentStep) return null;

                const fromX = getX(step.from);
                const toX = getX(step.to);
                const y = headerHeight + i * stepHeight;
                const isCurrentStep = i === currentStep;
                const isSelfCall = step.from === step.to;

                const fromActor = actors.find((a) => a.id === step.from)!;
                const arrowColor = isCurrentStep
                  ? fromActor.color
                  : fromActor.color + "88";

                if (isSelfCall) {
                  const loopSize = 18;
                  return (
                    <g key={i} opacity={isCurrentStep ? 1 : 0.6}>
                      <path
                        d={`M ${fromX} ${y} C ${fromX + loopSize * 2} ${y}, ${fromX + loopSize * 2} ${y + loopSize}, ${fromX} ${y + loopSize}`}
                        fill="none"
                        stroke={arrowColor}
                        strokeWidth={isCurrentStep ? 2 : 1.5}
                      />
                      <polygon
                        points={`${fromX},${y + loopSize} ${fromX + 5},${y + loopSize - 5} ${fromX - 5},${y + loopSize - 5}`}
                        fill={arrowColor}
                      />
                      <rect
                        x={fromX + loopSize * 2 + 4}
                        y={y - 2}
                        width={Math.min(step.label.length * 5.2 + 12, 350)}
                        height={16}
                        rx={3}
                        fill="#111827"
                        stroke={arrowColor}
                        strokeWidth={0.5}
                      />
                      <text
                        x={fromX + loopSize * 2 + 10}
                        y={y + 10}
                        fontSize={8.5}
                        fill={isCurrentStep ? "#f3f4f6" : "#9ca3af"}
                      >
                        {step.label.length > 60
                          ? step.label.substring(0, 58) + "\u2026"
                          : step.label}
                      </text>
                    </g>
                  );
                }

                const direction = toX > fromX ? 1 : -1;
                const arrowStart = fromX + direction * 8;
                const arrowEnd = toX - direction * 8;
                const midX = (arrowStart + arrowEnd) / 2;

                return (
                  <g key={i} opacity={isCurrentStep ? 1 : 0.6}>
                    <line
                      x1={arrowStart}
                      y1={y}
                      x2={arrowEnd}
                      y2={y}
                      stroke={arrowColor}
                      strokeWidth={isCurrentStep ? 2 : 1.5}
                    />
                    <polygon
                      points={`${arrowEnd},${y} ${arrowEnd - direction * 6},${y - 3.5} ${arrowEnd - direction * 6},${y + 3.5}`}
                      fill={arrowColor}
                    />

                    {(() => {
                      const maxLabelWidth =
                        Math.abs(arrowEnd - arrowStart) - 10;
                      const truncated =
                        step.label.length * 5.2 > maxLabelWidth
                          ? step.label.substring(
                              0,
                              Math.floor(maxLabelWidth / 5.2) - 2
                            ) + "\u2026"
                          : step.label;
                      const labelWidth = truncated.length * 5.2 + 10;
                      return (
                        <>
                          <rect
                            x={midX - labelWidth / 2}
                            y={y - 15}
                            width={labelWidth}
                            height={13}
                            rx={3}
                            fill="#111827ee"
                          />
                          <text
                            x={midX}
                            y={y - 5.5}
                            textAnchor="middle"
                            fontSize={8.5}
                            fill={isCurrentStep ? "#f3f4f6" : "#9ca3af"}
                          >
                            {truncated}
                          </text>
                        </>
                      );
                    })()}
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* ── Step detail panel ── */}
        {currentStep >= 0 && (
          <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 mb-4">
            <div className="flex items-center gap-3">
              <span className="text-xs font-mono bg-gray-800 rounded px-2 py-1 text-gray-400">
                {currentStep + 1}/{flow.steps.length}
              </span>
              <span className="text-sm">
                <span style={{ color: actors.find((a) => a.id === flow.steps[currentStep].from)?.color }}>
                  {actors.find((a) => a.id === flow.steps[currentStep].from)?.label}
                </span>
                {" \u2192 "}
                <span style={{ color: actors.find((a) => a.id === flow.steps[currentStep].to)?.color }}>
                  {actors.find((a) => a.id === flow.steps[currentStep].to)?.label}
                </span>
              </span>
              <span className="text-sm text-gray-300">
                {flow.steps[currentStep].label}
              </span>
            </div>
          </div>
        )}

        {/* ── Resolution Ladder reference ── */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4 mb-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            Resolution Ladder (cheapest {"\u2192"} most expensive)
          </h3>
          <div className="flex flex-wrap gap-2">
            {[
              { step: "1. Cache",        cost: "~free",       time: "<50ms",  color: "#f59e0b" },
              { step: "2. Google Places", cost: "~$0.002",    time: "~200ms", color: "#10b981" },
              { step: "3. Web Search",    cost: "~$0.01",     time: "~1-3s",  color: "#2563eb" },
              { step: "4. Pre-call",      cost: "free",       time: "<200ms", color: "#64748b" },
              { step: "5. Voice Call",    cost: "~$0.10-0.20", time: "~2-5min", color: "#ef4444" },
            ].map((item) => (
              <div
                key={item.step}
                className="flex items-center gap-2 bg-gray-800 rounded px-3 py-2"
              >
                <div
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: item.color }}
                />
                <span className="text-sm font-medium">{item.step}</span>
                <span className="text-xs text-gray-500">
                  {item.cost} {"\u00B7"} {item.time}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* ── Feedback loops reference ── */}
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
          <h3 className="text-sm font-semibold text-gray-300 mb-3">
            Recursive Feedback Loops
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {[
              {
                name: "Phone Score Loop",
                desc: "Call outcome \u2192 phone_scores \u2192 pre_call_check warns agent \u2192 smarter routing",
                color: "#f97316",
              },
              {
                name: "Business Intel Loop",
                desc: "Transcript \u2192 LLM extraction \u2192 business_profiles \u2192 injected into future prompts",
                color: "#f43f5e",
              },
              {
                name: "Memory Loop",
                desc: "Conversation \u2192 USER.md + daily logs \u2192 MEMORY.md distillation \u2192 future context",
                color: "#06b6d4",
              },
              {
                name: "Failure \u2192 Retry Loop",
                desc: "Failure \u2192 failure_log + exponential backoff \u2192 retry \u2192 eventual success or escalation",
                color: "#dc2626",
              },
              {
                name: "Cache Loop",
                desc: "First query: 3-4 tools. Second query: 1 cache hit. Facts expire and refresh.",
                color: "#f59e0b",
              },
              {
                name: "Paywall Loop",
                desc: "Free user \u2192 call intent \u2192 payment link \u2192 Stripe \u2192 upgrade \u2192 full access",
                color: "#84cc16",
              },
            ].map((loop) => (
              <div
                key={loop.name}
                className="flex items-start gap-3 bg-gray-800 rounded px-3 py-2.5"
              >
                <div
                  className="w-2 h-2 rounded-full mt-1.5 flex-shrink-0"
                  style={{ backgroundColor: loop.color }}
                />
                <div>
                  <span className="text-sm font-medium">{loop.name}</span>
                  <p className="text-xs text-gray-400 mt-0.5">{loop.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
