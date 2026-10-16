"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, askErrorMessage, askQuestion, documentErrorMessage, listChunks, useDocuments } from "@/lib/api";
import type { AskResponse } from "@/lib/types";
import AnswerPane, { type AnswerError } from "./AnswerPane";
import ChunksList, { fromAskChunk, fromChunkRow } from "./ChunksList";
import SearchBar from "./SearchBar";
import SourcesList from "./SourcesList";

type CardList = ReturnType<typeof fromChunkRow>[];

export default function Dashboard({ onOpenDocuments }: { onOpenDocuments: () => void }) {
  const { documents, loading: docsLoading } = useDocuments();
  const [unchecked, setUnchecked] = useState<Set<string>>(new Set());
  const [answer, setAnswer] = useState<AskResponse | null>(null);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<AnswerError | null>(null);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);
  const [highlightedChunkId, setHighlightedChunkId] = useState<string | null>(null);
  const [browsingDocId, setBrowsingDocId] = useState<string | null>(null);
  const [browseChunks, setBrowseChunks] = useState<CardList>([]);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [browseError, setBrowseError] = useState<string | null>(null);
  const requestId = useRef(0);

  const ready = useMemo(() => documents.filter((d) => d.status === "ready"), [documents]);
  const selected = ready.filter((d) => !unchecked.has(d.id));
  const noneSelected = ready.length > 0 && selected.length === 0;

  const ask = useCallback(async (question: string) => {
    const id = ++requestId.current;
    setLastQuestion(question);
    setAsking(true);
    setError(null);
    setBrowsingDocId(null);
    setHighlightedChunkId(null);
    const sel = ready.filter((d) => !unchecked.has(d.id));
    const docIds = sel.length === ready.length ? null : sel.map((d) => d.id);
    try {
      const res = await askQuestion(question, docIds);
      if (id !== requestId.current) return;
      setAnswer(res);
    } catch (e) {
      if (id !== requestId.current) return;
      setAnswer(null);
      if (e instanceof ApiError && e.status === 400 && e.detail === "Upload a document first")
        setError({ kind: "info", message: "Upload a document first" });
      else setError({ kind: "error", message: askErrorMessage(e) });
    } finally {
      if (id === requestId.current) setAsking(false);
    }
  }, [ready, unchecked]);

  useEffect(() => {
    if (!browsingDocId) return;
    let cancelled = false;
    setBrowseLoading(true);
    setBrowseError(null);
    listChunks(browsingDocId)
      .then((rows) => !cancelled && setBrowseChunks(rows.map(fromChunkRow)))
      .catch((e) => !cancelled && setBrowseError(documentErrorMessage(e)))
      .finally(() => !cancelled && setBrowseLoading(false));
    return () => {
      cancelled = true;
    };
  }, [browsingDocId]);

  const citedIds = useMemo(
    () => new Set((answer?.citations ?? []).map((c) => c.document_id).filter((x): x is string => !!x)),
    [answer],
  );

  const evidence = useMemo(() => {
    if (!answer) return [];
    const pages = new Map(answer.citations.filter((c) => c.chunk_id).map((c) => [c.chunk_id as string, c.page]));
    return answer.chunks.map((c) => fromAskChunk(c, pages.get(c.chunk_id) ?? null));
  }, [answer]);

  const browsing = browsingDocId !== null;
  const browsedName = documents.find((d) => d.id === browsingDocId)?.name ?? "document";

  return (
    <div className="space-y-6">
      <SearchBar loading={asking} disabled={noneSelected} onAsk={ask} />
      {noneSelected && <p className="-mt-3 text-xs text-slate-500">Select at least one source to ask a question.</p>}
      <div className="grid gap-6 lg:grid-cols-[1fr_2fr_1.5fr]">
        <div className="min-w-0">
          <SourcesList
            documents={documents} loading={docsLoading} unchecked={unchecked} citedIds={citedIds}
            browsingDocId={browsingDocId} onOpenDocuments={onOpenDocuments}
            onToggle={(id) => setUnchecked((prev) => {
              const next = new Set(prev);
              if (!next.delete(id)) next.add(id);
              return next;
            })}
            onBrowse={(id) => {
              setBrowseChunks([]);
              setHighlightedChunkId(null);
              setBrowsingDocId(id);
            }}
          />
        </div>
        <div className="min-w-0">
          <AnswerPane
            answer={answer} loading={asking} error={error} highlightedChunkId={highlightedChunkId}
            onCite={(chunkId) => {
              setBrowsingDocId(null);
              setHighlightedChunkId(chunkId);
            }}
            onRetry={() => lastQuestion && ask(lastQuestion)}
          />
        </div>
        <div className="min-w-0">
          {browsing ? (
            <ChunksList
              title={`Chunks in ${browsedName}`} chunks={browseChunks} highlightedChunkId={null}
              loading={browseLoading} error={browseError} emptyText="This document has no chunks."
              onBack={answer ? () => setBrowsingDocId(null) : undefined}
            />
          ) : (
            <ChunksList
              title={answer ? `Retrieved evidence (${evidence.length})` : "Retrieved evidence"}
              chunks={evidence} highlightedChunkId={highlightedChunkId} loading={false} error={null}
              emptyText={answer ? "No evidence was retrieved." : "Retrieved evidence appears here."}
            />
          )}
        </div>
      </div>
    </div>
  );
}
