# RAG Studio — Design Spec

**Date:** 2026-10-17
**Status:** Approved design, pending implementation plan

## 1. Purpose

A portfolio project demonstrating knowledge-based AI: a multi-user web app where users upload documents and ask questions answered **only** from those documents, with clickable citations, and an explicit refusal when the evidence is missing.

Audience: interviewers / reviewers. Success means:
- A reviewer can clone, run one command, sign up, upload, ask, and click a citation to the exact supporting chunk.
- Off-topic or unsupported questions are refused rather than guessed.
- Measurable rigor: an eval script reports refusal accuracy and citation validity.

Built fresh; the earlier `rag-doc-qa` Streamlit prototype is not reused.

## 2. Repository layout

One git repo, two sibling apps:

```
rag-studio/
├── frontend/        Next.js 15 (App Router, TypeScript, Tailwind)
├── backend/         FastAPI, Python 3.11+, own .venv
│   ├── app/         auth, ingest, retrieve, answer, storage modules
│   ├── tests/
│   ├── evals/       sample docs, labelled questions, run_eval.py, results.md
│   └── storage/     uploaded originals (gitignored) + app.db (gitignored)
├── docs/superpowers/specs/
├── Makefile         `make setup`, `make dev` (runs both), `make test`, `make eval`
└── README.md
```

The frontend reaches the backend only over HTTP. Next.js rewrites `/api/*` to FastAPI (`http://localhost:8000`) so cookies are same-origin and no CORS is needed.

## 3. Stack

| Concern | Choice |
|---|---|
| UI | Next.js 15, React, TypeScript, Tailwind |
| API | FastAPI + Uvicorn |
| DB | SQLite (single file), FTS5 for BM25 |
| Embeddings | fastembed `BAAI/bge-small-en-v1.5` (384-dim, local, no API key), stored as float32 blobs; brute-force cosine via numpy |
| LLM | Anthropic Claude `claude-sonnet-5-5` via tool use |
| Parsing | pypdf (PDF), python-docx (DOCX), trafilatura (HTML), httpx (URL fetch) |
| Auth | bcrypt password hashes, server-side sessions, httpOnly cookie |
| Tests | pytest (+ FastAPI TestClient), Playwright smoke test |

Python 3.11+ must be installed (system has 3.9); README documents `brew install python@3.12` or uv.

## 4. Data model (SQLite)

- `users(id, email UNIQUE, password_hash, created_at)`
- `sessions(token_hash PK, user_id FK, expires_at, created_at)`
- `documents(id, user_id FK, name, source_type[pdf|docx|md|txt|html|url], source_url NULL, file_path, size_bytes, status[processing|ready|failed], error NULL, chunk_count, created_at)`
- `chunks(id, document_id FK ON DELETE CASCADE, user_id, ordinal, text, location TEXT, page INT NULL, char_start, char_end, embedding BLOB)`
- `chunks_fts` — FTS5 virtual table over `chunks.text`, kept in sync via triggers.

All document/chunk access goes through a data-layer function that requires `user_id`.

## 5. Auth & sessions

- Sign up: email + password (min 8 chars), bcrypt-hashed. Signs the user in.
- Log in: issues a random 256-bit token; only its SHA-256 is stored. Cookie `session`: httpOnly, `SameSite=Lax`, `Secure` in production.
- "Remember me" (default on): 30-day persistent cookie with sliding expiry; unchecked = browser-session cookie (server-side expiry 24h).
- Uniform "Invalid email or password" on failure; in-memory rate limit of 5 login attempts/min/IP.
- Log out deletes the session row and clears the cookie.
- Next.js middleware redirects unauthenticated requests to `/login`; any API 401 also redirects.

Endpoints: `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.

## 6. Ingestion

1. `POST /api/documents` — multipart file **or** JSON `{url}`. Validates type (pdf, docx, md, txt, html) and size (≤ 20 MB). Saves original to `storage/{user_id}/{doc_id}.{ext}`, inserts `documents` row with `status=processing`, returns it immediately.
2. Background task (FastAPI `BackgroundTasks`) parses into location-labelled text segments:
   - PDF → one segment per page, location `p. N`, `page=N`
   - DOCX → segments per heading section, location = heading text
   - MD/TXT → split on headings (MD) or blank-line blocks, location = heading or `¶ N`
   - HTML/URL → trafilatura main text; URL fetch is http/https only, blocks private/loopback/link-local IPs, 10 s timeout, 5 MB cap; fetched HTML is saved as the original
3. Chunking: ~500 tokens (approximated as ~2,000 chars), ~15% overlap, splitting on paragraph then sentence boundaries; chunks never cross segment boundaries.
4. Embed all chunks (batched), insert chunks + FTS rows in one transaction.
5. Set `status=ready`, `chunk_count`. On any failure: roll back partial chunks, set `status=failed` with a human-readable `error` (e.g. "No extractable text — scanned PDFs need OCR (not supported)").

Other document endpoints:
- `GET /api/documents` — list the caller's documents.
- `DELETE /api/documents/{id}` — deletes row (cascade chunks + FTS) in a transaction, then best-effort file removal.
- `GET /api/documents/{id}/file` — streams the original with correct content type.
- `GET /api/documents/{id}/chunks` — paginated chunks for browsing.

Another user's `doc_id` returns 404.

## 7. Question answering

`POST /api/ask {question, doc_ids?: string[]}`

1. **Scope:** the caller's `ready` documents, optionally restricted to `doc_ids`. If none: `400 "Upload a document first"`.
2. **Hybrid retrieval:** top 20 by cosine similarity + top 20 by FTS5 BM25 → reciprocal rank fusion (k=60) → top 8.
3. **Gate 1 — relevance:** if max cosine similarity < `MIN_SIMILARITY` (config, start 0.35) **and** no chunk contains at least half of the question's non-stopword terms (a "strong BM25 hit" — this keeps exact-term queries like codes or names from being refused), return `status: "not_found"` with the closest chunks for transparency. No LLM call.
4. **Generation:** chunks are labelled `c1…c8` with document name + location. System prompt: answer only from the passages; every sentence must cite; if the passages don't answer, say so. Claude must call tool `submit_answer`:
   ```json
   {
     "status": "answered | partial | insufficient_evidence",
     "sentences": [{"text": "string", "citations": ["c1"]}],
     "missing": "string — what the documents don't cover (for partial/insufficient)"
   }
   ```
5. **Gate 2 — citation verification (server):** drop citation IDs not in the retrieved set; drop sentences with no remaining valid citation; if no sentences survive, force `status = insufficient_evidence`. Count dropped items in the response for transparency.
6. **Response:**
   ```json
   {
     "status": "answered | partial | insufficient_evidence | not_found",
     "sentences": [{"text": "...", "citations": [1, 3]}],
     "missing": "...",
     "citations": [{"n": 1, "chunk_id": "...", "document_id": "...", "document_name": "...", "location": "p. 4", "page": 4}],
     "chunks": [{"chunk_id": "...", "document_id": "...", "document_name": "...", "location": "...", "text": "...", "score": 0.0, "vector_rank": 1, "bm25_rank": 3}],
     "dropped_citations": 0,
     "timings_ms": {"retrieve": 0, "generate": 0}
   }
   ```
   Citation numbers are assigned in first-appearance order.
7. **Errors:** Claude API error/timeout (30 s) → `502` with retryable message, never a fabricated answer. Malformed tool output → one retry, then `insufficient_evidence`.

## 8. Frontend

Routes: `/login`, `/signup`, `/` (protected).

`/` has a header (app name, user email, log out) and two tabs (state in URL `?tab=documents`):

**Dashboard tab**
- **Search bar** at top (Enter or button submits; loading state).
- **Answer pane:** rendered sentences with inline citation badges `[1]`; status banner for `partial` (shows `missing`), `insufficient_evidence`, and `not_found` ("Not found in your documents"). Error banner with retry.
- **Sources list:** user's ready documents with checkboxes to scope the search (all checked by default); documents cited in the current answer are marked.
- **Chunks list:** after a question, shows retrieved chunks (doc name, location, score, rank badges); before a question, browsing a selected source shows its chunks.
- **Citation click:** scrolls the chunks list to the cited chunk and highlights it; the chunk card has "View in document" opening `/api/documents/{id}/file` (with `#page=N` for PDFs) in a new tab.

Layout (desktop): search bar full width; below, a left column with Sources, a center column with the Answer pane, a right column with Chunks. Stacks vertically on narrow screens.

**Documents tab**
- Drag-and-drop / file-picker upload (multiple files) and a "Import from URL" input.
- Table: name, type, size, status (processing spinner / ready with chunk count / failed with error tooltip), uploaded date, delete button with confirm dialog.
- Polls `GET /api/documents` every 2 s while any document is `processing`.

## 9. Testing & evaluation

**Backend unit (pytest):** chunker (boundaries, overlap, locations), each parser with small fixtures, RRF fusion, citation verifier (fake IDs dropped; uncited sentences dropped; all dropped → refusal), URL safety checks.

**Backend API (TestClient, temp DB, Claude stubbed):** signup/login/me/logout, remember-me cookie attributes, rate limit, cross-user isolation (B cannot list/read/delete/ask over A's docs), upload → ready → list → chunks → delete, Gate 1 path makes no LLM call.

**Eval harness** (`backend/evals/run_eval.py`, uses real Claude): bundled sample documents + ~20 labelled questions (~12 answerable with expected supporting document/location, ~8 plausible but unanswerable). Reports retrieval hit@8, answer rate on answerable, refusal precision/recall on unanswerable, citation validity rate. Writes `evals/results.md`.

**Frontend:** `tsc --noEmit`, lint, and one Playwright smoke test: sign up → upload sample PDF → wait for ready → ask → click `[1]` → chunk highlighted → ask off-topic → refusal shown.

## 10. Configuration

`backend/.env`: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default `claude-sonnet-5-5`), `MIN_SIMILARITY`, `DATABASE_PATH`, `STORAGE_DIR`, `COOKIE_SECURE`. `.env.example` committed; `.env` gitignored.

## 11. Out of scope (v1)

OCR for scanned PDFs, streaming responses, chat history / follow-ups, password reset / email verification, deployment, document sharing between users. Listed in README as next steps.
