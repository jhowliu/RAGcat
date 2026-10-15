from __future__ import annotations

import pymupdf
from conftest import RETURNS_PDF_PAGES, make_figure_pdf, make_pdf

from ragcat.curation.domain import lint
from ragcat.ingestion.adapters import PdfFile
from ragcat.ingestion.domain import (
    MAX,
    Block,
    chunk,
    figure_passage_text,
    drop_running_text,
    join_lines,
    merge_wrapped_lines,
    reading_order,
    split_table,
    table_markdown,
)
from ragcat.shared.text import sentences, text_length


def block(text: str, size: float = 11, bold: bool = False, page: int = 1, para: int = 1, box=(0.1, 0.1, 0.9, 0.2), kind: str = "text") -> Block:
    return Block(page, para, text, box, size, bold, kind)


BODY = "Customers can return unopened items within thirty days for a refund of the full price paid."
ZH = "未開封的商品可以在收到後三十天內退貨並全額退款。已開封的商品除非有瑕疵，否則不接受退貨。請附上訂單編號與商品照片聯絡客服。"


# ---------------------------------------------------------------- text measures

def test_cjk_text_is_measured_in_characters() -> None:
    assert text_length("one two three") == 3
    assert text_length("退貨政策說明") == 4  # 6 characters / 1.5
    assert text_length("Mochi 寵物食品") == 1 + 3


def test_sentences_split_on_cjk_punctuation_without_spaces() -> None:
    assert sentences(ZH) == [
        "未開封的商品可以在收到後三十天內退貨並全額退款。",
        "已開封的商品除非有瑕疵，否則不接受退貨。",
        "請附上訂單編號與商品照片聯絡客服。",
    ]
    assert sentences("Ship by Friday. e.g. tomorrow. Done!") == ["Ship by Friday. e.g. tomorrow.", "Done!"]


def test_join_lines_undoes_hyphenation_and_keeps_cjk_tight() -> None:
    assert join_lines(["The deliv-", "ery arrives", "", "tomorrow."]) == "The delivery arrives tomorrow."
    assert join_lines(["未開封的商品可以", "在三十天內退貨。"]) == "未開封的商品可以在三十天內退貨。"


# ---------------------------------------------------------------- chunking

def test_heading_attaches_to_the_following_paragraph() -> None:
    chunks = chunk([block("Returns", 16), block(BODY), block(BODY)])
    assert len(chunks) == 1 and chunks[0].text.startswith("Returns\n")


def test_consecutive_headings_leave_a_heading_only_passage() -> None:
    chunks = chunk([block("Policies", 18), block("Returns", 16), block(BODY)])
    assert [c.text.split("\n")[0] for c in chunks] == ["Policies", "Returns"]


def test_long_paragraph_is_split_on_sentences() -> None:
    chunks = chunk([block(" ".join([BODY] * 25))])
    assert len(chunks) > 1 and all(text_length(c.text) <= MAX for c in chunks)


def test_long_chinese_paragraph_is_split_into_comparable_sizes() -> None:
    chunks = chunk([block("第一章 退貨政策", 16), block(ZH * 12)])
    assert len(chunks) > 1 and all(text_length(c.text) <= MAX for c in chunks)
    assert chunks[0].text.startswith("第一章 退貨政策\n")
    assert " " not in chunks[1].text  # sentences re-joined without spaces


def test_running_headers_and_page_numbers_are_dropped() -> None:
    def edge(text: str, page: int, top: bool = True) -> Block:
        return block(text, 8, page=page, box=(0.1, 0.02, 0.9, 0.05) if top else (0.1, 0.95, 0.9, 0.98))

    blocks = [edge("Mochi Pet Co. 1", 1), block(BODY, page=1, para=2), edge("3", 1, top=False), edge("Mochi Pet Co. 2", 2), block(BODY, page=2, para=2)]
    kept = drop_running_text(blocks, pages=2)
    assert [b.text for b in kept] == [BODY, BODY] and [b.para for b in kept] == [1, 1]


# ---------------------------------------------------------------- layout and tables

def test_two_columns_are_read_column_by_column() -> None:
    title = block("Title", box=(0.1, 0.05, 0.9, 0.08))
    left = [block(f"L{i}", box=(0.08, 0.1 + i * 0.1, 0.48, 0.18 + i * 0.1)) for i in range(3)]
    right = [block(f"R{i}", box=(0.52, 0.11 + i * 0.1, 0.92, 0.19 + i * 0.1)) for i in range(3)]
    footer = block("Full width note", box=(0.1, 0.8, 0.9, 0.85))
    interleaved = [title, left[0], right[0], left[1], right[1], left[2], right[2], footer]
    assert [b.text for b in reading_order(interleaved)] == ["Title", "L0", "L1", "L2", "R0", "R1", "R2", "Full width note"]


def test_caption_above_a_full_width_table_stays_with_it() -> None:
    left = [block(f"L{i}", box=(0.08, 0.1 + i * 0.1, 0.48, 0.18 + i * 0.1)) for i in range(3)]
    right = [block(f"R{i}", box=(0.52, 0.1 + i * 0.1, 0.92, 0.18 + i * 0.1)) for i in range(2)]
    caption = block("Feeding table", box=(0.08, 0.45, 0.3, 0.47))
    table = block("| a | b |\n|---|---|", box=(0.08, 0.48, 0.8, 0.6), kind="table")
    order = [b.text for b in reading_order(left + right + [caption, table])]
    assert order == ["L0", "L1", "L2", "R0", "R1", "Feeding table", table.text]


def test_wrapped_lines_stored_as_separate_blocks_are_joined() -> None:
    lines = [block("成犬每天餵食兩次，早晚各一", 10.5, box=(0.1, 0.10, 0.45, 0.112)), block("次。幼犬建議少量多餐。", 10.5, box=(0.1, 0.116, 0.4, 0.128))]
    next_para = block("新段落。", 10.5, box=(0.1, 0.16, 0.2, 0.172))
    merged = merge_wrapped_lines(lines + [next_para], page_height=842)
    assert [b.text for b in merged] == ["成犬每天餵食兩次，早晚各一次。幼犬建議少量多餐。", "新段落。"]


def test_single_column_order_is_unchanged() -> None:
    blocks = [block("Heading", box=(0.1, 0.1, 0.3, 0.12)), block(BODY, box=(0.1, 0.13, 0.9, 0.2)), block("Next", box=(0.1, 0.21, 0.25, 0.23))]
    assert reading_order(blocks) == blocks


def test_table_becomes_one_markdown_passage_with_its_heading() -> None:
    md = table_markdown([["Region", "Standard", "Express"], ["Metro", "9.95", None], [None, None, None], ["Remote\nAU", "18.95", "29.95"]])
    assert md.split("\n") == ["| Region | Standard | Express |", "|---|---|---|", "| Metro | 9.95 |  |", "| Remote AU | 18.95 | 29.95 |"]
    chunks = chunk([block("Delivery fees", 16), block(md, kind="table"), block(BODY)])
    assert [c.text.split("\n")[0] for c in chunks] == ["Delivery fees", BODY]
    assert lint(chunks[0].text) == []  # a whole table is not a "table fragment"
    assert [w.code for w in lint("Metro 9.95 14.95 Regional 12.95 19.95")] == ["TABLE_FRAGMENT"]


def test_huge_table_is_split_by_rows_with_the_header_repeated() -> None:
    md = table_markdown([["Item", "Notes"]] + [[f"Row {i}", "words " * 20] for i in range(60)])
    pieces = split_table(md, 280)
    assert len(pieces) > 1 and all(p.startswith("| Item | Notes |\n|---|---|") for p in pieces)


# ---------------------------------------------------------------- real PDFs

def test_pdf_reader_extracts_blocks_and_renders_pages() -> None:
    pdf = PdfFile(make_pdf(RETURNS_PDF_PAGES))
    assert pdf.page_count == 2 and not pdf.needs_password
    blocks = pdf.blocks(0)
    assert blocks[0].text == "Returns policy" and blocks[0].bold
    assert all(0 <= v <= 1 for b in blocks for v in b.box)
    assert pdf.render(0).startswith(b"\xff\xd8")  # JPEG
    passages = chunk(blocks + pdf.blocks(1))
    assert [p.text.split("\n")[0] for p in passages] == ["Returns policy", "Shipping", "Pet food storage"]


def test_pdf_with_two_columns_a_ruled_table_and_chinese_text() -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 60), "Feeding guide", fontsize=18, fontname="hebo")
    for i, x in enumerate((72, 316)):  # two columns of three paragraphs
        for j in range(3):
            page.insert_textbox(pymupdf.Rect(x, 90 + j * 60, x + 220, 140 + j * 60), f"Column {i} paragraph {j} about portions and timing.", fontsize=10, fontname="helv")
    y = 300
    for r, row in enumerate([("Weight", "Daily"), ("5 kg", "80 g"), ("10 kg", "140 g")]):  # ruled 3x2 table
        for c, cell in enumerate(row):
            rect = pymupdf.Rect(72 + c * 120, y + r * 22, 192 + c * 120, y + (r + 1) * 22)
            page.draw_rect(rect, width=0.6)
            page.insert_textbox(rect + (4, 5, -4, 0), cell, fontsize=10, fontname="helv")
    page.insert_text((72, 420), "未開封的商品可以在三十天內退貨。", fontsize=11, fontname="china-t")
    pdf = PdfFile(doc.tobytes())

    texts = [(b.kind, b.text) for b in pdf.blocks(0)]
    assert texts[0] == ("text", "Feeding guide")
    columns = [t for k, t in texts if t.startswith("Column")]
    assert columns == [f"Column {i} paragraph {j} about portions and timing." for i in range(2) for j in range(3)]
    tables = [t for k, t in texts if k == "table"]
    assert tables == ["| Weight | Daily |\n|---|---|\n| 5 kg | 80 g |\n| 10 kg | 140 g |"]
    assert not any("80 g" in t for k, t in texts if k == "text")  # table text is not duplicated
    assert ("text", "未開封的商品可以在三十天內退貨。") in texts


# ---------------------------------------------------------------- figures

def test_figure_becomes_its_own_passage_with_its_heading() -> None:
    text = figure_passage_text("Figure 1. Average delivery days", "A bar chart: Metro 2, Regional 4, Remote 6 days.")
    chunks = chunk([block("Delivery report", 16), block(text, kind="figure"), block(BODY)])
    assert [c.text.split("\n")[:2] for c in chunks] == [
        ["Delivery report", "Figure 1. Average delivery days"],
        [BODY],
    ]
    assert "[Figure] A bar chart" in chunks[0].text


def test_pdf_figures_skip_logos_and_keep_their_labels_and_caption() -> None:
    pdf = PdfFile(make_figure_pdf())
    blocks, figures = pdf.read_page(0)
    assert len(figures) == 2  # the photo and the chart; the repeated logo is skipped
    photo, chart = figures
    assert photo.box[0] < 0.2 and photo.image.startswith(b"\xff\xd8")
    assert chart.caption == "Figure 1. Average delivery days by region"
    assert all(label in chart.inner_text for label in ("Metro", "Regional", "Remote"))
    texts = [b.text for b in blocks if b.kind == "text"]
    assert not any("Metro" in t or "Figure 1" in t for t in texts)  # labels and caption moved into the figure
    assert [b.kind for b in blocks] == ["text", "figure", "figure", "text"]
    assert pdf.read_page(1)[1] == []  # only the logo on page two
