"use client";

import { useEffect, useState } from "react";
import Header from "@/components/Header";
import { me } from "@/lib/api";

export default function Home() {
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    me().then((u) => setEmail(u.email)).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <Header email={email} />
      <main className="mx-auto max-w-6xl px-6 py-10">
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center text-sm text-slate-500">
          Your workspace will appear here.
        </div>
      </main>
    </div>
  );
}
