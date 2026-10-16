"""LLM judge for RQ3: is a generated sentence supported by the passages it cites?

Follows the ClaudeLLM pattern: messages.create with a json_schema output_config, then we check
stop_reason and validate the text ourselves. A refused, truncated or unparseable reply is None
(excluded from the rate and counted), never a guess.
"""
import hashlib
import json
from pathlib import Path

import anthropic
from anthropic import transform_schema
from pydantic import BaseModel, ValidationError

MODEL = "claude-sonnet-5-5"
DEFAULT_CACHE_DIR = Path(__file__).resolve().parent / "cache" / "judge"

RUBRIC = (
    "You check whether a sentence is supported by the passages it cites. "
    "Supported only if every factual claim in the sentence is stated in, or directly entailed by, "
    "the cited passages. Ignore style. A claim that adds details the passages do not state is not supported."
)


class JudgeVerdict(BaseModel):
    supported: bool
    reason: str


JUDGE_SCHEMA = transform_schema(JudgeVerdict)


def build_message(sentence: str, chunk_texts: list[str]) -> str:
    passages = "\n\n".join(f"[P{i}]\n{t}" for i, t in enumerate(chunk_texts, 1))
    return f"Cited passages:\n\n{passages}\n\nSentence: {sentence}"


class Judge:
    def __init__(self, api_key: str = "", client=None, cache_dir: Path | None = DEFAULT_CACHE_DIR, model: str = MODEL):
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=30, max_retries=1)
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, sentence: str, chunk_texts: list[str]) -> Path | None:
        if not self.cache_dir:
            return None
        key = hashlib.sha256(json.dumps(
            {"model": self.model, "rubric": RUBRIC, "sentence": sentence, "passages": chunk_texts}, sort_keys=True,
        ).encode()).hexdigest()
        return self.cache_dir / f"{key}.json"

    def judge_sentence(self, sentence: str, chunk_texts: list[str]) -> bool | None:
        """True/False if supported/unsupported; None if the judge gave no usable verdict."""
        if not chunk_texts:
            return False  # nothing was cited (or the label was unknown): cannot be supported
        path = self._path(sentence, chunk_texts)
        if path is not None and path.exists():
            try:
                return JudgeVerdict.model_validate_json(path.read_text()).supported
            except (OSError, ValidationError, ValueError):
                pass  # corrupt entry: ask again
        resp = self.client.messages.create(  # anthropic.APIError propagates
            model=self.model,
            max_tokens=1000,
            system=RUBRIC,
            messages=[{"role": "user", "content": build_message(sentence, chunk_texts)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        )
        if (resp.stop_reason or "") in ("refusal", "max_tokens"):
            return None
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
        try:
            verdict = JudgeVerdict.model_validate_json(text)
        except (ValidationError, ValueError):
            return None
        if path is not None:
            path.write_text(verdict.model_dump_json())
        return verdict.supported


class FakeJudge:
    """Offline stand-in for dry runs: supported iff most of the sentence's words occur in the passages."""

    def judge_sentence(self, sentence: str, chunk_texts: list[str]) -> bool | None:
        if not chunk_texts:
            return False
        words = {w for w in sentence.lower().split() if len(w) > 3}
        haystack = " ".join(chunk_texts).lower()
        return not words or sum(w in haystack for w in words) / len(words) >= 0.5


def judge_sentence(sentence: str, chunk_texts: list[str], judge=None) -> bool | None:
    """Module-level convenience; builds a Judge from backend/.env when none is given."""
    if judge is None:
        from app.config import Settings

        judge = Judge(Settings().anthropic_api_key)
    return judge.judge_sentence(sentence, chunk_texts)
