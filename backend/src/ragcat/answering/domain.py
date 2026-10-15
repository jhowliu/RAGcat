"""Answering domain: prompt assembly, citation extraction and the fallback rule."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from ragcat.infra.vectors import Hit

NO_ANSWER = "NO_ANSWER"
MAX_CITATIONS = 3
MAX_QUESTION = 1000


@dataclass(frozen=True)
class Caller:
    """Who is asking: the owner (any state) or a customer channel (published assistants only)."""

    kind: str  # owner | widget | api_key | discord
    owner_id: str | None = None


@dataclass(frozen=True)
class Citation:
    n: int
    chunk_id: str
    label: str
    document_id: str
    document_title: str
    page: int
    para: int
    boxes: list[dict[str, Any]]
    edited: bool

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def normalize(question: str) -> str:
    return " ".join((question or "").split())


def question_hash(question: str) -> str:
    return hashlib.sha256(normalize(question).lower().encode()).hexdigest()[:32]


def build_prompt(assistant_name: str, question: str, hits: list[Hit]) -> tuple[str, str]:
    system = (
        f"You are {assistant_name}, a customer support assistant. Answer ONLY from the numbered "
        "passages. After each sentence, cite the passage it came from as [n]. Keep the answer to "
        f"one to three sentences, in the language of the question. If the passages do not contain the answer, reply exactly {NO_ANSWER}."
    )
    blocks = [f"[{i}] {_header(h)}\n{h.metadata.get('text', '')}\n" for i, h in enumerate(hits, 1)]
    return system, "Passages:\n" + "\n".join(blocks) + f"\nQuestion: {question}"


def _header(hit: Hit) -> str:
    """Where a passage comes from; the section path is the cheap part of contextual retrieval
    worth showing the LLM (the generated context only shapes the vector)."""
    parts = [hit.metadata.get("document_title", ""), f"p.{hit.metadata.get('page', '?')}"]
    if hit.metadata.get("section"):
        parts.append(hit.metadata["section"])
    return " · ".join(parts)


def merge_preview(live: list[Hit], stale: set[str], preview: list[Hit], top_k: int) -> list[Hit]:
    """An owner's test: live hits whose passage changed give way to the passage's preview hit."""
    hits = [h for h in live if h.key not in stale] + preview
    return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]


def citations_for(answer: str, hits: list[Hit]) -> list[Citation]:
    seen: list[int] = []
    for match in re.finditer(r"\[(\d+)\]", answer):
        n = int(match.group(1))
        if 1 <= n <= len(hits) and n not in seen:
            seen.append(n)
    out = []
    for n in seen[:MAX_CITATIONS]:
        meta = hits[n - 1].metadata
        out.append(
            Citation(
                n=n,
                chunk_id=hits[n - 1].key,
                label=meta.get("label", ""),
                document_id=meta.get("document_id", ""),
                document_title=meta.get("document_title", ""),
                page=int(meta.get("page", 0)),
                para=int(meta.get("para", 0)),
                boxes=json.loads(meta.get("boxes") or "[]"),
                edited=bool(meta.get("edited", False)),
            )
        )
    return out


def fallback(contact: str) -> dict[str, str]:
    message = "I couldn't find that in our documents."
    if contact:
        message += f" Please contact {contact}."
    return {"contact": contact, "message": message}
