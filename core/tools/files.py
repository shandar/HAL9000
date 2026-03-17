"""File system tools."""

import datetime
import glob as glob_module
import os

from core.tools import tool, _human_size


@tool(
    name="list_files",
    description="List files and directories in a given path. Returns names with type indicators.",
    safety="safe",
    params={
        "path": {"type": "string", "description": "Directory path (supports ~)"},
    },
)
def list_files(path: str) -> str:
    expanded = os.path.expanduser(path)
    if not os.path.isdir(expanded):
        return f"Not a directory: {path}"

    entries = []
    try:
        for entry in sorted(os.listdir(expanded)):
            full = os.path.join(expanded, entry)
            if os.path.isdir(full):
                entries.append(f"  {entry}/")
            else:
                size = os.path.getsize(full)
                entries.append(f"  {entry}  ({_human_size(size)})")
    except PermissionError:
        return f"Permission denied: {path}"

    return f"{path}:\n" + "\n".join(entries[:100]) if entries else f"{path}: (empty)"


@tool(
    name="read_file",
    description="Read the text contents of a file. Returns first 10,000 characters.",
    safety="safe",
    params={
        "path": {"type": "string", "description": "File path (supports ~)"},
    },
)
def read_file(path: str) -> str:
    expanded = os.path.expanduser(path)

    # Block sensitive files
    basename = os.path.basename(expanded).lower()
    if basename in (".env", "credentials.json", ".npmrc", ".netrc"):
        return f"Blocked: '{basename}' may contain secrets"

    if not os.path.isfile(expanded):
        return f"File not found: {path}"

    try:
        with open(expanded, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(10000)
        if len(content) == 10000:
            content += "\n... (truncated at 10,000 chars)"
        return content
    except Exception as e:
        return f"Error reading {path}: {e}"


@tool(
    name="write_file",
    description="Write text content to a file. Creates the file if it doesn't exist, overwrites if it does.",
    safety="confirm",
    params={
        "path": {"type": "string", "description": "File path (supports ~)"},
        "content": {"type": "string", "description": "Text content to write"},
    },
)
def write_file(path: str, content: str) -> str:
    expanded = os.path.expanduser(path)
    try:
        os.makedirs(os.path.dirname(expanded), exist_ok=True)
        with open(expanded, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Written {len(content)} chars to {path}"
    except Exception as e:
        return f"Error writing {path}: {e}"


@tool(
    name="search_files",
    description="Search for files matching a glob pattern in a directory.",
    safety="safe",
    params={
        "path": {"type": "string", "description": "Directory to search in (supports ~)"},
        "pattern": {"type": "string", "description": "Glob pattern (e.g. '*.png', '**/*.js')"},
    },
)
def search_files(path: str, pattern: str) -> str:
    expanded = os.path.expanduser(path)
    full_pattern = os.path.join(expanded, pattern)
    matches = glob_module.glob(full_pattern, recursive=True)
    if not matches:
        return f"No files matching '{pattern}' in {path}"
    lines = [m.replace(expanded, ".") for m in sorted(matches)[:50]]
    return f"Found {len(matches)} files:\n" + "\n".join(lines)


@tool(
    name="file_info",
    description="Get detailed info about a file: size, creation date, modified date, type.",
    safety="safe",
    params={
        "path": {"type": "string", "description": "File path (supports ~)"},
    },
)
def file_info(path: str) -> str:
    expanded = os.path.expanduser(path)
    if not os.path.exists(expanded):
        return f"Not found: {path}"

    stat = os.stat(expanded)
    is_dir = os.path.isdir(expanded)
    created = getattr(stat, "st_birthtime", stat.st_ctime)
    return (
        f"Path: {path}\n"
        f"Type: {'directory' if is_dir else 'file'}\n"
        f"Size: {_human_size(stat.st_size)}\n"
        f"Modified: {datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()}\n"
        f"Created: {datetime.datetime.fromtimestamp(created).isoformat()}"
    )
