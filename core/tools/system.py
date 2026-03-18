"""Cross-platform system tools — volume, brightness, notifications, clipboard, screenshot."""

import datetime

from core.platform import platform
from core.tools import tool, _human_size


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
    description="Get battery level and charging status.",
    safety="safe",
    params={},
)
def get_battery() -> str:
    return platform.get_battery()


@tool(
    name="get_wifi",
    description="Get the current WiFi network name.",
    safety="safe",
    params={},
)
def get_wifi() -> str:
    return platform.get_wifi()


@tool(
    name="get_volume",
    description="Get the current system volume level (0-100).",
    safety="safe",
    params={},
)
def get_volume() -> str:
    return platform.get_volume()


@tool(
    name="set_volume",
    description="Set the system volume level.",
    safety="safe",
    params={
        "level": {"type": "integer", "description": "Volume level 0-100"},
    },
)
def set_volume(level: int) -> str:
    return platform.set_volume(int(level))


@tool(
    name="get_brightness",
    description="Get the current display brightness.",
    safety="safe",
    params={},
)
def get_brightness() -> str:
    return platform.get_brightness()


@tool(
    name="set_brightness",
    description="Set display brightness level.",
    safety="safe",
    params={
        "level": {"type": "number", "description": "Brightness 0.0-1.0"},
    },
)
def set_brightness(level: float) -> str:
    return platform.set_brightness(float(level))


@tool(
    name="send_notification",
    description="Show a desktop notification with a title and message.",
    safety="safe",
    params={
        "title": {"type": "string", "description": "Notification title"},
        "message": {"type": "string", "description": "Notification body text"},
    },
)
def send_notification(title: str, message: str) -> str:
    return platform.send_notification(title, message)


@tool(
    name="get_clipboard",
    description="Read the current contents of the clipboard.",
    safety="safe",
    params={},
)
def get_clipboard() -> str:
    return platform.get_clipboard()


@tool(
    name="set_clipboard",
    description="Copy text to the clipboard.",
    safety="confirm",
    params={
        "text": {"type": "string", "description": "Text to copy to clipboard"},
    },
)
def set_clipboard(text: str) -> str:
    return platform.set_clipboard(text)


@tool(
    name="screenshot",
    description="Take a screenshot of the screen. Returns the file path.",
    safety="safe",
    params={},
)
def screenshot() -> str:
    return platform.screenshot()
