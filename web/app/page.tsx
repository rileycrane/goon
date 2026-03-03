import SMSConversation from "./components/SMSConversation";
import PainPoints from "./components/PainPoints";
import WaitlistForm from "./components/WaitlistForm";

const USE_CASES = [
  "book me a table at Flour + Water for 4 at 8pm friday",
  "what time does the walgreens on 24th st close?",
  "can you call my dentist and reschedule to next week?",
  "ask if that salon on valencia has any openings tomorrow afternoon",
  "call the vet and ask if I need an appointment for a nail trim",
];

export default function Home() {
  return (
    <main>
      {/* ---- Hero ---- */}
      <section className="px-6 pt-20 pb-16 sm:pt-28 sm:pb-24">
        <div className="mx-auto max-w-6xl flex flex-col lg:flex-row items-center gap-16">
          <div className="flex-1 max-w-xl">
            <h1 className="text-5xl sm:text-6xl font-bold tracking-tight leading-[1.1]">
              you hate calling places.
              <br />
              <span style={{ color: "var(--accent)" }}>we call for you.</span>
            </h1>
            <p
              className="mt-6 text-lg"
              style={{ color: "var(--text-muted)" }}
            >
              text us what you need. we call the place. you get a text back when
              it's done. restaurants, salons, dentists, vets, whatever.
            </p>
            <div className="mt-10">
              <WaitlistForm />
            </div>
          </div>
          <div className="flex-shrink-0">
            <SMSConversation />
          </div>
        </div>
      </section>

      {/* ---- The Pain ---- */}
      <section className="px-6 py-20" style={{ background: "var(--bg-alt)" }}>
        <div className="mx-auto max-w-3xl">
          <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
            we get it
          </h2>
          <p
            className="text-center mb-12"
            style={{ color: "var(--text-muted)" }}
          >
            phone calls are the worst. here's a list of things you'll never have
            to do again.
          </p>
          <PainPoints />
        </div>
      </section>

      {/* ---- How It Works ---- */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl sm:text-4xl font-bold text-center mb-14">
            how it works
          </h2>
          <div className="space-y-10">
            <Step
              number="1"
              title="text us"
              description="tell us what you need, like you'd text a friend."
            />
            <Step
              number="2"
              title="we call"
              description="our AI calls the business and handles it."
            />
            <Step
              number="3"
              title="done"
              description="you get a text back with the result. that's it."
            />
          </div>
        </div>
      </section>

      {/* ---- Use Cases ---- */}
      <section className="px-6 py-20" style={{ background: "var(--bg-alt)" }}>
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl sm:text-4xl font-bold text-center mb-4">
            things people text us
          </h2>
          <p
            className="text-center mb-12"
            style={{ color: "var(--text-muted)" }}
          >
            real requests. no formalities required.
          </p>
          <div className="space-y-4">
            {USE_CASES.map((text, i) => (
              <div key={i} className="usecase-bubble">
                {text}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Pricing ---- */}
      <section className="px-6 py-20">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-3xl sm:text-4xl font-bold text-center mb-12">
            one plan. no nonsense.
          </h2>
          <div className="pricing-card">
            <p className="text-4xl font-bold">$19.99</p>
            <p style={{ color: "var(--text-muted)" }} className="mt-1">
              per month
            </p>
            <ul
              className="mt-8 space-y-3 text-left text-sm"
              style={{ color: "var(--text-muted)" }}
            >
              <li>- unlimited texts</li>
              <li>- we make the calls so you don't have to</li>
              <li>- works with any business that has a phone number</li>
              <li>- remembers your preferences</li>
            </ul>
            <p
              className="mt-8 text-xs"
              style={{ color: "var(--text-muted)" }}
            >
              no contracts. cancel anytime. seriously.
            </p>
          </div>
        </div>
      </section>

      {/* ---- Bottom CTA ---- */}
      <section className="px-6 py-20" style={{ background: "var(--bg-alt)" }}>
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-3xl sm:text-4xl font-bold mb-4">
            we're almost ready. get in line.
          </h2>
          <p
            className="mb-10"
            style={{ color: "var(--text-muted)" }}
          >
            early access coming soon. no phone call required to sign up.
          </p>
          <div className="flex justify-center">
            <WaitlistForm />
          </div>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="px-6 py-10 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        <p className="font-semibold" style={{ color: "var(--text)" }}>
          hold plz
        </p>
        <p className="mt-2">hello@holdplz.ai</p>
      </footer>
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
    <div className="flex gap-5 items-start">
      <div
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full font-bold text-white"
        style={{ background: "var(--accent)" }}
      >
        {number}
      </div>
      <div>
        <h3 className="text-lg font-semibold">{title}</h3>
        <p style={{ color: "var(--text-muted)" }} className="mt-1">
          {description}
        </p>
      </div>
    </div>
  );
}
