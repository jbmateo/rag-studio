"use client";

import { logout } from "@/lib/api";

export default function Header({ email }: { email: string | null }) {
  async function onLogout() {
    try {
      await logout();
    } finally {
      window.location.href = "/login";
    }
  }
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <span className="text-base font-semibold text-slate-900">RAG Studio</span>
        <div className="flex items-center gap-4 text-sm">
          {email && <span className="text-slate-600">{email}</span>}
          <button onClick={onLogout}
            className="rounded-lg border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
            Log out
          </button>
        </div>
      </div>
    </header>
  );
}
