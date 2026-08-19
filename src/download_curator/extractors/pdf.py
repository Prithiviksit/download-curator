"""
PDF metadata and text extractor.
Supports academic papers, books, invoices, statements, and general PDF documents.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Set
from pypdf import PdfReader

from download_curator.core.models import ExtractedMetadata
from download_curator.extractors.base import BaseExtractor


class PDFExtractor(BaseExtractor):
    """Extracts structured metadata and excerpts from PDF files."""

    @property
    def supported_extensions(self) -> Set[str]:
        return {".pdf"}

    def extract(self, file_path: Path) -> ExtractedMetadata:
        metadata = ExtractedMetadata(file_type="pdf")

        try:
            reader = PdfReader(str(file_path))
            num_pages = len(reader.pages)
            metadata.raw_metadata["page_count"] = num_pages

            # 1. Embedded PDF Document Info
            doc_info = reader.metadata
            if doc_info:
                if doc_info.title:
                    raw_title = str(doc_info.title).strip()
                    garbage_title = re.search(r"(\.indd|\.eps|\.ps|\.pdf|\.tex|untitled|microsoft word)", raw_title, re.I)
                    if raw_title and not garbage_title and len(raw_title) > 3:
                        metadata.title = raw_title
                if doc_info.author:
                    raw_author = str(doc_info.author).strip()
                    if raw_author:
                        candidates = [a.strip() for a in re.split(r"[,;]| and | & ", raw_author) if a.strip()]
                        valid_authors = []
                        for a in candidates:
                            # Must have alphabetic characters and not be generic system names
                            if re.search(r"[a-zA-Z]{2,}", a) and not re.match(r"^(admin|user|unknown|author|root|administrator|fonter)\b", a, re.I):
                                valid_authors.append(a)
                        if valid_authors:
                            metadata.authors = valid_authors

                # Check creation date in metadata (e.g. D:20240815120000)
                creation_date_str = str(doc_info.get("/CreationDate", "") or doc_info.get("/ModDate", ""))
                date_match = re.search(r"D:(\d{4})(\d{2})(\d{2})", creation_date_str)
                if date_match:
                    year_val = int(date_match.group(1))
                    month_val = date_match.group(2)
                    day_val = date_match.group(3)
                    if 1950 <= year_val <= 2050:
                        metadata.year = year_val
                        metadata.date = f"{year_val}-{month_val}-{day_val}"

            # 2. Extract text from first 2 pages
            extracted_text = ""
            for i in range(min(2, num_pages)):
                try:
                    page_text = reader.pages[i].extract_text() or ""
                    extracted_text += page_text + "\n"
                except Exception:
                    pass

            clean_text = re.sub(r"\s+", " ", extracted_text).strip()
            metadata.excerpt = clean_text[:1200] if clean_text else None

            # 3. Academic Paper Heuristics
            # arXiv check from filename or content
            arxiv_match = re.search(r"(?:arXiv:)?(\d{2})(\d{2})\.(\d{4,5})", file_path.name + " " + clean_text)
            if arxiv_match:
                arxiv_year_short = int(arxiv_match.group(1))
                arxiv_year = 2000 + arxiv_year_short
                if 2000 <= arxiv_year <= 2035:
                    metadata.year = arxiv_year
                    metadata.raw_metadata["arxiv_id"] = arxiv_match.group(0)

            # Look for 4-digit years in first 1000 characters if year not yet found
            if not metadata.year:
                years = re.findall(r"\b(19\d{2}|20\d{2})\b", clean_text[:1000])
                if years:
                    # Prefer the most recent plausible year <= current year + 1
                    current_year = datetime.now().year + 1
                    valid_years = [int(y) for y in years if 1970 <= int(y) <= current_year]
                    if valid_years:
                        metadata.year = valid_years[-1]

            # Infer Title from first page if missing or generic
            if not metadata.title and extracted_text:
                lines = [l.strip() for l in extracted_text.split("\n") if l.strip()]
                # Filter out header garbage
                candidate_lines = []
                for line in lines[:10]:
                    if len(line) < 4:
                        continue
                    if re.match(r"^(arxiv:|doi:|issn:|volume|page|\d+$|http)", line, re.I):
                        continue
                    if "abstract" in line.lower():
                        break
                    candidate_lines.append(line)
                    if len(candidate_lines) >= 2 or len(line) > 30:
                        break

                if candidate_lines:
                    metadata.title = " ".join(candidate_lines)

            # Infer Authors from first page text if missing
            if not metadata.authors and extracted_text:
                lines = [l.strip() for l in extracted_text.split("\n") if l.strip()]
                for i, line in enumerate(lines[:12]):
                    if metadata.title and metadata.title in line:
                        # Authors often in the line immediately after title
                        if i + 1 < len(lines):
                            potential_author_line = lines[i + 1]
                            if (
                                len(potential_author_line) < 100
                                and "abstract" not in potential_author_line.lower()
                                and not re.search(r"(university|department|email|institute)", potential_author_line, re.I)
                            ):
                                authors = [
                                    a.strip()
                                    for a in re.split(r"[,;*]| and | & ", potential_author_line)
                                    if a.strip() and len(a.strip()) > 2
                                ]
                                if authors:
                                    metadata.authors = authors[:5]
                                    break

            # 4. Invoice / Statement Heuristics
            # Check for invoice keywords
            if re.search(r"\b(invoice|tax invoice|receipt|bill to|amount due|payment received)\b", clean_text, re.I):
                metadata.raw_metadata["is_invoice"] = True
                # Look for date YYYY-MM-DD or Month DD, YYYY
                date_match = re.search(r"\b(\d{4}[-/.]\d{2}[-/.]\d{2})\b", clean_text)
                if date_match:
                    d_str = date_match.group(1).replace("/", "-").replace(".", "-")
                    metadata.date = d_str

                # Look for Merchant / Company name from top lines
                top_lines = [l.strip() for l in extracted_text.split("\n")[:6] if l.strip()]
                for line in top_lines:
                    if not re.search(r"(invoice|tax|receipt|bill|date|number|#|\d)", line, re.I) and 3 < len(line) < 40:
                        metadata.merchant_or_institution = line
                        break

            elif re.search(r"\b(statement of account|bank statement|monthly statement|account statement)\b", clean_text, re.I):
                metadata.raw_metadata["is_statement"] = True
                # Look for date or month-year
                date_match = re.search(r"\b(\d{4}[-/.]\d{2})\b", clean_text)
                if date_match:
                    metadata.date = date_match.group(1).replace(".", "-").replace("/", "-")

        except Exception as e:
            metadata.raw_metadata["error"] = str(e)

        return metadata
