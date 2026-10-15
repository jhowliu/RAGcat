"""OpenAI Embeddings REST adapter. Both indexing and query embedding cross the same seam."""

from __future__ import annotations

import os

import httpx

from ragcat.infra.models import checked_embedding
from ragcat.shared.config import Settings
from ragcat.shared.errors import UpstreamUnavailable


class OpenAiEmbedder:
    URL = "https://api.openai.com/v1/embeddings"

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ValueError("OPENAI_API_KEY is required for the openai embedding provider")
        self.model_id = settings.embed_model_id
        self.dims = settings.embed_dims
        self._headers = {"Authorization": f"Bearer {key}"}
        self._client = client if client is not None else httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=False)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = self._client.post(self.URL, headers=self._headers, json={
                "model": self.model_id, "input": texts, "dimensions": self.dims, "encoding_format": "float",
            })
            response.raise_for_status()
            entries = response.json()["data"]
            if not isinstance(entries, list) or len(entries) != len(texts):
                raise ValueError("Incomplete embedding batch")
            ordered: dict[int, list[float]] = {}
            for entry in entries:
                index = entry["index"]
                if type(index) is not int or not 0 <= index < len(texts) or index in ordered:
                    raise ValueError("Invalid embedding index")
                ordered[index] = checked_embedding(entry["embedding"], self.dims)
            return [ordered[i] for i in range(len(texts))]
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            # Never surface provider response bodies, keys or document text to HTTP clients.
            raise UpstreamUnavailable("Embedding model is unavailable") from exc
