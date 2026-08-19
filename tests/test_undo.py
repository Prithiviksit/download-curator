"""
Unit tests for the safe undo mechanism.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from download_curator.core.engine import CuratorEngine
from download_curator.core.models import AuditAction, ProposalStatus


def test_undo_restores_file_to_original_path(
    test_engine: CuratorEngine,
    mock_downloads_dir: Path,
) -> None:
    test_file = mock_downloads_dir / "draft_memo.txt"
    test_file.write_text("Confidential Memo Content")

    # 1. Scan & Propose
    test_engine.scan()
    pending = test_engine.get_pending_proposals()
    assert len(pending) == 1
    prop = pending[0]

    # 2. Approve & Execute
    moved_path = test_engine.approve_proposal(prop.id)  # type: ignore
    assert not test_file.exists()
    assert moved_path.exists()

    # 3. Undo
    restored_path = test_engine.undo()
    assert not moved_path.exists()
    assert restored_path.exists()
    assert restored_path == test_file
    assert restored_path.read_text() == "Confidential Memo Content"

    # Verify audit log
    history = test_engine.get_history(limit=5)
    actions = [h.action for h in history]
    assert AuditAction.UNDONE in actions


def test_undo_collision_safety(
    test_engine: CuratorEngine,
    mock_downloads_dir: Path,
) -> None:
    test_file = mock_downloads_dir / "invoice.txt"
    test_file.write_text("Invoice 101")

    test_engine.scan()
    pending = test_engine.get_pending_proposals()
    prop = pending[0]

    moved_path = test_engine.approve_proposal(prop.id)  # type: ignore

    # Simulate a new file created at original location with same name
    test_file.write_text("New file created while original was organized")

    # Undo should NOT overwrite the new file
    restored_path = test_engine.undo()

    assert test_file.exists()
    assert test_file.read_text() == "New file created while original was organized"

    assert restored_path.exists()
    assert restored_path != test_file
    assert restored_path.name == "invoice (1).txt"
    assert restored_path.read_text() == "Invoice 101"
