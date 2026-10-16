# RAG Studio — R&D Design Spec

**Date:** 2026-10-17
**Status:** Design approved; spec under review

## 1. Purpose

**An R&D project on grounded, abstaining question answering.** The question under study: *how do you build a document-QA system that answers only from evidence, cites it precisely, and refuses when evidence is missing — and how do you measure that?*

The deliverable has two halves:
1. **Research testbed** — a working multi-user web app (upload documents, ask questions, clickable citations, explicit refusals) whose pipeline components are configurable so they can be studied.
2. **Research output** — controlled experiments over that pipeline, reported in `FINDINGS.md` with method, results, charts, and limitations (including negative results).

Success means:
- Each research question (§2) has a reproducible experiment and a written, evidence-backed answer.
- Anyone can clone, run one command, use the app end-to-end, and re-run the experiments with one command.
- The shipped app uses the configuration the experiments found best, and `FINDINGS.md` says why.

## 2. Research questions

| ID | Question | Independent variable | Primary metrics |
|---|---|---|---|
| RQ1 | Does hybrid retrieval beat vector-only and BM25-only on mixed natural-language and exact-term questions? | `retrieval_mode`: vector / bm25 / hybrid | hit@8, MRR |
| RQ2 | How does the relevance threshold trade answer rate against refusal accuracy? | `MIN_SIMILARITY` swept 0.20–0.60 in 0.05 steps | answer rate (answerable), refusal precision/recall (unanswerable); plotted as a trade-off curve |
| RQ3 | Does server-side citation verification catch unsupported or fabricated citations that prompting alone lets through? | `verify_citations`: on / off | citation validity rate, unsupported-sentence rate |
| RQ4 | How does chunk size affect retrieval and answer quality? | `chunk_chars`: 1000 / 2000 / 4000 | hit@8, answer rate, citation validity |

Hypotheses are stated in `FINDINGS.md` before results are recorded. Each run holds all other variables at the default configuration.

Built fresh; the earlier `rag-doc-qa` Streamlit prototype is not reused.

## 3. Repository layout

One git repo, two sibling apps:

```
rag-studio/
├── frontend/        Next.js 15 (App Router, TypeScript, Tailwind)
├── backend/         FastAPI, Python 3.11+, own .venv
│   ├── app/         auth, ingest, retrieve, answer, storage modules
│   ├── tests/
│   ├── research/    corpus/, questions.jsonl, experiments/*.yaml, run_experiment.py,
│   │                results/ (raw JSONL per run, committed), plots/
│   └── storage/     uploaded originals (gitignored) + app.db (gitignored)
├── docs/            design/ (specs), plans/ (implementation plans)
├── FINDINGS.md      research report: questions, hypotheses, method, results, limitations
├── Makefile         `make setup`, `make dev` (runs both), `make test`, `make experiments`
└── README.md        project overview, links to FINDINGS.md, how to run app + experiments
```

The frontend reaches the backend only over HTTP. Next.js rewrites `/api/*` to FastAPI (`http://localhost:8000`) so cookies are same-origin and no CORS is needed.

## 4. Stack

| Concern | Choice |
|---|---|
| UI | Next.js 15, React, TypeScript, Tailwind |
| API | FastAPI + Uvicorn |
| DB | SQLite (single file), FTS5 for BM25 |
| Embeddings | fastembed `BAAI/bge-small-en-v1.5` (384-dim, local, no API key), stored as float32 blobs; brute-force cosine via numpy |
| LLM | Anthropic Claude `claude-sonnet-5-5` (configurable), structured outputs via `client.messages.parse` + Pydantic schema, effort `medium` set explicitly |
| Parsing | pypdf (PDF), python-docx (DOCX), trafilatura (HTML), httpx (URL fetch) |
| Auth | bcrypt password hashes, server-side sessions, httpOnly cookie |
| Tests | pytest (+ FastAPI TestClient), Playwright smoke test |
| Research | PyYAML configs, JSONL results, pandas + matplotlib for summaries and plots |

Python 3.11+ must be installed (system has 3.9); README documents `brew install python@3.12` or uv.

## 5. Data model (SQLite)

- `users(id, email UNIQUE, password_hash, created_at)`
- `sessions(token_hash PK, user_id FK, expires_at, created_at)`
- `documents(id, user_id FK, name, source_type[pdf|docx|md|txt|html|url], source_url NULL, file_path, size_bytes, status[processing|ready|failed], error NULL, chunk_count, created_at)`
- `chunks(id, document_id FK ON DELETE CASCADE, user_id, ordinal, text, location TEXT, page INT NULL, char_start, char_end, embedding BLOB)`
- `chunks_fts` — FTS5 virtual table over `chunks.text`, kept in sync via triggers.

All document/chunk access goes through a data-layer function that requires `user_id`.

## 6. Auth & sessions

- Sign up: email + password (min 8 chars), bcrypt-hashed. Signs the user in.
- Log in: issues a random 256-bit token; only its SHA-256 is stored. Cookie `session`: httpOnly, `SameSite=Lax`, `Secure` in production.
- "Remember me" (default on): 30-day persistent cookie with sliding expiry; unchecked = browser-session cookie (server-side expiry 24h).
- Uniform "Invalid email or password" on failure; in-memory rate limit of 5 login attempts/min/IP.
- Log out deletes the session row and clears the cookie.
- Next.js middleware redirects unauthenticated requests to `/login`; any API 401 also redirects.

Endpoints: `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`.

## 7. Ingestion

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

## 8. Question answering

`POST /api/ask {question, doc_ids?: string[]}`

1. **Scope:** the caller's `ready` documents, optionally restricted to `doc_ids`. If none: `400 "Upload a document first"`.
2. **Hybrid retrieval** (default `retrieval_mode=hybrid`): top 20 by cosine similarity + top 20 by FTS5 BM25 → reciprocal rank fusion (k=60) → top 8. In `vector` or `bm25` mode only that ranking is used, and Gate 1 applies only its own half of the condition.
3. **Gate 1 — relevance:** if max cosine similarity < `MIN_SIMILARITY` (config, start 0.35) **and** no chunk contains at least half of the question's non-stopword terms (a "strong BM25 hit" — this keeps exact-term queries like codes or names from being refused), return `status: "not_found"` with the closest chunks for transparency. No LLM call.
4. **Generation:** chunks are labelled `c1…c8` with document name + location. System prompt: answer only from the passages; every sentence must cite; if the passages don't answer, say so. The response is constrained with structured outputs (`messages.parse`, Pydantic `AnswerDraft` schema) — forced `tool_choice` and `temperature` are rejected by current models:
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
7. **Errors:** Claude API error/timeout (30 s) → `502` with retryable message, never a fabricated answer. Unparseable output or `stop_reason` of `max_tokens` → one retry, then `insufficient_evidence`. `stop_reason == "refusal"` (safety classifier) → `insufficient_evidence` with `missing` explaining the model declined.

## 9. Frontend

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

## 10. Testing

**Backend unit (pytest):** chunker (boundaries, overlap, locations), each parser with small fixtures, RRF fusion, citation verifier (fake IDs dropped; uncited sentences dropped; all dropped → refusal), URL safety checks.

**Backend API (TestClient, temp DB, Claude stubbed):** signup/login/me/logout, remember-me cookie attributes, rate limit, cross-user isolation (B cannot list/read/delete/ask over A's docs), upload → ready → list → chunks → delete, Gate 1 path makes no LLM call.

**Frontend:** `tsc --noEmit`, lint, and one Playwright smoke test: sign up → upload sample PDF → wait for ready → ask → click `[1]` → chunk highlighted → ask off-topic → refusal shown.

## 11. Research methodology

**Configurable pipeline.** The ingest/retrieve/answer modules take a `PipelineConfig` (`retrieval_mode`, `min_similarity`, `verify_citations`, `chunk_chars`, `top_k`, `model`) rather than reading globals. The web app builds it from `.env`; the experiment runner builds it from YAML. This is what makes the app a testbed.

**Dataset** (`backend/research/`):
- `corpus/` — 5–8 public-domain or self-written documents covering all supported formats (PDF, DOCX, MD, TXT, HTML), mixing prose with exact-term content (IDs, numbers, names).
- `questions.jsonl` — ~60 hand-labelled questions: ~40 answerable (each with expected document + location, tagged `natural` or `exact_term`) and ~20 unanswerable but plausible (topic-adjacent, not merely off-topic). Labelling guidelines are written in `FINDINGS.md`.

**Runner** (`run_experiment.py experiments/rq1.yaml`): ingests the corpus into an isolated temp DB per chunk configuration, runs every question for every config variant, writes raw per-question records (retrieved IDs, ranks, scores, status, sentences, citations, timings, cost) to `results/<rq>/<timestamp>.jsonl`, and prints a summary table. Current models do not accept `temperature`, so reproducibility comes from caching: Claude responses are cached on disk keyed by a hash of the exact request (model, system prompt, passages, question), so re-runs replay identical outputs and sweeps that do not change the LLM input (e.g. RQ2 thresholds) cost nothing extra. Run-to-run variance is measured once by re-running RQ3 uncached 3× and reported. Retrieval-only metrics (RQ1, RQ4 hit@8) need no LLM calls.

**Metrics:**
- hit@8 / MRR — expected location appears in retrieved top 8 / reciprocal rank of first match.
- answer rate — share of answerable questions returning `answered` or `partial`.
- refusal precision / recall — over `not_found` + `insufficient_evidence` outcomes vs the unanswerable label.
- citation validity — share of citations pointing to a retrieved chunk.
- unsupported-sentence rate — share of sentences whose cited chunks do not support them, judged by a separate Claude call with a fixed rubric; the judge is spot-checked by hand on 30 samples and its agreement rate reported.

**Reporting.** `make experiments` runs all four RQs and regenerates `plots/` (matplotlib: RQ1 grouped bars by question tag, RQ2 answer-rate vs refusal-recall curve, RQ3 before/after bars, RQ4 line chart). `FINDINGS.md` is written by hand from these results with sections: Question & hypothesis → Method → Results (table + plot) → Interpretation → Threats to validity (small dataset, single domain, LLM-judge bias, self-written questions). The shipped default config is justified by these findings.

## 12. Configuration

`backend/.env`: `ANTHROPIC_API_KEY`, `CLAUDE_MODEL` (default `claude-sonnet-5-5`), `RETRIEVAL_MODE` (default `hybrid`), `MIN_SIMILARITY`, `VERIFY_CITATIONS` (default on), `CHUNK_CHARS`, `DATABASE_PATH`, `STORAGE_DIR`, `COOKIE_SECURE`. `.env.example` committed; `.env` gitignored. Defaults are updated to whatever the experiments support.

## 13. Out of scope (v1)

OCR for scanned PDFs, streaming responses, chat history / follow-ups, password reset / email verification, deployment, document sharing between users, an in-app experiments UI, public benchmark datasets (e.g. SQuAD 2.0 unanswerables) — candidates for follow-up research. Listed in README as next steps.
