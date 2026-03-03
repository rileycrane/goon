"use client";

import { useState } from "react";
import { adminFetch } from "./api";

const STATUS_COLORS: Record<string, string> = {
  success: "#27ae60",
  in_progress: "var(--accent)",
  retry_pending: "#f39c12",
};

export default function CallCard({
  call,
  userPhone,
}: {
  call: any;
  userPhone?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [transcript, setTranscript] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const statusColor =
    STATUS_COLORS[call.status] ||
    (call.status?.startsWith("failed") ? "#e74c3c" : "var(--text-muted)");

  const loadTranscript = async () => {
    if (transcript !== null) {
      setExpanded(!expanded);
      return;
    }
    setLoading(true);
    try {
      const phone = userPhone || call.user_id;
      const data = await adminFetch(
        `/admin/users/${encodeURIComponent(phone)}/calls/${call.id}/transcript`
      );
      setTranscript(data.transcript || "(no transcript)");
      setExpanded(true);
    } catch {
      setTranscript("(failed to load)");
      setExpanded(true);
    }
    setLoading(false);
  };

  return (
    <div
      style={{
        background: "var(--bg)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        padding: "12px 16px",
        marginBottom: "8px",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          cursor: "pointer",
        }}
        onClick={loadTranscript}
      >
        <div>
          <span style={{ fontWeight: 600, fontSize: "13px" }}>
            {call.business_name || "Unknown"}
          </span>
          <span
            style={{
              marginLeft: "8px",
              fontSize: "11px",
              padding: "2px 8px",
              borderRadius: "4px",
              background: statusColor + "22",
              color: statusColor,
              fontWeight: 500,
            }}
          >
            {call.status}
          </span>
        </div>
        <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          {call.created_at?.slice(0, 16)}
          {call.duration_seconds != null && ` (${call.duration_seconds}s)`}
        </div>
      </div>

      {call.task && (
        <div
          style={{
            fontSize: "12px",
            color: "var(--text-muted)",
            marginTop: "4px",
          }}
        >
          {call.task}
        </div>
      )}

      {call.result && (
        <div
          style={{
            fontSize: "12px",
            color: "var(--text)",
            marginTop: "4px",
            fontStyle: "italic",
          }}
        >
          {call.result}
        </div>
      )}

      {expanded && transcript !== null && (
        <div
          style={{
            marginTop: "8px",
            padding: "10px 12px",
            background: "var(--card-bg)",
            borderRadius: "6px",
            fontSize: "12px",
            lineHeight: "1.5",
            color: "var(--text)",
            maxHeight: "300px",
            overflow: "auto",
            whiteSpace: "pre-wrap",
          }}
        >
          {transcript}
        </div>
      )}

      {loading && (
        <div
          style={{
            marginTop: "6px",
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          Loading transcript...
        </div>
      )}
    </div>
  );
}
