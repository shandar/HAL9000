"""
HAL9000 — MCP Server
Exposes HAL's physical capabilities (webcam, voice, macOS control, memory)
as MCP tools that Claude Code / Claude Desktop can call.

Usage:
    claude mcp add hal-9000 -- python /path/to/hal_mcp_server.py

This gives Claude Code access to:
    - hal_see:           Capture webcam frame and describe what's visible
    - hal_screenshot:    Capture the macOS screen
    - hal_speak:         Speak text aloud in HAL's cloned voice
    - hal_listen:        Listen via microphone and transcribe speech
    - hal_chat:          Send a message to HAL and get his response back
    - hal_remember:      Store a fact in persistent memory
    - hal_recall:        Search persistent memory
    - hal_forget:        Remove a memory
    - hal_list_memories: List all stored memories (with type filter)
    - hal_save_session: Save session context for handoff
    - hal_get_context:  Load context at session start
    - macos_volume:      Get or set system volume
    - macos_brightness:  Get or set display brightness
    - macos_notify:      Send a macOS notification
    - macos_clipboard:   Get or set clipboard contents
    - macos_apps:        List, open, or quit macOS applications
    - macos_wifi:        Get current WiFi network
    - macos_battery:     Get battery status
    - hal_web_search:    Search the web via DuckDuckGo
    - hal_fetch_url:     Fetch a webpage's text content
"""

import asyncio
import base64
import datetime
import io
import json
import os
import subprocess
import sys
import tempfile
import threading

# Ensure project root is on path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from mcp.server.fastmcp import FastMCP


def _escape_applescript(s: str) -> str:
    """Escape a string for safe embedding in AppleScript double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')

# ── Initialize MCP server ──────────────────────────────────

mcp = FastMCP("HAL9000")

# ── Lazy-loaded subsystems ──────────────────────────────────
# We lazy-load heavy subsystems (webcam, voice, hearing) only when
# a tool that needs them is first called. This keeps startup instant.

_vision = None
_vision_lock = threading.Lock()

_voice = None
_voice_lock = threading.Lock()

_hearing = None
_hearing_lock = threading.Lock()


def _get_vision():
    """Lazy-load the vision subsystem and start the camera."""
    global _vision
    if _vision is not None:
        return _vision
    with _vision_lock:
        if _vision is not None:
            return _vision
        # Set OpenCV env before import
        os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "0")
        from core.vision import Vision
        _vision = Vision()
        if not _vision.start():
            _vision = None
            return None
        # Give camera a moment to warm up
        import time
        time.sleep(0.5)
        return _vision


def _get_voice():
    """Lazy-load the voice (TTS) subsystem."""
    global _voice
    if _voice is not None:
        return _voice
    with _voice_lock:
        if _voice is not None:
            return _voice
        from config import cfg  # noqa: ensure dotenv loaded
        from core.voice import Voice
        _voice = Voice()
        return _voice


def _get_hearing():
    """Lazy-load the hearing (STT) subsystem."""
    global _hearing
    if _hearing is not None:
        return _hearing
    with _hearing_lock:
        if _hearing is not None:
            return _hearing
        from core.hearing import Hearing
        _hearing = Hearing()
        return _hearing


# ── Memory store (typed, shared with HAL engine) ──────────────

from core.memory_store import get_store as _get_store

# ── Cross-platform API ────────────────────────────────────────

from core.platform import platform as _platform


# ══════════════════════════════════════════════════════════════
#  MCP TOOLS
# ══════════════════════════════════════════════════════════════


# ── Vision ──────────────────────────────────────────────────

@mcp.tool()
def hal_see() -> str:
    """Capture a frame from the webcam and return it as a base64-encoded JPEG.
    Use this to see what's on the user's desk, who is in front of the computer,
    or understand the physical environment. The image is returned as base64 data
    that can be analyzed directly.
    NOTE: Requires HAL server to be running (python server.py) with Vision enabled."""
    import urllib.request
    import json as _json

    # Proxy through HAL's running web server (which has camera permission)
    try:
        req = urllib.request.Request("http://localhost:9000/api/frame")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())
        if "error" in data:
            return f"ERROR: {data['error']}. Make sure HAL server is running (python server.py) and Vision is toggled ON."
        return f"data:image/jpeg;base64,{data['frame']}"
    except Exception:
        # Fallback: try direct camera access (works when run from Terminal)
        vision = _get_vision()
        if vision is None:
            return "ERROR: Could not access camera. Start HAL server (python server.py), activate HAL, and toggle Vision ON."
        frame_b64 = vision.get_frame_b64()
        if not frame_b64:
            return "ERROR: Could not capture frame."
        return f"data:image/jpeg;base64,{frame_b64}"


@mcp.tool()
def hal_screenshot() -> str:
    """Take a screenshot of the entire macOS screen and return the file path.
    Use this to see what's on the user's screen — code editors, browsers,
    design tools, terminal output, etc."""
    path = "/tmp/hal_mcp_screenshot.png"
    # Use osascript to invoke screencapture — works better from sandboxed processes
    result = subprocess.run(
        ["screencapture", "-x", path],
        capture_output=True,
    )
    if result.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        return f"Screenshot captured ({size} bytes). data:image/png;base64,{img_data}"
    # Fallback: try via osascript
    result2 = subprocess.run(
        ["osascript", "-e", f'do shell script "screencapture -x {path}"'],
        capture_output=True,
    )
    if result2.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 0:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode("utf-8")
        return f"Screenshot captured ({size} bytes). data:image/png;base64,{img_data}"
    return "ERROR: Failed to capture screenshot. Grant Screen Recording permission to Claude.app in System Settings > Privacy & Security > Screen Recording."


# ── Voice (TTS) ────────────────────────────────────────────

@mcp.tool()
def hal_speak(text: str) -> str:
    """Speak the given text aloud using HAL9000's cloned voice.
    Use this to give verbal feedback, read code aloud, announce results,
    or communicate with the user via speech. The voice is a cloned HAL9000 voice.
    Keep text concise — spoken output should be short declarative sentences."""
    if not text.strip():
        return "ERROR: No text provided."

    voice = _get_voice()
    # Speak synchronously so the tool returns after audio finishes
    voice.speak(text, blocking=True)
    return f"Spoken: {text}"


# ── Hearing (STT) ──────────────────────────────────────────

@mcp.tool()
def hal_listen() -> str:
    """Listen through the microphone for speech and return the transcription.
    Waits for the user to speak, records until silence, then transcribes.
    Returns the transcribed text, or an error if no speech was detected.
    Timeout is approximately 6 seconds of silence before giving up."""
    hearing = _get_hearing()
    text = hearing.listen()
    if text:
        return f"Heard: {text}"
    return "No speech detected. The user may not have spoken, or the audio was too quiet."


# ── Chat (bidirectional — Claude Code ↔ HAL) ──────────────────

@mcp.tool()
def hal_chat(message: str) -> str:
    """Send a message to HAL and get his spoken response back.
    HAL will think about your message, speak the reply aloud, and return the text.
    Use this for bidirectional conversation between Claude Code and HAL.
    Example: hal_chat("I've finished reviewing the code. Found 3 issues.")
    HAL will process this as if the user said it, respond with his personality,
    and speak the response aloud through the browser."""
    import urllib.request
    import json as _json

    try:
        payload = _json.dumps({"text": f"[From Claude Code]: {message}"}).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:9000/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
        reply = data.get("reply", "(no response)")
        return f"HAL said: {reply}"
    except Exception as e:
        return f"Could not reach HAL server: {e}. Make sure HAL is running (python server.py)."


# ── Memory ──────────────────────────────────────────────────

@mcp.tool()
def hal_remember(fact: str, type: str = "fact", source: str = "claude_code") -> str:
    """Store a fact in HAL's persistent memory. This survives restarts.
    Use this to remember user preferences, project context, names, decisions, etc.
    type: fact (default), decision, preference, task.
    source: who is storing this — claude_code (default), hal, user."""
    store = _get_store()
    entry = store.add(content=fact, type=type, source=source)
    return f"Remembered ({entry.type}): {fact}"


@mcp.tool()
def hal_recall(query: str, type: str = "") -> str:
    """Search HAL's persistent memory for facts matching a query.
    Optionally filter by type: fact, decision, preference, task, session_summary."""
    store = _get_store()
    matches = store.search(query, type=type or None)
    if not matches:
        return f"No memories matching '{query}'" + (f" (type={type})" if type else "")

    lines = [f"- [{m.type}] {m.content} (saved {m.timestamp[:10]})" for m in matches]
    return f"Found {len(matches)} memories:\n" + "\n".join(lines)


@mcp.tool()
def hal_forget(query: str) -> str:
    """Remove memories matching a keyword from HAL's persistent memory."""
    store = _get_store()
    removed = store.remove(query)
    return f"Removed {removed} memories matching '{query}'" if removed else f"No memories matching '{query}'"


@mcp.tool()
def hal_list_memories(type: str = "") -> str:
    """List all facts stored in HAL's persistent memory.
    Optionally filter by type: fact, decision, preference, task, session_summary."""
    store = _get_store()
    entries = store.list_all(type=type or None)
    if not entries:
        return "No memories stored yet." + (f" (type={type})" if type else "")
    lines = [f"- [{m.type}] {m.content}" for m in entries]
    return f"{len(entries)} memories:\n" + "\n".join(lines)


@mcp.tool()
def hal_save_session(summary: str = "") -> str:
    """Manually save the current session context to HAL's memory.
    Use this when wrapping up a Claude Code session to hand off context.
    If summary is empty, a generic marker is stored."""
    store = _get_store()
    content = summary or "Claude Code session ended (no summary provided)."
    entry = store.add(
        content=content,
        type="session_summary",
        source="claude_code",
        metadata={"manual": True},
    )
    return f"Session saved: {entry.content}"


@mcp.tool()
def hal_get_context(query: str = "") -> str:
    """Get relevant context from HAL's memory for a new session.
    Returns recent session summaries and any memories matching the query.
    Call this at the start of a Claude Code session to load context."""
    store = _get_store()
    parts = []

    # Recent session summaries
    summaries = store.get_session_summaries(limit=3)
    if summaries:
        parts.append("=== Recent Sessions ===")
        for s in summaries:
            parts.append(f"- {s.content}")

    # Relevant memories if query provided
    if query:
        matches = store.search(query)
        if matches:
            parts.append(f"\n=== Memories matching '{query}' ===")
            for m in matches:
                parts.append(f"- [{m.type}] {m.content}")

    # Decisions and preferences (always useful)
    decisions = store.list_all(type="decision")
    if decisions:
        parts.append("\n=== Active Decisions ===")
        for d in decisions:
            parts.append(f"- {d.content}")

    prefs = store.list_all(type="preference")
    if prefs:
        parts.append("\n=== Preferences ===")
        for p in prefs:
            parts.append(f"- {p.content}")

    return "\n".join(parts) or "No context available yet."


# ── macOS System ────────────────────────────────────────────

@mcp.tool()
def macos_volume(action: str = "get", level: int = 50) -> str:
    """Get or set the system volume.
    action: 'get' to read current volume, 'set' to change it.
    level: volume level 0-100 (only used when action is 'set')."""
    if action == "set":
        return _platform.set_volume(level)
    return _platform.get_volume()


@mcp.tool()
def macos_brightness(action: str = "get", level: float = 0.5) -> str:
    """Get or set the display brightness.
    action: 'get' to read current brightness, 'set' to change it.
    level: brightness 0.0-1.0 (only used when action is 'set')."""
    if action == "set":
        return _platform.set_brightness(level)
    return _platform.get_brightness()


@mcp.tool()
def macos_notify(title: str, message: str) -> str:
    """Send a desktop notification with a title and message."""
    return _platform.send_notification(title, message)


@mcp.tool()
def macos_clipboard(action: str = "get", text: str = "") -> str:
    """Get or set the clipboard contents.
    action: 'get' to read clipboard, 'set' to copy text to clipboard.
    text: the text to copy (only used when action is 'set')."""
    if action == "set":
        return _platform.set_clipboard(text)
    return _platform.get_clipboard()


@mcp.tool()
def macos_apps(action: str = "list", name: str = "") -> str:
    """Manage applications.
    action: 'list' to see running apps, 'open' to launch an app, 'quit' to close an app.
    name: application name (required for 'open' and 'quit')."""
    if action == "open":
        if not name:
            return "ERROR: Provide an application name to open."
        return _platform.open_application(name)
    elif action == "quit":
        if not name:
            return "ERROR: Provide an application name to quit."
        return _platform.quit_application(name)
    return _platform.list_running_apps()


@mcp.tool()
def macos_wifi() -> str:
    """Get the current WiFi network name."""
    return _platform.get_wifi()


@mcp.tool()
def macos_battery() -> str:
    """Get battery level and charging status."""
    return _platform.get_battery()


# ── Web ─────────────────────────────────────────────────────

@mcp.tool()
def hal_web_search(query: str) -> str:
    """Search the web using DuckDuckGo and return top results.
    Use for current events, facts, documentation, or anything not in local knowledge."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No results found for: {query}"
        lines = []
        for r in results:
            lines.append(f"- {r['title']}: {r['body'][:200]}")
        return "\n".join(lines)
    except Exception as e:
        return f"Search error: {e}"


@mcp.tool()
def hal_fetch_url(url: str) -> str:
    """Fetch a webpage and return its text content (first 8000 chars).
    Good for reading articles, documentation, or API responses."""
    import re
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HAL9000/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000]
    except Exception as e:
        return f"Error fetching {url}: {e}"


# ── Time ────────────────────────────────────────────────────

@mcp.tool()
def hal_time() -> str:
    """Get the current date and time."""
    now = datetime.datetime.now()
    return now.strftime("%A, %B %d, %Y at %I:%M %p")


# ── Main ────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
