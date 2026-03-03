"""LLM orchestration -- resolution ladder, tool loop, response generation."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

import anthropic

from app.db.database import db
from app.services.auth import get_user, increment_call_count, is_call_quota_available
from app.services.cache import check_cache
from app.services.calls import check_duplicate_call, initiate_outbound_call, pre_call_check
from app.services.memory import load_memory, update_memory
from app.services.places import format_place_for_llm, search_places
from app.config.settings import settings
from app.config.test_businesses import TEST_BUSINESSES
from app.prompts.soul import get_sms_soul
from app.services.search import search_web

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-5-20250929"
MAX_TOOL_ROUNDS = 10

# Tools that require a paid subscription
GATED_TOOLS = {"call_business", "pre_call_check"}

# ---- Resolution ladder instruction for the system prompt ----

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

# ---- Tool definitions for the Claude API ----

TOOLS: list[dict] = [
    {
        "name": "check_cache",
        "description": (
            "Check if we have a cached answer for this business + question. "
            "ALWAYS try this first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "fact_type": {
                    "type": "string",
                    "enum": [
                        "hours", "phone", "address", "menu", "pricing",
                        "reservation_policy", "availability", "attributes",
                        "general",
                    ],
                },
            },
            "required": ["business_name", "fact_type"],
        },
    },
    {
        "name": "search_places",
        "description": (
            "Search Google Places for structured business data "
            "(hours, phone, address, ratings, attributes). "
            "Try this before web search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "location": {
                    "type": "string",
                    "description": "City or address for location bias",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_web",
        "description": (
            "Search the web for business info not available in Google Places "
            "(menus, specific pricing, specials, detailed reviews)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "pre_call_check",
        "description": (
            "Run pre-call validation before calling a business. "
            "Checks: is business open now? Is phone number reliable? "
            "Is this a chain?"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "business_phone": {"type": "string"},
                "place_id": {"type": "string"},
            },
            "required": ["business_name", "business_phone"],
        },
    },
    {
        "name": "call_business",
        "description": (
            "LAST RESORT. Initiate an AI voice call to a business. "
            "Only use after exhausting cache, places, and web search -- "
            "OR when the task requires human interaction "
            "(reservation, appointment, custom order)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "business_name": {"type": "string"},
                "business_phone": {"type": "string"},
                "task": {
                    "type": "string",
                    "description": "What to ask or do, stated naturally",
                },
                "task_type": {
                    "type": "string",
                    "enum": [
                        "information", "reservation", "appointment",
                        "availability_check", "custom_request",
                    ],
                },
                "place_id": {"type": "string"},
                "details": {
                    "type": "object",
                    "description": (
                        "Structured details (party_size, date, time, name, etc.)"
                    ),
                },
            },
            "required": ["business_name", "business_phone", "task", "task_type"],
        },
    },
    {
        "name": "update_memory",
        "description": "Save a new fact or preference about the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "preference", "fact", "routine",
                        "business_relationship", "task_result",
                    ],
                },
                "content": {"type": "string"},
            },
            "required": ["category", "content"],
        },
    },
    {
        "name": "schedule_followup",
        "description": "Schedule a future SMS to the user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "when": {
                    "type": "string",
                    "description": (
                        "ISO datetime or relative "
                        "('in 2 hours', 'tomorrow 9am')"
                    ),
                },
                "trigger": {
                    "type": "string",
                    "description": "Why this followup exists (for proactive system)",
                },
            },
            "required": ["message", "when"],
        },
    },
]


# ---- Result container ----

@dataclass
class OrchestratorResult:
    """Result from the orchestrator's agentic loop."""

    text: str
    memory_updates: list[dict] = field(default_factory=list)
    call_plan: dict | None = None


# ---- System prompt builder ----

def build_system_prompt(
    user: dict, memory, is_free_tier: bool = False
) -> str:
    """Build the system prompt with user context and resolution ladder."""
    name = user.get("name", "there")
    phone = user.get("phone", user.get("id", ""))
    soul = get_sms_soul()

    # Free tier context
    free_tier_section = ""
    if is_free_tier:
        used = user.get("free_messages_used", 0)
        limit = settings.free_message_limit
        remaining = max(0, limit - used)
        free_tier_section = f"""
## Access Level: Free Tier
This user has {remaining} free messages remaining (of {limit}).
They can search for business info but CANNOT make calls.
Do NOT mention calling businesses as an option.
If the user asks you to call somewhere, explain that calling requires the paid plan
and they can text "pay" to upgrade ($19.99/mo, 20 calls).
Keep responses helpful — show the value of what you can do for free (search, lookup, info).
"""
    else:
        calls_used = user.get("calls_used_this_period", 0)
        quota = settings.monthly_call_quota
        calls_remaining = max(0, quota - calls_used)
        if not user.get("allowlisted"):
            free_tier_section = f"""
## Call Quota
User has {calls_remaining} calls remaining this billing period (of {quota}).
"""

    return f"""{soul}

---

You are texting with {name} (phone: {phone}).
Today: {datetime.now().isoformat()}

{RESOLUTION_LADDER_INSTRUCTION}
{free_tier_section}

## User Memory
{memory.profile}

{memory.long_term_memory_section}

## Conversation History (last 5 + last interaction per active business)
{memory.formatted_recent}

## Active Tasks
{memory.formatted_tasks}

## Operational Guidelines
- Confirm before calling for reservations/appointments (get details right)
- For simple info questions, just answer -- don't ask permission to look it up
- Update memory when you learn something new about the user
- If the user's location matters and you don't know it, ask
- After a call completes, text the result concisely
- If a call is in progress, say so briefly: "Calling [business] now. Back in a few."
"""


# ---- Test business helper ----

def _check_test_business(query: str) -> str | None:
    """Check if query matches a test business. Returns formatted info or None."""
    if not settings.enable_test_businesses:
        return None
    query_lower = query.lower()
    for key, biz in TEST_BUSINESSES.items():
        if key in query_lower or biz["name"].lower() in query_lower:
            return (
                f"Name: {biz['name']}\n"
                f"Address: {biz['address']}\n"
                f"Phone: {biz['phone']}\n"
                f"Hours: {biz['hours']}\n"
                f"Open now: {biz['open_now']}\n"
                f"Reservable: {biz['attributes'].get('reservable', False)}"
            )
    return None


# ---- Tool execution dispatch ----

async def _execute_tool(
    tool_name: str,
    tool_input: dict,
    user: dict,
    memory_updates: list[dict],
    is_free_tier: bool = False,
) -> str:
    """Execute a single tool call and return the result as a string."""
    # Defense-in-depth: block gated tools for free tier even if LLM hallucinates them
    if is_free_tier and tool_name in GATED_TOOLS:
        return (
            "This feature requires a paid subscription. "
            "The user can text 'pay' to upgrade."
        )

    try:
        if tool_name == "check_cache":
            result = await check_cache(
                tool_input["business_name"],
                tool_input["fact_type"],
            )
            return result or "No cached answer found."

        elif tool_name == "search_places":
            # Check test businesses before hitting Google Places API
            test_result = _check_test_business(tool_input["query"])
            if test_result:
                return test_result
            places = await search_places(
                query=tool_input["query"],
                location=tool_input.get("location"),
            )
            if not places:
                return "No results found on Google Places."
            return "\n---\n".join(format_place_for_llm(p) for p in places)

        elif tool_name == "search_web":
            return await search_web(tool_input["query"])

        elif tool_name == "pre_call_check":
            result = await pre_call_check(
                business_name=tool_input["business_name"],
                business_phone=tool_input["business_phone"],
                place_id=tool_input.get("place_id"),
            )
            if result["ok"]:
                issues_text = ""
                if result["issues"]:
                    issues_text = " Warnings: " + "; ".join(
                        i["message"] for i in result["issues"]
                    )
                return f"Pre-call check passed.{issues_text} OK to call."
            else:
                issues_text = "; ".join(i["message"] for i in result["issues"])
                return f"Pre-call check FAILED: {issues_text}"

        elif tool_name == "call_business":
            # Call quota check for paying users
            if not await is_call_quota_available(user, settings.monthly_call_quota):
                return (
                    f"Call quota reached ({settings.monthly_call_quota} calls/month). "
                    "The user's quota resets at the start of their next billing period."
                )
            # Route test businesses to test phone before calling
            if settings.enable_test_businesses:
                query = tool_input["business_name"].lower()
                for key, biz in TEST_BUSINESSES.items():
                    if key in query or biz["name"].lower() in query:
                        tool_input["business_phone"] = biz["phone"]
                        tool_input["place_id"] = biz["place_id"]
                        break
            user_id = user.get("id", user.get("phone", ""))
            # Check for duplicate in-progress call
            existing = await check_duplicate_call(
                user_id, tool_input["business_phone"],
            )
            if existing:
                return (
                    f"A call to {tool_input['business_name']} is already in progress "
                    f"(call id: {existing['vapi_call_id']}). Wait for it to complete."
                )
            user_name = user.get("name", "")
            call_result = await initiate_outbound_call(
                business_name=tool_input["business_name"],
                business_phone=tool_input["business_phone"],
                task=tool_input["task"],
                user_id=user_id,
                task_type=tool_input.get("task_type", "information"),
                place_id=tool_input.get("place_id"),
                user_name=user_name,
                details=tool_input.get("details"),
            )
            # Track call usage against quota
            await increment_call_count(user.get("phone", user_id))
            return (
                f"Call initiated (id: {call_result['vapi_call_id']}). "
                f"Result will arrive via webhook."
            )

        elif tool_name == "update_memory":
            memory_updates.append({
                "category": tool_input["category"],
                "content": tool_input["content"],
            })
            return "Memory updated."

        elif tool_name == "schedule_followup":
            when = tool_input["when"]
            message = tool_input["message"]
            trigger = tool_input.get("trigger", "")
            user_id = user.get("id", user.get("phone", ""))
            await db.execute(
                """
                INSERT INTO scheduled_tasks (user_id, message, trigger, due_at, status)
                VALUES (?, ?, ?, ?, 'pending')
                """,
                [user_id, message, trigger, when],
            )
            return f"Followup scheduled for {when}."

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as exc:
        logger.exception("Tool %s failed", tool_name)
        return f"Tool error: {exc}"


# ---- Public API ----

async def handle_message(
    user_id: str, message: str, is_free_tier: bool = False
) -> str:
    """Process a user message through the resolution ladder.

    Called by the SMS webhook. Loads user + memory, runs the Claude
    tool-calling loop, persists memory updates, and returns the
    response text to send back via SMS.
    """
    # Load user record and memory
    user = await get_user(user_id)
    if not user:
        user = {"id": user_id, "phone": user_id, "name": "there"}

    memory = await load_memory(user_id)

    # Build the conversation for Claude
    system = build_system_prompt(user, memory, is_free_tier=is_free_tier)

    # Filter tools for free tier — LLM can't even see gated tools
    active_tools = [t for t in TOOLS if t["name"] not in GATED_TOOLS] if is_free_tier else TOOLS

    messages: list[dict] = [{"role": "user", "content": message}]

    client = anthropic.AsyncAnthropic()
    memory_updates: list[dict] = []
    call_plan: dict | None = None

    # Agentic loop: LLM decides which tools to call
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system,
                tools=active_tools,
                messages=messages,
            )
        except anthropic.RateLimitError:
            logger.warning("Anthropic rate limit hit for user %s", user_id)
            result_text = "I'm a bit overloaded right now. Try again in a minute."
            break
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API error %d: %s", exc.status_code, exc.message)
            result_text = "Something went wrong on my end. Try again in a minute."
            break
        except Exception:
            logger.exception("Unexpected error calling Anthropic API")
            result_text = "Something went wrong on my end. Try again in a minute."
            break

        # If no tool use, we have our final answer
        if response.stop_reason == "end_turn":
            text_blocks = [b.text for b in response.content if b.type == "text"]
            result_text = "\n".join(text_blocks)
            break

        # Handle tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            result = await _execute_tool(
                block.name, block.input, user, memory_updates,
                is_free_tier=is_free_tier,
            )

            # Capture call plan if call_business was invoked
            if block.name == "call_business":
                call_plan = block.input

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        # Feed tool results back and continue loop
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        # If a call was initiated, break -- the result comes async via webhook
        if call_plan:
            biz_name = call_plan.get("business_name", "the business")
            result_text = f"Calling {biz_name} now. Back in a few."
            break
    else:
        # Exhausted tool rounds without a final answer
        result_text = "Sorry, I had trouble with that. Try asking again?"

    # Persist memory (conversation + any LLM-generated updates)
    asyncio.create_task(
        update_memory(user_id, message, result_text, memory_updates or None)
    )

    return result_text
