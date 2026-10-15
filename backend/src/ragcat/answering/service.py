"""Answering application service: retrieve → generate → cite, as a stream of SSE-shaped events."""

from __future__ import annotations

import time
import json
import logging
from typing import Any, Iterator

from ragcat.answering.domain import (
    MAX_QUESTION,
    NO_ANSWER,
    Caller,
    build_prompt,
    citations_for,
    fallback,
    merge_preview,
    normalize,
    question_hash,
)
from ragcat.assistants.service import AssistantsService
from ragcat.identity.service import IdentityService
from ragcat.indexing.service import IndexingService, PreviewPlan
from ragcat.infra.cache import Cache, get_json, set_json
from ragcat.infra.models import Embedder, Llm
from ragcat.infra.vectors import Hit, VectorIndex, cosine
from ragcat.shared.errors import AppError, Forbidden, NotFound, NotPublished, UpstreamUnavailable, ValidationError
from ragcat.shared.ids import new_id

TOP_K = 5
LIVE_FETCH_MAX = 100  # one S3 Vectors QueryVectors page
ANSWER_TTL = 24 * 3600
QUERY_VECTOR_TTL = 7 * 24 * 3600
log = logging.getLogger("ragcat.answering")

Event = tuple[str, dict[str, Any]]


class AnsweringService:
    def __init__(
        self,
        assistants: AssistantsService,
        identity: IdentityService,
        embedder: Embedder,
        llm: Llm,
        vectors: VectorIndex,
        cache: Cache,
        embedding_key: str,
        *,
        answering_key: str | None = None,
        indexing: IndexingService | None = None,
    ) -> None:
        self.assistants = assistants
        self.identity = identity
        self.embedder = embedder
        self.llm = llm
        self.vectors = vectors
        self.cache = cache
        self.embedding_key = embedding_key
        self.answering_key = answering_key if answering_key is not None else embedding_key
        self.indexing = indexing  # previews unpublished edits for the owner's tests

    def ask(self, caller: Caller, aid: str, question: str, *, preview: bool = False) -> Iterator[Event]:
        """Validates eagerly (errors raise before streaming starts), then yields events. With
        `preview` the owner's unpublished edits answer too, without reaching the vector index."""
        q = normalize(question)
        if not q or len(q) > MAX_QUESTION:
            raise ValidationError(f"Question must be 1–{MAX_QUESTION} characters")
        config = self.assistants.config(aid)
        if caller.kind == "owner":
            if config.owner_id != caller.owner_id:
                raise NotFound("Assistant not found")
        elif not config.published:
            raise NotPublished("This Assistant is not published")
        elif caller.kind == "widget" and not config.widget_on:
            raise NotPublished("This Assistant is not on any website")
        self.identity.check_answers(config.owner_id)
        plan = None
        if preview:
            if caller.kind != "owner":
                raise Forbidden("Only the owner can test unpublished edits")
            if self.indexing is None:
                raise RuntimeError("Previews need the indexing service")
            plan = self.indexing.plan_preview(config.id, set(config.excluded_document_ids))
        # With nothing unpublished a preview is the live answer, and may come from the cache.
        return self._answer(config, q, None if plan is None or plan.empty else plan)

    def _answer(self, config: Any, q: str, plan: PreviewPlan | None) -> Iterator[Event]:
        started = time.monotonic()
        request_id = new_id("req")
        qhash = question_hash(q)
        answer_key = f"ans:{self.answering_key}:{config.id}:{config.content_version}:{qhash}"
        cached = get_json(self.cache, answer_key) if plan is None else None
        yield "meta", {"request_id": request_id, "content_version": config.content_version, "cached": cached is not None, "preview": plan is not None}
        if cached is not None:
            if cached["answer"]:
                yield "token", {"text": cached["answer"]}
            yield "citations", {"items": cached["citations"]}
            latency = _ms(started)
            _completed(request_id, config.id, True, cached["answered"], latency)
            yield "done", {"answered": cached["answered"], "fallback": cached["fallback"], "usage": {"input_tokens": 0, "output_tokens": 0}, "latency_ms": latency}
            return

        try:
            if plan is not None:
                assert self.indexing is not None
                for done, total in self.indexing.prepare_preview(plan):
                    yield "preparing", {"done": done, "total": total}
            vector = self._query_vector(q, qhash)
            hits = self._retrieve(config, vector, plan)
            answer, usage = "", {"input_tokens": 0, "output_tokens": 0}
            if hits:
                system, prompt = build_prompt(config.name, q, hits)
                stream = self.llm.stream(system, prompt)
                buffer, decided = "", False
                for delta in stream:
                    answer += delta
                    if decided:
                        yield "token", {"text": delta}
                        continue
                    buffer += delta
                    # Hold back the first characters until we know this is not the NO_ANSWER sentinel.
                    if len(buffer.strip()) >= len(NO_ANSWER) or not NO_ANSWER.startswith(buffer.strip()):
                        decided = True
                        if not buffer.strip().startswith(NO_ANSWER):
                            yield "token", {"text": buffer}
                if not decided and buffer.strip() and not NO_ANSWER.startswith(buffer.strip()):
                    yield "token", {"text": buffer}
                usage = {"input_tokens": stream.usage.input_tokens, "output_tokens": stream.usage.output_tokens}
            answer = answer.strip()
            answered = bool(answer) and not answer.startswith(NO_ANSWER)
            citations = [c.to_dict() for c in citations_for(answer, hits)] if answered else []
            if answered and not citations:
                answered = False  # an answer that cites nothing is not grounded
            result = {
                "answer": answer if answered else "",
                "answered": answered,
                "citations": citations,
                "fallback": None if answered else fallback(config.fallback_contact),
            }
        except AppError as exc:
            yield "error", {"code": exc.code, "message": exc.message}
            return
        if plan is None:  # a preview answer depends on edits that may change again
            set_json(self.cache, answer_key, result, ANSWER_TTL)
        self.identity.add_answer(config.owner_id)
        yield "citations", {"items": result["citations"]}
        latency = _ms(started)
        _completed(request_id, config.id, False, result["answered"], latency)
        yield "done", {"answered": result["answered"], "fallback": result["fallback"], "usage": usage, "latency_ms": latency}

    def _retrieve(self, config: Any, vector: list[float], plan: PreviewPlan | None) -> list[Hit]:
        excluded = list(config.excluded_document_ids)
        if plan is None:
            return self.vectors.query(vector, TOP_K, config.id, excluded)
        # Fetch extra live hits so dropping the stale ones still leaves TOP_K to choose from.
        live = self.vectors.query(vector, min(TOP_K + len(plan.stale), LIVE_FETCH_MAX), config.id, excluded)
        return merge_preview(live, plan.stale, [Hit(i.key, cosine(vector, i.vector), i.metadata) for i in plan.items], TOP_K)

    def _query_vector(self, q: str, qhash: str) -> list[float]:
        key = f"qemb:{self.embedding_key}:{qhash}"
        cached = get_json(self.cache, key)
        if cached is not None:
            return cached
        vector = self.embedder.embed([q])[0]
        set_json(self.cache, key, vector, QUERY_VECTOR_TTL)
        return vector


def collect(events: Iterator[Event]) -> dict[str, Any]:
    """Fold the event stream into the `stream: false` JSON response."""
    out: dict[str, Any] = {"answer": "", "citations": [], "answered": False, "fallback": None}
    for name, data in events:
        if name == "meta":
            out.update(request_id=data["request_id"], content_version=data["content_version"], cached=data["cached"], preview=data["preview"])
        elif name == "token":
            out["answer"] += data["text"]
        elif name == "citations":
            out["citations"] = data["items"]
        elif name == "done":
            out.update(answered=data["answered"], fallback=data["fallback"])
        elif name == "error":
            error = UpstreamUnavailable if data["code"] == UpstreamUnavailable.code else AppError
            raise error(data["message"], code=data["code"])
    out["answer"] = out["answer"].strip()
    return out


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _completed(request_id: str, assistant_id: str, cached: bool, answered: bool, latency_ms: int) -> None:
    # CloudWatch metric filters consume this JSON; exclude questions, answers and tokens.
    log.info(json.dumps({"event": "answer_completed", "request_id": request_id, "assistant_id": assistant_id, "cached": cached, "answered": answered, "latency_ms": latency_ms}))
