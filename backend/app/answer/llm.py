import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import anthropic
from pydantic import ValidationError

from app.answer.schema import AnswerDraft, DraftSentence, Passage

SYSTEM_PROMPT = """You answer questions using only the numbered passages provided. Each passage is labelled like [c1].
- Every sentence you write must cite at least one passage label that directly supports it.
- Use only information stated in the passages. Do not use outside knowledge, and do not infer beyond what the passages say.
- If the passages fully answer the question, use status "answered".
- If they answer only part of it, answer that part, use status "partial", and describe what is missing in "missing".
- If they do not answer it, use status "insufficient_evidence", return no sentences, and describe what is missing in "missing"."""


@dataclass
class LLMOutcome:
    draft: AnswerDraft | None
    stop_reason: str
    input_tokens: int
    output_tokens: int


class LLM(Protocol):
    def draft(self, question: str, passages: list[Passage], model: str) -> LLMOutcome: ...


def build_user_message(question: str, passages: list[Passage]) -> str:
    blocks = [f"[{p.label}] ({p.document_name} — {p.location})\n{p.text}" for p in passages]
    return "\n\n".join(blocks) + f"\n\nQuestion: {question}"


class ClaudeLLM:
    def __init__(self, api_key: str, client=None):
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=30, max_retries=1)

    def draft(self, question: str, passages: list[Passage], model: str) -> LLMOutcome:
        # anthropic.APIError (status, connection, timeout) propagates to the caller.
        resp = self.client.messages.parse(
            model=model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_message(question, passages)}],
            output_config={"effort": "medium"},
            output_format=AnswerDraft,
        )
        stop = resp.stop_reason or ""
        draft = None
        if stop not in ("refusal", "max_tokens"):
            try:
                draft = resp.parsed_output
            except (ValidationError, ValueError):
                draft = None
        return LLMOutcome(draft, stop, resp.usage.input_tokens, resp.usage.output_tokens)


class CachedLLM:
    def __init__(self, inner: LLM, cache_dir: Path):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def draft(self, question: str, passages: list[Passage], model: str) -> LLMOutcome:
        key = hashlib.sha256(
            json.dumps(
                {"model": model, "system": SYSTEM_PROMPT, "question": question,
                 "passages": [p.model_dump() for p in passages]},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            try:
                d = json.loads(path.read_text())
                return LLMOutcome(
                    draft=AnswerDraft.model_validate(d["draft"]),
                    stop_reason=d["stop_reason"],
                    input_tokens=d["input_tokens"],
                    output_tokens=d["output_tokens"],
                )
            except (OSError, ValueError, KeyError, ValidationError):
                pass  # corrupt entry: fall through and regenerate
        out = self.inner.draft(question, passages, model)
        if out.draft is not None:
            payload = asdict(out)
            payload["draft"] = out.draft.model_dump()
            path.write_text(json.dumps(payload))
        return out


class FakeLLM:
    def draft(self, question: str, passages: list[Passage], model: str) -> LLMOutcome:
        if "unanswerable" in question.lower() or not passages:
            draft = AnswerDraft(
                status="insufficient_evidence", sentences=[],
                missing="The passages do not answer this question.",
            )
        else:
            first = passages[0].text.strip().split(". ")[0].strip()
            if not first.endswith("."):
                first += "."
            draft = AnswerDraft(
                status="answered",
                sentences=[
                    DraftSentence(text=first, citations=["c1"]),
                    DraftSentence(text="This claim cites a passage that does not exist.", citations=["c99"]),
                ],
                missing="",
            )
        return LLMOutcome(draft, "end_turn", 0, 0)


def make_llm(settings) -> LLM:
    if settings.llm == "fake":
        return FakeLLM()
    return CachedLLM(ClaudeLLM(settings.anthropic_api_key), settings.storage_dir / "llm_cache")
