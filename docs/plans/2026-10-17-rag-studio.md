# RAG Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a multi-user document-QA web app that answers only from uploaded documents with clickable citations and refuses when evidence is missing, plus an experiment harness that answers four research questions about that pipeline.

**Architecture:** A FastAPI backend owns auth, ingestion, hybrid retrieval, and answer generation over one SQLite file (tables + FTS5 + embedding blobs). Every pipeline stage reads a `PipelineConfig`, so the same code serves the web app (config from `.env`) and the experiment runner (config from YAML). A Next.js frontend talks to it only through `/api/*` rewrites.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, pydantic-settings, SQLite/FTS5, numpy, fastembed (`BAAI/bge-small-en-v1.5`), anthropic SDK (`messages.parse`), pypdf, python-docx, trafilatura, httpx, bcrypt, pytest; Next.js 15, React, TypeScript, Tailwind, Playwright; PyYAML, pandas, matplotlib, fpdf2.

**Spec:** `docs/design/2026-10-17-rag-studio-design.md`

## Global Constraints

- Repo root `rag-studio/`; backend in `backend/`, frontend in `frontend/`. Plans in `docs/plans/`, specs in `docs/design/`.
- Python ≥ 3.12 in `backend/.venv` (system Python is 3.9: install with `brew install python@3.12`). Node 24 (already installed).
- Default model `claude-sonnet-5-5`, from `CLAUDE_MODEL`. Use `client.messages.parse(..., output_format=AnswerDraft)` with `output_config={"effort": "medium"}`. Never send `temperature`, `tool_choice` `any`/`tool`, or `thinking: disabled`; Sonnet 5.5 rejects all three with a 400. Set effort explicitly (Sonnet 5.5 defaults to `high`).
- Claude timeout 30 s (`anthropic.Anthropic(timeout=30, max_retries=1)`), `max_tokens=4000`.
- Upload limits: types `pdf, docx, md, txt, html`; ≤ 20 MB. URL import: http/https only, no private/loopback/link-local/reserved IPs (checked on every redirect hop), 10 s timeout, 5 MB cap.
- Chunking: `chunk_chars` default 2000, overlap 15% (`int(chunk_chars * 0.15)`), never across segments.
- Retrieval: 20 vector + 20 BM25 candidates, RRF k=60, `top_k` 8, `MIN_SIMILARITY` default 0.35.
- Sessions: cookie `session`, httpOnly, `SameSite=Lax`, `Secure` iff `COOKIE_SECURE`; remember-me 30 days sliding, otherwise browser-session cookie with a 24 h server expiry. Login rate limit 5/min/IP. Failure copy exactly `Invalid email or password`.
- Exact UI/API copy: `Upload a document first`, `Not found in your documents`, `No extractable text — scanned PDFs need OCR (not supported)`.
- Every document/chunk read or write goes through `app/store.py` functions that take `user_id`. Another user's document → 404.
- Tests never call the real Claude API or download the embedding model: they use `FakeLLM` and `HashEmbedder`.

## Review Focus

1. **FTS5 special characters in questions** (`"`, `*`, `-`, `AND`, `NEAR(`, `:`). The user expects a normal answer or a refusal, never a 500. *Pinned in Task 7.*
2. **Deleting a document while it is still processing.** Expect the delete to succeed, no orphan chunks, and the background task to exit quietly. *Pinned in Task 6.*
3. **Hostile or odd upload filenames** (`../../etc/passwd.pdf`, unicode, duplicates). Expect the original name shown in the UI, storage only at `storage/{user_id}/{doc_id}.{ext}`, and duplicates allowed as separate documents. *Pinned in Task 6.*
4. **URL import redirecting to a private address** (e.g. public URL → 302 → `http://127.0.0.1`). Expect it rejected as unsafe. *Pinned in Task 3.*
5. **Empty, whitespace-only, or very long questions.** Expect a 422 for empty or over 1000 chars, with the UI keeping the button disabled for empty input. *Pinned in Task 9.*

---

## File map

```
backend/
  pyproject.toml                 deps + pytest config
  .env.example
  app/
    config.py                    Settings, PipelineConfig
    db.py                        connect, init_db, schema
    store.py                     user-scoped data layer
    embeddings.py                Embedder protocol, FastEmbedder, HashEmbedder
    auth/{passwords,sessions,deps,routes}.py
    ingest/{parsers,fetch,chunker,pipeline}.py
    documents/routes.py
    retrieval.py
    answer/{schema,llm,verify,service}.py
    ask/routes.py
    main.py                      create_app()
  tests/                         one test file per module + conftest.py
  research/
    sources/                     hand-written corpus sources (.md)
    build_corpus.py              renders sources into PDF/DOCX/HTML/MD/TXT
    corpus/                      generated documents (committed)
    questions.jsonl
    experiments/rq{1..4}.yaml
    harness.py                   load corpus into temp DB, run questions
    metrics.py
    judge.py
    run_experiment.py
    plots.py
    spotcheck.py
    results/, plots/, cache/     (cache/ gitignored)
frontend/
  next.config.ts, middleware.ts, playwright.config.ts
  lib/{api,types}.ts
  app/{layout,page}.tsx, app/login/page.tsx, app/signup/page.tsx
  components/{Header,Tabs}.tsx
  components/dashboard/{Dashboard,SearchBar,AnswerPane,SourcesList,ChunksList}.tsx
  components/documents/{DocumentsTab,UploadPanel,DocumentsTable}.tsx
  e2e/{auth,documents,dashboard}.spec.ts
Makefile, README.md, FINDINGS.md
```

---

### Task 1: Backend scaffold, config, and database schema

**Files:**
- Create: `backend/pyproject.toml`, `backend/.env.example`, `backend/app/__init__.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `backend/tests/test_db.py`
- Modify: `.gitignore` (add `backend/research/cache/`, `backend/storage/`, `frontend/test-results/`, `frontend/playwright-report/`)

**Interfaces:**
- Produces:
  - `PipelineConfig` (frozen dataclass): `retrieval_mode: Literal["vector","bm25","hybrid"]="hybrid"`, `min_similarity: float=0.35`, `verify_citations: bool=True`, `chunk_chars: int=2000`, `top_k: int=8`, `model: str="claude-sonnet-5-5"`
  - `Settings` (pydantic-settings, reads `backend/.env`): `anthropic_api_key: str=""`, `claude_model`, `retrieval_mode`, `min_similarity`, `verify_citations`, `chunk_chars`, `database_path: Path=Path("storage/app.db")`, `storage_dir: Path=Path("storage")`, `cookie_secure: bool=False`, `embedder: Literal["fastembed","hash"]="fastembed"`, `llm: Literal["claude","fake"]="claude"`; method `pipeline() -> PipelineConfig`
  - `db.connect(path: Path | str) -> sqlite3.Connection` (row_factory `sqlite3.Row`, `PRAGMA foreign_keys=ON`, `check_same_thread=False`), `db.init_db(conn) -> None` (idempotent)
  - `main.create_app(settings: Settings, embedder=None, llm=None) -> FastAPI`; stores `settings`, `embedder`, `llm` on `app.state`; `GET /api/health` → `{"ok": true}`
  - `tests/conftest.py` fixtures: `settings(tmp_path)` (hash embedder, fake llm, tmp db/storage), `conn(settings)`

- [ ] **Step 1: Install Python 3.12 and create the venv**

Run: `brew install python@3.12 && cd backend && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"` (after writing `pyproject.toml` with runtime deps from the Tech Stack and a `dev` extra: pytest, httpx, fpdf2).
Expected: install succeeds; `.venv/bin/python --version` prints 3.12.x.

- [ ] **Step 2: Write the failing schema tests**

```python
def test_init_db_is_idempotent(conn):
    init_db(conn); init_db(conn)
    names = {r["name"] for r in conn.execute("select name from sqlite_master")}
    assert {"users", "sessions", "documents", "chunks", "chunks_fts"} <= names

def test_fts_tracks_chunk_insert_and_delete(conn, make_user_doc):
    user_id, doc_id = make_user_doc()
    conn.execute("insert into chunks(id,document_id,user_id,ordinal,text,location,char_start,char_end,embedding) values('c1',?,?,0,'refund policy window','p. 1',0,20,x'00')", (doc_id, user_id))
    assert conn.execute("select count(*) from chunks_fts where chunks_fts match 'refund'").fetchone()[0] == 1
    conn.execute("delete from documents where id=?", (doc_id,))
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0
    assert conn.execute("select count(*) from chunks_fts where chunks_fts match 'refund'").fetchone()[0] == 0

def test_settings_pipeline_defaults():
    p = Settings(_env_file=None).pipeline()
    assert p == PipelineConfig()
```

`make_user_doc` is a conftest fixture that inserts one user and one document row and returns their ids.

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && .venv/bin/pytest tests/test_db.py -v`
Expected: FAIL (ImportError).

- [ ] **Step 4: Implement `config.py`, `db.py`, `main.py`**

Schema is spec §5, plus `sessions.remember INTEGER NOT NULL DEFAULT 1`. Ids are `uuid4().hex` text. `chunks_fts` is an external-content FTS5 table (`content='chunks', content_rowid='rowid'`, tokenizer `porter unicode61`) kept in sync by `AFTER INSERT` / `AFTER DELETE` triggers on `chunks`. `documents.user_id` and `chunks.document_id` are `ON DELETE CASCADE`. Index on `chunks(user_id, document_id)`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add backend .gitignore
git commit -m "feat(backend): scaffold FastAPI app, config, and SQLite schema"
```

---

### Task 2: Authentication and sessions

**Files:**
- Create: `backend/app/auth/__init__.py`, `passwords.py`, `sessions.py`, `deps.py`, `routes.py`; `backend/tests/test_auth.py`
- Modify: `backend/app/main.py` (include auth router), `backend/tests/conftest.py` (add `client` fixture: `TestClient(create_app(settings, HashEmbedder(), FakeLLM()))`. Until Tasks 5 and 8 exist, pass `None`.)

**Interfaces:**
- Consumes: `db.connect`, `Settings`
- Produces:
  - `passwords.hash_password(pw: str) -> str`, `passwords.verify_password(pw: str, hashed: str) -> bool`
  - `sessions.create_session(conn, user_id: str, remember: bool) -> str` (returns raw token; stores sha256 hex and `remember`; expires now+30 d if remember, else now+24 h), `sessions.resolve_session(conn, token: str) -> str | None` (user_id; deletes expired rows; slides `expires_at` to now+30 d for remember sessions), `sessions.delete_session(conn, token: str) -> None`.
  - `deps.get_conn(request) -> sqlite3.Connection` (one connection per request, opened from `app.state.settings.database_path`), `deps.current_user(request, conn) -> User` raising 401. `User` pydantic: `id: str, email: str`.
  - Routes: `POST /api/auth/signup {email, password, remember=true}` → 201 `User` + cookie (409 if email exists, 422 if password < 8); `POST /api/auth/login {email, password, remember=true}` → 200 `User` + cookie | 401 `{"detail":"Invalid email or password"}` | 429; `POST /api/auth/logout` → 204, clears cookie; `GET /api/auth/me` → `User` | 401.

- [ ] **Step 1: Write the failing tests**

```python
def test_signup_sets_persistent_cookie_and_me_works(client):
    r = client.post("/api/auth/signup", json={"email": "a@x.io", "password": "password1"})
    assert r.status_code == 201
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=2592000" in cookie
    assert client.get("/api/auth/me").json()["email"] == "a@x.io"

def test_login_without_remember_sets_session_cookie(client, signup):
    signup("a@x.io"); client.cookies.clear()
    r = client.post("/api/auth/login", json={"email": "a@x.io", "password": "password1", "remember": False})
    assert "max-age" not in r.headers["set-cookie"].lower()

def test_bad_credentials_uniform_message(client, signup):
    signup("a@x.io")
    for body in ({"email": "a@x.io", "password": "wrongpass"}, {"email": "no@x.io", "password": "password1"}):
        r = client.post("/api/auth/login", json=body)
        assert r.status_code == 401 and r.json()["detail"] == "Invalid email or password"

def test_login_rate_limited_after_5_attempts(client):
    codes = [client.post("/api/auth/login", json={"email": "n@x.io", "password": "password1"}).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429

def test_logout_invalidates_session(client, signup):
    signup("a@x.io"); client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

def test_session_token_stored_hashed(client, conn, signup):
    signup("a@x.io")
    raw = client.cookies["session"]
    assert conn.execute("select count(*) from sessions where token_hash=?", (raw,)).fetchone()[0] == 0

def test_expired_session_rejected(client, conn, signup):
    signup("a@x.io"); conn.execute("update sessions set expires_at='2000-01-01T00:00:00+00:00'"); conn.commit()
    assert client.get("/api/auth/me").status_code == 401

def test_short_password_and_duplicate_email(client, signup):
    assert client.post("/api/auth/signup", json={"email": "b@x.io", "password": "short"}).status_code == 422
    signup("a@x.io")
    assert client.post("/api/auth/signup", json={"email": "a@x.io", "password": "password1"}).status_code == 409
```

`signup(email)` is a conftest helper that posts signup with password `password1`. Emails are lower-cased and stripped before storage and lookup.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_auth.py -v` · Expected: FAIL (404 / ImportError).

- [ ] **Step 3: Implement the auth package**

Use `secrets.token_urlsafe(32)` for tokens and `bcrypt` directly. The rate limiter is an in-memory `dict[ip, deque[timestamps]]` on `app.state`, counting every login attempt in the last 60 s; signup is not limited. Timestamps are ISO-8601 UTC strings.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest -v` · Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend && git commit -m "feat(auth): signup/login/logout with hashed server-side sessions"
```

---

### Task 3: Parsers and safe URL fetch

**Files:**
- Create: `backend/app/ingest/__init__.py`, `parsers.py`, `fetch.py`; `backend/tests/test_parsers.py`, `backend/tests/test_fetch.py`; fixture builders in `backend/tests/fixtures.py` (generate PDF with fpdf2 and DOCX with python-docx into `tmp_path` at test time; no binary fixtures committed)

**Interfaces:**
- Produces:
  - `Segment` (dataclass): `text: str, location: str, page: int | None`
  - `ParseError(Exception)`: its message is user-facing
  - `parse_file(path: Path, source_type: str) -> list[Segment]`: dispatch on `pdf|docx|md|txt|html|url` (`url` parses as html). Raises `ParseError("No extractable text — scanned PDFs need OCR (not supported)")` when a PDF yields only whitespace, and `ParseError("No extractable text")` for other empty files.
  - `UnsafeURLError(Exception)`
  - `fetch_url(url: str, *, max_bytes=5_000_000, timeout=10.0, resolver=socket.getaddrinfo) -> tuple[bytes, str]` returning `(body, final_url)`. Follows up to 5 redirects manually, validating scheme and resolved IPs before every hop. Raises `UnsafeURLError` or `ParseError("Page too large (max 5 MB)")`.

- [ ] **Step 1: Write the failing parser tests**

```python
def test_pdf_one_segment_per_page(tmp_path):
    p = make_pdf(tmp_path, ["Alpha page text", "Beta page text"])
    segs = parse_file(p, "pdf")
    assert [(s.location, s.page) for s in segs] == [("p. 1", 1), ("p. 2", 2)]
    assert "Beta" in segs[1].text

def test_blank_pdf_raises_ocr_message(tmp_path):
    with pytest.raises(ParseError, match="scanned PDFs need OCR"):
        parse_file(make_pdf(tmp_path, ["   "]), "pdf")

def test_docx_segments_by_heading(tmp_path):
    p = make_docx(tmp_path, [("Intro", "Hello."), ("Pricing", "Costs $5.")])
    assert [s.location for s in parse_file(p, "docx")] == ["Intro", "Pricing"]

def test_markdown_segments_by_heading(tmp_path):
    p = tmp_path / "a.md"; p.write_text("# Setup\nInstall it.\n\n## Usage\nRun it.\n")
    assert [(s.location, s.text.strip()) for s in parse_file(p, "md")] == [("Setup", "Install it."), ("Usage", "Run it.")]

def test_txt_blank_line_blocks(tmp_path):
    p = tmp_path / "a.txt"; p.write_text("one\n\ntwo\n")
    assert [s.location for s in parse_file(p, "txt")] == ["¶ 1", "¶ 2"]

def test_html_main_text(tmp_path):
    p = tmp_path / "a.html"; p.write_text("<html><nav>Menu</nav><article><h1>Policy</h1><p>" + "Refunds take 14 days. " * 20 + "</p></article></html>")
    text = " ".join(s.text for s in parse_file(p, "html"))
    assert "Refunds take 14 days" in text
```

Text before the first markdown heading gets location `Introduction`. HTML is converted with `trafilatura.extract(..., output_format="markdown")`, then split with the markdown splitter.

- [ ] **Step 2: Write the failing fetch tests** (no network: inject `resolver` and use `httpx.MockTransport` via a `transport` kwarg on `fetch_url`)

```python
@pytest.mark.parametrize("url", ["ftp://x.io/a", "file:///etc/passwd", "http://127.0.0.1/", "http://10.0.0.5/", "http://169.254.169.254/", "http://[::1]/"])
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeURLError):
        fetch_url(url, resolver=real_ip_resolver)

def test_rejects_redirect_to_private_ip():  # Review Focus 4
    transport = httpx.MockTransport(lambda req: httpx.Response(302, headers={"location": "http://127.0.0.1/admin"}) if req.url.host == "public.example" else httpx.Response(200, text="secret"))
    with pytest.raises(UnsafeURLError):
        fetch_url("http://public.example/", resolver=fake_resolver({"public.example": "93.184.216.34"}), transport=transport)

def test_rejects_oversized_body():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=b"x" * 6_000_000))
    with pytest.raises(ParseError, match="max 5 MB"):
        fetch_url("http://public.example/", resolver=fake_resolver({"public.example": "93.184.216.34"}), transport=transport)

def test_returns_body_and_final_url():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text="<p>hi</p>"))
    body, final = fetch_url("http://public.example/a", resolver=fake_resolver({"public.example": "93.184.216.34"}), transport=transport)
    assert body == b"<p>hi</p>" and final == "http://public.example/a"
```

The unsafe test is "any resolved address where `ipaddress.ip_address(a).is_global` is False".

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_parsers.py tests/test_fetch.py -v` · Expected: FAIL.

- [ ] **Step 4: Implement `parsers.py` and `fetch.py`**

The body is read by streaming, aborting past `max_bytes`.

- [ ] **Step 5: Run tests to verify they pass**, then commit

```bash
git add backend && git commit -m "feat(ingest): format parsers and SSRF-safe URL fetch"
```

---

### Task 4: Chunker

**Files:**
- Create: `backend/app/ingest/chunker.py`, `backend/tests/test_chunker.py`

**Interfaces:**
- Consumes: `Segment`
- Produces: `ChunkDraft` (dataclass): `text, location, page, char_start, char_end` (offsets within the segment text). `chunk_segments(segments: list[Segment], chunk_chars: int) -> list[ChunkDraft]`

- [ ] **Step 1: Write the failing tests**

```python
def test_short_segment_is_one_chunk():
    out = chunk_segments([Segment("Hello world.", "p. 1", 1)], 2000)
    assert [(c.text, c.location, c.page) for c in out] == [("Hello world.", "p. 1", 1)]

def test_chunks_respect_size_and_overlap():
    text = " ".join(f"Sentence number {i} is here." for i in range(400))
    out = chunk_segments([Segment(text, "p. 1", 1)], 1000)
    assert all(len(c.text) <= 1000 for c in out)
    for a, b in zip(out, out[1:]):
        assert b.char_start < a.char_end                      # overlap exists
        assert a.char_end - b.char_start <= 150 + 40          # ~15%, snapped to a sentence boundary

def test_never_crosses_segments():
    out = chunk_segments([Segment("A. " * 10, "p. 1", 1), Segment("B. " * 10, "p. 2", 2)], 2000)
    assert [c.location for c in out] == ["p. 1", "p. 2"]

def test_prefers_paragraph_boundary():
    text = ("x" * 600 + ".\n\n") + ("y" * 600 + ".")
    out = chunk_segments([Segment(text, "s", None)], 1000)
    assert out[0].text.endswith(".") and "y" not in out[0].text

def test_offsets_slice_back_to_text():
    seg = Segment("First para.\n\nSecond para. " * 50, "s", None)
    for c in chunk_segments([seg], 500):
        assert seg.text[c.char_start:c.char_end].strip() == c.text

def test_whitespace_only_segment_skipped():
    assert chunk_segments([Segment("   \n ", "s", None)], 500) == []
```

- [ ] **Step 2: Run to verify fail** · `.venv/bin/pytest tests/test_chunker.py -v`

- [ ] **Step 3: Implement `chunk_segments`**

Greedy window algorithm:

```
start = 0
while start < len(text):
    end = min(start + chunk_chars, len(text))
    if end < len(text):
        cut = last "\n\n" in text[start+chunk_chars//2 : end]   # paragraph boundary
           or last sentence end (". ", "? ", "! ", ".\n") in the same window
           or last whitespace in the same window
        end = cut position (exclusive, after the boundary) if found
    emit text[start:end].strip() with stripped offsets (skip if empty)
    if end == len(text): break
    next_start = end - overlap; advance next_start to the next sentence start/whitespace within 40 chars
    start = max(next_start, start + 1)
```

- [ ] **Step 4: Run to verify pass**, then commit

```bash
git add backend && git commit -m "feat(ingest): boundary-aware chunker with overlap"
```

---

### Task 5: Embedder, user-scoped store, and ingestion pipeline

**Files:**
- Create: `backend/app/embeddings.py`, `backend/app/store.py`, `backend/app/ingest/pipeline.py`; `backend/tests/test_store.py`, `backend/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `parse_file`, `ParseError`, `fetch_url`, `chunk_segments`, `PipelineConfig`
- Produces:
  - `Embedder` (Protocol): `dim: int`, `embed(texts: list[str]) -> np.ndarray` with shape (n, dim), float32, L2-normalised
  - `FastEmbedder(model="BAAI/bge-small-en-v1.5")` (lazy-loads; batch size 64); `HashEmbedder(dim=384)`, a deterministic bag-of-words hashing embedder for tests and e2e, so texts sharing words have higher cosine
  - `make_embedder(kind: str) -> Embedder`
  - `Document` (pydantic): `id, name, source_type, source_url, size_bytes, status, error, chunk_count, created_at`
  - `ChunkRow` (pydantic): `id, document_id, document_name, ordinal, text, location, page`
  - store functions (all take `conn` first and `user_id` second, except `_unscoped` helpers used only by the pipeline):
    - `create_document(conn, user_id, *, name, source_type, source_url, file_path, size_bytes) -> Document` (status `processing`)
    - `list_documents(conn, user_id) -> list[Document]` (newest first)
    - `get_document(conn, user_id, doc_id) -> Document | None`
    - `get_document_file(conn, user_id, doc_id) -> tuple[Document, Path] | None`
    - `delete_document(conn, user_id, doc_id) -> Path | None` (returns the file path to remove; None if not found)
    - `list_chunks(conn, user_id, doc_id, offset=0, limit=50) -> list[ChunkRow]`
    - `load_vectors(conn, user_id, doc_ids: list[str] | None) -> tuple[list[str], np.ndarray]` (chunk ids, matrix) over `ready` docs only
    - `get_chunks(conn, user_id, chunk_ids: list[str]) -> dict[str, ChunkRow]`
    - `ready_doc_ids(conn, user_id, doc_ids: list[str] | None) -> list[str]`
  - `ingest_document(conn, embedder, cfg: PipelineConfig, doc_id: str) -> None`: loads the row unscoped; for `url` docs fetches first and saves the body to the doc's `file_path`; parses, chunks and embeds; inserts all chunks in one transaction, then sets `ready` + `chunk_count`. On `ParseError`/`UnsafeURLError` it sets `failed` with `str(e)`; on any other exception `failed` with `"Processing failed"` (logged). If the document row disappears at any point it returns silently and leaves no chunks.

- [ ] **Step 1: Write the failing tests**

```python
def test_store_is_user_scoped(conn, two_users):
    a, b = two_users
    d = create_document(conn, a, name="x.md", source_type="md", source_url=None, file_path="f", size_bytes=1)
    assert get_document(conn, b, d.id) is None
    assert list_documents(conn, b) == []
    assert delete_document(conn, b, d.id) is None
    assert get_document(conn, a, d.id) is not None

def test_hash_embedder_similarity():
    e = HashEmbedder()
    v = e.embed(["refund policy days", "refund policy window", "quantum chromodynamics"])
    assert v.shape == (3, 384) and np.allclose(np.linalg.norm(v, axis=1), 1)
    assert v[0] @ v[1] > v[0] @ v[2]

def test_ingest_markdown_to_ready(conn, user, storage):
    doc = add_file_doc(conn, user, storage, "a.md", "# Refunds\nRefunds take 14 days.\n")
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert d.status == "ready" and d.chunk_count == 1
    assert list_chunks(conn, user, doc.id)[0].location == "Refunds"

def test_ingest_failure_sets_error_and_no_chunks(conn, user, storage):
    doc = add_file_doc(conn, user, storage, "blank.txt", "   ")
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert d.status == "failed" and d.error == "No extractable text"
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0

def test_ingest_after_delete_is_silent(conn, user, storage):   # Review Focus 2
    doc = add_file_doc(conn, user, storage, "a.md", "# A\ntext\n")
    delete_document(conn, user, doc.id)
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)   # must not raise
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0

def test_load_vectors_skips_non_ready(conn, user, storage):
    ready = add_file_doc(conn, user, storage, "a.md", "# A\nalpha\n"); ingest_document(conn, HashEmbedder(), PipelineConfig(), ready.id)
    add_file_doc(conn, user, storage, "b.md", "# B\nbeta\n")          # still processing
    ids, m = load_vectors(conn, user, None)
    assert len(ids) == 1 and m.shape == (1, 384)
```

`add_file_doc` (conftest) writes the file under `storage/{user}/{uuid}.{ext}` and calls `create_document`.

- [ ] **Step 2: Run to verify fail** · `.venv/bin/pytest tests/test_store.py tests/test_pipeline.py -v`

- [ ] **Step 3: Implement `embeddings.py`, `store.py`, `pipeline.py`**

Embeddings are stored as `np.float32` bytes (`tobytes()` / `frombuffer`). For the delete-during-processing case, the final insert checks that the document row still exists inside the same transaction before inserting.

- [ ] **Step 4: Run to verify pass**, then commit

```bash
git add backend && git commit -m "feat(ingest): embedder, user-scoped store, ingestion pipeline"
```

---

### Task 6: Documents API

**Files:**
- Create: `backend/app/documents/__init__.py`, `routes.py`; `backend/tests/test_documents_api.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: store functions, `ingest_document`, `current_user`, `get_conn`, `app.state.embedder`, `settings.pipeline()`
- Produces (all require auth):
  - `POST /api/documents` multipart field `files` (one or more) → 201 `list[Document]`; or JSON `{"url": str}` → 201 `list[Document]` (one item, `source_type="url"`, `name` = the URL). Rejects unknown extension or > 20 MB with 400 `{"detail": "<name>: unsupported file type"}` / `"<name>: file too large (max 20 MB)"` and saves nothing for that request. Each accepted doc schedules `ingest_document` via `BackgroundTasks` (the task opens its own connection).
  - `GET /api/documents` → `list[Document]`
  - `DELETE /api/documents/{id}` → 204 | 404
  - `GET /api/documents/{id}/file` → `FileResponse` with media type by extension and `Content-Disposition: inline; filename*=UTF-8''<name>` | 404
  - `GET /api/documents/{id}/chunks?offset=0&limit=50` → `list[ChunkRow]` | 404

- [ ] **Step 1: Write the failing tests**

```python
def test_upload_process_list_chunks_delete(authed):
    r = authed.post("/api/documents", files=[("files", ("notes.md", b"# Refunds\nRefunds take 14 days.\n", "text/markdown"))])
    assert r.status_code == 201 and r.json()[0]["status"] == "processing"
    doc_id = r.json()[0]["id"]
    docs = authed.get("/api/documents").json()          # TestClient runs background tasks before returning
    assert docs[0]["status"] == "ready" and docs[0]["chunk_count"] == 1
    assert authed.get(f"/api/documents/{doc_id}/chunks").json()[0]["location"] == "Refunds"
    assert authed.get(f"/api/documents/{doc_id}/file").content.startswith(b"# Refunds")
    assert authed.delete(f"/api/documents/{doc_id}").status_code == 204
    assert authed.get("/api/documents").json() == []

def test_rejects_bad_type_and_size(authed):
    assert authed.post("/api/documents", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))]).status_code == 400
    big = b"a" * (20 * 1024 * 1024 + 1)
    assert authed.post("/api/documents", files=[("files", ("big.txt", big, "text/plain"))]).json()["detail"] == "big.txt: file too large (max 20 MB)"

def test_hostile_filename_stored_safely(authed, settings):   # Review Focus 3
    r = authed.post("/api/documents", files=[("files", ("../../etc/passwd.md", b"# A\nx\n", "text/markdown")), ("files", ("résumé.md", b"# B\ny\n", "text/markdown")), ("files", ("résumé.md", b"# C\nz\n", "text/markdown"))])
    names = sorted(d["name"] for d in r.json())
    assert names == ["passwd.md", "résumé.md", "résumé.md"]
    stored = list(settings.storage_dir.rglob("*.md"))
    assert len(stored) == 3 and all(p.resolve().is_relative_to(settings.storage_dir.resolve()) for p in stored)

def test_cross_user_isolation(client, as_user):
    as_user("a@x.io"); doc_id = client.post("/api/documents", files=[("files", ("a.md", b"# A\nx\n", "text/markdown"))]).json()[0]["id"]
    as_user("b@x.io")
    assert client.get("/api/documents").json() == []
    for path in (f"/api/documents/{doc_id}/file", f"/api/documents/{doc_id}/chunks"):
        assert client.get(path).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}").status_code == 404

def test_requires_auth(client):
    assert client.get("/api/documents").status_code == 401
```

`authed` is a fixture: a client with a signed-up user. `as_user(email)` signs up or logs in as that user, replacing the cookie. Display names are `PurePosixPath(PureWindowsPath(name).name).name`.

- [ ] **Step 2: Run to verify fail** · `.venv/bin/pytest tests/test_documents_api.py -v`

- [ ] **Step 3: Implement `documents/routes.py`**

Read uploads in 1 MB chunks and abort past the limit. File removal after delete is best-effort (`missing_ok=True`). A URL import stores to `storage/{user_id}/{doc_id}.html`.

- [ ] **Step 4: Run to verify pass**, then commit

```bash
git add backend && git commit -m "feat(api): document upload, URL import, list, file, chunks, delete"
```

---

### Task 7: Hybrid retrieval and relevance gate

**Files:**
- Create: `backend/app/retrieval.py`, `backend/tests/test_retrieval.py`

**Interfaces:**
- Consumes: `load_vectors`, `get_chunks`, `ready_doc_ids`, `Embedder`, `PipelineConfig`
- Produces:
  - `RetrievedChunk` (pydantic): `chunk: ChunkRow, score: float` (RRF score, or the single-mode score), `similarity: float | None`, `vector_rank: int | None`, `bm25_rank: int | None` (1-based)
  - `RetrievalResult` (pydantic): `chunks: list[RetrievedChunk]` (≤ `top_k`), `max_similarity: float | None`, `strong_term_hit: bool | None`, `gate_passed: bool`
  - `query_terms(question: str) -> list[str]`: lower-cased `[a-z0-9]+` tokens (unicode letters allowed) minus an English stopword list, de-duplicated in order
  - `rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]`
  - `retrieve(conn, embedder, cfg, user_id, question, doc_ids=None) -> RetrievalResult`
- Rules:
  - The vector branch uses the top 20 by cosine; the BM25 branch the top 20 from `chunks_fts MATCH` (terms OR-joined, each double-quoted) ordered by `bm25(chunks_fts)` and filtered to the user's ready docs.
  - `strong_term_hit` is true iff some BM25 candidate's text contains ≥ ceil(half) of `query_terms` (whole-word, case-insensitive).
  - The gate: hybrid → `max_similarity >= min_similarity or strong_term_hit`; vector → the similarity half only; bm25 → the term half only. With no terms (e.g. all stopwords) the BM25 branch returns nothing and `strong_term_hit=False`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rrf_fuse_orders_by_combined_rank():
    fused = rrf_fuse([["a", "b", "c"], ["b", "c", "d"]])
    assert [i for i, _ in fused] == ["b", "c", "a", "d"]
    assert dict(fused)["b"] == pytest.approx(1/62 + 1/61)

def test_query_terms_drops_stopwords():
    assert query_terms("What is the refund window for ORD-4471?") == ["refund", "window", "ord", "4471"]

@pytest.mark.parametrize("q", ['"unbalanced', "refund*", "NEAR(a b)", "a AND OR NOT", "col:val -x", "()", "?!"])
def test_fts_special_characters_do_not_crash(seeded, q):   # Review Focus 1
    conn, user = seeded
    retrieve(conn, HashEmbedder(), PipelineConfig(), user, q)   # no exception

def test_exact_term_question_passes_gate_via_terms(seeded):
    conn, user = seeded   # corpus includes "Error code E-4471 means the token expired."
    r = retrieve(conn, HashEmbedder(), PipelineConfig(min_similarity=0.99), user, "What does E-4471 mean?")
    assert r.strong_term_hit and r.gate_passed
    assert "E-4471" in r.chunks[0].chunk.text

def test_off_topic_question_fails_gate(seeded):
    conn, user = seeded
    r = retrieve(conn, HashEmbedder(), PipelineConfig(), user, "Who won the 1998 world cup?")
    assert not r.gate_passed

def test_modes_populate_only_their_ranks(seeded):
    conn, user = seeded
    v = retrieve(conn, HashEmbedder(), PipelineConfig(retrieval_mode="vector"), user, "refund days")
    b = retrieve(conn, HashEmbedder(), PipelineConfig(retrieval_mode="bm25"), user, "refund days")
    assert all(c.bm25_rank is None for c in v.chunks) and v.strong_term_hit is None
    assert all(c.vector_rank is None for c in b.chunks) and b.max_similarity is None

def test_scoped_to_user_and_doc_ids(seeded_two_users):
    conn, a, b, a_doc_ids = seeded_two_users
    assert retrieve(conn, HashEmbedder(), PipelineConfig(), b, "refund days").chunks == []
    r = retrieve(conn, HashEmbedder(), PipelineConfig(), a, "refund days", doc_ids=a_doc_ids[:1])
    assert {c.chunk.document_id for c in r.chunks} <= {a_doc_ids[0]}
```

`seeded` (conftest) ingests three small markdown docs for one user: a refund policy ("Refunds take 14 days"), an error-code list ("Error code E-4471 means the token expired."), and an onboarding note.

- [ ] **Step 2: Run to verify fail** · `.venv/bin/pytest tests/test_retrieval.py -v`

- [ ] **Step 3: Implement `retrieval.py`**

In hybrid mode `score` is the RRF score and `similarity` comes from the vector branch, when present.

- [ ] **Step 4: Run to verify pass**, then commit

```bash
git add backend && git commit -m "feat(retrieval): hybrid vector+BM25 with RRF and relevance gate"
```

---

### Task 8: Answer generation and citation verification

**Files:**
- Create: `backend/app/answer/__init__.py`, `schema.py`, `llm.py`, `verify.py`, `service.py`; `backend/tests/test_verify.py`, `backend/tests/test_answer_service.py`

**Interfaces:**
- Consumes: `RetrievalResult`, `RetrievedChunk`, `PipelineConfig`
- Produces:
  - `schema.AnswerDraft` (pydantic, the LLM output schema): `status: Literal["answered","partial","insufficient_evidence"]`, `sentences: list[DraftSentence]`, `missing: str`; `DraftSentence`: `text: str`, `citations: list[str]`
  - `schema.Passage` (pydantic): `label: str` (`c1`…), `document_name: str`, `location: str`, `text: str`
  - `schema.AskResponse` (pydantic): exactly the spec §8 response shape (`status`, `sentences: list[{text, citations: list[int]}]`, `missing`, `citations: list[{n, chunk_id, document_id, document_name, location, page}]`, `chunks: list[{chunk_id, document_id, document_name, location, text, score, vector_rank, bm25_rank}]`, `dropped_citations`, `timings_ms: {retrieve, generate}`)
  - `llm.LLMOutcome` (dataclass): `draft: AnswerDraft | None`, `stop_reason: str`, `input_tokens: int`, `output_tokens: int`
  - `llm.LLM` (Protocol): `draft(question: str, passages: list[Passage], model: str) -> LLMOutcome`
  - `llm.ClaudeLLM(api_key)`: `client.messages.parse(model=model, max_tokens=4000, system=SYSTEM_PROMPT, output_config={"effort": "medium"}, output_format=AnswerDraft, messages=[...])` with a 30 s timeout; returns `draft=None` when `stop_reason` is `refusal` or `max_tokens` or the output fails to parse. API errors propagate as `anthropic.APIError`.
  - `llm.CachedLLM(inner: LLM, cache_dir: Path)`: a disk cache keyed by sha256 of `json.dumps({model, system, question, passages}, sort_keys=True)`; stores `LLMOutcome` as JSON
  - `llm.FakeLLM()`: deterministic. If the question contains the word `unanswerable`, it returns `insufficient_evidence`. Otherwise it returns one sentence (the first sentence of passage `c1`) citing `["c1"]`, plus a second sentence citing `["c99"]` (a deliberately fake citation, so verification is exercised end-to-end).
  - `llm.make_llm(settings) -> LLM` (`fake` → FakeLLM; `claude` → `CachedLLM(ClaudeLLM)` with cache dir `storage/llm_cache`)
  - `verify.verify_draft(draft: AnswerDraft, valid_labels: set[str]) -> tuple[AnswerDraft, int]`: returns the cleaned draft and the number of dropped citations
  - `service.answer_question(conn, embedder, llm, cfg, user_id, question, doc_ids) -> AskResponse`. Raises `NoDocumentsError` when `ready_doc_ids` is empty, and `LLMUnavailableError` on `anthropic.APIError` / timeout.
- `SYSTEM_PROMPT` (exact copy, in `llm.py`):

```
You answer questions using only the numbered passages provided. Each passage is labelled like [c1].
- Every sentence you write must cite at least one passage label that directly supports it.
- Use only information stated in the passages. Do not use outside knowledge, and do not infer beyond what the passages say.
- If the passages fully answer the question, use status "answered".
- If they answer only part of it, answer that part, use status "partial", and describe what is missing in "missing".
- If they do not answer it, use status "insufficient_evidence", return no sentences, and describe what is missing in "missing".
```

  The user message lists passages as `[c1] (document_name — location)\n<text>` separated by blank lines, then `Question: <question>`.

- [ ] **Step 1: Write the failing verifier tests**

```python
def d(*sents, status="answered"):
    return AnswerDraft(status=status, sentences=[DraftSentence(text=t, citations=c) for t, c in sents], missing="")

def test_drops_unknown_citations_keeps_valid():
    out, dropped = verify_draft(d(("A.", ["c1", "c9"])), {"c1", "c2"})
    assert out.sentences[0].citations == ["c1"] and dropped == 1

def test_drops_sentence_left_uncited():
    out, dropped = verify_draft(d(("A.", ["c1"]), ("B.", ["c7"])), {"c1"})
    assert [s.text for s in out.sentences] == ["A."] and dropped == 1

def test_all_dropped_becomes_insufficient():
    out, _ = verify_draft(d(("A.", ["c7"]), ("B.", [])), {"c1"})
    assert out.status == "insufficient_evidence" and out.sentences == []

def test_answered_with_dropped_sentence_becomes_partial():
    out, _ = verify_draft(d(("A.", ["c1"]), ("B.", ["c7"])), {"c1"})
    assert out.status == "partial"
```

- [ ] **Step 2: Write the failing service tests**

```python
def test_gate_fail_returns_not_found_without_llm(seeded):
    conn, user = seeded; llm = SpyLLM()
    r = answer_question(conn, HashEmbedder(), llm, PipelineConfig(), user, "Who won the 1998 world cup?", None)
    assert r.status == "not_found" and llm.calls == 0 and r.chunks   # closest chunks shown

def test_answer_maps_citations_in_first_appearance_order(seeded):
    conn, user = seeded
    llm = ScriptedLLM(d(("X.", ["c2"]), ("Y.", ["c1", "c2"])))
    r = answer_question(conn, HashEmbedder(), llm, PipelineConfig(), user, "refund days", None)
    assert [s.citations for s in r.sentences] == [[1], [2, 1]]
    assert r.citations[0].chunk_id == r.chunks[1].chunk_id   # n=1 is c2

def test_verification_toggle(seeded):
    conn, user = seeded
    on = answer_question(conn, HashEmbedder(), FakeLLM(), PipelineConfig(), user, "refund days", None)
    off = answer_question(conn, HashEmbedder(), FakeLLM(), PipelineConfig(verify_citations=False), user, "refund days", None)
    assert on.dropped_citations == 1 and len(on.sentences) == 1
    assert off.dropped_citations == 0 and len(off.sentences) == 2   # unverified citation kept, mapped to n with chunk_id None

def test_llm_refusal_or_unparseable_becomes_insufficient(seeded):
    conn, user = seeded
    r = answer_question(conn, HashEmbedder(), ScriptedLLM(None, stop_reason="refusal"), PipelineConfig(), user, "refund days", None)
    assert r.status == "insufficient_evidence"

def test_unparseable_retries_once(seeded):
    conn, user = seeded; llm = ScriptedLLM(None, stop_reason="max_tokens")
    answer_question(conn, HashEmbedder(), llm, PipelineConfig(), user, "refund days", None)
    assert llm.calls == 2

def test_no_ready_documents(conn, user):
    with pytest.raises(NoDocumentsError):
        answer_question(conn, HashEmbedder(), FakeLLM(), PipelineConfig(), user, "anything", None)

def test_cached_llm_hits_disk_once(tmp_path):
    spy = SpyLLM(); c = CachedLLM(spy, tmp_path)
    p = [Passage(label="c1", document_name="a", location="p. 1", text="t")]
    c.draft("q", p, "m"); c.draft("q", p, "m")
    assert spy.calls == 1
```

`SpyLLM` and `ScriptedLLM` are test doubles in `tests/conftest.py`. With verification off, a citation to an unknown label is still numbered, and its `citations[]` entry has `chunk_id=None`, `document_id=None`, `document_name="(unknown)"`, `location=""`, `page=None`. That keeps RQ3's "off" condition observable in the UI and in results.

- [ ] **Step 3: Run to verify fail** · `.venv/bin/pytest tests/test_verify.py tests/test_answer_service.py -v`

- [ ] **Step 4: Implement the answer package**

`service` times retrieval and generation separately (`time.perf_counter`, rounded to int ms). A refusal sets `missing` to `"The model declined to answer this question."`. Read the `anthropic` README at `/private/tmp/.../claude-api/python/claude-api/` (or the SDK repo) to confirm the `messages.parse` signature before writing `ClaudeLLM`.

- [ ] **Step 5: Run to verify pass**, then commit

```bash
git add backend && git commit -m "feat(answer): structured Claude answers, citation verification, response cache"
```

---

### Task 9: Ask endpoint and dev runner

**Files:**
- Create: `backend/app/ask/__init__.py`, `routes.py`; `backend/tests/test_ask_api.py`; `Makefile`
- Modify: `backend/app/main.py` (a module-level `app = create_app(Settings())` for uvicorn; `create_app` builds the embedder and LLM from settings when they are not passed)

**Interfaces:**
- Consumes: `answer_question`, `NoDocumentsError`, `LLMUnavailableError`
- Produces: `POST /api/ask {question: str (stripped, 1..1000 chars), doc_ids: list[str] | null}` → 200 `AskResponse` | 400 `{"detail": "Upload a document first"}` | 422 | 502 `{"detail": "The answer service is unavailable. Please try again."}`. Makefile targets: `setup` (venv + pip install + `npm install` in frontend), `dev` (uvicorn `app.main:app --reload --port 8000` and `next dev` together, Ctrl-C stops both), `test` (backend pytest only; Task 10 extends it with frontend `tsc`, lint and Playwright), `experiments` (added in Task 15).

- [ ] **Step 1: Write the failing tests**

```python
def test_ask_end_to_end_with_fake_llm(authed_with_doc):
    r = authed_with_doc.post("/api/ask", json={"question": "How long do refunds take?"})
    body = r.json()
    assert r.status_code == 200 and body["status"] in ("answered", "partial")
    assert body["sentences"][0]["citations"] == [1] and body["citations"][0]["document_name"] == "notes.md"

@pytest.mark.parametrize("q", ["", "   ", "x" * 1001])
def test_question_validation(authed_with_doc, q):   # Review Focus 5
    assert authed_with_doc.post("/api/ask", json={"question": q}).status_code == 422

def test_no_documents(authed):
    r = authed.post("/api/ask", json={"question": "hi"})
    assert r.status_code == 400 and r.json()["detail"] == "Upload a document first"

def test_llm_failure_is_502(authed_with_doc, failing_llm):
    assert authed_with_doc.post("/api/ask", json={"question": "How long do refunds take?"}).status_code == 502

def test_other_users_doc_ids_ignored(client, as_user):
    as_user("a@x.io"); doc = client.post("/api/documents", files=[("files", ("a.md", b"# A\nRefunds take 14 days.\n", "text/markdown"))]).json()[0]["id"]
    as_user("b@x.io")
    assert client.post("/api/ask", json={"question": "refunds", "doc_ids": [doc]}).status_code == 400
```

`failing_llm` swaps `app.state.llm` for an LLM whose `draft` raises `LLMUnavailableError`.

- [ ] **Step 2: Run to verify fail**, **Step 3: implement**, **Step 4: run the full suite** (`.venv/bin/pytest -v`, all pass)

- [ ] **Step 5: Manual check with the real stack**

Run: `cp backend/.env.example backend/.env` and add `ANTHROPIC_API_KEY`, then `cd backend && .venv/bin/uvicorn app.main:app --port 8000`. Then `curl` signup → upload a markdown file → ask an in-document question and an off-topic one.
Expected: the first returns `answered` with citation `[1]`, the second `not_found`. The first run downloads the fastembed model (~130 MB).

- [ ] **Step 6: Commit**

```bash
git add backend Makefile && git commit -m "feat(api): ask endpoint; Makefile dev runner"
```

---

### Task 10: Frontend scaffold, auth pages, and route protection

**Files:**
- Create: `frontend/` via `npx create-next-app@15 frontend --ts --tailwind --eslint --app --no-src-dir --import-alias "@/*"`; then `frontend/next.config.ts`, `middleware.ts`, `lib/types.ts`, `lib/api.ts`, `app/login/page.tsx`, `app/signup/page.tsx`, `app/page.tsx` (placeholder showing the email), `components/Header.tsx`, `playwright.config.ts`, `e2e/auth.spec.ts`

**Interfaces:**
- Produces:
  - `next.config.ts` rewrites `/api/:path*` → `${process.env.BACKEND_URL ?? "http://localhost:8000"}/api/:path*`
  - `middleware.ts`: for every path except `/login`, `/signup`, `/api/*`, `/_next/*`, `/favicon.ico`, redirect to `/login?next=<path>` when the `session` cookie is absent
  - `lib/types.ts`: TS mirrors of `User`, `Document`, `ChunkRow`, `AskResponse` (field names exactly as the backend)
  - `lib/api.ts`: `api<T>(path: string, init?: RequestInit): Promise<T>` (credentials `same-origin`; on 401 sets `window.location.href = "/login"`; throws `ApiError {status, detail}` on non-2xx), plus `me()`, `login(email, password, remember)`, `signup(email, password)`, `logout()`
  - `Header`: app name "RAG Studio", user email, "Log out" button
  - `playwright.config.ts`: two `webServer` entries. Backend: `cd ../backend && EMBEDDER=hash LLM=fake DATABASE_PATH=<tmp>/e2e.db STORAGE_DIR=<tmp>/e2e .venv/bin/uvicorn app.main:app --port 8000`. Frontend: `npm run dev -- --port 3000`. `baseURL` `http://localhost:3000`.

- [ ] **Step 1: Write the failing e2e test** (`e2e/auth.spec.ts`)

```ts
test("signup, persists across reload, logout, bad login", async ({ page }) => {
  const email = `u${Date.now()}@x.io`;
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await page.getByRole("link", { name: "Create an account" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("password1");
  await page.getByRole("button", { name: "Sign up" }).click();
  await expect(page.getByText(email)).toBeVisible();
  await page.reload();
  await expect(page.getByText(email)).toBeVisible();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrongpass1");
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByText("Invalid email or password")).toBeVisible();
});
```

The login page has Email and Password fields, a "Remember me" checkbox (checked by default), a "Log in" button, and a "Create an account" link. The signup page mirrors it with a "Sign up" button. After a successful login, go to `next` or `/`.

- [ ] **Step 2: Run to verify fail**

Run: `cd frontend && npx playwright install chromium && npx playwright test e2e/auth.spec.ts` · Expected: FAIL.

- [ ] **Step 3: Implement the pages, middleware, api client and header**

Styling: Tailwind, neutral palette, a centred card on the auth pages.

- [ ] **Step 4: Run to verify pass**, plus `npx tsc --noEmit && npm run lint`; extend the Makefile `test` target with these three frontend commands

- [ ] **Step 5: Commit**

```bash
git add frontend && git commit -m "feat(frontend): Next.js scaffold, auth pages, route protection"
```

---

### Task 11: Tabs and Documents tab

**Files:**
- Create: `frontend/components/Tabs.tsx`, `components/documents/DocumentsTab.tsx`, `UploadPanel.tsx`, `DocumentsTable.tsx`; `frontend/e2e/documents.spec.ts`; `frontend/e2e/fixtures/handbook.md` (≈ 10 lines, including "Refunds are issued within 14 days of purchase.")
- Modify: `frontend/app/page.tsx` (Header + Tabs; `?tab=documents` selects the Documents tab, default `dashboard`; switching tabs uses `router.replace`)

**Interfaces:**
- Consumes: `api`, `Document`
- Produces: `DocumentsTab` (self-contained, fetches its own list). `useDocuments()` hook in `lib/api.ts` returns `{documents, refresh}` and polls every 2 s while any doc is `processing`; Task 12 reuses it.

- [ ] **Step 1: Write the failing e2e test**

```ts
test("upload, see ready, import URL validation, delete", async ({ page }) => {
  await signUpFresh(page);                                   // helper in e2e/helpers.ts
  await page.getByRole("tab", { name: "Documents" }).click();
  await expect(page).toHaveURL(/tab=documents/);
  await page.getByLabel("Upload files").setInputFiles("e2e/fixtures/handbook.md");
  const row = page.getByRole("row", { name: /handbook\.md/ });
  await expect(row.getByText(/Ready · \d+ chunks?/)).toBeVisible({ timeout: 15000 });
  await page.getByPlaceholder("https://…").fill("http://127.0.0.1/secret");
  await page.getByRole("button", { name: "Import" }).click();
  await expect(page.getByRole("row", { name: /127\.0\.0\.1/ }).getByText("Failed")).toBeVisible({ timeout: 15000 });
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(row).toHaveCount(0);
});
```

Table columns are Name, Type, Size, Status, Uploaded, plus an action. Status text is `Processing…` (with a spinner), `Ready · N chunk(s)`, or `Failed` (`title` = error). Delete confirms with `window.confirm("Delete <name>? This cannot be undone.")`. The upload area accepts drag-and-drop and has a visually hidden `<input type="file" multiple aria-label="Upload files" accept=".pdf,.docx,.md,.txt,.html">`. Upload errors (400 detail) show in an inline alert.

- [ ] **Step 2: Run to verify fail**, **Step 3: implement**, **Step 4: run to verify pass** (`npx playwright test e2e/documents.spec.ts`, then `tsc` and lint)

- [ ] **Step 5: Commit**

```bash
git add frontend && git commit -m "feat(frontend): tabs and Documents tab with upload, URL import, delete"
```

---

### Task 12: Dashboard tab

**Files:**
- Create: `frontend/components/dashboard/Dashboard.tsx`, `SearchBar.tsx`, `AnswerPane.tsx`, `SourcesList.tsx`, `ChunksList.tsx`; `frontend/e2e/dashboard.spec.ts`
- Modify: `frontend/app/page.tsx` (render Dashboard for the default tab)

**Interfaces:**
- Consumes: `useDocuments`, `api`, `AskResponse`, `ChunkRow`
- Produces:
  - `Dashboard` owns the state: `selectedDocIds` (defaults to all ready docs), `answer: AskResponse | null`, `highlightedChunkId`, `browsingDocId`.
  - `SearchBar`: a textbox labelled "Ask a question" and an "Ask" button, disabled when the input is blank or loading.
  - `AnswerPane`: renders sentences with `<button aria-label="Citation n">[n]</button>` badges. Status banners: `partial` → "Partial answer — not covered: {missing}"; `insufficient_evidence` → "The documents don't contain enough evidence to answer this." + missing; `not_found` → "Not found in your documents". A 502 shows an error banner with a "Retry" button. When `dropped_citations > 0` it shows "{n} unsupported citation(s) removed".
  - `SourcesList`: ready documents with checkboxes (passed as `doc_ids`, or `null` when all are checked). Cited documents get a "cited" badge. Clicking a name sets `browsingDocId` and loads `/api/documents/{id}/chunks` into ChunksList while no answer is shown.
  - `ChunksList`: cards with `id="chunk-{chunk_id}"`, `data-highlighted`, document name, location, score (3 dp), "vector #r" / "BM25 #r" badges, and a "View in document" link to `/api/documents/{document_id}/file` (+ `#page=N` when `page` is set), opened with `target="_blank"`.
  - Citation click sets `highlightedChunkId` and calls `scrollIntoView({block: "center", behavior: "smooth"})`. A citation whose `chunk_id` is null is rendered disabled.
  - Layout: on `lg` and up, a 3-column grid (`Sources 1fr | Answer 2fr | Chunks 1.5fr`) under a full-width search bar; below `lg`, stacked.

- [ ] **Step 1: Write the failing e2e test** (this is the spec's smoke test)

```ts
test("ask, click citation highlights chunk, off-topic refuses", async ({ page }) => {
  await signUpFresh(page);
  await uploadAndWaitReady(page, "e2e/fixtures/handbook.md");     // helper reusing Task 11 steps
  await page.getByRole("tab", { name: "Dashboard" }).click();
  await page.getByLabel("Ask a question").fill("How long do refunds take?");
  await page.getByRole("button", { name: "Ask" }).click();
  await page.getByRole("button", { name: "Citation 1" }).click();
  const chunk = page.locator('[data-highlighted="true"]');
  await expect(chunk).toBeVisible();
  await expect(chunk).toContainText("14 days");
  await expect(chunk.getByRole("link", { name: "View in document" })).toHaveAttribute("href", /\/api\/documents\/.+\/file/);
  await page.getByLabel("Ask a question").fill("Who won the 1998 world cup?");
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByText("Not found in your documents")).toBeVisible();
});
```

- [ ] **Step 2: Run to verify fail**, **Step 3: implement**, **Step 4: run the whole e2e suite plus `tsc` and lint** (all pass)

- [ ] **Step 5: Check visually**

Start `make dev`, open the app in the browser pane, and take screenshots of the Dashboard at desktop and mobile widths after an answer. Check that the columns stack on mobile and nothing scrolls horizontally.

- [ ] **Step 6: Commit**

```bash
git add frontend && git commit -m "feat(frontend): dashboard with search, answer pane, sources, chunks, citation jump"
```

---

### Task 13: Research corpus and labelled questions

**Files:**
- Create: `backend/research/sources/*.md` (6 hand-written sources), `backend/research/build_corpus.py`, `backend/research/corpus/*` (generated, committed), `backend/research/questions.jsonl`, `backend/tests/test_research_data.py`

**Interfaces:**
- Produces:
  - A corpus about one fictional company (domain: "Lumen Robotics"), 6 documents of ~1,500–4,000 words each, together covering every format:
    1. `employee-handbook.pdf` (multi-page; leave policy, expenses, remote work)
    2. `api-reference.md` (endpoints, error codes like `E-4471`, rate limits with exact numbers)
    3. `product-spec-lr7.docx` (headed sections; dimensions, battery specs, model numbers)
    4. `incident-2026-03-14.txt` (postmortem prose; timestamps, ticket ids)
    5. `security-policy.html` (password rules, data-retention periods)
    6. `release-notes.md` (versions `v3.2.0`–`v3.4.1` with dated changes)
  - `build_corpus.py`: renders sources 1, 3 and 5 from their `.md` into PDF (fpdf2, one page per `## ` section), DOCX (headings preserved) and HTML (`<article>` with `<h2>`). It copies 2, 4 and 6. It is idempotent.
  - `questions.jsonl`, one object per line: `{"id": "q001", "question": str, "answerable": bool, "tag": "natural"|"exact_term"|"unanswerable", "expected": [{"document": "<corpus filename>", "evidence": "<verbatim substring of the document, 5–20 words>"}]}`. 40 answerable (20 `natural`, 20 `exact_term`) and 20 unanswerable. Unanswerable questions must be topic-adjacent: they ask about plausible facts the corpus does not state (e.g. LR7 price, when the corpus gives no price), not off-topic trivia. About 5 answerable questions need two documents (two `expected` entries).

- [ ] **Step 1: Write the failing data-validity tests**

```python
def test_question_counts_and_schema():
    qs = load_questions()
    assert len(qs) == 60 and len({q["id"] for q in qs}) == 60
    tags = Counter(q["tag"] for q in qs)
    assert tags == {"natural": 20, "exact_term": 20, "unanswerable": 20}
    assert all((q["tag"] == "unanswerable") == (not q["answerable"]) for q in qs)
    assert all(bool(q["expected"]) == q["answerable"] for q in qs)

def test_evidence_is_verbatim_in_parsed_corpus():
    texts = {p.name: " ".join(s.text for s in parse_file(p, p.suffix[1:])) for p in CORPUS.iterdir()}
    norm = lambda s: " ".join(s.split())
    for q in load_questions():
        for e in q["expected"]:
            assert norm(e["evidence"]) in norm(texts[e["document"]]), (q["id"], e)

def test_corpus_covers_all_formats():
    assert {p.suffix for p in CORPUS.iterdir()} == {".pdf", ".md", ".docx", ".txt", ".html"}
```

- [ ] **Step 2: Run to verify fail**, **Step 3: write the sources, the builder and the questions**, then run `python research/build_corpus.py`

Write the labelling guidelines at the same time: what counts as answerable, how evidence is chosen, and how unanswerable questions are made adjacent. They go into a `## Dataset` section of a new `FINDINGS.md`, with placeholder-free text describing the method.

- [ ] **Step 4: Run to verify pass**, then commit

```bash
git add backend/research FINDINGS.md && git commit -m "research: Lumen Robotics corpus and 60 labelled questions"
```

---

### Task 14: Experiment harness, metrics, and LLM judge

**Files:**
- Create: `backend/research/harness.py`, `metrics.py`, `judge.py`, `run_experiment.py`, `experiments/rq1.yaml`, `rq2.yaml`, `rq3.yaml`, `rq4.yaml`; `backend/tests/test_metrics.py`, `backend/tests/test_harness.py`

**Interfaces:**
- Consumes: `PipelineConfig`, `db`, store, `ingest_document`, `retrieve`, `answer_question`, `make_embedder`, `CachedLLM`, `ClaudeLLM`, `FakeLLM`
- Produces:
  - YAML schema: `{name: str, llm: bool, judge: bool, base: {PipelineConfig fields}, variants: [{label: str, <PipelineConfig overrides>}]}`
    - `rq1`: `llm: false`; variants `vector`, `bm25`, `hybrid`
    - `rq2`: `llm: true`; `min_similarity` 0.20–0.60 step 0.05 (9 variants)
    - `rq3`: `llm: true`, `judge: true`; `verify_citations` true/false
    - `rq4`: `llm: true`; `chunk_chars` 1000/2000/4000
  - `harness.Corpus.load(cfg_chunk_chars, embedder) -> (conn, user_id)`: ingests `research/corpus/` into a temp DB, cached per `chunk_chars` within a process
  - `harness.run_question(conn, user_id, embedder, llm, cfg, q, use_llm: bool) -> dict`: the record has `qid, tag, answerable, variant, retrieved: [{chunk_id, document_name, text, vector_rank, bm25_rank, similarity}], gate_passed, max_similarity, strong_term_hit, status, sentences, citations, dropped_citations, raw_citation_count, timings_ms, input_tokens, output_tokens`. With `use_llm=False`, status is `"retrieval_only"`. RQ3 needs the pre-verification draft, so the record also stores `raw_sentences` (the draft before verification) whenever an LLM call is made.
  - `metrics.hit_at_k(record, q, k=8) -> bool`: some expected `(document, evidence)` has a retrieved chunk from that document whose whitespace-normalised text contains the normalised evidence, **or** contains its first 8 words (handles evidence split across chunks). `metrics.mrr(record, q) -> float`. `metrics.summarize(records, questions) -> dict` with `hit@8`, `mrr` (answerable only), `answer_rate`, `refusal_precision`, `refusal_recall`, `citation_validity` (valid ÷ raw citations, from `raw_sentences`), `unsupported_sentence_rate` (when judged), `mean_generate_ms`, `cost_usd` (Sonnet 5.5: $2/M in, $10/M out). Also `summarize_by(records, questions, key="tag")`.
  - `judge.judge_sentence(sentence: str, chunk_texts: list[str]) -> bool` (supported?), using `messages.parse` with output `{supported: bool, reason: str}`, model `claude-sonnet-5-5`, effort `low`, and its own disk cache. The rubric: "Supported only if every factual claim in the sentence is stated in, or directly entailed by, the cited passages."
  - `run_experiment.py <yaml> [--no-cache] [--limit N]`: writes `research/results/<name>/<UTC timestamp>.jsonl` (one record per question × variant, plus a header line with config and git commit) and `summary.json`, and prints a table per variant. The LLM is `CachedLLM(ClaudeLLM)` with cache dir `research/cache/`; `--fake-llm` swaps in `FakeLLM` for dry runs. The embedder is always `FastEmbedder` (the real model) unless `--hash-embedder`.

- [ ] **Step 1: Write the failing metric and harness tests**

```python
def rec(status, retrieved_texts=(), doc="a.md", raw=None):
    return {"status": status, "retrieved": [{"document_name": doc, "text": t, "chunk_id": f"x{i}"} for i, t in enumerate(retrieved_texts)], "raw_sentences": raw or [], "citations": []}

def test_hit_at_k_matches_normalised_evidence():
    q = {"answerable": True, "expected": [{"document": "a.md", "evidence": "refunds take 14 days"}]}
    assert hit_at_k(rec("answered", ["Policy: Refunds  take\n14 days."]), q)
    assert not hit_at_k(rec("answered", ["Refunds take 14 days."], doc="b.md"), q)

def test_mrr_uses_first_matching_rank():
    q = {"answerable": True, "expected": [{"document": "a.md", "evidence": "alpha beta"}]}
    assert mrr(rec("answered", ["zzz", "alpha beta"]), q) == 0.5

def test_refusal_precision_recall():
    qs = [{"qid": "1", "answerable": False}, {"qid": "2", "answerable": False}, {"qid": "3", "answerable": True}]
    rs = [dict(rec("not_found"), qid="1"), dict(rec("answered"), qid="2"), dict(rec("insufficient_evidence"), qid="3")]
    s = summarize(rs, qs)
    assert s["refusal_recall"] == 0.5 and s["refusal_precision"] == 0.5

def test_citation_validity_counts_raw_citations():
    r = dict(rec("answered", raw=[{"text": "A", "citations": ["c1", "c9"]}]), qid="1", valid_labels=["c1"])
    assert summarize([r], [{"qid": "1", "answerable": True, "expected": []}])["citation_validity"] == 0.5

def test_harness_dry_run(tmp_path):
    out = run(["research/experiments/rq3.yaml", "--fake-llm", "--hash-embedder", "--limit", "3", "--results-dir", str(tmp_path)])
    lines = (next(tmp_path.rglob("*.jsonl"))).read_text().splitlines()
    assert len(lines) == 1 + 3 * 2
```

Each record stores `valid_labels` (the passage labels shown to the LLM). `run` is `run_experiment.main(argv) -> int`.

- [ ] **Step 2: Run to verify fail**, **Step 3: implement**, **Step 4: run to verify pass**

- [ ] **Step 5: Commit**

```bash
git add backend && git commit -m "research: experiment harness, metrics, LLM judge"
```

---

### Task 15: Run experiments, plots, findings, and README

**Files:**
- Create: `backend/research/plots.py`, `backend/research/spotcheck.py`, `README.md`
- Modify: `Makefile` (`experiments` target: run rq1–rq4, then `plots.py`), `FINDINGS.md`, `backend/.env.example` / `app/config.py` defaults (only if the findings justify a change)

**Interfaces:**
- Consumes: `results/<rq>/*.jsonl` (latest file per RQ), `metrics.summarize`, `summarize_by`
- Produces:
  - `plots.py`, which writes to `research/plots/`:
    - `rq1_retrieval.png`: grouped bars of hit@8 and MRR per mode, split by tag
    - `rq2_threshold.png`: answer rate and refusal recall against `min_similarity`, with the trade-off curve
    - `rq3_verification.png`: citation validity and unsupported-sentence rate, verification off vs on
    - `rq4_chunk_size.png`: hit@8, answer rate and citation validity against `chunk_chars`
    - One consistent palette, labelled axes, values annotated.
  - `spotcheck.py`: `export` samples 30 judged sentences (fixed seed 7) to `research/results/rq3/spotcheck.csv` with an empty `human_label` column; `score` reports judge–human agreement %.

- [ ] **Step 1: Estimate cost and get approval**

Run `run_experiment.py --limit 5` on rq4 (the largest LLM sweep) and read `cost_usd` from its summary. Extrapolate to the full four RQs: roughly 60 questions × (9 + 1 + 3 deduplicated by cache) calls, plus judge calls. **Ask the user to approve the estimate before the full run.**

- [ ] **Step 2: Write the hypotheses into FINDINGS.md before running**

One line per RQ, e.g. "H1: hybrid ≥ vector on `exact_term` hit@8 by ≥ 10 points; equal on `natural`."

- [ ] **Step 3: Run `make experiments`**

Expected: four results folders, four `summary.json` files, four PNGs. Then run RQ3 uncached 3× (`--no-cache`) to measure run-to-run variance.

- [ ] **Step 4: Judge spot-check**

Run `spotcheck.py export`. **The user hand-labels the 30 rows** (they are the researcher). Then `spotcheck.py score` gives the agreement %.

- [ ] **Step 5: Write FINDINGS.md**

For each RQ: Question & hypothesis → Method → Results (table + plot) → Interpretation. Close with sections on threats to validity (small, single-domain, self-written dataset; LLM-judge bias plus measured agreement; cache-pinned outputs plus measured variance) and on the chosen defaults. Set `MIN_SIMILARITY`, `CHUNK_CHARS` and `RETRIEVAL_MODE` defaults to what the results support, and re-run `pytest` afterwards.

- [ ] **Step 6: README**

Cover:
- a one-paragraph pitch framed as R&D, linking to FINDINGS.md
- an architecture diagram (ASCII or mermaid) and a key-results table
- setup (`brew install python@3.12`, `make setup`, `.env`, `make dev`)
- `make test` and `make experiments`
- next steps (spec §13)

- [ ] **Step 7: Final verification**

Run `make test` (backend pytest, frontend tsc, lint and Playwright: all pass). Then do a manual run of `make dev` with the real Claude and fastembed: upload the 6 corpus docs, ask 2 answerable questions, 1 unanswerable and 1 exact-term question, and take screenshots.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "research: run experiments, plots, FINDINGS report, README"
```
