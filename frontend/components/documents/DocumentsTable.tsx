"use client";

import { useState } from "react";
import { deleteDocument, documentErrorMessage } from "@/lib/api";
import type { Document } from "@/lib/types";

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function Status({ doc }: { doc: Document }) {
  if (doc.status === "processing")
    return (
      <span className="inline-flex items-center gap-2 text-slate-600">
        <span aria-hidden className="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />
        Processing…
      </span>
    );
  if (doc.status === "ready")
    return (
      <span className="text-emerald-700">
        Ready · {doc.chunk_count} {doc.chunk_count === 1 ? "chunk" : "chunks"}
      </span>
    );
  return <span className="text-red-600" title={doc.error ?? undefined}>Failed</span>;
}

export default function DocumentsTable({ documents, onChanged }: { documents: Document[]; onChanged: () => Promise<void> | void }) {
  const [error, setError] = useState<string | null>(null);

  async function onDelete(doc: Document) {
    if (!window.confirm(`Delete ${doc.name}? This cannot be undone.`)) return;
    setError(null);
    try {
      await deleteDocument(doc.id);
      await onChanged();
    } catch (e) {
      setError(documentErrorMessage(e));
    }
  }

  if (documents.length === 0)
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center text-sm text-slate-500">
        No documents yet. Upload a file or import a URL to get started.
      </div>
    );

  const th = "px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500";
  const td = "px-4 py-3 text-slate-700";
  return (
    <div>
      {error && <p role="alert" className="mb-2 text-sm text-red-600">{error}</p>}
      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th scope="col" className={th}>Name</th>
              <th scope="col" className={th}>Type</th>
              <th scope="col" className={th}>Size</th>
              <th scope="col" className={th}>Status</th>
              <th scope="col" className={th}>Uploaded</th>
              <th scope="col" className={th}><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {documents.map((d) => (
              <tr key={d.id}>
                <td className={`${td} font-medium text-slate-900`}>{d.name}</td>
                <td className={td}>{d.source_type}</td>
                <td className={td}>{formatSize(d.size_bytes)}</td>
                <td className={td}><Status doc={d} /></td>
                <td className={td}>{new Date(d.created_at).toLocaleString()}</td>
                <td className={`${td} text-right`}>
                  <button type="button" onClick={() => onDelete(d)}
                    className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
