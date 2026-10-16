from typing import Literal

from pydantic import BaseModel


class DraftSentence(BaseModel):
    text: str
    citations: list[str]


class AnswerDraft(BaseModel):
    status: Literal["answered", "partial", "insufficient_evidence"]
    sentences: list[DraftSentence]
    missing: str


class Passage(BaseModel):
    label: str
    document_name: str
    location: str
    text: str


class AskSentence(BaseModel):
    text: str
    citations: list[int]


class AskCitation(BaseModel):
    n: int
    chunk_id: str | None
    document_id: str | None
    document_name: str
    location: str
    page: int | None


class AskChunk(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    location: str
    text: str
    score: float
    vector_rank: int | None
    bm25_rank: int | None


class Timings(BaseModel):
    retrieve: int
    generate: int


class AskResponse(BaseModel):
    status: Literal["answered", "partial", "insufficient_evidence", "not_found"]
    sentences: list[AskSentence]
    missing: str
    citations: list[AskCitation]
    chunks: list[AskChunk]
    dropped_citations: int
    timings_ms: Timings
