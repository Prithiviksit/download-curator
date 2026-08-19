"""
Safe archive inspection (ZIP, TAR).
Inspects internal structure without extracting any files to disk.
"""

from __future__ import annotations

import os
import tarfile
import zipfile
from pathlib import Path
from typing import List, Set

from download_curator.core.models import ExtractedMetadata
from download_curator.extractors.base import BaseExtractor


class ArchiveExtractor(BaseExtractor):
    @property
    def supported_extensions(self) -> Set[str]:
        return {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z"}

    def extract(self, file_path: Path) -> ExtractedMetadata:
        ext = file_path.suffix.lower()
        metadata = ExtractedMetadata(file_type="archive")

        filenames: List[str] = []

        try:
            if ext == ".zip":
                with zipfile.ZipFile(file_path, "r") as zf:
                    # Safe check on total file count
                    infolist = zf.infolist()[:100]
                    filenames = [info.filename for info in infolist]
                    metadata.raw_metadata["total_files"] = len(zf.infolist())

            elif ext in {".tar", ".gz", ".tgz", ".bz2", ".xz"}:
                mode = "r:*" if ext != ".tar" else "r:"
                with tarfile.open(file_path, mode) as tf:
                    members = tf.getmembers()[:100]
                    filenames = [m.name for m in members]
                    metadata.raw_metadata["total_files"] = len(tf.getmembers())

            if filenames:
                # Find common root prefix if any
                first_parts = [f.split("/")[0] for f in filenames if "/" in f]
                common_root = None
                if first_parts and all(p == first_parts[0] for p in first_parts):
                    common_root = first_parts[0]
                    metadata.title = common_root

                # Check if it contains a .app bundle or installer
                app_bundles = [f for f in filenames if ".app/" in f or f.endswith(".app")]
                if app_bundles:
                    app_name = app_bundles[0].split(".app")[0].split("/")[-1]
                    metadata.application_name = app_name
                    metadata.raw_metadata["contains_app"] = app_name

                # Gather extension counts
                exts = [os.path.splitext(f)[1].lower() for f in filenames if os.path.splitext(f)[1]]
                metadata.raw_metadata["sample_extensions"] = list(set(exts))[:10]
                metadata.excerpt = (
                    f"Archive containing {metadata.raw_metadata.get('total_files', len(filenames))} items. "
                    f"Sample files: {', '.join(filenames[:5])}"
                )

        except Exception as e:
            metadata.raw_metadata["error"] = str(e)

        return metadata
