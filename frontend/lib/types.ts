export interface User {
  id: string;
  email: string;
}

export type DocStatus = "processing" | "ready" | "failed";

export interface Document {
  id: string;
  name: string;
  source_type: string;
  source_url: string | null;
  size_bytes: number;
  status: DocStatus;
  error: string | null;
  chunk_count: number;
  created_at: string;
}

export interface ChunkRow {
  id: string;
  document_id: string;
  document_name: string;
  ordinal: number;
  text: string;
  location: string;
  page: number | null;
}

export type AskStatus = "answered" | "partial" | "insufficient_evidence" | "not_found";

export interface AskSentence {
  text: string;
  citations: number[];
}

export interface AskCitation {
  n: number;
  chunk_id: string | null;
  document_id: string | null;
  document_name: string;
  location: string;
  page: number | null;
}

export interface AskChunk {
  chunk_id: string;
  document_id: string;
  document_name: string;
  location: string;
  text: string;
  score: number;
  vector_rank: number | null;
  bm25_rank: number | null;
}

export interface AskResponse {
  status: AskStatus;
  sentences: AskSentence[];
  missing: string;
  citations: AskCitation[];
  chunks: AskChunk[];
  dropped_citations: number;
  timings_ms: { retrieve: number; generate: number };
}
