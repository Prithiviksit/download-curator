"""
Installer and application package extractor (DMG, PKG, ISO).
Extracts application name, version, and architecture safely from metadata and filename structure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Set

from download_curator.core.models import ExtractedMetadata
from download_curator.extractors.base import BaseExtractor


class InstallerExtractor(BaseExtractor):
    @property
    def supported_extensions(self) -> Set[str]:
        return {".dmg", ".pkg", ".iso", ".app"}

    def extract(self, file_path: Path) -> ExtractedMetadata:
        ext = file_path.suffix.lower()
        metadata = ExtractedMetadata(file_type="installer")

        stem = file_path.stem

        # Extract architecture if present
        arch_match = re.search(r"[-_](arm64|aarch64|x86_64|x64|amd64|universal|darwin|mac|intel|apple[-_]silicon)\b", stem, re.I)
        if arch_match:
            raw_arch = arch_match.group(1).lower()
            if raw_arch in {"arm64", "aarch64", "apple-silicon", "apple_silicon"}:
                metadata.architecture = "arm64"
            elif raw_arch in {"x86_64", "x64", "amd64", "intel"}:
                metadata.architecture = "x86_64"
            elif raw_arch in {"universal", "darwin", "mac"}:
                metadata.architecture = "Universal"
            else:
                metadata.architecture = raw_arch

        # Extract semantic version if present (e.g. 1.2.3 or 2024.1)
        ver_match = re.search(r"[vV]?(\d+\.\d+(?:\.\d+)*(?:-(?:beta|alpha|rc|patch)\d*)?)", stem)
        if ver_match:
            metadata.version = ver_match.group(1)

        # Extract app name by stripping version, arch, and trailing delimiters
        clean_name = stem
        if arch_match and arch_match.start() > 0:
            clean_name = clean_name[:arch_match.start()]
        if ver_match and ver_match.start() > 0:
            clean_name = clean_name[:ver_match.start()]

        clean_name = re.sub(r"[-_.]+$", "", clean_name).strip()
        clean_name = re.sub(r"[-_]", " ", clean_name)

        if clean_name:
            metadata.application_name = clean_name
            metadata.title = f"{clean_name} Installer"

        metadata.excerpt = (
            f"Installer package for {metadata.application_name or stem}. "
            + (f"Version: {metadata.version}. " if metadata.version else "")
            + (f"Architecture: {metadata.architecture}." if metadata.architecture else "")
        ).strip()

        return metadata
