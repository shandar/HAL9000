"""Persistent memory tools — remember, recall, forget, list."""

import datetime

from core.tools import tool, _load_memories, _save_memories


@tool(
    name="remember",
    description="Store a fact in persistent memory. HAL will remember this across sessions.",
    safety="safe",
    params={
        "fact": {"type": "string", "description": "The fact or information to remember"},
    },
)
def remember(fact: str) -> str:
    memories = _load_memories()
    entry = {
        "fact": fact,
        "timestamp": datetime.datetime.now().isoformat(),
    }
    memories.append(entry)
    _save_memories(memories)
    return f"Remembered: {fact}"


@tool(
    name="recall",
    description="Search persistent memory for facts matching a query.",
    safety="safe",
    params={
        "query": {"type": "string", "description": "What to search for in memory"},
    },
)
def recall(query: str) -> str:
    memories = _load_memories()
    if not memories:
        return "No memories stored yet."

    query_lower = query.lower()
    matches = [m for m in memories if query_lower in m["fact"].lower()]
    if not matches:
        return f"No memories matching '{query}'"

    lines = [f"- {m['fact']} (saved {m['timestamp'][:10]})" for m in matches]
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
    memories = _load_memories()
    query_lower = query.lower()
    before = len(memories)
    memories = [m for m in memories if query_lower not in m["fact"].lower()]
    removed = before - len(memories)
    _save_memories(memories)
    return f"Removed {removed} memories matching '{query}'" if removed else f"No memories matching '{query}'"


@tool(
    name="list_memories",
    description="List all facts stored in persistent memory.",
    safety="safe",
    params={},
)
def list_memories() -> str:
    memories = _load_memories()
    if not memories:
        return "No memories stored yet."

    lines = [f"- {m['fact']}" for m in memories]
    return f"{len(memories)} memories:\n" + "\n".join(lines)
