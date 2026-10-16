import pytest

from app.config import PipelineConfig
from app.embeddings import HashEmbedder
from app.retrieval import query_terms, retrieve, rrf_fuse


def test_rrf_fuse_orders_by_combined_rank():
    fused = rrf_fuse([["a", "b", "c"], ["b", "c", "d"]])
    assert [i for i, _ in fused] == ["b", "c", "a", "d"]
    assert dict(fused)["b"] == pytest.approx(1 / 62 + 1 / 61)


def test_query_terms_drops_stopwords():
    assert query_terms("What is the refund window for ORD-4471?") == ["refund", "window", "ord", "4471"]


def test_query_terms_dedupes_and_keeps_single_letters():
    assert query_terms("What does E-4471 mean? e 4471") == ["e", "4471", "mean"]


@pytest.mark.parametrize("q", ['"unbalanced', "refund*", "NEAR(a b)", "a AND OR NOT", "col:val -x", "()", "?!"])
def test_fts_special_characters_do_not_crash(seeded, q):  # Review Focus 1
    conn, user = seeded
    retrieve(conn, HashEmbedder(), PipelineConfig(), user, q)
    retrieve(conn, HashEmbedder(), PipelineConfig(retrieval_mode="bm25"), user, q)


def test_all_stopwords_skips_bm25(seeded):
    conn, user = seeded
    r = retrieve(conn, HashEmbedder(), PipelineConfig(retrieval_mode="bm25"), user, "what is the")
    assert r.chunks == [] and r.strong_term_hit is False and not r.gate_passed


def test_exact_term_question_passes_gate_via_terms(seeded):
    conn, user = seeded
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
    assert v.chunks and b.chunks
    assert all(c.bm25_rank is None for c in v.chunks) and v.strong_term_hit is None
    assert all(c.vector_rank is None for c in b.chunks) and b.max_similarity is None
    assert all(c.score > 0 for c in b.chunks)
    assert all(c.score == c.similarity for c in v.chunks)


def test_hybrid_populates_both_ranks(seeded):
    conn, user = seeded
    r = retrieve(conn, HashEmbedder(), PipelineConfig(), user, "refund days")
    top = r.chunks[0]
    assert "Refunds take 14 days" in top.chunk.text
    assert top.vector_rank == 1 and top.bm25_rank == 1 and top.similarity is not None
    assert r.max_similarity is not None and r.strong_term_hit is True


def test_no_ready_docs(conn, user):
    r = retrieve(conn, HashEmbedder(), PipelineConfig(), user, "refund days")
    assert r.chunks == [] and r.max_similarity is None and r.strong_term_hit is False
    assert r.gate_passed is False


def test_scoped_to_user_and_doc_ids(seeded_two_users):
    conn, a, b, a_doc_ids = seeded_two_users
    assert retrieve(conn, HashEmbedder(), PipelineConfig(), b, "refund days").chunks == []
    r = retrieve(conn, HashEmbedder(), PipelineConfig(), a, "refund days", doc_ids=a_doc_ids[:1])
    assert r.chunks and {c.chunk.document_id for c in r.chunks} <= {a_doc_ids[0]}
    full = retrieve(conn, HashEmbedder(), PipelineConfig(), a, "refund days")
    assert {c.chunk.document_id for c in full.chunks} == set(a_doc_ids)


def test_top_k_limits_results(seeded):
    conn, user = seeded
    r = retrieve(conn, HashEmbedder(), PipelineConfig(top_k=2), user, "refund days")
    assert len(r.chunks) <= 2
