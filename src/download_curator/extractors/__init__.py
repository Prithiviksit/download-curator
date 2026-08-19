"""
Metadata and content extractors package.
"""

from download_curator.extractors.base import BaseExtractor
from download_curator.extractors.registry import (
    ExtractorRegistry,
    extract_metadata,
    get_default_registry,
)

__all__ = [
    "BaseExtractor",
    "ExtractorRegistry",
    "extract_metadata",
    "get_default_registry",
]
