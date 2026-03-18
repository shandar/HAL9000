"""
HAL9000 — Linux Platform Implementation
Uses pactl, xdg-open, xclip, notify-send, and standard Linux commands.
"""

import os
import subprocess

from core.platform.base import PlatformAPI


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


class LinuxPlatform(PlatformAPI):

    name = "Linux"

    # ── Volume ────────────────────────────────────────────

    def get_volume(self) -> str:
        # PulseAudio / PipeWire
        r = _run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"])
        if r.returncode == 0:
            # Parse "Volume: front-left: 42000 /  64% / -11.78 dB ..."
            for part in r.stdout.split("/"):
                part = part.strip()
                if part.endswith("%"):
                    return f"Volume: {part}"
        # Fallback: amixer
        r2 = _run(["amixer", "get", "Master"])
        if r2.returncode == 0:
            for line in r2.stdout.splitlines():
                if "%" in line:
                    start = line.find("[") + 1
                    end = line.find("%")
                    if start > 0 and end > start:
                        return f"Volume: {line[start:end]}%"
        return "Volume: unknown"

    def set_volume(self, level: int) -> str:
        level = max(0, min(100, int(level)))
        r = _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"])
        if r.returncode != 0:
            _run(["amixer", "set", "Master", f"{level}%"])
        return f"Volume set to {level}%"

    # ── Brightness ────────────────────────────────────────

    def get_brightness(self) -> str:
        r = _run(["brightnessctl", "get"])
        r_max = _run(["brightnessctl", "max"])
        if r.returncode == 0 and r_max.returncode == 0:
            try:
                current = int(r.stdout.strip())
                maximum = int(r_max.stdout.strip())
                pct = int(current / maximum * 100)
                return f"Brightness: {pct}%"
            except ValueError:
                pass
        return "Brightness: unknown (install brightnessctl)"

    def set_brightness(self, level: float) -> str:
        pct = max(0, min(100, int(level * 100)))
        r = _run(["brightnessctl", "set", f"{pct}%"])
        if r.returncode != 0:
            return "Failed to set brightness (install brightnessctl)"
        return f"Brightness set to {pct}%"

    # ── Notifications ─────────────────────────────────────

    def send_notification(self, title: str, message: str) -> str:
        r = _run(["notify-send", title, message])
        if r.returncode == 0:
            return f"Notification sent: {title}"
        return "Failed to send notification (install libnotify)"

    # ── Clipboard ─────────────────────────────────────────

    def get_clipboard(self) -> str:
        # Try xclip, then xsel, then wl-paste (Wayland)
        for cmd in [
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
            ["wl-paste"],
        ]:
            try:
                r = _run(cmd)
                if r.returncode == 0:
                    return r.stdout[:3000] or "(clipboard is empty)"
            except FileNotFoundError:
                continue
        return "(clipboard tool not found — install xclip, xsel, or wl-clipboard)"

    def set_clipboard(self, text: str) -> str:
        # Try xclip, then xsel, then wl-copy
        for cmd in [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["wl-copy"],
        ]:
            try:
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                proc.communicate(text.encode("utf-8"))
                if proc.returncode == 0:
                    return f"Copied {len(text)} chars to clipboard"
            except FileNotFoundError:
                continue
        return "Failed to set clipboard (install xclip, xsel, or wl-clipboard)"

    # ── Screenshot ────────────────────────────────────────

    def screenshot(self) -> str:
        path = self.temp_path("hal_screenshot.png")
        # Try multiple screenshot tools
        for cmd in [
            ["gnome-screenshot", "-f", path],
            ["scrot", path],
            ["grim", path],  # Wayland
            ["import", "-window", "root", path],  # ImageMagick
        ]:
            try:
                r = _run(cmd)
                if r.returncode == 0 and os.path.exists(path):
                    size = os.path.getsize(path)
                    return f"Screenshot saved to {path} ({size} bytes)"
            except FileNotFoundError:
                continue
        # Fallback: PIL
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(path)
            size = os.path.getsize(path)
            return f"Screenshot saved to {path} ({size} bytes)"
        except Exception:
            pass
        return "Failed to capture screenshot (install gnome-screenshot, scrot, or grim)"

    # ── Battery ───────────────────────────────────────────

    def get_battery(self) -> str:
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt is None:
                return "No battery detected (desktop PC)"
            status = "charging" if batt.power_plugged else "discharging"
            return f"Battery: {batt.percent}%, {status}"
        except ImportError:
            # Read from sysfs
            try:
                cap = open("/sys/class/power_supply/BAT0/capacity").read().strip()
                stat = open("/sys/class/power_supply/BAT0/status").read().strip()
                return f"Battery: {cap}%, {stat.lower()}"
            except FileNotFoundError:
                return "No battery detected"

    # ── WiFi ──────────────────────────────────────────────

    def get_wifi(self) -> str:
        r = _run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"])
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if line.startswith("yes:"):
                    return line.split(":", 1)[1]
        # Fallback
        r2 = _run(["iwgetid", "-r"])
        if r2.returncode == 0 and r2.stdout.strip():
            return r2.stdout.strip()
        return "Not connected to WiFi"

    # ── Applications ──────────────────────────────────────

    def open_application(self, name: str) -> str:
        # Try direct command, then desktop file
        try:
            subprocess.Popen([name.lower()], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"Opened {name}"
        except FileNotFoundError:
            pass
        # Try gtk-launch
        r = _run(["gtk-launch", f"{name.lower()}.desktop"])
        if r.returncode == 0:
            return f"Opened {name}"
        # Try xdg-open with desktop file
        r = _run(["xdg-open", f"/usr/share/applications/{name.lower()}.desktop"])
        if r.returncode == 0:
            return f"Opened {name}"
        return f"Could not open '{name}'"

    def quit_application(self, name: str) -> str:
        r = _run(["pkill", "-f", name])
        return f"Quit {name}" if r.returncode == 0 else f"Could not quit '{name}'"

    def list_running_apps(self) -> str:
        r = _run(["bash", "-c",
                   "wmctrl -l 2>/dev/null | awk '{$1=$2=$3=\"\"; print $0}' | sort -u || "
                   "ps -eo comm --no-headers | sort -u | head -40"])
        return r.stdout.strip() or "Could not list applications"

    def list_installed_apps(self, query: str = "") -> list[dict]:
        apps = []
        seen = set()

        # Scan .desktop files
        desktop_dirs = [
            "/usr/share/applications",
            "/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
            "/snap/current",
        ]

        for d in desktop_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for f in os.listdir(d):
                    if not f.endswith(".desktop"):
                        continue
                    name = f[:-8]  # strip .desktop
                    # Try to read Name= from desktop file
                    display_name = name
                    try:
                        with open(os.path.join(d, f), "r") as fh:
                            for line in fh:
                                if line.startswith("Name="):
                                    display_name = line.split("=", 1)[1].strip()
                                    break
                    except Exception:
                        pass

                    if display_name in seen:
                        continue
                    seen.add(display_name)
                    apps.append({
                        "name": display_name,
                        "path": os.path.join(d, f),
                        "location": d,
                    })
            except PermissionError:
                continue

        apps.sort(key=lambda a: a["name"].lower())
        if query:
            q = query.lower()
            apps = [a for a in apps if q in a["name"].lower()]
        return apps

    # ── URL ───────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened {url}"

    # ── Terminal ──────────────────────────────────────────

    def open_terminal(self, command: str, cwd: str = "") -> str:
        cwd = os.path.expanduser(cwd or "~")
        # Try common terminal emulators
        for term in ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"]:
            try:
                if term == "gnome-terminal":
                    subprocess.Popen(
                        [term, "--working-directory", cwd, "--", "bash", "-c", f"{command}; exec bash"],
                    )
                elif term == "konsole":
                    subprocess.Popen([term, "--workdir", cwd, "-e", "bash", "-c", f"{command}; exec bash"])
                else:
                    subprocess.Popen([term, "-e", f"bash -c 'cd {cwd} && {command}; exec bash'"])
                return f"Opened {term} at {cwd}"
            except FileNotFoundError:
                continue
        return "No terminal emulator found (install gnome-terminal, konsole, or xterm)"
