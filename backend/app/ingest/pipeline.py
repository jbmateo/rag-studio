import logging
from pathlib import Path

import numpy as np

from app.config import PipelineConfig
from app.embeddings import Embedder
from app.ingest.chunker import chunk_segments
from app.ingest.fetch import UnsafeURLError, fetch_url
from app.ingest.parsers import NO_TEXT, ParseError, parse_file
from app.store import (
    get_document_unscoped,
    insert_chunks_and_mark_ready_unscoped,
    mark_failed_unscoped,
    update_document_size_unscoped,
)

log = logging.getLogger(__name__)


def ingest_document(conn, embedder: Embedder, cfg: PipelineConfig, doc_id: str) -> None:
    doc = get_document_unscoped(conn, doc_id)
    if doc is None:
        return
    try:
        path = Path(doc["file_path"])
        source_type = doc["source_type"]
        if source_type == "url":
            body, _final_url = fetch_url(doc["source_url"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            update_document_size_unscoped(conn, doc_id, len(body))
            source_type = "html"
        drafts = chunk_segments(parse_file(path, source_type), cfg.chunk_chars)
        if not drafts:
            raise ParseError(NO_TEXT)
        vectors = np.asarray(embedder.embed([d.text for d in drafts]), dtype=np.float32)
        rows = [
            {
                "text": d.text, "location": d.location, "page": d.page,
                "char_start": d.char_start, "char_end": d.char_end,
                "embedding": vectors[i].tobytes(),
            }
            for i, d in enumerate(drafts)
        ]
        insert_chunks_and_mark_ready_unscoped(conn, doc_id, doc["user_id"], rows)
    except (ParseError, UnsafeURLError) as e:
        mark_failed_unscoped(conn, doc_id, str(e))
    except Exception:
        log.exception("Ingestion failed for document %s", doc_id)
        mark_failed_unscoped(conn, doc_id, "Processing failed")
