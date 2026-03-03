"use client";

import { useEffect, useState } from "react";

interface Message {
  from: "user" | "holdplz";
  text: string;
  delay: number; // ms before this message appears
}

const CONVERSATION: Message[] = [
  {
    from: "user",
    text: "hey can you book me a table at Flour + Water for 2 tonight at 7?",
    delay: 800,
  },
  {
    from: "holdplz",
    text: "on it! calling them now",
    delay: 2200,
  },
  {
    from: "holdplz",
    text: "you're all set! booked for 2 at 7pm tonight. confirmation under Riley. they said they have outdoor seating if you want it -- just ask when you arrive",
    delay: 4500,
  },
];

function TypingIndicator() {
  return (
    <div className="sms-bubble sms-incoming flex items-center gap-1 w-16 py-3">
      <span className="typing-dot" />
      <span className="typing-dot" style={{ animationDelay: "0.15s" }} />
      <span className="typing-dot" style={{ animationDelay: "0.3s" }} />
    </div>
  );
}

export default function SMSConversation() {
  const [visibleCount, setVisibleCount] = useState(0);
  const [showTyping, setShowTyping] = useState(false);

  useEffect(() => {
    if (visibleCount >= CONVERSATION.length) return;

    const nextMsg = CONVERSATION[visibleCount];

    // Show typing indicator before incoming messages
    if (nextMsg.from === "holdplz") {
      setShowTyping(true);
      const timer = setTimeout(() => {
        setShowTyping(false);
        setVisibleCount((c) => c + 1);
      }, nextMsg.delay - (visibleCount > 0 ? CONVERSATION[visibleCount - 1].delay : 0));
      return () => clearTimeout(timer);
    }

    const timer = setTimeout(() => {
      setVisibleCount((c) => c + 1);
    }, nextMsg.delay - (visibleCount > 0 ? CONVERSATION[visibleCount - 1].delay : 0));
    return () => clearTimeout(timer);
  }, [visibleCount]);

  return (
    <div className="iphone-frame">
      {/* Status bar */}
      <div className="iphone-notch">
        <div className="iphone-notch-pill" />
      </div>
      <div className="iphone-header">
        <span className="iphone-header-name">Hold Plz</span>
      </div>

      {/* Messages */}
      <div className="iphone-messages">
        {CONVERSATION.slice(0, visibleCount).map((msg, i) => (
          <div
            key={i}
            className={`sms-bubble ${msg.from === "user" ? "sms-outgoing" : "sms-incoming"} sms-appear`}
          >
            {msg.text}
          </div>
        ))}
        {showTyping && <TypingIndicator />}
      </div>
    </div>
  );
}
