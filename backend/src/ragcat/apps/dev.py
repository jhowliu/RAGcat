"""Local server: api + qa routes and stand-ins for the S3 upload endpoint and CloudFront /pages/*.
With RAGCAT_QUEUE=local the worker runs on a background thread; with redis, run
`python -m ragcat.apps.worker` alongside.

    uvicorn ragcat.apps.dev:app --port 8010
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse

from ragcat.apps.container import Container, container
from ragcat.apps.http import create_app
from ragcat.infra.queue import LocalQueue, SqsQueue
from ragcat.infra.storage import LocalObjectStore
from ragcat.shared.errors import NotFound

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_dev_app(c: Container) -> FastAPI:
    assert isinstance(c.store, LocalObjectStore) and not isinstance(c.queue, SqsQueue), "dev app needs local storage and a local queue"
    store, queue = c.store, c.queue

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logging.getLogger("ragcat.models").info("QA=%s; embedding=%s; vision=%s", c.settings.llm_key, c.settings.embedding_key, c.settings.vision_provider)
        c.table.ensure_exists()
        if isinstance(queue, LocalQueue):
            queue.start()
        yield

    app = create_app(c, api=True, qa=True)
    app.router.lifespan_context = lifespan

    @app.post(LocalObjectStore.UPLOAD_URL, status_code=204)
    async def upload(request: Request) -> Response:
        """Behaves like an S3 presigned POST, then emits what EventBridge would put on the parse queue."""
        form = await request.form()
        file = form.get("file")
        if file is None or isinstance(file, str):
            raise NotFound("Missing file field")
        fields = {k: v for k, v in form.items() if isinstance(v, str)}
        data = await file.read()
        key = store.accept_upload(fields, data, file.content_type or fields.get("Content-Type", ""))
        queue.send(
            "parse",
            {"source": "aws.s3", "detail-type": "Object Created", "detail": {"bucket": {"name": "local"}, "object": {"key": key, "size": len(data)}}},
        )
        return Response(status_code=204)

    @app.get(LocalObjectStore.OBJECT_URL + "{key:path}")
    def get_object(key: str) -> FileResponse:
        path = store.file_path(key)
        if not path.is_file():
            raise NotFound("Object not found")
        return FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

    return app


app = create_dev_app(container())
