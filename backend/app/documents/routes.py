import sqlite3
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.datastructures import UploadFile

from app.auth.deps import User, current_user, get_conn
from app.config import Settings
from app.db import connect
from app.embeddings import Embedder
from app.ingest.pipeline import ingest_document
from app.store import (
    ChunkRow,
    Document,
    create_document,
    delete_document,
    get_document_file,
    list_chunks,
    list_documents,
)

router = APIRouter(prefix="/api/documents")

MAX_BYTES = 20 * 1024 * 1024
ALLOWED = {"pdf", "docx", "md", "txt", "html"}
_READ_CHUNK = 1024 * 1024
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown; charset=utf-8",
    "txt": "text/plain; charset=utf-8",
    "html": "text/html; charset=utf-8",
    "url": "text/html; charset=utf-8",
}


class UrlImport(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


def _display_name(raw: str) -> str:
    return PurePosixPath(PureWindowsPath(raw).name).name


def _run_ingest(settings: Settings, embedder: Embedder, doc_id: str) -> None:
    conn = connect(settings.database_path)  # own connection: the request's is closed by then
    try:
        ingest_document(conn, embedder, settings.pipeline(), doc_id)
    finally:
        conn.close()


MAX_REQUEST_BYTES = 100 * 1024 * 1024
MAX_FILES = 20


async def _save_limited(upload: UploadFile, name: str, path: Path) -> int:
    """Stream the upload to `path`, aborting past the size limit. Returns bytes written."""
    size = 0
    with path.open("wb") as out:
        while chunk := await upload.read(_READ_CHUNK):
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(400, f"{name}: file too large (max 20 MB)")
            out.write(chunk)
    return size


async def _import_files(request: Request, user: User, conn, tasks: BackgroundTasks) -> list[Document]:
    settings: Settings = request.app.state.settings
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise HTTPException(413, "Upload too large (max 100 MB per request)")
    user_dir = settings.storage_dir / user.id
    written: list[tuple[str, str, str, Path, int]] = []
    docs: list[Document] = []
    try:
        async with request.form() as form:
            uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            if not uploads:
                raise HTTPException(422, "No files provided")
            if len(uploads) > MAX_FILES:
                raise HTTPException(400, "Too many files (max 20 per request)")
            user_dir.mkdir(parents=True, exist_ok=True)
            for up in uploads:  # validate + stream to disk; nothing is registered until all pass
                name = _display_name(up.filename or "")
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in ALLOWED:
                    raise HTTPException(400, f"{name or 'file'}: unsupported file type")
                doc_id = uuid.uuid4().hex
                path = user_dir / f"{doc_id}.{ext}"
                written.append((doc_id, name, ext, path, 0))
                size = await _save_limited(up, name, path)
                written[-1] = (doc_id, name, ext, path, size)
        for doc_id, name, ext, path, size in written:
            docs.append(create_document(
                conn, user.id, name=name, source_type=ext, source_url=None,
                file_path=str(path), size_bytes=size, doc_id=doc_id,
            ))
    except BaseException:
        for doc in docs:
            delete_document(conn, user.id, doc.id)
        for *_, path, _size in written:
            path.unlink(missing_ok=True)
        raise
    for doc in docs:
        tasks.add_task(_run_ingest, settings, request.app.state.embedder, doc.id)
    return docs


@router.post("", status_code=201)
async def add_documents(
    request: Request,
    tasks: BackgroundTasks,
    user: User = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[Document]:
    settings: Settings = request.app.state.settings
    ctype = request.headers.get("content-type", "").lower()
    if ctype.startswith("multipart/form-data"):
        return await _import_files(request, user, conn, tasks)
    if not ctype.startswith("application/json"):
        raise HTTPException(415, "Send multipart files or JSON {url}")
    try:
        body = UrlImport.model_validate(await request.json())
    except Exception as e:
        raise HTTPException(422, "url must be a non-empty string of 2,000 characters or fewer") from e
    doc_id = uuid.uuid4().hex
    path = settings.storage_dir / user.id / f"{doc_id}.html"
    doc = create_document(
        conn, user.id, name=body.url, source_type="url", source_url=body.url,
        file_path=str(path), size_bytes=0, doc_id=doc_id,
    )
    tasks.add_task(_run_ingest, settings, request.app.state.embedder, doc.id)
    return [doc]


@router.get("")
def list_all(user: User = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> list[Document]:
    return list_documents(conn, user.id)


@router.delete("/{doc_id}", status_code=204)
def remove(doc_id: str, user: User = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    path = delete_document(conn, user.id, doc_id)
    if path is None:
        raise HTTPException(404, "Not found")
    Path(path).unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/{doc_id}/file")
def get_file(doc_id: str, user: User = Depends(current_user), conn: sqlite3.Connection = Depends(get_conn)) -> FileResponse:
    found = get_document_file(conn, user.id, doc_id)
    if found is None or not found[1].is_file():
        raise HTTPException(404, "Not found")
    doc, path = found
    headers = {"X-Content-Type-Options": "nosniff", "Content-Disposition": f"inline; filename*=UTF-8''{quote(doc.name, safe='')}"}
    if doc.source_type in ("html", "url"):
        headers["Content-Security-Policy"] = "sandbox"  # uploaded HTML must not run scripts in our origin
    return FileResponse(path, media_type=MEDIA_TYPES[doc.source_type], headers=headers)


@router.get("/{doc_id}/chunks")
def get_chunks(
    doc_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    user: User = Depends(current_user),
    conn: sqlite3.Connection = Depends(get_conn),
) -> list[ChunkRow]:
    if get_document_file(conn, user.id, doc_id) is None:
        raise HTTPException(404, "Not found")
    return list_chunks(conn, user.id, doc_id, offset, limit)
