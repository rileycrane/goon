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
          setError(detail[0]?.msg || "Invalid input");
        } else {
          setError(detail || "Something went wrong");
        }
        setLoading(false);
        return;
      }

      const data = await res.json();
      window.location.href = data.checkout_url;
    } catch {
      setError("Could not connect to server. Try again.");
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16">
      <Link href="/" className="mb-8 text-sm text-gray-500 hover:text-gray-700">
        &larr; Back
      </Link>
      <div className="w-full max-w-md">
        <h1 className="text-3xl font-bold text-center">Sign up for Goon</h1>
        <p className="mt-2 text-center text-gray-600">
          $19.99/month. Cancel anytime.
        </p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          <div>
            <label htmlFor="name" className="block text-sm font-medium">
              Name
            </label>
            <input
              id="name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-4 py-2.5 focus:border-black focus:ring-1 focus:ring-black focus:outline-none"
              placeholder="Riley"
            />
          </div>

          <div>
            <label htmlFor="phone" className="block text-sm font-medium">
              Phone number
            </label>
            <input
              id="phone"
              type="tel"
              required
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-4 py-2.5 focus:border-black focus:ring-1 focus:ring-black focus:outline-none"
              placeholder="(555) 123-4567"
            />
            <p className="mt-1 text-xs text-gray-500">
              This is the number you&apos;ll text Goon from.
            </p>
          </div>

          <div>
            <label htmlFor="email" className="block text-sm font-medium">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-lg border border-gray-300 px-4 py-2.5 focus:border-black focus:ring-1 focus:ring-black focus:outline-none"
              placeholder="riley@example.com"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-black px-4 py-3 font-medium text-white hover:bg-gray-800 disabled:bg-gray-400 transition-colors"
          >
            {loading ? "Redirecting to payment..." : "Continue to payment"}
          </button>
        </form>
      </div>
    </main>
  );
}
