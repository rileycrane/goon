import Link from "next/link";

export default function SignupSuccess() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center">
      <h1 className="text-3xl font-bold">you're in.</h1>
      <p className="mt-4 max-w-md" style={{ color: "var(--text-muted)" }}>
        check your phone -- hold plz just texted you. text back whenever you
        need something done: restaurant reservations, business questions,
        anything.
      </p>
      <div className="mt-10 space-y-4">
        <p className="text-sm" style={{ color: "var(--text-muted)" }}>
          that's it. no app to download. just text.
        </p>
        <Link
          href="/"
          className="inline-block text-sm hover:opacity-70 transition-opacity"
          style={{ color: "var(--text-muted)" }}
        >
          &larr; back to home
        </Link>
      </div>
    </main>
  );
}
