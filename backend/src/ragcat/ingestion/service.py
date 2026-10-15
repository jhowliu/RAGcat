"""Ingestion: checking the file → reading pages (and describing figures) → organizing into Passages (api-design.md §1)."""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Callable

from ragcat.curation.service import Box, Cancelled, CurationService, ImportedPassage, Source
from ragcat.identity.service import IdentityService
from ragcat.infra.models import VisionModel
from ragcat.infra.storage import ObjectStore
from ragcat.ingestion.adapters import PdfFile
from ragcat.ingestion.domain import (
    FIGURE_LIMIT,
    Block,
    Figure,
    IngestError,
    chunk,
    describe_prompt,
    drop_running_text,
    figure_passage_text,
)
from ragcat.shared.errors import UpstreamUnavailable

log = logging.getLogger("ragcat.ingestion")

MAX_PAGES = 300
PROGRESS_EVERY_PAGES = 5
PROGRESS_EVERY_SECONDS = 2.0
VISION_CONCURRENCY = 4


def document_id_from_key(key: str) -> str:
    """uploads/{assistant_id}/{document_id}.pdf → document_id"""
    return key.rsplit("/", 1)[-1].removesuffix(".pdf")


class IngestionService:
    def __init__(
        self,
        curation: CurationService,
        identity: IdentityService,
        store: ObjectStore,
        vision: VisionModel,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.curation = curation
        self.identity = identity
        self.store = store
        self.vision = vision
        self.monotonic = monotonic

    def run(self, object_key: str) -> None:
        did = document_id_from_key(object_key)
        doc = self.curation.start_parsing(did)
        if doc is None:
            log.info("Skipping %s: not awaiting upload (duplicate delivery or cancelled)", did)
            return
        try:
            self._parse(did, doc.object_key, doc.owner_id, doc.progress["started_at"])
        except Cancelled:
            log.info("Stopped parsing %s: document left the parsing state", did)
        except IngestError as exc:
            self.curation.fail(did, exc.code, exc.message)

    def _parse(self, did: str, key: str, owner_id: str, started_at: str) -> None:
        data = self.store.get(key)
        if b"%PDF-" not in data[:1024]:
            raise IngestError("NOT_A_PDF", "This file is not a PDF.")
        try:
            pdf = PdfFile(data)
        except Exception as exc:
            raise IngestError("PARSE_ERROR", "The PDF could not be opened.") from exc
        try:
            if pdf.needs_password:
                raise IngestError("ENCRYPTED_PDF", "The PDF is password protected.")
            pages = pdf.page_count
            if pages == 0:
                raise IngestError("PARSE_ERROR", "The PDF has no pages.")
            if pages > MAX_PAGES:
                raise IngestError("TOO_MANY_PAGES", f"The PDF has {pages} pages; the limit is {MAX_PAGES}.")
            if not self.identity.pages_available(owner_id, pages):
                raise IngestError("QUOTA_EXCEEDED", "Not enough pages left on your plan.")

            def progress(stage: str, done: int = 0, total: int = 0) -> dict:
                return {"stage": stage, "done": done, "total": total, "started_at": started_at}

            self.curation.report_progress(did, progress("reading_pages", 0, pages), page_count=pages)
            blocks: list[Block] = []
            figures: dict[str, Figure] = {}
            sizes: list[tuple[float, float]] = []
            unbilled, last_report = 0, self.monotonic()
            for i in range(pages):
                page_blocks, page_figures = pdf.read_page(i)
                blocks.extend(page_blocks)
                figures.update((f.key, f) for f in page_figures)
                sizes.append(pdf.page_size(i))
                self.store.put(f"pages/{did}/{i + 1}.jpg", pdf.render(i), "image/jpeg")
                unbilled += 1
                done = i + 1
                if done % PROGRESS_EVERY_PAGES == 0 or self.monotonic() - last_report >= PROGRESS_EVERY_SECONDS or done == pages:
                    self.identity.add_pages(owner_id, unbilled)  # pages already read still count
                    unbilled, last_report = 0, self.monotonic()
                    self.curation.report_progress(did, progress("reading_pages", done, pages))
            blocks = drop_running_text(blocks, pages)
            if sum(len(b.text) for b in blocks if b.kind != "figure") < 20 and not figures:
                raise IngestError("NO_TEXT", "No text found. Scanned PDFs are not supported yet.")
            if figures:
                blocks = self._describe_figures(did, blocks, figures, progress)
            self.curation.report_progress(did, progress("organizing_passages"))
            passages = [
                ImportedPassage(
                    text=c.text,
                    source=Source(c.page_start, c.page_end, c.para_start, c.para_end, tuple(Box(*b) for b in c.boxes)),
                )
                for c in chunk(blocks)
            ]
            if not passages:
                raise IngestError("NO_TEXT", "No text or informative figures found.")
            self.curation.import_parsed(did, passages, sizes)
        finally:
            pdf.close()

    def _describe_figures(self, did: str, blocks: list[Block], figures: dict[str, Figure], progress: Callable[..., dict]) -> list[Block]:
        """Replace each figure placeholder with a vision-model description; drop decorative or
        undescribed figures. At most FIGURE_LIMIT per document, VISION_CONCURRENCY at a time."""
        chosen = [b.text for b in blocks if b.kind == "figure"][:FIGURE_LIMIT]
        descriptions: dict[str, str] = {}
        self.curation.report_progress(did, progress("describing_figures", 0, len(chosen)))
        last_report = self.monotonic()
        pool = ThreadPoolExecutor(max_workers=VISION_CONCURRENCY)
        try:
            futures = {pool.submit(self._describe, figures[key]): key for key in chosen}
            for done, future in enumerate(as_completed(futures), 1):
                description = future.result()
                if description:
                    descriptions[futures[future]] = description
                if self.monotonic() - last_report >= PROGRESS_EVERY_SECONDS or done == len(chosen):
                    last_report = self.monotonic()
                    self.curation.report_progress(did, progress("describing_figures", done, len(chosen)))
        finally:
            pool.shutdown(wait=False, cancel_futures=True)  # on cancel, skip the figures not started yet
        out = []
        for b in blocks:
            if b.kind != "figure":
                out.append(b)
            elif b.text in descriptions:
                figure = figures[b.text]
                out.append(replace(b, text=figure_passage_text(figure.caption, descriptions[b.text])))
        return out

    def _describe(self, figure: Figure) -> str | None:
        hints = "\n".join(t for t in (figure.caption, figure.inner_text) if t)
        try:
            text = self.vision.describe(figure.image, describe_prompt(hints))
        except UpstreamUnavailable:
            log.warning("Could not describe figure %s; leaving it out", figure.key, exc_info=True)
            return None
        return None if not text or text.strip().upper().startswith("DECORATIVE") else text.strip()
