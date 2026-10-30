"""DynamoDB repository for Assistants (AST#{aid} / META, listed per owner through GSI1)."""

from __future__ import annotations

from typing import Any

from ragcat.assistants.domain import Assistant
from ragcat.infra.dynamo import Table, plain

EXISTS = "attribute_exists(PK)"


def _to_item(a: Assistant) -> dict[str, Any]:
    return {
        "PK": f"AST#{a.id}",
        "SK": "META",
        "GSI1PK": f"OWNER#{a.owner_id}",
        "GSI1SK": f"AST#{a.id}",
        "type": "assistant",
        "id": a.id,
        "owner_id": a.owner_id,
        "label": a.label,
        "name": a.name,
        "fallback_contact": a.fallback_contact,
        "published": a.published,
        "content_version": a.content_version,
        "excluded_document_ids": a.excluded_document_ids or None,
        "widget_origins": a.widget_origins,
        "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _from_item(item: dict[str, Any]) -> Assistant:
    return Assistant(
        id=item["id"],
        owner_id=item["owner_id"],
        label=item["label"],
        name=item["name"],
        fallback_contact=item.get("fallback_contact", ""),
        published=bool(item.get("published", False)),
        content_version=plain(item.get("content_version", 0)),
        excluded_document_ids=set(item.get("excluded_document_ids") or ()),
        widget_origins=list(item.get("widget_origins") or ()),
        created_at=item.get("created_at", ""),
        updated_at=item.get("updated_at", ""),
    )


class DynamoAssistantRepo:
    def __init__(self, table: Table) -> None:
        self.table = table

    def add(self, assistant: Assistant) -> None:
        self.table.put(_to_item(assistant), condition="attribute_not_exists(PK)")

    def get(self, aid: str) -> Assistant | None:
        item = self.table.get(f"AST#{aid}", "META")
        return _from_item(item) if item else None

    def list_for(self, owner_id: str) -> list[Assistant]:
        return [_from_item(i) for i in self.table.query_prefix(f"OWNER#{owner_id}", "AST#", index="GSI1")]

    def remove(self, aid: str) -> None:
        self.table.delete(f"AST#{aid}", "META")

    # Updates are conditional: a deleted Assistant's documents still report changes while they are
    # removed, and an unconditional update would recreate the item.

    def save_settings(self, a: Assistant) -> None:
        self.table.update(
            f"AST#{a.id}",
            "META",
            set_fields={
                "name": a.name,
                "fallback_contact": a.fallback_contact,
                "published": a.published,
                "widget_origins": a.widget_origins,
                "updated_at": a.updated_at,
            },
            condition=EXISTS,
        )

    def bump_content_version(self, aid: str, updated_at: str) -> None:
        self.table.update(f"AST#{aid}", "META", set_fields={"updated_at": updated_at}, add_fields={"content_version": 1}, condition=EXISTS)

    def set_excluded(self, aid: str, did: str, excluded: bool, updated_at: str) -> None:
        if excluded:
            self.table.update(
                f"AST#{aid}", "META", set_fields={"updated_at": updated_at}, add_fields={"excluded_document_ids": {did}, "content_version": 1}, condition=EXISTS
            )
        else:
            self.table.update(
                f"AST#{aid}",
                "META",
                set_fields={"updated_at": updated_at},
                add_fields={"content_version": 1},
                delete_from_sets={"excluded_document_ids": {did}},
                condition=EXISTS,
            )
