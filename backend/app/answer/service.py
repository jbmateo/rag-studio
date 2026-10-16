import time
from dataclasses import dataclass

import anthropic

from app.answer.llm import LLM
from app.answer.schema import (
    AnswerDraft, AskChunk, AskCitation, AskResponse, AskSentence, DraftSentence, Passage, Timings,
)
from app.answer.verify import verify_draft
from app.config import PipelineConfig
from app.retrieval import RetrievalResult, retrieve
from app.store import ready_doc_ids

REFUSAL_MISSING = "The model declined to answer this question."
NO_ANSWER_MISSING = "The model did not return a usable answer."


class NoDocumentsError(Exception):
    pass


class LLMUnavailableError(Exception):
    pass


@dataclass
class AnswerTrace:
    raw_sentences: list[DraftSentence]
    valid_labels: list[str]
    input_tokens: int
    output_tokens: int
    retrieval: RetrievalResult


def _ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def answer_question_detailed(
    conn, embedder, llm: LLM, cfg: PipelineConfig, user_id: str, question: str,
    doc_ids: list[str] | None,
) -> tuple[AskResponse, AnswerTrace]:
    if not ready_doc_ids(conn, user_id, doc_ids):
        raise NoDocumentsError("Upload a document first")

    t0 = time.perf_counter()
    result = retrieve(conn, embedder, cfg, user_id, question, doc_ids)
    retrieve_ms = _ms(t0)

    labels = [f"c{i}" for i in range(1, len(result.chunks) + 1)]
    chunks = [
        AskChunk(
            chunk_id=rc.chunk.id, document_id=rc.chunk.document_id,
            document_name=rc.chunk.document_name, location=rc.chunk.location,
            text=rc.chunk.text, score=rc.score, vector_rank=rc.vector_rank, bm25_rank=rc.bm25_rank,
        )
        for rc in result.chunks
    ]
    trace = AnswerTrace([], labels, 0, 0, result)

    if not result.gate_passed:
        resp = AskResponse(
            status="not_found", sentences=[], missing="", citations=[], chunks=chunks,
            dropped_citations=0, timings_ms=Timings(retrieve=retrieve_ms, generate=0),
        )
        return resp, trace

    passages = [
        Passage(label=lb, document_name=rc.chunk.document_name, location=rc.chunk.location, text=rc.chunk.text)
        for lb, rc in zip(labels, result.chunks)
    ]
    t1 = time.perf_counter()
    outcome = None
    try:
        for _ in range(2):
            outcome = llm.draft(question, passages, cfg.model)
            trace.input_tokens += outcome.input_tokens
            trace.output_tokens += outcome.output_tokens
            if outcome.draft is not None or outcome.stop_reason == "refusal":
                break
    except anthropic.APIError as e:
        raise LLMUnavailableError(str(e)) from e
    generate_ms = _ms(t1)

    draft = outcome.draft
    dropped = 0
    if draft is None:
        missing = REFUSAL_MISSING if outcome.stop_reason == "refusal" else NO_ANSWER_MISSING
        final = AnswerDraft(status="insufficient_evidence", sentences=[], missing=missing)
    else:
        trace.raw_sentences = [s.model_copy(deep=True) for s in draft.sentences]
        if cfg.verify_citations:
            final, dropped = verify_draft(draft, set(labels))
        else:
            final = draft

    by_label = {lb: rc.chunk for lb, rc in zip(labels, result.chunks)}
    numbers: dict[str, int] = {}
    citations: list[AskCitation] = []
    sentences: list[AskSentence] = []
    for s in final.sentences:
        ns = []
        for lb in s.citations:
            if lb not in numbers:
                numbers[lb] = len(numbers) + 1
                c = by_label.get(lb)
                citations.append(
                    AskCitation(
                        n=numbers[lb], chunk_id=c.id, document_id=c.document_id,
                        document_name=c.document_name, location=c.location, page=c.page,
                    ) if c else AskCitation(
                        n=numbers[lb], chunk_id=None, document_id=None,
                        document_name="(unknown)", location="", page=None,
                    )
                )
            ns.append(numbers[lb])
        sentences.append(AskSentence(text=s.text, citations=ns))

    resp = AskResponse(
        status=final.status, sentences=sentences, missing=final.missing, citations=citations,
        chunks=chunks, dropped_citations=dropped,
        timings_ms=Timings(retrieve=retrieve_ms, generate=generate_ms),
    )
    return resp, trace


def answer_question(conn, embedder, llm, cfg, user_id, question, doc_ids) -> AskResponse:
    return answer_question_detailed(conn, embedder, llm, cfg, user_id, question, doc_ids)[0]
