"""Experiment harness: corpus ingestion, per-question records, experiment YAML loading."""
import atexit
import dataclasses
import json
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import yaml

from app.answer.service import LLMUnavailableError, answer_question_detailed
from app.config import BACKEND_DIR, PipelineConfig
from app.db import connect, init_db
from app.ingest.pipeline import ingest_document
from app.retrieval import retrieve
from app.store import create_document

RESEARCH_DIR = BACKEND_DIR / "research"
CORPUS_DIR = RESEARCH_DIR / "corpus"
QUESTIONS_PATH = RESEARCH_DIR / "questions.jsonl"
_FIELDS = {f.name for f in dataclasses.fields(PipelineConfig)}


class Corpus:
    """The research corpus ingested into a throwaway SQLite DB, once per chunk size per process."""

    _cache: dict[tuple[int, int], tuple] = {}

    @classmethod
    def load(cls, chunk_chars: int, embedder):
        key = (chunk_chars, id(embedder))
        if key not in cls._cache:
            tmp = Path(tempfile.mkdtemp(prefix="rag-studio-corpus-"))
            atexit.register(shutil.rmtree, tmp, ignore_errors=True)
            conn = connect(tmp / "research.db")
            init_db(conn)
            user_id = uuid.uuid4().hex
            conn.execute("INSERT INTO users(id, email, password_hash) VALUES (?,?,?)",
                         (user_id, f"research-{chunk_chars}@example.test", "x"))
            conn.commit()
            cfg = PipelineConfig(chunk_chars=chunk_chars)
            for path in sorted(CORPUS_DIR.iterdir()):
                doc = create_document(
                    conn, user_id, name=path.name, source_type=path.suffix[1:], source_url=None,
                    file_path=str(path), size_bytes=path.stat().st_size,
                )
                ingest_document(conn, embedder, cfg, doc.id)
                status = conn.execute("SELECT status, error FROM documents WHERE id=?", (doc.id,)).fetchone()
                if status["status"] != "ready":
                    raise RuntimeError(f"Ingesting {path.name} failed: {status['error']}")
            # keep a reference to the embedder so its id() cannot be reused while cached
            cls._cache[key] = (conn, user_id, embedder)
        conn, user_id, _ = cls._cache[key]
        return conn, user_id


class _Spy:
    """Wraps an LLM to learn whether every call it made was served from the cache."""

    def __init__(self, inner):
        self.inner, self.cached = inner, []

    def draft(self, question, passages, model, **kw):
        out = self.inner.draft(question, passages, model, **kw)
        self.cached.append(bool(out.cached))
        return out


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _chunk_view(rc) -> dict:
    return {
        "chunk_id": rc.chunk.id, "document_name": rc.chunk.document_name, "text": rc.chunk.text,
        "vector_rank": rc.vector_rank, "bm25_rank": rc.bm25_rank, "similarity": rc.similarity,
        "score": rc.score,
    }


def _judge_sentences(judge, resp, retrieved: dict[str, str]) -> list[dict]:
    """Judge the sentences the user would see; an unknown citation has no text and so cannot support."""
    texts_by_n = {c.n: retrieved.get(c.chunk_id) for c in resp.citations}
    out = []
    for s in resp.sentences:
        texts = [texts_by_n[n] for n in s.citations if texts_by_n.get(n)]
        # judge_called False: no resolvable cited passage, so it is unsupported by rule, not by the judge.
        out.append({"text": s.text, "supported": judge.judge_sentence(s.text, texts) if texts else False,
                    "judge_called": bool(texts)})
    return out


def run_question(conn, user_id, embedder, llm, cfg: PipelineConfig, q: dict, use_llm: bool, judge=None) -> dict:
    record = {
        "qid": q["id"], "tag": q["tag"], "answerable": q["answerable"], "variant": None,
        "retrieved": [], "gate_passed": False, "max_similarity": None, "strong_term_hit": None,
        "status": "retrieval_only", "sentences": [], "raw_sentences": [], "citations": [],
        "dropped_citations": 0, "raw_citation_count": 0, "valid_labels": [], "judgments": [],
        "timings_ms": {"retrieve": 0, "generate": 0}, "input_tokens": 0, "output_tokens": 0,
        "llm_called": False, "cached": False,
    }
    if not use_llm:
        t0 = time.perf_counter()
        result = retrieve(conn, embedder, cfg, user_id, q["question"], None)
        record["timings_ms"]["retrieve"] = _ms(t0)
        record["retrieved"] = [_chunk_view(rc) for rc in result.chunks]
        record["valid_labels"] = [f"c{i}" for i in range(1, len(result.chunks) + 1)]
        record.update(gate_passed=result.gate_passed, max_similarity=result.max_similarity,
                      strong_term_hit=result.strong_term_hit)
        return record

    spy = _Spy(llm)
    try:
        resp, trace = answer_question_detailed(conn, embedder, spy, cfg, user_id, q["question"], None)
    except LLMUnavailableError as e:
        record.update(status="error", error=str(e), llm_called=True)
        return record

    retrieved = [_chunk_view(rc) for rc in trace.retrieval.chunks]
    raw = [s.model_dump() for s in trace.raw_sentences]
    record.update(
        retrieved=retrieved, gate_passed=trace.retrieval.gate_passed,
        max_similarity=trace.retrieval.max_similarity, strong_term_hit=trace.retrieval.strong_term_hit,
        status=resp.status, sentences=[s.model_dump() for s in resp.sentences], raw_sentences=raw,
        citations=[c.model_dump() for c in resp.citations], dropped_citations=resp.dropped_citations,
        raw_citation_count=sum(len(s["citations"]) for s in raw), valid_labels=trace.valid_labels,
        timings_ms=resp.timings_ms.model_dump(), input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens, llm_called=bool(spy.cached),
        cached=bool(spy.cached) and all(spy.cached),
    )
    if judge is not None and resp.sentences:
        record["judgments"] = _judge_sentences(judge, resp, {c["chunk_id"]: c["text"] for c in retrieved})
    return record


def load_questions(path: Path = QUESTIONS_PATH, limit: int | None = None) -> list[dict]:
    qs = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
    return qs[:limit] if limit is not None else qs


def load_experiment(path: str | Path) -> dict:
    p = Path(path)
    if not p.exists():
        p = BACKEND_DIR / path
    exp = yaml.safe_load(p.read_text())
    exp.setdefault("llm", False)
    exp.setdefault("judge", False)
    exp.setdefault("base", {})
    for overrides in [exp["base"], *exp["variants"]]:
        unknown = set(overrides) - _FIELDS - {"label"}
        if unknown:
            raise ValueError(f"{p}: unknown PipelineConfig field(s) {sorted(unknown)}")
    if any("label" not in v for v in exp["variants"]):
        raise ValueError(f"{p}: every variant needs a label")
    return exp


def variant_config(exp: dict, variant: dict) -> PipelineConfig:
    return PipelineConfig(**{**exp["base"], **{k: v for k, v in variant.items() if k != "label"}})


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=BACKEND_DIR, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
