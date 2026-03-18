"""
HAL9000 — Windows Platform Implementation
Uses PowerShell, native Win32 APIs, and standard Windows commands.
"""

import os
import subprocess
import tempfile

from core.platform.base import PlatformAPI


def _ps(script: str, timeout: int = 10) -> subprocess.CompletedProcess:
    """Run a PowerShell command and return the result."""
    return subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True, text=True, timeout=timeout,
    )


class WindowsPlatform(PlatformAPI):

    name = "Windows"

    # ── Volume ────────────────────────────────────────────

    def get_volume(self) -> str:
        # Use PowerShell + Audio COM object
        r = _ps(
            "(New-Object -ComObject WScript.Shell).SendKeys([char]0); "
            "$vol = [Math]::Round((Get-AudioDevice -PlaybackVolume)); "
            "Write-Output $vol"
        )
        # Fallback: use nircmd or simple approach
        if r.returncode != 0:
            r = _ps(
                "Add-Type -TypeDefinition '"
                "using System.Runtime.InteropServices; "
                "public class Vol { "
                "[DllImport(\"winmm.dll\")] "
                "public static extern int waveOutGetVolume(IntPtr hwo, out uint dwVolume); "
                "}'; "
                "$v = 0; [Vol]::waveOutGetVolume([IntPtr]::Zero, [ref]$v); "
                "$pct = [Math]::Round(($v -band 0xFFFF) / 0xFFFF * 100); "
                "Write-Output $pct"
            )
        vol = r.stdout.strip() or "unknown"
        return f"Volume: {vol}%"

    def set_volume(self, level: int) -> str:
        level = max(0, min(100, int(level)))
        # Use PowerShell + COM to set volume
        _ps(
            f"$obj = New-Object -ComObject WScript.Shell; "
            f"(New-Object -com 'Shell.Application').Windows() | Out-Null; "
            f"$wshShell = New-Object -ComObject WScript.Shell; "
            f"1..50 | ForEach-Object {{ $wshShell.SendKeys([char]174) }}; "  # vol down to 0
            f"1..{level // 2} | ForEach-Object {{ $wshShell.SendKeys([char]175) }}"  # vol up
        )
        # Better approach if available: use pycaw or nircmd
        try:
            subprocess.run(
                ["nircmd", "setsysvolume", str(int(level / 100 * 65535))],
                capture_output=True, timeout=5,
            )
        except FileNotFoundError:
            pass  # nircmd not installed, SendKeys fallback already ran
        return f"Volume set to {level}%"

    # ── Brightness ────────────────────────────────────────

    def get_brightness(self) -> str:
        r = _ps(
            "(Get-WmiObject -Namespace root\\WMI -Class WmiMonitorBrightness)"
            ".CurrentBrightness"
        )
        brightness = r.stdout.strip() or "unknown"
        return f"Brightness: {brightness}%"

    def set_brightness(self, level: float) -> str:
        pct = max(0, min(100, int(level * 100)))
        _ps(
            f"(Get-WmiObject -Namespace root\\WMI -Class WmiMonitorBrightnessMethods)"
            f".WmiSetBrightness(1, {pct})"
        )
        return f"Brightness set to {pct}%"

    # ── Notifications ─────────────────────────────────────

    def send_notification(self, title: str, message: str) -> str:
        # Use PowerShell toast notification
        safe_t = title.replace("'", "''")
        safe_m = message.replace("'", "''")
        _ps(
            f"[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
            f"ContentType = WindowsRuntime] > $null; "
            f"$template = [Windows.UI.Notifications.ToastNotificationManager]::"
            f"GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$textNodes = $template.GetElementsByTagName('text'); "
            f"$textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_t}')) > $null; "
            f"$textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_m}')) > $null; "
            f"$toast = [Windows.UI.Notifications.ToastNotification]::new($template); "
            f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('HAL9000')"
            f".Show($toast)",
            timeout=15,
        )
        return f"Notification sent: {title}"

    # ── Clipboard ─────────────────────────────────────────

    def get_clipboard(self) -> str:
        r = _ps("Get-Clipboard")
        content = r.stdout[:3000]
        return content or "(clipboard is empty)"

    def set_clipboard(self, text: str) -> str:
        safe = text.replace("'", "''")
        _ps(f"Set-Clipboard -Value '{safe}'")
        return f"Copied {len(text)} chars to clipboard"

    # ── Screenshot ────────────────────────────────────────

    def screenshot(self) -> str:
        path = self.temp_path("hal_screenshot.png")
        # Use PIL (Pillow) which is already a dependency
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(path)
            size = os.path.getsize(path)
            return f"Screenshot saved to {path} ({size} bytes)"
        except Exception as e:
            return f"Failed to capture screenshot: {e}"

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
            r = _ps(
                "(Get-WmiObject Win32_Battery | Select-Object EstimatedChargeRemaining, "
                "BatteryStatus | Format-List | Out-String).Trim()"
            )
            return r.stdout.strip() or "Could not read battery status"

    # ── WiFi ──────────────────────────────────────────────

    def get_wifi(self) -> str:
        r = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True,
        )
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID") and "BSSID" not in line:
                return line.split(":", 1)[1].strip()
        return "Not connected to WiFi"

    # ── Applications ──────────────────────────────────────

    def open_application(self, name: str) -> str:
        try:
            subprocess.run(["start", "", name], shell=True, check=True, capture_output=True)
            return f"Opened {name}"
        except subprocess.CalledProcessError:
            # Try with full path search
            r = _ps(f"Start-Process '{name}' -ErrorAction SilentlyContinue")
            if r.returncode == 0:
                return f"Opened {name}"
            return f"Could not open '{name}'"

    def quit_application(self, name: str) -> str:
        # Use taskkill for Windows processes
        safe = name.replace("'", "''")
        r = _ps(f"Stop-Process -Name '{safe}' -Force -ErrorAction SilentlyContinue")
        if r.returncode == 0:
            return f"Quit {name}"
        # Try by window title
        r2 = subprocess.run(
            ["taskkill", "/IM", f"{name}.exe", "/F"],
            capture_output=True, text=True,
        )
        return f"Quit {name}" if r2.returncode == 0 else f"Could not quit '{name}'"

    def list_running_apps(self) -> str:
        r = _ps(
            "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | "
            "Select-Object -ExpandProperty ProcessName -Unique | Sort-Object"
        )
        return r.stdout.strip() or "Could not list applications"

    def list_installed_apps(self, query: str = "") -> list[dict]:
        # Search Start Menu shortcuts and Program Files
        apps = []
        seen = set()

        # Start Menu
        start_dirs = [
            os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs"),
            os.path.expandvars(r"%AppData%\Microsoft\Windows\Start Menu\Programs"),
        ]

        for start_dir in start_dirs:
            if not os.path.isdir(start_dir):
                continue
            for root, dirs, files in os.walk(start_dir):
                for f in files:
                    if f.endswith(".lnk"):
                        name = f[:-4]
                        if name in seen:
                            continue
                        seen.add(name)
                        apps.append({
                            "name": name,
                            "path": os.path.join(root, f),
                            "location": "Start Menu",
                        })

        # Program Files
        for pf_dir in [
            os.path.expandvars(r"%ProgramFiles%"),
            os.path.expandvars(r"%ProgramFiles(x86)%"),
            os.path.expandvars(r"%LocalAppData%\Programs"),
        ]:
            if not os.path.isdir(pf_dir):
                continue
            try:
                for entry in os.listdir(pf_dir):
                    full = os.path.join(pf_dir, entry)
                    if os.path.isdir(full) and entry not in seen:
                        seen.add(entry)
                        apps.append({"name": entry, "path": full, "location": pf_dir})
            except PermissionError:
                continue

        apps.sort(key=lambda a: a["name"].lower())
        if query:
            q = query.lower()
            apps = [a for a in apps if q in a["name"].lower()]
        return apps

    def app_action(self, app_name: str, command: str) -> str:
        # Windows automation via PowerShell COM
        blocked = ["remove-item", "format-volume", "stop-computer", "restart-computer"]
        cmd_lower = command.lower()
        for b in blocked:
            if b in cmd_lower:
                return f"[error] Command contains blocked phrase: '{b}'"

        try:
            r = _ps(command, timeout=15)
            if r.returncode != 0:
                err = r.stderr.strip()
                return f"[error] {err}" if err else "[error] Command failed"
            return r.stdout.strip() or f"Done — sent command to {app_name}"
        except subprocess.TimeoutExpired:
            return "[error] Command timed out"
        except Exception as e:
            return f"[error] {e}"

    # ── URL ───────────────────────────────────────────────

    def open_url(self, url: str) -> str:
        subprocess.run(["start", "", url], shell=True, check=False)
        return f"Opened {url}"

    # ── Terminal ──────────────────────────────────────────

    def open_terminal(self, command: str, cwd: str = "") -> str:
        cwd = os.path.expanduser(cwd or "~")
        # Try Windows Terminal first, fall back to cmd
        try:
            subprocess.Popen(
                ["wt", "-d", cwd, "cmd", "/k", command],
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
            return f"Opened Windows Terminal at {cwd}"
        except FileNotFoundError:
            subprocess.Popen(
                f'start cmd /k "cd /d {cwd} && {command}"',
                shell=True,
            )
            return f"Opened Command Prompt at {cwd}"
