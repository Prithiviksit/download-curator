"""
Factory to instantiate the appropriate AI / Rule provider.
"""

from __future__ import annotations

import logging
from typing import Optional

from download_curator.ai.base import BaseAIProvider
from download_curator.ai.llm_providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from download_curator.ai.rule_based import RuleBasedProvider
from download_curator.config import CuratorConfig

logger = logging.getLogger("download_curator.ai")


def get_ai_provider(config: CuratorConfig) -> BaseAIProvider:
    """Instantiate and return the configured AI provider, with rule-based fallback."""
    provider_name = (config.ai.provider or "rule_based").lower().strip()
    api_key = config.ai.api_key

    if provider_name == "gemini":
        if api_key:
            return GeminiProvider(api_key=api_key, model=config.ai.model)
        logger.info("No Gemini API key found, using rule-based provider.")
        return RuleBasedProvider()

    elif provider_name == "openai":
        if api_key:
            return OpenAIProvider(
                api_key=api_key,
                model=config.ai.model,
                base_url=config.ai.base_url,
            )
        logger.info("No OpenAI API key found, using rule-based provider.")
        return RuleBasedProvider()

    elif provider_name == "openrouter":
        if api_key:
            return OpenAIProvider(
                api_key=api_key,
                model=config.ai.model or "anthropic/claude-3.5-haiku",
                base_url=config.ai.base_url or "https://openrouter.ai/api/v1",
                custom_headers={
                    "HTTP-Referer": "https://github.com/Prithiviksit/download-curator",
                    "X-Title": "Download Curator",
                },
            )
        logger.info("No OpenRouter API key found, using rule-based provider.")
        return RuleBasedProvider()

    elif provider_name == "deepseek":
        if api_key:
            return OpenAIProvider(
                api_key=api_key,
                model=config.ai.model or "deepseek-chat",
                base_url=config.ai.base_url or "https://api.deepseek.com",
            )
        logger.info("No DeepSeek API key found, using rule-based provider.")
        return RuleBasedProvider()

    elif provider_name in ("opencode", "openai_compatible", "custom"):
        return OpenAIProvider(
            api_key=api_key or "not-needed",
            model=config.ai.model or "default",
            base_url=config.ai.base_url or "http://localhost:8000/v1",
        )

    elif provider_name == "anthropic":
        if api_key:
            return AnthropicProvider(api_key=api_key, model=config.ai.model)
        logger.info("No Anthropic API key found, using rule-based provider.")
        return RuleBasedProvider()

    elif provider_name == "ollama":
        return OllamaProvider(model=config.ai.model, base_url=config.ai.base_url)

    return RuleBasedProvider()
