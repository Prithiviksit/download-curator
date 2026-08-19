"""
Unit tests for modular AI provider factory and OpenAI-compatible endpoints.
"""

from __future__ import annotations

from pathlib import Path
from download_curator.ai.provider_factory import get_ai_provider
from download_curator.ai.llm_providers import OpenAIProvider, GeminiProvider, AnthropicProvider
from download_curator.ai.rule_based import RuleBasedProvider
from download_curator.config import CuratorConfig, AISettings


def test_provider_factory_openrouter() -> None:
    cfg = CuratorConfig(
        ai=AISettings(
            provider="openrouter",
            api_key="sk-or-v1-mock-key",
            model="deepseek/deepseek-chat",
        )
    )
    provider = get_ai_provider(cfg)
    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == "https://openrouter.ai/api/v1"
    assert provider.model == "deepseek/deepseek-chat"
    assert "HTTP-Referer" in provider.custom_headers


def test_provider_factory_deepseek() -> None:
    cfg = CuratorConfig(
        ai=AISettings(
            provider="deepseek",
            api_key="sk-deepseek-mock-key",
            model="deepseek-chat",
        )
    )
    provider = get_ai_provider(cfg)
    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == "https://api.deepseek.com"
    assert provider.model == "deepseek-chat"


def test_provider_factory_opencode_custom() -> None:
    cfg = CuratorConfig(
        ai=AISettings(
            provider="opencode",
            base_url="http://localhost:8000/v1",
            model="qwen-2.5-coder",
        )
    )
    provider = get_ai_provider(cfg)
    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == "http://localhost:8000/v1"
    assert provider.model == "qwen-2.5-coder"


def test_provider_factory_rule_based_fallback_when_no_key() -> None:
    cfg = CuratorConfig(
        ai=AISettings(
            provider="openrouter",
            api_key=None,
        )
    )
    provider = get_ai_provider(cfg)
    assert isinstance(provider, RuleBasedProvider)
