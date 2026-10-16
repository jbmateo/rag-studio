import pytest


def test_ask_end_to_end_with_fake_llm(authed_with_doc):
    r = authed_with_doc.post("/api/ask", json={"question": "How long do refunds take?"})
    body = r.json()
    assert r.status_code == 200 and body["status"] in ("answered", "partial")
    assert body["sentences"][0]["citations"] == [1] and body["citations"][0]["document_name"] == "notes.md"


@pytest.mark.parametrize("q", ["", "   ", "x" * 1001])
def test_question_validation(authed_with_doc, q):
    assert authed_with_doc.post("/api/ask", json={"question": q}).status_code == 422


def test_no_documents(authed):
    r = authed.post("/api/ask", json={"question": "hi"})
    assert r.status_code == 400 and r.json()["detail"] == "Upload a document first"


def test_llm_failure_is_502(authed_with_doc, failing_llm):
    r = authed_with_doc.post("/api/ask", json={"question": "How long do refunds take?"})
    assert r.status_code == 502
    assert r.json()["detail"] == "The answer service is unavailable. Please try again."


def test_requires_auth(client):
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 401


def test_other_users_doc_ids_ignored(client, as_user):
    as_user("a@x.io")
    doc = client.post(
        "/api/documents", files=[("files", ("a.md", b"# A\nRefunds take 14 days.\n", "text/markdown"))]
    ).json()[0]["id"]
    as_user("b@x.io")
    assert client.post("/api/ask", json={"question": "refunds", "doc_ids": [doc]}).status_code == 400
