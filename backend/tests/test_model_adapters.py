"""Provider contracts through the real adapter interfaces; no model calls or credentials."""

from __future__ import annotations

import json
from dataclasses import replace
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from botocore.exceptions import ClientError

from ragcat.answering.domain import Caller
from ragcat.answering.service import AnsweringService, collect
from ragcat.assistants.domain import AssistantConfig
from ragcat.indexing.domain import PassageState, plan_reconcile
from ragcat.indexing.service import IndexingService
from ragcat.infra import model_adapters, models, vectors
from ragcat.infra.cache import MemoryCache
from ragcat.infra.claude import ClaudeLlm
from ragcat.infra.models import BedrockEmbedder, BedrockLlm, FakeEmbedder, FakeLlm, LlmStream
from ragcat.infra.openai import OpenAiEmbedder
from ragcat.infra.vectors import LocalVectorIndex, S3VectorIndex, VectorItem
from ragcat.shared.config import get_settings
from ragcat.shared.errors import UpstreamUnavailable
from ragcat.shared.kernel import VectorSpec

MODEL_ENV = (
    "RAGCAT_MODELS", "RAGCAT_EMBED_PROVIDER", "RAGCAT_LLM_PROVIDER", "RAGCAT_VISION_PROVIDER",
    "RAGCAT_EMBED_MODEL_ID", "RAGCAT_EMBED_DIMS", "RAGCAT_LLM_MODEL_ID", "RAGCAT_CONTEXTUAL",
)


@pytest.fixture(autouse=True)
def clean_model_env(monkeypatch):
    for key in MODEL_ENV:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-key-not-a-credential")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "unit-test-key-not-a-credential")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize("preset,providers,dims,model", [
    ("fake", ("fake", "fake", "fake"), 2048, "fake-hashing-v3"),
    ("local", ("openai", "claude", "fake"), 1536, "text-embedding-3-small"),
    ("bedrock", ("bedrock", "bedrock", "bedrock"), 1024, "amazon.titan-embed-text-v2:0"),
])
def test_model_presets(monkeypatch, preset, providers, dims, model):
    monkeypatch.setenv("RAGCAT_MODELS", preset)
    settings = get_settings()
    assert (settings.embed_provider, settings.llm_provider, settings.vision_provider) == providers
    assert settings.embed_dims == dims and settings.embed_model_id == model


def test_providers_and_dimension_defaults_are_independent(monkeypatch):
    monkeypatch.setenv("RAGCAT_MODELS", "bedrock")
    monkeypatch.setenv("RAGCAT_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("RAGCAT_LLM_PROVIDER", "claude")
    settings = get_settings()
    assert settings.embed_model_id == "text-embedding-3-small" and settings.embed_dims == 1536
    assert settings.llm_model_id == "claude-haiku-5-5" and settings.vision_provider == "bedrock"


@pytest.mark.parametrize("name,value", [
    ("RAGCAT_MODELS", "typo"), ("RAGCAT_EMBED_PROVIDER", "claude"),
    ("RAGCAT_LLM_PROVIDER", "typo"), ("RAGCAT_VISION_PROVIDER", "openai"),
])
def test_unknown_provider_never_silently_uses_fake(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=name):
        get_settings()


@pytest.mark.parametrize("provider,dims", [("fake", 0), ("fake", -1), ("openai", 1537), ("bedrock", 1536)])
def test_invalid_embedding_dimensions_fail_before_model_calls(monkeypatch, provider, dims):
    monkeypatch.setenv("RAGCAT_EMBED_PROVIDER", provider)
    monkeypatch.setenv("RAGCAT_EMBED_DIMS", str(dims))
    with pytest.raises(ValueError):
        get_settings()


def test_openai_large_defaults_and_custom_dimensions(monkeypatch):
    monkeypatch.setenv("RAGCAT_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("RAGCAT_EMBED_MODEL_ID", "text-embedding-3-large")
    assert get_settings().embed_dims == 3072
    get_settings.cache_clear()
    monkeypatch.setenv("RAGCAT_EMBED_DIMS", "1024")
    assert get_settings().embedding_key == "openai:text-embedding-3-large:1024"


def test_factory_selects_each_adapter_independently(monkeypatch):
    settings = replace(get_settings(), embed_provider="openai", llm_provider="claude", vision_provider="bedrock")
    markers = {"OpenAiEmbedder": object(), "ClaudeLlm": object(), "BedrockVision": object()}
    for name, marker in markers.items():
        monkeypatch.setattr(model_adapters, name, lambda _, marker=marker: marker)
    selected = model_adapters.build_model_adapters(settings)
    assert selected.embedder is markers["OpenAiEmbedder"]
    assert selected.llm is markers["ClaudeLlm"] and selected.vision is markers["BedrockVision"]
    with pytest.raises(ValueError, match="refusing"):
        model_adapters.build_model_adapters(replace(settings, embed_provider="claude"))


def test_fake_factory_needs_no_model_keys(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    selected = model_adapters.build_model_adapters(get_settings())
    assert isinstance(selected.embedder, FakeEmbedder) and isinstance(selected.llm, FakeLlm)


def test_cloud_factory_uses_only_bedrock_without_local_keys(monkeypatch):
    monkeypatch.setenv("RAGCAT_MODELS", "bedrock")
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    markers = {"BedrockEmbedder": object(), "BedrockLlm": object(), "BedrockVision": object()}
    for name, marker in markers.items():
        monkeypatch.setattr(model_adapters, name, lambda _, marker=marker: marker)
    selected = model_adapters.build_model_adapters(get_settings())
    assert selected.embedder is markers["BedrockEmbedder"] and selected.llm is markers["BedrockLlm"]
    assert selected.vision is markers["BedrockVision"]


def test_local_composition_shares_the_real_adapters_without_calling_providers(monkeypatch, tmp_path):
    from ragcat.apps import container as composition

    monkeypatch.setenv("RAGCAT_MODELS", "local")
    monkeypatch.setattr(composition, "Table", lambda _: SimpleNamespace())
    settings = replace(get_settings(), data_dir=tmp_path)
    c = composition.build(settings)
    try:
        assert isinstance(c.embedder, OpenAiEmbedder) and isinstance(c.llm, ClaudeLlm)
        assert c.indexing.embedder is c.answering.embedder is c.embedder
        assert c.indexing.llm is c.answering.llm is c.llm
        assert c.vectors.embedding_key == settings.embedding_key
        assert c.answering.answering_key == settings.answering_key
    finally:
        c.embedder._client.close()
        c.llm._client.close()


@pytest.mark.parametrize("adapter,key", [(OpenAiEmbedder, "OPENAI_API_KEY"), (ClaudeLlm, "ANTHROPIC_API_KEY")])
def test_missing_credentials_fail_clearly(adapter, key, monkeypatch):
    monkeypatch.delenv(key)
    with pytest.raises(ValueError, match=key):
        adapter(get_settings())


def openai_settings():
    return replace(get_settings(), embed_provider="openai", embed_model_id="text-embedding-3-small", embed_dims=3)


def claude_settings():
    return replace(get_settings(), llm_provider="claude", llm_model_id="claude-haiku-5-5")


def test_openai_batches_use_float_dimensions_and_restore_input_order():
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "POST" and str(request.url) == OpenAiEmbedder.URL
        assert request.headers["authorization"] == "Bearer unit-test-key-not-a-credential"
        assert json.loads(request.content) == {
            "model": "text-embedding-3-small", "input": ["first", "second"], "dimensions": 3, "encoding_format": "float",
        }
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0, 1, 0]}, {"index": 0, "embedding": [1, 0, 0]},
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAiEmbedder(openai_settings(), client=client)
        assert adapter.embed([]) == [] and calls == []
        assert adapter.embed(["first", "second"]) == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


@pytest.mark.parametrize("data", [
    [], [{"index": 1, "embedding": [1, 0, 0]}], [{"index": True, "embedding": [1, 0, 0]}],
    [{"index": 0, "embedding": [1, 0]}], [{"index": 0, "embedding": [True, 0, 0]}],
    [{"index": 0, "embedding": [float("nan"), 0, 0]}], [{"index": 0, "embedding": [float("inf"), 0, 0]}],
])
def test_openai_rejects_incomplete_or_invalid_vectors(data):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps({"data": data})))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(UpstreamUnavailable, match="Embedding model is unavailable"):
            OpenAiEmbedder(openai_settings(), client=client).embed(["one"])


def test_openai_rejects_duplicate_indices():
    data = [{"index": 0, "embedding": [1, 0, 0]}, {"index": 0, "embedding": [0, 1, 0]}]
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"data": data}))) as client:
        with pytest.raises(UpstreamUnavailable):
            OpenAiEmbedder(openai_settings(), client=client).embed(["one", "two"])


@pytest.mark.parametrize("status", [307, 401, 403, 429, 500, 503])
def test_openai_provider_errors_are_sanitized(status):
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"error": {"message": "private provider details"}}))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(UpstreamUnavailable) as error:
            OpenAiEmbedder(openai_settings(), client=client).embed(["one"])
        assert error.value.message == "Embedding model is unavailable"


def test_openai_timeouts_are_sanitized():
    def handler(request):
        raise httpx.ReadTimeout("private provider details", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UpstreamUnavailable, match="Embedding model is unavailable"):
            OpenAiEmbedder(openai_settings(), client=client).embed(["one"])


class TrackedStream(httpx.SyncByteStream):
    def __init__(self, frames):
        self.payload = "".join("event: " + f["type"] + "\r\ndata: " + json.dumps(f, ensure_ascii=False) + "\r\n\r\n" for f in frames).encode()
        self.closed = False

    def __iter__(self):
        for start in range(0, len(self.payload), 7):
            yield self.payload[start:start + 7]

    def close(self):
        self.closed = True


def answer_frames(answer="可以退貨 [1]。"):
    return [
        {"type": "message_start", "message": {"usage": {"input_tokens": 25, "output_tokens": 1}}},
        {"type": "ping"}, {"type": "future_event"},
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "must not leak"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": answer}},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 9}},
        {"type": "message_stop"},
    ]


def test_claude_streams_unicode_text_and_usage_and_closes_response():
    stream = TrackedStream(answer_frames())

    def handler(request):
        assert str(request.url) == ClaudeLlm.URL and request.method == "POST"
        assert request.headers["x-api-key"] == "unit-test-key-not-a-credential"
        assert request.headers["anthropic-version"] == "2023-06-01"
        assert json.loads(request.content) == {
            "model": "claude-haiku-5-5", "system": "only cite", "max_tokens": 400, "stream": True,
            "messages": [{"role": "user", "content": "question"}], "thinking": {"type": "disabled"},
        }
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=stream)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = ClaudeLlm(claude_settings(), client=client).stream("only cite", "question")
        assert "".join(result) == "可以退貨 [1]。"
        assert result.usage.input_tokens == 25 and result.usage.output_tokens == 9
        assert stream.closed


def test_claude_cancellation_closes_response():
    stream = TrackedStream(answer_frames())
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))) as client:
        result = ClaudeLlm(claude_settings(), client=client).stream("", "question")
        assert next(result.chunks) == "可以退貨 [1]。"
        result.chunks.close()
        assert stream.closed


@pytest.mark.parametrize("frames", [
    [{"type": "error", "error": {"message": "private provider details"}}],
    answer_frames()[:-1],
    [{"type": "message_delta", "delta": {"stop_reason": "max_tokens"}}],
])
def test_claude_stream_errors_do_not_look_like_success(frames):
    stream = TrackedStream(frames)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))) as client:
        with pytest.raises(UpstreamUnavailable):
            list(ClaudeLlm(claude_settings(), client=client).stream("", "question"))
        assert stream.closed


def test_claude_multiline_sse_data_and_comments():
    payload = ': comment\n\nevent: content_block_delta\ndata: {"type":"content_block_delta",\ndata: "delta":{"type":"text_delta","text":"OK"}}\n\ndata: {"type":"message_stop"}\n\n'
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
        assert "".join(ClaudeLlm(claude_settings(), client=client).stream("", "question")) == "OK"


@pytest.mark.parametrize("payload", ['data: not-json\n\n', 'data: []\n\n', 'data: {"type":null}\n\n'])
def test_claude_malformed_stream_is_sanitized(payload):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))) as client:
        with pytest.raises(UpstreamUnavailable, match="Language model is unavailable"):
            list(ClaudeLlm(claude_settings(), client=client).stream("", "question"))


def test_claude_complete_uses_context_budget_and_only_text_blocks():
    def handler(request):
        body = json.loads(request.content)
        assert body["max_tokens"] == 120 and not body["stream"] and "system" not in body
        return httpx.Response(200, json={"content": [{"type": "thinking", "thinking": "private"}, {"type": "text", "text": " Context. "}], "stop_reason": "end_turn"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert ClaudeLlm(claude_settings(), client=client).complete("context prompt", 120) == "Context."


@pytest.mark.parametrize("status,body", [
    (401, {"error": {"message": "private"}}), (429, {}), (500, {}),
    (200, {"content": []}), (200, {"content": [{"type": "text", "text": "partial"}], "stop_reason": "max_tokens"}),
])
def test_claude_complete_errors_are_not_empty_context(status, body):
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))) as client:
        with pytest.raises(UpstreamUnavailable):
            ClaudeLlm(claude_settings(), client=client).complete("context", 120)


def test_embedding_and_context_model_identity_force_reembedding():
    old = VectorSpec("openai:model:3", contextual=True, context_model="fake:v1")
    new = VectorSpec("openai:model:3", contextual=True, context_model="claude:v1")
    passage = PassageState("p", "return policy", False, old.hash("return policy", "Returns"))
    assert [p.passage.id for p in plan_reconcile([passage], new).puts] == ["p"]
    base = get_settings()
    other = replace(base, llm_provider="claude", llm_model_id="claude-haiku-5-5")
    assert base.embedding_key == other.embedding_key and base.answering_key != other.answering_key
    assert replace(base, contextual=False).vector_spec.key == replace(other, contextual=False).vector_spec.key
    assert base.vector_spec.key != other.vector_spec.key


def item(key, vector, space, doc="doc", aid="assistant"):
    metadata = {"assistant_id": aid, "document_id": doc, "text": "Items can be returned.", "page": 1, "para": 1}
    if space is not None:
        metadata["embedding_key"] = space
    return VectorItem(key, vector, metadata)


def test_local_retrieval_filters_model_space_dimensions_owner_and_disabled_documents(tmp_path):
    original = LocalVectorIndex(tmp_path)
    original.put([
        item("current", [1, 0, 0], "openai:3"), item("fake", [1, 0, 0], "fake:3"),
        item("legacy", [1, 0, 0], None), item("wrong-dims", [1, 0], "openai:3"),
        item("disabled", [1, 0, 0], "openai:3", doc="disabled"), item("other", [1, 0, 0], "openai:3", aid="other"),
    ])
    before = original.path.read_bytes()
    current = LocalVectorIndex(tmp_path, "openai:3")
    assert [h.key for h in current.query([1, 0, 0], 5, "assistant", ["disabled"])] == ["current"]
    assert current.path.read_bytes() == before  # switching/retrieving never removes user data


def test_s3_retrieval_applies_embedding_space_filter(monkeypatch):
    calls = []

    def query_vectors(**kwargs):
        calls.append(kwargs)
        return {"vectors": []}

    monkeypatch.setattr(vectors.boto3, "client", lambda *args, **kwargs: SimpleNamespace(query_vectors=query_vectors))
    settings = get_settings()
    index = S3VectorIndex(settings)
    assert index.query([0.0] * settings.embed_dims, 5, "assistant", ["disabled"]) == []
    assert calls[0]["filter"] == {"$and": [
        {"assistant_id": {"$eq": "assistant"}}, {"embedding_key": {"$eq": settings.embedding_key}},
        {"document_id": {"$nin": ["disabled"]}},
    ]}


def test_bedrock_stream_failure_is_sanitized_and_closed(monkeypatch):
    class Broken:
        closed = False

        def __iter__(self):
            yield {"contentBlockDelta": {"delta": {"text": "partial"}}}
            raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "private"}}, "ConverseStream")

        def close(self):
            self.closed = True

    stream = Broken()
    client = SimpleNamespace(converse_stream=lambda **kwargs: {"stream": stream})
    monkeypatch.setattr(models.boto3, "client", lambda *args, **kwargs: client)
    with pytest.raises(UpstreamUnavailable, match="Language model is unavailable"):
        list(BedrockLlm(replace(get_settings(), llm_provider="bedrock", llm_model_id="google.gemma-3-12b-it")).stream("", "question"))
    assert stream.closed


def test_bedrock_embedding_validates_dimensions(monkeypatch):
    client = SimpleNamespace(invoke_model=lambda **kwargs: {"body": BytesIO(b'{"embedding":[1,0]}')})
    monkeypatch.setattr(models.boto3, "client", lambda *args, **kwargs: client)
    with pytest.raises(UpstreamUnavailable, match="Embedding model is unavailable"):
        BedrockEmbedder(replace(get_settings(), embed_provider="bedrock", embed_model_id="amazon.titan-embed-text-v2:0", embed_dims=1024)).embed(["one"])


def test_qa_uses_openai_vectors_claude_citations_and_model_scoped_cache(tmp_path):
    settings = openai_settings()
    space = settings.embedding_key
    index = LocalVectorIndex(tmp_path, space)
    calls = {"embedding": 0, "qa": 0}

    def embed(request):
        calls["embedding"] += 1
        inputs = json.loads(request.content)["input"]
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [1, 0, 0]} for i in range(len(inputs))]})

    def qa(request):
        calls["qa"] += 1
        body = json.loads(request.content)
        assert "Items can be returned." in body["messages"][0]["content"]
        return httpx.Response(200, stream=TrackedStream(answer_frames("Items can be returned [1].")))

    config = AssistantConfig("assistant", "owner", "Mochi", "", True, 1, ())
    assistants = SimpleNamespace(config=lambda aid: config)
    identity = SimpleNamespace(check_answers=lambda owner: None, add_answer=lambda owner: None)
    cache = MemoryCache()
    with httpx.Client(transport=httpx.MockTransport(embed)) as ec, httpx.Client(transport=httpx.MockTransport(qa)) as lc:
        embedder = OpenAiEmbedder(settings, client=ec)
        llm = ClaudeLlm(claude_settings(), client=lc)
        index.put([item("passage", embedder.embed(["Items can be returned."])[0], space)])
        answering = AnsweringService(assistants, identity, embedder, llm, index, cache, space, answering_key="model-a")
        caller = Caller("owner", "owner")
        events = list(answering.ask(caller, "assistant", "Can items be returned?"))
        first = collect(iter(events))
        assert first["answered"] and first["citations"][0]["chunk_id"] == "passage" and not first["cached"]
        assert dict(events)["done"]["usage"] == {"input_tokens": 25, "output_tokens": 9}
        assert collect(answering.ask(caller, "assistant", "Can items be returned?"))["cached"]
        other = AnsweringService(assistants, identity, embedder, llm, index, cache, space, answering_key="model-b")
        assert not collect(other.ask(caller, "assistant", "Can items be returned?"))["cached"]
        assert calls == {"embedding": 2, "qa": 2}  # document + query; query cache can survive QA changes


def test_indexing_calls_claude_context_then_openai_and_persists_provenance(tmp_path):
    settings = replace(openai_settings(), llm_provider="claude", llm_model_id="claude-haiku-5-5")
    calls, completed, marked = [], [], []
    passage = SimpleNamespace(
        id="passage", position=1, text="Returns policy\nItems can be returned.", deleted=False, embedded_hash=None,
        label="P-1", source=SimpleNamespace(page_start=1, para_start=1, boxes=[]), origin="auto",
    )
    doc = SimpleNamespace(id="doc", status="embedding", filename="returns.pdf", assistant_id="assistant")
    curation = SimpleNamespace(
        get_for_system=lambda did: doc, all_passages=lambda did: [passage],
        report_embed_progress=lambda *args: None, finish_embedding=lambda did: completed.append(did),
    )
    state = SimpleNamespace(mark_embedded=lambda *args: marked.append(args))
    assistants = SimpleNamespace(content_changed=lambda aid: completed.append(aid))

    def context(request):
        body = json.loads(request.content)
        assert body["max_tokens"] == 1000 and not body["stream"]
        calls.append("context")
        reply = json.dumps({"context": "Returns context.", "entities": [{"name": "Returns policy", "type": "policy"}]})
        return httpx.Response(200, json={"content": [{"type": "text", "text": reply}], "stop_reason": "end_turn"})

    def embedding(request):
        assert json.loads(request.content)["input"] == ["Returns context.\nEntities: Returns policy (policy)\n\nReturns policy\nItems can be returned."]
        calls.append("embedding")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0, 0]}]})

    index = LocalVectorIndex(tmp_path, settings.embedding_key)
    with httpx.Client(transport=httpx.MockTransport(context)) as lc, httpx.Client(transport=httpx.MockTransport(embedding)) as ec:
        service = IndexingService(state, curation, assistants, OpenAiEmbedder(settings, client=ec), ClaudeLlm(settings, client=lc), index, None, settings.vector_spec, cache=MemoryCache())
        service.reconcile("doc")
    assert calls == ["context", "embedding"] and completed == ["doc", "assistant"]
    assert marked == [("doc", "passage", settings.vector_spec.hash(passage.text, "Returns policy"), "Returns context.")]
    persisted = LocalVectorIndex(tmp_path, settings.embedding_key).query([1, 0, 0], 5, "assistant", [])
    assert persisted[0].metadata["embedding_key"] == settings.embedding_key
    assert persisted[0].metadata["context"] == "Returns context." and persisted[0].key == "passage"
    assert persisted[0].metadata["entities"] == ["policy:Returns policy"]


def test_indexing_embeds_the_bare_passage_when_the_context_reply_is_not_json(tmp_path):
    settings = replace(openai_settings(), llm_provider="claude", llm_model_id="claude-haiku-5-5")
    marked, inputs = [], []
    passage = SimpleNamespace(
        id="passage", position=1, text="Returns policy\nItems can be returned.", deleted=False, embedded_hash=None,
        label="P-1", source=SimpleNamespace(page_start=1, para_start=1, boxes=[]), origin="auto",
    )
    curation = SimpleNamespace(
        get_for_system=lambda did: SimpleNamespace(id="doc", status="embedding", filename="returns.pdf", assistant_id="assistant"),
        all_passages=lambda did: [passage], report_embed_progress=lambda *args: None, finish_embedding=lambda did: None,
    )
    state = SimpleNamespace(mark_embedded=lambda *args: marked.append(args))

    def context(request):
        return httpx.Response(200, json={"content": [{"type": "text", "text": "This passage covers returns."}], "stop_reason": "end_turn"})

    def embedding(request):
        inputs.append(json.loads(request.content)["input"])
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 0, 0]}]})

    index = LocalVectorIndex(tmp_path, settings.embedding_key)
    with httpx.Client(transport=httpx.MockTransport(context)) as lc, httpx.Client(transport=httpx.MockTransport(embedding)) as ec:
        IndexingService(state, curation, SimpleNamespace(content_changed=lambda aid: None), OpenAiEmbedder(settings, client=ec), ClaudeLlm(settings, client=lc), index, None, settings.vector_spec, cache=MemoryCache()).reconcile("doc")
    assert inputs == [["Returns policy\nItems can be returned."]]
    assert marked[0][3] == ""  # no context recorded, so the Review screen shows none
    assert "entities" not in LocalVectorIndex(tmp_path, settings.embedding_key).query([1, 0, 0], 5, "assistant", [])[0].metadata


def test_failed_qa_stream_is_not_cached_as_an_answer(tmp_path):
    calls = []
    index = LocalVectorIndex(tmp_path, "space")
    index.put([item("passage", [1, 0, 0], "space")])
    config = AssistantConfig("assistant", "owner", "Mochi", "", True, 1, ())

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=TrackedStream([
            {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Partial answer [1]."}},
            {"type": "error", "error": {"message": "private provider details"}},
        ]))

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        service = AnsweringService(
            SimpleNamespace(config=lambda aid: config), SimpleNamespace(check_answers=lambda _: None, add_answer=lambda _: None),
            SimpleNamespace(embed=lambda _: [[1, 0, 0]]), ClaudeLlm(claude_settings(), client=client), index, MemoryCache(), "space", answering_key="qa",
        )
        for _ in range(2):
            events = list(service.ask(Caller("owner", "owner"), "assistant", "Can items be returned?"))
            assert not events[0][1]["cached"] and events[-1][0] == "error"
            assert events[-1][1]["message"] == "Language model is unavailable"
            assert not any(event == "done" for event, data in events)
        assert len(calls) == 2
