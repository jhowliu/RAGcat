"""Runtime settings, read once from environment variables.

The local model preset uses Claude for QA/context and OpenAI for embeddings. The bedrock
preset uses AWS models; the fake preset is explicitly offline. Providers can be overridden
independently. Secrets stay in the environment, never in this settings object's repr.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ragcat.shared.kernel import VectorSpec


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _choice(name: str, value: str, choices: tuple[str, ...]) -> str:
    if value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}")
    return value


@dataclass(frozen=True)
class Settings:
    region: str
    table_name: str
    dynamodb_endpoint: str | None
    storage: str  # local | s3
    data_dir: Path
    bucket: str
    queue: str  # local | redis | sqs
    queue_url: str  # redis
    parse_queue_url: str
    embed_queue_url: str
    vectors: str  # local | s3vectors
    vector_bucket: str
    vector_index: str
    embed_provider: str  # fake | openai | bedrock
    llm_provider: str  # fake | claude | bedrock
    vision_provider: str  # fake | bedrock
    embed_model_id: str
    embed_dims: int
    llm_model_id: str
    vision_model_id: str
    contextual: bool
    cache: str  # memory | valkey
    cache_url: str
    auth: str  # dev | cognito
    cognito_pool_id: str
    cognito_client_id: str
    signing_secret: str

    @property
    def embedding_key(self) -> str:
        """Identifies the embedding space (query vectors are cached under it)."""
        model = "fake-hashing-v3" if self.embed_provider == "fake" else self.embed_model_id
        return f"{self.embed_provider}:{model}:{self.embed_dims}"

    @property
    def llm_key(self) -> str:
        model = "fake-extractive-v1" if self.llm_provider == "fake" else self.llm_model_id
        return f"{self.llm_provider}:{model}"

    @property
    def answering_key(self) -> str:
        """Changing either model must not reuse another model's cached answer."""
        return f"{self.vector_spec.key}:qa:{self.llm_key}"

    @property
    def vector_spec(self) -> VectorSpec:
        """What a passage vector represents; part of every content hash (see shared.kernel)."""
        return VectorSpec(self.embedding_key, self.contextual, context_model=self.llm_key)


@lru_cache
def get_settings() -> Settings:
    preset = _choice("RAGCAT_MODELS", _env("RAGCAT_MODELS", "fake"), ("fake", "local", "bedrock"))
    embed_default, llm_default, vision_default = {
        "fake": ("fake", "fake", "fake"),
        "local": ("openai", "claude", "fake"),
        "bedrock": ("bedrock", "bedrock", "bedrock"),
    }[preset]
    embed_provider = _choice("RAGCAT_EMBED_PROVIDER", _env("RAGCAT_EMBED_PROVIDER", embed_default), ("fake", "openai", "bedrock"))
    llm_provider = _choice("RAGCAT_LLM_PROVIDER", _env("RAGCAT_LLM_PROVIDER", llm_default), ("fake", "claude", "bedrock"))
    vision_provider = _choice("RAGCAT_VISION_PROVIDER", _env("RAGCAT_VISION_PROVIDER", vision_default), ("fake", "bedrock"))
    embed_model = _env("RAGCAT_EMBED_MODEL_ID", {
        "fake": "fake-hashing-v3", "openai": "text-embedding-3-small", "bedrock": "amazon.titan-embed-text-v2:0",
    }[embed_provider])
    default_dims = {"fake": 2048, "openai": 3072 if embed_model == "text-embedding-3-large" else 1536, "bedrock": 1024}[embed_provider]
    dims = int(_env("RAGCAT_EMBED_DIMS", str(default_dims)))
    if dims < 1:
        raise ValueError("RAGCAT_EMBED_DIMS must be positive")
    if embed_provider == "bedrock" and dims not in (256, 512, 1024):
        raise ValueError("Bedrock Titan v2 supports RAGCAT_EMBED_DIMS of 256, 512 or 1024")
    if embed_provider == "openai":
        limits = {"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}
        if embed_model not in limits or dims > limits[embed_model]:
            raise ValueError("OpenAI embedding requires text-embedding-3-small (up to 1536 dimensions) or text-embedding-3-large (up to 3072)")
    return Settings(
        region=_env("AWS_REGION", "ap-southeast-2"),
        table_name=_env("RAGCAT_TABLE", "n12218642-a3"),
        dynamodb_endpoint=_env("RAGCAT_DYNAMODB_ENDPOINT") or None,
        storage=_env("RAGCAT_STORAGE", "local"),
        data_dir=Path(_env("RAGCAT_DATA_DIR", ".data")).resolve(),
        bucket=_env("RAGCAT_BUCKET", "n12218642-a3-files"),
        queue=_env("RAGCAT_QUEUE", "local"),
        queue_url=_env("RAGCAT_QUEUE_URL", "redis://localhost:6380/0"),
        parse_queue_url=_env("RAGCAT_PARSE_QUEUE_URL"),
        embed_queue_url=_env("RAGCAT_EMBED_QUEUE_URL"),
        vectors=_env("RAGCAT_VECTORS", "local"),
        vector_bucket=_env("RAGCAT_VECTOR_BUCKET", "n12218642-a3-vectors"),
        vector_index=_env("RAGCAT_VECTOR_INDEX", "passages"),
        embed_provider=embed_provider,
        llm_provider=llm_provider,
        vision_provider=vision_provider,
        embed_model_id=embed_model,
        embed_dims=dims,
        llm_model_id=_env("RAGCAT_LLM_MODEL_ID", {"fake": "fake-extractive-v1", "claude": "claude-haiku-5-5", "bedrock": "google.gemma-3-12b-it"}[llm_provider]),
        vision_model_id=_env("RAGCAT_VISION_MODEL_ID", "google.gemma-3-12b-it"),
        contextual=_env("RAGCAT_CONTEXTUAL", "on") == "on",
        cache=_env("RAGCAT_CACHE", "memory"),
        cache_url=_env("RAGCAT_CACHE_URL", "redis://localhost:6380/0"),
        auth=_env("RAGCAT_AUTH", "dev"),
        cognito_pool_id=_env("COGNITO_USER_POOL_ID"),
        cognito_client_id=_env("COGNITO_CLIENT_ID"),
        signing_secret=_env("RAGCAT_SIGNING_SECRET", "local-dev-secret"),
    )
