"""
Unit tests for filesystem safety, collision prevention, and path traversal guards.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from download_curator.config import SafetySettings
from download_curator.core.safety import (
    CollisionError,
    SafetyViolationError,
    is_safe_path,
    resolve_collision,
    safe_atomic_move,
    sanitize_filename,
    validate_operation_paths,
)


def test_sanitize_filename_removes_invalid_characters() -> None:
    unsafe = 'Paper: Title/With\\Invalid*Chars?"<>|And\x00Null.pdf'
    cleaned = sanitize_filename(unsafe)
    assert ":" not in cleaned
    assert "/" not in cleaned
    assert "\\" not in cleaned
    assert "*" not in cleaned
    assert "?" not in cleaned
    assert '"' not in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "|" not in cleaned
    assert "\x00" not in cleaned
    assert cleaned.endswith(".pdf")


def test_sanitize_filename_length_limit() -> None:
    long_name = "A" * 300 + ".docx"
    cleaned = sanitize_filename(long_name, max_length=50)
    assert len(cleaned) <= 50
    assert cleaned.endswith(".docx")


def test_is_safe_path_detects_traversal(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()

    inside_path = allowed_root / "subdir" / "file.txt"
    outside_path = tmp_path / "outside.txt"
    traversal_path = allowed_root / ".." / "outside.txt"

    assert is_safe_path(inside_path, [allowed_root]) is True
    assert is_safe_path(outside_path, [allowed_root]) is False
    assert is_safe_path(traversal_path, [allowed_root]) is False


def test_validate_operation_paths_guards_unauthorized_source(tmp_path: Path) -> None:
    allowed_src = tmp_path / "downloads"
    allowed_src.mkdir()
    allowed_dst = tmp_path / "organized"
    allowed_dst.mkdir()

    unauthorized_src = tmp_path / "system" / "secret.txt"
    unauthorized_src.parent.mkdir()
    unauthorized_src.write_text("secret")

    dest_file = allowed_dst / "secret.txt"

    with pytest.raises(SafetyViolationError, match="outside allowed source directories"):
        validate_operation_paths(
            source_path=unauthorized_src,
            destination_path=dest_file,
            allowed_sources=[allowed_src],
            allowed_destinations=[allowed_dst],
        )


def test_validate_operation_paths_guards_unauthorized_destination(tmp_path: Path) -> None:
    allowed_src = tmp_path / "downloads"
    allowed_src.mkdir()
    allowed_dst = tmp_path / "organized"
    allowed_dst.mkdir()

    src_file = allowed_src / "valid.txt"
    src_file.write_text("content")

    unauthorized_dst = tmp_path / "etc" / "malicious.txt"

    with pytest.raises(SafetyViolationError, match="outside allowed destination roots"):
        validate_operation_paths(
            source_path=src_file,
            destination_path=unauthorized_dst,
            allowed_sources=[allowed_src],
            allowed_destinations=[allowed_dst],
        )


def test_resolve_collision_increments_filename(tmp_path: Path) -> None:
    target_dir = tmp_path / "dest"
    target_dir.mkdir()

    file1 = target_dir / "paper.pdf"
    file1.write_text("first")

    # Should resolve to paper (1).pdf
    candidate = resolve_collision(file1, strategy="rename_increment")
    assert candidate.name == "paper (1).pdf"
    candidate.write_text("second")

    # Next should resolve to paper (2).pdf
    candidate2 = resolve_collision(file1, strategy="rename_increment")
    assert candidate2.name == "paper (2).pdf"


def test_resolve_collision_abort_strategy(tmp_path: Path) -> None:
    target_dir = tmp_path / "dest"
    target_dir.mkdir()
    file1 = target_dir / "paper.pdf"
    file1.write_text("exists")

    with pytest.raises(CollisionError):
        resolve_collision(file1, strategy="abort")


def test_safe_atomic_move_never_deletes_without_copy(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    src_file = src_dir / "document.pdf"
    src_file.write_text("important data")

    settings = SafetySettings(
        allowed_source_directories=[src_dir],
        allowed_destination_roots=[dst_dir],
        preserve_metadata=True,
    )

    final_dst = safe_atomic_move(src_file, dst_dir / "document.pdf", settings)

    assert final_dst.exists()
    assert final_dst.read_text() == "important data"
    assert not src_file.exists()


def test_safe_atomic_move_preserves_metadata(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()

    src_file = src_dir / "data.csv"
    src_file.write_text("a,b,c")

    # Set specific mtime in the past
    past_mtime = 1600000000.0
    os.utime(src_file, (past_mtime, past_mtime))

    settings = SafetySettings(
        allowed_source_directories=[src_dir],
        allowed_destination_roots=[dst_dir],
        preserve_metadata=True,
    )

    final_dst = safe_atomic_move(src_file, dst_dir / "data.csv", settings)
    assert int(final_dst.stat().st_mtime) == int(past_mtime)
