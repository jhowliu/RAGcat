"""Worker entry points. On AWS: Lambda handlers for the `ingest` and `embed` functions (same
image, different CMD). Locally: `python -m ragcat.apps.worker` consumes the Redis queues.

Each SQS event source mapping uses batch size 1; raising makes SQS redeliver the message,
and after maxReceiveCount it moves to the DLQ.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ragcat.apps.container import container, handlers
from ragcat.infra.queue import RedisQueue

logging.getLogger().setLevel(logging.INFO)


def ingest(event: dict[str, Any], context: Any = None) -> None:
    _deliver("parse", event)


def embed(event: dict[str, Any], context: Any = None) -> None:
    _deliver("embed", event)


def _deliver(name: str, event: dict[str, Any]) -> None:
    handle = handlers(container())[name]
    for record in event.get("Records", []):
        handle(json.loads(record["body"]))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    c = container()
    assert isinstance(c.queue, RedisQueue), "the local worker needs RAGCAT_QUEUE=redis"
    logging.getLogger("ragcat.models").info("QA=%s; embedding=%s; vision=%s", c.settings.llm_key, c.settings.embedding_key, c.settings.vision_provider)
    c.table.ensure_exists()
    c.queue.consume(handlers(c))


if __name__ == "__main__":
    main()
