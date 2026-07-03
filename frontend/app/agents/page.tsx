"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/app/components/Nav";
import {
  Agent,
  AgentAccessEntry,
  AgentInput,
  createAgent,
  deleteAgent,
  getToken,
  grantAgentAccess,
  KB,
  listAgentAccess,
  listAgents,
  listKBs,
  revokeAgentAccess,
  updateAgent,
} from "@/lib/api";

const EMPTY: AgentInput = {
  name: "",
  system_prompt: "",
  description: "",
  kb_ids: [],
  temperature: 0.2,
  retrieval_top_k: 5,
  retrieval_threshold: 0,
};

export default function AgentsPage() {
  const router = useRouter();
  const [agents, setAgents] = useState<Agent[]>([]);
  const [kbs, setKbs] = useState<KB[]>([]);
  const [editing, setEditing] = useState<Agent | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<AgentInput>(EMPTY);
  const [access, setAccess] = useState<AgentAccessEntry[]>([]);
  const [grantEmail, setGrantEmail] = useState("");
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const refresh = useCallback(async () => {
    const [a, k] = await Promise.all([listAgents(), listKBs()]);
    setAgents(a);
    setKbs(k);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  function startCreate() {
    setCreating(true);
    setEditing(null);
    setForm(EMPTY);
    setAccess([]);
    setErr(null);
  }

  async function startEdit(a: Agent) {
    setCreating(false);
    setEditing(a);
    setErr(null);
    setForm({
      name: a.name,
      system_prompt: a.system_prompt,
      description: a.description || "",
      kb_ids: a.kb_ids,
      model_name: a.model_name,
      temperature: a.temperature,
      retrieval_top_k: a.retrieval_top_k,
      retrieval_threshold: a.retrieval_threshold,
    });
    setAccess(await listAgentAccess(a.id));
  }

  function toggleKb(id: string) {
    setForm((f) => {
      const set = new Set(f.kb_ids || []);
      set.has(id) ? set.delete(id) : set.add(id);
      return { ...f, kb_ids: [...set] };
    });
  }

  async function save() {
    if (!form.name.trim() || !form.system_prompt.trim()) {
      setErr("Name and instruction are required.");
      return;
    }
    setErr(null);
    try {
      if (editing) {
        await updateAgent(editing.id, form);
      } else {
        await createAgent(form);
      }
      await refresh();
      setCreating(false);
      setEditing(null);
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function onDelete(a: Agent) {
    if (!confirm(`Delete agent "${a.name}"?`)) return;
    try {
      await deleteAgent(a.id);
      if (editing?.id === a.id) setEditing(null);
      await refresh();
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function onGrant() {
    if (!editing || !grantEmail.trim()) return;
    try {
      await grantAgentAccess(editing.id, grantEmail.trim());
      setGrantEmail("");
      setAccess(await listAgentAccess(editing.id));
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  async function onRevoke(userId: string) {
    if (!editing) return;
    await revokeAgentAccess(editing.id, userId);
    setAccess(await listAgentAccess(editing.id));
  }

  const showForm = creating || editing;

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <Nav />
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* Agent list */}
        <div
          style={{
            width: 320,
            borderRight: "1px solid var(--border)",
            padding: 16,
            overflowY: "auto",
          }}
        >
          <button style={{ width: "100%", marginBottom: 12 }} onClick={startCreate}>
            + New agent
          </button>
          {agents.length === 0 && <p className="muted">No agents yet.</p>}
          {agents.map((a) => (
            <div
              key={a.id}
              className="card"
              style={{
                marginBottom: 8,
                padding: 12,
                cursor: "pointer",
                borderColor: editing?.id === a.id ? "var(--accent)" : "var(--border)",
              }}
              onClick={() => startEdit(a)}
            >
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div>
                  <div>{a.name}</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {a.kb_ids.length} KB{a.kb_ids.length === 1 ? "" : "s"}
                  </div>
                </div>
                <button
                  className="secondary"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(a);
                  }}
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Form */}
        <div style={{ flex: 1, padding: 24, overflowY: "auto" }}>
          {!showForm ? (
            <p className="muted">Select an agent to edit, or create a new one.</p>
          ) : (
            <div style={{ maxWidth: 640 }}>
              <h2 style={{ marginTop: 0 }}>
                {editing ? `Edit "${editing.name}"` : "New agent"}
              </h2>
              {err && (
                <div style={{ color: "#ff7676", marginBottom: 12 }}>{err}</div>
              )}

              <label className="muted">Name</label>
              <input
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                style={{ marginBottom: 12 }}
              />

              <label className="muted">Description</label>
              <input
                value={form.description || ""}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                style={{ marginBottom: 12 }}
              />

              <label className="muted">Instruction (system prompt)</label>
              <textarea
                rows={6}
                value={form.system_prompt}
                onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
                style={{ marginBottom: 12, width: "100%" }}
              />

              <label className="muted">Knowledge bases</label>
              <div style={{ marginBottom: 12 }}>
                {kbs.length === 0 && (
                  <p className="muted">No knowledge bases you can attach.</p>
                )}
                {kbs.map((k) => (
                  <label
                    key={k.id}
                    className="card"
                    style={{ display: "flex", gap: 10, padding: 10, marginBottom: 6 }}
                  >
                    <input
                      type="checkbox"
                      style={{ width: "auto" }}
                      checked={(form.kb_ids || []).includes(k.id)}
                      onChange={() => toggleKb(k.id)}
                    />
                    <span>{k.name}</span>
                    <span className="badge">
                      {k.owner_team_id ? "team" : "personal"}
                    </span>
                  </label>
                ))}
              </div>

              <div className="row" style={{ gap: 12, marginBottom: 12 }}>
                <div style={{ flex: 1 }}>
                  <label className="muted">Model (blank = default)</label>
                  <input
                    value={form.model_name || ""}
                    onChange={(e) => setForm({ ...form, model_name: e.target.value })}
                  />
                </div>
                <div style={{ width: 110 }}>
                  <label className="muted">Temperature</label>
                  <input
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={form.temperature ?? 0.2}
                    onChange={(e) =>
                      setForm({ ...form, temperature: parseFloat(e.target.value) })
                    }
                  />
                </div>
              </div>

              <div className="row" style={{ gap: 12, marginBottom: 16 }}>
                <div style={{ width: 140 }}>
                  <label className="muted">Retrieval top-k</label>
                  <input
                    type="number"
                    min="1"
                    max="50"
                    value={form.retrieval_top_k ?? 5}
                    onChange={(e) =>
                      setForm({ ...form, retrieval_top_k: parseInt(e.target.value, 10) })
                    }
                  />
                </div>
                <div style={{ width: 160 }}>
                  <label className="muted">Similarity threshold</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0"
                    max="1"
                    value={form.retrieval_threshold ?? 0}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        retrieval_threshold: parseFloat(e.target.value),
                      })
                    }
                  />
                </div>
              </div>

              <div className="row" style={{ gap: 10 }}>
                <button onClick={save}>{editing ? "Save changes" : "Create agent"}</button>
                <button
                  className="secondary"
                  onClick={() => {
                    setCreating(false);
                    setEditing(null);
                  }}
                >
                  Cancel
                </button>
              </div>

              {/* Access grants (edit only) */}
              {editing && (
                <div style={{ marginTop: 28 }}>
                  <h3>Access</h3>
                  <p className="muted" style={{ fontSize: 13 }}>
                    Users you grant can search this agent&apos;s knowledge bases
                    through chat — even KBs they cannot open directly.
                  </p>
                  <div className="row" style={{ marginBottom: 12 }}>
                    <input
                      placeholder="user@vng.com.vn"
                      value={grantEmail}
                      onChange={(e) => setGrantEmail(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && onGrant()}
                    />
                    <button onClick={onGrant}>Grant</button>
                  </div>
                  {access.length === 0 && (
                    <p className="muted">No one else has access.</p>
                  )}
                  {access.map((u) => (
                    <div
                      key={u.user_id}
                      className="card"
                      style={{
                        padding: 10,
                        marginBottom: 6,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span>
                        {u.display_name ? `${u.display_name} · ` : ""}
                        {u.email}
                      </span>
                      <button className="secondary" onClick={() => onRevoke(u.user_id)}>
                        Revoke
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
