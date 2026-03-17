"""macOS system tools — volume, brightness, notifications, clipboard, screenshot."""

import datetime
import os
import subprocess

from core.tools import tool, _escape_applescript, _human_size


@tool(
    name="get_time",
    description="Get the current date and time.",
    safety="safe",
    params={},
)
def get_time() -> str:
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y at %I:%M %p")


@tool(
    name="get_battery",
    description="Get Mac battery level and charging status.",
    safety="safe",
    params={},
)
def get_battery() -> str:
    result = subprocess.run(
        ["pmset", "-g", "batt"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "Could not read battery status"


@tool(
    name="get_wifi",
    description="Get the current WiFi network name.",
    safety="safe",
    params={},
)
def get_wifi() -> str:
    result = subprocess.run(
        ["/usr/sbin/networksetup", "-getairportnetwork", "en0"],
        capture_output=True, text=True,
    )
    output = result.stdout.strip()
    if "Current Wi-Fi Network:" in output:
        return output.split(":", 1)[1].strip()
    return output or "Not connected to WiFi"


@tool(
    name="get_volume",
    description="Get the current system volume level (0-100).",
    safety="safe",
    params={},
)
def get_volume() -> str:
    result = subprocess.run(
        ["osascript", "-e", "output volume of (get volume settings)"],
        capture_output=True, text=True,
    )
    return f"Volume: {result.stdout.strip()}%"


@tool(
    name="set_volume",
    description="Set the system volume level.",
    safety="safe",
    params={
        "level": {"type": "integer", "description": "Volume level 0-100"},
    },
)
def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    subprocess.run(
        ["osascript", "-e", f"set volume output volume {level}"],
        capture_output=True,
    )
    return f"Volume set to {level}%"


@tool(
    name="get_brightness",
    description="Get the current display brightness (0-100).",
    safety="safe",
    params={},
)
def get_brightness() -> str:
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


@tool(
    name="set_brightness",
    description="Set display brightness level.",
    safety="safe",
    params={
        "level": {"type": "number", "description": "Brightness 0.0-1.0"},
    },
)
def set_brightness(level: float) -> str:
    level = max(0.0, min(1.0, float(level)))
    subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to set value of slider 1 of group 1 of window 1 of process "Control Center" to {level}'],
        capture_output=True,
    )
    return f"Brightness set to {int(level * 100)}%"


@tool(
    name="send_notification",
    description="Show a macOS notification with a title and message.",
    safety="safe",
    params={
        "title": {"type": "string", "description": "Notification title"},
        "message": {"type": "string", "description": "Notification body text"},
    },
)
def send_notification(title: str, message: str) -> str:
    safe_title = _escape_applescript(title)
    safe_message = _escape_applescript(message)
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{safe_message}" with title "{safe_title}"'],
        capture_output=True,
    )
    return f"Notification sent: {title}"


@tool(
    name="get_clipboard",
    description="Read the current contents of the macOS clipboard.",
    safety="safe",
    params={},
)
def get_clipboard() -> str:
    result = subprocess.run(["pbpaste"], capture_output=True, text=True)
    content = result.stdout[:3000]
    return content or "(clipboard is empty)"


@tool(
    name="set_clipboard",
    description="Copy text to the macOS clipboard.",
    safety="confirm",
    params={
        "text": {"type": "string", "description": "Text to copy to clipboard"},
    },
)
def set_clipboard(text: str) -> str:
    process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    process.communicate(text.encode("utf-8"))
    return f"Copied {len(text)} chars to clipboard"


@tool(
    name="screenshot",
    description="Take a screenshot of the Mac screen. Returns a description of what was captured.",
    safety="safe",
    params={},
)
def screenshot() -> str:
    path = "/tmp/hal_screenshot.png"
    result = subprocess.run(
        ["screencapture", "-x", path],
        capture_output=True,
    )
    if result.returncode == 0 and os.path.exists(path):
        size = _human_size(os.path.getsize(path))
        return f"Screenshot saved to {path} ({size})"
    return "Failed to capture screenshot"
