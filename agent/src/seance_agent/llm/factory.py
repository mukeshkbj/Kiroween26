"""Pick the provider from settings (REQ-009, REQ-011).

An unknown provider cannot reach here (``Settings`` rejects it). A known provider
without credentials yields ``(None-or-provider, available=False)``: the service
starts, ``session_state.llm.available`` is false, and a user message gets
``llm_unavailable`` instead of a crash.
"""
from __future__ import annotations

from ..config import LlmProviderName, Settings, llm_availability
from .base import LlmProvider
from .scripted import DemoLlm


def build_llm(settings: Settings) -> tuple[LlmProvider | None, bool]:
    """Returns ``(provider_or_None, available)``."""
    available = llm_availability(settings)
    if settings.llm_provider is LlmProviderName.SCRIPTED:
        return DemoLlm(), True
    if not available:
        return None, False
    if settings.llm_provider is LlmProviderName.ANTHROPIC:
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings), True
    from .bedrock_provider import BedrockProvider

    return BedrockProvider(settings), True
