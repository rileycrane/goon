"use client";

import { useEffect, useRef, useState } from "react";

const PAINS = [
  "being on hold for 23 minutes to ask one question",
  '"your call is important to us" (it isn\'t)',
  "calling a restaurant and nobody picks up",
  "explaining your request to 3 different people",
  "that moment of dread before you dial",
  'googling "do I have to call or can I do this online"',
  "the hold music. always the hold music.",
];

function Equalizer() {
  return (
    <div className="equalizer" aria-hidden="true">
      {[...Array(5)].map((_, i) => (
        <div
          key={i}
          className="eq-bar"
          style={{ animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </div>
  );
}

export default function PainPoints() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!ref.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) setVisible(true);
      },
      { threshold: 0.2 },
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className="pain-grid">
      {PAINS.map((pain, i) => (
        <div
          key={i}
          className="pain-card"
          style={{
            opacity: visible ? 1 : 0,
            transform: visible ? "translateY(0)" : "translateY(20px)",
            transition: `opacity 0.5s ${i * 0.08}s, transform 0.5s ${i * 0.08}s`,
          }}
        >
          <span className="pain-x" aria-hidden="true">
            {/* phone icon crossed out */}
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07 19.5 19.5 0 01-6-6 19.79 19.79 0 01-3.07-8.67A2 2 0 014.11 2h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L8.09 9.91a16 16 0 006 6l1.27-1.27a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z" />
              <line x1="1" y1="1" x2="23" y2="23" stroke="currentColor" strokeWidth="2.5" />
            </svg>
          </span>
          {pain}
        </div>
      ))}
      <div
        className="pain-card pain-card-eq"
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? "translateY(0)" : "translateY(20px)",
          transition: `opacity 0.5s ${PAINS.length * 0.08}s, transform 0.5s ${PAINS.length * 0.08}s`,
        }}
      >
        <Equalizer />
      </div>
    </div>
  );
}
