"""
HAL9000 — Tools Package
Agent OS layer: tool registry, definitions, execution, and safety checks.
Each tool is a decorated Python function that HAL can call via LLM function calling.

Tool implementations are split by domain:
  shell.py      — run_shell
  apps.py       — open/quit/list applications, open URLs
  files.py      — list/read/write/search/info
  macos.py      — volume, brightness, notifications, clipboard, screenshot
  web.py        — web_search, fetch_url
  memory.py     — remember, recall, forget, list_memories
  delegation.py — delegate_to_claude_code
"""

import json
import os
from dataclasses import dataclass, field
from typing import Callable


# ── Security helpers ────────────────────────────────────

# Commands the LLM is allowed to run via run_shell.
SHELL_ALLOWED_COMMANDS = {
    "ls", "cat", "head", "tail", "wc", "find", "grep", "awk", "sed",
    "echo", "pwd", "whoami", "date", "cal", "uptime", "df", "du",
    "which", "file", "sort", "uniq", "tr", "cut", "diff", "basename",
    "dirname", "realpath", "stat", "md5", "shasum", "xxd",
    "git", "npm", "node", "python3", "python", "pip", "pip3",
    "brew", "make", "cargo", "go", "swift", "xcodebuild",
    "curl", "wget", "ping", "dig", "nslookup", "ifconfig", "networksetup",
    "open", "pbcopy", "pbpaste", "say", "screencapture",
    "pmset", "system_profiler", "sw_vers", "uname",
    "mkdir", "touch", "cp", "mv", "rm", "ln", "chmod",
    "tar", "zip", "unzip", "gzip", "gunzip",
    "top", "ps", "kill", "killall", "lsof",
}

# Commands explicitly blocked (destructive / dangerous)
SHELL_BLOCKED_COMMANDS = {
    "sudo", "su", "doas", "passwd", "chown", "chgrp",
    "shutdown", "reboot", "halt", "init",
    "mkfs", "fdisk", "diskutil",
    "launchctl",
}


def _escape_applescript(s: str) -> str:
    """Escape a string for safe embedding in AppleScript double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ── Memory persistence path (legacy — use core.memory_store instead) ──

MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory")
MEMORY_FILE = os.path.join(MEMORY_DIR, "facts.json")


# ── Tool Registry ────────────────────────────────────────

TOOL_REGISTRY: dict[str, "ToolDef"] = {}


@dataclass
class ToolParam:
    type: str
    description: str
    required: bool = True
    enum: list[str] = field(default_factory=list)


@dataclass
class ToolDef:
    name: str
    description: str
    safety: str  # "safe", "confirm", "dangerous"
    params: dict[str, ToolParam]
    fn: Callable


def tool(name: str, description: str, safety: str = "safe", params: dict = None):
    """Decorator to register a tool."""

    def decorator(fn: Callable):
        parsed_params = {}
        if params:
            for k, v in params.items():
                parsed_params[k] = ToolParam(
                    type=v.get("type", "string"),
                    description=v.get("description", ""),
                    required=v.get("required", True),
                    enum=v.get("enum", []),
                )

        TOOL_REGISTRY[name] = ToolDef(
            name=name,
            description=description,
            safety=safety,
            params=parsed_params,
            fn=fn,
        )
        return fn

    return decorator


# ── Tool Execution ───────────────────────────────────────

def execute(name: str, args: dict) -> dict:
    """
    Execute a tool by name with the given arguments.
    Returns {"result": str} on success or {"error": str} on failure.
    """
    tool_def = TOOL_REGISTRY.get(name)
    if not tool_def:
        return {"error": f"Unknown tool: {name}"}

    # Pro feature check
    try:
        from core.license import get_license, GATED_TOOLS, License
        if name in GATED_TOOLS:
            lic = get_license()
            required = GATED_TOOLS[name]
            if required not in lic.features:
                tier = License.tier_needed(required)
                return {"error": f"'{name}' requires HAL Pro. Upgrade at hal9000.dev"}
    except ImportError:
        pass

    try:
        result = tool_def.fn(**args)
        return {"result": str(result)}
    except Exception as e:
        return {"error": f"Tool '{name}' failed: {e}"}


def get_safety(name: str) -> str:
    """Return the safety level of a tool."""
    tool_def = TOOL_REGISTRY.get(name)
    return tool_def.safety if tool_def else "dangerous"


# ── Format Converters ────────────────────────────────────

def to_openai_tools() -> list[dict]:
    """Convert registry to OpenAI function calling format."""
    tools = []
    for t in TOOL_REGISTRY.values():
        properties = {}
        required = []
        for pname, param in t.params.items():
            prop = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            properties[pname] = prop
            if param.required:
                required.append(pname)

        tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return tools


def to_anthropic_tools() -> list[dict]:
    """Convert registry to Anthropic tool use format."""
    tools = []
    for t in TOOL_REGISTRY.values():
        properties = {}
        required = []
        for pname, param in t.params.items():
            prop = {"type": param.type, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            properties[pname] = prop
            if param.required:
                required.append(pname)

        tools.append({
            "name": t.name,
            "description": t.description,
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        })
    return tools


def to_gemini_tools() -> list[dict]:
    """Convert registry to Gemini function declarations format."""
    declarations = []
    for t in TOOL_REGISTRY.values():
        properties = {}
        required = []
        for pname, param in t.params.items():
            gtype = param.type.upper()
            if gtype not in ("INTEGER", "NUMBER", "BOOLEAN"):
                gtype = "STRING"

            prop = {"type": gtype, "description": param.description}
            if param.enum:
                prop["enum"] = param.enum
            properties[pname] = prop
            if param.required:
                required.append(pname)

        declarations.append({
            "name": t.name,
            "description": t.description,
            "parameters": {
                "type": "OBJECT",
                "properties": properties,
                "required": required,
            },
        })
    return [{"function_declarations": declarations}]


# ── Helpers (shared by tool modules) ─────────────────────

def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _load_memories() -> list[dict]:
    if os.path.isfile(MEMORY_FILE):
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_memories(memories: list[dict]):
    os.makedirs(MEMORY_DIR, exist_ok=True)
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, indent=2, ensure_ascii=False)


# ── Import all tool modules to trigger @tool registration ─
# These imports MUST be at the bottom so the registry is ready.

from core.tools import shell      # noqa: E402, F401
from core.tools import apps       # noqa: E402, F401
from core.tools import files      # noqa: E402, F401
from core.tools import system     # noqa: E402, F401  # cross-platform (was macos.py)
from core.tools import web        # noqa: E402, F401
from core.tools import memory     # noqa: E402, F401
from core.tools import delegation  # noqa: E402, F401
from core.tools import artifacts   # noqa: E402, F401
