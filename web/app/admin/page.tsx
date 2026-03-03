"use client";

import { useEffect, useState } from "react";
import { adminFetch } from "./components/api";
import StatsCard from "./components/StatsCard";

export default function AdminOverview() {
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    adminFetch("/admin/stats")
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  if (error)
    return <p style={{ color: "#e74c3c" }}>Error loading stats: {error}</p>;
  if (!stats)
    return <p style={{ color: "var(--text-muted)" }}>Loading...</p>;

  return (
    <div>
      <h1
        style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: "14px",
          color: "var(--accent)",
          marginBottom: "24px",
        }}
      >
        Dashboard
      </h1>

      <div
        style={{
          display: "flex",
          gap: "12px",
          flexWrap: "wrap",
          marginBottom: "32px",
        }}
      >
        <StatsCard
          label="Total Users"
          value={stats.users.total}
          sub={`${stats.users.free} free / ${stats.users.active} paid`}
        />
        <StatsCard
          label="Total Calls"
          value={stats.calls.total}
          sub={`${stats.calls.success} ok / ${stats.calls.failed} failed`}
        />
        <StatsCard label="Messages (24h)" value={stats.messages.last_24h} />
        <StatsCard label="Messages (7d)" value={stats.messages.last_7d} />
        <StatsCard label="Active Failures" value={stats.failures_active} />
      </div>

      <div style={{ display: "flex", gap: "24px", flexWrap: "wrap" }}>
        {/* Recent Messages */}
        <div style={{ flex: 1, minWidth: "300px" }}>
          <h2
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--text-muted)",
              marginBottom: "8px",
              textTransform: "uppercase",
              letterSpacing: "1px",
            }}
          >
            Recent Messages
          </h2>
          <div
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
            }}
          >
            {stats.recent_messages.map((msg: any, i: number) => (
              <div
                key={i}
                style={{
                  padding: "8px 12px",
                  borderBottom: "1px solid var(--border)",
                  fontSize: "12px",
                  display: "flex",
                  gap: "8px",
                }}
              >
                <span
                  style={{
                    color:
                      msg.direction === "in"
                        ? "var(--accent)"
                        : "var(--text-muted)",
                    width: "20px",
                    flexShrink: 0,
                  }}
                >
                  {msg.direction === "in" ? ">>" : "<<"}
                </span>
                <span style={{ color: "var(--text-muted)", flexShrink: 0, width: "100px" }}>
                  {msg.user_id?.slice(-4)}
                </span>
                <span
                  style={{
                    color: "var(--text)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {msg.body?.slice(0, 80)}
                </span>
                <span
                  style={{
                    marginLeft: "auto",
                    color: "var(--text-muted)",
                    flexShrink: 0,
                    fontSize: "11px",
                  }}
                >
                  {msg.created_at?.slice(11, 16)}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Calls */}
        <div style={{ flex: 1, minWidth: "300px" }}>
          <h2
            style={{
              fontSize: "13px",
              fontWeight: 600,
              color: "var(--text-muted)",
              marginBottom: "8px",
              textTransform: "uppercase",
              letterSpacing: "1px",
            }}
          >
            Recent Calls
          </h2>
          <div
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
            }}
          >
            {stats.recent_calls.map((call: any, i: number) => {
              const color = call.status === "success"
                ? "#27ae60"
                : call.status?.startsWith("failed")
                ? "#e74c3c"
                : "var(--text-muted)";
              return (
                <div
                  key={i}
                  style={{
                    padding: "8px 12px",
                    borderBottom: "1px solid var(--border)",
                    fontSize: "12px",
                    display: "flex",
                    gap: "8px",
                    alignItems: "center",
                  }}
                >
                  <span style={{ color, width: "8px", flexShrink: 0 }}>*</span>
                  <span style={{ fontWeight: 500 }}>
                    {call.business_name?.slice(0, 25)}
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      padding: "1px 6px",
                      borderRadius: "3px",
                      background: color + "22",
                      color,
                    }}
                  >
                    {call.status}
                  </span>
                  <span
                    style={{
                      marginLeft: "auto",
                      color: "var(--text-muted)",
                      fontSize: "11px",
                    }}
                  >
                    {call.created_at?.slice(11, 16)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
