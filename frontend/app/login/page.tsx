"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, setToken } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("alice@vng.com.vn");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const token = await login(email, password);
      setToken(token);
      router.replace("/chat");
    } catch {
      setError("Incorrect email or password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", placeItems: "center", height: "100vh" }}>
      <form onSubmit={submit} className="card" style={{ width: 360 }}>
        <h2 style={{ marginTop: 0 }}>RAG Chat Agent</h2>
        <p className="muted" style={{ marginTop: -8 }}>Sign in to continue</p>
        <div style={{ display: "grid", gap: 12 }}>
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
          </label>
          <label>
            Password
            <input
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              type="password"
            />
          </label>
          {error && <div style={{ color: "#ff7676" }}>{error}</div>}
          <button disabled={busy} type="submit">
            {busy ? "Signing in…" : "Sign in"}
          </button>
          <p className="muted" style={{ fontSize: 13 }}>
            Seeded users: alice / bob / carol @vng.com.vn · password123
          </p>
        </div>
      </form>
    </div>
  );
}
