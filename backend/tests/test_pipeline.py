import httpx

from app.config import PipelineConfig
from app.embeddings import HashEmbedder
from app.ingest.pipeline import ingest_document
from app.store import (
    create_document, delete_document, get_chunks, get_document, list_chunks,
    load_vectors, ready_doc_ids,
)


def test_ingest_markdown_to_ready(conn, user, storage, add_file_doc):
    doc = add_file_doc(conn, user, storage, "a.md", "# Refunds\nRefunds take 14 days.\n")
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert d.status == "ready" and d.chunk_count == 1
    assert list_chunks(conn, user, doc.id)[0].location == "Refunds"


def test_ingest_failure_sets_error_and_no_chunks(conn, user, storage, add_file_doc):
    doc = add_file_doc(conn, user, storage, "blank.txt", "   ")
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert d.status == "failed" and d.error == "No extractable text"
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0


def test_ingest_after_delete_is_silent(conn, user, storage, add_file_doc):
    doc = add_file_doc(conn, user, storage, "a.md", "# A\ntext\n")
    delete_document(conn, user, doc.id)
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0


def test_delete_during_embedding_leaves_no_chunks(conn, user, storage, add_file_doc):
    doc = add_file_doc(conn, user, storage, "a.md", "# A\ntext\n")

    class DeletingEmbedder(HashEmbedder):
        def embed(self, texts):
            delete_document(conn, user, doc.id)
            return super().embed(texts)

    ingest_document(conn, DeletingEmbedder(), PipelineConfig(), doc.id)
    assert conn.execute("select count(*) from chunks").fetchone()[0] == 0


def test_unexpected_error_sets_generic_message(conn, user, storage, add_file_doc):
    doc = add_file_doc(conn, user, storage, "a.md", "# A\ntext\n")

    class Boom(HashEmbedder):
        def embed(self, texts):
            raise RuntimeError("secret internals")

    ingest_document(conn, Boom(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert d.status == "failed" and d.error == "Processing failed"


def test_load_vectors_skips_non_ready(conn, user, storage, add_file_doc):
    ready = add_file_doc(conn, user, storage, "a.md", "# A\nalpha\n")
    ingest_document(conn, HashEmbedder(), PipelineConfig(), ready.id)
    other = add_file_doc(conn, user, storage, "b.md", "# B\nbeta\n")  # still processing
    ids, m = load_vectors(conn, user, None)
    assert len(ids) == 1 and m.shape == (1, 384)
    assert ready_doc_ids(conn, user, None) == [ready.id]
    assert ready_doc_ids(conn, user, [other.id]) == []
    assert get_chunks(conn, user, ids)[ids[0]].document_name == "a.md"


def test_load_vectors_empty(conn, user):
    ids, m = load_vectors(conn, user, None)
    assert ids == [] and m.shape == (0, 384)


def test_ingest_url_doc(conn, user, storage, monkeypatch):
    html = b"<html><body><article><h1>Policy</h1><p>" + b"Refunds are issued within fourteen days. " * 5 + b"</p></article></body></html>"
    monkeypatch.setattr("app.ingest.pipeline.fetch_url", lambda url: (html, url))
    path = storage / "u.html"
    doc = create_document(conn, user, name="example.com", source_type="url",
                          source_url="https://example.com/p", file_path=str(path), size_bytes=0)
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert path.read_bytes() == html
    assert d.status == "ready", d.error
    assert d.size_bytes == len(html)


def test_ingest_url_unsafe_sets_error(conn, user, storage):
    doc = create_document(conn, user, name="x", source_type="url",
                          source_url="http://127.0.0.1/", file_path=str(storage / "x.html"), size_bytes=0)
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    d = get_document(conn, user, doc.id)
    assert d.status == "failed" and d.error == "URL points to a non-public address"


def test_url_doc_deleted_mid_fetch_leaves_no_file(conn, user, storage, monkeypatch):
    html = b"<html><body><article><h1>Policy</h1><p>" + b"Refunds are issued within fourteen days. " * 5 + b"</p></article></body></html>"
    path = storage / "gone.html"
    doc = create_document(conn, user, name="example.com", source_type="url",
                          source_url="https://example.com/p", file_path=str(path), size_bytes=0)

    def fetch_and_delete(url):
        delete_document(conn, user, doc.id)
        return html, url

    monkeypatch.setattr("app.ingest.pipeline.fetch_url", fetch_and_delete)
    ingest_document(conn, HashEmbedder(), PipelineConfig(), doc.id)
    assert not path.exists()
