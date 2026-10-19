import json
import sys
from types import SimpleNamespace

import pytest
import yaml

from app.answer.llm import FakeLLM
from app.config import PipelineConfig, Settings
from app.embeddings import HashEmbedder
from research import run_experiment
from research.harness import Corpus, load_experiment, load_questions, run_question
from research.judge import JUDGE_SCHEMA, Judge, JudgeVerdict, judge_sentence
from research.run_experiment import main as run


@pytest.fixture(scope="module")
def corpus():
    emb = HashEmbedder()
    conn, user = Corpus.load(2000, emb)
    return conn, user, emb


def test_corpus_is_cached_per_chunk_size(corpus):
    conn, user, emb = corpus
    assert Corpus.load(2000, emb)[0] is conn
    assert Corpus.load(1000, emb)[0] is not conn
    n = conn.execute("select count(*) from documents where status='ready'").fetchone()[0]
    assert n == 6


def test_run_question_retrieval_only(corpus):
    conn, user, emb = corpus
    q = next(x for x in load_questions() if x["id"] == "q012")
    r = run_question(conn, user, emb, None, PipelineConfig(), q, use_llm=False)
    assert r["status"] == "retrieval_only" and r["qid"] == "q012" and r["tag"] == "exact_term" and r["answerable"] is True
    assert r["llm_called"] is False and r["input_tokens"] == 0 and r["sentences"] == [] and r["raw_sentences"] == []
    assert r["retrieved"] and {"chunk_id", "document_name", "text", "vector_rank", "bm25_rank", "similarity"} <= r["retrieved"][0].keys()
    assert r["valid_labels"] == [f"c{i}" for i in range(1, len(r["retrieved"]) + 1)]
    json.dumps(r)


def test_run_question_with_llm_records_raw_and_verified(corpus):
    conn, user, emb = corpus
    q = next(x for x in load_questions() if x["id"] == "q012")
    cfg = PipelineConfig(min_similarity=-1.0)
    on = run_question(conn, user, emb, FakeLLM(), cfg, q, use_llm=True)
    off = run_question(conn, user, emb, FakeLLM(), PipelineConfig(min_similarity=-1.0, verify_citations=False), q, use_llm=True)
    assert on["llm_called"] and on["raw_citation_count"] == 2 and on["dropped_citations"] == 1
    assert [s["citations"] for s in on["raw_sentences"]] == [["c1"], ["c99"]] and len(on["sentences"]) == 1
    assert len(off["sentences"]) == 2 and off["dropped_citations"] == 0
    assert on["cached"] is False and on["timings_ms"].keys() == {"retrieve", "generate"}


def test_run_question_judges_shown_sentences(corpus):
    conn, user, emb = corpus
    q = next(x for x in load_questions() if x["id"] == "q012")
    seen = []

    class J:
        def judge_sentence(self, sentence, chunk_texts):
            seen.append((sentence, chunk_texts))
            return True

    off = run_question(conn, user, emb, FakeLLM(), PipelineConfig(min_similarity=-1.0, verify_citations=False), q, use_llm=True, judge=J())
    # second sentence cites an unknown label: no text, so unsupported without asking the judge
    assert [j["supported"] for j in off["judgments"]] == [True, False]
    assert [j["judge_called"] for j in off["judgments"]] == [True, False]
    assert len(seen) == 1 and len(seen[0][1]) == 1
    on = run_question(conn, user, emb, FakeLLM(), PipelineConfig(min_similarity=-1.0), q, use_llm=True, judge=J())
    assert [j["supported"] for j in on["judgments"]] == [True]


def test_cached_flag_from_llm_outcome(corpus):
    conn, user, emb = corpus
    q = next(x for x in load_questions() if x["id"] == "q012")

    class Cached(FakeLLM):
        def draft(self, *a, **kw):
            out = super().draft(*a)
            out.cached = True
            return out

    r = run_question(conn, user, emb, Cached(), PipelineConfig(min_similarity=-1.0), q, use_llm=True)
    assert r["cached"] is True


def test_experiment_yamls_match_spec():
    base = "research/experiments/"
    rq1, rq2, rq3, rq4 = (load_experiment(base + f"rq{i}.yaml") for i in range(1, 5))
    assert (rq1["llm"], [v["retrieval_mode"] for v in rq1["variants"]]) == (False, ["vector", "bm25", "hybrid"])
    assert rq2["llm"] and [round(v["min_similarity"], 2) for v in rq2["variants"]] == [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    assert rq3["llm"] and rq3["judge"] and [v["verify_citations"] for v in rq3["variants"]] == [True, False]
    assert rq4["llm"] and [v["chunk_chars"] for v in rq4["variants"]] == [1000, 2000, 4000]
    assert all("label" in v for e in (rq1, rq2, rq3, rq4) for v in e["variants"])


def test_harness_dry_run(tmp_path):
    out = run(["research/experiments/rq3.yaml", "--fake-llm", "--hash-embedder", "--limit", "3", "--results-dir", str(tmp_path)])
    assert out == 0
    lines = (next(tmp_path.rglob("*.jsonl"))).read_text().splitlines()
    assert len(lines) == 1 + 3 * 2
    header = json.loads(lines[0])
    assert header["type"] == "header" and [v["label"] for v in header["variants"]] == ["verify_on", "verify_off"]
    assert {"config", "git_commit", "started_at"} <= header.keys()
    recs = [json.loads(x) for x in lines[1:]]
    assert all(r["type"] == "record" for r in recs) and {r["variant"] for r in recs} == {"verify_on", "verify_off"}
    summary = json.loads((tmp_path / "rq3" / "summary.json").read_text())
    assert set(summary["variants"]) == {"verify_on", "verify_off"}


def test_missing_api_key_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(run_experiment, "load_settings", lambda: Settings(_env_file=None, anthropic_api_key=""))
    assert run(["research/experiments/rq3.yaml", "--hash-embedder", "--results-dir", str(tmp_path)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not list(tmp_path.rglob("*.jsonl"))


# ---- judge ----

def _resp(text, stop="end_turn"):
    blocks = [SimpleNamespace(type="text", text=text)] if text is not None else []
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=SimpleNamespace(input_tokens=5, output_tokens=2))


class Client:
    def __init__(self, *resps):
        self.resps, self.calls = list(resps), []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        return self.resps.pop(0)


def test_judge_request_shape_and_cache(tmp_path):
    c = Client(_resp(JudgeVerdict(supported=True, reason="stated").model_dump_json()))
    j = Judge(client=c, cache_dir=tmp_path)
    assert j.judge_sentence("Refunds take 14 days.", ["Refunds take 14 days."]) is True
    kw = c.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["output_config"]["effort"] == "low"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": JUDGE_SCHEMA}
    assert not {"temperature", "tool_choice", "thinking"} & kw.keys()
    assert "every factual claim" in kw["system"]
    assert j.judge_sentence("Refunds take 14 days.", ["Refunds take 14 days."]) is True
    assert len(c.calls) == 1   # second answer came from the disk cache


def test_judge_unsupported_and_unparseable_and_refusal(tmp_path):
    c = Client(_resp('{"supported": false, "reason": "no"}'), _resp("not json"), _resp(None, "refusal"), _resp('{"supported": true', "max_tokens"), _resp('{"supported": true, "reason": "r"}'))
    j = Judge(client=c, cache_dir=tmp_path)
    assert j.judge_sentence("a", ["x"]) is False
    assert j.judge_sentence("b", ["x"]) is None
    assert j.judge_sentence("c", ["x"]) is None
    assert j.judge_sentence("d", ["x"]) is None
    assert j.judge_sentence("b", ["x"]) is True   # failures are not cached: it asks again
    assert len(c.calls) == 5


def test_judge_without_passages_is_unsupported_without_a_call(tmp_path):
    c = Client()
    assert Judge(client=c, cache_dir=tmp_path).judge_sentence("anything", []) is False
    assert c.calls == []


def test_module_level_judge_sentence(tmp_path):
    c = Client(_resp('{"supported": true, "reason": "ok"}'))
    assert judge_sentence("s", ["t"], judge=Judge(client=c, cache_dir=tmp_path)) is True
