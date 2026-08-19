"""
Configuration management for download-curator.
Supports YAML configuration files with sane defaults and environment overrides.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from pydantic import BaseModel, Field


DEFAULT_CONFIG_PATH = Path("~/.download-curator/config.yaml").expanduser()
DEFAULT_DB_PATH = Path("~/.download-curator/curator.db").expanduser()


class AISettings(BaseModel):
    provider: str = "rule_based"  # rule_based, gemini, openai, anthropic, ollama
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    confidence_threshold: float = 0.7


class IgnoreSettings(BaseModel):
    extensions: List[str] = Field(
        default_factory=lambda: [
            ".crdownload",
            ".part",
            ".download",
            ".tmp",
            ".swp",
            ".lock",
            ".DS_Store",
        ]
    )
    patterns: List[str] = Field(
        default_factory=lambda: [
            ".*",
            "~$*",
            "*.tmp",
            "*.crdownload",
            "*.part",
            "*.download",
        ]
    )
    directories: List[str] = Field(
        default_factory=lambda: [
            ".*",
            "Organized",
            "Academic Papers",
            "Books",
            "Presentations",
            "Financial",
            "Datasets",
            "Installers",
            "Images",
            "Archives",
            "Code",
            "Documents",
            "Spreadsheets",
            "Media",
            "Unclassified",
        ]
    )


class SafetySettings(BaseModel):
    allowed_source_directories: List[Path] = Field(
        default_factory=lambda: [Path("~/Downloads").expanduser()]
    )
    allowed_destination_roots: List[Path] = Field(
        default_factory=lambda: [
            Path("~/Downloads").expanduser(),
            Path("~/Documents").expanduser(),
        ]
    )
    collision_strategy: str = "rename_increment"  # "rename_increment" or "abort"
    preserve_metadata: bool = True
    atomic_moves: bool = True
    max_filename_length: int = 200
    reject_symlinks_outside: bool = True


class NamingRuleSettings(BaseModel):
    academic_papers: str = "{authors}_{year}_{short_title}.{ext}"
    books: str = "{authors}_{year}_{title}.{ext}"
    slides: str = "{topic_or_title}.{ext}"
    invoices: str = "{merchant}_{date}_{description}.{ext}"
    statements: str = "{institution}_{date}_Statement.{ext}"
    installers: str = "{app_name}_{version}_{arch}.{ext}"
    datasets: str = "{dataset_name}_{version}_{date}.{ext}"


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 58291
    poll_interval_seconds: float = 2.0


class CuratorConfig(BaseModel):
    watch_directory: Path = Field(
        default_factory=lambda: Path("~/Downloads").expanduser()
    )
    destination_root: Path = Field(
        default_factory=lambda: Path("~/Downloads").expanduser()
    )
    database_path: Path = Field(default_factory=lambda: DEFAULT_DB_PATH)
    categories: Dict[str, str] = Field(
        default_factory=lambda: {
            "Academic Papers": "Academic Papers",
            "Books": "Books",
            "Slides": "Presentations",
            "Invoices & Receipts": "Financial/Invoices",
            "Financial Statements": "Financial/Statements",
            "Datasets": "Datasets",
            "Installers": "Installers",
            "Images": "Images",
            "Archives": "Archives",
            "Code & Scripts": "Code",
            "Documents": "Documents",
            "Spreadsheets": "Spreadsheets",
            "Audio & Video": "Media",
            "Unclassified": "Unclassified",
        }
    )
    naming_rules: NamingRuleSettings = Field(default_factory=NamingRuleSettings)
    ignore: IgnoreSettings = Field(default_factory=IgnoreSettings)
    ai: AISettings = Field(default_factory=AISettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    server: ServerSettings = Field(default_factory=ServerSettings)

    def model_post_init(self, __context: Any) -> None:
        self.watch_directory = Path(self.watch_directory).expanduser().resolve()
        self.destination_root = Path(self.destination_root).expanduser().resolve()
        self.database_path = Path(self.database_path).expanduser().resolve()
        self.safety.allowed_source_directories = [
            Path(p).expanduser().resolve()
            for p in self.safety.allowed_source_directories
        ]
        self.safety.allowed_destination_roots = [
            Path(p).expanduser().resolve()
            for p in self.safety.allowed_destination_roots
        ]


def load_config(config_path: Optional[Path] = None) -> CuratorConfig:
    """Load configuration from YAML file or return defaults."""
    if config_path:
        target_path = Path(config_path).expanduser().resolve()
    elif Path("config.yaml").exists():
        target_path = Path("config.yaml").resolve()
    else:
        target_path = DEFAULT_CONFIG_PATH

    if target_path.exists():
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            config = CuratorConfig(**data)
        except Exception:
            # Fall back to defaults on error
            config = CuratorConfig()
    else:
        config = CuratorConfig()

    # Environment variable overrides
    if os.environ.get("CURATOR_AI_PROVIDER"):
        config.ai.provider = os.environ["CURATOR_AI_PROVIDER"]
    if os.environ.get("GEMINI_API_KEY"):
        config.ai.api_key = os.environ["GEMINI_API_KEY"]
    elif os.environ.get("OPENROUTER_API_KEY"):
        config.ai.api_key = os.environ["OPENROUTER_API_KEY"]
        if not os.environ.get("CURATOR_AI_PROVIDER") and config.ai.provider == "rule_based":
            config.ai.provider = "openrouter"
    elif os.environ.get("DEEPSEEK_API_KEY"):
        config.ai.api_key = os.environ["DEEPSEEK_API_KEY"]
        if not os.environ.get("CURATOR_AI_PROVIDER") and config.ai.provider == "rule_based":
            config.ai.provider = "deepseek"
    elif os.environ.get("OPENAI_API_KEY"):
        config.ai.api_key = os.environ["OPENAI_API_KEY"]
    elif os.environ.get("OPENCODE_API_KEY"):
        config.ai.api_key = os.environ["OPENCODE_API_KEY"]
    elif os.environ.get("ANTHROPIC_API_KEY"):
        config.ai.api_key = os.environ["ANTHROPIC_API_KEY"]

    if os.environ.get("CURATOR_WATCH_DIR"):
        config.watch_directory = Path(os.environ["CURATOR_WATCH_DIR"]).expanduser().resolve()

    if os.environ.get("CURATOR_DEST_ROOT"):
        config.destination_root = Path(os.environ["CURATOR_DEST_ROOT"]).expanduser().resolve()

    return config


def generate_default_config_yaml() -> str:
    """Generate default configuration as annotated YAML string."""
    default_dict = {
        "watch_directory": "~/Downloads",
        "destination_root": "~/Downloads",
        "database_path": "~/.download-curator/curator.db",
        "categories": {
            "Academic Papers": "Academic Papers",
            "Books": "Books",
            "Slides": "Presentations",
            "Invoices & Receipts": "Financial/Invoices",
            "Financial Statements": "Financial/Statements",
            "Datasets": "Datasets",
            "Installers": "Installers",
            "Images": "Images",
            "Archives": "Archives",
            "Code & Scripts": "Code",
            "Documents": "Documents",
            "Spreadsheets": "Spreadsheets",
            "Audio & Video": "Media",
            "Unclassified": "Unclassified",
        },
        "naming_rules": {
            "academic_papers": "{authors}_{year}_{short_title}.{ext}",
            "books": "{authors}_{year}_{title}.{ext}",
            "slides": "{topic_or_title}.{ext}",
            "invoices": "{merchant}_{date}_{description}.{ext}",
            "statements": "{institution}_{date}_Statement.{ext}",
            "installers": "{app_name}_{version}_{arch}.{ext}",
            "datasets": "{dataset_name}_{version}_{date}.{ext}",
        },
        "ignore": {
            "extensions": [
                ".crdownload",
                ".part",
                ".download",
                ".tmp",
                ".swp",
                ".lock",
                ".DS_Store",
            ],
            "patterns": [
                ".*",
                "~$*",
                "*.tmp",
                "*.crdownload",
                "*.part",
                "*.download",
            ],
            "directories": [
                ".*",
                "Organized",
                "Academic Papers",
                "Books",
                "Presentations",
                "Financial",
                "Datasets",
                "Installers",
                "Images",
                "Archives",
                "Code",
                "Documents",
                "Spreadsheets",
                "Media",
                "Unclassified",
            ],
        },
        "ai": {
            "provider": "rule_based",  # rule_based, gemini, openai, anthropic, ollama
            "api_key": None,
            "model": None,
            "confidence_threshold": 0.7,
        },
        "safety": {
            "allowed_source_directories": ["~/Downloads"],
            "allowed_destination_roots": ["~/Downloads", "~/Documents"],
            "collision_strategy": "rename_increment",
            "preserve_metadata": True,
            "atomic_moves": True,
            "max_filename_length": 200,
        },
        "server": {
            "host": "127.0.0.1",
            "port": 58291,
            "poll_interval_seconds": 2.0,
        },
    }
    return yaml.dump(default_dict, default_flow_style=False, sort_keys=False)
