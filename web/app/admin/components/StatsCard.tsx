"use client";

export default function StatsCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div
      style={{
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
        borderRadius: "12px",
        padding: "16px 20px",
        minWidth: "140px",
      }}
    >
      <div style={{ fontSize: "24px", fontWeight: 700, color: "var(--text)" }}>
        {value}
      </div>
      <div
        style={{
          fontSize: "12px",
          color: "var(--text-muted)",
          marginTop: "4px",
        }}
      >
        {label}
      </div>
      {sub && (
        <div
          style={{
            fontSize: "11px",
            color: "var(--text-muted)",
            marginTop: "2px",
          }}
        >
          {sub}
        </div>
      )}
    </div>
  );
}
