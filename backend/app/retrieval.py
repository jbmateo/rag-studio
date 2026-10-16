"""Hybrid retrieval (vector + BM25 fused with RRF) and the relevance gate."""
import math
import re

from pydantic import BaseModel

from app.config import PipelineConfig
from app.embeddings import Embedder
from app.store import ChunkRow, get_chunks, load_vectors, ready_doc_ids

CANDIDATES = 20
_WORD = re.compile(r"[^\W_]+")
STOPWORDS = frozenset(
    """a an the and or but nor if then else of to in on at by for with from into onto about as
    is are was were be been being am do does did doing done have has had having
    what which who whom whose when where why how that this these those there here
    it its i me my we our you your he she they them his her their
    can could should would will shall may might must not no so than too very
    s t""".split()
)


class RetrievedChunk(BaseModel):
    chunk: ChunkRow
    score: float
    similarity: float | None = None
    vector_rank: int | None = None
    bm25_rank: int | None = None


class RetrievalResult(BaseModel):
    chunks: list[RetrievedChunk]
    max_similarity: float | None
    strong_term_hit: bool | None
    gate_passed: bool


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def query_terms(question: str) -> list[str]:
    seen: dict[str, None] = {}
    for tok in _tokens(question):
        if tok not in STOPWORDS:
            seen.setdefault(tok)
    return list(seen)


def rrf_fuse(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: -kv[1])  # stable: ties keep first-seen order


def _fts_query(terms: list[str]) -> str:
    return " OR ".join('"' + t.replace('"', "") + '"' for t in terms)


def _bm25(conn, user_id: str, terms: list[str], doc_ids: list[str] | None) -> list[tuple[str, float]]:
    if not terms:
        return []
    sql = (
        "SELECT c.id AS id, bm25(chunks_fts) AS s FROM chunks_fts"
        " JOIN chunks c ON c.rowid = chunks_fts.rowid"
        " JOIN documents d ON d.id = c.document_id"
        " WHERE chunks_fts MATCH ? AND c.user_id=? AND d.user_id=? AND d.status='ready'"
    )
    params: list = [_fts_query(terms), user_id, user_id]
    if doc_ids is not None:
        if not doc_ids:
            return []
        sql += f" AND d.id IN ({','.join('?' * len(doc_ids))})"
        params += doc_ids
    rows = conn.execute(sql + " ORDER BY bm25(chunks_fts) LIMIT ?", [*params, CANDIDATES]).fetchall()
    return [(r["id"], -r["s"]) for r in rows]


def _strong_term_hit(terms: list[str], texts: list[str]) -> bool:
    if not terms:
        return False
    need = math.ceil(len(terms) / 2)
    return any(len(set(terms) & set(_tokens(t))) >= need for t in texts)


def retrieve(
    conn, embedder: Embedder, cfg: PipelineConfig, user_id: str, question: str,
    doc_ids: list[str] | None = None,
) -> RetrievalResult:
    mode = cfg.retrieval_mode
    use_vec = mode in ("vector", "hybrid")
    use_bm25 = mode in ("bm25", "hybrid")
    empty_term_hit = False if use_bm25 else None

    if not ready_doc_ids(conn, user_id, doc_ids):
        return RetrievalResult(chunks=[], max_similarity=None, strong_term_hit=empty_term_hit, gate_passed=False)

    sims: dict[str, float] = {}
    vec_ranking: list[str] = []
    max_sim: float | None = None
    if use_vec:
        ids, matrix = load_vectors(conn, user_id, doc_ids)
        if ids:
            q = embedder.embed([question])[0]
            scores = matrix @ q
            max_sim = float(scores.max())
            order = sorted(range(len(ids)), key=lambda i: -scores[i])[:CANDIDATES]
            vec_ranking = [ids[i] for i in order]
            sims = {ids[i]: float(scores[i]) for i in order}

    terms = query_terms(question)
    bm25_hits = _bm25(conn, user_id, terms, doc_ids) if use_bm25 else []
    bm25_ranking = [cid for cid, _ in bm25_hits]
    bm25_scores = dict(bm25_hits)

    if mode == "hybrid":
        ranked = rrf_fuse([vec_ranking, bm25_ranking])
    elif mode == "vector":
        ranked = [(cid, sims[cid]) for cid in vec_ranking]
    else:
        ranked = list(bm25_hits)
    ranked = ranked[: cfg.top_k]

    chunk_rows = get_chunks(conn, user_id, [cid for cid, _ in ranked])
    vrank = {cid: i for i, cid in enumerate(vec_ranking, 1)}
    brank = {cid: i for i, cid in enumerate(bm25_ranking, 1)}
    out = [
        RetrievedChunk(
            chunk=chunk_rows[cid], score=score, similarity=sims.get(cid),
            vector_rank=vrank.get(cid), bm25_rank=brank.get(cid),
        )
        for cid, score in ranked
        if cid in chunk_rows
    ]

    term_hit: bool | None = None
    if use_bm25:
        texts = [r.text for r in get_chunks(conn, user_id, bm25_ranking).values()]
        term_hit = _strong_term_hit(terms, texts)
    sim_ok = max_sim is not None and max_sim >= cfg.min_similarity
    if mode == "vector":
        passed = sim_ok
    elif mode == "bm25":
        passed = bool(term_hit)
    else:
        passed = sim_ok or bool(term_hit)
    return RetrievalResult(chunks=out, max_similarity=max_sim, strong_term_hit=term_hit, gate_passed=passed)
