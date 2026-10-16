from research.metrics import hit_at_k, mrr, summarize, summarize_by


def rec(status, retrieved_texts=(), doc="a.md", raw=None):
    return {"status": status, "retrieved": [{"document_name": doc, "text": t, "chunk_id": f"x{i}"} for i, t in enumerate(retrieved_texts)], "raw_sentences": raw or [], "citations": []}


def test_hit_at_k_matches_normalised_evidence():
    q = {"answerable": True, "expected": [{"document": "a.md", "evidence": "refunds take 14 days"}]}
    assert hit_at_k(rec("answered", ["Policy: Refunds  take\n14 days."]), q)
    assert not hit_at_k(rec("answered", ["Refunds take 14 days."], doc="b.md"), q)


def test_hit_at_k_first_eight_words_handles_split_evidence():
    ev = "one two three four five six seven eight nine ten"
    q = {"answerable": True, "expected": [{"document": "a.md", "evidence": ev}]}
    assert hit_at_k(rec("answered", ["intro one two three four five six seven eight and then it is cut"]), q)
    assert not hit_at_k(rec("answered", ["one two three four five six seven"]), q)


def test_hit_at_k_respects_k_and_any_expected_entry_counts():
    q = {"answerable": True, "expected": [
        {"document": "a.md", "evidence": "alpha beta"}, {"document": "a.md", "evidence": "gamma delta"}]}
    texts = ["zzz"] * 8 + ["alpha beta"]
    assert not hit_at_k(rec("answered", texts), q, k=8)
    assert hit_at_k(rec("answered", ["gamma delta"]), q)


def test_mrr_uses_first_matching_rank():
    q = {"answerable": True, "expected": [{"document": "a.md", "evidence": "alpha beta"}]}
    assert mrr(rec("answered", ["zzz", "alpha beta"]), q) == 0.5
    assert mrr(rec("answered", ["zzz"]), q) == 0.0


def test_refusal_precision_recall():
    qs = [{"qid": "1", "answerable": False}, {"qid": "2", "answerable": False}, {"qid": "3", "answerable": True}]
    rs = [dict(rec("not_found"), qid="1"), dict(rec("answered"), qid="2"), dict(rec("insufficient_evidence"), qid="3")]
    s = summarize(rs, qs)
    assert s["refusal_recall"] == 0.5 and s["refusal_precision"] == 0.5


def test_answer_rate_counts_answered_and_partial_over_answerable():
    qs = [{"id": "1", "answerable": True, "expected": []}, {"id": "2", "answerable": True, "expected": []},
          {"id": "3", "answerable": True, "expected": []}, {"id": "4", "answerable": False}]
    rs = [dict(rec("answered"), qid="1"), dict(rec("partial"), qid="2"), dict(rec("not_found"), qid="3"), dict(rec("answered"), qid="4")]
    assert summarize(rs, qs)["answer_rate"] == 2 / 3


def test_citation_validity_counts_raw_citations():
    r = dict(rec("answered", raw=[{"text": "A", "citations": ["c1", "c9"]}]), qid="1", valid_labels=["c1"])
    assert summarize([r], [{"qid": "1", "answerable": True, "expected": []}])["citation_validity"] == 0.5


def test_unsupported_rate_excludes_unparseable_judgments_and_counts_them():
    qs = [{"qid": "1", "answerable": True, "expected": []}]
    r = dict(rec("answered"), qid="1", judgments=[{"supported": True}, {"supported": False}, {"supported": None}, {"supported": False}])
    s = summarize([r], qs)
    assert s["unsupported_sentence_rate"] == 2 / 3 and s["judge_unparsed"] == 1 and s["judged_sentences"] == 3


def test_retrieval_only_records_have_no_answer_metrics():
    qs = [{"qid": "1", "answerable": True, "expected": [{"document": "a.md", "evidence": "alpha beta"}]}]
    s = summarize([dict(rec("retrieval_only", ["alpha beta"]), qid="1")], qs)
    assert s["hit@8"] == 1.0 and s["mrr"] == 1.0
    assert s["answer_rate"] is None and s["refusal_precision"] is None and s["unsupported_sentence_rate"] is None


def test_cost_nominal_vs_spent_and_generate_time():
    qs = [{"qid": "1", "answerable": True, "expected": []}, {"qid": "2", "answerable": True, "expected": []}]
    a = dict(rec("answered"), qid="1", input_tokens=1_000_000, output_tokens=100_000, cached=False, llm_called=True, timings_ms={"retrieve": 1, "generate": 400})
    b = dict(rec("answered"), qid="2", input_tokens=1_000_000, output_tokens=100_000, cached=True, llm_called=True, timings_ms={"retrieve": 1, "generate": 2})
    s = summarize([a, b], qs)
    assert s["cost_usd_nominal"] == 6.0 and s["cost_usd_spent"] == 3.0
    assert s["mean_generate_ms"] == 400   # cached replays are excluded


def test_summarize_by_tag():
    qs = [{"qid": "1", "answerable": True, "tag": "natural", "expected": [{"document": "a.md", "evidence": "alpha beta"}]},
          {"qid": "2", "answerable": True, "tag": "exact_term", "expected": [{"document": "a.md", "evidence": "alpha beta"}]}]
    rs = [dict(rec("retrieval_only", ["alpha beta"]), qid="1"), dict(rec("retrieval_only", ["zzz"]), qid="2")]
    by = summarize_by(rs, qs, key="tag")
    assert by["natural"]["hit@8"] == 1.0 and by["exact_term"]["hit@8"] == 0.0
