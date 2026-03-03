"use client";

export default function MarkdownViewer({ content }: { content: string }) {
  if (!content) {
    return (
      <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
        No content yet.
      </p>
    );
  }

  // Simple markdown rendering — handles headers, bullets, bold, and paragraphs
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("# ")) {
      elements.push(
        <h2
          key={i}
          style={{
            fontSize: "16px",
            fontWeight: 700,
            color: "var(--accent)",
            margin: "16px 0 8px",
          }}
        >
          {line.slice(2)}
        </h2>
      );
    } else if (line.startsWith("## ")) {
      elements.push(
        <h3
          key={i}
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--text)",
            margin: "12px 0 6px",
          }}
        >
          {line.slice(3)}
        </h3>
      );
    } else if (line.startsWith("### ")) {
      elements.push(
        <h4
          key={i}
          style={{
            fontSize: "13px",
            fontWeight: 600,
            color: "var(--text-muted)",
            margin: "10px 0 4px",
          }}
        >
          {line.slice(4)}
        </h4>
      );
    } else if (line.startsWith("- ") || line.startsWith("* ")) {
      elements.push(
        <div
          key={i}
          style={{
            paddingLeft: "16px",
            fontSize: "13px",
            lineHeight: "1.6",
            color: "var(--text)",
          }}
        >
          <span style={{ color: "var(--text-muted)" }}>-</span>{" "}
          {renderInline(line.slice(2))}
        </div>
      );
    } else if (line.trim() === "") {
      elements.push(<div key={i} style={{ height: "8px" }} />);
    } else {
      elements.push(
        <p
          key={i}
          style={{
            fontSize: "13px",
            lineHeight: "1.6",
            color: "var(--text)",
            margin: "2px 0",
          }}
        >
          {renderInline(line)}
        </p>
      );
    }
  }

  return (
    <div
      style={{
        background: "var(--bg)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        padding: "16px 20px",
        maxHeight: "500px",
        overflow: "auto",
      }}
    >
      {elements}
    </div>
  );
}

function renderInline(text: string): React.ReactNode {
  // Handle **bold** markers
  const parts = text.split(/(\*\*.*?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} style={{ color: "var(--accent)" }}>
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}
