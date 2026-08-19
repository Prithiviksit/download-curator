"""
Pytest configuration and fixtures.
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest
from download_curator.config import CuratorConfig, SafetySettings
from download_curator.core.database import CuratorDatabase
from download_curator.core.engine import CuratorEngine

os.environ["DISABLE_NOTIFICATIONS"] = "1"


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary directory."""
    return tmp_path


@pytest.fixture
def mock_downloads_dir(temp_dir: Path) -> Path:
    """Create a mock ~/Downloads folder."""
    d = temp_dir / "Downloads"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def mock_dest_dir(temp_dir: Path) -> Path:
    """Create a mock destination root folder."""
    d = temp_dir / "Organized"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def mock_config(mock_downloads_dir: Path, mock_dest_dir: Path, temp_dir: Path) -> CuratorConfig:
    """Provide a test CuratorConfig pointing to temporary directories."""
    db_path = temp_dir / "test_curator.db"
    cfg = CuratorConfig(
        watch_directory=mock_downloads_dir,
        destination_root=mock_dest_dir,
        database_path=db_path,
        safety=SafetySettings(
            allowed_source_directories=[mock_downloads_dir],
            allowed_destination_roots=[mock_dest_dir, mock_downloads_dir],
            collision_strategy="rename_increment",
            preserve_metadata=True,
            atomic_moves=True,
        ),
    )
    return cfg


@pytest.fixture
def test_db(mock_config: CuratorConfig) -> CuratorDatabase:
    """Provide a fresh SQLite test database."""
    return CuratorDatabase(mock_config.database_path)


@pytest.fixture
def test_engine(mock_config: CuratorConfig, test_db: CuratorDatabase) -> CuratorEngine:
    """Provide a test CuratorEngine."""
    return CuratorEngine(config=mock_config, db=test_db)
