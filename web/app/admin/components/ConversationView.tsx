"use client";

export default function ConversationView({
  messages,
}: {
  messages: any[];
}) {
  if (!messages.length) {
    return (
      <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
        No messages yet.
      </p>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        padding: "8px",
      }}
    >
      {messages.map((msg, i) => {
        const isOut = msg.direction === "out";
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
            }}
          >
            {msg.text || msg.body || ""}
            <div
              style={{
                fontSize: "10px",
                color: isOut ? "rgba(255,255,255,0.6)" : "var(--text-muted)",
                marginTop: "4px",
              }}
            >
              {msg.timestamp?.slice(0, 16) || msg.created_at?.slice(0, 16)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
