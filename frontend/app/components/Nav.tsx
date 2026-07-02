"use client";

import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { clearToken } from "@/lib/api";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  function logout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <div className="topbar">
      <div className="row" style={{ gap: 18 }}>
        <strong>RAG Chat Agent</strong>
        <Link href="/chat" style={{ opacity: pathname === "/chat" ? 1 : 0.6 }}>
          Chat
        </Link>
        <Link href="/kb" style={{ opacity: pathname === "/kb" ? 1 : 0.6 }}>
          Knowledge Bases
        </Link>
      </div>
      <button className="secondary" onClick={logout}>
        Sign out
      </button>
    </div>
  );
}
