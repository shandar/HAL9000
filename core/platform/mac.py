"""
HAL9000 — macOS Platform Implementation
Uses AppleScript (osascript) and native macOS commands.
"""

import os
import subprocess

from core.platform.base import PlatformAPI


def _escape_applescript(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


class MacPlatform(PlatformAPI):

    name = "macOS"

    # ── Volume ────────────────────────────────────────────

    def get_volume(self) -> str:
        result = subprocess.run(
            ["osascript", "-e", "output volume of (get volume settings)"],
            capture_output=True, text=True,
        )
        return f"Volume: {result.stdout.strip()}%"

    def set_volume(self, level: int) -> str:
        level = max(0, min(100, int(level)))
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {level}"],
            capture_output=True,
        )
        return f"Volume set to {level}%"

    # ── Brightness ────────────────────────────────────────

    def get_brightness(self) -> str:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to tell appearance preferences to get dark mode'],
            capture_output=True, text=True,
        )
        dark = result.stdout.strip() == "true"
        br_result = subprocess.run(
            ["bash", "-c",
             "ioreg -c AppleBacklightDisplay | grep brightness | head -1 | awk -F'= ' '{print $NF}'"],
            capture_output=True, text=True,
        )
        brightness = br_result.stdout.strip() or "unknown"
        return f"Brightness: {brightness}, Dark mode: {'on' if dark else 'off'}"

    def set_brightness(self, level: float) -> str:
        level = max(0.0, min(1.0, float(level)))
        subprocess.run(
            ["osascript", "-e",
             f'tell application "System Events" to set value of slider 1 '
             f'of group 1 of window 1 of process "Control Center" to {level}'],
            capture_output=True,
        )
        return f"Brightness set to {int(level * 100)}%"

    # ── Notifications ─────────────────────────────────────

    def send_notification(self, title: str, message: str) -> str:
        safe_t = _escape_applescript(title)
        safe_m = _escape_applescript(message)
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{safe_m}" with title "{safe_t}"'],
            capture_output=True,
        )
        return f"Notification sent: {title}"

    # ── Clipboard ─────────────────────────────────────────

    def get_clipboard(self) -> str:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True)
        content = result.stdout[:3000]
        return content or "(clipboard is empty)"

    def set_clipboard(self, text: str) -> str:
        process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        process.communicate(text.encode("utf-8"))
        return f"Copied {len(text)} chars to clipboard"

    # ── Screenshot ────────────────────────────────────────

    def screenshot(self) -> str:
        path = self.temp_path("hal_screenshot.png")
        result = subprocess.run(["screencapture", "-x", path], capture_output=True)
        if result.returncode == 0 and os.path.exists(path):
            size = os.path.getsize(path)
            return f"Screenshot saved to {path} ({size} bytes)"
        return "Failed to capture screenshot"

    # ── Battery ───────────────────────────────────────────

    def get_battery(self) -> str:
        result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
        return result.stdout.strip() or "Could not read battery status"

    # ── WiFi ──────────────────────────────────────────────

    def get_wifi(self) -> str:
        result = subprocess.run(
            ["/usr/sbin/networksetup", "-getairportnetwork", "en0"],
            capture_output=True, text=True,
        )
        output = result.stdout.strip()
        if "Current Wi-Fi Network:" in output:
            return output.split(":", 1)[1].strip()
        return output or "Not connected to WiFi"

    # ── Applications ──────────────────────────────────────

    def open_application(self, name: str) -> str:
        try:
            subprocess.run(["open", "-a", name], check=True, capture_output=True)
            return f"Opened {name}"
        except subprocess.CalledProcessError:
            return f"Could not open '{name}' — app not found"

    def quit_application(self, name: str) -> str:
        safe = _escape_applescript(name)
        result = subprocess.run(
            ["osascript", "-e", f'tell application "{safe}" to quit'],
            capture_output=True, text=True,
        )
        return f"Quit {name}" if result.returncode == 0 else f"Could not quit '{name}'"

    def list_running_apps(self) -> str:
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of every process whose background only is false'],
            capture_output=True, text=True,
        )
        return result.stdout.strip() or "Could not list applications"

    def list_installed_apps(self, query: str = "") -> list[dict]:
        app_dirs = [
            "/Applications",
            "/System/Applications",
            "/System/Applications/Utilities",
            os.path.expanduser("~/Applications"),
            "/Applications/Utilities",
        ]
        apps = []
        seen = set()
        for d in app_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for entry in os.listdir(d):
                    if not entry.endswith(".app"):
                        continue
                    name = entry[:-4]
                    if name in seen:
                        continue
                    seen.add(name)
                    apps.append({"name": name, "path": os.path.join(d, entry), "location": d})
            except PermissionError:
                continue
        apps.sort(key=lambda a: a["name"].lower())
        if query:
            q = query.lower()
            apps = [a for a in apps if q in a["name"].lower()]
        return apps

    def app_action(self, app_name: str, command: str) -> str:
        safe_app = _escape_applescript(app_name)
        blocked = ["do shell script", "run script", "system events", "keystroke"]
        cmd_lower = command.lower()
        for b in blocked:
            if b in cmd_lower:
                return f"[error] Command contains blocked phrase: '{b}'"

        script = f'tell application "{safe_app}"\n{command}\nend tell'
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                err = result.stderr.strip()
                return f"[error] {err}" if err else "[error] Command failed"
            return result.stdout.strip() or f"Done — sent command to {app_name}"
        except subprocess.TimeoutExpired:
            return "[error] Command timed out after 15 seconds"
        except Exception as e:
            return f"[error] {e}"

    # ── URL ───────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        subprocess.run(["open", url], check=False)
        return f"Opened {url}"

    # ── Terminal ──────────────────────────────────────────

    def open_terminal(self, command: str, cwd: str = "") -> str:
        cwd = os.path.expanduser(cwd or "~")
        safe_cwd = _escape_applescript(cwd)
        safe_cmd = _escape_applescript(command)
        script = f'''
        tell application "Terminal"
            activate
            do script "cd \\"{safe_cwd}\\" && {safe_cmd}"
        end tell
        '''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
            return f"Opened Terminal at {cwd}"
        except Exception as e:
            return f"Failed to open Terminal: {e}"
