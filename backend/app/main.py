from fastapi import FastAPI

from app.config import Settings


def create_app(settings: Settings, embedder=None, llm=None) -> FastAPI:
    app = FastAPI(title="RAG Studio")
    app.state.settings = settings
    app.state.embedder = embedder
    app.state.llm = llm

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True}

    return app
