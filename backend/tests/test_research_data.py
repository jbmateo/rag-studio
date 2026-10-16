"""Validity checks for the research dataset (corpus + labelled questions). No network, no models."""
import json
from collections import Counter
from pathlib import Path

from app.ingest.parsers import parse_file

RESEARCH = Path(__file__).resolve().parent.parent / "research"
CORPUS = RESEARCH / "corpus"
QUESTIONS = RESEARCH / "questions.jsonl"


def load_questions():
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


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
            assert 5 <= len(e["evidence"].split()) <= 20, (q["id"], e)


def test_corpus_covers_all_formats():
    assert {p.suffix for p in CORPUS.iterdir()} == {".pdf", ".md", ".docx", ".txt", ".html"}
