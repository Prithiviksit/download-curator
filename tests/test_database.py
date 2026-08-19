"""
Unit tests for SQLite database state management and audit logging.
"""

from __future__ import annotations

from pathlib import Path
from download_curator.core.database import CuratorDatabase
from download_curator.core.models import (
    AuditAction,
    AuditRecord,
    ExtractedMetadata,
    Proposal,
    ProposalStatus,
)


def test_database_lifecycle(test_db: CuratorDatabase) -> None:
    proposal = Proposal(
        file_hash="abc123hash",
        current_path="/Downloads/test.pdf",
        original_path="/Downloads/test.pdf",
        proposed_filename="Test_Paper.pdf",
        proposed_destination="Academic Papers",
        category="Academic Papers",
        confidence=0.95,
        reason="Found metadata",
        extracted_metadata=ExtractedMetadata(title="Test Paper", authors=["Author A"]),
        status=ProposalStatus.PENDING,
    )

    # Insert proposal
    saved = test_db.add_or_update_proposal(proposal)
    assert saved.id is not None

    # Retrieve pending proposals
    pending = test_db.get_pending_proposals()
    assert len(pending) == 1
    assert pending[0].id == saved.id
    assert pending[0].extracted_metadata is not None
    assert pending[0].extracted_metadata.title == "Test Paper"

    # Edit proposal
    edited = test_db.edit_proposal(
        saved.id,
        proposed_filename="New_Title.pdf",
        proposed_destination="Custom",
    )
    assert edited is not None
    assert edited.proposed_filename == "New_Title.pdf"
    assert edited.proposed_destination == "Custom"

    # Update status to executed
    test_db.update_proposal_status(
        saved.id,
        ProposalStatus.EXECUTED,
        executed_path="/Organized/Custom/New_Title.pdf",
    )

    pending_after = test_db.get_pending_proposals()
    assert len(pending_after) == 0

    last_exec = test_db.get_last_executed_proposal()
    assert last_exec is not None
    assert last_exec.id == saved.id
    assert last_exec.executed_path == "/Organized/Custom/New_Title.pdf"


def test_database_ignored_files(test_db: CuratorDatabase) -> None:
    test_hash = "ignore_hash_999"
    assert test_db.is_file_ignored(test_hash) is False

    test_db.ignore_file(test_hash, "/Downloads/junk.zip", reason="Not needed")
    assert test_db.is_file_ignored(test_hash) is True


def test_database_audit_trail(test_db: CuratorDatabase) -> None:
    record = AuditRecord(
        proposal_id=1,
        action=AuditAction.EXECUTED,
        source_path="/Downloads/doc.pdf",
        destination_path="/Organized/Documents/doc.pdf",
        details={"user": "explicit_approval"},
    )
    saved_record = test_db.record_audit(record)
    assert saved_record.id is not None

    history = test_db.get_audit_history(limit=10)
    assert len(history) >= 1
    assert history[0].action == AuditAction.EXECUTED
    assert history[0].details.get("user") == "explicit_approval"
