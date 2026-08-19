"""
Filesystem watcher for download directories.
Detects newly completed downloads, filters out incomplete/temporary files,
and guarantees files are settled before triggering analysis.
"""

from __future__ import annotations

import fnmatch
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional, Set
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from download_curator.config import CuratorConfig

logger = logging.getLogger("download_curator.watcher")


def is_ignored_file(file_path: Path, config: CuratorConfig) -> bool:
    """Check if file matches any ignore rules (temp extensions, hidden files, subdirectories)."""
    name = file_path.name

    # Ignore hidden files (starting with dot)
    if name.startswith("."):
        return True

    # Ignore temporary download extensions
    ext = file_path.suffix.lower()
    if ext in config.ignore.extensions:
        return True

    # Ignore temporary prefix patterns (e.g. ~$ for MS Office temporary files)
    if name.startswith("~$"):
        return True

    # Ignore glob patterns
    for pattern in config.ignore.patterns:
        if fnmatch.fnmatch(name, pattern):
            return True

    # Ignore if inside an ignored category directory
    try:
        rel = file_path.relative_to(config.watch_directory)
        first_part = rel.parts[0] if len(rel.parts) > 1 else None
        if first_part and first_part in config.ignore.directories:
            return True
    except ValueError:
        pass

    return False


def wait_for_file_settled(file_path: Path, max_wait: float = 15.0, check_interval: float = 0.5) -> bool:
    """
    Wait until file size stops changing and file is readable.
    Ensures in-progress downloads are not analyzed mid-write.
    """
    start = time.time()
    last_size = -1
    consecutive_stable_checks = 0

    while time.time() - start < max_wait:
        if not file_path.exists():
            return False

        try:
            current_size = file_path.stat().st_size
            # Try opening in read mode to check if exclusively locked
            with open(file_path, "rb") as f:
                f.read(10)

            if current_size == last_size and current_size > 0:
                consecutive_stable_checks += 1
                if consecutive_stable_checks >= 2:
                    return True
            else:
                consecutive_stable_checks = 0

            last_size = current_size
        except (OSError, PermissionError):
            consecutive_stable_checks = 0

        time.sleep(check_interval)

    return file_path.exists() and last_size > 0


class DownloadsEventHandler(FileSystemEventHandler):
    """Event handler that filters and queues newly finished downloads."""

    def __init__(self, config: CuratorConfig, on_file_completed: Callable[[Path], None]):
        super().__init__()
        self.config = config
        self.on_file_completed = on_file_completed
        self._recently_processed: Set[str] = set()

    def _handle_path(self, path_str: str) -> None:
        path = Path(path_str).resolve()
        if not path.is_file():
            return

        if is_ignored_file(path, self.config):
            return

        str_path = str(path)
        if str_path in self._recently_processed:
            return

        # Check if file has finished writing
        if wait_for_file_settled(path):
            self._recently_processed.add(str_path)
            # Cap cache size
            if len(self._recently_processed) > 500:
                self._recently_processed.clear()
            self.on_file_completed(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle_path(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        # e.g., file renamed from .crdownload to final name
        if not event.is_directory and event.dest_path:
            self._handle_path(event.dest_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._handle_path(event.src_path)


class DownloadsWatcher:
    """Manages the background filesystem observer for downloads."""

    def __init__(self, config: CuratorConfig, on_file_completed: Callable[[Path], None]):
        self.config = config
        self.on_file_completed = on_file_completed
        self.observer: Optional[Observer] = None

    def start(self) -> None:
        watch_dir = self.config.watch_directory
        if not watch_dir.exists():
            watch_dir.mkdir(parents=True, exist_ok=True)

        event_handler = DownloadsEventHandler(self.config, self.on_file_completed)
        self.observer = Observer()
        self.observer.schedule(event_handler, str(watch_dir), recursive=False)
        self.observer.start()
        logger.info(f"Started monitoring {watch_dir} for new downloads.")

    def stop(self) -> None:
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped download watcher.")
