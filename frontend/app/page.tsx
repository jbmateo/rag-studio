"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Header from "@/components/Header";
import Tabs from "@/components/Tabs";
import DocumentsTab from "@/components/documents/DocumentsTab";
import { me } from "@/lib/api";

function Workspace() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState<string | null>(null);
  const active = params.get("tab") === "documents" ? "documents" : "dashboard";

  useEffect(() => {
    me().then((u) => setEmail(u.email)).catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-slate-50">
      <Header email={email} />
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Tabs
          active={active}
          onChange={(id) => router.replace(id === "dashboard" ? "/" : `/?tab=${id}`)}
          tabs={[
            {
              id: "dashboard",
              label: "Dashboard",
              panel: (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center text-sm text-slate-500">
                  Dashboard coming soon
                </div>
              ),
            },
            { id: "documents", label: "Documents", panel: <DocumentsTab /> },
          ]}
        />
      </main>
    </div>
  );
}

export default function Home() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
