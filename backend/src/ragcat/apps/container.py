"""Composition root: picks an adapter for every port from Settings and wires the services."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from ragcat.answering.service import AnsweringService
from ragcat.assistants.adapters import DynamoAssistantRepo
from ragcat.assistants.service import AssistantsService
from ragcat.curation.adapters import DynamoCurationRepo
from ragcat.curation.service import CurationService
from ragcat.identity.adapters import CognitoPasswordAuth, DynamoIdentityRepo, JwtVerifier
from ragcat.identity.service import IdentityService
from ragcat.indexing.adapters import PassageIndexState
from ragcat.indexing.service import IndexingService
from ragcat.infra.cache import Cache, MemoryCache, ValkeyCache
from ragcat.infra.dynamo import Table
from ragcat.infra.model_adapters import build_model_adapters
from ragcat.infra.models import Embedder, Llm
from ragcat.infra.queue import Handler, LocalQueue, MessageQueue, RedisQueue, SqsQueue
from ragcat.infra.storage import LocalObjectStore, ObjectStore, S3ObjectStore
from ragcat.infra.vectors import LocalVectorIndex, S3VectorIndex, VectorIndex
from ragcat.ingestion.service import IngestionService
from ragcat.shared.config import Settings, get_settings


@dataclass
class Container:
    settings: Settings
    table: Table
    store: ObjectStore
    queue: MessageQueue
    vectors: VectorIndex
    embedder: Embedder
    llm: Llm
    cache: Cache
    verifier: JwtVerifier
    identity: IdentityService
    assistants: AssistantsService
    curation: CurationService
    ingestion: IngestionService
    indexing: IndexingService
    answering: AnsweringService


def build(settings: Settings) -> Container:
    models = build_model_adapters(settings)
    embedder, llm, vision = models.embedder, models.llm, models.vision
    table = Table(settings)
    store: ObjectStore = LocalObjectStore(settings.data_dir, settings.signing_secret) if settings.storage == "local" else S3ObjectStore(settings)
    queue: MessageQueue = LocalQueue() if settings.queue == "local" else RedisQueue(settings.queue_url) if settings.queue == "redis" else SqsQueue(settings)
    vectors: VectorIndex = LocalVectorIndex(settings.data_dir, settings.embedding_key) if settings.vectors == "local" else S3VectorIndex(settings)
    cache: Cache = MemoryCache() if settings.cache == "memory" else ValkeyCache(settings.cache_url)
    key = settings.embedding_key
    spec = settings.vector_spec

    verifier = JwtVerifier(settings)
    password_auth = CognitoPasswordAuth(settings) if settings.auth == "cognito" else None
    identity = IdentityService(DynamoIdentityRepo(table), auth=password_auth, verifier=verifier)
    curation_ref: list[CurationService] = []  # Assistants reads Curation's summaries; wired below
    assistants = AssistantsService(DynamoAssistantRepo(table), cache, documents=lambda aid: curation_ref[0].summaries(aid))
    curation = CurationService(DynamoCurationRepo(table), store, queue, hooks=assistants, spec=spec)
    curation_ref.append(curation)
    ingestion = IngestionService(curation, identity, store, vision)
    indexing = IndexingService(PassageIndexState(table), curation, assistants, embedder, llm, vectors, store, spec, cache=cache)
    answering = AnsweringService(assistants, identity, embedder, llm, vectors, cache, key, answering_key=settings.answering_key, indexing=indexing)

    c = Container(settings, table, store, queue, vectors, embedder, llm, cache, verifier, identity, assistants, curation, ingestion, indexing, answering)
    if isinstance(queue, LocalQueue):
        for name, handler in handlers(c).items():
            queue.register(name, handler)
    return c


def handlers(c: Container) -> dict[str, Handler]:
    """What a message on each queue runs, whichever consumer delivers it (thread, Redis worker, Lambda)."""
    return {
        "parse": lambda message: c.ingestion.run(message["detail"]["object"]["key"]),
        "embed": lambda message: c.indexing.reconcile(message["document_id"]),
    }


@lru_cache
def container() -> Container:
    return build(get_settings())
