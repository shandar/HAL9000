"""
HAL9000 — Platform API (Abstract Base)
Defines the cross-platform interface for OS-level operations.
Each platform (mac, windows, linux) implements this interface.
"""

import tempfile
from typing import Optional


class PlatformAPI:
    """Abstract interface for OS-level operations."""

    name: str = "unknown"

    # ── Volume ────────────────────────────────────────────

    def get_volume(self) -> str:
        raise NotImplementedError

    def set_volume(self, level: int) -> str:
        raise NotImplementedError

    # ── Brightness ────────────────────────────────────────

    def get_brightness(self) -> str:
        raise NotImplementedError

    def set_brightness(self, level: float) -> str:
        raise NotImplementedError

    # ── Notifications ─────────────────────────────────────

    def send_notification(self, title: str, message: str) -> str:
        raise NotImplementedError

    # ── Clipboard ─────────────────────────────────────────

    def get_clipboard(self) -> str:
        raise NotImplementedError

    def set_clipboard(self, text: str) -> str:
        raise NotImplementedError

    # ── Screenshot ────────────────────────────────────────

    def screenshot(self) -> str:
        """Take a screenshot and return the file path."""
        raise NotImplementedError

    # ── Battery ───────────────────────────────────────────

    def get_battery(self) -> str:
        raise NotImplementedError

    # ── WiFi ──────────────────────────────────────────────

    def get_wifi(self) -> str:
        raise NotImplementedError

    # ── Applications ──────────────────────────────────────

    def open_application(self, name: str) -> str:
        raise NotImplementedError

    def quit_application(self, name: str) -> str:
        raise NotImplementedError

    def list_running_apps(self) -> str:
        raise NotImplementedError

    def list_installed_apps(self, query: str = "") -> list[dict]:
        """Return list of {name, path, location} dicts."""
        raise NotImplementedError

    def app_action(self, app_name: str, command: str) -> str:
        """Send an automation command to a running application."""
        return f"[error] App automation not supported on {self.name}"

    # ── URL ───────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        raise NotImplementedError

    # ── Terminal (for Claude Code) ────────────────────────

    def open_terminal(self, command: str, cwd: str = "") -> str:
        """Open a new terminal window and run a command."""
        raise NotImplementedError

    # ── Temp path ─────────────────────────────────────────

    def temp_path(self, filename: str) -> str:
        """Return a cross-platform temp file path."""
        return f"{tempfile.gettempdir()}/{filename}"
