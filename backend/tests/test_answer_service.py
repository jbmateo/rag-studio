from types import SimpleNamespace

import anthropic
import httpx
import pytest

from app.answer.llm import ANSWER_SCHEMA, CachedLLM, ClaudeLLM, FakeLLM, make_llm
from app.answer.schema import AnswerDraft, DraftSentence, Passage
from app.answer.service import (
    LLMUnavailableError, NoDocumentsError, answer_question, answer_question_detailed,
)
from app.config import PipelineConfig
from app.embeddings import HashEmbedder
from tests.conftest import ScriptedLLM, SpyLLM


def d(*sents, status="answered"):
    return AnswerDraft(status=status, sentences=[DraftSentence(text=t, citations=c) for t, c in sents], missing="")


def test_gate_fail_returns_not_found_without_llm(seeded):
    conn, user = seeded; llm = SpyLLM()
    r = answer_question(conn, HashEmbedder(), llm, PipelineConfig(), user, "Who won the 1998 world cup?", None)
    assert r.status == "not_found" and llm.calls == 0 and r.chunks
    assert r.timings_ms.generate == 0 and r.sentences == [] and r.citations == []


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
    assert off.dropped_citations == 0 and len(off.sentences) == 2
    unk = off.citations[1]
    assert (unk.chunk_id, unk.document_id, unk.document_name, unk.location, unk.page) == (None, None, "(unknown)", "", None)


def test_llm_refusal_or_unparseable_becomes_insufficient(seeded):
    conn, user = seeded; llm = ScriptedLLM(None, stop_reason="refusal")
    r = answer_question(conn, HashEmbedder(), llm, PipelineConfig(), user, "refund days", None)
    assert r.status == "insufficient_evidence" and r.missing == "The model declined to answer this question."
    assert llm.calls == 1   # refusals are not retried


def test_unparseable_retries_once(seeded):
    conn, user = seeded; llm = ScriptedLLM(None, stop_reason="max_tokens")
    r = answer_question(conn, HashEmbedder(), llm, PipelineConfig(), user, "refund days", None)
    assert llm.calls == 2 and r.status == "insufficient_evidence"


def test_no_ready_documents(conn, user):
    with pytest.raises(NoDocumentsError):
        answer_question(conn, HashEmbedder(), FakeLLM(), PipelineConfig(), user, "anything", None)


def test_api_error_becomes_llm_unavailable(seeded):
    conn, user = seeded

    class Boom:
        def draft(self, *a):
            raise anthropic.APIConnectionError(request=httpx.Request("POST", "http://x"))

    with pytest.raises(LLMUnavailableError):
        answer_question(conn, HashEmbedder(), Boom(), PipelineConfig(), user, "refund days", None)


def test_detailed_trace(seeded):
    conn, user = seeded
    r, t = answer_question_detailed(conn, HashEmbedder(), FakeLLM(), PipelineConfig(), user, "refund days", None)
    assert [s.citations for s in t.raw_sentences] == [["c1"], ["c99"]]   # draft before verification
    assert t.valid_labels == [f"c{i}" for i in range(1, len(r.chunks) + 1)]
    assert t.retrieval.gate_passed
    _, t2 = answer_question_detailed(conn, HashEmbedder(), SpyLLM(), PipelineConfig(), user, "Who won the 1998 world cup?", None)
    assert t2.raw_sentences == []


def test_cached_llm_hits_disk_once(tmp_path):
    spy = SpyLLM(); c = CachedLLM(spy, tmp_path / "cache")
    p = [Passage(label="c1", document_name="a", location="p. 1", text="t")]
    first = c.draft("q", p, "m"); second = c.draft("q", p, "m")
    assert spy.calls == 1 and second.draft == first.draft
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_cached_llm_does_not_cache_failures(tmp_path):
    inner = ScriptedLLM(None, stop_reason="max_tokens"); c = CachedLLM(inner, tmp_path)
    c.draft("q", [], "m"); c.draft("q", [], "m")
    assert inner.calls == 2 and not list(tmp_path.glob("*.json"))


def test_fake_llm_unanswerable():
    out = FakeLLM().draft("this is unanswerable", [], "m")
    assert out.draft.status == "insufficient_evidence" and out.draft.sentences == []


def test_make_llm(settings):
    assert isinstance(make_llm(settings), FakeLLM)


class FakeClient:
    def __init__(self, resp):
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)
        self._resp = resp

    def _create(self, **kw):
        self.calls.append(kw)
        return self._resp


def _resp(text, stop):
    blocks = [SimpleNamespace(type="text", text=text)] if text is not None else []
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=SimpleNamespace(input_tokens=7, output_tokens=3))


P = [Passage(label="c1", document_name="a.md", location="p. 1", text="Hello.")]
VALID = d(("A.", ["c1"])).model_dump_json()


def test_claude_llm_success():
    client = FakeClient(_resp(VALID, "end_turn"))
    out = ClaudeLLM("k", client=client).draft("q?", P, "claude-sonnet-5-5")
    assert out.draft.sentences[0].text == "A." and (out.input_tokens, out.output_tokens) == (7, 3)
    kw = client.calls[0]
    assert kw["model"] == "claude-sonnet-5-5" and kw["max_tokens"] == 4000
    assert kw["output_config"]["effort"] == "medium"
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": ANSWER_SCHEMA}
    assert not {"temperature", "tool_choice", "thinking"} & kw.keys()
    assert kw["messages"][0]["content"] == "[c1] (a.md — p. 1)\nHello.\n\nQuestion: q?"


def test_answer_schema_is_strict_and_matches_model():
    assert ANSWER_SCHEMA["additionalProperties"] is False
    assert set(ANSWER_SCHEMA["required"]) == set(AnswerDraft.model_fields)
    sent = ANSWER_SCHEMA["$defs"]["DraftSentence"]
    assert sent["additionalProperties"] is False and set(sent["required"]) == {"text", "citations"}


def test_claude_llm_truncated_json_max_tokens():
    out = ClaudeLLM("k", client=FakeClient(_resp(VALID[:20], "max_tokens"))).draft("q", P, "m")
    assert out.draft is None and out.stop_reason == "max_tokens"


def test_claude_llm_refusal_empty_text():
    out = ClaudeLLM("k", client=FakeClient(_resp(None, "refusal"))).draft("q", P, "m")
    assert out.draft is None and out.stop_reason == "refusal"


def test_claude_llm_schema_invalid_json_gives_none():
    out = ClaudeLLM("k", client=FakeClient(_resp('{"status": "nope"}', "end_turn"))).draft("q", P, "m")
    assert out.draft is None and out.stop_reason == "end_turn"
    out = ClaudeLLM("k", client=FakeClient(_resp("not json", "end_turn"))).draft("q", P, "m")
    assert out.draft is None


def test_retry_that_succeeds(seeded):
    conn, user = seeded

    class Flaky:
        calls = 0

        def draft(self, q, passages, model):
            from app.answer.llm import LLMOutcome
            self.calls += 1
            if self.calls == 1:
                return LLMOutcome(None, "max_tokens", 5, 5)
            return LLMOutcome(d(("A.", ["c1"])), "end_turn", 5, 5)

    llm = Flaky()
    r, t = answer_question_detailed(conn, HashEmbedder(), llm, PipelineConfig(), user, "refund days", None)
    assert llm.calls == 2 and r.status == "answered" and t.input_tokens == 10


def test_duplicate_labels_deduped(seeded):
    conn, user = seeded
    for verify in (True, False):
        r = answer_question(conn, HashEmbedder(), ScriptedLLM(d(("A.", ["c1", "c1"]))),
                            PipelineConfig(verify_citations=verify), user, "refund days", None)
        assert r.sentences[0].citations == [1] and r.dropped_citations == 0


def test_cached_flag(tmp_path):
    c = CachedLLM(SpyLLM(), tmp_path)
    p = [Passage(label="c1", document_name="a", location="p. 1", text="t")]
    a = c.draft("q", p, "m"); b = c.draft("q", p, "m")
    assert a.cached is False and b.cached is True and b.input_tokens == a.input_tokens
