"use client";

import { useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function PhoneStartForm({ className }: { className?: string }) {
  const [phone, setPhone] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">(
    "idle",
  );

  function formatPhone(value: string): string {
    const digits = value.replace(/\D/g, "").slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    setPhone(formatPhone(e.target.value));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const digits = phone.replace(/\D/g, "");
    if (digits.length !== 10) return;
    setStatus("loading");

    try {
      const res = await fetch(`${API_URL}/register/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone: digits }),
      });
      if (!res.ok) throw new Error();
      setStatus("done");
    } catch {
      setStatus("error");
    }
  }

  if (status === "done") {
    return (
      <div className={`phone-success ${className || ""}`}>
        check your texts.
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={`phone-form ${className || ""}`}>
      <input
        type="tel"
        required
        placeholder="(555) 555-5555"
        value={phone}
        onChange={handleChange}
        className="phone-input"
      />
      <button
        type="submit"
        disabled={status === "loading" || phone.replace(/\D/g, "").length !== 10}
        className="phone-button"
      >
        {status === "loading" ? "..." : "text me"}
      </button>
      {status === "error" && (
        <p className="phone-error">something went wrong. try again.</p>
      )}
    </form>
  );
}
