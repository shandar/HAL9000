# HAL 9000 — Tool Reference

## Overview

HAL has **31 tools** that give it the ability to act on your behalf. When you ask HAL to do something, the LLM decides which tool(s) to call, HAL executes them, and then summarizes the result in speech.

All tools follow a safety model: **safe** tools run immediately, **confirm** tools ask before executing, **dangerous** tools warn and require explicit approval.

---

## Security Model

### Command Whitelist (run_shell)

`run_shell` no longer passes commands through a shell interpreter. Instead:

1. Commands are parsed with `shlex.split()` (no shell metacharacter interpretation)
2. The base command is checked against a **whitelist of 77 approved commands**
3. Commands on the **blocklist** (sudo, shutdown, etc.) are rejected immediately
4. Unknown commands are rejected with a message to ask the user

**Allowed commands include:** ls, cat, grep, find, git, npm, node, python, brew, curl, open, mkdir, cp, mv, rm, ps, kill, and more.

**Blocked commands:** sudo, su, shutdown, reboot, mkfs, diskutil, launchctl, passwd.

### AppleScript Escaping

All user-controlled strings interpolated into `osascript -e` commands are escaped via `_escape_applescript()`:
- `"` → `\"`
- `\` → `\\`

This prevents injection attacks where a crafted string could break out of an AppleScript string context.

### Safety Levels

| Level | Behavior | Examples |
|-------|----------|---------|
| `safe` | Execute immediately | get_time, get_battery, list_files, web_search |
| `confirm` | HAL asks "Shall I proceed?" | run_shell, write_file, quit_application, forget |
| `dangerous` | HAL warns + requires explicit "yes" | (reserved for future destructive tools) |

---

## Tool Categories

### 1. Shell & Terminal

| Tool | Safety | Description |
|------|--------|-------------|
| `run_shell` | confirm | Execute a whitelisted shell command, return stdout/stderr (30s timeout) |

**Security:** Commands are validated against a whitelist before execution. `shell=True` is never used. The command runs with `subprocess.run(parts)` using an argument list.

**Examples:**
- "How much disk space do I have?" → `run_shell("df -h")`
- "Run the build" → `run_shell("npm run build")`
- "Check if the server is running" → `run_shell("lsof -i:3000")`

---

### 2. Applications & URLs

| Tool | Safety | Description |
|------|--------|-------------|
| `open_application` | safe | Open a macOS application by name |
| `open_url` | safe | Open a URL in the default browser |
| `list_running_apps` | safe | List currently running applications |
| `list_installed_apps` | safe | List/search all installed macOS applications (.app bundles) |
| `app_action` | confirm | Send AppleScript commands to control running applications |
| `quit_application` | confirm | Quit an application by name (AppleScript escaped) |

**`list_installed_apps`** scans `/Applications`, `/System/Applications`, `~/Applications`, and `/Applications/Utilities` for `.app` bundles. Accepts an optional search query to filter results.

**`app_action`** sends AppleScript `tell` blocks to running applications for automation (create documents, insert text, navigate tabs, etc.). Blocked commands: `do shell script`, `run script`, `system events`, `keystroke`.

---

### 3. File System

| Tool | Safety | Description |
|------|--------|-------------|
| `list_files` | safe | List files in a directory (max 100 entries) |
| `read_file` | safe | Read text file contents (max 10,000 chars, blocks .env/credentials) |
| `write_file` | confirm | Write/overwrite a text file |
| `search_files` | safe | Search for files by glob pattern (max 50 results) |
| `file_info` | safe | Get file size, dates, type (cross-platform compatible) |

**Security:** `read_file` blocks access to `.env`, `credentials.json`, `.npmrc`, `.netrc`.

---

### 4. macOS System

| Tool | Safety | Description |
|------|--------|-------------|
| `get_time` | safe | Current date and time |
| `get_battery` | safe | Battery level and charging status |
| `get_wifi` | safe | Current WiFi network name |
| `get_volume` | safe | Current system volume level |
| `set_volume` | safe | Set system volume (0-100, clamped) |
| `get_brightness` | safe | Current display brightness + dark mode status |
| `set_brightness` | safe | Set display brightness (0.0-1.0, clamped) |
| `send_notification` | safe | Show a macOS notification (AppleScript escaped) |
| `get_clipboard` | safe | Read clipboard contents (max 3000 chars) |
| `set_clipboard` | confirm | Write to clipboard |
| `screenshot` | safe | Capture screen to /tmp |

---

### 5. Web & Search

| Tool | Safety | Description |
|------|--------|-------------|
| `web_search` | safe | Search the web via DuckDuckGo (5 results) |
| `fetch_url` | safe | Fetch and extract text from a URL (max 8000 chars, HTML stripped) |

---

### 6. Memory (Persistent)

| Tool | Safety | Description |
|------|--------|-------------|
| `remember` | safe | Store a fact in persistent memory |
| `recall` | safe | Search persistent memory by keyword |
| `forget` | confirm | Remove matching memories |
| `list_memories` | safe | List all stored memories |

Memory persists in `memory/facts.json` across restarts. It's also injected into the system prompt so the LLM always has context.

---

### 7. Claude Code Integration

| Tool | Safety | Description |
|------|--------|-------------|
| `open_claude_code` | safe | Open Claude Code CLI in a new Terminal window (visible, interactive) |
| `delegate_to_claude_code` | confirm | Delegate a coding task to Claude Code CLI silently (120s timeout) |

Two distinct tools for Claude Code interaction:
- **`open_claude_code`** — Opens a visible Terminal window with Claude Code running interactively. Has a 5-second debounce guard to prevent duplicate windows.
- **`delegate_to_claude_code`** — Runs Claude Code silently in the background with `--print` flag. Returns the result without opening a Terminal.

---

## MCP Tools (Claude Code Integration)

The MCP server (`hal_mcp_server.py`) exposes 18 tools to Claude Code/Desktop:

| MCP Tool | Maps To |
|----------|---------|
| `hal_see` | Webcam frame capture (proxied through Flask server) |
| `hal_screenshot` | Screen capture with base64 return |
| `hal_speak` | TTS speech (blocking) |
| `hal_listen` | Mic recording + Whisper STT |
| `hal_remember` | Persistent memory write |
| `hal_recall` | Persistent memory search |
| `hal_forget` | Persistent memory delete |
| `hal_list_memories` | List all memories |
| `macos_volume` | Get/set system volume |
| `macos_brightness` | Get/set display brightness |
| `macos_notify` | macOS notification (escaped) |
| `macos_clipboard` | Get/set clipboard |
| `macos_apps` | List/open/quit applications |
| `macos_wifi` | WiFi network info |
| `macos_battery` | Battery status |
| `hal_web_search` | DuckDuckGo search |
| `hal_fetch_url` | Webpage text extraction |
| `hal_time` | Current date/time |

---

## Adding Custom Tools

To add a new tool, create a function in the appropriate `core/tools/*.py` module:

```python
@tool(
    name="my_tool",
    description="What this tool does — the LLM reads this to decide when to use it",
    safety="safe",
    params={
        "arg1": {
            "type": "string",
            "description": "Description of the argument"
        }
    }
)
def my_tool(arg1: str) -> str:
    # Do something
    return "result string"
```

The tool is automatically:
- Added to the tool registry
- Included in LLM function calling definitions
- Available to all providers (OpenAI, Anthropic, Gemini)
- Logged in the chat window when executed
- Available via the MCP server (if also added to `hal_mcp_server.py`)
