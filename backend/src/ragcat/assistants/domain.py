"""Assistants & Access domain: the Assistant aggregate and the config read model for Answering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ragcat.shared.errors import InvalidState, ValidationError


@dataclass
class Assistant:
    id: str
    owner_id: str
    label: str
    name: str
    fallback_contact: str
    published: bool = False
    content_version: int = 0
    excluded_document_ids: set[str] = field(default_factory=set)
    created_at: str = ""
    updated_at: str = ""

    def rename(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValidationError("Assistant name cannot be empty")
        self.name = name[:80]

    def set_fallback(self, contact: str) -> None:
        self.fallback_contact = contact.strip()[:200]

    def set_published(self, published: bool, has_embedded_content: bool) -> None:
        if published and not has_embedded_content:
            raise InvalidState("Embed at least one document before publishing")
        self.published = published


@dataclass(frozen=True)
class AssistantConfig:
    """Read model Answering conforms to (cached as `ast:{aid}`)."""

    id: str
    owner_id: str
    name: str
    fallback_contact: str
    published: bool
    content_version: int
    excluded_document_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "fallback_contact": self.fallback_contact,
            "published": self.published,
            "content_version": self.content_version,
            "excluded_document_ids": list(self.excluded_document_ids),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> AssistantConfig:
        return AssistantConfig(
            d["id"], d["owner_id"], d["name"], d["fallback_contact"], d["published"], d["content_version"], tuple(d["excluded_document_ids"])
        )


def card_status(published: bool, doc_statuses: list[str], pending_changes: int) -> str:
    """Label on the My Assistants card: empty | processing | needs_review | ready | live."""
    if not doc_statuses:
        return "empty"
    if any(s in ("awaiting_upload", "parsing", "embedding") for s in doc_statuses):
        return "processing"
    if pending_changes:
        return "needs_review"
    return "live" if published else "ready"
