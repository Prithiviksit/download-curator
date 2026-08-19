"""
Base Extractor Interface and models.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Set

from download_curator.core.models import ExtractedMetadata


class BaseExtractor(ABC):
    """Abstract base class for file metadata and content extractors."""

    @property
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        """Set of lowercase extensions supported by this extractor (e.g. {'.pdf'})."""
        pass

    def can_handle(self, file_path: Path) -> bool:
        """Check if this extractor can handle the given file."""
        return file_path.suffix.lower() in self.supported_extensions

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractedMetadata:
        """
        Extract metadata and text excerpt from the file.
        MUST BE READ-ONLY. NEVER modify or lock the file.
        """
        pass
