"""Bounded request load for ECS scaling evidence. Tokens are read from the environment.

Use /v1/me for api load. For qa, supply a smoke-test Assistant ID: one warmup request
populates the answer cache so the load does not generate an LLM answer for every request.
With --miss-rate, that share of requests asks a new question instead, so each one embeds,
retrieves and calls the LLM (and counts against the owner's answer quota).
"""
from __future__ import annotations

import argparse
import itertools
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
    parser.add_argument("--miss-rate", type=float, default=0, help="qa only: share of requests that ask a new, uncached question")
    args = parser.parse_args()
    origin = urlparse(args.base_url)
    token = os.environ.get("RAGCAT_ACCESS_TOKEN", "")
    if origin.scheme != "https" or not origin.netloc or origin.username or origin.password or origin.path not in ("", "/") or origin.query or origin.fragment:
        parser.error("Use the CloudFront HTTPS origin")
    if not token or token.startswith("dev:"):
        parser.error("Set a Cognito RAGCAT_ACCESS_TOKEN")
    if not 1 <= args.concurrency <= 50 or not 1 <= args.seconds <= 900 or not 0 < args.requests_per_second <= 100:
        parser.error("Use concurrency 1–50, duration 1–900 seconds, and rate above 0 through 100 requests/s")
    if not 0 <= args.miss_rate <= 1 or (args.miss_rate and not args.assistant_id):
        parser.error("Use a miss rate from 0 through 1, and only with --assistant-id")
    headers = {"Authorization": f"Bearer {token}"}
    path = f"/v1/assistants/{args.assistant_id}/ask" if args.assistant_id else "/v1/me"
    run = os.urandom(3).hex()  # new questions differ between runs, so a rerun cannot hit the cache
    numbers = itertools.count(1)

    def request(client, question=args.question):
        return client.post(path, json={"question": question, "stream": False}) if args.assistant_id else client.get(path)

    def next_question():
        # Spreads misses evenly: with 0.8, four of every five requests ask a new question.
        # The number goes in front: as a suffix the LLM treats it as noise and declines to answer.
        n = next(numbers)
        if int(n * args.miss_rate) > int((n - 1) * args.miss_rate):
            return f"Customer {run}-{n} asks: {args.question}", True
        return args.question, False

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
                question, miss = next_question()
                before = time.monotonic()
                try:
                    response = request(client, question)
                    status = response.status_code
                    cached = status == 200 and bool(args.assistant_id) and response.json().get("cached")
                    if status in (401, 403, 429) or (args.assistant_id and status == 200 and not miss and not cached):
                        stopped.set()
                except httpx.HTTPError:
                    status, cached = 0, False
                with lock:
                    results.append((status, (time.monotonic() - before) * 1000, cached))
                next_request = max(next_request + interval, time.monotonic())

        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            list(pool.map(worker, range(args.concurrency)))

    def percentiles(rows):
        latencies = sorted(ms for _, ms, _ in rows)
        pick = lambda p: round(latencies[min(len(latencies) - 1, int((len(latencies) - 1) * p))], 1) if latencies else None
        return pick(.5), pick(.95)

    failures = sum(status != 200 for status, _, _ in results)
    summary = {"target": "qa" if args.assistant_id else "api", "requests": len(results), "failures": failures, "stopped_early": stopped.is_set(), "elapsed_seconds": round(time.monotonic() - start, 1)}
    summary["p50_ms"], summary["p95_ms"] = percentiles(results)
    if args.miss_rate:
        hits = [row for row in results if row[0] == 200 and row[2]]
        misses = [row for row in results if row[0] == 200 and not row[2]]
        summary.update(cache_hits=len(hits), cache_misses=len(misses))
        summary["hit_p50_ms"], summary["hit_p95_ms"] = percentiles(hits)
        summary["miss_p50_ms"], summary["miss_p95_ms"] = percentiles(misses)
    print(json.dumps(summary))
    return 1 if failures or stopped.is_set() else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, RuntimeError) as error:
        print(json.dumps({"status": "failed", "error": type(error).__name__}))
        raise SystemExit(1)
