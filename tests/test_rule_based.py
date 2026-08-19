"""
Unit tests for rule-based proposal generator and naming templates.
"""

from __future__ import annotations

from pathlib import Path
import pytest

from download_curator.ai.rule_based import RuleBasedProvider
from download_curator.config import CuratorConfig
from download_curator.core.models import ExtractedMetadata


def test_rule_based_academic_paper() -> None:
    provider = RuleBasedProvider()
    config = CuratorConfig()

    metadata = ExtractedMetadata(
        file_type="pdf",
        title="Credit Markets and Firm Dynamics",
        authors=["Daron Acemoglu", "James Smith"],
        year=2026,
        excerpt="Abstract: We develop a quantitative model of credit markets...",
    )

    file_path = Path("/mock/Downloads/2408.12345.pdf")
    proposal = provider.generate_proposal(file_path, metadata, config)

    assert proposal.category == "Academic Papers"
    assert proposal.destination == "Academic Papers"
    assert proposal.suggested_filename == "Acemoglu_Smith_2026_Credit_Markets_And_Firm_Dynamics.pdf"
    assert proposal.confidence >= 0.90


def test_rule_based_invoice() -> None:
    provider = RuleBasedProvider()
    config = CuratorConfig()

    metadata = ExtractedMetadata(
        file_type="pdf",
        merchant_or_institution="Apple Store",
        date="2026-08-15",
        raw_metadata={"is_invoice": True},
        excerpt="Tax Invoice for Apple Developer Subscription...",
    )

    file_path = Path("/mock/Downloads/invoice_august.pdf")
    proposal = provider.generate_proposal(file_path, metadata, config)

    assert proposal.category == "Invoices & Receipts"
    assert proposal.destination == "Financial/Invoices"
    assert "Apple_Store_2026-08-15_Invoice.pdf" in proposal.suggested_filename


def test_rule_based_financial_statement() -> None:
    provider = RuleBasedProvider()
    config = CuratorConfig()

    metadata = ExtractedMetadata(
        file_type="pdf",
        merchant_or_institution="Chase Bank",
        date="2026-08",
        raw_metadata={"is_statement": True},
        excerpt="Monthly statement of account ending in 4321...",
    )

    file_path = Path("/mock/Downloads/statement_chase.pdf")
    proposal = provider.generate_proposal(file_path, metadata, config)

    assert proposal.category == "Financial Statements"
    assert proposal.destination == "Financial/Statements"
    assert "Chase_Bank_2026-08_Statement.pdf" in proposal.suggested_filename


def test_rule_based_installer() -> None:
    provider = RuleBasedProvider()
    config = CuratorConfig()

    metadata = ExtractedMetadata(
        file_type="installer",
        application_name="Docker Desktop",
        version="4.30.0",
        architecture="arm64",
    )

    file_path = Path("/mock/Downloads/Docker-4.30.0-arm64.dmg")
    proposal = provider.generate_proposal(file_path, metadata, config)

    assert proposal.category == "Installers"
    assert proposal.destination == "Installers"
    assert proposal.suggested_filename == "Docker_Desktop_4.30.0_arm64.dmg"


def test_rule_based_slides() -> None:
    provider = RuleBasedProvider()
    config = CuratorConfig()

    metadata = ExtractedMetadata(
        file_type="pptx",
        title="Agentic AI Systems Overview",
        topic_or_subject="Agentic AI Systems Overview",
    )

    file_path = Path("/mock/Downloads/presentation1.pptx")
    proposal = provider.generate_proposal(file_path, metadata, config)

    assert proposal.category == "Slides"
    assert proposal.destination == "Presentations"
    assert proposal.suggested_filename == "Agentic_Ai_Systems_Overview.pptx"


def test_rule_based_unclassified_fallback() -> None:
    provider = RuleBasedProvider()
    config = CuratorConfig()

    metadata = ExtractedMetadata(
        file_type="bin",
        title="unknown_payload",
    )

    file_path = Path("/mock/Downloads/unknown_payload.bin")
    proposal = provider.generate_proposal(file_path, metadata, config)

    assert proposal.category == "Unclassified"
    assert proposal.confidence <= 0.5
