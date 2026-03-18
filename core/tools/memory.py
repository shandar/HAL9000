"""Persistent memory tools — remember, recall, forget, list, save_session."""

from core.memory_store import get_store
from core.tools import tool

# Engine reference — set by server.py at startup to avoid circular import
_engine_ref = None


def set_engine(engine):
    """Called by server.py to provide the engine reference."""
    global _engine_ref
    _engine_ref = engine


@tool(
    name="remember",
    description=(
        "Store a fact in persistent memory. HAL will remember this across sessions. "
        "Optionally specify a type: fact, decision, preference."
    ),
    safety="safe",
    params={
        "fact": {"type": "string", "description": "The fact or information to remember"},
        "type": {
            "type": "string",
            "description": "Memory type: fact (default), decision, or preference",
            "required": False,
            "enum": ["fact", "decision", "preference"],
        },
    },
)
def remember(fact: str, type: str = "fact") -> str:
    store = get_store()
    entry = store.add(content=fact, type=type, source="hal")
    return f"Remembered ({entry.type}): {fact}"


@tool(
    name="recall",
    description=(
        "Search persistent memory for facts matching a query. "
        "Optionally filter by memory type."
    ),
    safety="safe",
    params={
        "query": {"type": "string", "description": "What to search for in memory"},
        "type": {
            "type": "string",
            "description": "Filter by type: fact, decision, preference, task, session_summary",
            "required": False,
            "enum": ["fact", "decision", "preference", "task", "session_summary"],
        },
    },
)
def recall(query: str, type: str = "") -> str:
    store = get_store()
    matches = store.search(query, type=type or None)
    if not matches:
        return f"No memories matching '{query}'" + (f" (type={type})" if type else "")

    lines = [f"- [{m.type}] {m.content} (saved {m.timestamp[:10]})" for m in matches]
    return f"Found {len(matches)} memories:\n" + "\n".join(lines)


@tool(
    name="forget",
    description="Remove a fact from persistent memory by searching for a keyword.",
    safety="confirm",
    params={
        "query": {"type": "string", "description": "Keyword to match — removes all matching memories"},
    },
)
def forget(query: str) -> str:
    store = get_store()
    removed = store.remove(query)
    return f"Removed {removed} memories matching '{query}'" if removed else f"No memories matching '{query}'"


@tool(
    name="list_memories",
    description="List all facts stored in persistent memory, optionally filtered by type.",
    safety="safe",
    params={
        "type": {
            "type": "string",
            "description": "Filter by type: fact, decision, preference, task, session_summary",
            "required": False,
            "enum": ["fact", "decision", "preference", "task", "session_summary"],
        },
    },
)
def list_memories(type: str = "") -> str:
    store = get_store()
    entries = store.list_all(type=type or None)
    if not entries:
        return "No memories stored yet." + (f" (type={type})" if type else "")

    lines = [f"- [{m.type}] {m.content}" for m in entries]
    return f"{len(entries)} memories:\n" + "\n".join(lines)


@tool(
    name="save_session",
    description=(
        "Manually save the current session context. Use this when the user says "
        "'wrap up', 'save context', or 'save session'. Captures what was discussed "
        "and what tools were used."
    ),
    safety="safe",
    params={},
)
def save_session() -> str:
    if not _engine_ref:
        return "Session save not available. Is HAL running?"
    try:
        result = _engine_ref.summarize_session()
        return f"Session saved: {result['summary']}"
    except Exception as e:
        return f"Could not save session: {e}"
