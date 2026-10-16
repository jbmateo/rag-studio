"use client";

import type { Document } from "@/lib/types";

export default function SourcesList({
  documents, loading, error, onRetry, unchecked, citedIds, browsingDocId, onToggle, onBrowse, onOpenDocuments,
}: {
  documents: Document[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  unchecked: Set<string>;
  citedIds: Set<string>;
  browsingDocId: string | null;
  onToggle: (id: string) => void;
  onBrowse: (id: string) => void;
  onOpenDocuments: () => void;
}) {
  const ready = documents.filter((d) => d.status === "ready");
  return (
    <section aria-label="Sources" className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-sm font-semibold text-slate-900">Sources</h2>
      {loading ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : error ? (
        <div role="alert" className="space-y-3 text-sm text-red-700">
          <p>Couldn&apos;t load your documents.</p>
          <button type="button" onClick={onRetry}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
            Retry
          </button>
        </div>
      ) : ready.length === 0 ? (
        <div className="space-y-3 text-sm text-slate-500">
          <p>No ready documents — upload some in the Documents tab.</p>
          <button type="button" onClick={onOpenDocuments}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
            Go to Documents
          </button>
        </div>
      ) : (
        <ul className="space-y-2">
          {ready.map((d) => (
            <li key={d.id} className="flex items-start gap-2">
              <input type="checkbox" id={`src-${d.id}`} aria-label={`Include ${d.name}`}
                checked={!unchecked.has(d.id)} onChange={() => onToggle(d.id)}
                className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
              <div className="min-w-0 flex-1">
                <button type="button" onClick={() => onBrowse(d.id)}
                  className={`block max-w-full truncate text-left text-sm hover:text-indigo-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                    browsingDocId === d.id ? "font-semibold text-indigo-600" : "text-slate-800"
                  }`}>
                  {d.name}
                </button>
                <span className="text-xs text-slate-500">{d.chunk_count} {d.chunk_count === 1 ? "chunk" : "chunks"}</span>
                {citedIds.has(d.id) && (
                  <span className="ml-2 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">cited</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
