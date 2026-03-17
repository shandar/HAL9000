"""Application & URL tools."""

import os
import subprocess

from core.tools import tool, _escape_applescript


def _scan_installed_apps(query: str = "") -> list[dict]:
    """Scan standard macOS app directories for .app bundles."""
    app_dirs = [
        "/Applications",
        "/System/Applications",
        "/System/Applications/Utilities",
        os.path.expanduser("~/Applications"),
        "/Applications/Utilities",
    ]

    apps = []
    seen = set()

    for app_dir in app_dirs:
        if not os.path.isdir(app_dir):
            continue
        try:
            for entry in os.listdir(app_dir):
                if not entry.endswith(".app"):
                    continue
                name = entry[:-4]  # strip .app
                if name in seen:
                    continue
                seen.add(name)
                full_path = os.path.join(app_dir, entry)
                apps.append({
                    "name": name,
                    "path": full_path,
                    "location": app_dir,
                })
        except PermissionError:
            continue

    # Sort alphabetically
    apps.sort(key=lambda a: a["name"].lower())

    # Filter by query if provided
    if query:
        q = query.lower()
        apps = [a for a in apps if q in a["name"].lower()]

    return apps


@tool(
    name="open_application",
    description="Open a macOS desktop application by name (e.g. 'Safari', 'Figma', 'Terminal', 'Claude'). For the Claude desktop app, use name='Claude'.",
    safety="safe",
    params={
        "name": {"type": "string", "description": "Application name"},
    },
)
def open_application(name: str) -> str:
    try:
        subprocess.run(["open", "-a", name], check=True, capture_output=True)
        return f"Opened {name}"
    except subprocess.CalledProcessError:
        return f"Could not open '{name}' — app not found"


@tool(
    name="open_url",
    description="Open a URL in the default web browser.",
    safety="safe",
    params={
        "url": {"type": "string", "description": "The URL to open"},
    },
)
def open_url(url: str) -> str:
    subprocess.run(["open", url], check=False)
    return f"Opened {url}"


@tool(
    name="list_running_apps",
    description="List all currently running macOS applications.",
    safety="safe",
    params={},
)
def list_running_apps() -> str:
    result = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to get name of every process whose background only is false'],
        capture_output=True, text=True,
    )
    return result.stdout.strip() or "Could not list applications"


@tool(
    name="list_installed_apps",
    description=(
        "List installed macOS applications. Optionally filter by a search query. "
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
    apps = _scan_installed_apps(query)

    if not apps:
        if query:
            return f"No installed apps matching '{query}'. Try a broader search."
        return "Could not find any installed applications."

    # Format as numbered list for easy selection
    lines = []
    if query:
        lines.append(f"Apps matching '{query}' ({len(apps)} found):\n")
    else:
        lines.append(f"Installed applications ({len(apps)} total):\n")

    for i, app in enumerate(apps, 1):
        location = app["location"].replace("/System/Applications", "System")
        location = location.replace("/Applications", "Apps")
        location = location.replace(os.path.expanduser("~"), "~")
        lines.append(f"  {i:3d}. {app['name']}  [{location}]")

    return "\n".join(lines)


@tool(
    name="app_action",
    description=(
        "Send an AppleScript command to a running macOS application. "
        "Use this to control apps AFTER they are opened — create documents, "
        "insert text, save, close, navigate tabs, etc. "
        "The 'command' param is full AppleScript that goes inside a 'tell application' block. "
        "IMPORTANT for Microsoft Word text insertion — use this exact pattern: "
        "set content of text object of active document to \"your text here\" "
        "For multi-line text use \\n: \"Line one\\nLine two\" "
        "Other common commands: "
        "Word: 'make new document', 'save active document' "
        "Safari: 'make new tab', 'set URL of current tab of window 1 to \"url\"' "
        "TextEdit: 'make new document', 'set text of document 1 to \"text\"' "
        "Pages/Numbers: 'make new document'"
    ),
    safety="confirm",
    params={
        "app_name": {
            "type": "string",
            "description": "The application to control (e.g. 'Microsoft Word', 'Safari', 'TextEdit')",
        },
        "command": {
            "type": "string",
            "description": (
                "AppleScript command(s) to run inside 'tell application'. "
                "For multiple commands, separate with newlines. "
                "Use regular quotes for strings in AppleScript."
            ),
        },
    },
)
def app_action(app_name: str, command: str) -> str:
    safe_app = _escape_applescript(app_name)

    # Security: block dangerous AppleScript patterns
    blocked = ["do shell script", "run script", "system events", "keystroke"]
    cmd_lower = command.lower()
    for b in blocked:
        if b in cmd_lower:
            return f"[error] Command contains blocked phrase: '{b}'"

    # Build multi-line tell block so complex commands work
    script = f'tell application "{safe_app}"\n{command}\nend tell'

    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip()
            return f"[error] {err}" if err else "[error] Command failed"
        return output or f"Done — sent command to {app_name}"
    except subprocess.TimeoutExpired:
        return "[error] Command timed out after 15 seconds"
    except Exception as e:
        return f"[error] {e}"


@tool(
    name="quit_application",
    description="Quit a running macOS application by name.",
    safety="confirm",
    params={
        "name": {"type": "string", "description": "Application name to quit"},
    },
)
def quit_application(name: str) -> str:
    safe_name = _escape_applescript(name)
    result = subprocess.run(
        ["osascript", "-e", f'tell application "{safe_name}" to quit'],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        return f"Quit {name}"
    return f"Could not quit '{name}': {result.stderr.strip()}"
