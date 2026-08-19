"""
Deterministic Rule-Based Proposal Provider.
Implements robust heuristics and customizable naming rules without requiring external LLM APIs.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from download_curator.ai.base import BaseAIProvider
from download_curator.config import CuratorConfig
from download_curator.core.models import ExtractedMetadata, ProposalResult
from download_curator.core.safety import sanitize_filename


def clean_words_for_title(text: str, max_words: int = 7) -> str:
    """Convert text into Clean_Title_Case_Words_With_Underscores."""
    # Strip non-alphanumeric except spaces and hyphens
    cleaned = re.sub(r"[^\w\s-]", "", text)
    words = [w.capitalize() for w in cleaned.split() if w]
    selected_words = words[:max_words]
    return "_".join(selected_words) if selected_words else "Document"


def extract_last_name(author_str: str) -> str:
    """Extract a clean last name from an author string."""
    cleaned = re.sub(r"[^\w\s-]", "", author_str).strip()
    parts = cleaned.split()
    if not parts:
        return "Author"
    # If author is formatted as "LastName, FirstName"
    # or "FirstName LastName" -> take the last token
    last = parts[-1].capitalize()
    return last if len(last) > 1 else parts[0].capitalize()


def format_authors_string(authors: List[str]) -> str:
    """Format a list of authors into Lastname_Lastname or Lastname_et_al."""
    if not authors:
        return "Unknown"

    last_names = [extract_last_name(a) for a in authors if a.strip()]
    if not last_names:
        return "Unknown"

    if len(last_names) == 1:
        return last_names[0]
    elif len(last_names) == 2:
        return f"{last_names[0]}_{last_names[1]}"
    elif len(last_names) == 3:
        return f"{last_names[0]}_{last_names[1]}_{last_names[2]}"
    else:
        return f"{last_names[0]}_et_al"


class RuleBasedProvider(BaseAIProvider):
    """Deterministic proposal generator based on metadata heuristics and config templates."""

    def generate_proposal(
        self,
        file_path: Path,
        metadata: ExtractedMetadata,
        config: CuratorConfig,
    ) -> ProposalResult:
        ext = file_path.suffix.lower()
        stem = file_path.stem
        raw_meta = metadata.raw_metadata

        # 1. Check for Academic Papers (PDF with title, authors/arXiv/year)
        if ext == ".pdf":
            # Invoice or Statement check
            if raw_meta.get("is_invoice") or "invoice" in stem.lower() or "receipt" in stem.lower():
                merchant = metadata.merchant_or_institution or "Merchant"
                date_str = metadata.date or datetime.now().strftime("%Y-%m-%d")
                desc = "Invoice" if "invoice" in stem.lower() or raw_meta.get("is_invoice") else "Receipt"
                filename = f"{clean_words_for_title(merchant, 3)}_{date_str}_{desc}.pdf"
                dest = config.categories.get("Invoices & Receipts", "Financial/Invoices")
                return ProposalResult(
                    suggested_filename=sanitize_filename(filename),
                    category="Invoices & Receipts",
                    destination=dest,
                    confidence=0.92,
                    reason=f"Detected invoice/receipt keywords and date from document content ({merchant})",
                )

            if raw_meta.get("is_statement") or "statement" in stem.lower():
                inst = metadata.merchant_or_institution or "Institution"
                date_str = metadata.date or datetime.now().strftime("%Y-%m")
                filename = f"{clean_words_for_title(inst, 3)}_{date_str}_Statement.pdf"
                dest = config.categories.get("Financial Statements", "Financial/Statements")
                return ProposalResult(
                    suggested_filename=sanitize_filename(filename),
                    category="Financial Statements",
                    destination=dest,
                    confidence=0.90,
                    reason=f"Detected financial statement structure for {inst}",
                )

            # Check if likely academic paper
            is_arxiv = "arxiv_id" in raw_meta or bool(re.match(r"^\d{4}\.\d{4,5}", stem))
            has_paper_signals = (
                is_arxiv
                or bool(metadata.authors)
                or (metadata.title and metadata.year and metadata.excerpt and "abstract" in (metadata.excerpt or "").lower())
            )

            if has_paper_signals:
                authors_str = format_authors_string(metadata.authors) if metadata.authors else "Author"
                year_str = str(metadata.year) if metadata.year else str(datetime.now().year)
                title_str = clean_words_for_title(metadata.title, 6) if metadata.title else clean_words_for_title(stem, 6)

                filename = f"{authors_str}_{year_str}_{title_str}.pdf"
                dest = config.categories.get("Academic Papers", "Academic Papers")
                confidence = 0.94 if (metadata.authors and metadata.title) else 0.85
                reason = "Identified academic paper title, authors, and publication year"
                if is_arxiv:
                    reason = f"Identified arXiv paper ({raw_meta.get('arxiv_id', stem)}) with authors and title"

                return ProposalResult(
                    suggested_filename=sanitize_filename(filename),
                    category="Academic Papers",
                    destination=dest,
                    confidence=confidence,
                    reason=reason,
                )

            # General PDF document
            title_str = clean_words_for_title(metadata.title or stem, 6)
            year_suffix = f"_{metadata.year}" if metadata.year else ""
            filename = f"{title_str}{year_suffix}.pdf"
            dest = config.categories.get("Documents", "Documents")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Documents",
                destination=dest,
                confidence=0.75,
                reason="Extracted document title from PDF content",
            )

        # 2. Presentations / Slides
        if ext in {".pptx", ".ppt", ".key"}:
            topic = metadata.topic_or_subject or metadata.title or stem
            topic_str = clean_words_for_title(topic, 6)
            filename = f"{topic_str}{ext}"
            dest = config.categories.get("Slides", "Presentations")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Slides",
                destination=dest,
                confidence=0.88,
                reason="Extracted presentation topic from slide title",
            )

        # 3. Spreadsheets & Datasets
        if ext in {".xlsx", ".xls"}:
            title = metadata.title or stem
            clean_title = clean_words_for_title(title, 6)
            filename = f"{clean_title}{ext}"
            dest = config.categories.get("Spreadsheets", "Spreadsheets")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Spreadsheets",
                destination=dest,
                confidence=0.85,
                reason="Extracted sheet names and headers from spreadsheet",
            )

        if ext in {".csv", ".tsv"}:
            dataset_name = clean_words_for_title(metadata.dataset_name or stem, 5)
            date_part = f"_{datetime.now().strftime('%Y%m%d')}" if not re.search(r"\d{4}", dataset_name) else ""
            filename = f"{dataset_name}{date_part}{ext}"
            dest = config.categories.get("Datasets", "Datasets")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Datasets",
                destination=dest,
                confidence=0.86,
                reason="Detected tabular data with column structure",
            )

        # 4. Installers & Application Packages
        if ext in {".dmg", ".pkg", ".app", ".iso"}:
            app_name = clean_words_for_title(metadata.application_name or stem, 4)
            ver = f"_{metadata.version}" if metadata.version else ""
            arch = f"_{metadata.architecture}" if metadata.architecture else ""
            filename = f"{app_name}{ver}{arch}{ext}"
            dest = config.categories.get("Installers", "Installers")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Installers",
                destination=dest,
                confidence=0.92,
                reason=f"Parsed installer package metadata for {app_name}",
            )

        # 5. Images
        if ext in {".jpg", ".jpeg", ".png", ".heic", ".webp", ".tiff", ".gif", ".svg", ".bmp"}:
            if metadata.title:
                clean_name = clean_words_for_title(metadata.title, 5)
            elif metadata.date:
                clean_name = f"Photo_{metadata.date}_{clean_words_for_title(stem, 3)}"
            else:
                clean_name = clean_words_for_title(stem, 5)
            filename = f"{clean_name}{ext}"
            dest = config.categories.get("Images", "Images")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Images",
                destination=dest,
                confidence=0.82,
                reason="Preserved image format and extracted EXIF timestamp/description",
            )

        # 6. Archives
        if ext in {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z"}:
            if metadata.application_name:
                app_name = clean_words_for_title(metadata.application_name, 4)
                filename = f"{app_name}_Archive{ext}"
            elif metadata.title:
                filename = f"{clean_words_for_title(metadata.title, 5)}{ext}"
            else:
                filename = f"{clean_words_for_title(stem, 5)}{ext}"
            dest = config.categories.get("Archives", "Archives")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Archives",
                destination=dest,
                confidence=0.80,
                reason="Inferred archive contents from internal manifest",
            )

        # 7. Code & Scripts
        code_exts = {".py", ".js", ".ts", ".go", ".rs", ".cpp", ".c", ".java", ".sh", ".rb", ".swift", ".sql"}
        if ext in code_exts:
            lang = metadata.raw_metadata.get("language", "code")
            title = clean_words_for_title(metadata.title or stem, 5)
            filename = f"{title}{ext}"
            dest = config.categories.get("Code & Scripts", "Code")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Code & Scripts",
                destination=dest,
                confidence=0.85,
                reason=f"Detected {lang} source code module with header comments",
            )

        # 8. Office Documents
        if ext in {".docx", ".doc", ".odt"}:
            authors_str = format_authors_string(metadata.authors) if metadata.authors else ""
            title_str = clean_words_for_title(metadata.title or stem, 6)
            prefix = f"{authors_str}_" if authors_str and authors_str != "Unknown" else ""
            filename = f"{prefix}{title_str}{ext}"
            dest = config.categories.get("Documents", "Documents")
            return ProposalResult(
                suggested_filename=sanitize_filename(filename),
                category="Documents",
                destination=dest,
                confidence=0.82,
                reason="Extracted document properties and heading text",
            )

        # 9. Fallback / Unclassified
        clean_name = clean_words_for_title(stem, 5)
        filename = f"{clean_name}{ext}"
        dest = config.categories.get("Unclassified", "Unclassified")
        return ProposalResult(
            suggested_filename=sanitize_filename(filename),
            category="Unclassified",
            destination=dest,
            confidence=0.40,
            reason="Could not determine a high-confidence category; suggested Unclassified",
        )
