"use client";

import { useState, useEffect, ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/admin", label: "Overview", icon: "~" },
  { href: "/admin/users", label: "Users", icon: ">" },
  { href: "/admin/businesses", label: "Businesses", icon: "#" },
  { href: "/admin/failures", label: "Failures", icon: "!" },
  { href: "/admin/prompts", label: "Prompts", icon: "$" },
  { href: "/admin/diagrams", label: "Diagrams", icon: "%" },
];

function AuthGate({ children }: { children: ReactNode }) {
  const [password, setPassword] = useState("");
  const [authed, setAuthed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const saved = sessionStorage.getItem("admin_password");
    if (saved) {
      setPassword(saved);
      setAuthed(true);
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // Test the password against the API
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || ""}/admin/stats`,
        { headers: { "X-Admin-Password": password } }
      );
      if (res.ok) {
        sessionStorage.setItem("admin_password", password);
        setAuthed(true);
        setError("");
      } else {
        setError("Wrong password");
      }
    } catch {
      setError("Cannot reach API");
    }
  };

  if (!authed) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--bg)",
        }}
      >
        <form onSubmit={handleSubmit} style={{ textAlign: "center" }}>
          <h1
            style={{
              fontFamily: "'Press Start 2P', monospace",
              fontSize: "14px",
              color: "var(--accent)",
              marginBottom: "24px",
            }}
          >
            HOLD PLZ ADMIN
          </h1>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            style={{
              padding: "12px 16px",
              background: "var(--card-bg)",
              border: "2px solid var(--border)",
              borderRadius: "8px",
              color: "var(--text)",
              fontSize: "14px",
              width: "260px",
              outline: "none",
            }}
            autoFocus
          />
          <br />
          <button
            type="submit"
            style={{
              marginTop: "12px",
              padding: "10px 24px",
              background: "var(--accent)",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            Enter
          </button>
          {error && (
            <p style={{ color: "#e74c3c", marginTop: "8px", fontSize: "13px" }}>
              {error}
            </p>
          )}
        </form>
      </div>
    );
  }

  return <>{children}</>;
}

function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      style={{
        width: "200px",
        minHeight: "100vh",
        background: "var(--card-bg)",
        borderRight: "1px solid var(--border)",
        padding: "20px 0",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          padding: "0 16px 20px",
          fontFamily: "'Press Start 2P', monospace",
          fontSize: "10px",
          color: "var(--accent)",
        }}
      >
        HOLD PLZ
      </div>
      {NAV_ITEMS.map((item) => {
        const active =
          item.href === "/admin"
            ? pathname === "/admin"
            : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "10px 16px",
              color: active ? "var(--accent)" : "var(--text-muted)",
              textDecoration: "none",
              fontSize: "13px",
              fontWeight: active ? 600 : 400,
              background: active ? "rgba(255,107,53,0.08)" : "transparent",
              borderRight: active ? "2px solid var(--accent)" : "2px solid transparent",
            }}
          >
            <span style={{ fontFamily: "monospace", width: "14px" }}>
              {item.icon}
            </span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export default function AdminLayout({ children }: { children: ReactNode }) {
  return (
    <AuthGate>
      <div style={{ display: "flex", minHeight: "100vh" }}>
        <Sidebar />
        <main
          style={{
            flex: 1,
            padding: "24px 32px",
            maxWidth: "1200px",
            overflow: "auto",
          }}
        >
          {children}
        </main>
      </div>
    </AuthGate>
  );
}
