import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator

from app.answer.schema import AskResponse
from app.answer.service import LLMUnavailableError, NoDocumentsError, answer_question
from app.auth.deps import User, current_user, get_conn

router = APIRouter(prefix="/api")

LLM_UNAVAILABLE = "The answer service is unavailable. Please try again."


class AskRequest(BaseModel):
    question: str
    doc_ids: list[str] | None = None

    @field_validator("question")
    @classmethod
    def _question_len(cls, v: str) -> str:
        v = v.strip()
        if not 1 <= len(v) <= 1000:
            raise ValueError("question must be 1 to 1000 characters")
        return v


@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    request: Request,
    user: User = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> AskResponse:
    state = request.app.state
    try:
        return answer_question(
            conn, state.embedder, state.llm, state.settings.pipeline(),
            user.id, body.question, body.doc_ids,
        )
    except NoDocumentsError:
        raise HTTPException(status_code=400, detail="Upload a document first")
    except LLMUnavailableError:
        raise HTTPException(status_code=502, detail=LLM_UNAVAILABLE)
