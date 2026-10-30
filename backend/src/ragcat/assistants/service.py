"""Assistants & Access application service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ragcat.assistants.adapters import DynamoAssistantRepo
from ragcat.assistants.domain import Assistant, AssistantConfig, card_status
from ragcat.infra.cache import Cache, get_json, set_json
from ragcat.shared.errors import NotFound, ValidationError
from ragcat.shared.ids import new_id
from ragcat.shared.kernel import now_iso

CONFIG_TTL = 300


@dataclass(frozen=True)
class AssistantSummary:
    assistant: Assistant
    status: str
    document_count: int
    pending_changes: int
    processing: dict[str, Any] | None  # progress of a document being read, for the card subtitle


class AssistantsService:
    def __init__(
        self,
        repo: DynamoAssistantRepo,
        cache: Cache,
        documents: Callable[[str], list[Any]],
        clock: Callable[[], str] = now_iso,
    ) -> None:
        """`documents(aid)` returns Curation's DocumentSummary read model."""
        self.repo = repo
        self.cache = cache
        self.documents = documents
        self.now = clock

    # ------------------------------------------------------------ owner-facing

    def create(self, owner_id: str, name: str, fallback_contact: str) -> Assistant:
        existing = self.repo.list_for(owner_id)
        if len(existing) >= 10:
            raise ValidationError("Your plan allows 10 Assistants")
        now = self.now()
        assistant = Assistant(
            id=new_id("ast"),
            owner_id=owner_id,
            label=f"AS-{len(existing) + 1:02d}",
            name="",
            fallback_contact="",
            created_at=now,
            updated_at=now,
        )
        assistant.rename(name or "Untitled Assistant")
        assistant.set_fallback(fallback_contact)
        self.repo.add(assistant)
        return assistant

    def get(self, owner_id: str, aid: str) -> Assistant:
        assistant = self.repo.get(aid)
        if assistant is None or assistant.owner_id != owner_id:
            raise NotFound("Assistant not found")
        return assistant

    def summarize(self, assistant: Assistant) -> AssistantSummary:
        docs = self.documents(assistant.id)
        pending = sum(d.pending_changes for d in docs)
        reading = next((d.progress for d in docs if d.status == "parsing" and d.progress), None)
        return AssistantSummary(assistant, card_status(assistant.published, [d.status for d in docs], pending), len(docs), pending, reading)

    def list(self, owner_id: str) -> list[AssistantSummary]:
        assistants = sorted(self.repo.list_for(owner_id), key=lambda a: a.created_at)
        return [self.summarize(a) for a in assistants]

    def update(
        self,
        owner_id: str,
        aid: str,
        *,
        name: str | None = None,
        fallback_contact: str | None = None,
        published: bool | None = None,
        widget_origins: list[str] | None = None,
    ) -> Assistant:
        assistant = self.get(owner_id, aid)
        if name is not None:
            assistant.rename(name)
        if fallback_contact is not None:
            assistant.set_fallback(fallback_contact)
        if published is not None:
            assistant.set_published(published, any(d.has_embedded for d in self.documents(aid)))
        if widget_origins is not None:
            assistant.set_widget_origins(widget_origins)
        assistant.updated_at = self.now()
        self.repo.save_settings(assistant)
        self.cache.delete(f"ast:{aid}")
        return assistant

    def delete(self, owner_id: str, aid: str) -> None:
        """Owner and customers lose the Assistant at once. Its documents must already be marked for
        deletion: Indexing removes their vectors and files later."""
        self.get(owner_id, aid)
        self.repo.remove(aid)
        self.cache.delete(f"ast:{aid}")

    # ------------------------------------------------------------ read model for Answering

    def config(self, aid: str) -> AssistantConfig:
        cached = get_json(self.cache, f"ast:{aid}")
        if cached:
            return AssistantConfig.from_dict(cached)
        assistant = self.repo.get(aid)
        if assistant is None:
            raise NotFound("Assistant not found")
        config = AssistantConfig(
            assistant.id,
            assistant.owner_id,
            assistant.name,
            assistant.fallback_contact,
            assistant.published,
            assistant.content_version,
            tuple(sorted(assistant.excluded_document_ids)),
            tuple(assistant.widget_origins),
        )
        set_json(self.cache, f"ast:{aid}", config.to_dict(), CONFIG_TTL)
        return config

    # ------------------------------------------------------------ domain events from other contexts

    def content_changed(self, aid: str) -> None:
        """DocumentIndexed: new vectors are live, so answers cached for the old version must not be served."""
        self.repo.bump_content_version(aid, self.now())
        self.cache.delete(f"ast:{aid}")

    def document_visibility_changed(self, assistant_id: str, document_id: str, visible: bool) -> None:
        self.repo.set_excluded(assistant_id, document_id, not visible, self.now())
        self.cache.delete(f"ast:{assistant_id}")
