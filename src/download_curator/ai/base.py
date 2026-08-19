"""
Base AI / Rule Provider Interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from download_curator.config import CuratorConfig
from download_curator.core.models import ExtractedMetadata, ProposalResult


class BaseAIProvider(ABC):
    """Abstract base class for proposal generation providers."""

    @abstractmethod
    def generate_proposal(
        self,
        file_path: Path,
        metadata: ExtractedMetadata,
        config: CuratorConfig,
    ) -> ProposalResult:
        """
        Generate a structured proposal for renaming and organizing the file.
        NEVER executes any file operations.
        """
        pass
