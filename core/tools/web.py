"""Web search & URL fetching tools."""

import urllib.request
import urllib.error

from core.tools import tool


@tool(
    name="web_search",
    description="Search the web and return top results. Use for any question about current events, weather, facts, etc.",
    safety="safe",
    params={
        "query": {"type": "string", "description": "Search query"},
    },
)
def web_search(query: str) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            return f"No results found for: {query}"
        lines = []
        for r in results:
            lines.append(f"- {r['title']}: {r['body'][:200]}")
        return "\n".join(lines)
    except ImportError:
        return "Web search not available — install duckduckgo-search package"
    except Exception as e:
        return f"Search error: {e}"


@tool(
    name="fetch_url",
    description="Fetch a webpage and return its text content (first 8000 chars). Good for reading articles or documentation.",
    safety="safe",
    params={
        "url": {"type": "string", "description": "URL to fetch"},
    },
)
def fetch_url(url: str) -> str:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "HAL9000/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        import re
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000]
    except Exception as e:
        return f"Error fetching {url}: {e}"
