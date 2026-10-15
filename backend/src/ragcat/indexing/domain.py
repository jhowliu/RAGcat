"""Indexing domain: decide how to make the vector index match a document's passages.

want = the hash of what a visible passage's vector should represent (shared kernel: model,
text and, with contextual retrieval, its section); None for a deleted passage or every passage
when the document is being deleted. have = embedded_hash. See api-design.md §5.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ragcat.shared.kernel import VectorSpec, wanted_hashes


@dataclass(frozen=True)
class PassageState:
    id: str
    text: str
    deleted: bool
    embedded_hash: str | None


@dataclass(frozen=True)
class Put:
    passage: PassageState
    hash: str  # recorded as embedded_hash once the vector is written
    section: str  # heading the passage falls under (context input and citation header)


@dataclass
class ReconcilePlan:
    puts: list[Put] = field(default_factory=list)
    deletes: list[str] = field(default_factory=list)  # vector keys to delete
    purges: list[str] = field(default_factory=list)  # soft-deleted rows to remove afterwards

    @property
    def work(self) -> int:
        return len(self.puts) + len(self.deletes)


def plan_reconcile(passages: list[PassageState], spec: VectorSpec, document_deleting: bool = False) -> ReconcilePlan:
    """`passages` must be in document order: sections depend on the headings above each passage."""
    wanted = wanted_hashes(spec, [(p.id, p.text, p.deleted) for p in passages])
    plan = ReconcilePlan()
    for p in passages:
        want, section = (None, "") if document_deleting else wanted[p.id]
        have = p.embedded_hash
        if want == have:
            if p.deleted:
                plan.purges.append(p.id)
            continue
        if want is not None:
            plan.puts.append(Put(p, want, section))
            continue
        if have is not None:
            plan.deletes.append(p.id)
        if p.deleted:
            plan.purges.append(p.id)
    return plan


# ---------------------------------------------------------------- contextual retrieval

# The ontology the context call tags passages with: a fixed list so entity metadata stays comparable
# across documents. Changing it, or the prompt, means bumping CONTEXT_PROMPT_VERSION (shared kernel).
ENTITY_TYPES = ("product", "policy", "condition", "fee", "period", "contact", "organization", "person", "location")
MAX_ENTITIES = 10
MAX_ENTITY_NAME = 60


@dataclass(frozen=True)
class PassageContext:
    text: str = ""
    entities: tuple[tuple[str, str], ...] = ()  # (type, name) in the order they appear

    @property
    def tags(self) -> list[str]:
        """`type:name`, the form stored in vector metadata."""
        return [f"{kind}:{name}" for kind, name in self.entities]


def context_prompt(document_title: str, section: str, text: str) -> str:
    return (
        f"Document: {document_title}\n"
        f"Section: {section or '(none)'}\n\n"
        f"Passage:\n{text}\n\n"
        "Reply with one JSON object only (no code fence) with two keys.\n"
        '"context": one or two short sentences that situate this passage within the document so it can be '
        "found by search: name the document and topic it belongs to, and what the passage is about. "
        "Write them in the language of the passage.\n"
        '"entities": the named things the passage is about, as a list of {"name": ..., "type": ...}. '
        f"type is one of: {', '.join(ENTITY_TYPES)}. Copy each name as written in the passage, "
        "skip anything that fits none of the types, and use [] if there is nothing."
    )


def parse_context(reply: str) -> PassageContext:
    """Read the reply to `context_prompt`. Raises ValueError if it is not the JSON object asked for;
    entries of the wrong shape or type are dropped rather than failing the passage."""
    reply = reply.strip()
    start, end = reply.find("{"), reply.rfind("}")  # tolerate a code fence or a leading remark
    if start < 0 or end < start:
        raise ValueError("no JSON object in reply")
    data = json.loads(reply[start : end + 1])
    if not isinstance(data, dict) or not isinstance(data.get("context"), str):
        raise ValueError("reply has no context")
    entities: list[tuple[str, str]] = []
    for item in data.get("entities") if isinstance(data.get("entities"), list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or item.get("type") not in ENTITY_TYPES:
            continue
        name = " ".join(item["name"].split())[:MAX_ENTITY_NAME]
        entity = (item["type"], name)
        if name and entity not in entities:
            entities.append(entity)
    return PassageContext(" ".join(data["context"].split()), tuple(entities[:MAX_ENTITIES]))


def embedding_input(context: PassageContext, text: str) -> str:
    lines = [context.text, f"Entities: {', '.join(f'{name} ({kind})' for kind, name in context.entities)}" if context.entities else ""]
    head = "\n".join(line for line in lines if line)
    return f"{head}\n\n{text}" if head else text
