"""Shared kernel between Curation and Indexing (domain-design.md §4).

Both contexts must agree on what a passage's vector represents: Curation uses it to show which
passages are pending, Indexing uses it to decide what to embed. A vector represents the
embedding model, the passage text and, with contextual retrieval, the section the passage sits
in (its context is written from the document title, that section and the text).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from ragcat.shared.text import text_length

CONTEXT_PROMPT_VERSION = "ctx2"  # ctx2: context call also tags entities


@dataclass(frozen=True)
class VectorSpec:
    model: str  # embedding model id and dimensions
    contextual: bool = False
    context_model: str = ""  # context generator; changing it requires new context + embedding

    @property
    def key(self) -> str:
        if not self.contextual:
            return self.model
        context = f":{self.context_model}" if self.context_model else ""
        return f"{self.model}:{CONTEXT_PROMPT_VERSION}{context}"

    def hash(self, text: str, section: str = "") -> str:
        basis = f"{self.key}\n{section if self.contextual else ''}\n{text}"
        return hashlib.sha256(basis.encode()).hexdigest()[:32]


_NOT_A_HEADING = re.compile(r"^(\||\[Figure\]|(fig(ure)?\.?|chart|圖|图)\s*\d)", re.I)


def heading_of(text: str) -> str | None:
    """The heading a passage starts with: a short first line without sentence punctuation."""
    first = text.strip().split("\n", 1)[0].strip()
    if not first or len(first) > 90 or text_length(first) > 12:
        return None
    if _NOT_A_HEADING.match(first) or re.search(r"[.!?;,。！？；，、:：]$", first):
        return None
    return first


def sections(texts: list[str]) -> list[str]:
    """For passages in document order, the most recent heading each one falls under."""
    out, current = [], ""
    for text in texts:
        current = heading_of(text) or current
        out.append(current)
    return out


def wanted_hashes(spec: VectorSpec, passages: list[tuple[str, str, bool]]) -> dict[str, tuple[str | None, str]]:
    """(id, text, deleted) in document order → {id: (hash the vector should have, section)}.
    Deleted passages want no vector."""
    visible = [(pid, text) for pid, text, deleted in passages if not deleted]
    section_of = dict(zip((pid for pid, _ in visible), sections([text for _, text in visible])))
    return {
        pid: (None, "") if deleted else (spec.hash(text, section_of[pid]), section_of[pid])
        for pid, text, deleted in passages
    }


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
