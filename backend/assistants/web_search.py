"""web_search tool backed by Ollama Cloud's web search API (ADR-0011).

For the rule-draft assistant the tool is generic and unguarded. For the incident
assistant a PAP guard is injected so PAP:RED blocks incident-specific queries.
The actual search call is injectable (`search_fn`) so the orchestrator/tool tests
never hit the network.
"""
import logging

from django.conf import settings

from .tools import ToolResult, ToolSpec

logger = logging.getLogger(__name__)

WEB_SEARCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "What to search the public internet for (e.g. an IOC, CVE, "
                           "malware family, or how a Wazuh rule manifests).",
        },
    },
    "required": ["query"],
}

_DESCRIPTION = (
    "Search the public internet for threat intelligence — IOC/CVE reputation, malware "
    "behaviour, how a detection rule manifests. Returns titles, URLs, and snippets."
)


def web_search_available() -> bool:
    """True when a web-search backend is configured (Ollama Cloud key present)."""
    return bool(
        getattr(settings, "ASSISTANT_WEB_SEARCH_ENABLED", True)
        and getattr(settings, "OLLAMA_API_KEY", "")
    )


def _ollama_web_search(query: str, max_results: int = 5) -> list:
    """Call Ollama Cloud's web search and normalise to [{title, url, content}]."""
    import ollama

    client = ollama.Client(
        host=getattr(settings, "OLLAMA_BASE_URL", ""),
        headers={"Authorization": f"Bearer {getattr(settings, 'OLLAMA_API_KEY', '')}"},
        timeout=getattr(settings, "OLLAMA_TIMEOUT_S", 60.0),
    )
    try:
        resp = client.web_search(query=query, max_results=max_results)
    except TypeError:
        # older/newer SDKs may not accept max_results
        resp = client.web_search(query)
    raw = getattr(resp, "results", None)
    if raw is None and isinstance(resp, dict):
        raw = resp.get("results", [])
    results = []
    for r in raw or []:
        get = r.get if isinstance(r, dict) else lambda k, d=None: getattr(r, k, d)
        results.append({
            "title": get("title", ""),
            "url": get("url", ""),
            "content": get("content", "") or get("snippet", ""),
        })
    return results


def build_web_search_tool(guard=None, search_fn=None) -> ToolSpec:
    """Build the web_search ToolSpec.

    guard:      optional callable(query) -> (allowed: bool, reason: str), used by the
                incident assistant for PAP:RED enforcement.
    search_fn:  optional callable(query) -> list[result]; defaults to Ollama Cloud.
    """
    search = search_fn or _ollama_web_search

    def executor(args: dict) -> ToolResult:
        query = ((args or {}).get("query") or "").strip()
        if not query:
            return ToolResult(error="empty query", summary="empty query")
        if guard is not None:
            allowed, reason = guard(query)
            if not allowed:
                return ToolResult(error=reason, summary="blocked (PAP:RED)")
        try:
            results = search(query)
        except Exception as exc:
            logger.warning("web_search failed: %s", exc)
            return ToolResult(error=f"web search failed: {exc}", summary="search failed")
        return ToolResult(
            content=results,
            summary=f"web search '{query[:60]}': {len(results)} results",
            count=len(results),
        )

    return ToolSpec(
        name="web_search",
        description=_DESCRIPTION,
        parameters=WEB_SEARCH_PARAMETERS,
        executor=executor,
    )
