from fastapi import FastAPI

from app.auth.routes import router as auth_router
from app.config import Settings
from app.db import connect, init_db
from app.embeddings import make_embedder


def create_app(settings: Settings, embedder=None, llm=None) -> FastAPI:
    app = FastAPI(title="RAG Studio")
    app.state.settings = settings
    app.state.embedder = embedder if embedder is not None else make_embedder(settings.embedder)
    app.state.llm = llm
    app.state.login_attempts = {}

    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.database_path)
    try:
        init_db(conn)
    finally:
        conn.close()

    app.include_router(auth_router)

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
