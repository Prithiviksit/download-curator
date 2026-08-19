"""
macOS Notification System with batch consolidation and debounce.
Sends non-blocking system notifications without modifying files.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
from typing import List, Optional

logger = logging.getLogger("download_curator.notifier")


class MacNotifier:
    """Dispatches native macOS notifications with debounce and batching."""

    def __init__(self, debounce_seconds: float = 2.5, enabled: Optional[bool] = None):
        self.debounce_seconds = debounce_seconds
        if enabled is None:
            # Disable during test runs or if explicitly disabled
            is_test = (
                "PYTEST_CURRENT_TEST" in os.environ
                or "TESTING" in os.environ
                or os.environ.get("DISABLE_NOTIFICATIONS") == "1"
            )
            self.enabled = not is_test
        else:
            self.enabled = enabled

        self._pending_filenames: List[str] = []
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def notify_new_download(self, filename: str) -> None:
        """Queue a notification for a newly processed download."""
        if not self.enabled:
            return

        with self._lock:
            self._pending_filenames.append(filename)
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._flush_notifications)
            self._timer.daemon = True
            self._timer.start()

    def _flush_notifications(self) -> None:
        with self._lock:
            items = list(self._pending_filenames)
            self._pending_filenames.clear()
            self._timer = None

        if not items or not self.enabled:
            return

        if len(items) == 1:
            title = "Downloads Curator"
            subtitle = "New download ready to organize"
            message = items[0]
        else:
            title = "Downloads Curator"
            subtitle = f"{len(items)} downloads ready to organize"
            message = ", ".join(items[:3]) + (f" and {len(items) - 3} more" if len(items) > 3 else "")

        self._send_macos_notification(title, subtitle, message)

    def _send_macos_notification(self, title: str, subtitle: str, message: str) -> None:
        if not self.enabled:
            return

        # Sanitize for AppleScript string escaping
        safe_title = title.replace('"', '\\"')
        safe_subtitle = subtitle.replace('"', '\\"')
        safe_message = message.replace('"', '\\"')

        apple_script = (
            f'display notification "{safe_message}" '
            f'with title "{safe_title}" '
            f'subtitle "{safe_subtitle}" '
            f'sound name "Default"'
        )

        try:
            # Fire-and-forget subprocess.Popen so it NEVER blocks execution
            subprocess.Popen(
                ["osascript", "-e", apple_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                close_fds=True,
            )
        except Exception as e:
            logger.debug(f"Failed to dispatch macOS notification: {e}")


_DEFAULT_NOTIFIER: Optional[MacNotifier] = None


def get_default_notifier() -> MacNotifier:
    global _DEFAULT_NOTIFIER
    if _DEFAULT_NOTIFIER is None:
        _DEFAULT_NOTIFIER = MacNotifier()
    return _DEFAULT_NOTIFIER


def send_notification(filename: str) -> None:
    """Convenience function to notify about a newly created proposal."""
    get_default_notifier().notify_new_download(filename)
