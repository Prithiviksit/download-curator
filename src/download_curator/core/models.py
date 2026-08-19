"""
Data models and Enums for download-curator.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ProposalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    IGNORED = "ignored"
    EXECUTED = "executed"
    UNDONE = "undone"


class AuditAction(str, Enum):
    DISCOVERED = "discovered"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    IGNORED = "ignored"
    EDITED = "edited"
    EXECUTED = "executed"
    UNDONE = "undone"


class ExtractedMetadata(BaseModel):
    file_type: str = "unknown"
    title: Optional[str] = None
    authors: List[str] = Field(default_factory=list)
    year: Optional[int] = None
    date: Optional[str] = None  # YYYY-MM-DD or YYYY-MM
    merchant_or_institution: Optional[str] = None
    topic_or_subject: Optional[str] = None
    version: Optional[str] = None
    architecture: Optional[str] = None
    application_name: Optional[str] = None
    dataset_name: Optional[str] = None
    excerpt: Optional[str] = None
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)


class ProposalResult(BaseModel):
    suggested_filename: str
    category: str
    destination: str  # Destination subfolder relative to destination_root or category folder
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

    @field_validator("suggested_filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("suggested_filename cannot be empty")
        return v


class Proposal(BaseModel):
    id: Optional[int] = None
    file_hash: str
    current_path: str
    original_path: str
    proposed_filename: str
    proposed_destination: str  # Category or relative path from destination root
    category: str
    confidence: float = 0.0
    reason: str = ""
    extracted_metadata: Optional[ExtractedMetadata] = None
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    executed_at: Optional[datetime] = None
    executed_path: Optional[str] = None

    @property
    def file_exists(self) -> bool:
        return Path(self.current_path).exists()


class AuditRecord(BaseModel):
    id: Optional[int] = None
    proposal_id: Optional[int] = None
    action: AuditAction
    source_path: str
    destination_path: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class ReviewActionType(str, Enum):
    APPROVE = "approve"
    APPROVE_ALL = "approve_all"
    EDIT = "edit"
    REJECT = "reject"
    SKIP = "skip"
    IGNORE = "ignore"
    OPEN = "open"
    REVEAL = "reveal"
    QUIT = "quit"


class EditProposalRequest(BaseModel):
    proposed_filename: Optional[str] = None
    proposed_destination: Optional[str] = None
    category: Optional[str] = None
