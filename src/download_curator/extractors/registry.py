"""
Extractor registry and dispatcher.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from download_curator.core.models import ExtractedMetadata
from download_curator.extractors.archive import ArchiveExtractor
from download_curator.extractors.base import BaseExtractor
from download_curator.extractors.image import ImageExtractor
from download_curator.extractors.installer import InstallerExtractor
from download_curator.extractors.office import DocxExtractor, PptxExtractor, XlsxExtractor
from download_curator.extractors.pdf import PDFExtractor
from download_curator.extractors.text import CsvExtractor, TextExtractor


class ExtractorRegistry:
    """Maintains and dispatches file content extractors."""

    def __init__(self) -> None:
        self.extractors: List[BaseExtractor] = [
            PDFExtractor(),
            DocxExtractor(),
            XlsxExtractor(),
            PptxExtractor(),
            CsvExtractor(),
            TextExtractor(),
            ImageExtractor(),
            ArchiveExtractor(),
            InstallerExtractor(),
        ]

    def get_extractor(self, file_path: Path) -> Optional[BaseExtractor]:
        for extractor in self.extractors:
            if extractor.can_handle(file_path):
                return extractor
        return None

    def extract(self, file_path: Path) -> ExtractedMetadata:
        extractor = self.get_extractor(file_path)
        if extractor:
            try:
                return extractor.extract(file_path)
            except Exception as e:
                return ExtractedMetadata(
                    file_type=file_path.suffix.lstrip(".").lower() or "unknown",
                    title=file_path.stem,
                    raw_metadata={"error": str(e)},
                )

        # Fallback for unknown extensions
        return ExtractedMetadata(
            file_type=file_path.suffix.lstrip(".").lower() or "unknown",
            title=file_path.stem,
            excerpt=f"File: {file_path.name}",
        )


_DEFAULT_REGISTRY: Optional[ExtractorRegistry] = None


def get_default_registry() -> ExtractorRegistry:
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = ExtractorRegistry()
    return _DEFAULT_REGISTRY


def extract_metadata(file_path: Path) -> ExtractedMetadata:
    """Convenience function to extract metadata from a file."""
    return get_default_registry().extract(file_path)
