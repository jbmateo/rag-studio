import pytest

import app.answer.llm as llm_mod
from app.answer.llm import ANSWER_SCHEMA, SYSTEM_PROMPT, CachedLLM, ClaudeLLM, LLMOutcome
from app.answer.prompts import PROMPTS
from app.answer.schema import AnswerDraft, DraftSentence, Passage
from app.answer.service import answer_question_detailed
from app.config import PipelineConfig
from app.embeddings import HashEmbedder
from tests.test_answer_service import VALID, FakeClient, _resp

P = [Passage(label="c1", document_name="a.md", location="p. 1", text="Hello.")]


def test_default_prompt_unchanged(seeded):
    conn, user = seeded
    assert PROMPTS["default"] == SYSTEM_PROMPT
    client = FakeClient(_resp(VALID, "end_turn"))
    answer_question_detailed(conn, HashEmbedder(), ClaudeLLM("k", client=client), PipelineConfig(), user, "refund days", None)
    kw = client.calls[0]
    assert kw["system"] == SYSTEM_PROMPT
    assert kw["output_config"] == {"effort": "medium", "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}}


def test_prompt_variant_is_sent(seeded):
    conn, user = seeded
    client = FakeClient(_resp(VALID, "end_turn"))
    cfg = PipelineConfig(prompt_variant="terse_cite_all")
    answer_question_detailed(conn, HashEmbedder(), ClaudeLLM("k", client=client), cfg, user, "refund days", None)
    assert client.calls[0]["system"] == PROMPTS["terse_cite_all"]
    assert PROMPTS["terse_cite_all"].startswith(SYSTEM_PROMPT)


def test_unknown_prompt_variant_raises(seeded):
    conn, user = seeded
    client = FakeClient(_resp(VALID, "end_turn"))
    with pytest.raises(ValueError, match="terse_cite_all"):
        answer_question_detailed(conn, HashEmbedder(), ClaudeLLM("k", client=client),
                                 PipelineConfig(prompt_variant="nope"), user, "refund days", None)


class Counting:
    def __init__(self):
        self.calls = 0

    def draft(self, question, passages, model, system=SYSTEM_PROMPT):
        self.calls += 1
        d = AnswerDraft(status="answered", sentences=[DraftSentence(text="A.", citations=["c1"])], missing="")
        return LLMOutcome(d, "end_turn", 1, 1)


def test_cache_key_separates_prompts(tmp_path):
    inner = Counting()
    cached = CachedLLM(inner, tmp_path)
    cached.draft("q", P, "m", system="one")
    cached.draft("q", P, "m", system="two")
    assert inner.calls == 2
    cached.draft("q", P, "m", system="one")
    assert inner.calls == 2


def test_cache_key_includes_effort_and_schema(tmp_path, monkeypatch):
    CachedLLM(Counting(), tmp_path / "a").draft("q", P, "m")
    monkeypatch.setattr(llm_mod, "ANSWER_EFFORT", "low")
    CachedLLM(Counting(), tmp_path / "b").draft("q", P, "m")
    names_a = {p.name for p in (tmp_path / "a").iterdir()}
    names_b = {p.name for p in (tmp_path / "b").iterdir()}
    assert names_a and names_b and names_a != names_b


def test_trace_records_stop_reasons(seeded):
    conn, user = seeded

    class NoneThenValid:
        def __init__(self):
            self.n = 0

        def draft(self, question, passages, model, system=SYSTEM_PROMPT):
            self.n += 1
            if self.n == 1:
                return LLMOutcome(None, "end_turn", 1, 1)
            d = AnswerDraft(status="answered", sentences=[DraftSentence(text="A.", citations=["c1"])], missing="")
            return LLMOutcome(d, "end_turn", 1, 1)

    _, trace = answer_question_detailed(conn, HashEmbedder(), NoneThenValid(), PipelineConfig(), user, "refund days", None)
    assert trace.stop_reasons == ["end_turn", "end_turn"]
