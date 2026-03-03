"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function WaitlistForm({ className }: { className?: string }) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">(
    "idle",
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setStatus("loading");

    try {
      const res = await fetch(`${API_URL}/register/waitlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (!res.ok) throw new Error();
      setStatus("done");
    } catch {
      setStatus("error");
    }
  }

  if (status === "done") {
    return (
      <div className={`waitlist-success ${className || ""}`}>
        you're on the list. we'll be in touch.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={`waitlist-form ${className || ""}`}>
      <input
        type="email"
        required
        placeholder="your email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="waitlist-input"
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className="waitlist-button"
      >
        {status === "loading" ? "..." : "join waitlist"}
      </button>
      {status === "error" && (
        <p className="waitlist-error">something went wrong. try again.</p>
      )}
    </form>
  );
}
