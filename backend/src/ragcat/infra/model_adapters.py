"""Select model adapters at the composition root; callers only know Embedder/Llm/VisionModel."""

from __future__ import annotations

from dataclasses import dataclass

from ragcat.infra.claude import ClaudeLlm
from ragcat.infra.models import BedrockEmbedder, BedrockLlm, BedrockVision, Embedder, FakeEmbedder, FakeLlm, FakeVision, Llm, VisionModel
from ragcat.infra.openai import OpenAiEmbedder
from ragcat.shared.config import Settings


@dataclass(frozen=True)
class ModelAdapters:
    embedder: Embedder
    llm: Llm
    vision: VisionModel


def build_model_adapters(settings: Settings) -> ModelAdapters:
    embedding = {
        "fake": lambda: FakeEmbedder(settings.embed_dims),
        "openai": lambda: OpenAiEmbedder(settings),
        "bedrock": lambda: BedrockEmbedder(settings),
    }
    language = {"fake": lambda: FakeLlm(), "claude": lambda: ClaudeLlm(settings), "bedrock": lambda: BedrockLlm(settings)}
    vision = {"fake": lambda: FakeVision(), "bedrock": lambda: BedrockVision(settings)}
    if settings.embed_provider not in embedding or settings.llm_provider not in language or settings.vision_provider not in vision:
        raise ValueError("Unsupported model provider; refusing to fall back to fake models")
    return ModelAdapters(embedding[settings.embed_provider](), language[settings.llm_provider](), vision[settings.vision_provider]())
