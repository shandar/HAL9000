"""Shell & Terminal tools."""

import os
import shlex
import subprocess

from core.tools import tool, SHELL_ALLOWED_COMMANDS, SHELL_BLOCKED_COMMANDS


@tool(
    name="run_shell",
    description="Execute a shell command on the user's Mac and return stdout/stderr. Use for any terminal operation.",
    safety="confirm",
    params={
        "command": {"type": "string", "description": "The shell command to execute"},
    },
)
def run_shell(command: str) -> str:
    try:
        parts = shlex.split(command)
    except ValueError as e:
        return f"[error] Invalid command syntax: {e}"

    if not parts:
        return "[error] Empty command"

    base_cmd = os.path.basename(parts[0])

    if base_cmd in SHELL_BLOCKED_COMMANDS:
        return f"[error] '{base_cmd}' is blocked for safety. Ask the user to run it manually."

    if base_cmd not in SHELL_ALLOWED_COMMANDS:
        return (
            f"[error] '{base_cmd}' is not in the allowed command list. "
            f"Ask the user to approve or run it manually."
        )

    try:
        result = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.expanduser("~"),
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n[stderr] {result.stderr.strip()}"
        return output[:5000] or "(no output)"
    except subprocess.TimeoutExpired:
        return "[error] Command timed out after 30 seconds"
    except FileNotFoundError:
        return f"[error] Command not found: {base_cmd}"
    except OSError as e:
        return f"[error] {e}"
