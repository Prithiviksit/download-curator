"""
AI and Rule-based classification package.
"""

from download_curator.ai.base import BaseAIProvider
from download_curator.ai.provider_factory import get_ai_provider
from download_curator.ai.rule_based import RuleBasedProvider

__all__ = ["BaseAIProvider", "RuleBasedProvider", "get_ai_provider"]
