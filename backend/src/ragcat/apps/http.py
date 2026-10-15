"""HTTP layer for the api and qa services (api-design.md). Serialisation lives here, not in domains."""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Iterator, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ragcat.answering.domain import Caller
from ragcat.answering.service import collect
from ragcat.apps.container import Container
from ragcat.apps.widget import WidgetPage, public_events, visitor_ip
from ragcat.assistants.domain import AssistantConfig
from ragcat.assistants.service import AssistantSummary
from ragcat.curation.domain import ChangeSet, Document, Passage, PassageCounts
from ragcat.identity.domain import Principal, Tokens, User
from ragcat.infra.cache import fixed_window
from ragcat.shared.errors import AppError, NotFound, ValidationError

WIDGET_ASKS_PER_MINUTE = 10  # per Assistant and visitor IP (api-design.md §7)


def _now() -> float:
    return time.time()


# ---------------------------------------------------------------- request bodies

class CreateAssistant(BaseModel):
    name: str = Field(default="", max_length=80)
    fallback_contact: str = Field(default="", max_length=200)


class UpdateAssistant(BaseModel):
    name: str | None = Field(default=None, max_length=80)
    fallback_contact: str | None = Field(default=None, max_length=200)
    published: bool | None = None
    widget_origins: list[str] | None = Field(default=None, max_length=50)  # the domain allows 10


class UpdateMe(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class RefreshToken(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=8192)


class CreateDocument(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(gt=0)
    content_type: str


class UpdateDocument(BaseModel):
    enabled: bool


class AddChunk(BaseModel):
    after_id: str | None = None
    text: str
    page: int | None = None


class EditChunk(BaseModel):
    text: str


class SplitChunk(BaseModel):
    parts: list[str] = Field(min_length=2, max_length=20)


class MergeChunks(BaseModel):
    ids: list[str] = Field(min_length=2, max_length=50)
    separator: str = Field(default="\n\n", max_length=10)


class Ask(BaseModel):
    question: str = Field(max_length=2000)
    stream: bool = True
    preview: bool = False  # owner's test: unpublished edits answer too


class WidgetAsk(BaseModel):
    question: str = Field(max_length=2000)
    stream: bool = True


# ---------------------------------------------------------------- views

def session_response(tokens: Tokens, user: User | None = None, status_code: int = 200) -> JSONResponse:
    body: dict[str, Any] = {"access_token": tokens.access_token, "token_type": "Bearer", "expires_in": tokens.expires_in}
    if tokens.refresh_token:
        body["refresh_token"] = tokens.refresh_token
    if user is not None:
        body["user"] = {"name": user.name, "email": user.email}
    return JSONResponse(body, status_code=status_code, headers={"Cache-Control": "no-store"})


def user_view(user: Any, usage: Any) -> dict[str, Any]:
    limits = user.limits
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "plan": user.plan,
        "usage": {
            "period_start": usage.period_start,
            "pages_read": usage.pages_read,
            "pages_limit": limits["pages_limit"],
            "answers": usage.answers,
            "answers_limit": limits["answers_limit"],
        },
        "created_at": user.created_at,
    }


def assistant_view(s: AssistantSummary) -> dict[str, Any]:
    a = s.assistant
    return {
        "id": a.id,
        "label": a.label,
        "name": a.name,
        "fallback_contact": a.fallback_contact,
        "status": s.status,
        "published": a.published,
        "document_count": s.document_count,
        "pending_changes": s.pending_changes,
        "content_version": a.content_version,
        "processing": s.processing,
        "channels": [],
        "widget_origins": a.widget_origins,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def document_view(doc: Document, counts: PassageCounts | None) -> dict[str, Any]:
    return {
        "id": doc.id,
        "assistant_id": doc.assistant_id,
        "filename": doc.filename,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "status": doc.status,
        "progress": doc.progress,
        "enabled": doc.enabled,
        "edit_version": doc.edit_version,
        "pending_changes": counts.pending_changes if counts else 0,
        "warning_count": counts.warnings if counts else 0,
        "error": doc.error,
        "last_embedded_at": doc.last_embedded_at,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def passage_view(p: Passage, pending: set[str]) -> dict[str, Any]:
    return {
        "id": p.id,
        "label": p.label,
        "document_id": p.document_id,
        "text": p.text,
        "original_text": p.original_text,
        "origin": p.origin,
        "source": p.source.to_dict(),
        "warnings": [{"code": w.code, "message": w.message} for w in p.warnings],
        "token_count": p.token_count,
        "embedded": p.id not in pending,
        "context": p.context,
        "updated_at": p.updated_at,
    }


def _etag(body: Any) -> str:
    return '"' + hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16] + '"'


def _if_match(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip().strip('W/').strip('"'))
    except ValueError as exc:
        raise ValidationError("If-Match must be the document's edit_version") from exc


# ---------------------------------------------------------------- app

def create_app(c: Container, *, api: bool = True, qa: bool = True) -> FastAPI:
    app = FastAPI(title="RAGcat", version="1", docs_url="/v1/docs", openapi_url="/v1/openapi.json")

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = {"fields": [{"loc": list(e["loc"]), "message": e["msg"]} for e in exc.errors()]}
        return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": "Invalid request", "details": details}}, status_code=400)

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def owner(authorization: str | None = Header(default=None)) -> Principal:
        principal = c.verifier.verify(authorization)
        c.identity.ensure(principal)
        return principal

    router = APIRouter(prefix="/v1")

    if api:
        # -------------------------------------------------------- users

        @router.get("/me")
        def me(p: Principal = Depends(owner)) -> dict[str, Any]:
            return user_view(*c.identity.me(p.sub))

        @router.patch("/me")
        def update_me(body: UpdateMe, p: Principal = Depends(owner)) -> dict[str, Any]:
            c.identity.rename(p.sub, body.name)
            return user_view(*c.identity.me(p.sub))

        # -------------------------------------------------------- password sign-in (Cognito)

        @router.post("/auth/signup")
        def sign_up(body: Credentials) -> JSONResponse:
            return session_response(*c.identity.sign_up(body.email, body.password), status_code=201)

        @router.post("/auth/login")
        def sign_in(body: Credentials) -> JSONResponse:
            return session_response(*c.identity.sign_in(body.email, body.password))

        @router.post("/auth/refresh")
        def refresh(body: RefreshToken) -> JSONResponse:
            return session_response(c.identity.refresh(body.refresh_token))

        @router.post("/auth/logout", status_code=204)
        def sign_out(body: RefreshToken) -> Response:
            c.identity.sign_out(body.refresh_token)
            return Response(status_code=204)

        # -------------------------------------------------------- assistants

        @router.get("/assistants")
        def list_assistants(p: Principal = Depends(owner)) -> dict[str, Any]:
            return {"items": [assistant_view(s) for s in c.assistants.list(p.sub)], "next_cursor": None}

        @router.post("/assistants", status_code=201)
        def create_assistant(body: CreateAssistant, p: Principal = Depends(owner)) -> dict[str, Any]:
            a = c.assistants.create(p.sub, body.name, body.fallback_contact)
            return assistant_view(c.assistants.summarize(a))

        @router.get("/assistants/{aid}")
        def get_assistant(aid: str, p: Principal = Depends(owner)) -> dict[str, Any]:
            return assistant_view(c.assistants.summarize(c.assistants.get(p.sub, aid)))

        @router.patch("/assistants/{aid}")
        def update_assistant(aid: str, body: UpdateAssistant, p: Principal = Depends(owner)) -> dict[str, Any]:
            a = c.assistants.update(
                p.sub, aid, name=body.name, fallback_contact=body.fallback_contact, published=body.published, widget_origins=body.widget_origins
            )
            return assistant_view(c.assistants.summarize(a))

        # -------------------------------------------------------- website widget (public, api-design.md §7)

        widget_page = WidgetPage(c.settings.widget_template_url)

        @router.get("/widget/{aid}/frame", response_class=HTMLResponse)
        def widget_frame(aid: str) -> HTMLResponse:
            try:
                config: AssistantConfig | None = c.assistants.config(aid)
            except NotFound:
                config = None
            body, headers = widget_page.render(aid, config)
            return HTMLResponse(body, status_code=200 if config else 404, headers=headers)

        # -------------------------------------------------------- documents

        @router.get("/assistants/{aid}/documents")
        def list_documents(aid: str, p: Principal = Depends(owner)) -> dict[str, Any]:
            c.assistants.get(p.sub, aid)
            docs = c.curation.documents(p.sub, aid)
            return {"items": [document_view(d, c.curation.counts(d.id)) for d in docs], "next_cursor": None}

        @router.post("/assistants/{aid}/documents", status_code=201)
        def create_document(aid: str, body: CreateDocument, p: Principal = Depends(owner)) -> dict[str, Any]:
            c.assistants.get(p.sub, aid)
            doc, upload = c.curation.create_document(p.sub, aid, body.filename, body.size_bytes, body.content_type)
            return {"document": document_view(doc, None), "upload": upload}

        @router.get("/documents/{did}")
        def get_document(did: str, request: Request, p: Principal = Depends(owner)) -> Response:
            doc = c.curation.document(p.sub, did)
            body = document_view(doc, c.curation.counts(did))
            etag = _etag(body)
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=304, headers={"ETag": etag})
            return JSONResponse(body, headers={"ETag": etag, "Cache-Control": "no-cache"})

        @router.patch("/documents/{did}")
        def update_document(did: str, body: UpdateDocument, p: Principal = Depends(owner)) -> dict[str, Any]:
            doc = c.curation.set_enabled(p.sub, did, body.enabled)
            return document_view(doc, c.curation.counts(did))

        @router.delete("/documents/{did}", status_code=202)
        def delete_document(did: str, p: Principal = Depends(owner)) -> dict[str, Any]:
            c.curation.delete(p.sub, did)
            return {"document": {"id": did, "status": "deleting"}}

        @router.post("/documents/{did}/cancel")
        def cancel_document(did: str, p: Principal = Depends(owner)) -> dict[str, Any]:
            return document_view(c.curation.cancel(p.sub, did), None)

        @router.get("/documents/{did}/pages")
        def pages(did: str, from_: int = Query(1, alias="from", ge=1), to: int | None = Query(None), p: Principal = Depends(owner)) -> dict[str, Any]:
            doc = c.curation.document(p.sub, did)
            last = min(to or doc.page_count or 0, doc.page_count or 0, from_ + 49)
            items = []
            for n in range(from_, last + 1):
                width, height = doc.page_sizes[n - 1] if n <= len(doc.page_sizes) else (595.0, 842.0)
                items.append({"page": n, "width_pt": width, "height_pt": height, "image_url": c.store.url_for(f"pages/{did}/{n}.jpg")})
            return {"items": items}

        @router.get("/jobs")
        def jobs(state: Literal["active"] = "active", p: Principal = Depends(owner)) -> dict[str, Any]:
            items = []
            for s in c.assistants.list(p.sub):
                for d in c.curation.documents(p.sub, s.assistant.id):
                    if d.status in ("parsing", "embedding"):
                        kind = "parse" if d.status == "parsing" else "embed"
                        items.append({"type": kind, "assistant_id": d.assistant_id, "document_id": d.id, "filename": d.filename, "progress": d.progress})
            return {"items": items}

        # -------------------------------------------------------- chunks (passages)

        def change_set(changes: ChangeSet, doc: Document) -> JSONResponse:
            _, _, counts, pending = c.curation.passages(doc.owner_id, doc.id)
            body = {
                "edit_version": doc.edit_version,
                "upserted": [passage_view(x, pending) for x in changes.upserted],
                "deleted": changes.deleted,
                "document": {"status": doc.status, "warning_count": counts.warnings, "pending_changes": counts.pending_changes},
            }
            return JSONResponse(body, headers={"ETag": f'"{doc.edit_version}"'})

        @router.get("/documents/{did}/chunks")
        def list_chunks(did: str, filter: Literal["all", "warnings", "edited", "pending"] = "all", p: Principal = Depends(owner)) -> JSONResponse:
            doc, passages, counts, pending = c.curation.passages(p.sub, did)
            keep = {
                "all": lambda x: True,
                "warnings": lambda x: bool(x.warnings),
                "edited": lambda x: x.origin != "auto",
                "pending": lambda x: x.id in pending,
            }[filter]
            body = {
                "items": [passage_view(x, pending) for x in passages if keep(x)],
                "next_cursor": None,
                "edit_version": doc.edit_version,
                "counts": counts.to_dict(),
            }
            return JSONResponse(body, headers={"ETag": f'"{doc.edit_version}"'})

        @router.post("/documents/{did}/chunks", status_code=201)
        def add_chunk(did: str, body: AddChunk, p: Principal = Depends(owner), if_match: str | None = Header(default=None)) -> JSONResponse:
            changes, doc, _ = c.curation.edit(p.sub, did, _if_match(if_match), lambda e: e.add(body.after_id, body.text, body.page))
            response = change_set(changes, doc)
            response.status_code = 201
            return response

        @router.patch("/documents/{did}/chunks/{cid}")
        def edit_chunk(did: str, cid: str, body: EditChunk, p: Principal = Depends(owner), if_match: str | None = Header(default=None)) -> JSONResponse:
            changes, doc, _ = c.curation.edit(p.sub, did, _if_match(if_match), lambda e: e.edit(cid, body.text))
            return change_set(changes, doc)

        @router.delete("/documents/{did}/chunks/{cid}")
        def delete_chunk(did: str, cid: str, p: Principal = Depends(owner), if_match: str | None = Header(default=None)) -> JSONResponse:
            changes, doc, _ = c.curation.edit(p.sub, did, _if_match(if_match), lambda e: e.delete(cid))
            return change_set(changes, doc)

        @router.post("/documents/{did}/chunks/merge")
        def merge_chunks(did: str, body: MergeChunks, p: Principal = Depends(owner), if_match: str | None = Header(default=None)) -> JSONResponse:
            changes, doc, _ = c.curation.edit(p.sub, did, _if_match(if_match), lambda e: e.merge(body.ids, body.separator))
            return change_set(changes, doc)

        @router.post("/documents/{did}/chunks/{cid}/split")
        def split_chunk(did: str, cid: str, body: SplitChunk, p: Principal = Depends(owner), if_match: str | None = Header(default=None)) -> JSONResponse:
            changes, doc, _ = c.curation.edit(p.sub, did, _if_match(if_match), lambda e: e.split(cid, body.parts))
            return change_set(changes, doc)

        @router.post("/documents/{did}/chunks/{cid}/restore")
        def restore_chunk(did: str, cid: str, p: Principal = Depends(owner), if_match: str | None = Header(default=None)) -> JSONResponse:
            changes, doc, _ = c.curation.edit(p.sub, did, _if_match(if_match), lambda e: e.restore(cid))
            return change_set(changes, doc)

        @router.post("/documents/{did}/embed", status_code=202)
        def embed(did: str, p: Principal = Depends(owner)) -> dict[str, Any]:
            job = c.curation.request_embed(p.sub, did)
            return {"job": job, "document": {"status": "embedding"}}

    if qa:

        @router.post("/assistants/{aid}/ask")
        def ask(aid: str, body: Ask, p: Principal = Depends(owner)) -> Response:
            events = c.answering.ask(Caller("owner", p.sub), aid, body.question, preview=body.preview)
            if not body.stream:
                return JSONResponse(collect(events))
            return StreamingResponse(_sse(events), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

        @router.post("/widget/{aid}/ask")
        def widget_ask(aid: str, body: WidgetAsk, request: Request) -> Response:
            wait = fixed_window(c.cache, f"rl:w:{aid}:{visitor_ip(request)}", WIDGET_ASKS_PER_MINUTE, 60, _now())
            if wait:
                error = {"code": "RATE_LIMITED", "message": "Too many questions. Try again shortly.", "details": {"retry_after": wait}}
                return JSONResponse({"error": error}, status_code=429, headers={"Retry-After": str(wait)})
            events = public_events(c.answering.ask(Caller("widget"), aid, body.question))
            if not body.stream:
                return JSONResponse(collect(events))
            return StreamingResponse(_sse(events), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.include_router(router)
    return app


def _sse(events: Iterator[tuple[str, dict[str, Any]]]) -> Iterator[str]:
    for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data)}\n\n"
