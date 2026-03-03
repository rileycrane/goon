"use client";

import { useEffect, useState } from "react";
import { adminFetch, adminPost } from "../components/api";
import StatsCard from "../components/StatsCard";

const SEVERITY_COLORS: Record<string, string> = {
  low: "#3498db",
  medium: "var(--accent)",
  high: "#e74c3c",
  critical: "#c0392b",
};

export default function FailuresPage() {
  const [failures, setFailures] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [filterType, setFilterType] = useState("");
  const [filterSeverity, setFilterSeverity] = useState("");
  const [showResolved, setShowResolved] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    const params = new URLSearchParams();
    if (filterType) params.set("failure_type", filterType);
    if (filterSeverity) params.set("severity", filterSeverity);
    if (!showResolved) params.set("resolved", "false");
    const q = params.toString() ? `?${params.toString()}` : "";

    adminFetch(`/admin/failures${q}`)
      .then((d) => setFailures(d.failures || []))
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
    adminFetch("/admin/failures/summary").then(setSummary).catch(() => {});
  }, [filterType, filterSeverity, showResolved]);

  const handleResolve = async (id: number) => {
    const notes = prompt("Resolution notes (optional):");
    if (notes === null) return;
    await adminPost(`/admin/failures/${id}/resolve`, { notes });
    load();
  };

  if (error) return <p style={{ color: "#e74c3c" }}>Error: {error}</p>;

  return (
    <div>
      <h1
        style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: "14px",
          color: "var(--accent)",
          marginBottom: "20px",
        }}
      >
        Failures
      </h1>

      {/* Summary cards */}
      {summary && (
        <div
          style={{
            display: "flex",
            gap: "12px",
            flexWrap: "wrap",
            marginBottom: "20px",
          }}
        >
          <StatsCard label="This Week" value={summary.total_this_week} />
          <StatsCard label="Unresolved" value={summary.unresolved} />
          {summary.by_type?.slice(0, 3).map((t: any) => (
            <StatsCard key={t.failure_type} label={t.failure_type} value={t.count} />
          ))}
        </div>
      )}

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          style={selectStyle}
        >
          <option value="">All types</option>
          <option value="wrong_number">wrong_number</option>
          <option value="hung_up">hung_up</option>
          <option value="busy">busy</option>
          <option value="no_answer">no_answer</option>
          <option value="voicemail">voicemail</option>
          <option value="timeout">timeout</option>
          <option value="composition_failure">composition_failure</option>
          <option value="webhook_error">webhook_error</option>
        </select>
        <select
          value={filterSeverity}
          onChange={(e) => setFilterSeverity(e.target.value)}
          style={selectStyle}
        >
          <option value="">All severities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
        <label
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontSize: "13px",
            color: "var(--text-muted)",
            cursor: "pointer",
          }}
        >
          <input
            type="checkbox"
            checked={showResolved}
            onChange={(e) => setShowResolved(e.target.checked)}
          />
          Show resolved
        </label>
      </div>

      {/* Table */}
      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          overflow: "hidden",
        }}
      >
        {failures.map((f) => {
          const sevColor = SEVERITY_COLORS[f.severity] || "var(--text-muted)";
          const isExpanded = expanded === f.id;
          return (
            <div
              key={f.id}
              style={{ borderBottom: "1px solid var(--border)" }}
            >
              <div
                onClick={() => setExpanded(isExpanded ? null : f.id)}
                style={{
                  padding: "10px 14px",
                  cursor: "pointer",
                  display: "flex",
                  gap: "10px",
                  alignItems: "center",
                  fontSize: "13px",
                }}
              >
                <span
                  style={{
                    padding: "2px 8px",
                    borderRadius: "4px",
                    background: sevColor + "22",
                    color: sevColor,
                    fontSize: "11px",
                    fontWeight: 500,
                    flexShrink: 0,
                  }}
                >
                  {f.severity}
                </span>
                <span style={{ fontWeight: 500, flexShrink: 0 }}>
                  {f.failure_type}
                </span>
                <span
                  style={{
                    color: "var(--text-muted)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    flex: 1,
                  }}
                >
                  {f.description?.slice(0, 60)}
                </span>
                {f.business_name && (
                  <span style={{ color: "var(--text-muted)", fontSize: "12px", flexShrink: 0 }}>
                    {f.business_name}
                  </span>
                )}
                <span style={{ color: "var(--text-muted)", fontSize: "11px", flexShrink: 0 }}>
                  {f.created_at?.slice(0, 16)}
                </span>
                {f.resolved && (
                  <span style={{ color: "#27ae60", fontSize: "11px" }}>resolved</span>
                )}
              </div>

              {isExpanded && (
                <div
                  style={{
                    padding: "0 14px 12px",
                    fontSize: "12px",
                    lineHeight: "1.8",
                  }}
                >
                  <div>
                    <strong style={{ color: "var(--text-muted)" }}>Description: </strong>
                    {f.description}
                  </div>
                  {f.user_id && (
                    <div>
                      <strong style={{ color: "var(--text-muted)" }}>User: </strong>
                      {f.user_id}
                    </div>
                  )}
                  {f.context && (
                    <div>
                      <strong style={{ color: "var(--text-muted)" }}>Context: </strong>
                      <pre
                        style={{
                          background: "var(--bg)",
                          padding: "8px",
                          borderRadius: "4px",
                          overflow: "auto",
                          maxHeight: "150px",
                          margin: "4px 0",
                          fontSize: "11px",
                        }}
                      >
                        {f.context}
                      </pre>
                    </div>
                  )}
                  {f.resolution_notes && (
                    <div>
                      <strong style={{ color: "var(--text-muted)" }}>Resolution: </strong>
                      {f.resolution_notes}
                    </div>
                  )}
                  {!f.resolved && (
                    <button
                      onClick={() => handleResolve(f.id)}
                      style={{
                        marginTop: "6px",
                        padding: "4px 12px",
                        background: "#27ae60",
                        color: "#fff",
                        border: "none",
                        borderRadius: "4px",
                        cursor: "pointer",
                        fontSize: "12px",
                      }}
                    >
                      Mark Resolved
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {failures.length === 0 && (
          <p
            style={{
              padding: "16px",
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: "13px",
            }}
          >
            No failures found.
          </p>
        )}
      </div>
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  padding: "8px 12px",
  background: "var(--card-bg)",
  border: "1px solid var(--border)",
  borderRadius: "6px",
  color: "var(--text)",
  fontSize: "13px",
};
