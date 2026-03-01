import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen">
      {/* Hero */}
      <section className="flex flex-col items-center justify-center px-6 py-24 text-center">
        <h1 className="text-5xl font-bold tracking-tight sm:text-6xl">Goon</h1>
        <p className="mt-4 max-w-xl text-xl text-gray-600">
          Your AI that does the thing so you don&apos;t have to.
        </p>
        <p className="mt-6 max-w-lg text-gray-500">
          Text or call one number. Goon answers questions about businesses,
          calls them on your behalf, makes reservations, and remembers your
          preferences. No app. No humans in the loop.
        </p>
        <Link
          href="/signup"
          className="mt-10 rounded-lg bg-black px-8 py-3 text-lg font-medium text-white hover:bg-gray-800 transition-colors"
        >
          Get started &mdash; $19.99/mo
        </Link>
      </section>

      {/* How it works */}
      <section className="bg-gray-50 px-6 py-20">
        <div className="mx-auto max-w-3xl">
          <h2 className="text-center text-3xl font-bold">How it works</h2>
          <div className="mt-12 space-y-10">
            <Step
              number="1"
              title="Text your question"
              description='Just text the Goon number. "Does Delfina have a table for 2 tonight at 7?"'
            />
            <Step
              number="2"
              title="Goon figures it out"
              description="It checks cached data, Google, and the web first. If it needs to, it calls the business with an AI voice agent that sounds human."
            />
            <Step
              number="3"
              title="You get an answer"
              description='"Delfina has a table for 2 at 7:30. Name is Riley. Want me to confirm?" Done.'
            />
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-4xl">
          <h2 className="text-center text-3xl font-bold">
            Why it&apos;s different
          </h2>
          <div className="mt-12 grid gap-8 sm:grid-cols-2">
            <Feature
              title="Only calls when it has to"
              description="Most questions get answered from Google or the web. Phone calls are a last resort, saving you time and money."
            />
            <Feature
              title="Remembers everything"
              description="Your name, party size, preferred times, allergies, favorite spots. Every interaction makes Goon smarter about you."
            />
            <Feature
              title="Sounds human"
              description={`The AI voice agent calls like a regular person. No "I'm calling on behalf of" -- just a natural conversation.`}
            />
            <Feature
              title="Handles failure gracefully"
              description="Busy line, voicemail, wrong number? Goon tells you what happened and offers a plan: retry, try online, or gives you the number."
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-gray-50 px-6 py-20 text-center">
        <h2 className="text-3xl font-bold">Stop making phone calls</h2>
        <p className="mt-4 text-gray-600">
          $19.99/month. Cancel anytime. Works with any US phone number.
        </p>
        <Link
          href="/signup"
          className="mt-8 inline-block rounded-lg bg-black px-8 py-3 text-lg font-medium text-white hover:bg-gray-800 transition-colors"
        >
          Sign up
        </Link>
      </section>
    </main>
  );
}

function Step({
  number,
  title,
  description,
}: {
  number: string;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-6">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-black text-white font-bold">
        {number}
      </div>
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="mt-1 text-gray-600">{description}</p>
      </div>
    </div>
  );
}

function Feature({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 p-6">
      <h3 className="font-semibold">{title}</h3>
      <p className="mt-2 text-sm text-gray-600">{description}</p>
    </div>
  );
}
