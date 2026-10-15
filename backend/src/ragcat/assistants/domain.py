"""Assistants & Access domain: the Assistant aggregate and the config read model for Answering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ragcat.shared.errors import InvalidState, ValidationError

MAX_WIDGET_ORIGINS = 10
_ORIGIN = re.compile(r"^(https?)://([a-z0-9.-]+|\[::1\])(:\d{1,5})?$")
_DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}


def widget_origin(value: str) -> str:
    """A site allowed to embed the Website widget (api-design.md §7): scheme://host[:port], no
    path or wildcard, https except on the owner's own machine."""
    origin = value.strip().lower().rstrip("/")
    match = _ORIGIN.match(origin)
    if match is None:
        raise ValidationError(f"{value!r} is not a website address like https://www.yourshop.com")
    scheme, host = match.group(1), match.group(2)
    local = host in _LOCAL_HOSTS
    if not local and not _DOMAIN.match(host):
        raise ValidationError(f"{value!r} is not a website address like https://www.yourshop.com")
    if scheme == "http" and not local:
        raise ValidationError(f"{value!r} must use https://")
    return origin


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
    widget_origins: list[str] = field(default_factory=list)  # empty: the Website widget is off
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

    def set_widget_origins(self, origins: list[str]) -> None:
        normalized = list(dict.fromkeys(widget_origin(o) for o in origins))
        if len(normalized) > MAX_WIDGET_ORIGINS:
            raise ValidationError(f"You can add up to {MAX_WIDGET_ORIGINS} websites")
        self.widget_origins = normalized


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
    widget_origins: tuple[str, ...] = ()

    @property
    def widget_on(self) -> bool:
        """Customers can ask through the Website widget."""
        return self.published and bool(self.widget_origins)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "fallback_contact": self.fallback_contact,
            "published": self.published,
            "content_version": self.content_version,
            "excluded_document_ids": list(self.excluded_document_ids),
            "widget_origins": list(self.widget_origins),
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> AssistantConfig:
        return AssistantConfig(
            d["id"],
            d["owner_id"],
            d["name"],
            d["fallback_contact"],
            d["published"],
            d["content_version"],
            tuple(d["excluded_document_ids"]),
            tuple(d.get("widget_origins", ())),
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
