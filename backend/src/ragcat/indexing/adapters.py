"""Indexing's side of the shared kernel: the fields of a passage row that Indexing owns.

Curation owns text / deleted / order; only this adapter writes `embedded_hash` and `context`,
and removes soft-deleted rows once their vectors are gone (domain-design.md §4).
"""

from __future__ import annotations

from ragcat.infra.dynamo import Table


class PassageIndexState:
    def __init__(self, table: Table) -> None:
        self.table = table

    def mark_embedded(self, did: str, pid: str, content_hash: str, context: str | None) -> None:
        # attribute_exists: never resurrect a row that was removed meanwhile.
        self.table.update(
            f"DOC#{did}",
            f"CHK#{pid}",
            set_fields={"embedded_hash": content_hash, "context": context or None},
            condition="attribute_exists(PK)",
        )

    def purge(self, did: str, pid: str) -> None:
        self.table.delete(f"DOC#{did}", f"CHK#{pid}", condition="#deleted = :true", condition_values={":true": True})
