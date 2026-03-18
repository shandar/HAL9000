"""Application & URL tools — cross-platform."""

import os

from core.platform import platform
from core.tools import tool


@tool(
    name="open_application",
    description="Open a desktop application by name (e.g. 'Safari', 'Chrome', 'Terminal', 'Claude').",
    safety="safe",
    params={
        "name": {"type": "string", "description": "Application name"},
    },
)
def open_application(name: str) -> str:
    return platform.open_application(name)


@tool(
    name="open_url",
    description="Open a URL in the default web browser.",
    safety="safe",
    params={
        "url": {"type": "string", "description": "The URL to open"},
    },
)
def open_url(url: str) -> str:
    return platform.open_url(url)


@tool(
    name="list_running_apps",
    description="List all currently running applications.",
    safety="safe",
    params={},
)
def list_running_apps() -> str:
    return platform.list_running_apps()


@tool(
    name="list_installed_apps",
    description=(
        "List installed applications. Optionally filter by a search query. "
        "Use this when the user asks 'what apps do I have', 'show my apps', "
        "'find an app', or when you need to discover the correct app name before "
        "opening it. Returns app names and their install locations. "
        "Always prefer this over guessing app names."
    ),
    safety="safe",
    params={
        "query": {
            "type": "string",
            "description": (
                "Optional search filter — only show apps whose name contains "
                "this text (case-insensitive). Leave empty to list all apps."
            ),
            "required": False,
        },
    },
)
def list_installed_apps(query: str = "") -> str:
    apps = platform.list_installed_apps(query)

    if not apps:
        if query:
            return f"No installed apps matching '{query}'. Try a broader search."
        return "Could not find any installed applications."

    lines = []
    if query:
        lines.append(f"Apps matching '{query}' ({len(apps)} found):\n")
    else:
        lines.append(f"Installed applications ({len(apps)} total):\n")

    for i, app in enumerate(apps, 1):
        location = app["location"]
        # Shorten common prefixes
        for prefix, short in [
            ("/System/Applications", "System"),
            ("/Applications", "Apps"),
            (os.path.expanduser("~"), "~"),
        ]:
            location = location.replace(prefix, short)
        lines.append(f"  {i:3d}. {app['name']}  [{location}]")

    return "\n".join(lines)


@tool(
    name="app_action",
    description=(
        "Send an automation command to a running application. "
        "On macOS this uses AppleScript; on Windows this uses PowerShell COM. "
        "Use this to control apps AFTER they are opened — create documents, "
        "insert text, save, close, navigate tabs, etc."
    ),
    safety="confirm",
    params={
        "app_name": {
            "type": "string",
            "description": "The application to control",
        },
        "command": {
            "type": "string",
            "description": "Automation command to send to the application",
        },
    },
)
def app_action(app_name: str, command: str) -> str:
    return platform.app_action(app_name, command)


@tool(
    name="quit_application",
    description="Quit a running application by name.",
    safety="confirm",
    params={
        "name": {"type": "string", "description": "Application name to quit"},
    },
)
def quit_application(name: str) -> str:
    return platform.quit_application(name)
