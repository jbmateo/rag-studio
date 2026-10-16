import uuid
from pathlib import Path

import pytest

from app.config import Settings
from app.db import connect, init_db


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        embedder="hash",
        llm="fake",
        database_path=tmp_path / "app.db",
        storage_dir=tmp_path / "storage",
    )


@pytest.fixture
def conn(settings):
    c = connect(settings.database_path)
    init_db(c)
    yield c
    c.close()


@pytest.fixture
def make_user_doc(conn):
    def _make(email="a@example.com"):
        user_id, doc_id = uuid.uuid4().hex, uuid.uuid4().hex
        conn.execute(
            "insert into users(id,email,password_hash) values(?,?,?)",
            (user_id, email, "x"),
        )
        conn.execute(
            "insert into documents(id,user_id,name,source_type,file_path) values(?,?,?,?,?)",
            (doc_id, user_id, "doc.txt", "txt", "doc.txt"),
        )
        conn.commit()
        return user_id, doc_id

    return _make


@pytest.fixture
def client(settings):
    from fastapi.testclient import TestClient

    from app.main import create_app

    from app.embeddings import HashEmbedder

    from app.answer.llm import FakeLLM

    with TestClient(create_app(settings, HashEmbedder(), FakeLLM())) as c:
        yield c


@pytest.fixture
def signup(client):
    def _signup(email, password="password1"):
        r = client.post("/api/auth/signup", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        return r

    return _signup


def _insert_user(conn, email):
    user_id = uuid.uuid4().hex
    conn.execute(
        "insert into users(id,email,password_hash) values(?,?,?)", (user_id, email, "x")
    )
    conn.commit()
    return user_id


@pytest.fixture
def two_users(conn):
    return _insert_user(conn, "a@example.com"), _insert_user(conn, "b@example.com")


@pytest.fixture
def user(conn):
    return _insert_user(conn, "u@example.com")


@pytest.fixture
def storage(tmp_path):
    path = tmp_path / "files"
    path.mkdir()
    return path


@pytest.fixture
def add_file_doc():
    """Write `content` to storage/{user}/{uuid}.{ext} and register it as a document."""
    from app.store import create_document

    def _add(conn, user_id, storage, name, content):
        ext = name.rsplit(".", 1)[-1]
        path = Path(storage) / user_id / f"{uuid.uuid4().hex}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content if isinstance(content, bytes) else content.encode()
        path.write_bytes(data)
        return create_document(
            conn, user_id, name=name, source_type=ext, source_url=None,
            file_path=str(path), size_bytes=len(data),
        )

    return _add


@pytest.fixture
def as_user(client):
    """Sign up (or log in if the user exists) as `email`, replacing the client's cookie."""

    def _as(email, password="password1"):
        client.cookies.clear()
        r = client.post("/api/auth/signup", json={"email": email, "password": password})
        if r.status_code != 201:
            r = client.post("/api/auth/login", json={"email": email, "password": password})
            assert r.status_code == 200, r.text
        return r

    return _as


@pytest.fixture
def authed(client, as_user):
    as_user("authed@example.com")
    return client


def _ingest(conn, user_id, storage, add_file_doc, docs):
    from app.config import PipelineConfig
    from app.embeddings import HashEmbedder
    from app.ingest.pipeline import ingest_document

    ids = []
    for name, content in docs:
        doc = add_file_doc(conn, user_id, storage, name, content)
        ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
        ids.append(doc.id)
    return ids


@pytest.fixture
def seeded(conn, user, storage, add_file_doc):
    _ingest(conn, user, storage, add_file_doc, [
        ("refunds.md", "# Refund policy\n\nRefunds take 14 days to reach your original payment method.\n"),
        ("errors.md", "# Error codes\n\nError code E-4471 means the token expired.\n"),
        ("onboarding.md", "# Onboarding\n\nWelcome aboard. Your manager will schedule a first-week orientation.\n"),
    ])
    return conn, user


@pytest.fixture
def seeded_two_users(conn, two_users, storage, add_file_doc):
    a, b = two_users
    a_doc_ids = _ingest(conn, a, storage, add_file_doc, [
        ("refunds.md", "# Refunds\n\nRefunds take 14 days after approval.\n"),
        ("returns.md", "# Returns\n\nReturned items are refunded within 10 days of receipt.\n"),
    ])
    _ingest(conn, b, storage, add_file_doc, [
        ("b_refunds.md", "# Refunds\n\nB refunds arrive in 7 days.\n"),
    ])
    return conn, a, b, a_doc_ids


class ScriptedLLM:
    def __init__(self, draft, stop_reason="end_turn"):
        self._draft, self._stop, self.calls = draft, stop_reason, 0

    def draft(self, question, passages, model):
        from app.answer.llm import LLMOutcome

        self.calls += 1
        return LLMOutcome(self._draft, self._stop, 10, 5)


class SpyLLM:
    def __init__(self):
        self.calls = 0

    def draft(self, question, passages, model):
        from app.answer.llm import LLMOutcome
        from app.answer.schema import AnswerDraft, DraftSentence

        self.calls += 1
        d = AnswerDraft(status="answered", sentences=[DraftSentence(text="Spy.", citations=["c1"])], missing="")
        return LLMOutcome(d, "end_turn", 1, 1)
