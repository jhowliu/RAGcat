"""Claude Messages REST adapter: streaming QA plus short contextual-retrieval completions."""

from __future__ import annotations

import json
import os
from typing import Any, Iterator

import httpx

from ragcat.infra.models import LlmStream, LlmUsage
from ragcat.shared.config import Settings
from ragcat.shared.errors import UpstreamUnavailable


def _events(lines: Iterator[str]) -> Iterator[dict[str, Any]]:
    """Decode SSE data frames, allowing comments, CRLF, multi-line data and new event types."""
    data: list[str] = []
    size = 0
    for line in lines:
        if not line:
            if data:
                value = json.loads("\n".join(data))
                if not isinstance(value, dict) or not isinstance(value.get("type"), str):
                    raise ValueError("Invalid Claude stream event")
                yield value
            data, size = [], 0
        elif line.startswith("data:"):
            chunk = line[5:].lstrip(" ")
            size += len(chunk)
            if size > 262_144:
                raise ValueError("Claude stream event is too large")
            data.append(chunk)
    if data:
        value = json.loads("\n".join(data))
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ValueError("Invalid Claude stream event")
        yield value


def _count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid Claude usage")
    return value


class ClaudeLlm:
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, settings: Settings, *, client: httpx.Client | None = None) -> None:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is required for the claude QA provider")
        self.model_id = settings.llm_model_id
        self._headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
        self._client = client if client is not None else httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=False)

    def _body(self, prompt: str, max_tokens: int, *, system: str = "", stream: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model_id, "max_tokens": max_tokens, "stream": stream,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        if self.model_id == "claude-haiku-5-5":
            # QA/context have small output budgets; default adaptive thinking consumes them.
            body["thinking"] = {"type": "disabled"}
        return body

    def stream(self, system: str, prompt: str) -> LlmStream:
        result = LlmStream(iter(()))

        def chunks() -> Iterator[str]:
            try:
                with self._client.stream("POST", self.URL, headers=self._headers, json=self._body(prompt, 400, system=system, stream=True)) as response:
                    response.raise_for_status()
                    for event in _events(response.iter_lines()):
                        kind = event["type"]
                        if kind == "error":
                            raise UpstreamUnavailable("Language model is unavailable")
                        if kind == "message_start":
                            usage = event["message"].get("usage", {})
                            result.usage = LlmUsage(_count(usage.get("input_tokens", 0)), _count(usage.get("output_tokens", 0)))
                        elif kind == "message_delta":
                            usage = event.get("usage", {})
                            result.usage = LlmUsage(
                                _count(usage.get("input_tokens", result.usage.input_tokens)),
                                _count(usage.get("output_tokens", result.usage.output_tokens)),
                            )
                            if event.get("delta", {}).get("stop_reason") == "max_tokens":
                                raise UpstreamUnavailable("Language model response was truncated")
                        elif kind in ("content_block_start", "content_block_delta"):
                            block = event["content_block"] if kind == "content_block_start" else event["delta"]
                            if block.get("type") in ("text", "text_delta"):
                                text = block.get("text", "")
                                if not isinstance(text, str):
                                    raise ValueError("Invalid Claude text")
                                if text:
                                    yield text
                        elif kind == "message_stop":
                            return
                    raise UpstreamUnavailable("Language model stream ended unexpectedly")
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
                raise UpstreamUnavailable("Language model is unavailable") from exc

        result.chunks = chunks()
        return result

    def complete(self, prompt: str, max_tokens: int) -> str:
        try:
            response = self._client.post(self.URL, headers=self._headers, json=self._body(prompt, max_tokens))
            response.raise_for_status()
            message = response.json()
            if message.get("stop_reason") == "max_tokens":
                raise UpstreamUnavailable("Language model response was truncated")
            text = "".join(block["text"] for block in message["content"] if block.get("type") == "text").strip()
            if not text:
                raise ValueError("Claude returned no text")
            return text
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise UpstreamUnavailable("Language model is unavailable") from exc
