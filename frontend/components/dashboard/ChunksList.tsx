"use client";

import { useEffect } from "react";
import type { AskChunk, ChunkRow } from "@/lib/types";

interface CardProps {
  id: string;
  documentId: string;
  documentName: string;
  location: string;
  text: string;
  page: number | null;
  score?: number;
  vectorRank?: number | null;
  bm25Rank?: number | null;
}

export function fromAskChunk(c: AskChunk, page: number | null): CardProps {
  return {
    id: c.chunk_id, documentId: c.document_id, documentName: c.document_name, location: c.location,
    text: c.text, page, score: c.score, vectorRank: c.vector_rank, bm25Rank: c.bm25_rank,
  };
}

export function fromChunkRow(c: ChunkRow): CardProps {
  return {
    id: c.id, documentId: c.document_id, documentName: c.document_name, location: c.location,
    text: c.text, page: c.page,
  };
}

const badge = "rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600";

export default function ChunksList({
  title, chunks, highlightedChunkId, loading, error, emptyText, onBack,
}: {
  title: string;
  chunks: CardProps[];
  highlightedChunkId: string | null;
  loading: boolean;
  error: string | null;
  emptyText: string;
  onBack?: () => void;
}) {
  useEffect(() => {
    if (!highlightedChunkId) return;
    document.getElementById(`chunk-${highlightedChunkId}`)?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [highlightedChunkId, chunks]);

  return (
    <section aria-label="Evidence" className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {onBack && (
          <button type="button" onClick={onBack}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
            Back to evidence
          </button>
        )}
      </div>
      {loading && <p className="text-sm text-slate-500">Loading…</p>}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      {!loading && !error && chunks.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">{emptyText}</div>
      )}
      {chunks.map((c) => {
        const highlighted = c.id === highlightedChunkId;
        const href = `/api/documents/${c.documentId}/file${c.page != null ? `#page=${c.page}` : ""}`;
        return (
          <article key={c.id} id={`chunk-${c.id}`} data-highlighted={highlighted ? "true" : "false"}
            className={`rounded-2xl border bg-white p-4 shadow-sm ${highlighted ? "border-indigo-500 ring-2 ring-indigo-200" : "border-slate-200"}`}>
            <div className="mb-2 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
              <span className="max-w-full truncate font-medium text-slate-800">{c.documentName}</span>
              <span>· {c.location}</span>
            </div>
            {(c.score !== undefined || c.vectorRank != null || c.bm25Rank != null) && (
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                {c.score !== undefined && <span className={badge}>score {c.score.toFixed(3)}</span>}
                {c.vectorRank != null && <span className={badge}>vector #{c.vectorRank}</span>}
                {c.bm25Rank != null && <span className={badge}>BM25 #{c.bm25Rank}</span>}
              </div>
            )}
            <p className="whitespace-pre-wrap break-words text-sm leading-6 text-slate-700">{c.text}</p>
            <a href={href} target="_blank" rel="noreferrer"
              className="mt-3 inline-block text-xs font-medium text-indigo-600 hover:text-indigo-500 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
              View in document
            </a>
          </article>
        );
      })}
    </section>
  );
}
