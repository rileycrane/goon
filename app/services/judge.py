"""LLM Request Judge -- classifies messages into sessions/requests, resolves from calls."""
from __future__ import annotations

import json
import logging
from datetime import datetime

import anthropic

from app.db.database import db

logger = logging.getLogger(__name__)

JUDGE_MODEL = "claude-haiku-4-5-20251001"

# ---- Judge tool schema for forced tool use ----

CLASSIFY_TOOL = {
    "name": "classify_requests",
    "description": "Classify the user message into zero or more business requests.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["new", "continuation"],
                        },
                        "existing_request_id": {
                            "type": ["integer", "null"],
                            "description": "If continuation, the request ID being continued",
                        },
                        "business_name": {"type": "string"},
                        "task_summary": {
                            "type": "string",
                            "description": "1-line summary of the task",
                        },
                        "task_type": {
                            "type": "string",
                            "enum": [
                                "information",
                                "reservation",
                                "appointment",
                                "availability_check",
                                "custom_request",
                            ],
                        },
                    },
                    "required": [
                        "type",
                        "business_name",
                        "task_summary",
                        "task_type",
                    ],
                },
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of the classification",
            },
        },
        "required": ["items", "reasoning"],
    },
}

JUDGE_SYSTEM_PROMPT = """You are a request classifier for Hold Plz, an AI concierge that helps users interact with businesses via SMS and phone calls.

Given a user message, the assistant's response, and recent conversation context, classify the message into zero or more business requests.

## Rules

1. One message can reference multiple businesses -> multiple requests in different sessions.
2. Same business + same task in consecutive messages = continuation of existing request.
3. Same business + different question = new request in same session.
4. Corrections ("make it 7:30", "actually 3 people") = continuation of the most recent request for that business.
5. Chit-chat, preferences, thanks, "ok", "cool" = not a request (return empty items).
6. "Cancel X" or "never mind about X" = continuation that should be noted but is still the same request.

## Determining status from the assistant response

- If the response contains "Calling ... now" or similar -> the request will become pending_call
- If the response gives a substantive answer (hours, address, info) -> resolved
- If the response asks a clarifying question -> open
- If the response is chit-chat / acknowledgment -> not a request

Use the classify_requests tool to return your classification."""


async def classify_message(
    user_id: str,
    message: str,
    response_text: str,
    message_log_id: int,
) -> None:
    """Classify a user message into sessions and requests. Runs async after SMS response."""
    try:
        # Load recent conversation for context
        recent = await db.fetch_all(
            "SELECT id, direction, body, created_at FROM message_log "
            "WHERE user_id = ? ORDER BY created_at DESC LIMIT 8",
            [user_id],
        )
        recent.reverse()

        # Load open requests with their sessions
        open_requests = await db.fetch_all(
            """SELECT r.id, r.task_summary, r.task_type, r.status, s.business_name
               FROM requests r
               JOIN sessions s ON r.session_id = s.id
               WHERE s.user_id = ? AND r.status IN ('open', 'pending_call', 'retry_pending')
               ORDER BY r.created_at DESC LIMIT 10""",
            [user_id],
        )

        # Build context for the judge
        convo_lines = []
        for msg in recent:
            prefix = "User" if msg["direction"] == "in" else "Assistant"
            convo_lines.append(f"{prefix}: {msg['body']}")
        convo_context = "\n".join(convo_lines)

        open_req_lines = []
        for req in open_requests:
            open_req_lines.append(
                f"- Request #{req['id']} ({req['status']}): "
                f"{req['business_name']} -- {req['task_summary']}"
            )
        open_req_context = "\n".join(open_req_lines) if open_req_lines else "(none)"

        user_prompt = (
            f"## Recent conversation\n{convo_context}\n\n"
            f"## Open requests\n{open_req_context}\n\n"
            f"## Current message\nUser: {message}\n\n"
            f"## Assistant response\n{response_text}\n\n"
            f"Classify this message."
        )

        client = anthropic.AsyncAnthropic()
        resp = await client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=512,
            system=JUDGE_SYSTEM_PROMPT,
            tools=[CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "classify_requests"},
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract the tool use result
        classification = None
        for block in resp.content:
            if block.type == "tool_use" and block.name == "classify_requests":
                classification = block.input
                break

        if not classification:
            logger.warning("Judge returned no classification for user %s", user_id)
            return

        items = classification.get("items", [])
        reasoning = classification.get("reasoning", "")

        if not items:
            logger.debug("Judge: no requests in message from %s (%s)", user_id, reasoning)
            return

        # Determine status from response text
        response_lower = response_text.lower()
        calling_now = "calling" in response_lower and "now" in response_lower

        for item in items:
            biz_name = item["business_name"]
            task_summary = item["task_summary"]
            task_type = item.get("task_type", "information")
            item_type = item.get("type", "new")
            existing_id = item.get("existing_request_id")

            # Get or create session
            session = await _get_or_create_session(user_id, biz_name)

            if item_type == "continuation" and existing_id:
                # Update existing request
                await db.execute(
                    "UPDATE requests SET task_summary = ? WHERE id = ?",
                    [task_summary, existing_id],
                )
                # Link message to existing request
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO request_messages (request_id, message_log_id) VALUES (?, ?)",
                        [existing_id, message_log_id],
                    )
                except Exception:
                    pass
                request_id = existing_id
            else:
                # Determine initial status
                if calling_now:
                    status = "pending_call"
                    resolution_method = None
                elif _looks_resolved(response_text, task_type):
                    status = "resolved"
                    resolution_method = _infer_resolution_method(response_text)
                else:
                    status = "open"
                    resolution_method = None

                # Check billability
                user = await db.fetch_one(
                    "SELECT plan_type FROM users WHERE id = ?", [user_id]
                )
                plan_type = user["plan_type"] if user else "basic"
                billable = status == "resolved" and plan_type == "request"

                # Create new request
                request_id = await db.execute(
                    """INSERT INTO requests
                       (session_id, task_summary, task_type, status, billable,
                        resolution_method, judge_reasoning, resolved_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        session["id"],
                        task_summary,
                        task_type,
                        status,
                        billable,
                        resolution_method,
                        reasoning,
                        datetime.utcnow().isoformat() if status == "resolved" else None,
                    ],
                )

                # Link message
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO request_messages (request_id, message_log_id) VALUES (?, ?)",
                        [request_id, message_log_id],
                    )
                except Exception:
                    pass

                # Charge if billable
                if billable:
                    try:
                        await _charge_request(request_id, user_id)
                    except Exception:
                        logger.exception("Failed to charge request %d", request_id)

                # Categorize against the living taxonomy (async, non-blocking)
                import asyncio
                asyncio.create_task(
                    categorize_request(request_id, task_summary, task_type)
                )

            # Update session activity
            await db.execute(
                "UPDATE sessions SET last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                [session["id"]],
            )

        logger.info(
            "Judge classified %d items for user %s: %s",
            len(items), user_id, reasoning,
        )

    except Exception:
        logger.exception("Judge classification failed for user %s", user_id)


async def resolve_request_from_call(
    call_log_id: int,
    success: bool,
    is_final_failure: bool,
) -> None:
    """Resolve a request based on call outcome. Called from vapi_events after call ends."""
    try:
        # Find request via call_log.request_id
        call = await db.fetch_one(
            "SELECT request_id, user_id, business_name, place_id FROM call_log WHERE id = ?",
            [call_log_id],
        )
        if not call:
            logger.warning("resolve_request_from_call: no call_log for id=%d", call_log_id)
            return

        request_id = call.get("request_id")

        # Fallback: fuzzy match by (user, business, status)
        if not request_id:
            request = await db.fetch_one(
                """SELECT r.id FROM requests r
                   JOIN sessions s ON r.session_id = s.id
                   WHERE s.user_id = ? AND s.business_name = ?
                     AND r.status IN ('pending_call', 'retry_pending')
                   ORDER BY r.created_at DESC LIMIT 1""",
                [call["user_id"], call["business_name"]],
            )
            if request:
                request_id = request["id"]
                # Backfill the link
                await db.execute(
                    "UPDATE call_log SET request_id = ? WHERE id = ?",
                    [request_id, call_log_id],
                )

        if not request_id:
            logger.debug(
                "resolve_request_from_call: no matching request for call %d (%s / %s)",
                call_log_id, call["user_id"], call["business_name"],
            )
            return

        if success:
            # Check if user is on request plan
            user = await db.fetch_one(
                "SELECT plan_type FROM users WHERE id = ?", [call["user_id"]]
            )
            plan_type = user["plan_type"] if user else "basic"
            billable = plan_type == "request"

            await db.execute(
                """UPDATE requests SET status = 'resolved', resolution_method = 'call',
                   billable = ?, resolved_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                [billable, request_id],
            )

            if billable:
                try:
                    await _charge_request(request_id, call["user_id"])
                except Exception:
                    logger.exception("Failed to charge request %d after call", request_id)

        elif is_final_failure:
            await db.execute(
                "UPDATE requests SET status = 'failed' WHERE id = ?",
                [request_id],
            )
        else:
            await db.execute(
                "UPDATE requests SET status = 'retry_pending' WHERE id = ?",
                [request_id],
            )

        # Update session activity + backfill place_id from call
        req_row = await db.fetch_one(
            "SELECT session_id FROM requests WHERE id = ?", [request_id]
        )
        if req_row:
            sid = req_row["session_id"]
            await db.execute(
                "UPDATE sessions SET last_activity_at = CURRENT_TIMESTAMP WHERE id = ?",
                [sid],
            )
            # Backfill place_id on session if the call had one
            if call.get("place_id"):
                await db.execute(
                    "UPDATE sessions SET place_id = ? WHERE id = ? AND place_id IS NULL",
                    [call["place_id"], sid],
                )

        logger.info(
            "Resolved request %d from call %d: success=%s final_failure=%s",
            request_id, call_log_id, success, is_final_failure,
        )

    except Exception:
        logger.exception("resolve_request_from_call failed for call %d", call_log_id)


async def _get_or_create_session(user_id: str, business_name: str) -> dict:
    """Get existing session or create a new one for (user, business)."""
    session = await db.fetch_one(
        "SELECT * FROM sessions WHERE user_id = ? AND business_name = ?",
        [user_id, business_name],
    )
    if session:
        # Backfill place_id if missing
        if not session.get("place_id"):
            place_id = await _lookup_place_id(business_name)
            if place_id:
                await db.execute(
                    "UPDATE sessions SET place_id = ? WHERE id = ?",
                    [place_id, session["id"]],
                )
                session = dict(session)
                session["place_id"] = place_id
        return session

    # Try to find place_id for new session
    place_id = await _lookup_place_id(business_name)

    session_id = await db.execute(
        "INSERT INTO sessions (user_id, business_name, place_id) VALUES (?, ?, ?)",
        [user_id, business_name, place_id],
    )
    return {"id": session_id, "user_id": user_id, "business_name": business_name, "place_id": place_id}


async def _lookup_place_id(business_name: str) -> str | None:
    """Try to find a place_id for a business from existing data."""
    # Check call_log first (most reliable — we've interacted)
    record = await db.fetch_one(
        "SELECT place_id FROM call_log WHERE business_name = ? AND place_id IS NOT NULL ORDER BY created_at DESC LIMIT 1",
        [business_name],
    )
    if record:
        return record["place_id"]

    # Check business_facts
    record = await db.fetch_one(
        "SELECT place_id FROM business_facts WHERE business_name = ? AND place_id IS NOT NULL LIMIT 1",
        [business_name],
    )
    if record:
        return record["place_id"]

    # Check business_profiles
    record = await db.fetch_one(
        "SELECT place_id FROM business_profiles WHERE business_name = ? LIMIT 1",
        [business_name],
    )
    if record:
        return record["place_id"]

    return None


def _looks_resolved(response_text: str, task_type: str) -> bool:
    """Heuristic: does the response look like it answered the question?"""
    lower = response_text.lower()
    # If calling, not resolved yet
    if "calling" in lower and "now" in lower:
        return False
    # Information requests are often resolved inline
    if task_type == "information" and len(response_text) > 40:
        return True
    # Reservations/appointments need a call
    if task_type in ("reservation", "appointment"):
        return False
    # Default: if it's a long response, probably resolved
    return len(response_text) > 60


def _infer_resolution_method(response_text: str) -> str:
    """Infer how the request was resolved from the response."""
    lower = response_text.lower()
    if "google" in lower or "hours" in lower:
        return "places"
    if "found" in lower or "search" in lower:
        return "web"
    return "cache"


async def _charge_request(request_id: int, user_id: str) -> None:
    """Charge $1 for a resolved request on the request plan."""
    from app.services.billing import charge_request
    await charge_request(request_id, user_id)


# ---- Request Taxonomy ----

CATEGORIZE_TOOL = {
    "name": "categorize_request",
    "description": "Categorize a request against the existing taxonomy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["match_existing", "create_new", "merge_categories"],
            },
            "existing_category_id": {
                "type": ["integer", "null"],
                "description": "If match_existing, which category ID it matches",
            },
            "new_category": {
                "type": ["string", "null"],
                "description": "If create_new, the snake_case category name",
            },
            "new_description": {
                "type": ["string", "null"],
                "description": "If create_new, a 1-line description of what this category covers",
            },
            "merge_from": {
                "type": ["integer", "null"],
                "description": "If merge_categories, the category ID to merge FROM",
            },
            "merge_into": {
                "type": ["integer", "null"],
                "description": "If merge_categories, the category ID to merge INTO",
            },
            "reasoning": {"type": "string"},
        },
        "required": ["action", "reasoning"],
    },
}

CATEGORIZE_SYSTEM = """You maintain a living taxonomy of request categories for Hold Plz, an AI concierge.

Given a new request and the existing taxonomy, decide:
1. Does this request match an existing category? -> match_existing
2. Is this genuinely new? -> create_new (be conservative -- only if truly different)
3. Should two existing categories be merged? -> merge_categories (if you realize they're the same thing)

Be parsimonious. Prefer matching existing categories. Only create new ones when the request is fundamentally different from everything that exists. Categories should be useful for analytics (e.g., "restaurant_reservation", "business_hours_check", "appointment_booking").

Use snake_case for category names. Keep them specific enough to be useful but general enough to accumulate counts."""


async def categorize_request(request_id: int, task_summary: str, task_type: str) -> None:
    """Categorize a request against the living taxonomy. Runs async."""
    try:
        # Load existing taxonomy
        categories = await db.fetch_all(
            "SELECT id, category, description, count FROM request_categories ORDER BY count DESC"
        )

        cat_lines = []
        for cat in categories:
            cat_lines.append(
                f"- ID {cat['id']}: {cat['category']} ({cat['count']} requests) -- {cat['description']}"
            )
        cat_context = "\n".join(cat_lines) if cat_lines else "(empty -- this is the first request)"

        client = anthropic.AsyncAnthropic()
        resp = await client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=256,
            system=CATEGORIZE_SYSTEM,
            tools=[CATEGORIZE_TOOL],
            tool_choice={"type": "tool", "name": "categorize_request"},
            messages=[{
                "role": "user",
                "content": (
                    f"## Existing taxonomy\n{cat_context}\n\n"
                    f"## New request\nSummary: {task_summary}\nType: {task_type}\n\n"
                    f"Categorize this request."
                ),
            }],
        )

        result = None
        for block in resp.content:
            if block.type == "tool_use" and block.name == "categorize_request":
                result = block.input
                break

        if not result:
            return

        action = result.get("action")

        if action == "match_existing" and result.get("existing_category_id"):
            cat_id = result["existing_category_id"]
            # Increment count and add example
            cat = await db.fetch_one(
                "SELECT example_summaries FROM request_categories WHERE id = ?", [cat_id]
            )
            if cat:
                examples = json.loads(cat["example_summaries"] or "[]")
                if len(examples) < 10:
                    examples.append(task_summary)
                await db.execute(
                    """UPDATE request_categories
                       SET count = count + 1, example_summaries = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    [json.dumps(examples), cat_id],
                )
                await db.execute(
                    "UPDATE requests SET category_id = ? WHERE id = ?",
                    [cat_id, request_id],
                )

        elif action == "create_new" and result.get("new_category"):
            cat_id = await db.execute(
                """INSERT INTO request_categories (category, description, example_summaries)
                   VALUES (?, ?, ?)""",
                [
                    result["new_category"],
                    result.get("new_description", ""),
                    json.dumps([task_summary]),
                ],
            )
            await db.execute(
                "UPDATE requests SET category_id = ? WHERE id = ?",
                [cat_id, request_id],
            )

        elif action == "merge_categories" and result.get("merge_from") and result.get("merge_into"):
            merge_from = result["merge_from"]
            merge_into = result["merge_into"]
            # Move all requests from merge_from to merge_into
            from_cat = await db.fetch_one(
                "SELECT count, example_summaries FROM request_categories WHERE id = ?",
                [merge_from],
            )
            if from_cat:
                into_cat = await db.fetch_one(
                    "SELECT example_summaries FROM request_categories WHERE id = ?",
                    [merge_into],
                )
                if into_cat:
                    from_examples = json.loads(from_cat["example_summaries"] or "[]")
                    into_examples = json.loads(into_cat["example_summaries"] or "[]")
                    merged = (into_examples + from_examples)[:10]
                    await db.execute(
                        """UPDATE request_categories
                           SET count = count + ?, example_summaries = ?, updated_at = CURRENT_TIMESTAMP
                           WHERE id = ?""",
                        [from_cat["count"], json.dumps(merged), merge_into],
                    )
                await db.execute(
                    "UPDATE requests SET category_id = ? WHERE category_id = ?",
                    [merge_into, merge_from],
                )
                await db.execute(
                    "DELETE FROM request_categories WHERE id = ?", [merge_from]
                )
            # Also categorize the current request
            await db.execute(
                "UPDATE requests SET category_id = ? WHERE id = ?",
                [merge_into, request_id],
            )

        logger.debug(
            "Categorized request %d: %s (%s)", request_id, action, result.get("reasoning", "")
        )

    except Exception:
        logger.exception("Failed to categorize request %d", request_id)
