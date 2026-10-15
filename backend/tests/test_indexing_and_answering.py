from __future__ import annotations

import json

import pytest

from ragcat.answering.domain import NO_ANSWER, build_prompt, citations_for, merge_preview
from ragcat.indexing.domain import MAX_ENTITIES, PassageContext, PassageState, embedding_input, parse_context, plan_reconcile
from ragcat.infra.models import FakeEmbedder, FakeLlm
from ragcat.infra.vectors import Hit
from ragcat.shared.kernel import VectorSpec, heading_of, sections

SPEC = VectorSpec("model-a:8")


def state(pid: str, text: str, deleted: bool = False, embedded: str | None = None) -> PassageState:
    return PassageState(pid, text, deleted, SPEC.hash(embedded) if embedded is not None else None)


def test_reconcile_plan_covers_every_case() -> None:
    plan = plan_reconcile(
        [
            state("same", "unchanged", embedded="unchanged"),
            state("edited", "new words", embedded="old words"),
            state("added", "brand new"),
            state("removed", "gone", deleted=True, embedded="gone"),
            state("never", "added then deleted", deleted=True),
        ],
        SPEC,
    )
    assert [p.passage.id for p in plan.puts] == ["edited", "added"]
    assert plan.puts[0].hash == SPEC.hash("new words")
    assert plan.deletes == ["removed"]
    assert plan.purges == ["removed", "never"]
    assert plan.work == 3


def test_deleting_a_document_removes_every_vector() -> None:
    plan = plan_reconcile([state("a", "x", embedded="x"), state("b", "y")], SPEC, document_deleting=True)
    assert plan.puts == [] and plan.deletes == ["a"] and plan.purges == []


def test_changing_embedding_model_reembeds_everything() -> None:
    plan = plan_reconcile([state("a", "x", embedded="x"), state("b", "y", embedded="y")], VectorSpec("model-b:8"))
    assert [p.passage.id for p in plan.puts] == ["a", "b"]
    assert [p.passage.id for p in plan_reconcile([state("a", "x", embedded="x")], VectorSpec("model-a:8", contextual=True)).puts] == ["a"]


def hits() -> list[Hit]:
    meta = {"document_id": "doc_1", "document_title": "returns.pdf", "para": 2, "boxes": "[]"}
    return [
        Hit("chk_a", 0.9, meta | {"label": "P-1", "page": 3, "edited": True, "text": "Opened items cannot be returned unless defective."}),
        Hit("chk_b", 0.8, meta | {"label": "P-2", "page": 4, "edited": False, "text": "Orders ship within two business days."}),
    ]


def test_citations_follow_first_mention_and_ignore_unknown_numbers() -> None:
    cites = citations_for("Ships fast [2]. Opened items no [1]. Again [2] and [7].", hits())
    assert [(c.n, c.chunk_id, c.page) for c in cites] == [(2, "chk_b", 4), (1, "chk_a", 3)]
    assert cites[1].edited is True


def test_fake_llm_answers_from_the_best_passage_or_declines() -> None:
    system, prompt = build_prompt("Mochi", "Can opened items be returned?", hits())
    assert "[1] returns.pdf · p.3" in prompt
    answer = "".join(FakeLlm().stream(system, prompt))
    assert answer.endswith("[1]")
    _, unrelated = build_prompt("Mochi", "What is the capital of France?", hits())
    assert "".join(FakeLlm().stream(system, unrelated)) == NO_ANSWER


def test_fake_embedder_is_deterministic_and_lexical() -> None:
    e = FakeEmbedder(256)
    a, b, c = e.embed(["opened items returned", "can opened items be returned", "express shipping metro"])
    assert a == e.embed(["opened items returned"])[0]
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731
    assert dot(a, b) > dot(a, c)


def test_sections_follow_the_most_recent_heading() -> None:
    texts = ["Returns policy", "1. Who can return\nOrders can be returned.", "More detail without a heading.", "| a | b |\n|---|---|", "第二章 運送\n訂單兩天內出貨。"]
    assert sections(texts) == ["Returns policy", "1. Who can return", "1. Who can return", "1. Who can return", "第二章 運送"]
    assert heading_of("Figure 1. Average days") is None and heading_of("Orders ship fast.") is None


def test_contextual_plan_carries_each_passages_section() -> None:
    spec = VectorSpec("model-a:8", contextual=True)
    plan = plan_reconcile([PassageState("h", "Shipping\nOrders ship in two days.", False, None), PassageState("b", "Express is next day.", False, None)], spec)
    assert [(p.passage.id, p.section) for p in plan.puts] == [("h", "Shipping"), ("b", "Shipping")]


def test_fake_llm_writes_a_context_naming_document_and_section() -> None:
    from ragcat.indexing.domain import context_prompt

    reply = FakeLlm().complete(context_prompt("returns-policy", "2. Opened items", "Opened items cannot be returned."), 1000)
    assert parse_context(reply) == PassageContext("This passage is from returns-policy, in the section “2. Opened items”.", (("policy", "2. Opened items"),))


def test_parse_context_reads_context_and_entities_from_the_reply() -> None:
    reply = json.dumps({
        "context": "  From the\nreturns policy. ",
        "entities": [
            {"name": "Mochi Kibble", "type": "product"},
            {"name": "30  days", "type": "period"},
            {"name": "Mochi Kibble", "type": "product"},  # duplicate
            {"name": "Tuesday", "type": "weekday"},  # not in the ontology
            {"name": "", "type": "fee"},
            {"type": "fee"},
            "loose string",
        ],
    })
    expected = PassageContext("From the returns policy.", (("product", "Mochi Kibble"), ("period", "30 days")))
    assert parse_context(reply) == expected
    assert parse_context(f"Here you go:\n```json\n{reply}\n```") == expected
    assert parse_context('{"context": "Only context."}') == PassageContext("Only context.")
    assert parse_context('{"context": "x", "entities": "none"}') == PassageContext("x")


def test_parse_context_caps_entities() -> None:
    reply = json.dumps({"context": "x", "entities": [{"name": f"item {i}", "type": "product"} for i in range(MAX_ENTITIES + 5)]})
    assert len(parse_context(reply).entities) == MAX_ENTITIES


@pytest.mark.parametrize("reply", ["The passage is about returns.", '{"context": "cut off', '{"entities": []}', '{"context": 3}', "[]"])
def test_parse_context_rejects_a_reply_that_is_not_the_requested_json(reply: str) -> None:
    with pytest.raises(ValueError):
        parse_context(reply)


def test_embedding_input_puts_context_and_entities_before_the_text() -> None:
    context = PassageContext("From the returns policy.", (("product", "Mochi Kibble"), ("period", "30 days")))
    assert embedding_input(context, "Body.") == "From the returns policy.\nEntities: Mochi Kibble (product), 30 days (period)\n\nBody."
    assert embedding_input(PassageContext("Only context."), "Body.") == "Only context.\n\nBody."
    assert embedding_input(PassageContext(), "Body.") == "Body."


def test_local_vector_index_sees_writes_from_another_process(tmp_path) -> None:
    from ragcat.infra.vectors import LocalVectorIndex, VectorItem

    api, worker = LocalVectorIndex(tmp_path), LocalVectorIndex(tmp_path)  # two processes share the file
    assert api.query([1.0, 0.0], 5, "a", []) == []
    worker.put([VectorItem("p1", [1.0, 0.0], {"assistant_id": "a", "document_id": "d"})])
    assert [h.key for h in api.query([1.0, 0.0], 5, "a", [])] == ["p1"]
    worker.put([VectorItem("p2", [0.0, 1.0], {"assistant_id": "a", "document_id": "d"})])
    api.delete(["p1"])
    assert [h.key for h in worker.query([0.0, 1.0], 5, "a", [])] == ["p2"]


def test_merge_preview_replaces_stale_live_hits_with_preview_hits() -> None:
    live = [Hit("edited", 0.9, {}), Hit("removed", 0.8, {}), Hit("same", 0.5, {})]
    preview = [Hit("edited", 0.4, {"text": "new"}), Hit("added", 0.7, {})]
    merged = merge_preview(live, {"edited", "removed"}, preview, 3)
    assert [(h.key, h.score) for h in merged] == [("added", 0.7), ("same", 0.5), ("edited", 0.4)]
    assert merged[2].metadata == {"text": "new"}
