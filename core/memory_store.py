"""
HAL9000 — Typed Memory Store
Persistent, typed memory with auto-migration from legacy flat format.

Memory types:
    fact             — General knowledge (user prefs, names, etc.)
    decision         — Architectural/design decisions made during work
    task             — Completed task records from background runs
    session_summary  — Auto-generated session wrap-ups
    preference       — User preferences for behavior/tools/workflow
"""

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory")
MEMORY_FILE = os.path.join(MEMORY_DIR, "facts.json")

VALID_TYPES = {"fact", "decision", "task", "session_summary", "preference"}
VALID_SOURCES = {"hal", "claude_code", "claude_desktop", "user"}


@dataclass
class MemoryEntry:
    id: str
    type: str
    content: str
    timestamp: str
    source: str = "hal"
    session_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)


class MemoryStore:
    """Thread-safe typed memory store with auto-migration."""

    def __init__(self):
        self._entries: list[MemoryEntry] = []
        self._lock = threading.Lock()
        self._load()

    # ── Persistence ───────────────────────────────────────

    def _load(self):
        """Load from disk, auto-migrating legacy entries."""
        if not os.path.isfile(MEMORY_FILE):
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        for raw in raw_list:
            self._entries.append(self._migrate(raw))

    def _migrate(self, raw: dict) -> MemoryEntry:
        """Convert old {fact, timestamp} format to new typed format."""
        if "fact" in raw and "type" not in raw:
            return MemoryEntry(
                id=str(uuid.uuid4()),
                type="fact",
                content=raw["fact"],
                timestamp=raw.get("timestamp", datetime.now().isoformat()),
                source="hal",
            )
        # Already new format
        return MemoryEntry(
            id=raw.get("id", str(uuid.uuid4())),
            type=raw.get("type", "fact"),
            content=raw.get("content", ""),
            timestamp=raw.get("timestamp", datetime.now().isoformat()),
            source=raw.get("source", "hal"),
            session_id=raw.get("session_id"),
            metadata=raw.get("metadata", {}),
        )

    def _save(self):
        """Persist to disk. Caller must hold self._lock."""
        os.makedirs(MEMORY_DIR, exist_ok=True)
        data = [asdict(e) for e in self._entries]
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    # ── Public API ────────────────────────────────────────

    def add(
        self,
        content: str,
        type: str = "fact",
        source: str = "hal",
        session_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> MemoryEntry:
        """Store a new memory entry."""
        try:
            from core.license import get_license
            lic = get_license()
            if lic.max_memories != -1 and self.count() >= lic.max_memories:
                raise RuntimeError(
                    f"Memory limit reached ({lic.max_memories}). "
                    f"Upgrade to HAL Pro for unlimited memory at hal9000.dev"
                )
        except ImportError:
            pass

        entry = MemoryEntry(
            id=str(uuid.uuid4()),
            type=type if type in VALID_TYPES else "fact",
            content=content,
            timestamp=datetime.now().isoformat(),
            source=source if source in VALID_SOURCES else "hal",
            session_id=session_id,
            metadata=metadata or {},
        )
        with self._lock:
            self._entries.append(entry)
            self._save()
        return entry

    def search(self, query: str, type: Optional[str] = None) -> list[MemoryEntry]:
        """Search memories by substring, optionally filtered by type."""
        q = query.lower()
        with self._lock:
            results = []
            for e in self._entries:
                if type and e.type != type:
                    continue
                if q in e.content.lower():
                    results.append(e)
            return results

    def remove(self, query: str) -> int:
        """Remove all memories whose content matches the query substring."""
        q = query.lower()
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if q not in e.content.lower()]
            removed = before - len(self._entries)
            if removed:
                self._save()
            return removed

    def list_all(self, type: Optional[str] = None) -> list[MemoryEntry]:
        """List all memories, optionally filtered by type."""
        with self._lock:
            if type:
                return [e for e in self._entries if e.type == type]
            return list(self._entries)

    def get_session_summaries(self, limit: int = 5) -> list[MemoryEntry]:
        """Return the most recent session summaries."""
        with self._lock:
            summaries = [e for e in self._entries if e.type == "session_summary"]
            return summaries[-limit:]

    def count(self, type: Optional[str] = None) -> int:
        """Count entries, optionally by type."""
        with self._lock:
            if type:
                return sum(1 for e in self._entries if e.type == type)
            return len(self._entries)

    # ── Legacy compatibility ──────────────────────────────

    def to_legacy_list(self) -> list[dict]:
        """Return entries in old {fact, timestamp} format for brain prompt."""
        with self._lock:
            return [{"fact": e.content, "timestamp": e.timestamp} for e in self._entries]


# ── Singleton ─────────────────────────────────────────────

_store: Optional[MemoryStore] = None
_store_lock = threading.Lock()


def get_store() -> MemoryStore:
    """Get the shared MemoryStore singleton."""
    global _store
    if _store is not None:
        return _store
    with _store_lock:
        if _store is not None:
            return _store
        _store = MemoryStore()
        return _store
