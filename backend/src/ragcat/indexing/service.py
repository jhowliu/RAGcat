"""Indexing application service: the reconcile job behind POST /documents/{id}/embed, and the
preview vectors an owner's test uses for passages that are not published yet."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterator

from ragcat.assistants.service import AssistantsService
from ragcat.curation.domain import Document, Passage
from ragcat.curation.service import CurationService
from ragcat.indexing.adapters import PassageIndexState
from ragcat.indexing.domain import PassageContext, PassageState, Put, context_prompt, embedding_input, parse_context, plan_reconcile
from ragcat.infra.cache import Cache, get_json, set_json
from ragcat.infra.models import Embedder, Llm
from ragcat.infra.storage import ObjectStore
from ragcat.infra.vectors import VectorIndex, VectorItem
from ragcat.shared.errors import InvalidState, UpstreamUnavailable
from ragcat.shared.kernel import VectorSpec

log = logging.getLogger("ragcat.indexing")

BATCH = 16
CONTEXT_CONCURRENCY = 4
CONTEXT_MAX_TOKENS = 1000
PREVIEW_LIMIT = 100  # passages one test may prepare while the owner waits; more is a job for Publish
PREVIEW_TTL = 7 * 24 * 3600
PREVIEW_STATUSES = ("review", "embedding", "ready")  # documents whose passages can answer


@dataclass(frozen=True)
class Prepared:
    """A passage's context and vector. Cached under the passage hash, so Publish writes exactly
    what a test prepared instead of paying for it again."""

    context: PassageContext
    vector: list[float]

    def to_dict(self) -> dict[str, Any]:
        return {"context": self.context.text, "entities": [list(e) for e in self.context.entities], "vector": self.vector}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Prepared:
        return Prepared(PassageContext(d["context"], tuple((kind, name) for kind, name in d["entities"])), d["vector"])


@dataclass
class PreviewPlan:
    """What an owner's test searches: the live index minus `stale` (vectors whose passage has
    changed or been removed) plus `items`, a vector for every changed passage. `todo` holds the
    passages prepare_preview still has to embed."""

    stale: set[str] = field(default_factory=set)
    items: list[VectorItem] = field(default_factory=list)
    todo: list[tuple[Document, Passage, Put]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.stale or self.items or self.todo)


class IndexingService:
    def __init__(
        self,
        state: PassageIndexState,
        curation: CurationService,
        assistants: AssistantsService,
        embedder: Embedder,
        llm: Llm,
        vectors: VectorIndex,
        store: ObjectStore,
        spec: VectorSpec,
        *,
        cache: Cache,
    ) -> None:
        self.state = state
        self.curation = curation
        self.assistants = assistants
        self.embedder = embedder
        self.llm = llm
        self.vectors = vectors
        self.store = store
        self.spec = spec
        self.cache = cache

    def reconcile(self, did: str) -> None:
        doc = self.curation.get_for_system(did)
        if doc is None or doc.status not in ("embedding", "deleting"):
            log.info("Skipping reconcile for %s (status %s)", did, doc.status if doc else "missing")
            return
        try:
            self._reconcile(did, doc)
        except UpstreamUnavailable as exc:
            # Work done so far is kept (embedded_hash per passage), so the next embed resumes.
            log.warning("Embedding %s failed: %s", did, exc.message)
            if doc.status == "embedding":
                self.curation.embedding_failed(did, f"{exc.message}. Embedded passages were kept; try again.")
            else:
                raise  # deletion must finish: let the queue retry

    def _reconcile(self, did: str, doc: Document) -> None:
        deleting = doc.status == "deleting"
        passages = sorted(self.curation.all_passages(did), key=lambda p: p.position)
        plan = plan_reconcile([PassageState(p.id, p.text, p.deleted, p.embedded_hash) for p in passages], self.spec, document_deleting=deleting)
        by_id = {p.id: p for p in passages}
        done = 0
        self.curation.report_embed_progress(did, done, plan.work)

        if plan.deletes:
            self.vectors.delete(plan.deletes)
            done += len(plan.deletes)
        for pid in plan.purges:
            self.state.purge(did, pid)

        for start in range(0, len(plan.puts), BATCH):
            batch = plan.puts[start : start + BATCH]
            prepared = self._prepare(_title(doc), batch)
            self.vectors.put([self._item(doc, by_id[put.passage.id], put, p) for put, p in zip(batch, prepared)])
            for put, p in zip(batch, prepared):
                self.state.mark_embedded(did, put.passage.id, put.hash, p.context.text)
            done += len(batch)
            self.curation.report_embed_progress(did, done, plan.work)

        if deleting:
            self.curation.delete_rows(did)
            self.store.delete_prefix(f"pages/{did}/")
            self.store.delete(doc.object_key)
        else:
            self.curation.finish_embedding(did)
        if plan.work:
            self.assistants.content_changed(doc.assistant_id)

    # ------------------------------------------------------------ preview for an owner's test

    def plan_preview(self, aid: str, excluded: set[str]) -> PreviewPlan:
        """Compare every answering document's passages with the live index, the way reconcile
        would. Raises InvalidState when more passages need embedding than a test should wait for."""
        plan = PreviewPlan()
        for doc in self.curation.documents_for_system(aid):
            if doc.id in excluded or not doc.enabled or doc.status not in PREVIEW_STATUSES:
                continue
            passages = sorted(self.curation.all_passages(doc.id), key=lambda p: p.position)
            by_id = {p.id: p for p in passages}
            changes = plan_reconcile([PassageState(p.id, p.text, p.deleted, p.embedded_hash) for p in passages], self.spec)
            plan.stale.update(changes.deletes)
            for put in changes.puts:
                if put.passage.embedded_hash is not None:
                    plan.stale.add(put.passage.id)
                cached = self._cached(put)
                if cached is None:
                    plan.todo.append((doc, by_id[put.passage.id], put))
                else:
                    plan.items.append(self._item(doc, by_id[put.passage.id], put, cached))
        if len(plan.todo) > PREVIEW_LIMIT:
            raise InvalidState(
                f"{len(plan.todo)} changed Passages are too many to test before publishing (the limit is {PREVIEW_LIMIT}). Publish changes to test them.",
                code="TOO_MANY_CHANGES",
                details={"passages": len(plan.todo), "limit": PREVIEW_LIMIT},
            )
        return plan

    def prepare_preview(self, plan: PreviewPlan) -> Iterator[tuple[int, int]]:
        """Embed plan.todo BATCH at a time, yielding (done, total). Nothing goes into the vector
        index: the vectors are cached for the next test and for Publish."""
        todo, total = plan.todo, len(plan.todo)
        if not total:
            return
        yield 0, total
        for start in range(0, total, BATCH):
            batch = todo[start : start + BATCH]
            prepared = self._compute([(_title(doc), put) for doc, _, put in batch])
            for (doc, passage, put), p in zip(batch, prepared):
                set_json(self.cache, _preview_key(put), p.to_dict(), PREVIEW_TTL)
                plan.items.append(self._item(doc, passage, put, p))
            yield start + len(batch), total
        plan.todo = []

    # ------------------------------------------------------------ shared by reconcile and preview

    def _prepare(self, title: str, puts: list[Put]) -> list[Prepared]:
        """Reuse what a test already prepared for these exact passages; compute the rest."""
        cached = [self._cached(put) for put in puts]
        computed = iter(self._compute([(title, put) for put, c in zip(puts, cached) if c is None]))
        return [c if c is not None else next(computed) for c in cached]

    def _cached(self, put: Put) -> Prepared | None:
        data = get_json(self.cache, _preview_key(put))
        return Prepared.from_dict(data) if data else None

    def _compute(self, work: list[tuple[str, Put]]) -> list[Prepared]:
        """(document title, put) pairs → context and vector."""
        if not work:
            return []
        contexts = self._contexts(work) if self.spec.contextual else [PassageContext()] * len(work)
        vectors = self.embedder.embed([embedding_input(ctx, put.passage.text) for (_, put), ctx in zip(work, contexts)])
        return [Prepared(ctx, vector) for ctx, vector in zip(contexts, vectors)]

    def _item(self, doc: Document, passage: Passage, put: Put, prepared: Prepared) -> VectorItem:
        context = prepared.context
        return VectorItem(
            key=passage.id,
            vector=prepared.vector,
            metadata={
                "embedding_key": self.spec.model,
                "assistant_id": doc.assistant_id,
                "document_id": doc.id,
                "document_title": doc.filename,
                "label": passage.label,
                "text": put.passage.text,
                "section": put.section,
                "context": context.text,
                "page": passage.source.page_start,
                "para": passage.source.para_start or 0,
                "boxes": json.dumps([b.to_dict() for b in passage.source.boxes]),
                "edited": passage.origin != "auto",
                **({"entities": context.tags} if context.entities else {}),  # filterable list of "type:name"
            },
        )

    def _contexts(self, work: list[tuple[str, Put]]) -> list[PassageContext]:
        """One LLM call per passage, a few at a time (Bedrock on-demand quotas are small)."""
        prompts = [context_prompt(title, put.section, put.passage.text) for title, put in work]
        with ThreadPoolExecutor(max_workers=CONTEXT_CONCURRENCY) as pool:
            replies = list(pool.map(lambda p: self.llm.complete(p, CONTEXT_MAX_TOKENS), prompts))
        return [self._parse(reply) for reply in replies]

    @staticmethod
    def _parse(reply: str) -> PassageContext:
        try:
            return parse_context(reply)
        except ValueError:  # includes JSONDecodeError. Context only helps search: embed the bare passage rather than fail the document.
            log.warning("Context reply was not the JSON asked for; embedding without context: %.200s", reply)
            return PassageContext()


def _title(doc: Document) -> str:
    return doc.filename.removesuffix(".pdf")


def _preview_key(put: Put) -> str:
    # put.hash covers the embedding space, context prompt and model, section and text.
    return f"pv:{put.passage.id}:{put.hash}"
