"""
Extractors for Text, Markdown, CSV, Config, and Source Code files.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Set

from download_curator.core.models import ExtractedMetadata
from download_curator.extractors.base import BaseExtractor


CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "react_jsx",
    ".tsx": "react_tsx",
    ".go": "go",
    ".rs": "rust",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c_header",
    ".java": "java",
    ".sh": "shell",
    ".zsh": "zsh",
    ".bash": "bash",
    ".rb": "ruby",
    ".swift": "swift",
    ".kt": "kotlin",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
}

TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".xml",
}


class TextExtractor(BaseExtractor):
    @property
    def supported_extensions(self) -> Set[str]:
        return TEXT_EXTENSIONS.union(CODE_EXTENSIONS.keys())

    def extract(self, file_path: Path) -> ExtractedMetadata:
        ext = file_path.suffix.lower()
        is_code = ext in CODE_EXTENSIONS
        file_type = CODE_EXTENSIONS.get(ext, ext.lstrip("."))

        metadata = ExtractedMetadata(file_type=file_type)

        try:
            # Read first 16KB of text safely with UTF-8 fallback
            content = ""
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(16384)

            lines = [l.strip() for l in content.splitlines() if l.strip()]

            if is_code:
                metadata.raw_metadata["language"] = file_type
                # Look for module docstring or top comment
                docstring_match = re.search(r'^[ruRU]?("""|\'\'\')([\s\S]*?)\1', content)
                if docstring_match:
                    doc = docstring_match.group(2).strip()
                    metadata.excerpt = doc[:800]
                    first_doc_line = doc.splitlines()[0].strip()
                    if len(first_doc_line) > 3:
                        metadata.title = first_doc_line[:80]
                else:
                    # Look for top comments
                    top_comments = []
                    for line in lines[:8]:
                        if line.startswith(("//", "#", "/*", "*")):
                            clean_c = re.sub(r"^[/#\*\s]+", "", line).strip()
                            if clean_c:
                                top_comments.append(clean_c)
                    if top_comments:
                        metadata.title = top_comments[0][:80]
                        metadata.excerpt = " ".join(top_comments)[:800]
                    else:
                        metadata.excerpt = content[:800]

            elif ext in {".md", ".markdown", ".rst"}:
                # Look for markdown header # Title
                header_match = re.search(r"^#+\s+(.+)$", content, re.MULTILINE)
                if header_match:
                    metadata.title = header_match.group(1).strip()
                elif lines:
                    metadata.title = lines[0][:80]
                metadata.excerpt = content[:1000]

            else:
                # General text
                if lines:
                    metadata.title = lines[0][:80]
                metadata.excerpt = content[:1000]

        except Exception as e:
            metadata.raw_metadata["error"] = str(e)

        return metadata


class CsvExtractor(BaseExtractor):
    @property
    def supported_extensions(self) -> Set[str]:
        return {".csv", ".tsv"}

    def extract(self, file_path: Path) -> ExtractedMetadata:
        ext = file_path.suffix.lower()
        metadata = ExtractedMetadata(file_type=ext.lstrip("."))

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                sample = f.read(8192)

            delimiter = "\t" if ext == ".tsv" else ","
            try:
                sniffer = csv.Sniffer()
                dialect = sniffer.sniff(sample[:2048])
                delimiter = dialect.delimiter
            except Exception:
                pass

            reader = csv.reader(io.StringIO(sample), delimiter=delimiter)
            rows = list(reader)
            if rows:
                headers = [h.strip() for h in rows[0] if h.strip()]
                metadata.raw_metadata["headers"] = headers[:20]
                metadata.raw_metadata["sample_row_count"] = len(rows)
                metadata.excerpt = f"CSV headers: {', '.join(headers[:10])}. Sample preview: {len(rows)} rows."
                metadata.dataset_name = file_path.stem

        except Exception as e:
            metadata.raw_metadata["error"] = str(e)

        return metadata
