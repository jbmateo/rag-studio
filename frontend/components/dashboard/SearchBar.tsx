"use client";

import { useState } from "react";

export default function SearchBar({ loading, disabled, onAsk }: { loading: boolean; disabled?: boolean; onAsk: (q: string) => void }) {
  const [value, setValue] = useState("");
  const blank = value.trim() === "";
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!blank && !loading && !disabled) onAsk(value.trim());
      }}
      className="flex flex-col gap-2 sm:flex-row"
    >
      <input
        aria-label="Ask a question"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Ask a question about your documents…"
        className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
      />
      <button
        type="submit"
        disabled={blank || loading || disabled}
        className="rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? "Asking…" : "Ask"}
      </button>
    </form>
  );
}
