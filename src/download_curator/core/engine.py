"""
Core Curator Engine.
Orchestrates metadata extraction, proposal generation, safety validation,
explicit approval execution, and undo workflows.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from download_curator.ai.base import BaseAIProvider
from download_curator.ai.provider_factory import get_ai_provider
from download_curator.config import CuratorConfig, load_config
from download_curator.core.database import (
    CuratorDatabase,
    compute_file_fingerprint,
)
from download_curator.core.models import (
    AuditAction,
    AuditRecord,
    Proposal,
    ProposalStatus,
)
from download_curator.core.notifier import MacNotifier, get_default_notifier
from download_curator.core.safety import (
    SafetyViolationError,
    safe_atomic_move,
    sanitize_filename,
)
from download_curator.core.watcher import is_ignored_file
from download_curator.extractors.registry import extract_metadata

logger = logging.getLogger("download_curator.engine")


class CuratorEngine:
    """Central engine for safe download management."""

    def __init__(
        self,
        config: Optional[CuratorConfig] = None,
        db: Optional[CuratorDatabase] = None,
        ai_provider: Optional[BaseAIProvider] = None,
        notifier: Optional[MacNotifier] = None,
    ):
        self.config = config or load_config()
        self.db = db or CuratorDatabase(self.config.database_path)
        self.ai_provider = ai_provider or get_ai_provider(self.config)
        self.notifier = notifier or get_default_notifier()

    def process_file(self, file_path: Path, notify: bool = True) -> Optional[Proposal]:
        """
        Process a completed download file (READ-ONLY).
        Generates proposal and stores in database. NEVER touches or moves the file.
        """
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            return None

        if is_ignored_file(path, self.config):
            return None

        fingerprint = compute_file_fingerprint(path)

        # Check if file is ignored
        if self.db.is_file_ignored(fingerprint):
            return None

        # Check existing proposal
        existing = self.db.get_proposal_by_hash(fingerprint)
        if existing:
            if existing.status in (ProposalStatus.EXECUTED, ProposalStatus.IGNORED):
                return None
            if existing.status == ProposalStatus.PENDING:
                return existing

        # Extract metadata (read-only)
        metadata = extract_metadata(path)

        # Generate proposal via AI or rule-based provider
        result = self.ai_provider.generate_proposal(path, metadata, self.config)

        # Ensure safe filename
        safe_name = sanitize_filename(
            result.suggested_filename,
            max_length=self.config.safety.max_filename_length,
        )

        proposal = Proposal(
            file_hash=fingerprint,
            current_path=str(path),
            original_path=str(path),
            proposed_filename=safe_name,
            proposed_destination=result.destination,
            category=result.category,
            confidence=result.confidence,
            reason=result.reason,
            extracted_metadata=metadata,
            status=ProposalStatus.PENDING,
        )

        saved = self.db.add_or_update_proposal(proposal)

        if notify:
            self.notifier.notify_new_download(path.name)

        return saved

    def scan(self, dry_run: bool = False) -> List[Proposal]:
        """
        Scan watch_directory for uncurated downloads (READ-ONLY).
        Generates proposals. NEVER renames or moves any file.
        """
        watch_dir = self.config.watch_directory
        if not watch_dir.exists():
            return []

        created_proposals: List[Proposal] = []

        try:
            entries = list(watch_dir.iterdir())
        except Exception as e:
            logger.error(f"Failed to list directory {watch_dir}: {e}")
            return []

        # Sort by mtime descending
        entries.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)

        for entry in entries:
            if not entry.is_file():
                continue
            if is_ignored_file(entry, self.config):
                continue

            try:
                fingerprint = compute_file_fingerprint(entry)
                if self.db.is_file_ignored(fingerprint):
                    continue

                existing = self.db.get_proposal_by_hash(fingerprint)
                if existing:
                    if existing.status in (ProposalStatus.EXECUTED, ProposalStatus.IGNORED):
                        continue
                    if not dry_run:
                        created_proposals.append(existing)
                    continue

                # Extract and propose
                metadata = extract_metadata(entry)
                result = self.ai_provider.generate_proposal(entry, metadata, self.config)
                safe_name = sanitize_filename(
                    result.suggested_filename,
                    max_length=self.config.safety.max_filename_length,
                )

                proposal = Proposal(
                    file_hash=fingerprint,
                    current_path=str(entry),
                    original_path=str(entry),
                    proposed_filename=safe_name,
                    proposed_destination=result.destination,
                    category=result.category,
                    confidence=result.confidence,
                    reason=result.reason,
                    rule_based_filename=safe_name,
                    rule_based_destination=result.destination,
                    extracted_metadata=metadata,
                    status=ProposalStatus.PENDING,
                )

                if dry_run:
                    created_proposals.append(proposal)
                else:
                    saved = self.db.add_or_update_proposal(proposal)
                    created_proposals.append(saved)
            except Exception as e:
                logger.warning(f"Error processing file {entry}: {e}")

        if created_proposals and not dry_run:
            self.notifier.notify_new_download(f"{len(created_proposals)} files")

        return created_proposals

    def enhance_with_ai(self, proposal_id: int) -> Proposal:
        """Run configured AI model on an existing proposal to generate an AI suggestion for comparison."""
        proposal = self.db.get_proposal_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found.")

        file_path = Path(proposal.current_path)
        metadata = proposal.extracted_metadata or (extract_metadata(file_path) if file_path.exists() else None)
        if not metadata:
            metadata = ExtractedMetadata()

        # Always generate rule-based proposal for comparison baseline
        from download_curator.ai.rule_based import RuleBasedProvider
        rule_res = RuleBasedProvider().generate_proposal(file_path, metadata, self.config)
        safe_rule_name = sanitize_filename(
            rule_res.suggested_filename,
            max_length=self.config.safety.max_filename_length,
        )
        proposal.rule_based_filename = safe_rule_name
        proposal.rule_based_destination = rule_res.destination

        # Run configured AI provider
        ai_res = self.ai_provider.generate_proposal(file_path, metadata, self.config)
        safe_ai_name = sanitize_filename(
            ai_res.suggested_filename,
            max_length=self.config.safety.max_filename_length,
        )

        proposal.ai_filename = safe_ai_name
        proposal.ai_destination = ai_res.destination
        proposal.ai_reason = ai_res.reason
        proposal.ai_confidence = ai_res.confidence

        updated = self.db.add_or_update_proposal(proposal)
        return updated

    def get_pending_proposals(self) -> List[Proposal]:
        """Fetch all pending proposals whose source files still exist."""
        all_pending = self.db.get_pending_proposals()
        valid = []
        for p in all_pending:
            if p.file_exists:
                valid.append(p)
        return valid

    def get_proposal(self, proposal_id: int) -> Optional[Proposal]:
        return self.db.get_proposal_by_id(proposal_id)

    def edit_proposal(
        self,
        proposal_id: int,
        proposed_filename: Optional[str] = None,
        proposed_destination: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[Proposal]:
        """Update proposed filename or destination without executing."""
        if proposed_filename:
            proposed_filename = sanitize_filename(
                proposed_filename,
                max_length=self.config.safety.max_filename_length,
            )
        return self.db.edit_proposal(
            proposal_id=proposal_id,
            proposed_filename=proposed_filename,
            proposed_destination=proposed_destination,
            category=category,
        )

    def reject_proposal(self, proposal_id: int) -> bool:
        """Explicitly reject a proposal. Leaves source file untouched."""
        proposal = self.db.get_proposal_by_id(proposal_id)
        if not proposal:
            return False

        self.db.update_proposal_status(proposal_id, ProposalStatus.REJECTED)
        self.db.record_audit(
            AuditRecord(
                proposal_id=proposal_id,
                action=AuditAction.REJECTED,
                source_path=proposal.current_path,
                details={"reason": "User rejected proposal"},
            )
        )
        return True

    def ignore_file(self, proposal_id: int) -> bool:
        """Permanently ignore a file. Leaves source file untouched."""
        proposal = self.db.get_proposal_by_id(proposal_id)
        if not proposal:
            return False

        self.db.ignore_file(
            file_hash=proposal.file_hash,
            file_path=proposal.current_path,
            reason="User permanently ignored file",
        )
        self.db.record_audit(
            AuditRecord(
                proposal_id=proposal_id,
                action=AuditAction.IGNORED,
                source_path=proposal.current_path,
                details={"reason": "User permanently ignored file"},
            )
        )
        return True

    def approve_proposal(
        self,
        proposal_id: int,
        custom_filename: Optional[str] = None,
        custom_destination: Optional[str] = None,
    ) -> Path:
        """
        EXPLICIT APPROVAL ACTION.
        Deterministically executes safe move/rename with full collision and security checks.
        """
        proposal = self.db.get_proposal_by_id(proposal_id)
        if not proposal:
            raise SafetyViolationError(f"Proposal ID {proposal_id} not found.")

        src_path = Path(proposal.current_path).expanduser().resolve()
        if not src_path.exists():
            raise SafetyViolationError(f"Source file no longer exists: {src_path}")

        # Determine target filename and directory
        target_filename = custom_filename or proposal.proposed_filename
        target_filename = sanitize_filename(
            target_filename,
            max_length=self.config.safety.max_filename_length,
        )

        subfolder = custom_destination or proposal.proposed_destination
        dest_dir = (self.config.destination_root / subfolder).expanduser().resolve()
        target_path = dest_dir / target_filename

        # Perform verified safe atomic move
        final_path = safe_atomic_move(
            src_path,
            target_path,
            self.config.safety,
        )

        # Update database state
        self.db.update_proposal_status(
            proposal_id=proposal_id,
            status=ProposalStatus.EXECUTED,
            executed_path=str(final_path),
        )

        # Record immutable audit log
        self.db.record_audit(
            AuditRecord(
                proposal_id=proposal_id,
                action=AuditAction.EXECUTED,
                source_path=str(src_path),
                destination_path=str(final_path),
                details={
                    "original_path": proposal.original_path,
                    "final_path": str(final_path),
                    "category": proposal.category,
                    "reason": proposal.reason,
                },
            )
        )

        return final_path

    def undo(self, proposal_id: Optional[int] = None) -> Path:
        """
        Undo the last executed move (or specific proposal).
        Checks collisions before undoing to guarantee no overwrites.
        """
        if proposal_id:
            proposal = self.db.get_proposal_by_id(proposal_id)
        else:
            proposal = self.db.get_last_executed_proposal()

        if not proposal:
            raise SafetyViolationError("No executed proposal found to undo.")

        if proposal.status != ProposalStatus.EXECUTED or not proposal.executed_path:
            raise SafetyViolationError(f"Proposal {proposal.id} is not in executed state.")

        current_file = Path(proposal.executed_path).expanduser().resolve()
        if not current_file.exists():
            raise SafetyViolationError(f"Executed file no longer exists at: {current_file}")

        original_target = Path(proposal.original_path).expanduser().resolve()

        # For undo, source is the organized location and destination is original source directory
        undo_safety = self.config.safety.model_copy()
        combined_roots = list(
            set(self.config.safety.allowed_source_directories + self.config.safety.allowed_destination_roots)
        )
        undo_safety.allowed_source_directories = combined_roots
        undo_safety.allowed_destination_roots = combined_roots

        # Perform verified safe atomic move back to original location
        restored_path = safe_atomic_move(
            current_file,
            original_target,
            undo_safety,
        )

        # Update state in DB
        self.db.update_proposal_status(
            proposal_id=proposal.id,  # type: ignore
            status=ProposalStatus.UNDONE,
            executed_path=None,
        )

        # Record audit log
        self.db.record_audit(
            AuditRecord(
                proposal_id=proposal.id,
                action=AuditAction.UNDONE,
                source_path=str(current_file),
                destination_path=str(restored_path),
                details={"restored_to": str(restored_path)},
            )
        )

        return restored_path

    def get_history(self, limit: int = 50) -> List[AuditRecord]:
        return self.db.get_audit_history(limit=limit)
