def _md(name, body=b"# A\nx\n"):
    return ("files", (name, body, "text/markdown"))


def test_upload_process_list_chunks_delete(authed):
    r = authed.post("/api/documents", files=[("files", ("notes.md", b"# Refunds\nRefunds take 14 days.\n", "text/markdown"))])
    assert r.status_code == 201 and r.json()[0]["status"] == "processing"
    doc_id = r.json()[0]["id"]
    docs = authed.get("/api/documents").json()          # TestClient runs background tasks before returning
    assert docs[0]["status"] == "ready" and docs[0]["chunk_count"] == 1
    assert authed.get(f"/api/documents/{doc_id}/chunks").json()[0]["location"] == "Refunds"
    f = authed.get(f"/api/documents/{doc_id}/file")
    assert f.content.startswith(b"# Refunds")
    assert f.headers["content-type"] == "text/markdown; charset=utf-8"
    assert f.headers["content-disposition"] == "inline; filename*=UTF-8''notes.md"
    assert authed.delete(f"/api/documents/{doc_id}").status_code == 204
    assert authed.get("/api/documents").json() == []


def test_rejects_bad_type_and_size(authed, settings):
    r = authed.post("/api/documents", files=[("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400 and r.json()["detail"] == "x.exe: unsupported file type"
    big = b"a" * (20 * 1024 * 1024 + 1)
    assert authed.post("/api/documents", files=[("files", ("big.txt", big, "text/plain"))]).json()["detail"] == "big.txt: file too large (max 20 MB)"


def test_bad_file_saves_nothing_for_request(authed, settings):
    r = authed.post("/api/documents", files=[_md("ok.md"), ("files", ("x.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400
    assert authed.get("/api/documents").json() == []
    assert not list(settings.storage_dir.rglob("*.md"))


def test_hostile_filename_stored_safely(authed, settings):
    r = authed.post("/api/documents", files=[_md("../../etc/passwd.md"), _md("résumé.md", b"# B\ny\n"), _md("résumé.md", b"# C\nz\n")])
    names = sorted(d["name"] for d in r.json())
    assert names == ["passwd.md", "résumé.md", "résumé.md"]
    stored = list(settings.storage_dir.rglob("*.md"))
    assert len(stored) == 3 and all(p.resolve().is_relative_to(settings.storage_dir.resolve()) for p in stored)


def test_cross_user_isolation(client, as_user):
    as_user("a@x.io"); doc_id = client.post("/api/documents", files=[("files", ("a.md", b"# A\nx\n", "text/markdown"))]).json()[0]["id"]
    as_user("b@x.io")
    assert client.get("/api/documents").json() == []
    for path in (f"/api/documents/{doc_id}/file", f"/api/documents/{doc_id}/chunks"):
        assert client.get(path).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}").status_code == 404


def test_requires_auth(client):
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/documents", json={"url": "https://example.com"}).status_code == 401


def test_html_served_with_csp_sandbox(authed):
    r = authed.post("/api/documents", files=[("files", ("p.html", b"<html><body><p>Hello world</p><script>1</script></body></html>", "text/html"))])
    f = authed.get(f"/api/documents/{r.json()[0]['id']}/file")
    assert f.headers["content-security-policy"] == "sandbox"
    assert f.headers["content-type"] == "text/html; charset=utf-8"


def test_url_import_unsafe_scheme_marked_failed(authed, settings):
    r = authed.post("/api/documents", json={"url": "ftp://example.com/x"})
    assert r.status_code == 201
    d = r.json()[0]
    assert d["source_type"] == "url" and d["name"] == "ftp://example.com/x" and d["source_url"] == "ftp://example.com/x"
    assert authed.get("/api/documents").json()[0]["status"] == "failed"


def test_url_import_validation(authed):
    for body in ({"url": ""}, {"url": "h" * 2001}, {}):
        assert authed.post("/api/documents", json=body).status_code == 422
    assert authed.post("/api/documents", json={"url": "h" * 2000}).status_code == 201


def test_url_import_success_stores_html(authed, settings, monkeypatch):
    import app.ingest.pipeline as pipeline
    monkeypatch.setattr(pipeline, "fetch_url", lambda url: (b"<html><body><p>Hi there</p></body></html>", url))
    d = authed.post("/api/documents", json={"url": "https://example.com/p"}).json()[0]
    docs = authed.get("/api/documents").json()
    assert docs[0]["status"] == "ready"
    assert (settings.storage_dir / authed.get("/api/auth/me").json()["id"] / f"{d['id']}.html").exists()
    f = authed.get(f"/api/documents/{d['id']}/file")
    assert f.headers["content-security-policy"] == "sandbox"


def test_chunks_pagination(authed):
    body = b"# A\none\n# B\ntwo\n# C\nthree\n"
    doc_id = authed.post("/api/documents", files=[_md("p.md", body)]).json()[0]["id"]
    allc = authed.get(f"/api/documents/{doc_id}/chunks").json()
    assert len(allc) >= 3
    page = authed.get(f"/api/documents/{doc_id}/chunks?offset=1&limit=1").json()
    assert page == [allc[1]]


def test_missing_doc_404(authed):
    assert authed.get("/api/documents/nope/chunks").status_code == 404
    assert authed.get("/api/documents/nope/file").status_code == 404


def test_too_many_files(authed, settings):
    r = authed.post("/api/documents", files=[_md(f"{i}.md") for i in range(21)])
    assert r.status_code == 400 and r.json()["detail"] == "Too many files (max 20 per request)"
    assert authed.get("/api/documents").json() == []


def test_declared_content_length_413(authed):
    r = authed.post("/api/documents", files=[_md("a.md")], headers={"content-length": str(101 * 1024 * 1024)})
    assert r.status_code == 413 and r.json()["detail"] == "Upload too large (max 100 MB per request)"


def test_late_failure_cleans_written_files(authed, settings):
    r = authed.post("/api/documents", files=[_md("ok.md"), ("files", ("big.txt", b"a" * (20 * 1024 * 1024 + 1), "text/plain"))])
    assert r.status_code == 400
    assert not [p for p in settings.storage_dir.rglob("*") if p.is_file()]
    assert authed.get("/api/documents").json() == []


def test_file_response_nosniff(authed):
    doc_id = authed.post("/api/documents", files=[_md("a.md")]).json()[0]["id"]
    assert authed.get(f"/api/documents/{doc_id}/file").headers["x-content-type-options"] == "nosniff"
