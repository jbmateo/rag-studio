"""Retrieval and answer metrics over per-question experiment records."""
from collections import defaultdict

# Sonnet 5.5 list price, USD per token.
PRICE_IN = 2.0 / 1_000_000
PRICE_OUT = 10.0 / 1_000_000
REFUSALS = ("not_found", "insufficient_evidence")
ANSWERED = ("answered", "partial")


def norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def qid(item: dict) -> str:
    return item["qid"] if "qid" in item else item["id"]


def _matches(chunk_text: str, evidence: str) -> bool:
    text, ev = norm(chunk_text), norm(evidence)
    return ev in text or " ".join(ev.split()[:8]) in text  # head match: evidence may span chunks


def _first_rank(record: dict, q: dict, k: int) -> int | None:
    for rank, chunk in enumerate(record["retrieved"][:k], start=1):
        for e in q["expected"]:
            if chunk["document_name"] == e["document"] and _matches(chunk["text"], e["evidence"]):
                return rank
    return None


def hit_at_k(record: dict, q: dict, k: int = 8) -> bool:
    return _first_rank(record, q, k) is not None


def mrr(record: dict, q: dict) -> float:
    rank = _first_rank(record, q, len(record["retrieved"]))
    return 1.0 / rank if rank else 0.0


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ratio(num: int, den: int) -> float | None:
    return num / den if den else None


def summarize(records: list[dict], questions: list[dict]) -> dict:
    by_id = {qid(q): q for q in questions}
    pairs = [(r, by_id[r["qid"]]) for r in records]
    answerable = [(r, q) for r, q in pairs if q["answerable"]]
    llm_pairs = [(r, q) for r, q in pairs if r["status"] not in ("retrieval_only", "error")]

    refused = [(r, q) for r, q in llm_pairs if r["status"] in REFUSALS]
    unanswerable = [(r, q) for r, q in llm_pairs if not q["answerable"]]
    correct_refusals = sum(1 for _, q in refused if not q["answerable"])

    raw_total = valid = 0
    for r, _ in llm_pairs:
        labels = set(r.get("valid_labels", []))
        for s in r.get("raw_sentences", []):
            raw_total += len(s["citations"])
            valid += sum(1 for c in s["citations"] if c in labels)

    # Post-verification validity: citation numbers in the shown sentences that resolve to a retrieved chunk.
    # 1.0 by construction when verification is on; below 1.0 only when it is off.
    post_total = post_valid = 0
    for r, _ in llm_pairs:
        retrieved_ids = {c["chunk_id"] for c in r["retrieved"]}
        chunk_by_n = {c["n"]: c.get("chunk_id") for c in r.get("citations", [])}
        for sent in r.get("sentences", []):
            post_total += len(sent["citations"])
            post_valid += sum(1 for n in sent["citations"] if chunk_by_n.get(n) in retrieved_ids)

    judgments = [j["supported"] for r, _ in pairs for j in r.get("judgments", [])]
    judged = [j for j in judgments if j is not None]

    called = [r for r, _ in pairs if r.get("llm_called")]
    fresh = [r for r in called if not r.get("cached") and r.get("timings_ms")]
    cost = lambda rs: sum(r["input_tokens"] * PRICE_IN + r["output_tokens"] * PRICE_OUT for r in rs)

    return {
        "n": len(records),
        "n_answerable": len(answerable),
        "hit@8": _mean([float(hit_at_k(r, q)) for r, q in answerable]),
        "mrr": _mean([mrr(r, q) for r, q in answerable]),
        "answer_rate": _ratio(sum(1 for r, q in llm_pairs if q["answerable"] and r["status"] in ANSWERED),
                              sum(1 for _, q in llm_pairs if q["answerable"])),
        "refusal_precision": _ratio(correct_refusals, len(refused)),
        "refusal_recall": _ratio(correct_refusals, len(unanswerable)),
        "citation_validity": _ratio(valid, raw_total),
        "citation_validity_post": _ratio(post_valid, post_total),
        "unsupported_sentence_rate": _ratio(sum(1 for j in judged if not j), len(judged)),
        "judged_sentences": len(judged),
        "judge_unparsed": len(judgments) - len(judged),
        "mean_generate_ms": _mean([r["timings_ms"]["generate"] for r in fresh]),
        "llm_errors": sum(1 for r in records if r["status"] == "error"),
        "cost_usd_nominal": cost(called),
        "cost_usd_spent": cost([r for r in called if not r.get("cached")]),
    }


def summarize_by(records: list[dict], questions: list[dict], key: str = "tag") -> dict[str, dict]:
    by_id = {qid(q): q for q in questions}
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[str(by_id[r["qid"]][key])].append(r)
    return {k: summarize(rs, questions) for k, rs in groups.items()}
