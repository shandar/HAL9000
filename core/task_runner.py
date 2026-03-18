"""
HAL9000 — Background Task Runner
Async task queue for delegating coding tasks to Claude Code CLI.

Tasks run via `claude --print` in background threads with:
- Real-time progress (last stdout line)
- Configurable timeout (default 600s)
- Cancellation via process.terminate()
- Concurrent execution (configurable max, default 2)
- Results stored in typed memory on completion
"""

import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from config import cfg


@dataclass
class Task:
    id: str
    description: str
    status: str  # queued | running | completed | failed | cancelled
    working_directory: str
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[str] = None
    error: Optional[str] = None
    progress: str = ""  # last line of stdout for live updates


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


class TaskRunner:
    """Manages a queue of background Claude Code tasks."""

    def __init__(self, max_concurrent: int = 2):
        self._tasks: dict[str, Task] = {}
        self._queue: list[str] = []  # task IDs waiting to run
        self._lock = threading.Lock()
        self._max_concurrent = max_concurrent
        self._processes: dict[str, subprocess.Popen] = {}

    def submit(self, description: str, working_directory: str = "") -> Task:
        """Submit a new task to the queue."""
        cwd = os.path.expanduser(working_directory or "~")
        task = Task(
            id=str(uuid.uuid4())[:8],
            description=description,
            status="queued",
            working_directory=cwd,
            created_at=time.time(),
        )

        with self._lock:
            self._tasks[task.id] = task
            self._queue.append(task.id)

        self._try_start_next()
        return task

    def cancel(self, task_id: str) -> bool:
        """Cancel a queued or running task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False

            if task.status == "queued":
                task.status = "cancelled"
                task.completed_at = time.time()
                if task_id in self._queue:
                    self._queue.remove(task_id)
                return True

            if task.status == "running":
                proc = self._processes.get(task_id)
                if proc:
                    proc.terminate()
                task.status = "cancelled"
                task.completed_at = time.time()
                return True

        return False

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[str] = None) -> list[dict]:
        """List all tasks as dicts, optionally filtered by status."""
        with self._lock:
            tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        # Sort: running first, then queued, then completed
        order = {"running": 0, "queued": 1, "completed": 2, "failed": 3, "cancelled": 4}
        tasks.sort(key=lambda t: (order.get(t.status, 5), -t.created_at))
        return [asdict(t) for t in tasks]

    def active_count(self) -> int:
        """Count currently running tasks."""
        with self._lock:
            return sum(1 for t in self._tasks.values() if t.status == "running")

    def _try_start_next(self):
        """Start next queued task if under concurrency limit."""
        with self._lock:
            running = sum(1 for t in self._tasks.values() if t.status == "running")
            while self._queue and running < self._max_concurrent:
                task_id = self._queue.pop(0)
                task = self._tasks.get(task_id)
                if not task or task.status != "queued":
                    continue
                task.status = "running"
                task.started_at = time.time()
                running += 1
                thread = threading.Thread(
                    target=self._worker, args=(task_id,), daemon=True
                )
                thread.start()

    def _worker(self, task_id: str):
        """Execute a task via Claude Code CLI."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            return

        claude_bin = _find_claude_bin()
        home = os.path.expanduser("~")
        env = os.environ.copy()
        env["PATH"] = (
            os.path.join(home, ".local/bin") + ":"
            + "/opt/homebrew/bin:/usr/local/bin:"
            + env.get("PATH", "")
        )

        timeout = getattr(cfg, "TASK_TIMEOUT", 600)

        try:
            proc = subprocess.Popen(
                [claude_bin, "--print", task.description],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=task.working_directory,
                env=env,
            )

            with self._lock:
                self._processes[task_id] = proc

            # Read stdout in real-time for progress updates
            output_lines: list[str] = []
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if line:
                    output_lines.append(line)
                    with self._lock:
                        task.progress = line[:200]

                # Check timeout
                elapsed = time.time() - (task.started_at or time.time())
                if elapsed > timeout:
                    proc.terminate()
                    with self._lock:
                        task.status = "failed"
                        task.error = f"Timed out after {timeout}s"
                        task.completed_at = time.time()
                    self._on_complete(task_id)
                    return

            proc.wait()
            stderr = proc.stderr.read().strip() if proc.stderr else ""

            with self._lock:
                if task.status == "cancelled":
                    return  # was cancelled while running

                full_output = "\n".join(output_lines)
                if stderr:
                    full_output += f"\n[stderr] {stderr}"

                if proc.returncode == 0:
                    task.status = "completed"
                    task.result = full_output[:10000] or "(no output)"
                else:
                    task.status = "failed"
                    task.error = full_output[:5000] or f"Exit code {proc.returncode}"
                task.completed_at = time.time()

        except FileNotFoundError:
            with self._lock:
                task.status = "failed"
                task.error = "Claude Code CLI not found. Install: npm i -g @anthropic-ai/claude-code"
                task.completed_at = time.time()
        except Exception as e:
            with self._lock:
                task.status = "failed"
                task.error = str(e)[:1000]
                task.completed_at = time.time()
        finally:
            with self._lock:
                self._processes.pop(task_id, None)

        self._on_complete(task_id)

    def _on_complete(self, task_id: str):
        """Store result in memory and start next queued task."""
        with self._lock:
            task = self._tasks.get(task_id)

        if task and task.status == "completed":
            try:
                from core.memory_store import get_store
                store = get_store()
                store.add(
                    content=f"Background task completed: {task.description[:200]}",
                    type="task",
                    source="hal",
                    metadata={
                        "task_id": task.id,
                        "duration_seconds": int((task.completed_at or 0) - (task.started_at or 0)),
                        "result_preview": (task.result or "")[:500],
                    },
                )
            except Exception:
                pass  # memory storage is best-effort

        self._try_start_next()
