"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/app/components/Nav";
import {
  Citation,
  createSession,
  getHistory,
  getToken,
  KB,
  listKBs,
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
  const [kbs, setKbs] = useState<KB[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<Session | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [picker, setPicker] = useState<Set<string>>(new Set());
  const [creating, setCreating] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const refresh = useCallback(async () => {
    const [k, s] = await Promise.all([listKBs(), listSessions()]);
    setKbs(k);
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
    setPicker(new Set());
  }

  function togglePick(id: string) {
    setPicker((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function confirmNew() {
    if (picker.size === 0) return;
    const s = await createSession([...picker]);
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

  const kbName = (id: string) => kbs.find((k) => k.id === id)?.name || id.slice(0, 8);

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
                {s.kb_ids.map(kbName).join(", ")}
              </div>
            </div>
          ))}
        </div>

        {/* Main */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0 }}>
          {creating ? (
            <div style={{ padding: 24, overflowY: "auto" }}>
              <h3>Select knowledge base(s) for this chat</h3>
              {kbs.length === 0 && (
                <p className="muted">
                  No knowledge bases. Create one under “Knowledge Bases” first.
                </p>
              )}
              {kbs.map((k) => (
                <label
                  key={k.id}
                  className="card"
                  style={{ display: "flex", gap: 10, padding: 12, marginBottom: 8 }}
                >
                  <input
                    type="checkbox"
                    style={{ width: "auto" }}
                    checked={picker.has(k.id)}
                    onChange={() => togglePick(k.id)}
                  />
                  <span>{k.name}</span>
                  <span className="badge">{k.owner_team_id ? "team" : "personal"}</span>
                </label>
              ))}
              <button disabled={picker.size === 0} onClick={confirmNew}>
                Start chat
              </button>
            </div>
          ) : !active ? (
            <div style={{ display: "grid", placeItems: "center", flex: 1 }}>
              <p className="muted">Start a new chat or select an existing one.</p>
            </div>
          ) : (
            <>
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
