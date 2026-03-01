import Link from "next/link";

export default function SignupSuccess() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-6 py-16 text-center">
      <h1 className="text-3xl font-bold">You&apos;re in.</h1>
      <p className="mt-4 max-w-md text-gray-600">
        Check your phone -- Goon just texted you. Text back whenever you need
        something done: restaurant reservations, business questions, anything.
      </p>
      <div className="mt-10 space-y-4">
        <p className="text-sm text-gray-500">
          That&apos;s it. No app to download. Just text.
        </p>
        <Link
          href="/"
          className="inline-block text-sm text-gray-500 hover:text-gray-700"
        >
          &larr; Back to home
        </Link>
      </div>
    </main>
  );
}
