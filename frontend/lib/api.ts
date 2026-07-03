"use client";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const TOKEN_KEY = "rag_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function handle(res: Response) {
  if (res.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `Request failed: ${res.status}`);
  }
  return res.status === 204 ? null : res.json();
}

// --- Types ---
export interface KB {
  id: string;
  name: string;
  owner_user_id: string | null;
  owner_team_id: string | null;
  created_at: string;
}
export interface Doc {
  id: string;
  filename: string;
  status: string;
  error: string | null;
  chunk_count: number;
}
export interface Session {
  id: string;
  title: string | null;
  agent_id: string | null;
  agent_name: string | null;
  created_at: string;
}
export interface Agent {
  id: string;
  owner_user_id: string;
  name: string;
  description: string | null;
  system_prompt: string;
  kb_ids: string[];
  model_name: string;
  temperature: number;
  retrieval_top_k: number;
  retrieval_threshold: number;
  created_at: string;
}
export interface AgentInput {
  name: string;
  system_prompt: string;
  description?: string | null;
  kb_ids?: string[];
  model_name?: string | null;
  temperature?: number | null;
  retrieval_top_k?: number | null;
  retrieval_threshold?: number | null;
}
export interface AgentAccessEntry {
  user_id: string;
  email: string;
  display_name: string | null;
}
export interface Citation {
  document_id: string;
  kb_id: string;
  filename: string;
  chunk_index: number;
  snippet: string;
}

// --- Auth ---
export async function login(email: string, password: string): Promise<string> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const data = await handle(res);
  return data.access_token as string;
}

// --- KB ---
export async function listKBs(): Promise<KB[]> {
  return handle(await fetch(`${API_BASE}/kb`, { headers: authHeaders() }));
}
export async function createKB(name: string, team_id?: string): Promise<KB> {
  return handle(
    await fetch(`${API_BASE}/kb`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ name, team_id: team_id || null }),
    }),
  );
}
export async function deleteKB(id: string): Promise<void> {
  await handle(
    await fetch(`${API_BASE}/kb/${id}`, { method: "DELETE", headers: authHeaders() }),
  );
}

// --- Documents ---
export async function listDocs(kbId: string): Promise<Doc[]> {
  return handle(
    await fetch(`${API_BASE}/kb/${kbId}/documents`, { headers: authHeaders() }),
  );
}
export async function uploadDoc(kbId: string, file: File): Promise<Doc> {
  const form = new FormData();
  form.append("file", file);
  return handle(
    await fetch(`${API_BASE}/kb/${kbId}/documents`, {
      method: "POST",
      headers: authHeaders(),
      body: form,
    }),
  );
}
export async function deleteDoc(kbId: string, docId: string): Promise<void> {
  await handle(
    await fetch(`${API_BASE}/kb/${kbId}/documents/${docId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }),
  );
}

// --- Agents ---
export async function listAgents(): Promise<Agent[]> {
  return handle(await fetch(`${API_BASE}/agents`, { headers: authHeaders() }));
}
export async function createAgent(input: AgentInput): Promise<Agent> {
  return handle(
    await fetch(`${API_BASE}/agents`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(input),
    }),
  );
}
export async function updateAgent(
  id: string,
  input: Partial<AgentInput>,
): Promise<Agent> {
  return handle(
    await fetch(`${API_BASE}/agents/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(input),
    }),
  );
}
export async function deleteAgent(id: string): Promise<void> {
  await handle(
    await fetch(`${API_BASE}/agents/${id}`, {
      method: "DELETE",
      headers: authHeaders(),
    }),
  );
}
export async function listAgentAccess(id: string): Promise<AgentAccessEntry[]> {
  return handle(
    await fetch(`${API_BASE}/agents/${id}/access`, { headers: authHeaders() }),
  );
}
export async function grantAgentAccess(
  id: string,
  email: string,
): Promise<AgentAccessEntry> {
  return handle(
    await fetch(`${API_BASE}/agents/${id}/access`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ email }),
    }),
  );
}
export async function revokeAgentAccess(
  id: string,
  userId: string,
): Promise<void> {
  await handle(
    await fetch(`${API_BASE}/agents/${id}/access/${userId}`, {
      method: "DELETE",
      headers: authHeaders(),
    }),
  );
}

// --- Chat ---
export async function listSessions(): Promise<Session[]> {
  return handle(await fetch(`${API_BASE}/chat/sessions`, { headers: authHeaders() }));
}
export async function createSession(
  agent_id: string,
  title?: string,
): Promise<Session> {
  return handle(
    await fetch(`${API_BASE}/chat/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ agent_id, title: title || null }),
    }),
  );
}
export async function getHistory(
  sessionId: string,
): Promise<{ role: string; content: string }[]> {
  return handle(
    await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages`, {
      headers: authHeaders(),
    }),
  );
}

/**
 * Send a message and stream the reply. Parses the SSE events emitted by the
 * backend (token / citations / done / error).
 */
export async function streamMessage(
  sessionId: string,
  content: string,
  onToken: (t: string) => void,
  onCitations: (c: Citation[]) => void,
): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ content }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Chat failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const evt of events) {
      let event = "";
      let data = "";
      for (const line of evt.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      if (event === "token") onToken(JSON.parse(data).content);
      else if (event === "citations") onCitations(JSON.parse(data));
      else if (event === "error") throw new Error(JSON.parse(data).detail);
    }
  }
}
