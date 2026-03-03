"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminFetch } from "../components/api";

export default function BusinessesPage() {
  const [businesses, setBusinesses] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    adminFetch("/admin/businesses")
      .then((d) => setBusinesses(d.businesses || []))
      .catch((e) => setError(e.message));
  }, []);

  const filtered = businesses.filter((b) => {
    if (!search) return true;
    return b.business_name?.toLowerCase().includes(search.toLowerCase());
  });

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
        Businesses
      </h1>

      <input
        type="text"
        placeholder="Search by name..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        style={{
          padding: "8px 12px",
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "6px",
          color: "var(--text)",
          fontSize: "13px",
          width: "260px",
          outline: "none",
          marginBottom: "16px",
        }}
      />

      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          overflow: "hidden",
        }}
      >
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "13px",
          }}
        >
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)", textAlign: "left" }}>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>Total Calls</th>
              <th style={thStyle}>Success Rate</th>
              <th style={thStyle}>Queries</th>
              <th style={thStyle}>Last Updated</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((b) => {
              const rate =
                b.total_calls > 0
                  ? Math.round((b.successful_calls / b.total_calls) * 100)
                  : null;
              return (
                <tr
                  key={b.place_id}
                  style={{ borderBottom: "1px solid var(--border)" }}
                >
                  <td style={tdStyle}>
                    <Link
                      href={`/admin/businesses/${encodeURIComponent(b.place_id)}`}
                      style={{ color: "var(--accent)", textDecoration: "none" }}
                    >
                      {b.business_name}
                    </Link>
                  </td>
                  <td style={tdStyle}>{b.total_calls}</td>
                  <td style={tdStyle}>
                    {rate !== null ? (
                      <span
                        style={{
                          color: rate >= 70 ? "#27ae60" : rate >= 40 ? "#f39c12" : "#e74c3c",
                        }}
                      >
                        {rate}%
                      </span>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td style={tdStyle}>{b.total_queries}</td>
                  <td style={{ ...tdStyle, color: "var(--text-muted)" }}>
                    {b.last_updated?.slice(0, 10)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p
            style={{
              padding: "16px",
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: "13px",
            }}
          >
            {businesses.length === 0
              ? "No businesses tracked yet."
              : "No matches."}
          </p>
        )}
      </div>
    </div>
  );
}

const thStyle: React.CSSProperties = {
  padding: "10px 12px",
  fontWeight: 600,
  fontSize: "11px",
  textTransform: "uppercase",
  letterSpacing: "0.5px",
  color: "var(--text-muted)",
};

const tdStyle: React.CSSProperties = {
  padding: "10px 12px",
};
