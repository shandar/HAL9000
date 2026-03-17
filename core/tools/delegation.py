"""Claude Code tools — open interactively or delegate tasks."""

import os
import subprocess
import time

from core.tools import tool, _escape_applescript

# Debounce guard — prevent duplicate Terminal opens
_last_open_time = 0
_OPEN_COOLDOWN = 5  # seconds


def _find_claude_bin() -> str:
    """Locate the claude CLI binary."""
    home = os.path.expanduser("~")
    for candidate in [
        os.path.join(home, ".local/bin/claude"),
        "/opt/homebrew/bin/claude",
        "/usr/local/bin/claude",
        os.path.join(home, ".npm-global/bin/claude"),
    ]:
        if os.path.isfile(candidate):
            return candidate
    return "claude"


@tool(
    name="open_claude_code",
    description=(
        "Open Claude Code CLI in a new Terminal window so the user can interact "
        "with it directly. Use this when the user says 'open claude code CLI', "
        "'launch claude code terminal', or picks the CLI option from disambiguation. "
        "This opens a visible Terminal window — it does NOT run silently."
    ),
    safety="safe",
    params={
        "working_directory": {
            "type": "string",
            "description": "The directory to open Claude Code in (defaults to home)",
            "required": False,
        },
    },
)
def open_claude_code(working_directory: str = "") -> str:
    global _last_open_time
    now = time.time()
    if now - _last_open_time < _OPEN_COOLDOWN:
        return "Claude Code terminal is already opening. Please wait."
    _last_open_time = now

    cwd = os.path.expanduser(working_directory or "~")
    if not os.path.isdir(cwd):
        return f"Directory not found: {cwd}"

    claude_bin = _find_claude_bin()
    safe_cwd = _escape_applescript(cwd)
    safe_bin = _escape_applescript(claude_bin)

    # Open a new Terminal window, cd to directory, and run claude
    script = f'''
    tell application "Terminal"
        activate
        do script "cd \\"{safe_cwd}\\" && \\"{safe_bin}\\""
    end tell
    '''

    try:
        subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return f"Opened Claude Code CLI in Terminal at {cwd}"
    except Exception as e:
        return f"Failed to open Terminal: {e}"


@tool(
    name="delegate_to_claude_code",
    description=(
        "Delegate a coding task to Claude Code CLI silently in the background. "
        "Claude Code runs non-interactively, executes the task, and returns the result. "
        "Use this when the user wants to delegate work like: reading/editing files, "
        "running builds, writing tests, refactoring, debugging. "
        "Do NOT use this to 'open' Claude Code — use open_claude_code for that."
    ),
    safety="confirm",
    params={
        "task": {
            "type": "string",
            "description": (
                "A clear, specific coding task description. "
                "Include file paths, expected behavior, and context."
            ),
        },
        "working_directory": {
            "type": "string",
            "description": "The directory to work in (defaults to home)",
            "required": False,
        },
    },
)
def delegate_to_claude_code(task: str, working_directory: str = "") -> str:
    cwd = os.path.expanduser(working_directory or "~")
    if not os.path.isdir(cwd):
        return f"Directory not found: {cwd}"

    claude_bin = _find_claude_bin()

    # Ensure local bins are on PATH for the subprocess
    home = os.path.expanduser("~")
    env = os.environ.copy()
    env["PATH"] = (
        os.path.join(home, ".local/bin") + ":"
        + "/opt/homebrew/bin:/usr/local/bin:"
        + env.get("PATH", "")
    )

    try:
        result = subprocess.run(
            [
                claude_bin,
                "--print",       # non-interactive, print result
                task,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=cwd,
            env=env,
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n[stderr] {result.stderr.strip()}"
        return output[:10000] or "(no output)"
    except FileNotFoundError:
        return (
            "Claude Code CLI not found. "
            "Install it with: npm install -g @anthropic-ai/claude-code"
        )
    except subprocess.TimeoutExpired:
        return "Claude Code task timed out after 120 seconds."
    except Exception as e:
        return f"Claude Code error: {e}"
