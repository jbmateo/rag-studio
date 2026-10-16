"""User-scoped persistence for documents and chunks.

Every public function takes `user_id`; the `_unscoped` helpers are for the
ingestion pipeline only, which runs after the owner has been established.
"""
import sqlite3
import uuid
from pathlib import Path

import numpy as np
from pydantic import BaseModel

from app.embeddings import DEFAULT_DIM

_DOC_COLS = "id, name, source_type, source_url, size_bytes, status, error, chunk_count, created_at"


class Document(BaseModel):
    id: str
    name: str
    source_type: str
    source_url: str | None
    size_bytes: int
    status: str
    error: str | None
    chunk_count: int
    created_at: str


class ChunkRow(BaseModel):
    id: str
    document_id: str
    document_name: str
    ordinal: int
    text: str
    location: str
    page: int | None


def _doc(row: sqlite3.Row) -> Document:
    return Document(**{k: row[k] for k in Document.model_fields})


def _chunk(row: sqlite3.Row) -> ChunkRow:
    return ChunkRow(**{k: row[k] for k in ChunkRow.model_fields})


def create_document(
    conn, user_id: str, *, name: str, source_type: str, source_url: str | None,
    file_path: str, size_bytes: int,
) -> Document:
    doc_id = uuid.uuid4().hex
    conn.execute(
        "INSERT INTO documents(id, user_id, name, source_type, source_url, file_path, size_bytes)"
        " VALUES (?,?,?,?,?,?,?)",
        (doc_id, user_id, name, source_type, source_url, file_path, size_bytes),
    )
    conn.commit()
    return get_document(conn, user_id, doc_id)


def list_documents(conn, user_id: str) -> list[Document]:
    rows = conn.execute(
        f"SELECT {_DOC_COLS} FROM documents WHERE user_id=? ORDER BY created_at DESC, rowid DESC",
        (user_id,),
    ).fetchall()
    return [_doc(r) for r in rows]


def get_document(conn, user_id: str, doc_id: str) -> Document | None:
    row = conn.execute(
        f"SELECT {_DOC_COLS} FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)
    ).fetchone()
    return _doc(row) if row else None


def get_document_file(conn, user_id: str, doc_id: str) -> tuple[Document, Path] | None:
    row = conn.execute(
        f"SELECT {_DOC_COLS}, file_path FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)
    ).fetchone()
    return (_doc(row), Path(row["file_path"])) if row else None


def delete_document(conn, user_id: str, doc_id: str) -> Path | None:
    row = conn.execute(
        "SELECT file_path FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)
    ).fetchone()
    if row is None:
        return None
    conn.execute("DELETE FROM documents WHERE id=? AND user_id=?", (doc_id, user_id))
    conn.commit()
    return Path(row["file_path"])


def list_chunks(conn, user_id: str, doc_id: str, offset: int = 0, limit: int = 50) -> list[ChunkRow]:
    rows = conn.execute(
        "SELECT c.id, c.document_id, d.name AS document_name, c.ordinal, c.text, c.location, c.page"
        " FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE c.user_id=? AND d.user_id=? AND c.document_id=?"
        " ORDER BY c.ordinal LIMIT ? OFFSET ?",
        (user_id, user_id, doc_id, limit, offset),
    ).fetchall()
    return [_chunk(r) for r in rows]


def ready_doc_ids(conn, user_id: str, doc_ids: list[str] | None) -> list[str]:
    sql = "SELECT id FROM documents WHERE user_id=? AND status='ready'"
    params: list = [user_id]
    if doc_ids is not None:
        if not doc_ids:
            return []
        sql += f" AND id IN ({','.join('?' * len(doc_ids))})"
        params += doc_ids
    return [r["id"] for r in conn.execute(sql + " ORDER BY created_at, rowid", params)]


def load_vectors(conn, user_id: str, doc_ids: list[str] | None) -> tuple[list[str], np.ndarray]:
    sql = (
        "SELECT c.id, c.embedding FROM chunks c JOIN documents d ON d.id = c.document_id"
        " WHERE c.user_id=? AND d.user_id=? AND d.status='ready'"
    )
    params: list = [user_id, user_id]
    if doc_ids is not None:
        if not doc_ids:
            return [], np.zeros((0, DEFAULT_DIM), dtype=np.float32)
        sql += f" AND d.id IN ({','.join('?' * len(doc_ids))})"
        params += doc_ids
    rows = conn.execute(sql + " ORDER BY d.created_at, d.rowid, c.ordinal", params).fetchall()
    if not rows:
        return [], np.zeros((0, DEFAULT_DIM), dtype=np.float32)
    matrix = np.vstack([np.frombuffer(r["embedding"], dtype=np.float32) for r in rows])
    return [r["id"] for r in rows], matrix


def get_chunks(conn, user_id: str, chunk_ids: list[str]) -> dict[str, ChunkRow]:
    if not chunk_ids:
        return {}
    rows = conn.execute(
        "SELECT c.id, c.document_id, d.name AS document_name, c.ordinal, c.text, c.location, c.page"
        " FROM chunks c JOIN documents d ON d.id = c.document_id"
        f" WHERE c.user_id=? AND d.user_id=? AND c.id IN ({','.join('?' * len(chunk_ids))})",
        [user_id, user_id, *chunk_ids],
    ).fetchall()
    return {r["id"]: _chunk(r) for r in rows}


# --- pipeline-only helpers (no user scoping: the pipeline knows only doc_id) ---


def get_document_unscoped(conn, doc_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT id, user_id, source_type, source_url, file_path FROM documents WHERE id=?", (doc_id,)
    ).fetchone()


def update_document_size_unscoped(conn, doc_id: str, size_bytes: int) -> None:
    conn.execute("UPDATE documents SET size_bytes=? WHERE id=?", (size_bytes, doc_id))
    conn.commit()


def mark_failed_unscoped(conn, doc_id: str, error: str) -> None:
    conn.execute("UPDATE documents SET status='failed', error=? WHERE id=?", (error, doc_id))
    conn.commit()


def insert_chunks_and_mark_ready_unscoped(conn, doc_id: str, user_id: str, chunks: list[dict]) -> bool:
    """Insert all chunks and flip the doc to ready in one transaction.

    Returns False (inserting nothing) if the document row no longer exists.
    """
    conn.commit()
    conn.execute("BEGIN IMMEDIATE")
    try:
        if conn.execute("SELECT 1 FROM documents WHERE id=?", (doc_id,)).fetchone() is None:
            conn.rollback()
            return False
        conn.executemany(
            "INSERT INTO chunks(id, document_id, user_id, ordinal, text, location, page,"
            " char_start, char_end, embedding) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    uuid.uuid4().hex, doc_id, user_id, i, c["text"], c["location"], c["page"],
                    c["char_start"], c["char_end"], c["embedding"],
                )
                for i, c in enumerate(chunks)
            ],
        )
        conn.execute(
            "UPDATE documents SET status='ready', error=NULL, chunk_count=? WHERE id=?",
            (len(chunks), doc_id),
        )
        conn.commit()
        return True
    except BaseException:
        conn.rollback()
        raise
