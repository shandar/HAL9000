"""HAL9000 — Knowledge Upload & Recall Tools"""

from core.tools import tool


@tool(
    name="learn_recall",
    description=(
        "Search HAL's uploaded knowledge files for information relevant to a query. "
        "Returns the most relevant text chunks from uploaded documents. "
        "Use this when the user asks about something that might be in their uploaded files."
    ),
    safety="safe",
    params={
        "query": {
            "type": "string",
            "description": "Search query — keywords or a question about the uploaded knowledge",
        },
    },
)
def learn_recall(query: str) -> str:
    from core.knowledge import recall

    results = recall(query)
    if not results:
        return "No relevant knowledge found. The user may not have uploaded files about this topic."

    lines = []
    for r in results:
        lines.append(f"[{r['file_name']}] (relevance: {r['score']})")
        lines.append(r["text"][:1000])
        lines.append("")

    return "\n".join(lines)


@tool(
    name="learn_list",
    description="List all knowledge files the user has uploaded to HAL.",
    safety="safe",
    params={},
)
def learn_list() -> str:
    from core.knowledge import list_uploads, get_storage_info

    uploads = list_uploads()
    if not uploads:
        return "No knowledge files uploaded yet. Drag and drop files onto the chat to teach me."

    info = get_storage_info()
    lines = [f"Knowledge files ({info['file_count']} files, {info['used_mb']} MB / {info['max_mb']} MB):"]
    for u in uploads:
        mode_tag = "always" if u["mode"] == "always" else f"{u.get('chunks', 0)} chunks"
        lines.append(f"  [{u['id']}] {u['name']} — {u['size_kb']} KB ({mode_tag})")

    return "\n".join(lines)


@tool(
    name="learn_forget",
    description="Delete an uploaded knowledge file by its ID. Use learn_list to find IDs.",
    safety="confirm",
    params={
        "file_id": {
            "type": "string",
            "description": "The ID of the knowledge file to delete (from learn_list output)",
        },
    },
)
def learn_forget(file_id: str) -> str:
    from core.knowledge import delete_upload

    if delete_upload(file_id):
        return f"Knowledge file {file_id} deleted."
    return f"Knowledge file {file_id} not found."
