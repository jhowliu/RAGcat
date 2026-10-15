"""PyMuPDF reader: text blocks, tables and figures with positions (in reading order), page sizes,
page images."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pymupdf

from ragcat.ingestion.domain import Block, Figure, is_caption, join_lines, merge_wrapped_lines, reading_order, table_markdown

BOLD_FLAG = 16
FIGURE_MIN_AREA = 0.04  # of the page; smaller images are icons and decorations
FIGURE_MIN_SIDE = 0.05  # thinner drawings are rules and separators
FIGURE_MARGIN = 12  # pt around a figure whose text counts as the figure's labels
FIGURE_MAX_PIXELS = 1200  # longest side of the crop sent to the vision model


def _inside(box: tuple[float, float, float, float], area: tuple[float, float, float, float]) -> bool:
    """True when most of `box` lies within `area`."""
    x0, y0 = max(box[0], area[0]), max(box[1], area[1])
    x1, y1 = min(box[2], area[2]), min(box[3], area[3])
    overlap = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    size = max(1e-6, (box[2] - box[0]) * (box[3] - box[1]))
    return overlap / size > 0.5


class PdfFile:
    def __init__(self, data: bytes) -> None:
        self.doc = pymupdf.open(stream=data, filetype="pdf")
        self._repeated_images: set[int] | None = None

    @property
    def page_count(self) -> int:
        return self.doc.page_count

    @property
    def needs_password(self) -> bool:
        return bool(self.doc.needs_pass)

    def page_size(self, index: int) -> tuple[float, float]:
        rect = self.doc[index].rect
        return rect.width, rect.height

    def blocks(self, index: int) -> list[Block]:
        return self.read_page(index)[0]

    def read_page(self, index: int) -> tuple[list[Block], list[Figure]]:
        page = self.doc[index]
        width, height = page.rect.width, page.rect.height

        def norm(b: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            return (max(0.0, b[0] / width), max(0.0, b[1] / height), min(1.0, b[2] / width), min(1.0, b[3] / height))

        out: list[Block] = []

        # Tables first: their ruling lines must not be mistaken for figures.
        tables: list[tuple[float, float, float, float]] = []
        try:
            found = page.find_tables().tables
        except Exception:  # table detection is best effort; fall back to plain text blocks
            found = []
        for table in found:
            markdown = table_markdown(table.extract())
            if markdown:
                tables.append(tuple(table.bbox))
                out.append(Block(index + 1, 0, markdown, norm(tuple(table.bbox)), 0.0, False, kind="table"))

        figure_rects = self._figure_rects(page, tables)
        absorbed: list[list[str]] = [[] for _ in figure_rects]

        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0 or any(_inside(block["bbox"], t) for t in tables):
                continue
            lines, sized, bold_chars, chars = [], 0.0, 0, 0
            for line in block["lines"]:
                lines.append("".join(span["text"] for span in line["spans"]))
                for span in line["spans"]:
                    n = len(span["text"].strip())
                    chars += n
                    sized += span["size"] * n
                    if span["flags"] & BOLD_FLAG:
                        bold_chars += n
            text = join_lines(lines)
            if not text or chars == 0:
                continue
            owner = next((i for i, r in enumerate(figure_rects) if _inside(block["bbox"], tuple(r + (-FIGURE_MARGIN, -FIGURE_MARGIN, FIGURE_MARGIN, FIGURE_MARGIN)))), None)
            if owner is not None:
                absorbed[owner].append(text)  # chart labels belong to the figure, not to the passages
                figure_rects[owner] |= pymupdf.Rect(block["bbox"])  # and the crop should show them
                continue
            out.append(Block(index + 1, 0, text, norm(block["bbox"]), sized / chars, bold_chars >= 0.6 * chars))

        figures: dict[str, Figure] = {}
        for n, rect in enumerate(figure_rects, 1):
            key = f"{index + 1}:{n}"
            captions = [t for t in absorbed[n - 1] if is_caption(t)]
            inner = [t for t in absorbed[n - 1] if not is_caption(t)]
            dpi = min(150, int(FIGURE_MAX_PIXELS * 72 / max(rect.width, rect.height)))
            image = page.get_pixmap(clip=rect, dpi=dpi).tobytes("jpeg", jpg_quality=85)
            figures[key] = Figure(key, index + 1, norm(tuple(rect)), image, "\n".join(inner), captions[0] if captions else "")
            out.append(Block(index + 1, 0, key, norm(tuple(rect)), 0.0, False, kind="figure"))

        ordered = merge_wrapped_lines(reading_order(out), height)
        # A caption printed right after a figure belongs to it.
        kept: list[Block] = []
        for b in ordered:
            prev = kept[-1] if kept else None
            if prev is not None and prev.kind == "figure" and b.kind == "text" and is_caption(b.text) and not figures[prev.text].caption:
                figures[prev.text] = replace(figures[prev.text], caption=b.text)
                continue
            kept.append(b)
        return [replace(b, para=i + 1) for i, b in enumerate(kept)], list(figures.values())

    def _figure_rects(self, page: pymupdf.Page, tables: list[tuple[float, float, float, float]]) -> list[pymupdf.Rect]:
        area = page.rect.width * page.rect.height
        candidates = [pymupdf.Rect(info["bbox"]) & page.rect for info in page.get_image_info(xrefs=True) if info.get("xref", 0) not in self._logos()]
        try:
            candidates += [pymupdf.Rect(r) & page.rect for r in page.cluster_drawings()]
        except Exception:
            pass
        rects: list[pymupdf.Rect] = []
        for r in candidates:
            if r.is_empty or r.width * r.height < FIGURE_MIN_AREA * area:
                continue
            if min(r.width / page.rect.width, r.height / page.rect.height) < FIGURE_MIN_SIDE:
                continue
            if any(_inside(tuple(r), t) for t in tables):
                continue
            for i, existing in enumerate(rects):
                if existing.intersects(r):
                    rects[i] = existing | r
                    break
            else:
                rects.append(r)
        return rects

    def _logos(self) -> set[int]:
        """Images repeated on at least half the pages (logos, letterheads) are not figures."""
        if self._repeated_images is None:
            counts = Counter(xref for page in self.doc for xref in {img[0] for img in page.get_images()})
            pages = self.doc.page_count
            self._repeated_images = {x for x, n in counts.items() if pages >= 2 and n >= max(2, pages // 2)}
        return self._repeated_images

    def render(self, index: int, dpi: int = 110) -> bytes:
        return self.doc[index].get_pixmap(dpi=dpi).tobytes("jpeg", jpg_quality=80)

    def close(self) -> None:
        self.doc.close()
