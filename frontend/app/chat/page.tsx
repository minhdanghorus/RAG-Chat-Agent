"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/app/components/Nav";
import {
  Agent,
  Citation,
  createSession,
  getHistory,
  getToken,
  listAgents,
  listSessions,
  Session,
  streamMessage,
} from "@/lib/api";

interface Msg {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export default function ChatPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pickedAgent, setPickedAgent] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const refresh = useCallback(async () => {
    const [a, s] = await Promise.all([listAgents(), listSessions()]);
    setAgents(a);
    setSessions(s);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  async function openSession(s: Session) {
    setActive(s);
    setCreating(false);
    const hist = await getHistory(s.id);
    setMessages(hist.map((m) => ({ role: m.role as Msg["role"], content: m.content })));
  }

  function startNew() {
    setCreating(true);
    setActive(null);
    setMessages([]);
    setPickedAgent(null);
  }

  async function confirmNew() {
    if (!pickedAgent) return;
    const s = await createSession(pickedAgent);
    await refresh();
    setCreating(false);
    setActive(s);
    setMessages([]);
  }

  async function send() {
    if (!input.trim() || !active || busy) return;
    const question = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: question }]);
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    setBusy(true);
    try {
      await streamMessage(
        active.id,
        question,
        (tok) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = {
              ...copy[copy.length - 1],
              content: copy[copy.length - 1].content + tok,
            };
            return copy;
          }),
        (cits) =>
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { ...copy[copy.length - 1], citations: cits };
            return copy;
          }),
      );
    } catch (e) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          role: "assistant",
          content: `⚠️ ${(e as Error).message}`,
        };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <Nav />
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* Sessions sidebar */}
        <div
          style={{
            width: 280,
            borderRight: "1px solid var(--border)",
            padding: 14,
            overflowY: "auto",
          }}
        >
          <button style={{ width: "100%", marginBottom: 12 }} onClick={startNew}>
            + New chat
          </button>
          {sessions.map((s) => (
            <div
              key={s.id}
              className="card"
              style={{
                padding: 10,
                marginBottom: 6,
                cursor: "pointer",
                borderColor: active?.id === s.id ? "var(--accent)" : "var(--border)",
              }}
              onClick={() => openSession(s)}
            >
              <div style={{ fontSize: 14 }}>{s.title || "Untitled chat"}</div>
              <div className="muted" style={{ fontSize: 12 }}>
                {s.agent_name || "Unknown agent"}
              </div>
            </div>
          ))}
        </div>

        {/* Main */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {creating ? (
            <div style={{ padding: 24, overflowY: "auto" }}>
              <h3>Pick an agent for this chat</h3>
              {agents.length === 0 && (
                <p className="muted">
                  No agents available. Create one under “Agents” first.
                </p>
              )}
              {agents.map((a) => (
                <label
                  key={a.id}
                  className="card"
                  style={{
                    display: "flex",
                    gap: 10,
                    padding: 12,
                    marginBottom: 8,
                    cursor: "pointer",
                    borderColor:
                      pickedAgent === a.id ? "var(--accent)" : "var(--border)",
                  }}
                >
                  <input
                    type="radio"
                    name="agent"
                    style={{ width: "auto" }}
                    checked={pickedAgent === a.id}
                    onChange={() => setPickedAgent(a.id)}
                  />
                  <div>
                    <div>{a.name}</div>
                    {a.description && (
                      <div className="muted" style={{ fontSize: 12 }}>
                        {a.description}
                      </div>
                    )}
                  </div>
                </label>
              ))}
              <button disabled={!pickedAgent} onClick={confirmNew}>
                Start chat
              </button>
            </div>
          ) : !active ? (
            <div style={{ display: "grid", placeItems: "center", flex: 1 }}>
              <p className="muted">Start a new chat or select an existing one.</p>
            </div>
          ) : (
            <>
              <div
                className="muted"
                style={{
                  padding: "10px 24px",
                  borderBottom: "1px solid var(--border)",
                  fontSize: 13,
                }}
              >
                Agent: {active.agent_name || "Unknown agent"}
              </div>
              <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 24 }}>
                {messages.map((m, i) => (
                  <div key={i} style={{ marginBottom: 18 }}>
                    <div
                      className="muted"
                      style={{ fontSize: 12, marginBottom: 4 }}
                    >
                      {m.role === "user" ? "You" : "Agent"}
                    </div>
                    <div
                      className="card"
                      style={{
                        whiteSpace: "pre-wrap",
                        background:
                          m.role === "user" ? "var(--panel-2)" : "var(--panel)",
                      }}
                    >
                      {m.content || (busy && i === messages.length - 1 ? "…" : "")}
                    </div>
                    {m.citations && m.citations.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <div className="muted" style={{ fontSize: 12 }}>
                          Sources
                        </div>
                        {m.citations.map((c, j) => (
                          <div
                            key={j}
                            className="card"
                            style={{ padding: 10, marginTop: 6, fontSize: 13 }}
                          >
                            <strong>
                              [{j + 1}] {c.filename}
                            </strong>{" "}
                            <span className="muted">· chunk {c.chunk_index}</span>
                            <div className="muted" style={{ marginTop: 4 }}>
                              {c.snippet}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div
                className="row"
                style={{ padding: 16, borderTop: "1px solid var(--border)" }}
              >
                <textarea
                  rows={1}
                  placeholder="Ask about your documents…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                />
                <button disabled={busy || !input.trim()} onClick={send}>
                  Send
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
