"""Curation application service: the public API other contexts and the HTTP layer call."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Protocol

from ragcat.curation.adapters import DynamoCurationRepo
from ragcat.curation.domain import (
    STEP,
    Box,
    ChangeSet,
    Document,
    Passage,
    PassageCounts,
    PassageEditor,
    Source,
    count_passages,
    pending_ids,
)
from ragcat.infra.queue import MessageQueue
from ragcat.infra.storage import ObjectStore
from ragcat.shared.errors import (
    InvalidState,
    NoChanges,
    NotFound,
    PreconditionFailed,
    PreconditionRequired,
    ValidationError,
)
from ragcat.shared.ids import new_id
from ragcat.shared.kernel import VectorSpec, now_iso

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Value objects that are part of Curation's public contract (used by Ingestion).
__all__ = ["Box", "Source", "ImportedPassage", "Cancelled", "CurationService", "DocumentSummary"]


class Cancelled(Exception):
    """The document left the parsing state (cancelled or deleted); ingestion should stop."""


@dataclass(frozen=True)
class ImportedPassage:
    """What Ingestion hands to Curation (customer–supplier contract, domain-design.md §4)."""

    text: str
    source: Source


class VisibilityHooks(Protocol):
    def document_visibility_changed(self, assistant_id: str, document_id: str, visible: bool) -> None: ...


@dataclass(frozen=True)
class DocumentSummary:
    """Read model handed to Assistants & Access for list cards and the publish check."""

    id: str
    filename: str
    status: str
    progress: dict[str, Any] | None
    pending_changes: int
    has_embedded: bool
    updated_at: str


class CurationService:
    def __init__(
        self,
        repo: DynamoCurationRepo,
        store: ObjectStore,
        queue: MessageQueue,
        hooks: VisibilityHooks,
        spec: VectorSpec,
        clock: Callable[[], str] = now_iso,
    ) -> None:
        self.repo = repo
        self.store = store
        self.queue = queue
        self.hooks = hooks
        self.spec = spec
        self.now = clock

    # ------------------------------------------------------------ owner-facing

    def create_document(self, owner_id: str, assistant_id: str, filename: str, size_bytes: int, content_type: str) -> tuple[Document, dict[str, Any]]:
        if content_type != "application/pdf" or not filename.lower().endswith(".pdf"):
            raise ValidationError("Only PDF files can be uploaded")
        if not 0 < size_bytes <= MAX_UPLOAD_BYTES:
            raise ValidationError("PDF must be between 1 byte and 50 MB")
        did = new_id("doc")
        now = self.now()
        doc = Document(
            id=did,
            assistant_id=assistant_id,
            owner_id=owner_id,
            filename=filename[:200],
            size_bytes=size_bytes,
            object_key=f"uploads/{assistant_id}/{did}.pdf",
            created_at=now,
            updated_at=now,
        )
        self.repo.add_document(doc)
        return doc, self.store.presign_upload(doc.object_key, content_type, MAX_UPLOAD_BYTES)

    def documents(self, owner_id: str, assistant_id: str) -> list[Document]:
        docs = [d for d in self.repo.list_documents(assistant_id) if d.owner_id == owner_id and d.status != "deleting"]
        return sorted(docs, key=lambda d: d.created_at)

    def document(self, owner_id: str, did: str) -> Document:
        doc = self.repo.get_document(did)
        if doc is None or doc.owner_id != owner_id or doc.status == "deleting":
            raise NotFound("Document not found")
        return doc

    def counts(self, did: str) -> PassageCounts:
        return count_passages(self.repo.load_passages(did), self.spec)

    def passages(self, owner_id: str, did: str) -> tuple[Document, list[Passage], PassageCounts, set[str]]:
        """Visible passages in order, their counts, and the ids of those not embedded yet."""
        doc = self.document(owner_id, did)
        all_passages = self.repo.load_passages(did)
        visible = sorted((p for p in all_passages if not p.deleted), key=lambda p: p.position)
        return doc, visible, count_passages(all_passages, self.spec), pending_ids(all_passages, self.spec)

    def edit(self, owner_id: str, did: str, if_match: int | None, apply: Callable[[PassageEditor], Any]) -> tuple[ChangeSet, Document, Any]:
        """Run one edit operation against the aggregate with optimistic locking."""
        if if_match is None:
            raise PreconditionRequired("Send If-Match with the document's edit_version")
        doc = self.document(owner_id, did)
        if doc.edit_version != if_match:
            raise PreconditionFailed("The document has changed", details={"current_edit_version": doc.edit_version})
        editor = PassageEditor(doc, self.repo.load_passages(did), self.now())
        result = apply(editor)
        changes = editor.commit()
        if changes.empty:
            return changes, doc, result
        if not self.repo.save_edit(doc, if_match, changes.writes, changes.removals):
            current = self.repo.get_document(did)
            raise PreconditionFailed("The document has changed", details={"current_edit_version": current.edit_version if current else None})
        return changes, doc, result

    def request_embed(self, owner_id: str, did: str) -> dict[str, Any]:
        doc = self.document(owner_id, did)
        if doc.status == "embedding" and doc.job_id:
            return {"id": doc.job_id, "type": "reconcile", "document_id": did}
        if doc.status not in ("review", "ready"):
            raise InvalidState(f"Document is {doc.status}")
        if self.counts(did).pending_changes == 0:
            raise NoChanges("Nothing to embed")
        job_id = new_id("job")
        progress = {"stage": "embedding", "done": 0, "total": 0, "started_at": self.now()}
        if not self.repo.update_document(did, {"status": "embedding", "job_id": job_id, "progress": progress, "error": None, "updated_at": self.now()}, expect_status=("review", "ready")):
            raise InvalidState("Document changed state; try again")
        self.queue.send("embed", {"type": "reconcile", "job_id": job_id, "document_id": did})
        return {"id": job_id, "type": "reconcile", "document_id": did}

    def cancel(self, owner_id: str, did: str) -> Document:
        self.document(owner_id, did)
        if not self.repo.update_document(did, {"status": "cancelled", "progress": None, "updated_at": self.now()}, expect_status=("awaiting_upload", "parsing")):
            raise InvalidState("Only uploads and parsing can be cancelled")
        return self.document(owner_id, did)

    def delete(self, owner_id: str, did: str) -> None:
        doc = self.document(owner_id, did)
        self.repo.update_document(did, {"status": "deleting", "progress": None, "updated_at": self.now()})
        self.hooks.document_visibility_changed(doc.assistant_id, did, visible=False)
        self.queue.send("embed", {"type": "reconcile", "job_id": new_id("job"), "document_id": did})

    def set_enabled(self, owner_id: str, did: str, enabled: bool) -> Document:
        doc = self.document(owner_id, did)
        if doc.enabled != enabled:
            self.repo.update_document(did, {"enabled": enabled, "updated_at": self.now()})
            self.hooks.document_visibility_changed(doc.assistant_id, did, visible=enabled)
        return self.document(owner_id, did)

    def summaries(self, assistant_id: str) -> list[DocumentSummary]:
        out = []
        for doc in self.repo.list_documents(assistant_id):
            if doc.status == "deleting":
                continue
            pending = self.counts(doc.id).pending_changes if doc.status in ("review", "ready", "embedding") else 0
            out.append(DocumentSummary(doc.id, doc.filename, doc.status, doc.progress, pending, doc.last_embedded_at is not None, doc.updated_at))
        return out

    # ------------------------------------------------------------ ingestion-facing

    def get_for_system(self, did: str) -> Document | None:
        return self.repo.get_document(did)

    def documents_for_system(self, assistant_id: str) -> list[Document]:
        return [d for d in self.repo.list_documents(assistant_id) if d.status != "deleting"]

    def all_passages(self, did: str) -> list[Passage]:
        """Every row including soft-deleted ones (Indexing needs them to delete vectors)."""
        return self.repo.load_passages(did)

    def start_parsing(self, did: str) -> Document | None:
        """awaiting_upload → parsing. Returns None if another delivery already started it."""
        progress = {"stage": "checking_file", "done": 0, "total": 0, "started_at": self.now()}
        if not self.repo.update_document(did, {"status": "parsing", "progress": progress, "error": None, "updated_at": self.now()}, expect_status=("awaiting_upload",)):
            return None
        return self.repo.get_document(did)

    def report_progress(self, did: str, progress: dict[str, Any], **fields: Any) -> None:
        if not self.repo.update_document(did, {"progress": progress, **fields}, expect_status=("parsing",)):
            raise Cancelled(did)

    def import_parsed(self, did: str, passages: list[ImportedPassage], page_sizes: list[tuple[float, float]]) -> None:
        now = self.now()
        rows = [
            Passage(
                id=new_id("chk"),
                document_id=did,
                label=f"P-{i + 1}",
                text=p.text,
                original_text=p.text,
                origin="auto",
                source=p.source,
                position=STEP * Decimal(i + 1),
                updated_at=now,
            )
            for i, p in enumerate(passages)
        ]
        self.repo.add_passages(rows)
        fields = {"status": "review", "progress": None, "next_label": len(rows) + 1, "page_count": len(page_sizes), "updated_at": now}
        if not self.repo.update_document(did, fields | {"page_sizes": _page_sizes(page_sizes)}, expect_status=("parsing",)):
            raise Cancelled(did)

    def fail(self, did: str, code: str, message: str) -> None:
        self.repo.update_document(did, {"status": "failed", "error": {"code": code, "message": message}, "updated_at": self.now()}, expect_status=("parsing",))

    # ------------------------------------------------------------ indexing-facing

    def report_embed_progress(self, did: str, done: int, total: int) -> None:
        doc = self.repo.get_document(did)
        if doc and doc.status == "embedding" and doc.progress:
            self.repo.update_document(did, {"progress": doc.progress | {"done": done, "total": total}}, expect_status=("embedding",))

    def embedding_failed(self, did: str, message: str) -> None:
        """Reconcile is resumable: passages already embedded keep their hash, so retrying continues."""
        self.repo.update_document(
            did,
            {"status": "review", "progress": None, "job_id": None, "error": {"code": "EMBED_FAILED", "message": message}, "updated_at": self.now()},
            expect_status=("embedding",),
        )

    def finish_embedding(self, did: str) -> None:
        doc = self.repo.get_document(did)
        if doc is None:
            return
        pending = self.counts(did).pending_changes
        fields = {"status": "ready" if pending == 0 else "review", "progress": None, "job_id": None, "error": None, "last_embedded_at": self.now(), "updated_at": self.now()}
        if not self.repo.update_document(did, fields, expect_version=doc.edit_version):
            # An edit landed after we counted; it is pending by definition.
            self.repo.update_document(did, fields | {"status": "review"})

    def delete_rows(self, did: str) -> None:
        self.repo.delete_document_rows(did)


def _page_sizes(sizes: list[tuple[float, float]]) -> str:
    return json.dumps([[round(w, 1), round(h, 1)] for w, h in sizes])
