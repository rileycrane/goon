"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { adminFetch } from "../../components/api";
import CallCard from "../../components/CallCard";
import StatsCard from "../../components/StatsCard";

export default function BusinessDetailPage() {
  const params = useParams();
  const placeId = decodeURIComponent(params.placeId as string);
  const [data, setData] = useState<any>(null);
  const [calls, setCalls] = useState<any[]>([]);
  const [error, setError] = useState("");

  const enc = encodeURIComponent(placeId);

  useEffect(() => {
    adminFetch(`/admin/businesses/${enc}`)
      .then(setData)
      .catch((e) => setError(e.message));
    adminFetch(`/admin/businesses/${enc}/calls`)
      .then((d) => setCalls(d.calls || []))
      .catch(() => {});
  }, [enc]);

  if (error) return <p style={{ color: "#e74c3c" }}>Error: {error}</p>;
  if (!data) return <p style={{ color: "var(--text-muted)" }}>Loading...</p>;

  const p = data.profile;
  const rate =
    p.total_calls > 0
      ? Math.round((p.successful_calls / p.total_calls) * 100)
      : null;

  return (
    <div>
      <h1
        style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: "12px",
          color: "var(--accent)",
          marginBottom: "4px",
        }}
      >
        {p.business_name}
      </h1>
      <p style={{ color: "var(--text-muted)", fontSize: "13px", marginBottom: "20px" }}>
        {p.address || placeId}
      </p>

      {/* Stats row */}
      <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "24px" }}>
        <StatsCard label="Total Calls" value={p.total_calls} />
        <StatsCard label="Success Rate" value={rate !== null ? `${rate}%` : "-"} />
        <StatsCard label="Queries" value={p.total_queries} />
        {p.avg_call_duration_seconds != null && (
          <StatsCard label="Avg Duration" value={`${Math.round(p.avg_call_duration_seconds)}s`} />
        )}
        {p.avg_hold_time_seconds != null && (
          <StatsCard label="Avg Hold" value={`${Math.round(p.avg_hold_time_seconds)}s`} />
        )}
      </div>

      {/* Info card */}
      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "16px",
          fontSize: "13px",
          lineHeight: "2",
          marginBottom: "24px",
        }}
      >
        <Row label="Phone" value={p.phone} />
        <Row label="Address" value={p.address} />
        <Row label="Lat/Lng" value={p.lat && p.lng ? `${p.lat}, ${p.lng}` : "-"} />
        <Row label="First Seen" value={p.first_seen} />
        <Row label="Last Updated" value={p.last_updated} />
        {p.known_contacts && (
          <Row label="Known Contacts" value={p.known_contacts} />
        )}
        {p.busy_patterns && (
          <Row label="Busy Patterns" value={p.busy_patterns} />
        )}
        {p.notes && <Row label="Notes" value={p.notes} />}
      </div>

      {/* Facts */}
      {data.facts?.length > 0 && (
        <Section title="Cached Facts">
          <div
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={thStyle}>Type</th>
                  <th style={thStyle}>Answer</th>
                  <th style={thStyle}>Source</th>
                  <th style={thStyle}>Confidence</th>
                  <th style={thStyle}>Expires</th>
                </tr>
              </thead>
              <tbody>
                {data.facts.map((f: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={tdStyle}>{f.fact_type}</td>
                    <td style={{ ...tdStyle, maxWidth: "300px", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {f.answer?.slice(0, 100)}
                    </td>
                    <td style={tdStyle}>{f.source}</td>
                    <td style={tdStyle}>{f.confidence}</td>
                    <td style={{ ...tdStyle, color: "var(--text-muted)" }}>
                      {f.expires_at?.slice(0, 10)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* Phone Scores */}
      {data.phone_scores?.length > 0 && (
        <Section title="Phone Scores">
          <div
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={thStyle}>Phone</th>
                  <th style={thStyle}>Calls</th>
                  <th style={thStyle}>Success</th>
                  <th style={thStyle}>Last Outcome</th>
                  <th style={thStyle}>Last Attempt</th>
                </tr>
              </thead>
              <tbody>
                {data.phone_scores.map((s: any, i: number) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={tdStyle}>{s.phone}</td>
                    <td style={tdStyle}>{s.call_count}</td>
                    <td style={tdStyle}>{s.success_count}</td>
                    <td style={tdStyle}>{s.last_outcome}</td>
                    <td style={{ ...tdStyle, color: "var(--text-muted)" }}>
                      {s.last_attempt?.slice(0, 16)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}

      {/* IVR Maps */}
      {data.ivr_maps?.length > 0 && (
        <Section title="IVR Maps">
          {data.ivr_maps.map((ivr: any, i: number) => (
            <div
              key={i}
              style={{
                background: "var(--bg)",
                border: "1px solid var(--border)",
                borderRadius: "6px",
                padding: "10px 14px",
                fontSize: "12px",
                marginBottom: "6px",
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: "4px" }}>{ivr.phone}</div>
              <pre style={{ margin: 0, color: "var(--text-muted)", whiteSpace: "pre-wrap" }}>
                {ivr.menu_structure}
              </pre>
            </div>
          ))}
        </Section>
      )}

      {/* Call History */}
      <Section title="Call History">
        {calls.length > 0 ? (
          calls.map((call) => (
            <CallCard key={call.id} call={call} userPhone={call.user_id} />
          ))
        ) : (
          <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
            No calls yet.
          </p>
        )}
      </Section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <div style={{ display: "flex", gap: "12px" }}>
      <span style={{ color: "var(--text-muted)", width: "140px", flexShrink: 0 }}>
        {label}
      </span>
      <span style={{ color: "var(--text)" }}>{String(value ?? "-")}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: "24px" }}>
      <h3
        style={{
          fontSize: "13px",
          fontWeight: 600,
          color: "var(--text-muted)",
          marginBottom: "8px",
          textTransform: "uppercase",
          letterSpacing: "1px",
        }}
      >
        {title}
      </h3>
      {children}
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "8px 12px",
  fontWeight: 600,
  fontSize: "11px",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  color: "var(--text-muted)",
  textAlign: "left",
};

const tdStyle: React.CSSProperties = {
  padding: "8px 12px",
};
