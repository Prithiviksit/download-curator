"""
Unit tests for CuratorEngine orchestrator and approval enforcement invariants.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from download_curator.core.engine import CuratorEngine
from download_curator.core.models import ProposalStatus
from download_curator.core.safety import SafetyViolationError


def test_scan_and_process_never_moves_file(test_engine: CuratorEngine, mock_downloads_dir: Path) -> None:
    """Core safety invariant: scan and proposal creation MUST NOT rename or move files."""
    test_file = mock_downloads_dir / "sample_paper.txt"
    test_file.write_text("# Deep Learning Survey\n\nA comprehensive review of models.\n")

    # Run scan
    proposals = test_engine.scan()
    assert len(proposals) == 1

    # Invariant check: original file MUST still exist in ~/Downloads untouched!
    assert test_file.exists()
    assert test_file.read_text().startswith("# Deep Learning Survey")

    # Proposals must be in pending status
    pending = test_engine.get_pending_proposals()
    assert len(pending) == 1
    assert pending[0].status == ProposalStatus.PENDING


def test_ignores_temporary_and_incomplete_downloads(test_engine: CuratorEngine, mock_downloads_dir: Path) -> None:
    """Ensure .crdownload, .part, .download, and hidden files are ignored."""
    (mock_downloads_dir / "video.mp4.crdownload").write_text("in progress")
    (mock_downloads_dir / "installer.dmg.download").write_text("in progress")
    (mock_downloads_dir / "archive.zip.part").write_text("in progress")
    (mock_downloads_dir / ".DS_Store").write_text("hidden")
    (mock_downloads_dir / ".~lock.file.docx#").write_text("lock")

    proposals = test_engine.scan()
    assert len(proposals) == 0
    assert len(test_engine.get_pending_proposals()) == 0


def test_explicit_approval_moves_file(test_engine: CuratorEngine, mock_downloads_dir: Path, mock_dest_dir: Path) -> None:
    """Only explicit approval triggers the move operation."""
    test_file = mock_downloads_dir / "presentation.txt"
    test_file.write_text("# Team Strategy 2026\nQuarterly goals.\n")

    test_engine.scan()
    pending = test_engine.get_pending_proposals()
    assert len(pending) == 1
    prop = pending[0]

    # Explicit approve
    final_path = test_engine.approve_proposal(prop.id)  # type: ignore

    # Verify source is moved
    assert not test_file.exists()
    assert final_path.exists()
    assert final_path.read_text().startswith("# Team Strategy 2026")
    assert final_path.parent.resolve() == (mock_dest_dir / prop.proposed_destination).resolve()

    # Verify status in database
    updated_prop = test_engine.get_proposal(prop.id)  # type: ignore
    assert updated_prop.status == ProposalStatus.EXECUTED
    assert updated_prop.executed_path == str(final_path)


def test_reject_leaves_file_untouched(test_engine: CuratorEngine, mock_downloads_dir: Path) -> None:
    test_file = mock_downloads_dir / "notes.txt"
    test_file.write_text("some notes")

    test_engine.scan()
    pending = test_engine.get_pending_proposals()
    assert len(pending) == 1
    prop = pending[0]

    test_engine.reject_proposal(prop.id)  # type: ignore

    # File remains in place
    assert test_file.exists()
    assert len(test_engine.get_pending_proposals()) == 0

    updated = test_engine.get_proposal(prop.id)  # type: ignore
    assert updated.status == ProposalStatus.REJECTED


def test_ignore_permanently_skips_file(test_engine: CuratorEngine, mock_downloads_dir: Path) -> None:
    test_file = mock_downloads_dir / "scratch.txt"
    test_file.write_text("scratch file")

    test_engine.scan()
    pending = test_engine.get_pending_proposals()
    prop = pending[0]

    test_engine.ignore_file(prop.id)  # type: ignore

    # File remains untouched in Downloads
    assert test_file.exists()

    # Re-scanning should NOT propose it again
    new_proposals = test_engine.scan()
    assert len(new_proposals) == 0
