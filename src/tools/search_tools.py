"""Search tools: full-text search across a project's items."""

import logging
from typing import Any, Dict, List, Optional

from src.session import execute_taiga_operation, resolve_client

logger = logging.getLogger(__name__)

# Result groups Taiga returns from GET /search, in the order we present them.
SEARCH_GROUPS = ("userstories", "tasks", "issues", "epics", "wikipages")
HIT_FIELDS = ("id", "ref", "subject", "slug", "status")


def _trim_hit(hit: Dict[str, Any]) -> Dict[str, Any]:
    """Keep only the fields needed to identify a hit and fetch it with another tool."""
    trimmed = {key: hit[key] for key in HIT_FIELDS if key in hit}
    status_info = hit.get("status_extra_info")
    if isinstance(status_info, dict) and status_info.get("name"):
        trimmed["status_name"] = status_info["name"]
    return trimmed


def search(
    project_id: int, text: str, session_id: Optional[str] = None
) -> Dict[str, Any]:
    """Searches user stories, tasks, issues, epics and wiki pages of a project by text."""
    query = (text or "").strip()
    if not query:
        raise ValueError("Search text cannot be empty.")
    logger.info(f"Executing search '{query}' in project {project_id}...")
    taiga_client_wrapper = resolve_client(session_id)
    result = execute_taiga_operation(
        "search",
        lambda: taiga_client_wrapper.api.get(
            "/search", params={"project": project_id, "text": query}
        ),
        f"project {project_id}",
    )
    raw = result or {}
    grouped: Dict[str, Any] = {}
    for group in SEARCH_GROUPS:
        hits: List[Dict[str, Any]] = raw.get(group) or []
        grouped[group] = [_trim_hit(hit) for hit in hits]
    grouped["count"] = raw.get("count", sum(len(v) for v in grouped.values()))
    return grouped


def register(mcp):
    mcp.tool(
        "search",
        description=(
            "Full-text search across a project's user stories, tasks, issues, epics and wiki "
            "pages. Returns hits grouped per type with id, ref (the #N number shown in Taiga) "
            "and subject; use get_<type> with the id or get_<type>_by_ref with the ref for "
            "details. Uses default session if session_id not provided."
        ),
    )(search)
