"""Bounded request load for ECS scaling evidence. Tokens are read from the environment.

Use /v1/me for api load. For qa, supply a smoke-test Assistant ID: one warmup request
populates the answer cache so the load does not generate an LLM answer for every request.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--assistant-id", help="Omit for api load; supply for qa load")
    parser.add_argument("--question", default="Can unopened items be returned?")
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--requests-per-second", type=float, default=10)
    args = parser.parse_args()
    origin = urlparse(args.base_url)
    token = os.environ.get("RAGCAT_ACCESS_TOKEN", "")
    if origin.scheme != "https" or not origin.netloc or origin.username or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment:
        parser.error("Use the CloudFront HTTPS origin")
    if not token or token.startswith("dev:"):
        parser.error("Set a Cognito RAGCAT_ACCESS_TOKEN")
    if not 1 <= args.concurrency <= 50 or not 1 <= args.seconds <= 900 or not 0 < args.requests_per_second <= 100:
        parser.error("Use concurrency 1–50, duration 1–900 seconds, and rate above 0 through 100 requests/s")
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/v1/assistants/{args.assistant_id}/ask" if args.assistant_id else "/v1/me"
    payload = {"question": args.question, "stream": False}

    def request(client):
        return client.post(path, json=payload) if args.assistant_id else client.get(path)

    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60) as client:
        response = request(client)
        response.raise_for_status()
        if args.assistant_id:
            response = request(client)
            response.raise_for_status()
            if not response.json().get("cached"):
                raise RuntimeError("QA warmup did not hit the cache; stop to avoid repeated model charges")
        results = []
        lock = threading.Lock()
        stopped = threading.Event()
        start = time.monotonic()
        deadline = start + args.seconds
        interval = args.concurrency / args.requests_per_second

        def worker(index):
            next_request = start + index / args.requests_per_second
            while not stopped.is_set() and next_request < deadline:
                stopped.wait(max(0, next_request - time.monotonic()))
                if stopped.is_set() or time.monotonic() >= deadline:
                    break
                before = time.monotonic()
                try:
                    response = request(client)
                    status = response.status_code
                    if status in (401, 403) or (args.assistant_id and status == 200 and not response.json().get("cached")):
                        stopped.set()
                except httpx.HTTPError:
                    status = 0
                with lock:
                    results.append((status, (time.monotonic() - before) * 1000))
                next_request = max(next_request + interval, time.monotonic())

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            list(pool.map(worker, range(args.concurrency)))
    latencies = sorted(ms for _, ms in results)
    failures = sum(status != 200 for status, _ in results)
    percentile = lambda p: round(latencies[min(len(latencies) - 1, int((len(latencies) - 1) * p))], 1) if latencies else None
    print(json.dumps({"target": "qa" if args.assistant_id else "api", "requests": len(results), "failures": failures, "stopped_early": stopped.is_set(), "elapsed_seconds": round(time.monotonic() - start, 1), "p50_ms": percentile(.5), "p95_ms": percentile(.95)}))
    return 1 if failures or stopped.is_set() else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, RuntimeError) as error:
        print(json.dumps({"status": "failed", "error": type(error).__name__}))
        raise SystemExit(1)
