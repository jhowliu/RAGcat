"""DynamoDB repository for the Document aggregate: one partition per document (DOC#{did})."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from ragcat.curation.domain import Document, Passage, Source
from ragcat.infra.dynamo import Table, plain


def _doc_pk(did: str) -> str:
    return f"DOC#{did}"


def document_to_item(doc: Document) -> dict[str, Any]:
    return {
        "PK": _doc_pk(doc.id),
        "SK": "META",
        "GSI1PK": f"AST#{doc.assistant_id}",
        "GSI1SK": f"DOC#{doc.id}",
        "type": "document",
        "id": doc.id,
        "assistant_id": doc.assistant_id,
        "owner_id": doc.owner_id,
        "filename": doc.filename,
        "size_bytes": doc.size_bytes,
        "object_key": doc.object_key,
        "status": doc.status,
        "page_count": doc.page_count,
        "page_sizes": json.dumps(doc.page_sizes) if doc.page_sizes else None,
        "progress": doc.progress,
        "enabled": doc.enabled,
        "edit_version": doc.edit_version,
        "next_label": doc.next_label,
        "job_id": doc.job_id,
        "error": doc.error,
        "last_embedded_at": doc.last_embedded_at,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


def document_from_item(item: dict[str, Any]) -> Document:
    return Document(
        id=item["id"],
        assistant_id=item["assistant_id"],
        owner_id=item["owner_id"],
        filename=item["filename"],
        size_bytes=plain(item["size_bytes"]),
        object_key=item["object_key"],
        status=item["status"],
        page_count=plain(item.get("page_count")),
        page_sizes=[tuple(s) for s in json.loads(item["page_sizes"])] if item.get("page_sizes") else [],
        progress=plain(item.get("progress")),
        enabled=bool(item.get("enabled", True)),
        edit_version=plain(item.get("edit_version", 0)),
        next_label=plain(item.get("next_label", 1)),
        job_id=item.get("job_id"),
        error=plain(item.get("error")),
        last_embedded_at=item.get("last_embedded_at"),
        created_at=item.get("created_at", ""),
        updated_at=item.get("updated_at", ""),
    )


def passage_to_item(p: Passage) -> dict[str, Any]:
    return {
        "PK": _doc_pk(p.document_id),
        "SK": f"CHK#{p.id}",
        "type": "passage",
        "id": p.id,
        "document_id": p.document_id,
        "label": p.label,
        "text": p.text,
        "original_text": p.original_text,
        "origin": p.origin,
        "source": json.dumps(p.source.to_dict()),
        "position": p.position,
        "deleted": p.deleted,
        "embedded_hash": p.embedded_hash,
        "updated_at": p.updated_at,
    }


def passage_from_item(item: dict[str, Any]) -> Passage:
    return Passage(
        id=item["id"],
        document_id=item["document_id"],
        label=item["label"],
        text=item["text"],
        original_text=item.get("original_text"),
        origin=item["origin"],
        source=Source.from_dict(json.loads(item["source"])),
        position=Decimal(item["position"]),
        deleted=bool(item.get("deleted", False)),
        embedded_hash=item.get("embedded_hash"),
        updated_at=item.get("updated_at", ""),
        context=item.get("context"),
    )


# Fields the edit path owns on a passage row. `embedded_hash` belongs to Indexing (shared
# kernel), so edits never overwrite it; see domain-design.md §4.
_CURATION_FIELDS = ("label", "text", "original_text", "origin", "source", "position", "deleted", "updated_at", "document_id", "id", "type")


class DynamoCurationRepo:
    def __init__(self, table: Table) -> None:
        self.table = table

    # -- documents

    def add_document(self, doc: Document) -> None:
        if not self.table.put(document_to_item(doc), condition="attribute_not_exists(PK)"):
            raise RuntimeError(f"Document {doc.id} already exists")

    def get_document(self, did: str) -> Document | None:
        item = self.table.get(_doc_pk(did), "META")
        return document_from_item(item) if item else None

    def list_documents(self, aid: str) -> list[Document]:
        items = self.table.query_prefix(f"AST#{aid}", "DOC#", index="GSI1")
        return [document_from_item(i) for i in items]

    def update_document(
        self,
        did: str,
        fields: dict[str, Any],
        *,
        expect_status: tuple[str, ...] | None = None,
        expect_version: int | None = None,
    ) -> bool:
        conditions, values = ["attribute_exists(PK)"], {}
        if expect_status:
            keys = []
            for i, status in enumerate(expect_status):
                values[f":es{i}"] = status
                keys.append(f":es{i}")
            conditions.append(f"#status IN ({', '.join(keys)})")
        if expect_version is not None:
            values[":ev"] = expect_version
            conditions.append("#edit_version = :ev")
        return bool(
            self.table.update(
                _doc_pk(did), "META", set_fields=fields, condition=" AND ".join(conditions), condition_values=values
            )
        )

    def delete_document_rows(self, did: str) -> None:
        items = self.table.query_prefix(_doc_pk(did), "")
        self.table.batch_delete([(i["PK"], i["SK"]) for i in items])

    # -- passages

    def load_passages(self, did: str) -> list[Passage]:
        return [passage_from_item(i) for i in self.table.query_prefix(_doc_pk(did), "CHK#")]

    def add_passages(self, passages: list[Passage]) -> None:
        self.table.batch_put([passage_to_item(p) for p in passages])

    def save_edit(self, doc: Document, expected_version: int, writes: list[Passage], removals: list[str]) -> bool:
        """Persist one edit atomically; fails if the document changed since it was loaded."""
        meta_fields = {"edit_version": doc.edit_version, "next_label": doc.next_label, "updated_at": doc.updated_at}
        if doc.status == "review":
            meta_fields["status"] = "review"  # ready → review after an edit; never overwrites embedding
        names = {f"#f{i}": k for i, k in enumerate(meta_fields)} | {"#ev": "edit_version"}
        values = {f":f{i}": v for i, v in enumerate(meta_fields.values())} | {":expected": expected_version}
        ops: list[dict[str, Any]] = [
            {
                "Update": {
                    "Key": {"PK": _doc_pk(doc.id), "SK": "META"},
                    "UpdateExpression": "SET " + ", ".join(f"#f{i} = :f{i}" for i in range(len(meta_fields))),
                    "ConditionExpression": "#ev = :expected",
                    "ExpressionAttributeNames": names,
                    "ExpressionAttributeValues": values,
                }
            }
        ]
        for p in writes:
            item = passage_to_item(p)
            fields = {k: item[k] for k in _CURATION_FIELDS}
            set_names = {f"#p{i}": k for i, k in enumerate(fields)}
            set_values = {f":p{i}": v for i, v in enumerate(fields.values()) if v is not None}
            sets = [f"#p{i} = :p{i}" for i, v in enumerate(fields.values()) if v is not None]
            removes = [f"#p{i}" for i, v in enumerate(fields.values()) if v is None]
            expression = "SET " + ", ".join(sets) + (" REMOVE " + ", ".join(removes) if removes else "")
            ops.append(
                {
                    "Update": {
                        "Key": {"PK": item["PK"], "SK": item["SK"]},
                        "UpdateExpression": expression,
                        "ExpressionAttributeNames": set_names,
                        "ExpressionAttributeValues": set_values,
                    }
                }
            )
        for pid in removals:
            ops.append({"Delete": {"Key": {"PK": _doc_pk(doc.id), "SK": f"CHK#{pid}"}}})
        if len(ops) > 100:
            raise ValueError("Too many Passages changed in one operation")
        return self.table.transact(ops)
