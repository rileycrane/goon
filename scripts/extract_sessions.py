#!/usr/bin/env python3
"""
Extract salient back-and-forths from Claude Code session JSONL files.

Reads all session logs from ~/.claude/projects/, extracts user requests and
assistant text responses (skipping tool calls, tool results, and thinking
blocks), and writes a clean JSON log.

Usage:
    # All projects (default output: ~/.claude/session-history.json)
    python3 scripts/extract_sessions.py

    # Specific project only
    python3 scripts/extract_sessions.py --project goon-mayor-rig

    # Custom output path
    python3 scripts/extract_sessions.py -o docs/session-log.json

    # Markdown output instead of JSON
    python3 scripts/extract_sessions.py --format md -o docs/session-log.md

    # Filter by date range
    python3 scripts/extract_sessions.py --since 2026-03-01 --until 2026-03-04
"""

import json
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional


CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
DEFAULT_OUTPUT = CLAUDE_DIR / "session-history.json"


def extract_text_from_content(content) -> str:
    """Pull plain text from a message's content field."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                t = block.get("text", "").strip()
                if t:
                    texts.append(t)
        return "\n\n".join(texts)
    return ""


def is_tool_result_only(content) -> bool:
    """Check if a user message is purely tool results (no human text)."""
    if isinstance(content, str):
        return False
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "tool_result":
                    continue
                if block.get("type") == "text":
                    return False
                # Other types — treat as non-tool-result
                return False
            elif isinstance(block, str):
                return False
        return True  # all blocks were tool_result
    return False


def extract_session(jsonl_path: Path, since: Optional[datetime] = None,
                    until: Optional[datetime] = None) -> dict:
    """Extract exchanges from one session JSONL file."""
    session_id = jsonl_path.stem
    project_dir = jsonl_path.parent.name
    # Derive a readable project name
    project_name = project_dir.replace("-Users-rileycrane-", "").replace("-", "/")

    exchanges = []
    session_start = None
    session_end = None

    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type")
            if msg_type not in ("user", "assistant"):
                continue

            ts_str = obj.get("timestamp")
            ts = None
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            # Track session time range
            if ts:
                if session_start is None or ts < session_start:
                    session_start = ts
                if session_end is None or ts > session_end:
                    session_end = ts

            # Date filtering
            if since and ts and ts < since:
                continue
            if until and ts and ts > until:
                continue

            message = obj.get("message", {})
            content = message.get("content", "")

            # Skip sidechain messages (subagent internals)
            if obj.get("isSidechain"):
                continue

            # Skip parent tool use contexts (subagent calls)
            if obj.get("parentToolUseID"):
                continue

            if msg_type == "user":
                # Skip tool results — these are just Claude getting tool output back
                if is_tool_result_only(content):
                    continue
                text = extract_text_from_content(content)
                if text:
                    exchanges.append({
                        "role": "user",
                        "text": text,
                        "timestamp": ts_str,
                    })

            elif msg_type == "assistant":
                text = extract_text_from_content(content)
                if text:
                    exchanges.append({
                        "role": "assistant",
                        "text": text,
                        "timestamp": ts_str,
                    })

    if not exchanges:
        return None

    return {
        "session_id": session_id,
        "project": project_name,
        "started": session_start.isoformat() if session_start else None,
        "ended": session_end.isoformat() if session_end else None,
        "exchange_count": len(exchanges),
        "exchanges": exchanges,
    }


def format_markdown(sessions: list[dict]) -> str:
    """Render sessions as readable markdown."""
    lines = ["# Claude Code Session History\n"]
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n")
    lines.append(f"Sessions: {len(sessions)}\n")

    for sess in sessions:
        started = sess["started"][:16].replace("T", " ") if sess["started"] else "unknown"
        lines.append(f"\n---\n\n## {sess['project']} — {started}\n")
        lines.append(f"Session: `{sess['session_id']}`  ")
        lines.append(f"Exchanges: {sess['exchange_count']}\n")

        for ex in sess["exchanges"]:
            role_label = "**You**" if ex["role"] == "user" else "**Claude**"
            ts = ""
            if ex.get("timestamp"):
                ts = f" _{ex['timestamp'][:16].replace('T', ' ')}_"
            lines.append(f"\n### {role_label}{ts}\n")
            lines.append(ex["text"] + "\n")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract Claude Code session history")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output file path (default: ~/.claude/session-history.json)")
    parser.add_argument("--project", type=str, default=None,
                        help="Filter to project name substring (e.g. 'goon-mayor')")
    parser.add_argument("--format", choices=["json", "md"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--since", type=str, default=None,
                        help="Only include exchanges after this date (YYYY-MM-DD)")
    parser.add_argument("--until", type=str, default=None,
                        help="Only include exchanges before this date (YYYY-MM-DD)")
    parser.add_argument("--compact", action="store_true",
                        help="Compact JSON output (no indentation)")
    args = parser.parse_args()

    since = None
    until = None
    if args.since:
        since = datetime.fromisoformat(args.since + "T00:00:00+00:00")
    if args.until:
        until = datetime.fromisoformat(args.until + "T23:59:59+00:00")

    output_path = args.output
    if not output_path:
        ext = ".md" if args.format == "md" else ".json"
        output_path = str(CLAUDE_DIR / f"session-history{ext}")

    # Find all JSONL session files
    jsonl_files = []
    if not PROJECTS_DIR.exists():
        print("No Claude projects directory found.", file=sys.stderr)
        sys.exit(1)

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        if args.project and args.project not in project_dir.name:
            continue
        for f in sorted(project_dir.glob("*.jsonl")):
            jsonl_files.append(f)

    print(f"Found {len(jsonl_files)} session files across "
          f"{len(set(f.parent for f in jsonl_files))} projects", file=sys.stderr)

    sessions = []
    for jf in jsonl_files:
        result = extract_session(jf, since=since, until=until)
        if result:
            sessions.append(result)

    # Sort by start time
    sessions.sort(key=lambda s: s["started"] or "")

    total_exchanges = sum(s["exchange_count"] for s in sessions)
    print(f"Extracted {total_exchanges} exchanges from {len(sessions)} sessions",
          file=sys.stderr)

    # Write output
    if args.format == "md":
        content = format_markdown(sessions)
    else:
        indent = None if args.compact else 2
        content = json.dumps({
            "generated": datetime.now(timezone.utc).isoformat(),
            "session_count": len(sessions),
            "exchange_count": total_exchanges,
            "sessions": sessions,
        }, indent=indent, ensure_ascii=False)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(content)

    print(f"Written to {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
