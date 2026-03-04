"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { adminFetch } from "../../components/api";
import MarkdownViewer from "../../components/MarkdownViewer";
import ConversationView from "../../components/ConversationView";
import CallCard from "../../components/CallCard";
import StatsCard from "../../components/StatsCard";
import SandboxChat from "../../components/SandboxChat";

const TABS = ["Overview", "Soul", "User", "Memory", "Playbook", "Conversations", "Calls", "Sandbox"];

export default function UserDetailPage() {
  const params = useParams();
  const phone = decodeURIComponent(params.phone as string);
  const [tab, setTab] = useState("Overview");
  const [user, setUser] = useState<any>(null);
  const [soul, setSoul] = useState("");
  const [userModel, setUserModel] = useState("");
  const [memory, setMemory] = useState("");
  const [playbook, setPlaybook] = useState("");
  const [conversations, setConversations] = useState<any[]>([]);
  const [bizConversations, setBizConversations] = useState<any>(null);
  const [calls, setCalls] = useState<any[]>([]);
  const [error, setError] = useState("");

  const enc = encodeURIComponent(phone);

  useEffect(() => {
    adminFetch(`/admin/users/${enc}`)
      .then(setUser)
      .catch((e) => setError(e.message));
  }, [enc]);

  // Load data lazily per tab
  useEffect(() => {
    if (tab === "Soul" && !soul) {
      adminFetch(`/admin/users/${enc}/soul`).then((d) =>
        setSoul(d.content || "")
      );
    } else if (tab === "User" && !userModel) {
      adminFetch(`/admin/users/${enc}/user-model`).then((d) =>
        setUserModel(d.content || "")
      );
    } else if (tab === "Memory" && !memory) {
      adminFetch(`/admin/users/${enc}/memory`).then((d) =>
        setMemory(d.memory || "")
      );
    } else if (tab === "Playbook" && !playbook) {
      adminFetch(`/admin/users/${enc}/playbook`).then((d) =>
        setPlaybook(d.content || "")
      );
    } else if (tab === "Conversations" && !bizConversations) {
      adminFetch(`/admin/users/${enc}/conversations/businesses`).then(
        setBizConversations
      );
    } else if (tab === "Calls" && !calls.length) {
      adminFetch(`/admin/users/${enc}/calls`).then((d) =>
        setCalls(d.calls || [])
      );
    }
  }, [tab, enc, soul, userModel, memory, playbook, bizConversations, calls.length]);

  if (error) return <p style={{ color: "#e74c3c" }}>Error: {error}</p>;
  if (!user) return <p style={{ color: "var(--text-muted)" }}>Loading...</p>;

  return (
    <div>
      <h1
        style={{
          fontFamily: "'Press Start 2P', monospace",
          fontSize: "12px",
          color: "var(--accent)",
          marginBottom: "4px",
        }}
      >
        {user.name || phone}
      </h1>
      <p style={{ color: "var(--text-muted)", fontSize: "13px", marginBottom: "20px" }}>
        {phone}
      </p>

      {/* Tab bar */}
      <div
        style={{
          display: "flex",
          gap: "4px",
          marginBottom: "20px",
          borderBottom: "1px solid var(--border)",
          paddingBottom: "8px",
        }}
      >
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              padding: "6px 14px",
              background: tab === t ? "var(--accent)" : "transparent",
              color: tab === t ? "#fff" : "var(--text-muted)",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "12px",
              fontWeight: tab === t ? 600 : 400,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "Overview" && (
        <div>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "20px" }}>
            <StatsCard label="Tier" value={user.subscription_status} />
            <StatsCard label="Messages" value={user.total_messages || 0} />
            <StatsCard label="Calls" value={user.total_calls || 0} />
            <StatsCard
              label="Success Rate"
              value={
                user.total_calls
                  ? Math.round(((user.successful_calls || 0) / user.total_calls) * 100) + "%"
                  : "-"
              }
            />
          </div>
          <div
            style={{
              background: "var(--card-bg)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "16px",
              fontSize: "13px",
              lineHeight: "2",
            }}
          >
            <Row label="Phone" value={user.phone} />
            <Row label="Email" value={user.email || "-"} />
            <Row label="Stripe ID" value={user.stripe_customer_id || "-"} />
            <Row label="Allowlisted" value={user.allowlisted ? "Yes" : "No"} />
            <Row label="Free msgs used" value={user.free_messages_used} />
            <Row label="Calls this period" value={user.calls_used_this_period} />
            <Row label="Created" value={user.created_at} />
          </div>
        </div>
      )}

      {tab === "Soul" && <MarkdownViewer content={soul} />}
      {tab === "User" && <MarkdownViewer content={userModel} />}
      {tab === "Memory" && <MarkdownViewer content={memory} />}
      {tab === "Playbook" && <MarkdownViewer content={playbook} />}

      {tab === "Conversations" && (
        <div>
          {bizConversations ? (
            <>
              {bizConversations.businesses?.length > 0 && (
                <div>
                  <h3
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      marginBottom: "12px",
                      textTransform: "uppercase",
                      letterSpacing: "1px",
                    }}
                  >
                    By Business
                  </h3>
                  {bizConversations.businesses.map((biz: any, i: number) => (
                    <BusinessGroup key={i} biz={biz} phone={phone} />
                  ))}
                </div>
              )}

              {bizConversations.general?.length > 0 && (
                <div style={{ marginTop: "24px" }}>
                  <h3
                    style={{
                      fontSize: "13px",
                      fontWeight: 600,
                      color: "var(--text-muted)",
                      marginBottom: "12px",
                      textTransform: "uppercase",
                      letterSpacing: "1px",
                    }}
                  >
                    General
                  </h3>
                  <ConversationView messages={bizConversations.general} />
                </div>
              )}
            </>
          ) : (
            <p style={{ color: "var(--text-muted)" }}>Loading...</p>
          )}
        </div>
      )}

      {tab === "Calls" && (
        <div>
          {calls.length > 0 ? (
            calls.map((call) => (
              <CallCard key={call.id} call={call} userPhone={phone} />
            ))
          ) : (
            <p style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
              No calls yet.
            </p>
          )}
        </div>
      )}

      {tab === "Sandbox" && <SandboxChat phone={phone} />}
    </div>
  );
}

function Row({ label, value }: { label: string; value: any }) {
  return (
    <div style={{ display: "flex", gap: "12px" }}>
      <span style={{ color: "var(--text-muted)", width: "140px", flexShrink: 0 }}>
        {label}
      </span>
      <span style={{ color: "var(--text)" }}>{String(value ?? "-")}</span>
    </div>
  );
}

function BusinessGroup({ biz, phone }: { biz: any; phone: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{
        marginBottom: "12px",
        background: "var(--card-bg)",
        border: "1px solid var(--border)",
        borderRadius: "8px",
        overflow: "hidden",
      }}
    >
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          padding: "10px 14px",
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ fontWeight: 600, fontSize: "13px" }}>
          {biz.business_name}
        </span>
        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
          {biz.messages?.length || 0} msgs / {biz.calls?.length || 0} calls{" "}
          {expanded ? "[-]" : "[+]"}
        </span>
      </div>

      {expanded && (
        <div style={{ padding: "0 14px 14px" }}>
          {biz.calls?.map((call: any) => (
            <CallCard key={call.id} call={call} userPhone={phone} />
          ))}
          {biz.messages?.length > 0 && (
            <div style={{ marginTop: "8px" }}>
              <ConversationView messages={biz.messages} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
