"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Nav from "@/app/components/Nav";
import {
  createKB,
  deleteDoc,
  deleteKB,
  Doc,
  getToken,
  KB,
  listDocs,
  listKBs,
  uploadDoc,
} from "@/lib/api";

export default function KBPage() {
  const router = useRouter();
  const [kbs, setKbs] = useState<KB[]>([]);
  const [selected, setSelected] = useState<KB | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [newName, setNewName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  const refreshKbs = useCallback(async () => {
    setKbs(await listKBs());
  }, []);

  const refreshDocs = useCallback(async (kb: KB) => {
    setDocs(await listDocs(kb.id));
  }, []);

  useEffect(() => {
    refreshKbs();
  }, [refreshKbs]);

  useEffect(() => {
    if (!selected) return;
    refreshDocs(selected);
    // Poll while any document is still ingesting.
    const t = setInterval(() => {
      refreshDocs(selected);
    }, 2000);
    return () => clearInterval(t);
  }, [selected, refreshDocs]);

  async function onCreate() {
    if (!newName.trim()) return;
    const kb = await createKB(newName.trim());
    setNewName("");
    await refreshKbs();
    setSelected(kb);
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selected) return;
    await uploadDoc(selected.id, file);
    if (fileRef.current) fileRef.current.value = "";
    refreshDocs(selected);
  }

  async function onDelete(kb: KB) {
    if (!confirm(`Delete "${kb.name}" and all its documents?`)) return;
    await deleteKB(kb.id);
    if (selected?.id === kb.id) setSelected(null);
    refreshKbs();
  }

  async function onDeleteDoc(doc: Doc) {
    if (!selected) return;
    if (!confirm(`Delete "${doc.filename}"? This removes it from retrieval.`)) return;
    await deleteDoc(selected.id, doc.id);
    refreshDocs(selected);
  }

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <Nav />
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* KB list */}
        <div
          style={{
            width: 320,
            borderRight: "1px solid var(--border)",
            padding: 16,
            overflowY: "auto",
          }}
        >
          <div className="row" style={{ marginBottom: 12 }}>
            <input
              placeholder="New knowledge base"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onCreate()}
            />
            <button onClick={onCreate}>Add</button>
          </div>
          {kbs.length === 0 && <p className="muted">No knowledge bases yet.</p>}
          {kbs.map((kb) => (
            <div
              key={kb.id}
              className="card"
              style={{
                marginBottom: 8,
                padding: 12,
                cursor: "pointer",
                borderColor: selected?.id === kb.id ? "var(--accent)" : "var(--border)",
              }}
              onClick={() => setSelected(kb)}
            >
              <div className="row" style={{ justifyContent: "space-between" }}>
                <div>
                  <div>{kb.name}</div>
                  <div className="badge">{kb.owner_team_id ? "team" : "personal"}</div>
                </div>
                <button
                  className="secondary"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(kb);
                  }}
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Documents */}
        <div style={{ flex: 1, padding: 24, overflowY: "auto" }}>
          {!selected ? (
            <p className="muted">Select a knowledge base to manage its documents.</p>
          ) : (
            <>
              <h2 style={{ marginTop: 0 }}>{selected.name}</h2>
              <div className="row" style={{ marginBottom: 16 }}>
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.docx,.txt,.md"
                  onChange={onUpload}
                />
              </div>
              {docs.length === 0 && <p className="muted">No documents uploaded yet.</p>}
              {docs.map((d) => (
                <div
                  key={d.id}
                  className="card"
                  style={{ marginBottom: 8, padding: 12 }}
                >
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span>{d.filename}</span>
                    <div className="row" style={{ gap: 8 }}>
                      <span className={`badge ${d.status}`}>
                        {d.status}
                        {d.status === "ready" ? ` · ${d.chunk_count} chunks` : ""}
                      </span>
                      <button className="secondary" onClick={() => onDeleteDoc(d)}>
                        ✕
                      </button>
                    </div>
                  </div>
                  {d.error && (
                    <div style={{ color: "#ff7676", fontSize: 13, marginTop: 6 }}>
                      {d.error}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
