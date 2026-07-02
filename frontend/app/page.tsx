"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/chat" : "/login");
  }, [router]);
  return <div style={{ padding: 40 }} className="muted">Loading…</div>;
}
