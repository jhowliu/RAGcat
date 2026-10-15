"""Message queue port: SQS in AWS; in development a Redis list per queue consumed by a separate
worker process, or an in-process worker thread (offline backend and tests).

The local queues mimic an SQS event source mapping with batch size 1 and maxReceiveCount 3,
so handlers see the same retry behaviour they get from Lambda.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Any, Callable, Protocol

import boto3
import redis

from ragcat.shared.config import Settings

log = logging.getLogger("ragcat.queue")

Handler = Callable[[dict[str, Any]], None]


class MessageQueue(Protocol):
    def send(self, name: str, message: dict[str, Any]) -> None: ...


class LocalQueue:
    MAX_RECEIVES = 3

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, dict[str, Any], int]] = queue.Queue()
        self._handlers: dict[str, Handler] = {}
        self._thread: threading.Thread | None = None

    def register(self, name: str, handler: Handler) -> None:
        self._handlers[name] = handler

    def send(self, name: str, message: dict[str, Any]) -> None:
        self._queue.put((name, json.loads(json.dumps(message)), 1))

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="local-queue", daemon=True)
            self._thread.start()

    def drain(self, timeout: float = 30.0) -> None:
        """Block until every queued message has been handled (used by tests)."""
        done = threading.Event()

        def wait() -> None:
            self._queue.join()
            done.set()

        threading.Thread(target=wait, daemon=True).start()
        if not done.wait(timeout):
            raise TimeoutError("Local queue did not drain")

    def _run(self) -> None:
        while True:
            name, message, receives = self._queue.get()
            try:
                self._handlers[name](message)
            except Exception:
                if receives < self.MAX_RECEIVES:
                    log.warning("Handler %s failed (attempt %d); retrying", name, receives, exc_info=True)
                    self._queue.put((name, message, receives + 1))
                else:
                    log.exception("Handler %s failed %d times; dropping message (DLQ)", name, receives)
            finally:
                self._queue.task_done()


class RedisQueue:
    """LPUSH to send, BRPOP to receive; `python -m ragcat.apps.worker` runs `consume`.

    Unlike SQS there is no visibility timeout: a message the worker has popped is lost if the
    worker dies before handling it.
    """

    MAX_RECEIVES = 3

    def __init__(self, url: str) -> None:
        self.client = redis.Redis.from_url(url, decode_responses=True)

    def send(self, name: str, message: dict[str, Any]) -> None:
        self._push(name, message, 1)

    def consume(self, handlers: dict[str, Handler]) -> None:
        """Handle one message at a time, forever."""
        names = {f"queue:{name}": name for name in handlers}
        while True:
            popped = self.client.brpop(list(names), timeout=1)  # under redis-py's 5 s socket timeout
            if popped is None:
                continue
            key, raw = popped
            name, envelope = names[key], json.loads(raw)
            message, receives = envelope["message"], envelope["receives"]
            try:
                handlers[name](message)
            except Exception:
                if receives < self.MAX_RECEIVES:
                    log.warning("Handler %s failed (attempt %d); retrying", name, receives, exc_info=True)
                    self._push(name, message, receives + 1)
                else:
                    log.exception("Handler %s failed %d times; moving message to queue:%s:dlq", name, receives, name)
                    self.client.lpush(f"queue:{name}:dlq", raw)

    def _push(self, name: str, message: dict[str, Any], receives: int) -> None:
        self.client.lpush(f"queue:{name}", json.dumps({"message": message, "receives": receives}))


class SqsQueue:
    def __init__(self, settings: Settings) -> None:
        self.urls = {"parse": settings.parse_queue_url, "embed": settings.embed_queue_url}
        self.sqs = boto3.client("sqs", region_name=settings.region)

    def send(self, name: str, message: dict[str, Any]) -> None:
        self.sqs.send_message(QueueUrl=self.urls[name], MessageBody=json.dumps(message))
