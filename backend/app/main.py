from fastapi import FastAPI

from app.ask.routes import router as ask_router
from app.auth.routes import router as auth_router
from app.documents.routes import router as documents_router
from app.answer.llm import make_llm
from app.config import Settings
from app.db import connect, init_db
from app.embeddings import make_embedder


def create_app(settings: Settings, embedder=None, llm=None) -> FastAPI:
    app = FastAPI(title="RAG Studio")
    app.state.settings = settings
    app.state.embedder = embedder if embedder is not None else make_embedder(settings.embedder)
    app.state.llm = llm if llm is not None else make_llm(settings)
    app.state.login_attempts = {}

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.database_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    app.include_router(auth_router)
    app.include_router(documents_router)
    app.include_router(ask_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app


def get_app() -> FastAPI:
    """Factory for uvicorn (`--factory`). Not a module-level `app`: importing this module
    must not read .env or create storage/app.db."""
    return create_app(Settings())
