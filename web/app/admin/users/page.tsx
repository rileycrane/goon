"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { adminFetch } from "../components/api";

const TIER_COLORS: Record<string, string> = {
  free: "#3498db",
  active: "#27ae60",
  trial: "#f39c12",
  canceled: "#e74c3c",
  past_due: "#e74c3c",
};

export default function UsersPage() {
  const [users, setUsers] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [filterTier, setFilterTier] = useState("");
  const [sortBy, setSortBy] = useState("created_at");
  const [error, setError] = useState("");

  useEffect(() => {
    adminFetch("/admin/users")
      .then((d) => setUsers(d.users || []))
      .catch((e) => setError(e.message));
  }, []);

  const filtered = users
    .filter((u) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !u.phone?.toLowerCase().includes(q) &&
          !u.name?.toLowerCase().includes(q)
        )
          return false;
      }
      if (filterTier && u.subscription_status !== filterTier) return false;
      return true;
    })
    .sort((a, b) => {
      if (sortBy === "total_messages") return (b.total_messages || 0) - (a.total_messages || 0);
      if (sortBy === "total_calls") return (b.total_calls || 0) - (a.total_calls || 0);
      return (b.created_at || "").localeCompare(a.created_at || "");
    });

  if (error)
    return <p style={{ color: "#e74c3c" }}>Error: {error}</p>;

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
        Users
      </h1>

      {/* Filters */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", flexWrap: "wrap" }}>
        <input
          type="text"
          placeholder="Search phone or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            color: "var(--text)",
            fontSize: "13px",
            width: "220px",
            outline: "none",
          }}
        />
        <select
          value={filterTier}
          onChange={(e) => setFilterTier(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            color: "var(--text)",
            fontSize: "13px",
          }}
        >
          <option value="">All tiers</option>
          <option value="free">Free</option>
          <option value="active">Active</option>
          <option value="trial">Trial</option>
          <option value="canceled">Canceled</option>
        </select>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "var(--card-bg)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            color: "var(--text)",
            fontSize: "13px",
          }}
        >
          <option value="created_at">Sort: newest</option>
          <option value="total_messages">Sort: most messages</option>
          <option value="total_calls">Sort: most calls</option>
        </select>
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
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "13px",
          }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "1px solid var(--border)",
                textAlign: "left",
              }}
            >
              <th style={thStyle}>Phone</th>
              <th style={thStyle}>Name</th>
              <th style={thStyle}>Tier</th>
              <th style={thStyle}>Messages</th>
              <th style={thStyle}>Calls</th>
              <th style={thStyle}>Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => {
              const tierColor =
                TIER_COLORS[u.subscription_status] || "var(--text-muted)";
              return (
                <tr
                  key={u.id}
                  style={{ borderBottom: "1px solid var(--border)" }}
                >
                  <td style={tdStyle}>
                    <Link
                      href={`/admin/users/${encodeURIComponent(u.phone)}`}
                      style={{
                        color: "var(--accent)",
                        textDecoration: "none",
                      }}
                    >
                      {u.phone}
                    </Link>
                  </td>
                  <td style={tdStyle}>{u.name || "-"}</td>
                  <td style={tdStyle}>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        background: tierColor + "22",
                        color: tierColor,
                        fontSize: "11px",
                        fontWeight: 500,
                      }}
                    >
                      {u.subscription_status}
                      {u.allowlisted ? " *" : ""}
                    </span>
                  </td>
                  <td style={tdStyle}>{u.total_messages || u.free_messages_used || 0}</td>
                  <td style={tdStyle}>{u.total_calls || u.calls_used_this_period || 0}</td>
                  <td style={{ ...tdStyle, color: "var(--text-muted)" }}>
                    {u.created_at?.slice(0, 10)}
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
            No users found.
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
