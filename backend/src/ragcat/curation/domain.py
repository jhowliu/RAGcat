"""Curation domain: a Document aggregate and the Passages the owner reviews before embedding.

Pure logic only (no I/O). Invariants enforced here (domain-design.md §3):
- passages can only be edited while the document is review / embedding / ready;
- merge needs adjacent passages in document order; split parts must add up to the text;
- passages that never had a vector are removed outright, embedded ones are soft-deleted
  so Indexing can delete their vectors on the next embed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from typing import Any

from ragcat.shared.errors import InvalidState, NotFound, Unprocessable, ValidationError
from ragcat.shared.ids import new_id
from ragcat.shared.kernel import VectorSpec, wanted_hashes
from ragcat.shared.text import text_length, token_estimate, words

EDITABLE = ("review", "embedding", "ready")
STEP = Decimal(1024)
MAX_TEXT = 20_000


@dataclass(frozen=True)
class Box:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float

    def to_dict(self) -> dict[str, Any]:
        return {"page": self.page, "x0": round(self.x0, 4), "y0": round(self.y0, 4), "x1": round(self.x1, 4), "y1": round(self.y1, 4)}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Box:
        return Box(int(d["page"]), float(d["x0"]), float(d["y0"]), float(d["x1"]), float(d["y1"]))


@dataclass(frozen=True)
class Source:
    page_start: int
    page_end: int
    para_start: int | None = None
    para_end: int | None = None
    boxes: tuple[Box, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_start": self.page_start,
            "page_end": self.page_end,
            "para_start": self.para_start,
            "para_end": self.para_end,
            "boxes": [b.to_dict() for b in self.boxes],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Source:
        return Source(
            int(d["page_start"]),
            int(d["page_end"]),
            d.get("para_start"),
            d.get("para_end"),
            tuple(Box.from_dict(b) for b in d.get("boxes", [])),
        )


@dataclass(frozen=True)
class PassageWarning:
    code: str
    message: str


@dataclass
class Passage:
    id: str
    document_id: str
    label: str
    text: str
    original_text: str | None
    origin: str  # auto | edited | merged | split | added
    source: Source
    position: Decimal
    deleted: bool = False
    embedded_hash: str | None = None
    updated_at: str = ""
    context: str | None = None  # written by Indexing when contextual retrieval is on

    @property
    def warnings(self) -> list[PassageWarning]:
        return lint(self.text)

    @property
    def token_count(self) -> int:
        return token_count(self.text)



@dataclass
class Document:
    id: str
    assistant_id: str
    owner_id: str
    filename: str
    size_bytes: int
    object_key: str
    status: str = "awaiting_upload"
    page_count: int | None = None
    page_sizes: list[tuple[float, float]] = field(default_factory=list)
    progress: dict[str, Any] | None = None
    enabled: bool = True
    edit_version: int = 0
    next_label: int = 1
    job_id: str | None = None
    error: dict[str, Any] | None = None
    last_embedded_at: str | None = None
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------- text helpers

_MARKDOWN_TABLE = re.compile(r"^\|.*\|[ \t]*\n\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*$", re.M)


def token_count(text: str) -> int:
    return token_estimate(text)


def is_table(text: str) -> bool:
    """A whole Markdown table, as Ingestion writes detected tables."""
    return bool(_MARKDOWN_TABLE.search(text))


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _clean(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationError("Passage text cannot be empty")
    if len(text) > MAX_TEXT:
        raise ValidationError(f"Passage text is longer than {MAX_TEXT} characters")
    return text


def lint(text: str) -> list[PassageWarning]:
    """Lengths are word-equivalent units (shared.text), so the thresholds hold for CJK text too."""
    stripped = text.strip()
    length = text_length(stripped)
    table = is_table(stripped)
    out: list[PassageWarning] = []
    numeric = sum(1 for w in words(stripped) if re.fullmatch(r"\d+([.,]\d+)?", w))
    looks_tabular = (length >= 6 and numeric / length > 0.4) or stripped.count("|") >= 3 or stripped.count("\t") >= 3
    if looks_tabular and not table:
        out.append(PassageWarning("TABLE_FRAGMENT", "Looks like part of a table. Check that rows stay together."))
    elif length <= 10 and "\n" not in stripped and not re.search(r"[.!?:;。！？：；]$", stripped):
        out.append(PassageWarning("HEADING_ONLY", "Only a heading. Merge it with the next Passage."))
    elif length < 12 and not table:
        out.append(PassageWarning("TOO_SHORT", "Very short. It may not answer anything on its own."))
    if length > (600 if table else 300):
        out.append(PassageWarning("TOO_LONG", "Long Passage. Consider splitting it."))
    return out


# ---------------------------------------------------------------- ordering

def position_between(lo: Decimal | None, hi: Decimal | None) -> Decimal:
    """Fractional index: a position strictly between two neighbours."""
    with localcontext() as ctx:
        ctx.prec = 38
        if lo is None and hi is None:
            return STEP
        if lo is None:
            return hi - STEP
        if hi is None:
            return lo + STEP
        return (lo + hi) / 2


def positions_between(lo: Decimal | None, hi: Decimal | None, count: int) -> list[Decimal]:
    out, current = [], lo
    for i in range(count):
        if hi is None:
            current = position_between(current, None)
        else:
            with localcontext() as ctx:
                ctx.prec = 38
                base = lo if lo is not None else hi - STEP * (count + 1)
                current = base + (hi - base) * (i + 1) / (count + 1)
        out.append(current)
    return out


def _slice_boxes(boxes: tuple[Box, ...], start: float, end: float) -> tuple[Box, ...]:
    """Boxes covering the [start, end) fraction of a passage's text.

    Text is assumed to be spread over the boxes in proportion to their area (a heading's small
    box holds little text, a paragraph's large box holds most of it), top to bottom in each box.
    """
    areas = [max(1e-6, (b.x1 - b.x0) * (b.y1 - b.y0)) for b in boxes]
    total = sum(areas)
    out, lo = [], 0.0
    for box, area in zip(boxes, areas):
        hi = lo + area / total
        s, e = max(start, lo), min(end, hi)
        if e - s > 1e-9:
            f0, f1 = (s - lo) / (hi - lo), (e - lo) / (hi - lo)
            height = box.y1 - box.y0
            out.append(Box(box.page, box.x0, box.y0 + height * f0, box.x1, box.y0 + height * f1))
        lo = hi
    return tuple(out)


# ---------------------------------------------------------------- the aggregate's edit operations

@dataclass
class ChangeSet:
    upserted: list[Passage]  # visible passages that changed (returned to the client)
    deleted: list[str]  # ids that are no longer visible
    writes: list[Passage]  # every passage row to write, including soft-deleted ones
    removals: list[str]  # rows to remove outright

    @property
    def empty(self) -> bool:
        return not self.writes and not self.removals


class PassageEditor:
    """Applies owner edits to one document's passages; `commit()` returns what to persist."""

    def __init__(self, document: Document, passages: list[Passage], now: str) -> None:
        if document.status not in EDITABLE:
            raise InvalidState(f"Passages cannot be edited while the document is {document.status}")
        self.document = document
        self._by_id = {p.id: p for p in passages}
        self._now = now
        self._touched: dict[str, Passage] = {}
        self._hidden: list[str] = []
        self._removed: list[str] = []

    # -- queries

    def visible(self) -> list[Passage]:
        return sorted((p for p in self._by_id.values() if not p.deleted), key=lambda p: p.position)

    def _get(self, pid: str) -> Passage:
        passage = self._by_id.get(pid)
        if passage is None or passage.deleted:
            raise NotFound("Passage not found")
        return passage

    def _neighbour_after(self, passage: Passage) -> Passage | None:
        order = self.visible()
        idx = next(i for i, p in enumerate(order) if p.id == passage.id)
        return order[idx + 1] if idx + 1 < len(order) else None

    # -- bookkeeping

    def _touch(self, passage: Passage) -> None:
        passage.updated_at = self._now
        self._touched[passage.id] = passage

    def _hide(self, passage: Passage) -> None:
        self._hidden.append(passage.id)
        if passage.embedded_hash is None:
            self._removed.append(passage.id)
            self._touched.pop(passage.id, None)
            del self._by_id[passage.id]
        else:
            passage.deleted = True
            self._touch(passage)

    def _new_label(self) -> str:
        label = f"P-{self.document.next_label}"
        self.document.next_label += 1
        return label

    # -- operations

    def edit(self, pid: str, text: str) -> None:
        passage = self._get(pid)
        text = _clean(text)
        if text == passage.text:
            return
        passage.text = text
        if passage.origin == "auto":
            passage.origin = "edited"
        self._touch(passage)

    def delete(self, pid: str) -> None:
        self._hide(self._get(pid))

    def restore(self, pid: str) -> None:
        passage = self._get(pid)
        if passage.original_text is None:
            raise Unprocessable("This Passage was added by you and has no original text", code="CANNOT_RESTORE")
        if passage.text == passage.original_text:
            return
        passage.text = passage.original_text
        if passage.origin == "edited":
            passage.origin = "auto"
        self._touch(passage)

    def add(self, after_id: str | None, text: str, page: int | None = None) -> Passage:
        text = _clean(text)
        order = self.visible()
        if after_id is None:
            lo, hi, anchor = None, (order[0].position if order else None), (order[0] if order else None)
        else:
            anchor = self._get(after_id)
            nxt = self._neighbour_after(anchor)
            lo, hi = anchor.position, (nxt.position if nxt else None)
        if page is None:
            page = anchor.source.page_end if anchor else 1
        if self.document.page_count and not 1 <= page <= self.document.page_count:
            raise ValidationError("Page is outside the document")
        passage = Passage(
            id=new_id("chk"),
            document_id=self.document.id,
            label=self._new_label(),
            text=text,
            original_text=None,
            origin="added",
            source=Source(page, page),
            position=position_between(lo, hi),
        )
        self._by_id[passage.id] = passage
        self._touch(passage)
        return passage

    def split(self, pid: str, parts: list[str]) -> list[Passage]:
        parts = [p.strip() for p in parts]
        if len(parts) < 2 or any(not p for p in parts):
            raise ValidationError("Split needs at least two non-empty parts")
        passage = self._get(pid)
        if _squash("".join(parts)) != _squash(passage.text):
            raise Unprocessable("The parts do not add up to the Passage text", code="SPLIT_MISMATCH")
        nxt = self._neighbour_after(passage)
        positions = positions_between(passage.position, nxt.position if nxt else None, len(parts) - 1)
        total = sum(len(p) for p in parts)
        bounds, acc = [], 0
        for part in parts:
            bounds.append((acc / total, (acc + len(part)) / total))
            acc += len(part)
        boxes = passage.source.boxes
        out = []
        for i, part in enumerate(parts):
            part_boxes = _slice_boxes(boxes, *bounds[i]) if boxes else ()
            pages = [b.page for b in part_boxes] or [passage.source.page_start, passage.source.page_end]
            source = Source(min(pages), max(pages), passage.source.para_start, passage.source.para_end, part_boxes)
            if i == 0:
                target = passage
                target.text, target.source = part, source
            else:
                target = Passage(
                    id=new_id("chk"),
                    document_id=self.document.id,
                    label=self._new_label(),
                    text=part,
                    original_text=part,
                    origin="split",
                    source=source,
                    position=positions[i - 1],
                )
                self._by_id[target.id] = target
            target.original_text = part
            target.origin = "split"
            self._touch(target)
            out.append(target)
        return out

    def merge(self, ids: list[str], separator: str = "\n\n") -> Passage:
        if len(ids) < 2 or len(set(ids)) != len(ids):
            raise ValidationError("Merge needs at least two different Passages")
        for pid in ids:
            self._get(pid)
        order = self.visible()
        index = {p.id: i for i, p in enumerate(order)}
        idx = [index[pid] for pid in ids]
        if idx != list(range(idx[0], idx[0] + len(idx))):
            raise Unprocessable("Only adjacent Passages, in document order, can be merged", code="NOT_CONTIGUOUS")
        group = [order[i] for i in idx]
        first = group[0]
        first.text = separator.join(p.text for p in group)
        first.original_text = separator.join(p.original_text if p.original_text is not None else p.text for p in group)
        first.origin = "merged"
        first.source = Source(
            min(p.source.page_start for p in group),
            max(p.source.page_end for p in group),
            first.source.para_start,
            group[-1].source.para_end,
            tuple(b for p in group for b in p.source.boxes),
        )
        self._touch(first)
        for passage in group[1:]:
            self._hide(passage)
        return first

    # -- result

    def commit(self) -> ChangeSet:
        writes = list(self._touched.values())
        if not writes and not self._removed:
            return ChangeSet([], [], [], [])
        self.document.edit_version += 1
        self.document.updated_at = self._now
        if self.document.status == "ready":
            self.document.status = "review"
        hidden = set(self._hidden)
        upserted = [p for p in writes if not p.deleted and p.id not in hidden]
        return ChangeSet(upserted, list(dict.fromkeys(self._hidden)), writes, self._removed)


# ---------------------------------------------------------------- summaries

@dataclass(frozen=True)
class PassageCounts:
    all: int
    warnings: int
    edited: int
    pending: int
    removed: int

    @property
    def pending_changes(self) -> int:
        return self.pending + self.removed

    def to_dict(self) -> dict[str, int]:
        return {"all": self.all, "warnings": self.warnings, "edited": self.edited, "pending": self.pending, "removed": self.removed}


def pending_ids(passages: list[Passage], spec: VectorSpec) -> set[str]:
    """Visible passages whose vector is missing or out of date (text or section changed)."""
    ordered = sorted(passages, key=lambda p: p.position)
    wanted = wanted_hashes(spec, [(p.id, p.text, p.deleted) for p in ordered])
    return {p.id for p in ordered if not p.deleted and wanted[p.id][0] != p.embedded_hash}


def count_passages(passages: list[Passage], spec: VectorSpec) -> PassageCounts:
    visible = [p for p in passages if not p.deleted]
    return PassageCounts(
        all=len(visible),
        warnings=sum(1 for p in visible if p.warnings),
        edited=sum(1 for p in visible if p.origin != "auto"),
        pending=len(pending_ids(passages, spec)),
        removed=sum(1 for p in passages if p.deleted and p.embedded_hash is not None),
    )
