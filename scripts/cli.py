#!/usr/bin/env python3
"""Hold Plz CLI — production management tool."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import click
import httpx
from dotenv import load_dotenv

# Load .env from repo root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_URL = os.getenv("HOLDPLZ_API_URL", os.getenv("BASE_URL", "http://localhost:8000"))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


def api(method: str, path: str, raw: bool = False, **kwargs) -> dict | str:
    """Sync admin API call with auth header."""
    headers = {"X-Admin-Password": ADMIN_PASSWORD}
    # URL-encode path segments (phone numbers have + which must be %2B)
    import urllib.parse
    parts = path.split("/")
    encoded_path = "/".join(urllib.parse.quote(p, safe="") for p in parts)
    url = f"{BASE_URL}/admin{encoded_path}"
    try:
        r = httpx.request(method, url, headers=headers, timeout=60, **kwargs)
        r.raise_for_status()
        if raw:
            return r.text
        return r.json()
    except httpx.ConnectError:
        click.echo(f"Error: could not connect to {BASE_URL}", err=True)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        try:
            detail = e.response.json().get("detail", e.response.text)
        except Exception:
            detail = e.response.text
        click.echo(f"Error {e.response.status_code}: {detail}", err=True)
        sys.exit(1)


def normalize_phone(raw: str) -> str:
    """Normalize phone to E.164 format."""
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if raw.startswith("+"):
        return raw
    return f"+{digits}"


def table(rows: list[dict], columns: list[str], headers: list[str] | None = None) -> None:
    """Print a simple aligned table."""
    if not rows:
        click.echo("(no results)")
        return
    headers = headers or columns
    widths = [len(h) for h in headers]
    str_rows = []
    for row in rows:
        vals = [str(row.get(c, "") or "") for c in columns]
        for i, v in enumerate(vals):
            widths[i] = max(widths[i], len(v))
        str_rows.append(vals)

    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    click.echo(fmt.format(*headers))
    click.echo(fmt.format(*["-" * w for w in widths]))
    for vals in str_rows:
        click.echo(fmt.format(*vals))


# ---- Root ----

@click.group()
def cli():
    """Hold Plz CLI — production management tool."""
    pass


# ---- status ----

@cli.command()
def status():
    """System dashboard."""
    data = api("GET", "/stats")

    u = data["users"]
    c = data["calls"]
    m = data["messages"]

    click.echo("=== Hold Plz Status ===\n")
    click.echo(f"Users:      {u['total']} total  ({u['active']} active, {u['free']} free)")
    click.echo(f"Calls:      {c['total']} total  ({c['success']} ok, {c['failed']} failed)")
    click.echo(f"Messages:   {m['last_24h']} (24h)  {m['last_7d']} (7d)")
    click.echo(f"Failures:   {data['failures_active']} unresolved")


# ---- health ----

@cli.command()
def health():
    """Quick connectivity check."""
    data = api("GET", "/")
    if data.get("status") == "ok":
        click.echo("OK")
    else:
        click.echo(f"Unexpected: {data}")


# ---- user ----

@cli.group()
def user():
    """User management commands."""
    pass


@user.command("ls")
def user_ls():
    """List all users."""
    data = api("GET", "/users")
    table(
        data["users"],
        ["phone", "name", "subscription_status", "allowlisted", "total_messages", "total_calls", "created_at"],
        ["PHONE", "NAME", "TIER", "ALLOW", "MSGS", "CALLS", "CREATED"],
    )


@user.command("show")
@click.argument("phone")
def user_show(phone: str):
    """Full user detail."""
    phone = normalize_phone(phone)
    data = api("GET", f"/users/{phone}")
    for key, val in data.items():
        click.echo(f"  {key:30s}  {val}")


@user.command("seed")
@click.argument("phone")
@click.option("--name", default=None, help="User display name")
def user_seed(phone: str, name: str | None):
    """Create or update an allowlisted user."""
    phone = normalize_phone(phone)
    body = {"phone": phone, "allowlisted": True}
    if name:
        body["name"] = name
    data = api("POST", "/seed-user", json=body)
    click.echo(f"Seeded {data['phone']} (name={data.get('name')})")


@user.command("delete")
@click.argument("phone")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def user_delete(phone: str, yes: bool):
    """Permanently delete a user and all data."""
    phone = normalize_phone(phone)
    if not yes:
        click.confirm(f"Delete {phone} and ALL associated data?", abort=True)
    data = api("DELETE", f"/users/{phone}")
    click.echo(f"Deleted {data['phone']}")


@user.command("reset")
@click.argument("phone")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def user_reset(phone: str, yes: bool):
    """Wipe data but keep account record."""
    phone = normalize_phone(phone)
    if not yes:
        click.confirm(f"Reset all data for {phone}? (account record kept)", abort=True)
    data = api("POST", f"/users/{phone}/reset")
    click.echo(f"Reset {data['phone']}")


@user.command("allowlist")
@click.argument("phone")
@click.option("--on/--off", default=True)
def user_allowlist(phone: str, on: bool):
    """Toggle allowlist status."""
    phone = normalize_phone(phone)
    data = api("POST", f"/users/{phone}/allowlist", json={"allowlisted": on})
    click.echo(f"{data['phone']} allowlisted={data['allowlisted']}")


@user.command("tier")
@click.argument("phone")
@click.argument("tier")
def user_tier(phone: str, tier: str):
    """Set subscription_status."""
    phone = normalize_phone(phone)
    data = api("POST", f"/users/{phone}/tier", json={"tier": tier})
    click.echo(f"{data['phone']} tier={data['tier']}")


@user.command("consent")
@click.argument("phone")
@click.argument("state", type=click.Choice(["fresh", "confirmed", "declined"]))
def user_consent(phone: str, state: str):
    """Set consent_state (fresh = re-trigger signup flow)."""
    phone = normalize_phone(phone)
    data = api("POST", f"/users/{phone}/consent", json={"state": state})
    click.echo(f"{data['phone']} consent_state={data['consent_state']}")


# ---- memory ----

@cli.group()
@click.argument("phone")
@click.pass_context
def memory(ctx, phone: str):
    """Memory inspection for a user."""
    ctx.ensure_object(dict)
    ctx.obj["phone"] = normalize_phone(phone)


@memory.command("show")
@click.pass_context
def memory_show(ctx):
    """Show all 4 memory files."""
    phone = ctx.obj["phone"]
    for label, endpoint, key in [
        ("SOUL.md", "soul", "content"),
        ("USER.md", "user-model", "content"),
        ("MEMORY.md", "memory", "memory"),
        ("AGENTS.md", "playbook", "content"),
    ]:
        data = api("GET", f"/users/{phone}/{endpoint}")
        content = data.get(key, "")
        click.echo(f"\n{'=' * 40}")
        click.echo(f"  {label}")
        click.echo(f"{'=' * 40}")
        click.echo(content if content else "(empty)")


@memory.command("soul")
@click.pass_context
def memory_soul(ctx):
    """SOUL.md only."""
    phone = ctx.obj["phone"]
    data = api("GET", f"/users/{phone}/soul")
    click.echo(data.get("content", "(empty)"))


@memory.command("user-model")
@click.pass_context
def memory_user_model(ctx):
    """USER.md only."""
    phone = ctx.obj["phone"]
    data = api("GET", f"/users/{phone}/user-model")
    click.echo(data.get("content", "(empty)"))


@memory.command("long-term")
@click.pass_context
def memory_long_term(ctx):
    """MEMORY.md only."""
    phone = ctx.obj["phone"]
    data = api("GET", f"/users/{phone}/memory")
    click.echo(data.get("memory", "(empty)"))


@memory.command("playbook")
@click.pass_context
def memory_playbook(ctx):
    """AGENTS.md only."""
    phone = ctx.obj["phone"]
    data = api("GET", f"/users/{phone}/playbook")
    click.echo(data.get("content", "(empty)"))


@memory.command("conversations")
@click.option("--limit", "-n", default=100, help="Max entries")
@click.option("--by-business", is_flag=True, help="Group by business")
@click.pass_context
def memory_conversations(ctx, limit: int, by_business: bool):
    """Conversation history."""
    phone = ctx.obj["phone"]
    if by_business:
        data = api("GET", f"/users/{phone}/conversations/businesses")
        for biz in data.get("businesses", []):
            click.echo(f"\n--- {biz['business_name']} ---")
            for msg in biz["messages"]:
                ts = msg.get("timestamp", "")
                role = msg.get("role", "?")
                text = msg.get("text", "")
                click.echo(f"  [{ts}] {role}: {text[:120]}")
            for call in biz["calls"]:
                click.echo(f"  [CALL] {call.get('status', '')} - {call.get('result', '')}")
        general = data.get("general", [])
        if general:
            click.echo(f"\n--- General ({len(general)} messages) ---")
            for msg in general[-20:]:
                ts = msg.get("timestamp", "")
                role = msg.get("role", "?")
                text = msg.get("text", "")
                click.echo(f"  [{ts}] {role}: {text[:120]}")
    else:
        data = api("GET", f"/users/{phone}/conversations", params={"limit": limit})
        for msg in data.get("conversations", []):
            ts = msg.get("timestamp", "")
            role = msg.get("role", "?")
            text = msg.get("text", "")
            click.echo(f"[{ts}] {role}: {text[:200]}")


@memory.command("distill")
@click.pass_context
def memory_distill(ctx):
    """Trigger daily logs -> MEMORY.md distillation."""
    phone = ctx.obj["phone"]
    click.echo("Running distill_memory (may take 10-30s)...")
    data = api("POST", f"/users/{phone}/memory/distill")
    click.echo(f"Done: {data.get('action', 'ok')}")


@memory.command("reflect")
@click.pass_context
def memory_reflect(ctx):
    """Trigger full reflection (soul + playbook too)."""
    phone = ctx.obj["phone"]
    click.echo("Running reflect (may take 30-60s)...")
    data = api("POST", f"/users/{phone}/memory/reflect")
    click.echo(f"Done: {data.get('action', 'ok')}")


# ---- calls ----

@cli.group()
@click.argument("phone")
@click.pass_context
def calls(ctx, phone: str):
    """Call history for a user."""
    ctx.ensure_object(dict)
    ctx.obj["phone"] = normalize_phone(phone)


@calls.command("ls")
@click.pass_context
def calls_ls(ctx):
    """List calls."""
    phone = ctx.obj["phone"]
    data = api("GET", f"/users/{phone}/calls")
    table(
        data["calls"],
        ["id", "business_name", "business_phone", "status", "duration_seconds", "created_at"],
        ["ID", "BUSINESS", "PHONE", "STATUS", "DURATION", "CREATED"],
    )


@calls.command("transcript")
@click.argument("call_id", type=int)
@click.pass_context
def calls_transcript(ctx, call_id: int):
    """Show call transcript."""
    phone = ctx.obj["phone"]
    data = api("GET", f"/users/{phone}/calls/{call_id}/transcript")
    click.echo(f"Call #{data.get('id', call_id)} — {data.get('business_name', '?')}")
    click.echo(f"Status: {data.get('status', '?')}  Duration: {data.get('duration_seconds', '?')}s")
    click.echo(f"Result: {data.get('result', '(none)')}")
    click.echo(f"\n--- Transcript ---")
    click.echo(data.get("transcript", "(no transcript)"))


@calls.command("trigger")
@click.option("--business-name", "-b", required=True, help="Business name")
@click.option("--business-phone", "-p", required=True, help="Business phone number")
@click.option("--task", "-t", required=True, help="Task for the voice agent")
@click.option("--task-type", default="information",
              type=click.Choice(["information", "reservation", "appointment", "availability_check", "custom_request"]))
@click.option("--place-id", default=None, help="Google Places ID (optional)")
@click.pass_context
def calls_trigger(ctx, business_name: str, business_phone: str, task: str,
                  task_type: str, place_id: str | None):
    """Manually trigger an outbound call. Bypasses payment gate."""
    phone = ctx.obj["phone"]
    body = {
        "phone": phone,
        "business_name": business_name,
        "business_phone": business_phone,
        "task": task,
        "task_type": task_type,
    }
    if place_id:
        body["place_id"] = place_id
    data = api("POST", "/trigger-call", json=body)
    click.echo(f"Call triggered:")
    click.echo(f"  call_log_id:  {data.get('call_log_id')}")
    click.echo(f"  vapi_call_id: {data.get('vapi_call_id')}")
    click.echo(f"  status:       {data.get('call_status')}")


@calls.command("replay")
@click.argument("message")
@click.pass_context
def calls_replay(ctx, message: str):
    """Replay a message through the orchestrator (payment gate bypassed).

    Useful for re-triggering a request after payment.
    Example: cli.py calls +1234567890 replay "Call Riley's Pizza and make a reservation for 2 at 7pm"
    """
    phone = ctx.obj["phone"]
    data = api("POST", "/replay", json={"phone": phone, "message": message})
    click.echo(f"Response: {data.get('response')}")
    click.echo(f"SMS sent: {data.get('sms_sent')}")


# ---- biz ----

@cli.group()
def biz():
    """Business intelligence commands."""
    pass


@biz.command("ls")
def biz_ls():
    """List all businesses."""
    data = api("GET", "/businesses")
    table(
        data["businesses"],
        ["place_id", "business_name", "phone", "total_calls", "successful_calls", "last_updated"],
        ["PLACE_ID", "NAME", "PHONE", "CALLS", "OK", "UPDATED"],
    )


@biz.command("show")
@click.argument("place_id")
def biz_show(place_id: str):
    """Full business profile."""
    data = api("GET", f"/businesses/{place_id}")
    click.echo("=== Profile ===")
    for k, v in data.get("profile", {}).items():
        click.echo(f"  {k:30s}  {v}")
    facts = data.get("facts", [])
    if facts:
        click.echo(f"\n=== Facts ({len(facts)}) ===")
        for f in facts:
            click.echo(f"  [{f.get('fact_type', '')}] {f.get('answer', '')} (src={f.get('source', '')})")
    scores = data.get("phone_scores", [])
    if scores:
        click.echo(f"\n=== Phone Scores ({len(scores)}) ===")
        for s in scores:
            click.echo(
                f"  {s.get('phone', '')}  calls={s.get('call_count', 0)} "
                f"ok={s.get('success_count', 0)} last={s.get('last_outcome', '')}"
            )


@biz.command("calls")
@click.argument("place_id")
def biz_calls(place_id: str):
    """Calls to a business."""
    data = api("GET", f"/businesses/{place_id}/calls")
    table(
        data["calls"],
        ["id", "user_id", "task_type", "status", "duration_seconds", "created_at"],
        ["ID", "USER", "TYPE", "STATUS", "DURATION", "CREATED"],
    )


# ---- failures ----

@cli.group()
def failures():
    """Failure tracking commands."""
    pass


@failures.command("ls")
@click.option("--type", "-t", "failure_type", default=None, help="Filter by type")
@click.option("--severity", "-s", default=None, help="Filter by severity")
@click.option("--unresolved", is_flag=True, help="Only unresolved")
def failures_ls(failure_type: str | None, severity: str | None, unresolved: bool):
    """List failures."""
    params: dict = {}
    if failure_type:
        params["failure_type"] = failure_type
    if severity:
        params["severity"] = severity
    if unresolved:
        params["resolved"] = False
    data = api("GET", "/failures", params=params)
    table(
        data["failures"],
        ["id", "failure_type", "severity", "business_name", "resolved", "created_at"],
        ["ID", "TYPE", "SEV", "BUSINESS", "RESOLVED", "CREATED"],
    )


@failures.command("summary")
def failures_summary():
    """Aggregated failure stats."""
    data = api("GET", "/failures/summary")
    click.echo(f"Total this week:  {data['total_this_week']}")
    click.echo(f"Unresolved:       {data['unresolved']}")
    if data.get("by_type"):
        click.echo("\nBy type:")
        for row in data["by_type"]:
            click.echo(f"  {row['failure_type']:30s}  {row['count']}")
    if data.get("by_severity"):
        click.echo("\nBy severity:")
        for row in data["by_severity"]:
            click.echo(f"  {row['severity']:30s}  {row['count']}")
    if data.get("top_failing_businesses"):
        click.echo("\nTop failing businesses:")
        for row in data["top_failing_businesses"]:
            click.echo(f"  {row['business_name']:30s}  {row['count']}")


@failures.command("resolve")
@click.argument("failure_id", type=int)
@click.option("--notes", default="", help="Resolution notes")
def failures_resolve(failure_id: int, notes: str):
    """Mark a failure as resolved."""
    api("POST", f"/failures/{failure_id}/resolve", json={"notes": notes})
    click.echo(f"Resolved failure #{failure_id}")


# ---- messages ----

@cli.group()
def messages():
    """Message log commands."""
    pass


@messages.command("ls")
@click.option("--phone", default=None, help="Filter by user phone")
@click.option("--limit", "-n", default=50, help="Max entries")
def messages_ls(phone: str | None, limit: int):
    """List message_log entries."""
    params: dict = {"limit": limit}
    if phone:
        params["user_id"] = normalize_phone(phone)
    data = api("GET", "/messages", params=params)
    table(
        data["messages"],
        ["id", "user_id", "direction", "body", "created_at"],
        ["ID", "USER", "DIR", "BODY", "CREATED"],
    )


# ---- sms ----

@cli.group()
def sms():
    """SMS commands."""
    pass


@sms.command("send")
@click.argument("phone")
@click.argument("body")
def sms_send(phone: str, body: str):
    """Send a test SMS."""
    phone = normalize_phone(phone)
    data = api("POST", "/sms/send", json={"to": phone, "body": body})
    click.echo(f"Sent to {data['to']} ({data['segments']} segment(s))")


# ---- settings ----

@cli.group()
def settings():
    """App settings commands."""
    pass


@settings.command("show")
def settings_show():
    """Dump all app_settings."""
    data = api("GET", "/settings")
    rows = data.get("settings", [])
    if not rows:
        click.echo("(no settings)")
        return
    table(rows, ["key", "value", "updated_at"], ["KEY", "VALUE", "UPDATED"])


@settings.command("signups")
@click.option("--on/--off", default=None)
def settings_signups(on: bool | None):
    """Get or toggle signups."""
    if on is None:
        data = api("GET", "/settings/signups")
        click.echo(f"signups_enabled={data['signups_enabled']}")
    else:
        api("POST", "/settings/signups", json={"enabled": on})
        click.echo(f"signups_enabled={on}")


@settings.command("test-mode")
@click.option("--on/--off", default=None)
def settings_test_mode(on: bool | None):
    """Get or toggle test mode."""
    if on is None:
        data = api("GET", "/settings/test-mode")
        click.echo(f"test_mode={data['test_mode']}")
    else:
        api("POST", "/settings/test-mode", json={"enabled": on})
        click.echo(f"test_mode={on}")


if __name__ == "__main__":
    cli()
