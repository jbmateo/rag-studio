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

    # The LLM fake arrives in a later task; pass None until then.
    with TestClient(create_app(settings, HashEmbedder(), None)) as c:
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
