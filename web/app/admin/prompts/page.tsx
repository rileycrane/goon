"use client";

import { useEffect, useState } from "react";
import { adminFetch, adminPut } from "../components/api";

export default function PromptsPage() {
  const [soul, setSoul] = useState("");
  const [savedSoul, setSavedSoul] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");

  // Preview system prompt
  const [users, setUsers] = useState<any[]>([]);
  const [previewPhone, setPreviewPhone] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);

  useEffect(() => {
    adminFetch("/admin/prompts/soul").then((d) => {
      setSoul(d.content || "");
      setSavedSoul(d.content || "");
    });
    adminFetch("/admin/users").then((d) => setUsers(d.users || []));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg("");
    try {
      await adminPut("/admin/prompts/soul", { content: soul });
      setSavedSoul(soul);
      setSaveMsg("Saved");
      setTimeout(() => setSaveMsg(""), 2000);
    } catch (e: any) {
      setSaveMsg("Error: " + e.message);
    }
    setSaving(false);
  };

  const handlePreview = async (phone: string) => {
    setPreviewPhone(phone);
    if (!phone) {
      setSystemPrompt("");
      return;
    }
    setLoadingPreview(true);
    try {
      const enc = encodeURIComponent(phone);
      const d = await adminFetch(`/admin/prompts/system?phone=${enc}`);
      setSystemPrompt(d.system_prompt || "");
    } catch (e: any) {
      setSystemPrompt("Error: " + e.message);
    }
    setLoadingPreview(false);
  };

  const dirty = soul !== savedSoul;

  return (
    <div>
      <h1
        style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: "12px",
          color: "var(--accent)",
          marginBottom: "20px",
        }}
      >
        PROMPTS
      </h1>

      {/* Soul.md editor */}
      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "24px",
        }}
      >
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "12px",
          }}
        >
          <h2 style={{ fontSize: "14px", fontWeight: 600, color: "var(--text)" }}>
            soul.md
          </h2>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            {saveMsg && (
              <span
                style={{
                  fontSize: "12px",
                  color: saveMsg.startsWith("Error") ? "#e74c3c" : "#2ecc71",
                }}
              >
                {saveMsg}
              </span>
            )}
            <button
              onClick={handleSave}
              disabled={saving || !dirty}
              style={{
                padding: "6px 16px",
                background: dirty ? "var(--accent)" : "#444",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                cursor: dirty ? "pointer" : "default",
                fontSize: "12px",
                fontWeight: 600,
                opacity: dirty ? 1 : 0.5,
              }}
            >
              {saving ? "Saving..." : "Save"}
            </button>
          </div>
        </div>
        <textarea
          value={soul}
          onChange={(e) => setSoul(e.target.value)}
          spellCheck={false}
          style={{
            width: "100%",
            minHeight: "400px",
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            color: "var(--text)",
            fontSize: "13px",
            fontFamily: "monospace",
            lineHeight: "1.6",
            padding: "12px",
            resize: "vertical",
            outline: "none",
          }}
        />
      </div>

      {/* Preview as user */}
      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "24px",
        }}
      >
        <h2
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--text)",
            marginBottom: "12px",
          }}
        >
          Preview Rendered System Prompt
        </h2>
        <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "12px" }}>
          <select
            value={previewPhone}
            onChange={(e) => handlePreview(e.target.value)}
            style={{
              padding: "6px 12px",
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              color: "var(--text)",
              fontSize: "13px",
            }}
          >
            <option value="">Select a user...</option>
            {users.map((u) => (
              <option key={u.phone} value={u.phone}>
                {u.name || u.phone} ({u.phone})
              </option>
            ))}
          </select>
          {loadingPreview && (
            <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
              Loading...
            </span>
          )}
        </div>
        {systemPrompt && (
          <pre
            style={{
              background: "var(--bg)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              padding: "12px",
              fontSize: "12px",
              lineHeight: "1.5",
              color: "var(--text)",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {systemPrompt}
          </pre>
        )}
      </div>

      {/* Resolution Ladder reference */}
      <div
        style={{
          background: "var(--card-bg)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "16px",
        }}
      >
        <h2
          style={{
            fontSize: "14px",
            fontWeight: 600,
            color: "var(--text)",
            marginBottom: "12px",
          }}
        >
          Resolution Ladder (hardcoded in orchestrator.py)
        </h2>
        <pre
          style={{
            background: "var(--bg)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            padding: "12px",
            fontSize: "12px",
            lineHeight: "1.5",
            color: "var(--text-muted)",
            whiteSpace: "pre-wrap",
          }}
        >
{`1. CACHE: Check business_facts cache first (check_cache tool)
2. PLACES: Try Google Places for structured data (search_places tool)
3. WEB: Try web search for the answer (search_web tool)
4. PRE-CALL: If you must call, run pre_call_check first
5. CALL: Only as last resort, or when the task REQUIRES human interaction

Tasks that ALWAYS require a call:
- Making a reservation or appointment
- Asking about specific item availability (not on website)
- Custom orders or special requests
- Anything requiring back-and-forth negotiation

Tasks that NEVER require a call:
- Hours, address, phone number, website
- Whether they offer takeout/delivery
- General ratings or price level
- Menu (usually findable online)`}
        </pre>
      </div>
    </div>
  );
}
