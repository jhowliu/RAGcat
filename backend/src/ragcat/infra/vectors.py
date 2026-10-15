"""Vector index port: S3 Vectors in AWS, a brute-force JSON index in development.

The vector key and metadata schema are the published language between Indexing and
Answering (domain-design.md §4): key = chunk id; filterable assistant_id, document_id and embedding_key;
everything a citation needs is stored as non-filterable metadata.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3

from ragcat.shared.config import Settings


@dataclass(frozen=True)
class VectorItem:
    key: str
    vector: list[float]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class Hit:
    key: str
    score: float
    metadata: dict[str, Any]


class VectorIndex(Protocol):
    def put(self, items: list[VectorItem]) -> None: ...
    def delete(self, keys: list[str]) -> None: ...
    def query(self, vector: list[float], top_k: int, assistant_id: str, exclude_documents: list[str]) -> list[Hit]: ...


class LocalVectorIndex:
    def __init__(self, data_dir: Path, embedding_key: str | None = None) -> None:
        self.embedding_key = embedding_key
        self.path = data_dir / "vectors.json"
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}
        self._stamp: tuple[int, int] | None = None
        with self._lock:
            self._refresh()

    def _refresh(self) -> None:
        """The API process queries while the Redis worker process writes, so reload when the file changed."""
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return
        stamp = (stat.st_mtime_ns, stat.st_size)
        if stamp != self._stamp:
            self._items = json.loads(self.path.read_text())
            self._stamp = stamp

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._items))
        tmp.replace(self.path)
        stat = self.path.stat()
        self._stamp = (stat.st_mtime_ns, stat.st_size)

    def put(self, items: list[VectorItem]) -> None:
        with self._lock:
            self._refresh()
            for item in items:
                self._items[item.key] = {"vector": item.vector, "metadata": item.metadata}
            self._save()

    def delete(self, keys: list[str]) -> None:
        with self._lock:
            self._refresh()
            for key in keys:
                self._items.pop(key, None)
            self._save()

    def query(self, vector: list[float], top_k: int, assistant_id: str, exclude_documents: list[str]) -> list[Hit]:
        excluded = set(exclude_documents)
        with self._lock:
            self._refresh()
            candidates = [
                (key, item)
                for key, item in self._items.items()
                if item["metadata"].get("assistant_id") == assistant_id
                and item["metadata"].get("document_id") not in excluded
                and (self.embedding_key is None or item["metadata"].get("embedding_key") == self.embedding_key)
                and len(item["vector"]) == len(vector)
            ]
        scored = [Hit(key, cosine(vector, item["vector"]), item["metadata"]) for key, item in candidates]
        return sorted(scored, key=lambda h: h.score, reverse=True)[:top_k]


def cosine(a: list[float], b: list[float]) -> float:
    """Similarity on the same scale as the S3 Vectors cosine index's 1 - distance."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class S3VectorIndex:
    BATCH = 500

    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.vector_bucket
        self.index = settings.vector_index
        self.embedding_key = settings.embedding_key
        self.client = boto3.client("s3vectors", region_name=settings.region)

    def put(self, items: list[VectorItem]) -> None:
        for start in range(0, len(items), self.BATCH):
            self.client.put_vectors(
                vectorBucketName=self.bucket,
                indexName=self.index,
                vectors=[
                    {"key": i.key, "data": {"float32": i.vector}, "metadata": i.metadata}
                    for i in items[start : start + self.BATCH]
                ],
            )

    def delete(self, keys: list[str]) -> None:
        for start in range(0, len(keys), self.BATCH):
            self.client.delete_vectors(vectorBucketName=self.bucket, indexName=self.index, keys=keys[start : start + self.BATCH])

    def query(self, vector: list[float], top_k: int, assistant_id: str, exclude_documents: list[str]) -> list[Hit]:
        filters: list[dict[str, Any]] = [
            {"assistant_id": {"$eq": assistant_id}},
            {"embedding_key": {"$eq": self.embedding_key}},
        ]
        if exclude_documents:
            filters.append({"document_id": {"$nin": exclude_documents}})
        out = self.client.query_vectors(
            vectorBucketName=self.bucket,
            indexName=self.index,
            queryVector={"float32": vector},
            topK=top_k,
            filter={"$and": filters},
            returnMetadata=True,
            returnDistance=True,
        )
        return [Hit(v["key"], 1.0 - float(v.get("distance", 1.0)), v.get("metadata", {})) for v in out.get("vectors", [])]
