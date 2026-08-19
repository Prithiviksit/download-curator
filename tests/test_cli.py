"""
Unit tests for Typer CLI commands.
"""

from __future__ import annotations

import os
from pathlib import Path
from typer.testing import CliRunner
import yaml

from download_curator.cli import app

os.environ["DISABLE_NOTIFICATIONS"] = "1"
runner = CliRunner()


def test_cli_config_show(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_data = {"watch_directory": str(tmp_path)}
    cfg_file.write_text(yaml.dump(cfg_data))

    result = runner.invoke(app, ["config", "show", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "watch_directory" in result.stdout


def test_cli_scan_dry_run(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "document.txt").write_text("# Title\nBody")

    cfg_file = tmp_path / "config.yaml"
    cfg_data = {
        "watch_directory": str(downloads),
        "destination_root": str(tmp_path / "Organized"),
        "database_path": str(tmp_path / "db.sqlite"),
        "safety": {
            "allowed_source_directories": [str(downloads)],
            "allowed_destination_roots": [str(tmp_path / "Organized")],
        },
    }
    cfg_file.write_text(yaml.dump(cfg_data))

    result = runner.invoke(app, ["scan", "--dry-run", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "Dry run mode" in result.stdout


def test_cli_pending_json(tmp_path: Path) -> None:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    (downloads / "notes.txt").write_text("notes")

    cfg_file = tmp_path / "config.yaml"
    cfg_data = {
        "watch_directory": str(downloads),
        "destination_root": str(tmp_path / "Organized"),
        "database_path": str(tmp_path / "db.sqlite"),
        "safety": {
            "allowed_source_directories": [str(downloads)],
            "allowed_destination_roots": [str(tmp_path / "Organized")],
        },
    }
    cfg_file.write_text(yaml.dump(cfg_data))

    # Scan first to populate DB
    runner.invoke(app, ["scan", "--config", str(cfg_file)])

    # Query pending as JSON
    result = runner.invoke(app, ["pending", "--json", "--config", str(cfg_file)])
    assert result.exit_code == 0
    assert "proposed_filename" in result.stdout


def test_cli_launchd_plist() -> None:
    result = runner.invoke(app, ["launchd", "plist"])
    assert result.exit_code == 0
    assert "com.user.download-curator" in result.stdout
