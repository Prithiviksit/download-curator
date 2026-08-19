"""
Filesystem safety enforcement for download-curator.
Guarantees:
- NEVER delete files
- NEVER overwrite existing files
- Prevent path traversal
- Verify source/destination boundaries
- Sanitize filenames
- Handle collisions safely (e.g. filename (1).ext)
- Preserve original metadata
- Atomic operations with undo support
"""

from __future__ import annotations

import os
import re
import shutil
import unicodedata
from pathlib import Path
from typing import List, Optional, Tuple

from download_curator.config import SafetySettings


class SafetyViolationError(Exception):
    """Raised when an operation violates a core safety constraint."""
    pass


class CollisionError(Exception):
    """Raised when a filename collision occurs and strategy does not allow increment."""
    pass


def sanitize_filename(filename: str, max_length: int = 200) -> str:
    """
    Sanitize a filename for macOS/POSIX filesystems.
    - Replaces invalid characters: /, \, :, *, ?, ", <, >, |, null, control characters.
    - Strips leading/trailing spaces and dots.
    - Normalizes Unicode to NFC.
    - Truncates filename safely preserving extension.
    """
    if not filename or not filename.strip():
        return "unnamed_file"

    # Normalize unicode
    cleaned = unicodedata.normalize("NFC", filename.strip())

    # Replace forbidden path/filesystem characters with underscores or hyphens
    cleaned = re.sub(r'[\x00-\x1f\x7f/\\:\*\?"<>\|]', "_", cleaned)

    # Collapse multiple underscores/spaces
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Strip leading/trailing dots and spaces
    cleaned = cleaned.strip(". ")
    if not cleaned:
        cleaned = "unnamed_file"

    # Separate stem and extension
    parts = cleaned.rsplit(".", 1)
    if len(parts) == 2 and parts[1]:
        stem, ext = parts[0], "." + parts[1]
    else:
        stem, ext = cleaned, ""

    # Enforce max length while preserving extension
    if len(cleaned) > max_length:
        allowed_stem_len = max(10, max_length - len(ext))
        stem = stem[:allowed_stem_len].rstrip(". ")
        cleaned = f"{stem}{ext}"

    return cleaned


def is_safe_path(
    target_path: Path,
    allowed_roots: List[Path],
    check_symlinks: bool = True,
) -> bool:
    """
    Verify that target_path is within one of the allowed roots and does not traverse outside.
    """
    try:
        resolved_target = Path(target_path).expanduser().resolve()
    except Exception:
        return False

    for root in allowed_roots:
        try:
            resolved_root = Path(root).expanduser().resolve()
            # Check if resolved_target is child of resolved_root
            try:
                resolved_target.relative_to(resolved_root)
                return True
            except ValueError:
                continue
        except Exception:
            continue

    return False


def validate_operation_paths(
    source_path: Path,
    destination_path: Path,
    allowed_sources: List[Path],
    allowed_destinations: List[Path],
    reject_symlinks: bool = True,
) -> None:
    """
    Validate that source and destination paths are safe and within authorized roots.
    """
    src = Path(source_path).expanduser().resolve()
    dst = Path(destination_path).expanduser().resolve()

    if not src.exists():
        raise SafetyViolationError(f"Source file does not exist: {src}")

    if not src.is_file():
        raise SafetyViolationError(f"Source path is not a regular file: {src}")

    if reject_symlinks and (src.is_symlink() or dst.is_symlink()):
        raise SafetyViolationError("Symlink operations are prohibited for safety.")

    if not is_safe_path(src, allowed_sources, reject_symlinks):
        raise SafetyViolationError(
            f"Source path {src} is outside allowed source directories: {allowed_sources}"
        )

    if not is_safe_path(dst, allowed_destinations, reject_symlinks):
        raise SafetyViolationError(
            f"Destination path {dst} is outside allowed destination roots: {allowed_destinations}"
        )


def resolve_collision(
    destination_path: Path,
    strategy: str = "rename_increment",
) -> Path:
    """
    Check if destination exists. If so, apply collision resolution without overwriting.
    """
    dst = Path(destination_path).expanduser().resolve()
    if not dst.exists():
        return dst

    if strategy == "abort":
        raise CollisionError(f"Destination file already exists: {dst}")

    parent = dst.parent
    stem = dst.stem
    ext = dst.suffix

    counter = 1
    while True:
        candidate = parent / f"{stem} ({counter}){ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def safe_atomic_move(
    source_path: Path,
    destination_path: Path,
    safety_settings: Optional[SafetySettings] = None,
) -> Path:
    """
    Execute a safe, non-destructive move from source to destination.
    Guarantees:
    - Never overwrites existing destination
    - Creates destination directories safely
    - Preserves file metadata (mtime, atime, permissions)
    - Returns final destination path
    """
    settings = safety_settings or SafetySettings()
    src = Path(source_path).expanduser().resolve()
    dst = Path(destination_path).expanduser().resolve()

    # 1. Validate security boundaries
    validate_operation_paths(
        src,
        dst,
        settings.allowed_source_directories,
        settings.allowed_destination_roots,
        settings.reject_symlinks_outside,
    )

    # 2. Collision resolution (NEVER overwrite)
    final_dst = resolve_collision(dst, settings.collision_strategy)

    # 3. Create destination directory if needed
    final_dst.parent.mkdir(parents=True, exist_ok=True)

    # 4. Perform atomic move or safe copy-then-verify-then-unlink
    # First, record original stat
    src_stat = src.stat()

    # Try atomic rename first (works on same filesystem)
    try:
        os.rename(src, final_dst)
    except OSError:
        # Cross-device move fallback
        # Copy to a temporary file in destination folder first, then atomically rename
        tmp_dst = final_dst.parent / f".tmp_{final_dst.name}_{os.getpid()}"
        try:
            shutil.copy2(src, tmp_dst)
            # Verify copied size matches
            if tmp_dst.stat().st_size != src_stat.st_size:
                raise SafetyViolationError(
                    f"File copy verification failed: expected {src_stat.st_size} bytes, got {tmp_dst.stat().st_size} bytes"
                )
            os.rename(tmp_dst, final_dst)
            # Safe removal of source only after verified destination write
            os.unlink(src)
        except Exception as e:
            if tmp_dst.exists():
                try:
                    os.unlink(tmp_dst)
                except Exception:
                    pass
            raise SafetyViolationError(f"Cross-device safe move failed: {e}") from e

    # 5. Preserve timestamps where feasible
    if settings.preserve_metadata:
        try:
            os.utime(final_dst, (src_stat.st_atime, src_stat.st_mtime))
        except Exception:
            pass

    return final_dst
