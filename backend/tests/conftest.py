import uuid

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
