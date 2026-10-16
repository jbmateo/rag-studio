"use client";

import { useState } from "react";
import { logout } from "@/lib/api";

export default function Header({ email }: { email: string | null }) {
  const [error, setError] = useState<string | null>(null);

  async function onLogout() {
    setError(null);
    try {
      await logout();
    } catch {
      setError("Couldn't log out. Please try again.");
      return;
    }
    window.location.href = "/login";
  }
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
        <span className="text-base font-semibold text-slate-900">RAG Studio</span>
        <div className="flex items-center gap-4 text-sm">
          {error && <span role="alert" className="text-xs text-red-600">{error}</span>}
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
