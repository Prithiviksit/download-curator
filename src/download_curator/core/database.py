"""
SQLite State Database and Audit Log for download-curator.
Thread-safe and WAL-mode enabled for concurrent CLI and background operations.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from download_curator.core.models import (
    AuditAction,
    AuditRecord,
    ExtractedMetadata,
    Proposal,
    ProposalStatus,
)


def compute_file_fingerprint(path: Path) -> str:
    """
    Compute a fast and reliable fingerprint for a file using size, mtime,
    and partial sha256 (first 64KB and last 64KB).
    """
    stat = path.stat()
    size = stat.st_size
    mtime = int(stat.st_mtime)

    hasher = hashlib.sha256()
    hasher.update(f"{size}:{mtime}:".encode("utf-8"))

    if size > 0:
        with open(path, "rb") as f:
            first_chunk = f.read(65536)
            hasher.update(first_chunk)
            if size > 65536:
                f.seek(max(0, size - 65536))
                last_chunk = f.read(65536)
                hasher.update(last_chunk)

    return hasher.hexdigest()


class CuratorDatabase:
    """Thread-safe SQLite database manager."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=30.0,
            check_same_thread=False,
            isolation_level=None,  # Autocommit mode
        )
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for concurrent read/write
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS proposals (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_hash TEXT NOT NULL,
                        current_path TEXT NOT NULL,
                        original_path TEXT NOT NULL,
                        proposed_filename TEXT NOT NULL,
                        proposed_destination TEXT NOT NULL,
                        category TEXT NOT NULL,
                        confidence REAL NOT NULL,
                        reason TEXT NOT NULL,
                        extracted_metadata TEXT,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        executed_at TEXT,
                        executed_path TEXT
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_proposals_hash ON proposals(file_hash);
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_proposals_current_path ON proposals(current_path);
                    """
                )

                # Migrate comparison columns if they do not exist yet
                for col_name, col_type in [
                    ("rule_based_filename", "TEXT"),
                    ("rule_based_destination", "TEXT"),
                    ("ai_filename", "TEXT"),
                    ("ai_destination", "TEXT"),
                    ("ai_reason", "TEXT"),
                    ("ai_confidence", "REAL"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE proposals ADD COLUMN {col_name} {col_type};")
                    except Exception:
                        pass

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        proposal_id INTEGER,
                        action TEXT NOT NULL,
                        source_path TEXT NOT NULL,
                        destination_path TEXT,
                        details TEXT,
                        timestamp TEXT NOT NULL
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_audit_proposal ON audit_log(proposal_id);
                    """
                )

                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ignored_files (
                        file_hash TEXT PRIMARY KEY,
                        file_path TEXT NOT NULL,
                        reason TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )

    def _row_to_proposal(self, row: sqlite3.Row) -> Proposal:
        metadata = None
        if row["extracted_metadata"]:
            try:
                metadata_dict = json.loads(row["extracted_metadata"])
                metadata = ExtractedMetadata(**metadata_dict)
            except Exception:
                pass

        keys = row.keys()
        return Proposal(
            id=row["id"],
            file_hash=row["file_hash"],
            current_path=row["current_path"],
            original_path=row["original_path"],
            proposed_filename=row["proposed_filename"],
            proposed_destination=row["proposed_destination"],
            category=row["category"],
            confidence=row["confidence"],
            reason=row["reason"],
            rule_based_filename=row["rule_based_filename"] if "rule_based_filename" in keys else None,
            rule_based_destination=row["rule_based_destination"] if "rule_based_destination" in keys else None,
            ai_filename=row["ai_filename"] if "ai_filename" in keys else None,
            ai_destination=row["ai_destination"] if "ai_destination" in keys else None,
            ai_reason=row["ai_reason"] if "ai_reason" in keys else None,
            ai_confidence=row["ai_confidence"] if "ai_confidence" in keys else None,
            extracted_metadata=metadata,
            status=ProposalStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            executed_at=(
                datetime.fromisoformat(row["executed_at"])
                if row["executed_at"]
                else None
            ),
            executed_path=row["executed_path"],
        )

    def add_or_update_proposal(self, proposal: Proposal) -> Proposal:
        """Create a new proposal or update existing pending proposal for unchanged file."""
        with self._lock:
            with self._get_connection() as conn:
                now_iso = datetime.now().isoformat()
                metadata_json = (
                    proposal.extracted_metadata.model_dump_json()
                    if proposal.extracted_metadata
                    else None
                )

                if proposal.id:
                    # Update existing proposal by ID
                    conn.execute(
                        """
                        UPDATE proposals SET
                            proposed_filename = ?,
                            proposed_destination = ?,
                            category = ?,
                            confidence = ?,
                            reason = ?,
                            rule_based_filename = ?,
                            rule_based_destination = ?,
                            ai_filename = ?,
                            ai_destination = ?,
                            ai_reason = ?,
                            ai_confidence = ?,
                            extracted_metadata = ?,
                            status = ?,
                            updated_at = ?,
                            executed_at = ?,
                            executed_path = ?
                        WHERE id = ?;
                        """,
                        (
                            proposal.proposed_filename,
                            proposal.proposed_destination,
                            proposal.category,
                            proposal.confidence,
                            proposal.reason,
                            proposal.rule_based_filename,
                            proposal.rule_based_destination,
                            proposal.ai_filename,
                            proposal.ai_destination,
                            proposal.ai_reason,
                            proposal.ai_confidence,
                            metadata_json,
                            proposal.status.value,
                            now_iso,
                            proposal.executed_at.isoformat() if proposal.executed_at else None,
                            proposal.executed_path,
                            proposal.id,
                        ),
                    )
                    return proposal

                # Check if pending proposal with same file_hash already exists
                existing = self.get_proposal_by_hash(proposal.file_hash)
                if existing and existing.status == ProposalStatus.PENDING:
                    conn.execute(
                        """
                        UPDATE proposals SET
                            current_path = ?,
                            proposed_filename = ?,
                            proposed_destination = ?,
                            category = ?,
                            confidence = ?,
                            reason = ?,
                            rule_based_filename = ?,
                            rule_based_destination = ?,
                            ai_filename = ?,
                            ai_destination = ?,
                            ai_reason = ?,
                            ai_confidence = ?,
                            extracted_metadata = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (
                            proposal.current_path,
                            proposal.proposed_filename,
                            proposal.proposed_destination,
                            proposal.category,
                            proposal.confidence,
                            proposal.reason,
                            proposal.rule_based_filename,
                            proposal.rule_based_destination,
                            proposal.ai_filename,
                            proposal.ai_destination,
                            proposal.ai_reason,
                            proposal.ai_confidence,
                            metadata_json,
                            now_iso,
                            existing.id,
                        ),
                    )
                    proposal.id = existing.id
                    return proposal

                cursor = conn.execute(
                    """
                    INSERT INTO proposals (
                        file_hash, current_path, original_path,
                        proposed_filename, proposed_destination, category,
                        confidence, reason, rule_based_filename, rule_based_destination,
                        ai_filename, ai_destination, ai_reason, ai_confidence,
                        extracted_metadata, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        proposal.file_hash,
                        proposal.current_path,
                        proposal.original_path,
                        proposal.proposed_filename,
                        proposal.proposed_destination,
                        proposal.category,
                        proposal.confidence,
                        proposal.reason,
                        proposal.rule_based_filename,
                        proposal.rule_based_destination,
                        proposal.ai_filename,
                        proposal.ai_destination,
                        proposal.ai_reason,
                        proposal.ai_confidence,
                        metadata_json,
                        proposal.status.value,
                        now_iso,
                        now_iso,
                    ),
                )
                proposal.id = cursor.lastrowid
                self.record_audit(
                    AuditRecord(
                        proposal_id=proposal.id,
                        action=AuditAction.PROPOSED,
                        source_path=proposal.current_path,
                        destination_path=None,
                        details={
                            "proposed_filename": proposal.proposed_filename,
                            "proposed_destination": proposal.proposed_destination,
                            "category": proposal.category,
                            "confidence": proposal.confidence,
                            "reason": proposal.reason,
                        },
                    )
                )
                return proposal

    def get_proposal_by_id(self, proposal_id: int) -> Optional[Proposal]:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM proposals WHERE id = ?;", (proposal_id,)
                ).fetchone()
                return self._row_to_proposal(row) if row else None

    def get_proposal_by_hash(self, file_hash: str) -> Optional[Proposal]:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT * FROM proposals WHERE file_hash = ? ORDER BY id DESC LIMIT 1;",
                    (file_hash,),
                ).fetchone()
                return self._row_to_proposal(row) if row else None

    def get_pending_proposals(self) -> List[Proposal]:
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM proposals WHERE status = 'pending' ORDER BY id ASC;"
                ).fetchall()
                return [self._row_to_proposal(r) for r in rows]

    def get_all_proposals(
        self,
        status: Optional[ProposalStatus] = None,
        limit: int = 100,
    ) -> List[Proposal]:
        with self._lock:
            with self._get_connection() as conn:
                if status:
                    rows = conn.execute(
                        "SELECT * FROM proposals WHERE status = ? ORDER BY id DESC LIMIT ?;",
                        (status.value, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM proposals ORDER BY id DESC LIMIT ?;",
                        (limit,),
                    ).fetchall()
                return [self._row_to_proposal(r) for r in rows]

    def update_proposal_status(
        self,
        proposal_id: int,
        status: ProposalStatus,
        executed_path: Optional[str] = None,
    ) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                now_iso = datetime.now().isoformat()
                executed_at_iso = now_iso if status == ProposalStatus.EXECUTED else None

                if status == ProposalStatus.EXECUTED:
                    cursor = conn.execute(
                        """
                        UPDATE proposals SET
                            status = ?,
                            executed_path = ?,
                            executed_at = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (status.value, executed_path, executed_at_iso, now_iso, proposal_id),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE proposals SET
                            status = ?,
                            updated_at = ?
                        WHERE id = ?;
                        """,
                        (status.value, now_iso, proposal_id),
                    )
                return cursor.rowcount > 0

    def edit_proposal(
        self,
        proposal_id: int,
        proposed_filename: Optional[str] = None,
        proposed_destination: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Optional[Proposal]:
        with self._lock:
            with self._get_connection() as conn:
                proposal = self.get_proposal_by_id(proposal_id)
                if not proposal:
                    return None

                new_filename = (
                    proposed_filename.strip()
                    if proposed_filename
                    else proposal.proposed_filename
                )
                new_destination = (
                    proposed_destination.strip()
                    if proposed_destination
                    else proposal.proposed_destination
                )
                new_category = (
                    category.strip() if category else proposal.category
                )
                now_iso = datetime.now().isoformat()

                conn.execute(
                    """
                    UPDATE proposals SET
                        proposed_filename = ?,
                        proposed_destination = ?,
                        category = ?,
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (new_filename, new_destination, new_category, now_iso, proposal_id),
                )

                self.record_audit(
                    AuditRecord(
                        proposal_id=proposal_id,
                        action=AuditAction.EDITED,
                        source_path=proposal.current_path,
                        details={
                            "old_filename": proposal.proposed_filename,
                            "new_filename": new_filename,
                            "old_destination": proposal.proposed_destination,
                            "new_destination": new_destination,
                            "old_category": proposal.category,
                            "new_category": new_category,
                        },
                    )
                )

                return self.get_proposal_by_id(proposal_id)

    def record_audit(self, record: AuditRecord) -> AuditRecord:
        with self._lock:
            with self._get_connection() as conn:
                details_json = json.dumps(record.details) if record.details else None
                now_iso = record.timestamp.isoformat()
                cursor = conn.execute(
                    """
                    INSERT INTO audit_log (
                        proposal_id, action, source_path, destination_path, details, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        record.proposal_id,
                        record.action.value,
                        record.source_path,
                        record.destination_path,
                        details_json,
                        now_iso,
                    ),
                )
                record.id = cursor.lastrowid
                return record

    def get_audit_history(self, limit: int = 50) -> List[AuditRecord]:
        with self._lock:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?;", (limit,)
                ).fetchall()
                records = []
                for r in rows:
                    details = json.loads(r["details"]) if r["details"] else {}
                    records.append(
                        AuditRecord(
                            id=r["id"],
                            proposal_id=r["proposal_id"],
                            action=AuditAction(r["action"]),
                            source_path=r["source_path"],
                            destination_path=r["destination_path"],
                            details=details,
                            timestamp=datetime.fromisoformat(r["timestamp"]),
                        )
                    )
                return records

    def get_last_executed_proposal(self) -> Optional[Proposal]:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT * FROM proposals
                    WHERE status = 'executed' AND executed_path IS NOT NULL
                    ORDER BY executed_at DESC, id DESC LIMIT 1;
                    """
                ).fetchone()
                return self._row_to_proposal(row) if row else None

    def is_file_ignored(self, file_hash: str) -> bool:
        with self._lock:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT 1 FROM ignored_files WHERE file_hash = ?;", (file_hash,)
                ).fetchone()
                return row is not None

    def ignore_file(
        self,
        file_hash: str,
        file_path: str,
        reason: str = "User ignored",
    ) -> None:
        with self._lock:
            with self._get_connection() as conn:
                now_iso = datetime.now().isoformat()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO ignored_files (
                        file_hash, file_path, reason, created_at
                    ) VALUES (?, ?, ?, ?);
                    """,
                    (file_hash, file_path, reason, now_iso),
                )
                # Also mark any existing proposal as ignored
                conn.execute(
                    "UPDATE proposals SET status = 'ignored', updated_at = ? WHERE file_hash = ?;",
                    (now_iso, file_hash),
                )
