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

            # 2. Extract text from first 8 pages (front-matter inspection for books, papers, notes)
            pages_text: List[str] = []
            for i in range(min(8, num_pages)):
                try:
                    page_text = reader.pages[i].extract_text() or ""
                    pages_text.append(page_text)
                except Exception:
                    pass

            full_front_matter = "\n---PAGE---\n".join(pages_text)
            extracted_text = "\n".join(pages_text[:2])
            clean_text = re.sub(r"\s+", " ", full_front_matter).strip()
            metadata.excerpt = clean_text[:1200] if clean_text else None

            # 3. Book / Monograph Detection (ISBN, Library of Congress CIP, Copyright Page, Title Page)
            isbn_match = re.search(r"\b(97[89][-\s]?(?:\d[-\s]?){9}\d)\b", file_path.name + " " + full_front_matter)
            cip_match = re.search(
                r"Library of Congress Cataloging[- ]in[- ]Publication Data\s*\n+([^\n]+)\n+([^\n]+)",
                full_front_matter,
                re.I,
            )
            cp_year_match = re.search(r"(?:©|c©|\(c\)|copyright)\s*(19\d{2}|20\d{2})", full_front_matter, re.I)
            if cp_year_match:
                metadata.year = int(cp_year_match.group(1))
                metadata.date = str(metadata.year)

            if isbn_match or cip_match or num_pages > 80:
                cip_author = None
                cip_title = None
                if cip_match:
                    raw_a = cip_match.group(1).strip()
                    raw_t = cip_match.group(2).strip()
                    a_clean = re.sub(r",\s*\d{4}.*$", "", raw_a)
                    a_clean = re.sub(r"\(.*?\)", "", a_clean).strip()
                    if "," in a_clean:
                        parts = [p.strip() for p in a_clean.split(",", 1)]
                        cip_author = f"{parts[1]} {parts[0]}".strip()
                    else:
                        cip_author = a_clean
                    cip_title = raw_t.rstrip(".").strip()

                if not cip_author:
                    affil_match = re.search(
                        r"([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+)+)\s*\n\s*(?:Department of|School of|Faculty of|University of|[A-Z][a-z]+ University)",
                        full_front_matter,
                    )
                    if affil_match:
                        cip_author = affil_match.group(1).strip()

                # Find clean Title Page lines from front matter
                cover_title = None
                for p_txt in pages_text[:5]:
                    raw_lines = [l.strip() for l in p_txt.split("\n") if l.strip()]
                    if not (1 <= len(raw_lines) <= 8):
                        continue
                    if any(re.search(r"(series in|advisors:|editorial board|table of contents|^contents\b|for \w+…|who was very eager)", l, re.I) for l in raw_lines[:2]):
                        continue
                    clean_lines = [
                        l for l in raw_lines
                        if not re.search(r"(isbn|doi:|http|subject classification|department of|university|all rights|springer series|advisors:|editorial board|\b\d{3}\b)", l, re.I)
                    ]
                    if clean_lines:
                        non_pub_lines = [
                            l for l in clean_lines
                            if not re.search(r"(springer|wiley|cambridge|oxford|new york|berlin|heidelberg|london|paris|tokyo|boston|singapore|publish|press)", l, re.I)
                        ]
                        if cip_author:
                            author_tokens = set(re.findall(r"\w+", cip_author.lower()))
                            t_lines = [
                                l for l in non_pub_lines
                                if not (set(re.findall(r"\w+", l.lower())) & author_tokens and len(set(re.findall(r"\w+", l.lower())) & author_tokens) >= 2)
                            ]
                            if t_lines:
                                cover_title = " ".join(t_lines)
                                break
                        elif len(non_pub_lines) >= 2:
                            cover_title = " ".join(non_pub_lines[1:])
                            cip_author = non_pub_lines[0]
                            break

                if cip_author or cover_title or isbn_match:
                    metadata.raw_metadata["is_book"] = True
                    if isbn_match:
                        metadata.raw_metadata["isbn"] = isbn_match.group(1)

                    if cip_author:
                        metadata.authors = [cip_author]

                    if cover_title:
                        metadata.title = cover_title
                    elif cip_title:
                        metadata.title = cip_title

                    # Build high-quality excerpt for AI
                    excerpt_parts = []
                    if cover_title and cip_author:
                        excerpt_parts.append(f"[Title Page]:\n{cip_author}\n{cover_title}")
                    if cip_match:
                        excerpt_parts.append("[Library of Congress CIP]:\n" + cip_match.group(0))
                    if excerpt_parts:
                        metadata.excerpt = "\n\n".join(excerpt_parts)

            # 4. Course and Lecture Notes Detection (only if not already confirmed as a book monograph)
            if not metadata.raw_metadata.get("is_book"):
                course_match = re.search(r"\b([A-Z]{2,5}\s*\d{2,4}[A-Za-z]?)\b(?::|\s+-|\s+)", clean_text[:800])
                # Filter corporate/metadata False positives
                if course_match and course_match.group(1).replace(" ", "").upper() in {"AG", "GMBH", "INC", "LLC", "LTD", "CORP", "ISBN", "PAGE", "VOL", "CHAP", "SEC", "DOC", "PDF"}:
                    course_match = None

                lecture_match = re.search(
                    r"\b(Lecture|Class|Discussion|Recitation|Handout|Problem Set|HW|Homework)\s*(?:#|No\.?|Number)?\s*(\d+)?(?::|-)?\s*([^\n\*†\n]+)",
                    extracted_text[:1000],
                    re.I,
                )

            if course_match or (lecture_match and lecture_match.group(2)):
                raw_course = course_match.group(1).replace(" ", "").upper() if course_match else ""
                unit_type = lecture_match.group(1).capitalize() if lecture_match else "Lecture"
                unit_num = lecture_match.group(2) if (lecture_match and lecture_match.group(2)) else ""
                raw_topic = lecture_match.group(3).strip() if (lecture_match and lecture_match.group(3)) else ""
                clean_topic = re.sub(r"[\*†‡§\d]+$", "", raw_topic).strip()

                metadata.raw_metadata["is_lecture_notes"] = True
                if raw_course:
                    metadata.raw_metadata["course_code"] = raw_course
                if unit_num:
                    metadata.raw_metadata["lecture_unit"] = f"{unit_type}{unit_num}"
                elif unit_type:
                    metadata.raw_metadata["lecture_unit"] = unit_type
                if clean_topic:
                    metadata.raw_metadata["lecture_topic"] = clean_topic
                    metadata.title = clean_topic

                # Find instructor name from line right after lecture line or copyright footnote
                lines = [l.strip() for l in extracted_text.split("\n") if l.strip()]
                instructor_found = None
                for i, line in enumerate(lines[:10]):
                    if re.search(r"\b(Lecture|Class|Discussion|Recitation|Handout|CS\d|ECON\d|MATH\d)\b", line, re.I):
                        if i + 1 < len(lines):
                            cand = re.sub(r"[\*†‡§\d]", "", lines[i + 1]).strip()
                            if re.match(r"^[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+$", cand) and not re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december|stanford|university|mit|harvard|berkeley|department)", cand, re.I):
                                instructor_found = cand
                                break

                # Footnote copyright check if not found
                if not instructor_found:
                    cp_match = re.search(r"(?:©|c©|\(c\))\s*(?:\d{4})?,?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)", clean_text[:1500])
                    if cp_match:
                        instructor_found = cp_match.group(1).strip()

                if instructor_found and not metadata.authors:
                    metadata.authors = [instructor_found]

            # 4. Academic Paper Heuristics
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
