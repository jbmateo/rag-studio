"use client";

import type { AskResponse } from "@/lib/types";

export interface AnswerError {
  kind: "info" | "error";
  message: string;
}

const card = "rounded-2xl border border-slate-200 bg-white p-5 shadow-sm";

function Banner({ tone, children }: { tone: "amber" | "red" | "sky" | "slate"; children: React.ReactNode }) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    red: "border-red-200 bg-red-50 text-red-800",
    sky: "border-sky-200 bg-sky-50 text-sky-900",
    slate: "border-slate-200 bg-slate-50 text-slate-700",
  };
  return <div className={`rounded-xl border px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>;
}

export default function AnswerPane({
  answer, loading, error, highlightedChunkId, onCite, onRetry,
}: {
  answer: AskResponse | null;
  loading: boolean;
  error: AnswerError | null;
  highlightedChunkId: string | null;
  onCite: (chunkId: string) => void;
  onRetry: () => void;
}) {
  return (
    <section aria-label="Answer" aria-busy={loading} className={`${card} min-h-40 space-y-4`}>
      {loading && <p className="text-sm text-slate-500">Searching your documents…</p>}
      {error?.kind === "info" && <Banner tone="sky">{error.message}</Banner>}
      {error?.kind === "error" && (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <span>{error.message}</span>
          <button type="button" onClick={onRetry}
            className="rounded-lg border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500">
            Retry
          </button>
        </div>
      )}
      {!answer && !error && !loading && (
        <p className="text-sm text-slate-500">
          Ask a question about your documents. Answers cite their sources, and the system says so when the documents don&apos;t contain the answer.
        </p>
      )}
      {answer && !loading && (
        <>
          {answer.status === "not_found" && <Banner tone="slate">Not found in your documents</Banner>}
          {answer.status === "partial" && <Banner tone="amber">Partial answer — not covered: {answer.missing}</Banner>}
          {answer.status === "insufficient_evidence" && (
            <Banner tone="amber">
              The documents don&apos;t contain enough evidence to answer this.
              {answer.missing && <span className="mt-1 block">Not covered: {answer.missing}</span>}
            </Banner>
          )}
          {answer.sentences.length > 0 && (
            <p className="text-[15px] leading-7 text-slate-800">
              {answer.sentences.map((s, i) => (
                <span key={i}>
                  {s.text}
                  {s.citations.map((n) => {
                    const cite = answer.citations.find((c) => c.n === n);
                    const chunkId = cite?.chunk_id ?? null;
                    const active = chunkId !== null && chunkId === highlightedChunkId;
                    return (
                      <button key={n} type="button" aria-label={`Citation ${n}`} disabled={chunkId === null}
                        title={cite ? `${cite.document_name} · ${cite.location}` : undefined}
                        onClick={() => chunkId && onCite(chunkId)}
                        className={`mx-0.5 rounded-md px-1.5 py-0.5 align-baseline text-xs font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50 ${
                          active ? "bg-indigo-600 text-white" : "bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
                        }`}>
                        [{n}]
                      </button>
                    );
                  })}{" "}
                </span>
              ))}
            </p>
          )}
          {answer.dropped_citations > 0 && (
            <p className="text-xs text-slate-500">
              {answer.dropped_citations} unsupported {answer.dropped_citations === 1 ? "citation" : "citations"} removed
            </p>
          )}
        </>
      )}
    </section>
  );
}
