"""Artifact tools — create and update visual artifacts in the workspace panel."""

import time
import uuid

from core.tools import tool


def _get_engine():
    """Get the HAL engine (lazy import to avoid circular)."""
    try:
        from server import engine
        return engine
    except Exception:
        return None


@tool(
    name="create_artifact",
    description=(
        "Create a visual artifact in HAL's workspace panel. "
        "Use for showing code, diagrams, documents, or rendered HTML. "
        "The artifact appears in a panel alongside the chat. "
        "Types: code, markdown, html, mermaid, json."
    ),
    safety="safe",
    params={
        "title": {
            "type": "string",
            "description": "Short title for the artifact",
        },
        "type": {
            "type": "string",
            "description": "Artifact type: code, markdown, html, mermaid, json",
            "enum": ["code", "markdown", "html", "mermaid", "json"],
        },
        "content": {
            "type": "string",
            "description": "The artifact content (code, markdown, HTML, etc.)",
        },
        "language": {
            "type": "string",
            "description": "Programming language for code artifacts (e.g. python, javascript)",
            "required": False,
        },
    },
)
def create_artifact(title: str, type: str, content: str, language: str = "") -> str:
    eng = _get_engine()
    if not eng:
        return "Artifact system not available. Is HAL running?"

    artifact = {
        "id": str(uuid.uuid4())[:8],
        "type": type,
        "title": title,
        "content": content,
        "language": language,
        "created_at": time.time(),
        "updated_at": time.time(),
    }

    with eng._artifact_lock:
        eng._artifacts.append(artifact)
        eng._artifact_version += 1

    return f"Artifact '{title}' created (id: {artifact['id']}, type: {type})"


@tool(
    name="update_artifact",
    description="Update the content of an existing artifact by its ID.",
    safety="safe",
    params={
        "artifact_id": {
            "type": "string",
            "description": "The artifact ID to update",
        },
        "content": {
            "type": "string",
            "description": "New content for the artifact",
        },
    },
)
def update_artifact(artifact_id: str, content: str) -> str:
    eng = _get_engine()
    if not eng:
        return "Artifact system not available."

    with eng._artifact_lock:
        for a in eng._artifacts:
            if a["id"] == artifact_id:
                a["content"] = content
                a["updated_at"] = time.time()
                eng._artifact_version += 1
                return f"Artifact '{a['title']}' updated."

    return f"Artifact {artifact_id} not found."
