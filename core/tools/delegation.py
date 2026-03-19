"""Claude Code tools — open interactively, delegate tasks, or run background jobs."""

import json
import os
import subprocess
import time

from core.platform import platform
from core.tools import tool

# Engine reference — set by server.py at startup to avoid circular import
_engine_ref = None


def set_engine(engine):
    """Called by server.py to provide the engine reference."""
    global _engine_ref
    _engine_ref = engine

# Debounce guard — prevent duplicate Terminal opens
_last_open_time = 0
_OPEN_COOLDOWN = 5  # seconds


def _find_claude_bin() -> str:
    """Locate the claude CLI binary (cross-platform)."""
    import platform as _plat
    home = os.path.expanduser("~")

    if _plat.system() == "Windows":
        candidates = [
            os.path.join(home, ".local", "bin", "claude.exe"),
            os.path.join(home, "AppData", "Roaming", "npm", "claude.cmd"),
            os.path.join(home, "AppData", "Roaming", "npm", "claude"),
            os.path.join(os.environ.get("ProgramFiles", ""), "claude", "claude.exe"),
        ]
    else:
        candidates = [
            os.path.join(home, ".local/bin/claude"),
            "/opt/homebrew/bin/claude",
            "/usr/local/bin/claude",
            os.path.join(home, ".npm-global/bin/claude"),
        ]

    for candidate in candidates:
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

    # Use platform API to open a terminal with claude command
    result = platform.open_terminal(f'"{claude_bin}"', cwd)
    return f"Opened Claude Code CLI at {cwd}" if "Failed" not in result else result


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
    # Default to HAL project dir (not home) so Claude Code has project context
    hal_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cwd = os.path.expanduser(working_directory) if working_directory else hal_dir
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
    # Remove API key so Claude Code uses OAuth (Max plan) instead of API credits
    env.pop("ANTHROPIC_API_KEY", None)

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


# ── Background Task Tools ─────────────────────────────────


def _get_task_runner():
    """Get the task runner from the engine."""
    if _engine_ref:
        return _engine_ref.task_runner
    return None


@tool(
    name="background_task",
    description=(
        "Submit a coding task to run in the background via Claude Code. "
        "The task runs asynchronously — HAL continues while it executes. "
        "Use for long-running tasks: refactoring, writing tests, building projects, "
        "running analysis. Returns a task ID to check progress."
    ),
    safety="confirm",
    params={
        "task": {
            "type": "string",
            "description": "A clear, specific coding task description.",
        },
        "working_directory": {
            "type": "string",
            "description": "The directory to work in (defaults to home)",
            "required": False,
        },
    },
)
def background_task(task: str, working_directory: str = "") -> str:
    runner = _get_task_runner()
    if not runner:
        return "Background task runner not available. Is HAL running?"

    # Default to HAL project dir
    if not working_directory:
        working_directory = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    t = runner.submit(task, working_directory)
    queue_pos = len(runner.list_tasks(status="queued"))
    running = runner.active_count()

    status_msg = f"Task {t.id} submitted."
    if t.status == "running":
        status_msg += " Running now."
    else:
        status_msg += f" Queued (position {queue_pos}, {running} running)."
    return status_msg


@tool(
    name="list_tasks",
    description="List all background tasks and their current status.",
    safety="safe",
    params={},
)
def list_tasks() -> str:
    runner = _get_task_runner()
    if not runner:
        return "Task runner not available."

    tasks = runner.list_tasks()
    if not tasks:
        return "No background tasks."

    lines = []
    for t in tasks:
        elapsed = ""
        if t["started_at"]:
            end = t["completed_at"] or time.time()
            secs = int(end - t["started_at"])
            elapsed = f" ({secs}s)"
        line = f"[{t['status']}] {t['id']}: {t['description'][:60]}{elapsed}"
        if t["status"] == "running" and t["progress"]:
            line += f"\n  → {t['progress'][:100]}"
        elif t["status"] == "completed" and t.get("result"):
            line += f"\n  Result: {t['result'][:300]}"
        elif t["status"] == "failed" and t.get("error"):
            line += f"\n  Error: {t['error'][:200]}"
        lines.append(line)
    return "\n".join(lines)


@tool(
    name="cancel_task",
    description="Cancel a queued or running background task by its ID.",
    safety="safe",
    params={
        "task_id": {
            "type": "string",
            "description": "The task ID to cancel (from list_tasks output)",
        },
    },
)
def cancel_task(task_id: str) -> str:
    runner = _get_task_runner()
    if not runner:
        return "Task runner not available."

    if runner.cancel(task_id):
        return f"Task {task_id} cancelled."
    return f"Could not cancel task {task_id} — not found or already completed."


# ── Multi-Agent Orchestration ─────────────────────────────


def _get_orchestrator():
    """Get the orchestrator from the engine."""
    if _engine_ref:
        return getattr(_engine_ref, "orchestrator", None)
    return None


@tool(
    name="orchestrate",
    description=(
        "Launch multiple Claude Code agents on parallel tasks. "
        "Each agent gets a name and task, and they run concurrently. "
        "HAL monitors all agents and reports conflicts if they touch the same files. "
        "Pass tasks as a JSON array: [{\"name\": \"frontend\", \"task\": \"...\", \"cwd\": \"...\"}]"
    ),
    safety="confirm",
    params={
        "tasks": {
            "type": "string",
            "description": (
                "JSON array of agent definitions. Each object has: "
                "name (string), task (string), cwd (string, optional). "
                "Example: [{\"name\": \"tests\", \"task\": \"write unit tests for auth\"}]"
            ),
        },
    },
)
def orchestrate(tasks: str) -> str:
    orch = _get_orchestrator()
    if not orch:
        return "Orchestrator not available. Is HAL running?"

    try:
        task_list = json.loads(tasks)
    except json.JSONDecodeError:
        return "Invalid JSON. Expected array of {name, task, cwd} objects."

    if not isinstance(task_list, list) or not task_list:
        return "Expected a non-empty JSON array."

    agents = []
    for t in task_list:
        name = t.get("name", f"agent-{len(agents)+1}")
        task_desc = t.get("task", "")
        cwd = t.get("cwd", "")
        if not task_desc:
            continue
        agent = orch.spawn_agent(name, task_desc, cwd)
        agents.append(f"{agent.name} (id: {agent.id})")

    if not agents:
        return "No valid tasks provided."

    return f"Spawned {len(agents)} agents: {', '.join(agents)}. Monitor via list_agents."


@tool(
    name="list_agents",
    description="List all orchestrated agents and their current status.",
    safety="safe",
    params={},
)
def list_agents() -> str:
    orch = _get_orchestrator()
    if not orch:
        return "Orchestrator not available."

    agents = orch.list_agents()
    if not agents:
        return "No agents spawned."

    lines = []
    for a in agents:
        elapsed = ""
        if a["started_at"]:
            end = a["completed_at"] or time.time()
            elapsed = f" ({int(end - a['started_at'])}s)"
        line = f"[{a['status']}] {a['name']} ({a['id']}): {a['task'][:60]}{elapsed}"
        if a["files_touched"]:
            line += f"\n  Files: {', '.join(a['files_touched'][:5])}"
        lines.append(line)

    return "\n".join(lines)


@tool(
    name="check_conflicts",
    description="Check if any orchestrated agents modified the same files (potential conflicts).",
    safety="safe",
    params={},
)
def check_conflicts() -> str:
    orch = _get_orchestrator()
    if not orch:
        return "Orchestrator not available."

    conflicts = orch.check_conflicts()
    if not conflicts:
        return "No file conflicts detected."

    lines = ["File conflicts detected:"]
    for c in conflicts:
        lines.append(f"  {c['file']} — modified by: {', '.join(c['agents'])}")
    return "\n".join(lines)
