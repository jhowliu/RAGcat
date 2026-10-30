"""End to end through HTTP against DynamoDB Local, with the in-process queue, store and models."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterator

import pytest
from conftest import RETURNS_PDF_PAGES, make_figure_pdf, make_pdf
from fastapi.testclient import TestClient

from ragcat.apps.container import Container, build
from ragcat.apps.dev import create_dev_app
from ragcat.shared.config import get_settings
from ragcat.shared.ids import ulid

H = {"Authorization": "Bearer dev:tester"}


@pytest.fixture
def env(tmp_path, dynamodb_endpoint) -> Iterator[tuple[TestClient, Container]]:
    settings = replace(
        get_settings(),
        table_name=f"ragcat-test-{ulid().lower()}",
        dynamodb_endpoint=dynamodb_endpoint,
        data_dir=tmp_path,
        storage="local",
        queue="local",
        vectors="local",
        embed_provider="fake",
        llm_provider="fake",
        vision_provider="fake",
        embed_dims=2048,
        cache="memory",
        auth="dev",
    )
    c = build(settings)
    with TestClient(create_dev_app(c)) as client:
        yield client, c
    c.table.drop()


def upload(client: TestClient, c: Container, aid: str, pages=RETURNS_PDF_PAGES, pdf: bytes | None = None) -> str:
    pdf = pdf or make_pdf(pages)
    r = client.post(f"/v1/assistants/{aid}/documents", json={"filename": "returns.pdf", "size_bytes": len(pdf), "content_type": "application/pdf"}, headers=H)
    assert r.status_code == 201, r.text
    upload = r.json()["upload"]
    r = client.post(upload["url"], data=upload["fields"], files={"file": ("returns.pdf", pdf, "application/pdf")})
    assert r.status_code == 204, r.text
    c.queue.drain()
    return upload["fields"]["key"].rsplit("/", 1)[-1].removesuffix(".pdf")


def chunks(client: TestClient, did: str) -> dict:
    r = client.get(f"/v1/documents/{did}/chunks", headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def ask(client: TestClient, aid: str, question: str, preview: bool = False) -> dict:
    r = client.post(f"/v1/assistants/{aid}/ask", json={"question": question, "stream": False, "preview": preview}, headers=H)
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_flow(env) -> None:
    client, c = env
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers=H).json()["usage"]["pages_read"] == 0

    aid = client.post("/v1/assistants", json={"name": "Mochi Pet Co. support", "fallback_contact": "help@mochi.example"}, headers=H).json()["id"]
    did = upload(client, c, aid)

    # Parsing finished: three passages, page images, usage counted.
    doc = client.get(f"/v1/documents/{did}", headers=H)
    assert doc.json()["status"] == "review" and doc.json()["page_count"] == 2
    assert client.get(f"/v1/documents/{did}", headers=H | {"If-None-Match": doc.headers["etag"]}).status_code == 304
    listing = chunks(client, did)
    assert [p["text"].split("\n")[0] for p in listing["items"]] == ["Returns policy", "Shipping", "Pet food storage"]
    page = client.get(f"/v1/documents/{did}/pages?from=1&to=2", headers=H).json()["items"][0]
    assert client.get(page["image_url"]).headers["content-type"] == "image/jpeg"
    assert client.get("/v1/me", headers=H).json()["usage"]["pages_read"] == 2

    # Optimistic locking on edits.
    first, second, third = (p["id"] for p in listing["items"])
    version = listing["edit_version"]
    assert client.post(f"/v1/documents/{did}/chunks/merge", json={"ids": [first, second]}, headers=H).status_code == 428
    assert client.post(f"/v1/documents/{did}/chunks/merge", json={"ids": [first, second]}, headers=H | {"If-Match": '"99"'}).status_code == 412
    merged = client.post(f"/v1/documents/{did}/chunks/merge", json={"ids": [first, second]}, headers=H | {"If-Match": f'"{version}"'})
    assert merged.status_code == 200, merged.text
    assert merged.json()["deleted"] == [second] and merged.json()["edit_version"] == version + 1

    # Embed, then ask: answered with a citation, second time from cache.
    assert client.post(f"/v1/documents/{did}/embed", headers=H).status_code == 202
    c.queue.drain()
    doc = client.get(f"/v1/documents/{did}", headers=H).json()
    assert doc["status"] == "ready" and doc["pending_changes"] == 0
    assert client.post(f"/v1/documents/{did}/embed", headers=H).json()["error"]["code"] == "NO_CHANGES"
    first_passage = chunks(client, did)["items"][0]
    assert first_passage["context"] == "This passage is from returns, in the section “Returns policy”."
    vector = c.vectors._items[first]
    assert vector["metadata"]["section"] == "Returns policy" and vector["metadata"]["context"] == first_passage["context"]
    assert vector["metadata"]["entities"] == ["policy:Returns policy"]
    answer = ask(client, aid, "Can opened items be returned?")
    assert answer["answered"] and answer["citations"][0]["chunk_id"] == first and not answer["cached"]
    assert ask(client, aid, "can  opened items be returned?")["cached"]
    missing = ask(client, aid, "What is the capital of France?")
    assert not missing["answered"] and missing["fallback"]["contact"] == "help@mochi.example"

    # Streaming returns the same answer as SSE events.
    with client.stream("POST", f"/v1/assistants/{aid}/ask", json={"question": "How should kibble be stored?"}, headers=H) as r:
        body = "".join(r.iter_text())
    assert body.startswith("event: meta") and "event: citations" in body and "event: done" in body

    # Publishing needs embedded content; editing a ready document invalidates cached answers.
    assert client.patch(f"/v1/assistants/{aid}", json={"published": True}, headers=H).json()["status"] == "live"
    version = chunks(client, did)["edit_version"]
    r = client.patch(f"/v1/documents/{did}/chunks/{first}", json={"text": "Opened items can be returned within 14 days if they are unused and still in the original bag."}, headers=H | {"If-Match": f'"{version}"'})
    assert r.json()["document"] == {"status": "review", "warning_count": 0, "pending_changes": 1}
    client.post(f"/v1/documents/{did}/embed", headers=H)
    c.queue.drain()
    assert not ask(client, aid, "Can opened items be returned?")["cached"]

    # Deleting removes the document, its passages and its vectors.
    assert client.delete(f"/v1/documents/{did}", headers=H).status_code == 202
    c.queue.drain()
    assert client.get(f"/v1/documents/{did}", headers=H).status_code == 404
    assert c.vectors._items == {}
    assert c.table.query_prefix(f"DOC#{did}", "") == [] and not c.store.file_path(f"pages/{did}").exists()
    assert client.get(f"/v1/assistants/{aid}", headers=H).json()["status"] == "empty"


class CountingEmbedder:
    def __init__(self, inner) -> None:
        self.inner, self.texts = inner, []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.extend(texts)
        return self.inner.embed(texts)


def edit(client: TestClient, did: str, method: str, path: str, body: dict | None = None) -> dict:
    version = chunks(client, did)["edit_version"]
    r = client.request(method, f"/v1/documents/{did}/chunks{path}", json=body, headers=H | {"If-Match": f'"{version}"'})
    assert r.status_code == 200, r.text
    return r.json()


def test_owner_preview_answers_from_unpublished_edits(env) -> None:
    client, c = env
    aid = client.post("/v1/assistants", json={"name": "Mochi", "fallback_contact": "help@mochi.example"}, headers=H).json()["id"]
    did = upload(client, c, aid)
    returns, shipping, storage = (p["id"] for p in chunks(client, did)["items"])

    # Nothing published yet: a preview answers from passages that are not in the vector index.
    first = ask(client, aid, "How should kibble be stored?", preview=True)
    assert first["preview"] and first["answered"] and first["citations"][0]["chunk_id"] == storage
    assert c.vectors._items == {}

    # Publishing writes the vectors the preview prepared instead of embedding again.
    counting = c.indexing.embedder = CountingEmbedder(c.indexing.embedder)
    client.post(f"/v1/documents/{did}/embed", headers=H)
    c.queue.drain()
    assert counting.texts == [] and set(c.vectors._items) == {returns, shipping, storage}
    assert client.patch(f"/v1/assistants/{aid}", json={"published": True}, headers=H).json()["status"] == "live"

    # An edit answers in a preview at once; customers keep the published text until Publish.
    edit(client, did, "PATCH", f"/{shipping}", {"text": "Shipping\nOrders ship by drone to Tasmania within one hour."})
    with client.stream("POST", f"/v1/assistants/{aid}/ask", json={"question": "Do you ship by drone?", "preview": True}, headers=H) as r:
        body = "".join(r.iter_text())
    assert 'event: preparing\ndata: {"done": 0, "total": 1}' in body and 'data: {"done": 1, "total": 1}' in body
    assert "drone" in ask(client, aid, "Do you ship by drone?", preview=True)["answer"]
    assert not ask(client, aid, "Do you ship by drone?", preview=True)["cached"]  # previews are never cached
    assert "drone" not in ask(client, aid, "Do you ship by drone?")["answer"]
    assert "drone" not in c.vectors._items[shipping]["metadata"]["text"]

    # Split: the old whole-passage vector drops out of the preview and each part answers.
    text = chunks(client, did)["items"][0]["text"]
    cut = text.index("Opened items")
    upserted = edit(client, did, "POST", f"/{returns}/split", {"parts": [text[:cut], text[cut:]]})["upserted"]
    second_half = next(p["id"] for p in upserted if p["id"] != returns)
    assert ask(client, aid, "Can opened items be returned if defective?", preview=True)["citations"][0]["chunk_id"] == second_half
    assert ask(client, aid, "Can opened items be returned if defective?")["citations"][0]["chunk_id"] == returns

    # A removed passage stops answering in the preview only.
    edit(client, did, "DELETE", f"/{storage}")
    assert not ask(client, aid, "How should kibble be stored?", preview=True)["answered"]
    assert ask(client, aid, "How should kibble be stored?")["answered"]

    # Publish reuses every prepared vector, and customers now get the edits.
    counting.texts.clear()
    client.post(f"/v1/documents/{did}/embed", headers=H)
    c.queue.drain()
    assert counting.texts == []
    assert set(c.vectors._items) == {returns, second_half, shipping}
    assert "drone" in ask(client, aid, "Do you ship by drone?")["answer"]


def test_preview_refuses_more_changes_than_a_test_should_wait_for(env, monkeypatch) -> None:
    client, c = env
    monkeypatch.setattr("ragcat.indexing.service.PREVIEW_LIMIT", 2)
    aid = client.post("/v1/assistants", json={"name": "A"}, headers=H).json()["id"]
    upload(client, c, aid)  # three passages, none published
    r = client.post(f"/v1/assistants/{aid}/ask", json={"question": "Can opened items be returned?", "stream": False, "preview": True}, headers=H)
    assert r.status_code == 409 and r.json()["error"]["code"] == "TOO_MANY_CHANGES"
    assert r.json()["error"]["details"] == {"passages": 3, "limit": 2}


def test_deleting_an_assistant_removes_its_documents_vectors_and_files(env) -> None:
    client, c = env
    empty = client.post("/v1/assistants", json={"name": "Nothing uploaded"}, headers=H).json()["id"]
    aid = client.post("/v1/assistants", json={"name": "Mochi Pet Co. support"}, headers=H).json()["id"]
    did = upload(client, c, aid)
    client.post(f"/v1/documents/{did}/embed", headers=H)
    c.queue.drain()
    client.patch(f"/v1/assistants/{aid}", json={"published": True, "widget_origins": ["https://mochi.example"]}, headers=H)
    assert ask(client, aid, "Can opened items be returned?")["answered"]
    waiting = client.post(f"/v1/assistants/{aid}/documents", json={"filename": "later.pdf", "size_bytes": 10, "content_type": "application/pdf"}, headers=H)
    waiting = waiting.json()["document"]["id"]
    assert c.vectors._items and c.store.file_path(f"pages/{did}/1.jpg").exists()

    assert client.delete(f"/v1/assistants/{aid}", headers={"Authorization": "Bearer dev:someone-else"}).status_code == 404
    assert client.delete(f"/v1/assistants/{empty}", headers=H).status_code == 202
    r = client.delete(f"/v1/assistants/{aid}", headers=H)
    assert r.status_code == 202 and r.json() == {"assistant": {"id": aid, "status": "deleting"}}

    # Gone at once for the owner and for customers; documents, vectors and files go in the background.
    assert client.get(f"/v1/assistants/{aid}", headers=H).status_code == 404
    assert client.get("/v1/assistants", headers=H).json()["items"] == []
    assert client.post(f"/v1/assistants/{aid}/ask", json={"question": "hi", "stream": False}, headers=H).status_code == 404
    assert client.post(f"/v1/widget/{aid}/ask", json={"question": "hi", "stream": False}).status_code == 404
    c.queue.drain()
    assert client.get(f"/v1/documents/{did}", headers=H).status_code == 404
    assert client.get(f"/v1/documents/{waiting}", headers=H).status_code == 404
    assert c.vectors._items == {}
    assert not c.store.file_path(f"uploads/{aid}/{did}.pdf").exists() and not c.store.file_path(f"pages/{did}").exists()
    assert c.table.get(f"AST#{aid}", "META") is None  # indexing reports the vector change after the Assistant is gone
    assert client.delete(f"/v1/assistants/{aid}", headers=H).status_code == 404


def test_rejects_non_pdf_and_other_owners(env) -> None:
    client, c = env
    aid = client.post("/v1/assistants", json={"name": "A"}, headers=H).json()["id"]
    r = client.post(f"/v1/assistants/{aid}/documents", json={"filename": "x.txt", "size_bytes": 3, "content_type": "text/plain"}, headers=H)
    assert r.status_code == 400
    other = {"Authorization": "Bearer dev:someone-else"}
    assert client.get(f"/v1/assistants/{aid}", headers=other).status_code == 404
    assert client.post(f"/v1/assistants/{aid}/ask", json={"question": "hi", "stream": False}, headers=other).status_code == 404


def test_fake_pdf_fails_with_not_a_pdf(env) -> None:
    client, c = env
    aid = client.post("/v1/assistants", json={"name": "A"}, headers=H).json()["id"]
    r = client.post(f"/v1/assistants/{aid}/documents", json={"filename": "fake.pdf", "size_bytes": 5, "content_type": "application/pdf"}, headers=H)
    upload, did = r.json()["upload"], r.json()["document"]["id"]
    client.post(upload["url"], data=upload["fields"], files={"file": ("fake.pdf", b"hello", "application/pdf")})
    c.queue.drain()
    doc = client.get(f"/v1/documents/{did}", headers=H).json()
    assert doc["status"] == "failed" and doc["error"]["code"] == "NOT_A_PDF"


def test_figures_become_described_passages(env) -> None:
    client, c = env
    aid = client.post("/v1/assistants", json={"name": "A"}, headers=H).json()["id"]
    did = upload(client, c, aid, pdf=make_figure_pdf())
    assert client.get(f"/v1/documents/{did}", headers=H).json()["status"] == "review"
    texts = [p["text"] for p in chunks(client, did)["items"]]
    figure = next(t for t in texts if "[Figure]" in t)
    # The photo has no text, so the fake model calls it decorative; the heading goes to the chart.
    assert figure.startswith("Delivery report\nFigure 1. Average delivery days by region\n[Figure] A figure with the text:")
    assert "Metro" in figure
    assert sum("[Figure]" in t for t in texts) == 1  # the text-less photo is decorative for the fake model


def test_embedding_failure_returns_to_review_and_the_retry_resumes(env) -> None:
    from ragcat.shared.errors import UpstreamUnavailable

    client, c = env
    aid = client.post("/v1/assistants", json={"name": "A"}, headers=H).json()["id"]
    did = upload(client, c, aid)
    working = c.indexing.embedder

    class Down:
        def embed(self, texts: list[str]) -> list[list[float]]:
            raise UpstreamUnavailable("Embedding model is unavailable")

    c.indexing.embedder = Down()
    client.post(f"/v1/documents/{did}/embed", headers=H)
    c.queue.drain()
    doc = client.get(f"/v1/documents/{did}", headers=H).json()
    assert doc["status"] == "review" and doc["error"]["code"] == "EMBED_FAILED"

    c.indexing.embedder = working
    assert client.post(f"/v1/documents/{did}/embed", headers=H).status_code == 202
    c.queue.drain()
    doc = client.get(f"/v1/documents/{did}", headers=H).json()
    assert doc["status"] == "ready" and doc["error"] is None and doc["pending_changes"] == 0


def test_website_widget(env, monkeypatch) -> None:
    """api-design.md §7: customers ask through the widget once the Assistant is published on a site."""
    client, c = env
    monkeypatch.setattr("ragcat.apps.widget._get", lambda url: '<html><body><div id="root"></div></body></html>')
    monkeypatch.setattr("ragcat.apps.http._now", lambda: 6000.0)
    aid = client.post("/v1/assistants", json={"name": "Mochi Pet Co. support", "fallback_contact": "help@mochi.example"}, headers=H).json()["id"]
    did = upload(client, c, aid)
    client.post(f"/v1/documents/{did}/embed", headers=H)
    c.queue.drain()
    question = {"question": "Can opened items be returned?", "stream": False}

    # Not published, then published without a site: the widget can't answer and can't be framed.
    assert client.post(f"/v1/widget/{aid}/ask", json=question).json()["error"]["code"] == "NOT_PUBLISHED"
    assert client.patch(f"/v1/assistants/{aid}", json={"published": True}, headers=H).json()["widget_origins"] == []
    assert client.post(f"/v1/widget/{aid}/ask", json=question).status_code == 403
    assert client.get(f"/v1/widget/{aid}/frame").headers["content-security-policy"] == "frame-ancestors 'none'"

    # The owner lists their sites; anything that isn't a whole https site is refused.
    bad = client.patch(f"/v1/assistants/{aid}", json={"widget_origins": ["https://*.mochi.example"]}, headers=H)
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    sites = ["https://mochi.example", "http://localhost:5173"]
    assert client.patch(f"/v1/assistants/{aid}", json={"widget_origins": sites}, headers=H).json()["widget_origins"] == sites
    assert client.get(f"/v1/assistants/{aid}", headers=H).json()["widget_origins"] == sites

    frame = client.get(f"/v1/widget/{aid}/frame?lang=zh")
    assert frame.status_code == 200 and frame.headers["content-security-policy"] == "frame-ancestors https://mochi.example http://localhost:5173"
    assert f'data-aid="{aid}"' in frame.text and 'data-available="true"' in frame.text and 'data-contact="help@mochi.example"' in frame.text
    unknown = client.get("/v1/widget/ast_unknown/frame")
    assert unknown.status_code == 404 and unknown.headers["content-security-policy"] == "frame-ancestors 'none'"

    # No sign-in; citations name the Document and page only.
    answer = client.post(f"/v1/widget/{aid}/ask", json=question)
    assert answer.status_code == 200, answer.text
    assert answer.json()["answered"] and set(answer.json()["citations"][0]) == {"n", "document_title", "page", "para"}
    with client.stream("POST", f"/v1/widget/{aid}/ask", json={"question": "How should kibble be stored?"}) as r:
        body = "".join(r.iter_text())
    assert "event: citations" in body and "chunk_id" not in body and "boxes" not in body
    assert client.post(f"/v1/widget/{aid}/ask", json=question | {"preview": True}).status_code == 200  # preview is ignored

    # Ten requests a minute per visitor, refused ones included: five so far, five more pass, then it waits.
    for _ in range(5):
        assert client.post(f"/v1/widget/{aid}/ask", json=question).status_code == 200
    limited = client.post(f"/v1/widget/{aid}/ask", json=question)
    assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    other = client.post(f"/v1/widget/{aid}/ask", json=question, headers={"CloudFront-Viewer-Address": "203.0.113.9:4431"})
    assert other.status_code == 200  # another visitor

    # Taking the site list away turns the widget off again.
    client.patch(f"/v1/assistants/{aid}", json={"widget_origins": []}, headers=H)
    assert client.post(f"/v1/widget/{aid}/ask", json=question, headers={"CloudFront-Viewer-Address": "203.0.113.10:1"}).status_code == 403
