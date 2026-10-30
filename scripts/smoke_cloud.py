"""Verify upload -> parse -> review/edit -> embed -> publish -> streaming answer/cache.

Set RAGCAT_ACCESS_TOKEN to a Cognito access token. It is never sent to S3 or printed.
Unless --keep is supplied, the test deletes what it created: its Assistant, or only its Document
when --assistant-id names an existing Assistant.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]


def wait_document(client: httpx.Client, did: str, desired: str, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/documents/{did}")
        if desired == "deleted" and response.status_code == 404:
            return {}
        response.raise_for_status()
        document = response.json()
        if document["status"] == desired:
            return document
        if document["status"] in ("failed", "cancelled") or document.get("error"):
            raise RuntimeError(f"Document processing failed: {document.get('error')}")
        time.sleep(2)
    raise TimeoutError(f"Document {did} did not reach {desired} in {timeout}s")


def streamed_answer(client: httpx.Client, aid: str, question: str) -> dict:
    events = {}
    tokens = []
    event, data = "", []
    with client.stream("POST", f"/v1/assistants/{aid}/ask", json={"question": question, "stream": True}, headers={"Accept": "text/event-stream"}) as response:
        response.raise_for_status()
        if not response.headers.get("content-type", "").startswith("text/event-stream"):
            raise RuntimeError("Question endpoint did not return SSE")
        for line in response.iter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
            elif not line and data:
                payload = json.loads("\n".join(data))
                if event == "error":
                    raise RuntimeError(f"Answer failed: {payload.get('code')}")
                if event == "token":
                    tokens.append(payload["text"])
                else:
                    events[event] = payload
                event, data = "", []
    if not events.get("done", {}).get("answered") or not events.get("citations", {}).get("items") or not tokens:
        raise RuntimeError("The answer must complete with text and at least one citation")
    return {"cached": events["meta"]["cached"], "latency_ms": events["done"]["latency_ms"], "citations": len(events["citations"]["items"])}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--assistant-id")
    parser.add_argument("--pdf", type=Path, default=ROOT / "samples" / "mochi-returns-policy.pdf")
    parser.add_argument("--question", default="Can unopened items be returned?")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    base = urlparse(args.base_url)
    token = os.environ.get("RAGCAT_ACCESS_TOKEN", "")
    if base.scheme not in ("http", "https") or not base.netloc or base.username or base.password or base.query or base.fragment or base.path not in ("", "/"):
        parser.error("Use an HTTP(S) site origin without credentials or a path")
    local = base.hostname in ("localhost", "127.0.0.1", "::1")
    if not token or (token.startswith("dev:") and not local) or (base.scheme != "https" and not local):
        parser.error("Set a Cognito RAGCAT_ACCESS_TOKEN and use HTTPS for cloud tests; dev tokens are only allowed on localhost")
    if not args.pdf.is_file():
        parser.error("The sample PDF does not exist")
    did = None
    aid = args.assistant_id
    own_assistant = False
    exit_code = 1
    with httpx.Client(base_url=args.base_url.rstrip("/"), headers={"Authorization": f"Bearer {token}"}, timeout=90) as client:
        try:
            me = client.get("/v1/me")
            me.raise_for_status()
            if not aid:
                response = client.post("/v1/assistants", json={"name": "RAGcat cloud smoke", "fallback_contact": ""})
                response.raise_for_status()
                aid, own_assistant = response.json()["id"], True
            print(json.dumps({"stage": "assistant", "assistant_id": aid}))
            response = client.post(f"/v1/assistants/{aid}/documents", json={"filename": args.pdf.name, "size_bytes": args.pdf.stat().st_size, "content_type": "application/pdf"})
            response.raise_for_status()
            created = response.json()
            did = created["document"]["id"]
            upload = created["upload"]
            # A separate client prevents leaking the owner's Authorization header to S3.
            with httpx.Client(timeout=90) as objects:
                upload_url = str(client.base_url.join(upload["url"]))
                with args.pdf.open("rb") as pdf:
                    uploaded = objects.post(upload_url, data=upload["fields"], files={"file": (args.pdf.name, pdf, "application/pdf")})
                uploaded.raise_for_status()
                wait_document(client, did, "review", args.timeout)
                response = client.get(f"/v1/documents/{did}/pages?from=1&to=1")
                response.raise_for_status()
                image_url = str(client.base_url.join(response.json()["items"][0]["image_url"]))
                page = objects.get(image_url)
                page.raise_for_status()
                if not page.headers.get("content-type", "").startswith("image/"):
                    raise RuntimeError("Page preview was not an image")
            response = client.get(f"/v1/documents/{did}/chunks")
            response.raise_for_status()
            listing = response.json()
            passage = listing["items"][0]
            edited = client.patch(f"/v1/documents/{did}/chunks/{passage['id']}", headers={"If-Match": f"\"{listing['edit_version']}\""}, json={"text": passage["text"] + "\nThis copy was reviewed during a deployment smoke test."})
            edited.raise_for_status()
            if edited.json()["edit_version"] <= listing["edit_version"]:
                raise RuntimeError("Review edit did not advance the Document version")
            response = client.post(f"/v1/documents/{did}/embed")
            response.raise_for_status()
            wait_document(client, did, "ready", args.timeout)
            published = client.patch(f"/v1/assistants/{aid}", json={"published": True})
            published.raise_for_status()
            if not published.json()["published"]:
                raise RuntimeError("Assistant did not publish")
            cold = streamed_answer(client, aid, args.question)
            warm = streamed_answer(client, aid, args.question)
            if cold["cached"] or not warm["cached"]:
                raise RuntimeError("Expected a cold answer followed by an answer cache hit")
            print(json.dumps({"status": "passed", "assistant_id": aid, "document_id": did, "cold": cold, "warm": warm}))
            exit_code = 0
        except (httpx.HTTPError, KeyError, IndexError, RuntimeError, TimeoutError) as error:
            # Avoid formatting HTTP URLs, which can contain presigned credentials.
            detail = f"HTTP {error.response.status_code}" if isinstance(error, httpx.HTTPStatusError) else str(error) if isinstance(error, (RuntimeError, TimeoutError)) else type(error).__name__
            print(json.dumps({"status": "failed", "assistant_id": aid, "document_id": did, "error": detail}))
            exit_code = 1
        finally:
            if not args.keep and (did or own_assistant):
                try:
                    response = client.delete(f"/v1/assistants/{aid}" if own_assistant else f"/v1/documents/{did}")
                    response.raise_for_status()
                    if did:
                        wait_document(client, did, "deleted", args.timeout)
                    print(json.dumps({"stage": "cleanup", "deleted_assistant_id": aid if own_assistant else None, "deleted_document_id": did}))
                except (httpx.HTTPError, RuntimeError, TimeoutError):
                    print(json.dumps({"stage": "cleanup_incomplete", "assistant_id": aid, "document_id": did}))
                    exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
