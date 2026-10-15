from __future__ import annotations

from decimal import Decimal

import pytest

from ragcat.curation.domain import (
    Box,
    Document,
    Passage,
    PassageEditor,
    Source,
    count_passages,
    lint,
    pending_ids,
    position_between,
)
from ragcat.shared.errors import InvalidState, NotFound, Unprocessable, ValidationError
from ragcat.shared.kernel import VectorSpec, wanted_hashes

SPEC = VectorSpec("test-model:8", contextual=True)
NOW = "2026-10-08T00:00:00Z"
LONG = "has enough words to read like an ordinary passage about returns, refunds and delivery times."


def make(n: int = 4, status: str = "review", embedded: bool = False) -> tuple[Document, list[Passage]]:
    doc = Document("doc_1", "ast_1", "owner", "f.pdf", 1, "k", status=status, page_count=5, next_label=n + 1)
    passages = []
    for i in range(n):
        text = f"Passage {i} {LONG}"
        passages.append(
            Passage(
                id=f"chk_{i}",
                document_id="doc_1",
                label=f"P-{i + 1}",
                text=text,
                original_text=text,
                origin="auto",
                source=Source(i + 1, i + 1, 1, 1, (Box(i + 1, 0.1, 0.2, 0.9, 0.4),)),
                position=Decimal(1024 * (i + 1)),
            )
        )
    if embedded:
        wanted = wanted_hashes(SPEC, [(p.id, p.text, False) for p in passages])
        for p in passages:
            p.embedded_hash = wanted[p.id][0]
    return doc, passages


def ids(editor: PassageEditor) -> list[str]:
    return [p.id for p in editor.visible()]


def test_edit_marks_origin_and_bumps_version() -> None:
    doc, ps = make()
    editor = PassageEditor(doc, ps, NOW)
    editor.edit("chk_1", f"  Rewritten passage {LONG}  ")
    changes = editor.commit()
    assert doc.edit_version == 1
    assert [p.id for p in changes.upserted] == ["chk_1"]
    assert ps[1].origin == "edited" and ps[1].text.startswith("Rewritten")


def test_edit_with_same_text_changes_nothing() -> None:
    doc, ps = make()
    editor = PassageEditor(doc, ps, NOW)
    editor.edit("chk_1", ps[1].text)
    assert editor.commit().empty and doc.edit_version == 0


def test_empty_text_is_rejected() -> None:
    doc, ps = make()
    with pytest.raises(ValidationError):
        PassageEditor(doc, ps, NOW).edit("chk_0", "   ")


@pytest.mark.parametrize("pair", [["chk_0", "chk_2"], ["chk_1", "chk_0"]])
def test_merge_requires_adjacent_passages_in_order(pair: list[str]) -> None:
    doc, ps = make()
    with pytest.raises(Unprocessable) as exc:
        PassageEditor(doc, ps, NOW).merge(pair)
    assert exc.value.code == "NOT_CONTIGUOUS"


def test_merge_removes_never_embedded_rows() -> None:
    doc, ps = make()
    editor = PassageEditor(doc, ps, NOW)
    merged = editor.merge(["chk_0", "chk_1"])
    changes = editor.commit()
    assert changes.removals == ["chk_1"] and changes.deleted == ["chk_1"]
    assert merged.origin == "merged" and "Passage 0" in merged.text and "Passage 1" in merged.text
    assert (merged.source.page_start, merged.source.page_end, len(merged.source.boxes)) == (1, 2, 2)
    assert ids(editor) == ["chk_0", "chk_2", "chk_3"]


def test_merge_soft_deletes_embedded_rows_so_vectors_can_be_removed() -> None:
    doc, ps = make(embedded=True)
    editor = PassageEditor(doc, ps, NOW)
    editor.merge(["chk_0", "chk_1"])
    changes = editor.commit()
    assert changes.removals == [] and ps[1].deleted
    assert "chk_1" in [p.id for p in changes.writes]
    counts = count_passages(ps, SPEC)
    assert (counts.pending, counts.removed, counts.pending_changes) == (1, 1, 2)


def test_split_requires_parts_that_add_up() -> None:
    doc, ps = make()
    with pytest.raises(Unprocessable) as exc:
        PassageEditor(doc, ps, NOW).split("chk_0", ["foo", "bar"])
    assert exc.value.code == "SPLIT_MISMATCH"


def test_split_keeps_order_and_slices_boxes() -> None:
    doc, ps = make()
    text = ps[0].text
    editor = PassageEditor(doc, ps, NOW)
    first, second = editor.split("chk_0", [text[:30], text[30:]])
    assert first.id == "chk_0" and second.label == "P-5"
    assert ids(editor)[:3] == ["chk_0", second.id, "chk_1"]
    assert first.source.boxes[0].y1 < 0.4 and second.source.boxes[0].y0 > 0.2
    assert first.origin == second.origin == "split"


def test_add_after_and_at_top() -> None:
    doc, ps = make()
    editor = PassageEditor(doc, ps, NOW)
    end = editor.add("chk_3", f"New {LONG}")
    top = editor.add(None, f"Top {LONG}")
    assert ids(editor)[0] == top.id and ids(editor)[-1] == end.id
    assert end.origin == "added" and end.original_text is None and end.source.page_start == 4


def test_restore_reverts_edit_but_not_added_passages() -> None:
    doc, ps = make()
    editor = PassageEditor(doc, ps, NOW)
    original = ps[2].text
    editor.edit("chk_2", f"Changed {LONG}")
    editor.restore("chk_2")
    assert ps[2].text == original and ps[2].origin == "auto"
    added = editor.add("chk_2", f"Added {LONG}")
    with pytest.raises(Unprocessable) as exc:
        editor.restore(added.id)
    assert exc.value.code == "CANNOT_RESTORE"


def test_editing_is_blocked_while_parsing() -> None:
    doc, ps = make(status="parsing")
    with pytest.raises(InvalidState):
        PassageEditor(doc, ps, NOW)


def test_ready_document_returns_to_review_after_edit() -> None:
    doc, ps = make(status="ready", embedded=True)
    editor = PassageEditor(doc, ps, NOW)
    editor.delete("chk_3")
    editor.commit()
    assert doc.status == "review"


def test_unknown_passage_is_not_found() -> None:
    doc, ps = make()
    with pytest.raises(NotFound):
        PassageEditor(doc, ps, NOW).delete("chk_missing")


def test_lint_codes() -> None:
    assert [w.code for w in lint("Returns policy")] == ["HEADING_ONLY"]
    assert [w.code for w in lint("Too short to help.")] == ["TOO_SHORT"]
    assert "TOO_LONG" in [w.code for w in lint(" ".join(["word"] * 310) + ".")]
    assert "TABLE_FRAGMENT" in [w.code for w in lint("Size 1 2 3 4 5 6 7 8 9 grams.")]
    assert lint(f"Passage {LONG}") == []


def test_positions_stay_ordered_under_repeated_bisection() -> None:
    lo, hi = Decimal(1024), Decimal(2048)
    for _ in range(100):
        mid = position_between(lo, hi)
        assert lo < mid < hi
        hi = mid


def test_editing_a_heading_makes_its_section_pending_when_contextual() -> None:
    doc, ps = make(embedded=True)
    ps[1].text = "Returns\nPassage 1 " + LONG  # P-2 now starts a section that P-3 and P-4 fall under
    assert pending_ids(ps, SPEC) == {"chk_1", "chk_2", "chk_3"}
    assert pending_ids(ps, VectorSpec("test-model:8", contextual=False)) == {"chk_0", "chk_1", "chk_2", "chk_3"}  # different vector space
