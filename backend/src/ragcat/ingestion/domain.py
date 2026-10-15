"""Ingestion domain: turn text blocks read from a PDF into the first draft of Passages.

Chunking policy: a heading starts a new Passage and stays attached to the paragraph that
follows; consecutive paragraphs are packed until a Passage reaches about TARGET units, never
exceeding MAX; an oversized paragraph is split on sentence boundaries. A table is kept whole
as its own Passage (split by rows, header repeated, only when very large). Lengths are
word-equivalent units, so English and CJK text are sized alike (see shared.text).
Imperfect results (heading-only passages, odd layouts) are expected: the owner fixes them in review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from ragcat.shared.text import join_text, joins_tightly, sentences, text_length

TARGET = 140
MAX = 260
TABLE_MAX = 600
SPANNING = 0.55  # a block wider than this fraction of the page spans all columns


class IngestError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Block:
    page: int  # 1-based
    para: int  # 1-based, per page, in reading order
    text: str  # a table's text is Markdown
    box: tuple[float, float, float, float]  # normalised 0–1 page coordinates
    font_size: float
    bold: bool
    kind: str = "text"  # text | table | figure


@dataclass(frozen=True)
class Figure:
    """An image or vector chart worth describing. Its Block carries `key` as a placeholder text
    until a vision model has described it."""

    key: str  # "{page}:{n}"
    page: int
    box: tuple[float, float, float, float]
    image: bytes  # JPEG crop of the figure
    inner_text: str  # labels and values drawn inside the figure
    caption: str  # "Figure 1. …" text attached to it, if any


FIGURE_LIMIT = 40
_CAPTION = re.compile(r"^(fig(ure)?\.?|chart|diagram|photo|圖|图)\s*[\dA-Za-z一二三四五六七八九十]*\s*[.:：、]?", re.I)


def is_caption(text: str) -> bool:
    return text_length(text) <= 40 and bool(_CAPTION.match(text.strip()))


def describe_prompt(hints: str) -> str:
    return (
        "This image is a figure from a company document. A customer support assistant will use your "
        "description to answer questions about it. Describe what it shows in 2 to 4 sentences. Transcribe "
        "every label, number and short text you can read; for a chart, give the key values and the trend. "
        "If it is purely decorative (a logo, an icon, a photo with no information), reply exactly DECORATIVE. "
        f"Write in the language of these nearby words: {hints.strip()[:400] or '(none)'}"
    )


def figure_passage_text(caption: str, description: str) -> str:
    body = f"[Figure] {description.strip()}"
    return f"{caption.strip()}\n{body}" if caption.strip() else body


@dataclass(frozen=True)
class Chunk:
    text: str
    page_start: int
    page_end: int
    para_start: int
    para_end: int
    boxes: tuple[tuple[int, float, float, float, float], ...]


# ---------------------------------------------------------------- page layout

def reading_order(blocks: list[Block]) -> list[Block]:
    """Order one page's blocks for reading, column by column.

    Blocks wider than SPANNING (titles, full-width paragraphs, tables) split the page into
    horizontal bands. Inside a band, narrower blocks are grouped into columns by overlapping
    x ranges, and each column is read top to bottom, left column first.
    """
    out: list[Block] = []
    band: list[Block] = []

    def flush() -> None:
        columns: list[tuple[float, float, list[Block]]] = []
        for b in sorted(band, key=lambda b: b.box[0]):
            if columns and b.box[0] < columns[-1][1] - 0.01:
                lo, hi, members = columns[-1]
                columns[-1] = (lo, max(hi, b.box[2]), members + [b])
            else:
                columns.append((b.box[0], b.box[2], [b]))
        for _, _, members in columns:
            out.extend(sorted(members, key=lambda b: b.box[1]))
        band.clear()

    for b in sorted(blocks, key=lambda b: (b.box[1], b.box[0])):
        if b.box[2] - b.box[0] > SPANNING:
            caption = _caption_above(band, b)
            if caption is not None:
                band.remove(caption)
            flush()
            if caption is not None:
                out.append(caption)
            out.append(b)
        else:
            band.append(b)
    flush()
    return out


def _caption_above(band: list[Block], wide: Block) -> Block | None:
    """A short block sitting right above a full-width block (a table's caption or heading)
    belongs with it, not at the end of whichever column it happens to line up with."""
    if not band:
        return None
    lowest = max(band, key=lambda b: b.box[3])
    if lowest.kind == "text" and text_length(lowest.text) <= 12 and 0 <= wide.box[1] - lowest.box[3] < 0.04:
        return lowest
    return None


def merge_wrapped_lines(blocks: list[Block], page_height: float) -> list[Block]:
    """Some PDFs store every line as its own block. Join consecutive blocks (in reading order)
    that are lines of one paragraph: same left edge and font, gap under half a line."""
    out: list[Block] = []
    for b in blocks:
        prev = out[-1] if out else None
        if (
            prev is not None
            and prev.kind == b.kind == "text"
            and prev.page == b.page
            and prev.bold == b.bold
            and abs(prev.box[0] - b.box[0]) < 0.02
            and abs(prev.font_size - b.font_size) <= 0.1 * max(prev.font_size, 1.0)
            and 0 <= (b.box[1] - prev.box[3]) * page_height < 0.6 * b.font_size
        ):
            box = (min(prev.box[0], b.box[0]), prev.box[1], max(prev.box[2], b.box[2]), b.box[3])
            out[-1] = replace(prev, text=join_text(prev.text, b.text), box=box)
        else:
            out.append(b)
    return out


def table_markdown(rows: list[list[str | None]]) -> str:
    """Rows of cells (as PyMuPDF's Table.extract() returns them) → a Markdown table."""
    cleaned = [[" ".join((cell or "").split()) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return ""
    width = max(len(row) for row in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    lines = ["| " + " | ".join(cleaned[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(row) + " |" for row in cleaned[1:]]
    return "\n".join(lines)


def split_table(markdown: str, target: int) -> list[str]:
    """Split a large Markdown table by rows, repeating the header in every piece."""
    lines = markdown.split("\n")
    header, rows = lines[:2], lines[2:]
    pieces, current = [], []
    for row in rows:
        if current and text_length("\n".join(header + current + [row])) > target:
            pieces.append("\n".join(header + current))
            current = []
        current.append(row)
    if current or not pieces:
        pieces.append("\n".join(header + current))
    return pieces


# ---------------------------------------------------------------- chunking

def body_font_size(blocks: list[Block]) -> float:
    """Font size covering the most characters: the size of ordinary paragraphs."""
    weights: dict[float, int] = {}
    for b in blocks:
        if b.kind == "text":
            size = round(b.font_size, 1)
            weights[size] = weights.get(size, 0) + len(b.text)
    return max(weights, key=weights.__getitem__) if weights else 0.0


_NUMBERED = re.compile(r"^(\d+(\.\d+)*|[A-Z]|[IVX]+|第[一二三四五六七八九十百\d]+[章節条條])[.)、]?\s*\S")


def is_heading(block: Block, body_size: float) -> bool:
    if block.kind != "text":
        return False
    text = block.text.strip()
    length = text_length(text)
    if length == 0 or length > 12 or len(text) > 90 or re.search(r"[.!?;,。！？；，、]$", text):
        return False
    return block.font_size >= body_size * 1.15 or block.bold or bool(_NUMBERED.match(text))


def split_sentences(text: str, target: int) -> list[str]:
    pieces: list[str] = []
    current = ""
    for sentence in sentences(text):
        if current and text_length(join_text(current, sentence)) > target:
            pieces.append(current)
            current = ""
        current = join_text(current, sentence)
    if current:
        pieces.append(current)
    return pieces


@dataclass
class _Group:
    heading: Block | None = None
    parts: list[tuple[Block, str]] = field(default_factory=list)

    @property
    def length(self) -> int:
        return sum(text_length(t) for _, t in self.parts) + (text_length(self.heading.text) if self.heading else 0)

    def build(self) -> Chunk:
        blocks = ([self.heading] if self.heading else []) + [b for b, _ in self.parts]
        body = "\n\n".join(t for _, t in self.parts)
        text = f"{self.heading.text}\n{body}" if self.heading and body else (self.heading.text if self.heading else body)
        first, last = blocks[0], blocks[-1]
        return Chunk(
            text=text.strip(),
            page_start=first.page,
            page_end=last.page,
            para_start=first.para,
            para_end=last.para,
            boxes=tuple((b.page, *b.box) for b in dict.fromkeys(blocks)),
        )


def chunk(blocks: list[Block]) -> list[Chunk]:
    body = body_font_size(blocks)
    chunks: list[Chunk] = []
    current: _Group | None = None
    heading: Block | None = None

    def flush() -> None:
        nonlocal current
        if current is not None and current.parts:
            chunks.append(current.build())
        current = None

    for block in blocks:
        if is_heading(block, body):
            flush()
            if heading is not None:
                chunks.append(_Group(heading=heading).build())
            heading = block
            continue
        length = text_length(block.text)
        if block.kind in ("table", "figure") or length > MAX:
            flush()
            if block.kind == "table":
                pieces = [block.text] if length <= TABLE_MAX else split_table(block.text, TARGET * 2)
            elif block.kind == "figure":
                pieces = [block.text]
            else:
                pieces = split_sentences(block.text, TARGET)
            for i, piece in enumerate(pieces):
                chunks.append(_Group(heading=heading if i == 0 else None, parts=[(block, piece)]).build())
            heading = None
            continue
        if current is not None and (current.length >= TARGET or current.length + length > MAX):
            flush()
        if current is None:
            current, heading = _Group(heading=heading), None
        current.parts.append((block, block.text))
    flush()
    if heading is not None:
        chunks.append(_Group(heading=heading).build())
    return chunks


# ---------------------------------------------------------------- cleanup

_PAGE_NUMBER = re.compile(r"(page\s*)?\d+(\s*(of|/)\s*\d+)?|第?\s*\d+\s*頁", re.I)
EDGE = 0.1  # top / bottom 10% of a page


def drop_running_text(blocks: list[Block], pages: int) -> list[Block]:
    """Remove page headers and footers: blocks at the top or bottom edge that are page numbers
    or whose text (digits ignored) repeats on at least half the pages. Renumbers paragraphs."""

    def at_edge(b: Block) -> bool:
        return b.kind == "text" and (b.box[3] < EDGE or b.box[1] > 1 - EDGE)

    def key(b: Block) -> str:
        return re.sub(r"\d+", "#", b.text.strip().lower())

    counts: dict[str, int] = {}
    for b in blocks:
        if at_edge(b):
            counts[key(b)] = counts.get(key(b), 0) + 1
    repeated = {k for k, n in counts.items() if pages >= 2 and n >= max(2, pages // 2)}
    kept = [b for b in blocks if not (at_edge(b) and (key(b) in repeated or _PAGE_NUMBER.fullmatch(b.text.strip())))]
    out, para, page = [], 0, 0
    for b in kept:
        para = para + 1 if b.page == page else 1
        page = b.page
        out.append(replace(b, para=para))
    return out


def join_lines(lines: list[str]) -> str:
    """Join PDF lines into a paragraph: undo end-of-line hyphenation; no spaces inside CJK text."""
    out = ""
    for line in (l.strip() for l in lines):
        if not line:
            continue
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        elif joins_tightly(out, line):
            out += line
        else:
            out = f"{out} {line}" if out else line
    return out
