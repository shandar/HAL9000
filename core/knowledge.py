"""
HAL9000 — Knowledge Loader
Reads local files from knowledge/ and fetches remote llms.txt URLs.
Combines everything into a single context string for HAL's brain.
"""

import os
import urllib.request
import urllib.error

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")
SOURCES_FILE = os.path.join(KNOWLEDGE_DIR, "sources.txt")
SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown"}
FETCH_TIMEOUT = 10  # seconds


def load_local_files() -> list[tuple[str, str]]:
    """Read all .md and .txt files from knowledge/ (excluding sources.txt)."""
    entries = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        return entries

    for filename in sorted(os.listdir(KNOWLEDGE_DIR)):
        if filename == "sources.txt":
            continue

        _, ext = os.path.splitext(filename)
        if ext.lower() not in SUPPORTED_EXTENSIONS:
            continue

        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                entries.append((filename, content))
                print(f"[Knowledge] Loaded: {filename} ({len(content)} chars)")
        except Exception as e:
            print(f"[Knowledge] Failed to read {filename}: {e}")

    return entries


def fetch_remote_sources() -> list[tuple[str, str]]:
    """Fetch llms.txt (or any text) from URLs listed in sources.txt."""
    entries = []
    if not os.path.isfile(SOURCES_FILE):
        return entries

    with open(SOURCES_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        url = line.strip()
        if not url or url.startswith("#"):
            continue

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "HAL9000-KnowledgeLoader/1.0"},
            )
            with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
                content = resp.read().decode("utf-8", errors="replace").strip()

            if content:
                # Use domain + path as label
                label = url.split("//", 1)[-1]
                entries.append((label, content))
                print(f"[Knowledge] Fetched: {label} ({len(content)} chars)")
        except (urllib.error.URLError, Exception) as e:
            print(f"[Knowledge] Failed to fetch {url}: {e}")

    return entries


def load_all() -> str:
    """Load all knowledge and return as a single formatted string."""
    local = load_local_files()
    remote = fetch_remote_sources()
    all_entries = local + remote

    if not all_entries:
        print("[Knowledge] No knowledge files found.")
        return ""

    sections = []
    for label, content in all_entries:
        sections.append(f"--- {label} ---\n{content}")

    combined = "\n\n".join(sections)
    print(f"[Knowledge] Total: {len(all_entries)} sources, {len(combined)} chars")
    return combined
