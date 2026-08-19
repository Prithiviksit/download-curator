"""
macOS LaunchAgent plist generator and manager.
Generates and controls the background download-curator daemon.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional


LABEL = "com.user.download-curator"
LAUNCH_AGENTS_DIR = Path("~/Library/LaunchAgents").expanduser().resolve()
PLIST_PATH = LAUNCH_AGENTS_DIR / f"{LABEL}.plist"
LOG_DIR = Path("~/.download-curator/logs").expanduser().resolve()


def get_default_executable() -> str:
    """Find the path to the download-curator executable or Python binary."""
    # Check if download-curator is in current venv or PATH
    which_curator = shutil.which("download-curator")
    if which_curator:
        return which_curator

    # Otherwise use current sys.executable
    venv_bin = Path(sys.executable).parent / "download-curator"
    if venv_bin.exists():
        return str(venv_bin)

    return sys.executable


def generate_plist_content(executable_path: Optional[str] = None) -> str:
    """Generate macOS launchd XML plist content."""
    exe = executable_path or get_default_executable()
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    stdout_log = str(LOG_DIR / "daemon.stdout.log")
    stderr_log = str(LOG_DIR / "daemon.stderr.log")

    if exe.endswith("python") or exe.endswith("python3"):
        args = f"""        <string>{exe}</string>
        <string>-m</string>
        <string>download_curator.cli</string>
        <string>serve</string>"""
    else:
        args = f"""        <string>{exe}</string>
        <string>serve</string>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{stdout_log}</string>
    <key>StandardErrorPath</key>
    <string>{stderr_log}</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
"""


class LaunchAgentManager:
    """Controls the lifecycle of the macOS LaunchAgent."""

    @staticmethod
    def get_status() -> Dict[str, str]:
        installed = PLIST_PATH.exists()
        running = False

        if installed:
            try:
                res = subprocess.run(
                    ["launchctl", "list", LABEL],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                running = res.returncode == 0
            except Exception:
                pass

        return {
            "label": LABEL,
            "plist_path": str(PLIST_PATH),
            "installed": "Yes" if installed else "No",
            "running": "Running" if running else "Stopped",
            "log_dir": str(LOG_DIR),
        }

    @staticmethod
    def install(executable_path: Optional[str] = None) -> Path:
        LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

        plist_content = generate_plist_content(executable_path)
        with open(PLIST_PATH, "w", encoding="utf-8") as f:
            f.write(plist_content)

        # Load into launchd
        subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=False)
        return PLIST_PATH

    @staticmethod
    def uninstall() -> None:
        if PLIST_PATH.exists():
            subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=False)
            try:
                PLIST_PATH.unlink()
            except Exception:
                pass

    @staticmethod
    def start() -> None:
        if PLIST_PATH.exists():
            subprocess.run(["launchctl", "start", LABEL], check=False)

    @staticmethod
    def stop() -> None:
        if PLIST_PATH.exists():
            subprocess.run(["launchctl", "stop", LABEL], check=False)
