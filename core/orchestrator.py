"""
HAL9000 — Multi-Agent Orchestrator
Coordinates multiple Claude Code instances working on parallel tasks.

Each "agent" is a named background task that HAL can spawn, monitor,
and check for file conflicts when they complete.
"""

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from core.task_runner import TaskRunner


@dataclass
class Agent:
    id: str
    name: str  # e.g. "frontend", "backend", "tests"
    task: str
    working_directory: str
    status: str  # idle | working | completed | failed | cancelled | conflict
    task_id: str = ""  # linked TaskRunner task ID
    files_touched: list[str] = field(default_factory=list)
    result_preview: str = ""
    started_at: float = 0.0
    completed_at: float = 0.0


class Orchestrator:
    """Coordinates multiple Claude Code agents on parallel tasks."""

    def __init__(self, task_runner: TaskRunner):
        self._agents: dict[str, Agent] = {}
        self._task_runner = task_runner
        self._lock = threading.Lock()

    def spawn_agent(self, name: str, task: str, cwd: str = "") -> Agent:
        """Spawn a named agent to work on a task."""
        agent = Agent(
            id=str(uuid.uuid4())[:8],
            name=name,
            task=task,
            working_directory=cwd,
            status="working",
            started_at=time.time(),
        )

        # Submit to task runner
        bg_task = self._task_runner.submit(task, cwd)
        agent.task_id = bg_task.id

        with self._lock:
            self._agents[agent.id] = agent

        # Monitor completion in background
        thread = threading.Thread(
            target=self._monitor, args=(agent.id,), daemon=True
        )
        thread.start()

        return agent

    def _monitor(self, agent_id: str):
        """Poll the task runner until the agent's task completes."""
        with self._lock:
            agent = self._agents.get(agent_id)
        if not agent:
            return

        while True:
            bg_task = self._task_runner.get_task(agent.task_id)
            if not bg_task:
                break

            if bg_task.status in ("completed", "failed", "cancelled"):
                with self._lock:
                    agent.status = bg_task.status
                    agent.completed_at = time.time()
                    agent.result_preview = (bg_task.result or bg_task.error or "")[:500]

                    # Extract file paths from result (best-effort)
                    if bg_task.result:
                        agent.files_touched = self._extract_files(bg_task.result)
                break

            # Update progress
            with self._lock:
                if bg_task.progress:
                    agent.result_preview = bg_task.progress[:200]

            time.sleep(2)

    @staticmethod
    def _extract_files(output: str) -> list[str]:
        """Best-effort extraction of file paths from Claude Code output."""
        import re
        # Match common file path patterns
        paths = re.findall(r'(?:^|\s)([/.][\w./-]+\.[\w]+)', output)
        # Deduplicate and limit
        seen = set()
        unique = []
        for p in paths:
            if p not in seen:
                seen.add(p)
                unique.append(p)
            if len(unique) >= 20:
                break
        return unique

    def list_agents(self) -> list[dict]:
        """List all agents with status."""
        with self._lock:
            agents = list(self._agents.values())
        order = {"working": 0, "completed": 1, "failed": 2, "conflict": 3, "cancelled": 4}
        agents.sort(key=lambda a: (order.get(a.status, 5), -a.started_at))
        return [asdict(a) for a in agents]

    def check_conflicts(self) -> list[dict]:
        """Detect if multiple agents modified the same file."""
        with self._lock:
            completed = [a for a in self._agents.values() if a.files_touched]

        conflicts = []
        seen_files: dict[str, list[str]] = {}  # file -> [agent names]

        for agent in completed:
            for f in agent.files_touched:
                seen_files.setdefault(f, []).append(agent.name)

        for filepath, agent_names in seen_files.items():
            if len(agent_names) > 1:
                conflicts.append({
                    "file": filepath,
                    "agents": agent_names,
                })

        # Mark conflicting agents
        if conflicts:
            conflict_agents = set()
            for c in conflicts:
                conflict_agents.update(c["agents"])
            with self._lock:
                for a in self._agents.values():
                    if a.name in conflict_agents and a.status == "completed":
                        a.status = "conflict"

        return conflicts

    def merge_results(self) -> str:
        """Summarize all agent outputs and flag conflicts."""
        agents = self.list_agents()
        conflicts = self.check_conflicts()

        lines = ["=== Agent Orchestration Summary ===\n"]
        for a in agents:
            elapsed = ""
            if a["started_at"]:
                end = a["completed_at"] or time.time()
                elapsed = f" ({int(end - a['started_at'])}s)"
            lines.append(f"[{a['status']}] {a['name']}: {a['task'][:80]}{elapsed}")
            if a["files_touched"]:
                lines.append(f"  Files: {', '.join(a['files_touched'][:5])}")
            if a["result_preview"]:
                lines.append(f"  Result: {a['result_preview'][:200]}")

        if conflicts:
            lines.append("\n⚠ FILE CONFLICTS:")
            for c in conflicts:
                lines.append(f"  {c['file']} — modified by: {', '.join(c['agents'])}")

        return "\n".join(lines)

    def cancel_agent(self, agent_id: str) -> bool:
        """Cancel an agent and its background task."""
        with self._lock:
            agent = self._agents.get(agent_id)
        if not agent:
            return False

        if agent.task_id:
            self._task_runner.cancel(agent.task_id)

        with self._lock:
            agent.status = "cancelled"
            agent.completed_at = time.time()
        return True

    def get_agent(self, agent_id: str) -> Optional[dict]:
        """Get a single agent by ID."""
        with self._lock:
            agent = self._agents.get(agent_id)
            return asdict(agent) if agent else None
