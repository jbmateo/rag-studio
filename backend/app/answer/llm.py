import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import anthropic
from anthropic import transform_schema
from pydantic import ValidationError

from app.answer.prompts import PROMPTS
from app.answer.schema import AnswerDraft, DraftSentence, Passage

SYSTEM_PROMPT = PROMPTS["default"]
ANSWER_EFFORT = "medium"
ANSWER_MAX_TOKENS = 4000


ANSWER_SCHEMA = transform_schema(AnswerDraft)


@dataclass
class LLMOutcome:
    draft: AnswerDraft | None
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cached: bool = False


class LLM(Protocol):
    def draft(self, question: str, passages: list[Passage], model: str, system: str = SYSTEM_PROMPT) -> LLMOutcome: ...


def build_user_message(question: str, passages: list[Passage]) -> str:
    blocks = [f"[{p.label}] ({p.document_name} — {p.location})\n{p.text}" for p in passages]
    return "\n\n".join(blocks) + f"\n\nQuestion: {question}"


class ClaudeLLM:
    def __init__(self, api_key: str, client=None):
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=30, max_retries=1)

    def draft(self, question: str, passages: list[Passage], model: str, system: str = SYSTEM_PROMPT) -> LLMOutcome:
        # anthropic.APIError (status, connection, timeout) propagates to the caller.
        resp = self.client.messages.create(
            model=model,
            max_tokens=ANSWER_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": build_user_message(question, passages)}],
            output_config={"effort": ANSWER_EFFORT, "format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
        )
        stop = resp.stop_reason or ""
        draft = None
        if stop not in ("refusal", "max_tokens"):
            text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
            try:
                draft = AnswerDraft.model_validate_json(text)
            except (ValidationError, ValueError):
                draft = None
        return LLMOutcome(draft, stop, resp.usage.input_tokens, resp.usage.output_tokens)


# Fingerprint of the user-message template when cache keys were introduced. Keys for that template
# stay as they were (existing caches remain valid); any other rendering or max_tokens gets its own key.
_LEGACY_TEMPLATE_FP = "a7a55061173317373b40023d3fb32deea0c2d8b232755cd1bccc38fffa01d287"
_LEGACY_MAX_TOKENS = 4000
_PROBE = [Passage(label="c1", document_name="d", location="l", text="t")]


def _request_shape() -> dict:
    extra = {}
    fp = hashlib.sha256(build_user_message("q", _PROBE).encode()).hexdigest()
    if fp != _LEGACY_TEMPLATE_FP:
        extra["user_template"] = fp
    if ANSWER_MAX_TOKENS != _LEGACY_MAX_TOKENS:
        extra["max_tokens"] = ANSWER_MAX_TOKENS
    return extra


class CachedLLM:
    def __init__(self, inner: LLM, cache_dir: Path):
        self.inner = inner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, question: str, passages: list[Passage], model: str, system: str) -> Path:
        key = hashlib.sha256(
            json.dumps(
                {"model": model, "system": system, "effort": ANSWER_EFFORT, "schema": ANSWER_SCHEMA,
                 "question": question, "passages": [p.model_dump() for p in passages], **_request_shape()},
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return self.cache_dir / f"{key}.json"

    def has(self, question: str, passages: list[Passage], model: str, system: str = SYSTEM_PROMPT) -> bool:
        """Whether a draft for exactly this request is cached (lets callers estimate cost before calling)."""
        try:
            d = json.loads(self._path(question, passages, model, system).read_text())
            AnswerDraft.model_validate(d["draft"])
            return True
        except (OSError, ValueError, KeyError, ValidationError):
            return False

    def draft(self, question: str, passages: list[Passage], model: str, system: str = SYSTEM_PROMPT) -> LLMOutcome:
        path = self._path(question, passages, model, system)
        if path.exists():
            try:
                d = json.loads(path.read_text())
                return LLMOutcome(
                    draft=AnswerDraft.model_validate(d["draft"]),
                    stop_reason=d["stop_reason"],
                    input_tokens=d["input_tokens"],
                    output_tokens=d["output_tokens"],
                    cached=True,
                )
            except (OSError, ValueError, KeyError, ValidationError):
                pass  # corrupt entry: fall through and regenerate
        out = self.inner.draft(question, passages, model, system=system)
        if out.draft is not None:
            payload = asdict(out)
            payload.pop("cached")
            payload["draft"] = out.draft.model_dump()
            path.write_text(json.dumps(payload))
        return out


class FakeLLM:
    def draft(self, question: str, passages: list[Passage], model: str, system: str = SYSTEM_PROMPT) -> LLMOutcome:
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
