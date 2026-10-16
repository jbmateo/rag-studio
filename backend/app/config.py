from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class PipelineConfig:
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid"
    min_similarity: float = 0.35
    verify_citations: bool = True
    chunk_chars: int = 2000
    top_k: int = 8
    model: str = "claude-sonnet-5-5"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        case_sensitive=False,
        extra="ignore",
    )

    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-5-5"
    retrieval_mode: Literal["vector", "bm25", "hybrid"] = "hybrid"
    min_similarity: float = 0.35
    verify_citations: bool = True
    chunk_chars: int = 2000
    database_path: Path = Path("storage/app.db")
    storage_dir: Path = Path("storage")
    cookie_secure: bool = False
    embedder: Literal["fastembed", "hash"] = "fastembed"
    llm: Literal["claude", "fake"] = "claude"

    def pipeline(self) -> PipelineConfig:
        return PipelineConfig(
            retrieval_mode=self.retrieval_mode,
            min_similarity=self.min_similarity,
            verify_citations=self.verify_citations,
            chunk_chars=self.chunk_chars,
            model=self.claude_model,
        )
