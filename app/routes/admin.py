"""Admin dashboard — user management, business intelligence, system health."""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Response
from pydantic import BaseModel

from app.config import settings
from app.db.database import db
from app.services.auth import get_signups_enabled, set_signups_enabled
from app.services.memory import distill_memory, load_memory, reflect
from app.services.sms import send_sms, calculate_segments

logger = logging.getLogger(__name__)

router = APIRouter()

USER_DATA_DIR = Path(settings.user_data_dir)


def _check_admin(password: Optional[str]) -> None:
    if not settings.admin_password or password != settings.admin_password:
        raise HTTPException(status_code=401, detail="unauthorized")


# ---- Overview ----

@router.get("/stats")
async def admin_stats(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """System-wide metrics for admin overview."""
    _check_admin(x_admin_password)

    users_total = await db.fetch_one("SELECT COUNT(*) as c FROM users")
    users_free = await db.fetch_one(
        "SELECT COUNT(*) as c FROM users WHERE subscription_status = 'free'"
    )
    users_active = await db.fetch_one(
        "SELECT COUNT(*) as c FROM users WHERE subscription_status = 'active'"
    )
    calls_total = await db.fetch_one("SELECT COUNT(*) as c FROM call_log")
    calls_success = await db.fetch_one(
        "SELECT COUNT(*) as c FROM call_log WHERE status = 'success'"
    )
    calls_failed = await db.fetch_one(
        "SELECT COUNT(*) as c FROM call_log WHERE status LIKE 'failed%'"
    )
    msgs_24h = await db.fetch_one(
        "SELECT COUNT(*) as c FROM message_log WHERE created_at > datetime('now', '-1 day')"
    )
    msgs_7d = await db.fetch_one(
        "SELECT COUNT(*) as c FROM message_log WHERE created_at > datetime('now', '-7 days')"
    )
    failures_active = await db.fetch_one(
        "SELECT COUNT(*) as c FROM failure_log WHERE resolved = FALSE"
    )

    sessions_total = await db.fetch_one("SELECT COUNT(*) as c FROM sessions")
    requests_total = await db.fetch_one("SELECT COUNT(*) as c FROM requests")
    requests_open = await db.fetch_one(
        "SELECT COUNT(*) as c FROM requests WHERE status IN ('open', 'pending_call', 'retry_pending')"
    )
    requests_billable_uncharged = await db.fetch_one(
        "SELECT COUNT(*) as c FROM requests WHERE billable = TRUE AND charged = FALSE"
    )

    recent_messages = await db.fetch_all(
        "SELECT * FROM message_log ORDER BY created_at DESC LIMIT 10"
    )
    recent_calls = await db.fetch_all(
        "SELECT * FROM call_log ORDER BY created_at DESC LIMIT 10"
    )

    return {
        "users": {
            "total": users_total["c"] if users_total else 0,
            "free": users_free["c"] if users_free else 0,
            "active": users_active["c"] if users_active else 0,
        },
        "calls": {
            "total": calls_total["c"] if calls_total else 0,
            "success": calls_success["c"] if calls_success else 0,
            "failed": calls_failed["c"] if calls_failed else 0,
        },
        "messages": {
            "last_24h": msgs_24h["c"] if msgs_24h else 0,
            "last_7d": msgs_7d["c"] if msgs_7d else 0,
        },
        "sessions": {
            "total": sessions_total["c"] if sessions_total else 0,
        },
        "requests": {
            "total": requests_total["c"] if requests_total else 0,
            "open": requests_open["c"] if requests_open else 0,
            "billable_uncharged": requests_billable_uncharged["c"] if requests_billable_uncharged else 0,
        },
        "failures_active": failures_active["c"] if failures_active else 0,
        "recent_messages": recent_messages,
        "recent_calls": recent_calls,
    }


@router.get("/")
async def admin_dashboard() -> dict:
    """Admin dashboard overview."""
    return {"status": "ok"}


# ---- User Management ----

class SeedUserRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    allowlisted: bool = True


@router.post("/seed-user")
async def seed_user(
    body: SeedUserRequest,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Seed or update a user in the database."""
    _check_admin(x_admin_password)
    await db.execute(
        """INSERT INTO users (id, phone, name, subscription_status, allowlisted)
           VALUES (?, ?, ?, 'active', ?)
           ON CONFLICT(id) DO UPDATE SET
               name = excluded.name,
               subscription_status = 'active',
               allowlisted = excluded.allowlisted""",
        (body.phone, body.phone, body.name, body.allowlisted),
    )
    return {"status": "ok", "phone": body.phone, "name": body.name}


@router.get("/users")
async def list_users(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """List all users with tier, message count, call count."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        """SELECT id, phone, name, subscription_status, allowlisted,
                  free_messages_used, calls_used_this_period, created_at
           FROM users ORDER BY created_at DESC"""
    )
    # Add message and call counts per user
    for row in rows:
        msg_count = await db.fetch_one(
            "SELECT COUNT(*) as c FROM message_log WHERE user_id = ?",
            [row["id"]],
        )
        call_count = await db.fetch_one(
            "SELECT COUNT(*) as c FROM call_log WHERE user_id = ?",
            [row["id"]],
        )
        row["total_messages"] = msg_count["c"] if msg_count else 0
        row["total_calls"] = call_count["c"] if call_count else 0
    return {"users": rows}


@router.get("/users/{phone}")
async def get_user_detail(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Full user record with aggregated stats."""
    _check_admin(x_admin_password)
    user = await db.fetch_one("SELECT * FROM users WHERE phone = ?", [phone])
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    msg_count = await db.fetch_one(
        "SELECT COUNT(*) as c FROM message_log WHERE user_id = ?", [phone]
    )
    call_count = await db.fetch_one(
        "SELECT COUNT(*) as c FROM call_log WHERE user_id = ?", [phone]
    )
    call_success = await db.fetch_one(
        "SELECT COUNT(*) as c FROM call_log WHERE user_id = ? AND status = 'success'",
        [phone],
    )

    return {
        **user,
        "total_messages": msg_count["c"] if msg_count else 0,
        "total_calls": call_count["c"] if call_count else 0,
        "successful_calls": call_success["c"] if call_success else 0,
    }


@router.get("/users/{phone}/profile")
async def get_user_profile(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return USER.md content for a user (legacy endpoint)."""
    _check_admin(x_admin_password)
    return await _read_user_md(phone, "USER.md", "profile", legacy="profile.md")


@router.get("/users/{phone}/user-model")
async def get_user_model(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return USER.md content for a user."""
    _check_admin(x_admin_password)
    return await _read_user_md(phone, "USER.md", "content", legacy="profile.md")


@router.get("/users/{phone}/soul")
async def get_user_soul(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return SOUL.md content for a user (agent's self-model)."""
    _check_admin(x_admin_password)
    return await _read_user_md(phone, "SOUL.md", "content")


@router.get("/users/{phone}/playbook")
async def get_user_playbook(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return AGENTS.md content for a user (operational playbook)."""
    _check_admin(x_admin_password)
    return await _read_user_md(phone, "AGENTS.md", "content")


@router.get("/users/{phone}/memory")
async def get_user_memory(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return MEMORY.md content for a user."""
    _check_admin(x_admin_password)
    return await _read_user_md(phone, "MEMORY.md", "memory")


async def _read_user_md(
    phone: str, filename: str, key: str, legacy: str | None = None
) -> dict:
    """Read a markdown file from a user's data directory."""
    user_dir = USER_DATA_DIR / phone
    target = user_dir / filename

    content = ""
    try:
        if target.exists():
            content = target.read_text()
        elif legacy and (user_dir / legacy).exists():
            content = (user_dir / legacy).read_text()
    except Exception:
        logger.exception("Failed to read %s for %s", filename, phone)

    return {"phone": phone, key: content}


@router.get("/users/{phone}/conversations")
async def get_user_conversations(
    phone: str,
    limit: int = Query(100, ge=1, le=1000),
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return conversation history (from JSONL + message_log)."""
    _check_admin(x_admin_password)

    # Load from JSONL file
    user_dir = USER_DATA_DIR / phone
    convos_path = user_dir / "conversations.jsonl"
    messages: list[dict] = []
    try:
        if convos_path.exists():
            for line in convos_path.read_text().strip().split("\n"):
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        logger.exception("Failed to read conversations for %s", phone)

    return {"phone": phone, "conversations": messages[-limit:]}


@router.get("/users/{phone}/conversations/text")
async def get_user_conversations_text(
    phone: str,
    limit: int = Query(200, ge=1, le=2000),
    x_admin_password: Optional[str] = Header(None),
) -> Response:
    """Conversation transcript with a copy-to-clipboard button.

    Includes SMS messages and call results in chronological order.
    Serves an HTML page with the transcript and a copy button.
    """
    _check_admin(x_admin_password)

    user = await db.fetch_one("SELECT name, phone FROM users WHERE phone = ?", [phone])
    name = user["name"] if user else phone

    # Get messages from DB
    messages = await db.fetch_all(
        "SELECT direction, body, created_at FROM message_log WHERE user_id = ? ORDER BY created_at ASC LIMIT ?",
        [phone, limit],
    )

    # Get calls interleaved
    calls = await db.fetch_all(
        "SELECT business_name, task, status, result, created_at, duration_seconds FROM call_log WHERE user_id = ? ORDER BY created_at ASC",
        [phone],
    )

    # Merge into a single timeline
    events: list[tuple[str, str]] = []
    for msg in messages:
        ts = msg["created_at"] or ""
        if msg["direction"] == "in":
            events.append((ts, f"[{ts}] {name}: {msg['body']}"))
        else:
            events.append((ts, f"[{ts}] Hold Plz: {msg['body']}"))

    for call in calls:
        ts = call["created_at"] or ""
        status = call["status"] or "unknown"
        dur = f" ({call['duration_seconds']}s)" if call.get("duration_seconds") else ""
        line = f"[{ts}] --- Call to {call['business_name']}: {status}{dur}"
        if call.get("result"):
            line += f"\n         Result: {call['result']}"
        events.append((ts, line))

    events.sort(key=lambda e: e[0])

    header = f"=== Hold Plz conversation with {name} ({phone}) ==="
    transcript = header + "\n" + "\n".join(e[1] for e in events)

    # Escape for HTML embedding
    import html
    escaped = html.escape(transcript)

    page = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Transcript: {html.escape(name)} ({html.escape(phone)})</title>
<style>
  body {{ font-family: monospace; margin: 2rem; background: #1a1a1a; color: #e0e0e0; }}
  #transcript {{ white-space: pre-wrap; padding: 1rem; background: #111; border-radius: 8px;
                 border: 1px solid #333; max-height: 80vh; overflow-y: auto; }}
  button {{ position: fixed; top: 1rem; right: 1rem; padding: 0.6rem 1.2rem;
           font-size: 14px; font-family: monospace; cursor: pointer;
           background: #2563eb; color: white; border: none; border-radius: 6px; }}
  button:hover {{ background: #1d4ed8; }}
  button.copied {{ background: #16a34a; }}
</style>
</head><body>
<button onclick="copyTranscript()">Copy</button>
<div id="transcript">{escaped}</div>
<script>
function copyTranscript() {{
  const text = document.getElementById('transcript').innerText;
  navigator.clipboard.writeText(text).then(() => {{
    const btn = document.querySelector('button');
    btn.textContent = 'Copied';
    btn.classList.add('copied');
    setTimeout(() => {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
  }});
}}
</script>
</body></html>"""

    return Response(content=page, media_type="text/html; charset=utf-8")


@router.get("/users/{phone}/conversations/businesses")
async def get_user_conversations_by_business(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Conversations grouped by business name."""
    _check_admin(x_admin_password)

    # Get all business names from call_log for this user
    call_records = await db.fetch_all(
        """SELECT id, business_name, business_phone, place_id, task, task_type,
                  status, result, created_at, duration_seconds
           FROM call_log WHERE user_id = ? ORDER BY created_at""",
        [phone],
    )
    business_names = {r["business_name"].lower(): r["business_name"] for r in call_records if r.get("business_name")}

    # Load conversations
    user_dir = USER_DATA_DIR / phone
    convos_path = user_dir / "conversations.jsonl"
    messages: list[dict] = []
    try:
        if convos_path.exists():
            for line in convos_path.read_text().strip().split("\n"):
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass

    # Group messages by business
    grouped: dict[str, dict] = {}
    general: list[dict] = []

    for msg in messages:
        text = msg.get("text", "").lower()
        matched_business = None
        for biz_lower, biz_name in business_names.items():
            if biz_lower in text:
                matched_business = biz_name
                break

        # Also check metadata for business references
        if not matched_business and msg.get("business"):
            matched_business = msg["business"]

        if matched_business:
            if matched_business not in grouped:
                grouped[matched_business] = {
                    "business_name": matched_business,
                    "messages": [],
                    "calls": [],
                }
            grouped[matched_business]["messages"].append(msg)
        else:
            general.append(msg)

    # Attach call records to their business groups
    for record in call_records:
        biz = record.get("business_name", "")
        if biz in grouped:
            grouped[biz]["calls"].append(record)
        elif biz:
            grouped[biz] = {
                "business_name": biz,
                "messages": [],
                "calls": [record],
            }

    return {
        "phone": phone,
        "businesses": list(grouped.values()),
        "general": general,
    }


@router.get("/users/{phone}/calls")
async def get_user_calls(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """All call_log entries for a user."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        "SELECT * FROM call_log WHERE user_id = ? ORDER BY created_at DESC",
        [phone],
    )
    return {"phone": phone, "calls": rows}


@router.get("/users/{phone}/calls/{call_id}/transcript")
async def get_call_transcript(
    phone: str,
    call_id: int,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Single call transcript on demand."""
    _check_admin(x_admin_password)
    record = await db.fetch_one(
        "SELECT id, vapi_call_id, business_name, transcript, result, status, duration_seconds, created_at FROM call_log WHERE id = ? AND user_id = ?",
        [call_id, phone],
    )
    if not record:
        raise HTTPException(status_code=404, detail="call not found")
    return record


class AllowlistToggle(BaseModel):
    allowlisted: bool


@router.post("/users/{phone}/allowlist")
async def toggle_allowlist(
    phone: str,
    body: AllowlistToggle,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Toggle allowlist status for a user."""
    _check_admin(x_admin_password)
    await db.execute(
        "UPDATE users SET allowlisted = ? WHERE phone = ?",
        [body.allowlisted, phone],
    )
    return {"status": "ok", "phone": phone, "allowlisted": body.allowlisted}


@router.delete("/users/{phone}")
async def delete_user(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Permanently delete a user and all associated data."""
    _check_admin(x_admin_password)
    user = await db.fetch_one("SELECT * FROM users WHERE phone = ?", [phone])
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    # Delete in FK order: junction tables first, then leaf tables, then user
    await db.execute(
        "DELETE FROM request_messages WHERE message_log_id IN (SELECT id FROM message_log WHERE user_id = ?)",
        [phone],
    )
    await db.execute(
        "DELETE FROM requests WHERE session_id IN (SELECT id FROM sessions WHERE user_id = ?)",
        [phone],
    )
    await db.execute("DELETE FROM sessions WHERE user_id = ?", [phone])
    await db.execute("DELETE FROM message_log WHERE user_id = ?", [phone])
    await db.execute("DELETE FROM call_log WHERE user_id = ?", [phone])
    await db.execute("DELETE FROM scheduled_tasks WHERE user_id = ?", [phone])
    await db.execute("DELETE FROM users WHERE id = ?", [phone])

    user_dir = USER_DATA_DIR / phone
    if user_dir.exists():
        shutil.rmtree(user_dir)

    return {"status": "ok", "phone": phone, "deleted": True}


@router.post("/users/{phone}/reset")
async def reset_user(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Wipe user data but keep the account record."""
    _check_admin(x_admin_password)
    user = await db.fetch_one("SELECT * FROM users WHERE phone = ?", [phone])
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    await db.execute("DELETE FROM message_log WHERE user_id = ?", [phone])
    await db.execute("DELETE FROM call_log WHERE user_id = ?", [phone])
    await db.execute("DELETE FROM scheduled_tasks WHERE user_id = ?", [phone])
    await db.execute(
        "UPDATE users SET free_messages_used = 0, calls_used_this_period = 0 WHERE id = ?",
        [phone],
    )

    user_dir = USER_DATA_DIR / phone
    if user_dir.exists():
        shutil.rmtree(user_dir)

    return {"status": "ok", "phone": phone, "reset": True}


VALID_TIERS = {"free", "active", "trial", "canceled", "past_due", "pending_consent"}
VALID_CONSENT_STATES = {"fresh", "confirmed", "declined"}


class SetConsentRequest(BaseModel):
    state: str


@router.post("/users/{phone}/consent")
async def set_consent_state(
    phone: str,
    body: SetConsentRequest,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Set a user's consent_state directly."""
    _check_admin(x_admin_password)
    if body.state not in VALID_CONSENT_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"invalid state '{body.state}', must be one of: {', '.join(sorted(VALID_CONSENT_STATES))}",
        )
    user = await db.fetch_one("SELECT * FROM users WHERE phone = ?", [phone])
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    await db.execute(
        "UPDATE users SET consent_state = ?, consent_sent_at = NULL, consent_confirmed_at = NULL WHERE phone = ?",
        [body.state, phone],
    )
    return {"status": "ok", "phone": phone, "consent_state": body.state}


class SetTierRequest(BaseModel):
    tier: str


@router.post("/users/{phone}/tier")
async def set_user_tier(
    phone: str,
    body: SetTierRequest,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Set a user's subscription_status directly."""
    _check_admin(x_admin_password)
    if body.tier not in VALID_TIERS:
        raise HTTPException(
            status_code=400,
            detail=f"invalid tier '{body.tier}', must be one of: {', '.join(sorted(VALID_TIERS))}",
        )
    user = await db.fetch_one("SELECT * FROM users WHERE phone = ?", [phone])
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    await db.execute(
        "UPDATE users SET subscription_status = ? WHERE phone = ?",
        [body.tier, phone],
    )
    return {"status": "ok", "phone": phone, "tier": body.tier}


@router.post("/users/{phone}/memory/distill")
async def trigger_distill(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Trigger distill_memory() for a user (LLM call, may take 10-30s)."""
    _check_admin(x_admin_password)
    await distill_memory(phone)
    return {"status": "ok", "phone": phone, "action": "distill_memory"}


@router.post("/users/{phone}/memory/reflect")
async def trigger_reflect(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Trigger reflect() for a user (multiple LLM calls, may take 30-60s)."""
    _check_admin(x_admin_password)
    await reflect(phone)
    return {"status": "ok", "phone": phone, "action": "reflect"}


# ---- Sessions & Requests ----

@router.get("/sessions")
async def list_sessions(
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """List sessions, optionally filtered by user."""
    _check_admin(x_admin_password)
    if user_id:
        rows = await db.fetch_all(
            """SELECT s.*, COUNT(r.id) as request_count
               FROM sessions s LEFT JOIN requests r ON r.session_id = s.id
               WHERE s.user_id = ?
               GROUP BY s.id ORDER BY s.last_activity_at DESC LIMIT ?""",
            [user_id, limit],
        )
    else:
        rows = await db.fetch_all(
            """SELECT s.*, COUNT(r.id) as request_count
               FROM sessions s LEFT JOIN requests r ON r.session_id = s.id
               GROUP BY s.id ORDER BY s.last_activity_at DESC LIMIT ?""",
            [limit],
        )
    return {"sessions": rows}


@router.get("/sessions/{session_id}")
async def get_session_detail(
    session_id: int,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Session detail with all requests, linked messages, and calls."""
    _check_admin(x_admin_password)
    session = await db.fetch_one(
        "SELECT * FROM sessions WHERE id = ?", [session_id]
    )
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    requests = await db.fetch_all(
        "SELECT * FROM requests WHERE session_id = ? ORDER BY created_at DESC",
        [session_id],
    )

    # Attach messages and calls to each request
    for req in requests:
        messages = await db.fetch_all(
            """SELECT m.* FROM message_log m
               JOIN request_messages rm ON rm.message_log_id = m.id
               WHERE rm.request_id = ? ORDER BY m.created_at""",
            [req["id"]],
        )
        req["messages"] = messages

        calls = await db.fetch_all(
            "SELECT * FROM call_log WHERE request_id = ? ORDER BY created_at",
            [req["id"]],
        )
        req["calls"] = calls

    return {"session": session, "requests": requests}


@router.get("/users/{phone}/sessions")
async def get_user_sessions(
    phone: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """All sessions for a user."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        """SELECT s.*, COUNT(r.id) as request_count
           FROM sessions s LEFT JOIN requests r ON r.session_id = s.id
           WHERE s.user_id = ?
           GROUP BY s.id ORDER BY s.last_activity_at DESC""",
        [phone],
    )
    return {"phone": phone, "sessions": rows}


@router.get("/requests")
async def list_requests(
    status: Optional[str] = Query(None),
    billable: Optional[bool] = Query(None),
    charged: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """List requests with optional filters."""
    _check_admin(x_admin_password)
    conditions = []
    params: list = []
    if status:
        conditions.append("r.status = ?")
        params.append(status)
    if billable is not None:
        conditions.append("r.billable = ?")
        params.append(billable)
    if charged is not None:
        conditions.append("r.charged = ?")
        params.append(charged)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.fetch_all(
        f"""SELECT r.*, s.user_id, s.business_name as session_business
            FROM requests r JOIN sessions s ON r.session_id = s.id
            {where} ORDER BY r.created_at DESC LIMIT ?""",
        params + [limit],
    )
    return {"requests": rows}


# ---- Request Taxonomy ----

@router.get("/taxonomy")
async def get_taxonomy(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """The living request taxonomy with counts and examples."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        "SELECT * FROM request_categories ORDER BY count DESC"
    )
    # Parse example_summaries JSON
    for row in rows:
        try:
            row["example_summaries"] = json.loads(row.get("example_summaries") or "[]")
        except (json.JSONDecodeError, TypeError):
            row["example_summaries"] = []
    return {"categories": rows}


# ---- SMS ----

class SendSmsRequest(BaseModel):
    to: str
    body: str


@router.post("/sms/send")
async def admin_send_sms(
    body: SendSmsRequest,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Send an SMS via Twilio (test/debug)."""
    _check_admin(x_admin_password)
    segments = calculate_segments(body.body)
    await send_sms(body.to, body.body)
    return {"status": "ok", "to": body.to, "segments": segments}


# ---- Messages ----

@router.get("/messages")
async def list_messages(
    user_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Query message_log with optional filters."""
    _check_admin(x_admin_password)
    if user_id:
        rows = await db.fetch_all(
            "SELECT * FROM message_log WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            [user_id, limit],
        )
    else:
        rows = await db.fetch_all(
            "SELECT * FROM message_log ORDER BY created_at DESC LIMIT ?",
            [limit],
        )
    return {"messages": rows}


# ---- Business Intelligence ----

@router.get("/businesses")
async def list_businesses(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """List all business profiles with stats."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        "SELECT * FROM business_profiles ORDER BY last_updated DESC"
    )
    return {"businesses": rows}


@router.get("/businesses/{place_id}")
async def get_business_detail(
    place_id: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Full business profile with facts and phone scores."""
    _check_admin(x_admin_password)

    profile = await db.fetch_one(
        "SELECT * FROM business_profiles WHERE place_id = ?", [place_id]
    )
    if not profile:
        raise HTTPException(status_code=404, detail="business not found")

    facts = await db.fetch_all(
        "SELECT * FROM business_facts WHERE place_id = ? ORDER BY verified_at DESC",
        [place_id],
    )
    scores = await db.fetch_all(
        "SELECT * FROM phone_scores WHERE place_id = ?", [place_id]
    )
    ivr_maps = await db.fetch_all(
        "SELECT * FROM ivr_maps WHERE place_id = ?", [place_id]
    )

    return {
        "profile": profile,
        "facts": facts,
        "phone_scores": scores,
        "ivr_maps": ivr_maps,
    }


@router.get("/businesses/{place_id}/calls")
async def get_business_calls(
    place_id: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """All calls to a specific business."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all(
        "SELECT * FROM call_log WHERE place_id = ? ORDER BY created_at DESC",
        [place_id],
    )
    return {"place_id": place_id, "calls": rows}


@router.get("/businesses/{place_id}/sessions")
async def get_business_sessions(
    place_id: str,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """All sessions across all users for a business (business-eye view)."""
    _check_admin(x_admin_password)

    sessions = await db.fetch_all(
        """SELECT s.*, u.name as user_name, u.phone as user_phone,
                  COUNT(r.id) as request_count,
                  SUM(CASE WHEN r.status = 'resolved' THEN 1 ELSE 0 END) as resolved_count,
                  SUM(CASE WHEN r.status = 'failed' THEN 1 ELSE 0 END) as failed_count
           FROM sessions s
           JOIN users u ON s.user_id = u.id
           LEFT JOIN requests r ON r.session_id = s.id
           WHERE s.place_id = ?
           GROUP BY s.id ORDER BY s.last_activity_at DESC""",
        [place_id],
    )

    # Also get aggregate call stats for this business
    call_stats = await db.fetch_one(
        """SELECT COUNT(*) as total_calls,
                  SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_calls,
                  AVG(duration_seconds) as avg_duration
           FROM call_log WHERE place_id = ?""",
        [place_id],
    )

    return {
        "place_id": place_id,
        "sessions": sessions,
        "call_stats": call_stats,
    }


class DoNotCallToggle(BaseModel):
    do_not_call: bool
    reason: Optional[str] = None


@router.post("/businesses/{place_id}/do-not-call")
async def toggle_do_not_call(
    place_id: str,
    body: DoNotCallToggle,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Toggle do-not-call flag for a business."""
    _check_admin(x_admin_password)

    profile = await db.fetch_one(
        "SELECT * FROM business_profiles WHERE place_id = ?", [place_id]
    )
    if not profile:
        raise HTTPException(status_code=404, detail="business profile not found")

    await db.execute(
        "UPDATE business_profiles SET do_not_call = ?, do_not_call_reason = ?, last_updated = CURRENT_TIMESTAMP WHERE place_id = ?",
        [body.do_not_call, body.reason, place_id],
    )
    return {
        "status": "ok",
        "place_id": place_id,
        "do_not_call": body.do_not_call,
        "reason": body.reason,
    }


# ---- Failure Tracking ----

@router.get("/failures")
async def list_failures(
    failure_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Failure log with optional filters."""
    _check_admin(x_admin_password)

    conditions = []
    params: list = []
    if failure_type:
        conditions.append("failure_type = ?")
        params.append(failure_type)
    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if resolved is not None:
        conditions.append("resolved = ?")
        params.append(resolved)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.fetch_all(
        f"SELECT * FROM failure_log {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    )
    return {"failures": rows}


@router.get("/failures/summary")
async def failures_summary(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Aggregated failure stats."""
    _check_admin(x_admin_password)

    total = await db.fetch_one(
        "SELECT COUNT(*) as c FROM failure_log WHERE created_at > datetime('now', '-7 days')"
    )
    by_type = await db.fetch_all(
        """SELECT failure_type, COUNT(*) as count
           FROM failure_log WHERE created_at > datetime('now', '-7 days')
           GROUP BY failure_type ORDER BY count DESC"""
    )
    by_severity = await db.fetch_all(
        """SELECT severity, COUNT(*) as count
           FROM failure_log WHERE created_at > datetime('now', '-7 days')
           GROUP BY severity ORDER BY count DESC"""
    )
    top_businesses = await db.fetch_all(
        """SELECT business_name, COUNT(*) as count
           FROM failure_log WHERE created_at > datetime('now', '-7 days')
           AND business_name IS NOT NULL
           GROUP BY business_name ORDER BY count DESC LIMIT 5"""
    )
    unresolved = await db.fetch_one(
        "SELECT COUNT(*) as c FROM failure_log WHERE resolved = FALSE"
    )

    return {
        "total_this_week": total["c"] if total else 0,
        "by_type": by_type,
        "by_severity": by_severity,
        "top_failing_businesses": top_businesses,
        "unresolved": unresolved["c"] if unresolved else 0,
    }


class ResolveFailure(BaseModel):
    notes: str = ""


@router.post("/failures/{failure_id}/resolve")
async def resolve_failure(
    failure_id: int,
    body: ResolveFailure,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Mark a failure as resolved with optional notes."""
    _check_admin(x_admin_password)
    await db.execute(
        "UPDATE failure_log SET resolved = TRUE, resolution_notes = ? WHERE id = ?",
        [body.notes, failure_id],
    )
    return {"status": "ok", "failure_id": failure_id}


# ---- Settings ----

class SignupsToggle(BaseModel):
    enabled: bool


@router.post("/settings/signups")
async def toggle_signups(
    body: SignupsToggle,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Toggle signups_enabled setting (runtime, stored in DB)."""
    _check_admin(x_admin_password)
    await set_signups_enabled(body.enabled)
    return {"status": "ok", "signups_enabled": body.enabled}


@router.get("/settings/signups")
async def get_signups_status(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Get current signups_enabled status."""
    _check_admin(x_admin_password)
    enabled = await get_signups_enabled()
    return {"signups_enabled": enabled}


class TestModeToggle(BaseModel):
    enabled: bool


@router.get("/settings/test-mode")
async def get_test_mode(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Get current test_mode status."""
    _check_admin(x_admin_password)
    row = await db.fetch_one(
        "SELECT value FROM app_settings WHERE key = 'test_mode'"
    )
    enabled = row["value"] == "true" if row else False
    return {"test_mode": enabled}


@router.post("/settings/test-mode")
async def toggle_test_mode(
    body: TestModeToggle,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Toggle test_mode setting."""
    _check_admin(x_admin_password)
    await db.execute(
        """INSERT INTO app_settings (key, value, updated_at)
           VALUES ('test_mode', ?, CURRENT_TIMESTAMP)
           ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP""",
        [str(body.enabled).lower()],
    )
    return {"status": "ok", "test_mode": body.enabled}


@router.get("/settings")
async def get_all_settings(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Dump all app_settings rows."""
    _check_admin(x_admin_password)
    rows = await db.fetch_all("SELECT * FROM app_settings ORDER BY key")
    return {"settings": rows}


# ---- Prompts Management ----

SOUL_MD_PATH = Path(__file__).parent.parent / "prompts" / "soul.md"


@router.get("/prompts/soul")
async def get_soul_prompt(
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return raw soul.md content."""
    _check_admin(x_admin_password)
    content = ""
    try:
        content = SOUL_MD_PATH.read_text()
    except Exception:
        logger.exception("Failed to read soul.md")
    return {"content": content}


class UpdateSoulRequest(BaseModel):
    content: str


@router.put("/prompts/soul")
async def update_soul_prompt(
    body: UpdateSoulRequest,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Overwrite soul.md and reload the cached version."""
    _check_admin(x_admin_password)
    try:
        SOUL_MD_PATH.write_text(body.content)
        from app.prompts.soul import reload
        reload()
    except Exception:
        logger.exception("Failed to write soul.md")
        raise HTTPException(status_code=500, detail="Failed to save soul.md")
    return {"status": "ok"}


@router.get("/prompts/system")
async def get_rendered_system_prompt(
    phone: str = Query(...),
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Return the fully rendered system prompt for a specific user."""
    _check_admin(x_admin_password)
    from app.services.auth import get_user
    from app.services.orchestrator import build_system_prompt

    user = await get_user(phone)
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    memory = await load_memory(phone)
    is_free = user.get("subscription_status") == "free"
    prompt = build_system_prompt(user, memory, is_free_tier=is_free)
    return {"phone": phone, "system_prompt": prompt}


# ---- Sandbox Chat ----

class SandboxRequest(BaseModel):
    phone: str
    message: str


@router.post("/sandbox")
async def sandbox_chat(
    body: SandboxRequest,
    x_admin_password: Optional[str] = Header(None),
) -> dict:
    """Chat as a user without storing anything. Dry-run orchestrator."""
    _check_admin(x_admin_password)
    from app.services.orchestrator import handle_message

    response = await handle_message(body.phone, body.message, dry_run=True)
    return {"phone": body.phone, "response": response}
