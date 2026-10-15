"""In-memory cache port: ElastiCache Valkey in AWS, a process-local dict in development."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Protocol

import redis


class Cache(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl: int) -> None: ...
    def delete(self, key: str) -> None: ...


def get_json(cache: Cache, key: str) -> Any | None:
    raw = cache.get(key)
    return json.loads(raw) if raw is not None else None


def set_json(cache: Cache, key: str, value: Any, ttl: int) -> None:
    cache.set(key, json.dumps(value), ttl)



class MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires < time.monotonic():
                del self._data[key]
                return None
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + ttl, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)


class ValkeyCache:
    def __init__(self, url: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=0.5)

    def get(self, key: str) -> str | None:
        try:
            return self.client.get(key)
        except redis.RedisError:
            return None  # a cache outage degrades to cache misses

    def set(self, key: str, value: str, ttl: int) -> None:
        try:
            self.client.set(key, value, ex=ttl)
        except redis.RedisError:
            pass

    def delete(self, key: str) -> None:
        try:
            self.client.delete(key)
        except redis.RedisError:
            pass
