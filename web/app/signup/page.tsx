"use client";

import { useState } from "react";
import Link from "next/link";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function Signup() {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/register/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, phone, email }),
      });

      if (!res.ok) {
        const data = await res.json();
        const detail = data.detail;
        if (Array.isArray(detail)) {
          setError(detail[0]?.msg || "invalid input");
        } else {
          setError(detail || "something went wrong");
        }
        setLoading(false);
        return;
      }

      const data = await res.json();
      window.location.href = data.checkout_url;
    } catch {
      setError("could not connect to server. try again.");
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <Link
        href="/"
        className="mb-8 text-sm hover:opacity-70 transition-opacity"
        style={{ color: "var(--text-muted)" }}
      >
        &larr; back
      </Link>
      <div className="w-full max-w-md">
        <h1 className="text-3xl font-bold text-center">sign up for hold plz</h1>
        <p className="mt-2 text-center" style={{ color: "var(--text-muted)" }}>
          $19.99/month. cancel anytime.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          <div>
            <label htmlFor="name" className="block text-sm font-medium">
              name
            </label>
            <input
              id="name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-lg border-2 px-4 py-2.5 focus:outline-none transition-colors"
              style={{
                borderColor: "#c8d0c8",
                background: "var(--white)",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.target.style.borderColor = "#c8d0c8")}
              placeholder="Riley"
            />
          </div>

          <div>
            <label htmlFor="phone" className="block text-sm font-medium">
              phone number
            </label>
            <input
              id="phone"
              type="tel"
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="mt-1 block w-full rounded-lg border-2 px-4 py-2.5 focus:outline-none transition-colors"
              style={{
                borderColor: "#c8d0c8",
                background: "var(--white)",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.target.style.borderColor = "#c8d0c8")}
              placeholder="(555) 123-4567"
            />
            <p className="mt-1 text-xs" style={{ color: "var(--text-muted)" }}>
              this is the number you'll text hold plz from.
            </p>
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium">
              email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-lg border-2 px-4 py-2.5 focus:outline-none transition-colors"
              style={{
                borderColor: "#c8d0c8",
                background: "var(--white)",
              }}
              onFocus={(e) => (e.target.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.target.style.borderColor = "#c8d0c8")}
              placeholder="riley@example.com"
            />
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg px-4 py-3 font-medium text-white transition-colors disabled:opacity-50"
            style={{ background: "var(--accent)" }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.background = "var(--accent-hover)")
            }
            onMouseLeave={(e) =>
              (e.currentTarget.style.background = "var(--accent)")
            }
          >
            {loading ? "redirecting to payment..." : "continue to payment"}
          </button>
        </form>
      </div>
    </main>
  );
}
