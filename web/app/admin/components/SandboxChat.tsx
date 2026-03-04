"use client";

import { useState, useRef, useEffect } from "react";
import { adminPost } from "./api";

interface Message {
  role: "user" | "assistant";
  text: string;
}

export default function SandboxChat({ phone }: { phone: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    try {
      const d = await adminPost("/admin/sandbox", { phone, message: text });
      setMessages((prev) => [...prev, { role: "assistant", text: d.response }]);
    } catch (e: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `Error: ${e.message}` },
      ]);
    }
    setLoading(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div>
      <div
        style={{
          background: "#1a1a2e",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "8px 12px",
          marginBottom: "12px",
          fontSize: "11px",
          color: "var(--text-muted)",
        }}
      >
        Sandbox mode -- messages are NOT stored. Full user context is loaded.
      </div>

      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "6px",
          marginBottom: "12px",
          minHeight: "200px",
        }}
      >
        {messages.map((msg, i) => {
          const isOut = msg.role === "assistant";
          return (
            <div
              key={i}
              style={{
                alignSelf: isOut ? "flex-end" : "flex-start",
                maxWidth: "80%",
                padding: "8px 12px",
                borderRadius: "12px",
                borderBottomRightRadius: isOut ? "4px" : "12px",
                borderBottomLeftRadius: isOut ? "12px" : "4px",
                background: isOut ? "var(--accent)" : "#252545",
                color: isOut ? "#fff" : "var(--text)",
                fontSize: "13px",
                lineHeight: "1.4",
                whiteSpace: "pre-wrap",
              }}
            >
              {msg.text}
            </div>
          );
        })}
        {loading && (
          <div
            style={{
              alignSelf: "flex-end",
              padding: "8px 12px",
              borderRadius: "12px",
              background: "var(--accent)",
              color: "#fff",
              fontSize: "13px",
              opacity: 0.6,
            }}
          >
            Thinking...
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div style={{ display: "flex", gap: "8px" }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message..."
          disabled={loading}
          style={{
            flex: 1,
            padding: "10px 14px",
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            color: "var(--text)",
            fontSize: "13px",
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
          style={{
            padding: "10px 18px",
            background: "var(--accent)",
            color: "#fff",
            border: "none",
            borderRadius: "8px",
            cursor: loading ? "default" : "pointer",
            fontSize: "13px",
            fontWeight: 600,
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}
        >
          Send
        </button>
        <button
          onClick={() => setMessages([])}
          style={{
            padding: "10px 14px",
            background: "transparent",
            color: "var(--text-muted)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            cursor: "pointer",
            fontSize: "12px",
          }}
        >
          Clear
        </button>
      </div>
    </div>
  );
}
