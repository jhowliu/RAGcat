# syntax=docker/dockerfile:1.7
# Two images from one build context, both linux/arm64 and both pinned to uv.lock:
#   service: api / qa on ECS Fargate. The task definition picks the app with `command`.
#   worker:  ingest / embed on Lambda. The function picks the handler with `image_config.command`.
# Build with `make images` (see Makefile).

ARG PYTHON_VERSION=3.13

FROM ghcr.io/astral-sh/uv:0.12.23 AS uv

# uv.lock -> requirements.txt (third-party packages only; our code is copied separately so
# editing it doesn't reinstall dependencies).
FROM python:${PYTHON_VERSION}-slim-trixie AS requirements
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv export --frozen --no-dev --no-emit-project --no-header -o /requirements.txt


FROM python:${PYTHON_VERSION}-slim-trixie AS service
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=from=requirements,source=/requirements.txt,target=/tmp/requirements.txt \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --compile-bytecode --link-mode=copy -r /tmp/requirements.txt \
 && useradd --system --uid 10001 --no-create-home ragcat
WORKDIR /app
COPY src/ragcat ragcat
RUN python -m compileall -q ragcat
# The ALB keeps idle connections for 60 s; uvicorn must keep them longer (default 5 s), or the
# ALB sometimes sends a request on a connection uvicorn just closed and returns 502.
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1 \
    UVICORN_HOST=0.0.0.0 UVICORN_PORT=8080 UVICORN_TIMEOUT_KEEP_ALIVE=75
USER ragcat
EXPOSE 8080
CMD ["uvicorn", "ragcat.apps.api:app"]


# The AWS base image brings the Lambda runtime client, and the Runtime Interface Emulator for
# local runs (docker run -p 9000:8080, then POST /2015-03-31/functions/function/invocations).
FROM public.ecr.aws/lambda/python:${PYTHON_VERSION} AS worker
RUN --mount=from=uv,source=/uv,target=/bin/uv \
    --mount=from=requirements,source=/requirements.txt,target=/tmp/requirements.txt \
    --mount=type=cache,target=/root/.cache/uv \
    uv pip install --target "${LAMBDA_TASK_ROOT}" --compile-bytecode --link-mode=copy -r /tmp/requirements.txt
COPY src/ragcat ${LAMBDA_TASK_ROOT}/ragcat
# /var/task is read-only at run time, so compile now rather than on every cold start.
RUN python -m compileall -q ${LAMBDA_TASK_ROOT}/ragcat
CMD ["ragcat.apps.worker.ingest"]
