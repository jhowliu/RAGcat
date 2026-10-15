"""Model interfaces, Bedrock adapters and deterministic offline fakes.

The fakes are good enough to exercise the whole pipeline: the embedder is a hashing
vectorizer (lexical similarity), and the LLM answers extractively from the best passage.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Iterator, Protocol

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from ragcat.shared.config import Settings
from ragcat.shared.errors import UpstreamUnavailable
from ragcat.shared.text import CJK_RANGES, join_text, sentences


# Bedrock on-demand quotas are small on student accounts: back off and retry on throttling.
BEDROCK_CONFIG = Config(retries={"mode": "adaptive", "max_attempts": 8}, read_timeout=60)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


def checked_embedding(value: object, dims: int) -> list[float]:
    """Reject malformed provider output before it can corrupt the vector index."""
    if not isinstance(value, list) or len(value) != dims:
        raise ValueError("Embedding dimension mismatch")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError("Embedding values must be finite numbers")
    return [float(v) for v in value]


@dataclass
class LlmUsage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class LlmStream:
    """Iterate for text deltas; `usage` is filled in once the stream ends."""

    chunks: Iterator[str]
    usage: LlmUsage = field(default_factory=LlmUsage)

    def __iter__(self) -> Iterator[str]:
        return self.chunks


class Llm(Protocol):
    def stream(self, system: str, prompt: str) -> LlmStream: ...
    def complete(self, prompt: str, max_tokens: int) -> str: ...


class VisionModel(Protocol):
    def describe(self, image_jpeg: bytes, prompt: str) -> str: ...


_WORD = re.compile(r"[a-z0-9]+")
_CJK_RUN = re.compile(f"[{CJK_RANGES}]+")
_STOP = set(
    "a an and are as at be by can do does for from has have how i if in is it its may of on or our "
    "so than that the their them there this to was we what when where which who will with you your".split()
)


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _terms(text: str) -> list[str]:
    """Stemmed words and word bigrams; CJK text (no spaces) contributes characters and character bigrams."""
    words = [_stem(w) for w in _WORD.findall(text.lower()) if w not in _STOP]
    runs = _CJK_RUN.findall(text)
    cjk = [ch for run in runs for ch in run] + [run[i : i + 2] for run in runs for i in range(len(run) - 1)]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])] + cjk


class FakeEmbedder:
    def __init__(self, dims: int) -> None:
        self.dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vec = [0.0] * self.dims
        for term in _terms(text):
            digest = hashlib.blake2b(term.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dims
            vec[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeLlm:
    """Picks the passage sharing most terms with the question and quotes its first sentences."""

    def stream(self, system: str, prompt: str) -> LlmStream:
        question = prompt.rsplit("Question:", 1)[-1].strip()
        passages = re.findall(r"^\[(\d+)\][^\n]*\n(.*?)(?=^\[\d+\]|^Question:)", prompt, flags=re.M | re.S)
        q_terms = set(_terms(question))
        best, best_score = None, 0
        for n, text in passages:
            score = len(q_terms & set(_terms(text)))
            if score > best_score:
                best, best_score = (n, text.strip()), score
        if best is None:
            answer = "NO_ANSWER"
        else:
            first_two = sentences(" ".join(best[1].split()))[:2]
            answer = join_text(join_text(*first_two) if len(first_two) == 2 else first_two[0], f"[{best[0]}]")
        usage = LlmUsage(input_tokens=len(prompt.split()), output_tokens=len(answer.split()))
        return LlmStream(iter(re.findall(r"\S+\s*", answer)), usage)

    def complete(self, prompt: str, max_tokens: int) -> str:
        """Contextual-retrieval stand-in: names the document and section the passage is in, and tags
        the section as its one entity."""
        title = re.search(r"^Document: (.*)$", prompt, re.M)
        section = re.search(r"^Section: (.*)$", prompt, re.M)
        name = section.group(1) if section and section.group(1) != "(none)" else ""
        where = f"the section “{name}”" if name else "the document"
        context = f"This passage is from {title.group(1) if title else 'the document'}, in {where}."
        return json.dumps({"context": context, "entities": [{"name": name, "type": "policy"}] if name else []}, ensure_ascii=False)


class FakeVision:
    """Offline stand-in: 'describes' a figure from the text found in and around it, and treats a
    figure without any text as decorative."""

    def describe(self, image_jpeg: bytes, prompt: str) -> str:
        hints = prompt.rsplit("nearby words:", 1)[-1].strip()
        if hints in ("", "(none)"):
            return "DECORATIVE"
        return "A figure with the text: " + " · ".join(hints.split())[:300]


class BedrockEmbedder:
    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.embed_model_id
        self.dims = settings.embed_dims
        self.client = boto3.client("bedrock-runtime", region_name=settings.region, config=BEDROCK_CONFIG)
        self._pool = ThreadPoolExecutor(max_workers=8)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            return list(self._pool.map(self._one, texts))
        except (BotoCoreError, ClientError, ValueError, KeyError, TypeError) as exc:
            raise UpstreamUnavailable("Embedding model is unavailable") from exc

    def _one(self, text: str) -> list[float]:
        body = json.dumps({"inputText": text, "dimensions": self.dims, "normalize": True})
        out = self.client.invoke_model(modelId=self.model_id, body=body, contentType="application/json")
        return checked_embedding(json.loads(out["body"].read())["embedding"], self.dims)


class BedrockLlm:
    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.llm_model_id
        self.client = boto3.client("bedrock-runtime", region_name=settings.region, config=BEDROCK_CONFIG)

    def stream(self, system: str, prompt: str) -> LlmStream:
        try:
            response = self.client.converse_stream(
                modelId=self.model_id,
                system=[{"text": system}],
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 400, "temperature": 0.2},
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailable("Language model is unavailable") from exc
        result = LlmStream(iter(()))

        def chunks() -> Iterator[str]:
            try:
                for event in response["stream"]:
                    if "contentBlockDelta" in event:
                        text = event["contentBlockDelta"]["delta"].get("text")
                        if text:
                            yield text
                    elif "metadata" in event:
                        usage = event["metadata"].get("usage", {})
                        result.usage = LlmUsage(usage.get("inputTokens", 0), usage.get("outputTokens", 0))
            except (BotoCoreError, ClientError) as exc:
                raise UpstreamUnavailable("Language model is unavailable") from exc
            finally:
                close = getattr(response["stream"], "close", None)
                if close is not None:
                    close()

        result.chunks = chunks()
        return result

    def complete(self, prompt: str, max_tokens: int) -> str:
        try:
            out = self.client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": max_tokens, "temperature": 0.0},
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailable("Language model is unavailable") from exc
        return "".join(block.get("text", "") for block in out["output"]["message"]["content"]).strip()


class BedrockVision:
    def __init__(self, settings: Settings) -> None:
        self.model_id = settings.vision_model_id
        self.client = boto3.client("bedrock-runtime", region_name=settings.region, config=BEDROCK_CONFIG)

    def describe(self, image_jpeg: bytes, prompt: str) -> str:
        try:
            out = self.client.converse(
                modelId=self.model_id,
                messages=[{"role": "user", "content": [{"image": {"format": "jpeg", "source": {"bytes": image_jpeg}}}, {"text": prompt}]}],
                inferenceConfig={"maxTokens": 350, "temperature": 0.0},
            )
        except (BotoCoreError, ClientError) as exc:
            raise UpstreamUnavailable("Vision model is unavailable") from exc
        return "".join(block.get("text", "") for block in out["output"]["message"]["content"]).strip()
