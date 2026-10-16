import numpy as np

from app.embeddings import HashEmbedder, make_embedder
from app.store import create_document, delete_document, get_document, list_documents


def test_store_is_user_scoped(conn, two_users):
    a, b = two_users
    d = create_document(conn, a, name="x.md", source_type="md", source_url=None, file_path="f", size_bytes=1)
    assert get_document(conn, b, d.id) is None
    assert list_documents(conn, b) == []
    assert delete_document(conn, b, d.id) is None
    assert get_document(conn, a, d.id) is not None


def test_hash_embedder_similarity():
    e = HashEmbedder()
    v = e.embed(["refund policy days", "refund policy window", "quantum chromodynamics"])
    assert v.dtype == np.float32
    assert v.shape == (3, 384) and np.allclose(np.linalg.norm(v, axis=1), 1)
    assert v[0] @ v[1] > v[0] @ v[2]


def test_hash_embedder_empty_text_is_zero_vector():
    v = HashEmbedder().embed(["", "!!!"])
    assert v.shape == (2, 384) and not v.any()


def test_make_embedder():
    import pytest

    assert isinstance(make_embedder("hash"), HashEmbedder)
    with pytest.raises(ValueError):
        make_embedder("nope")


def test_delete_returns_file_path_and_cascades(conn, user, storage, add_file_doc):
    from pathlib import Path

    d = add_file_doc(conn, user, storage, "a.md", "# A\nx\n")
    assert isinstance(delete_document(conn, user, d.id), Path)
    assert get_document(conn, user, d.id) is None
