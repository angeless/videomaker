"""4 read-only query tools for MCP (A4).

Tools: review_query_state, review_query_comments,
       review_query_diagnostics, review_query_versions.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict

from modules.mcp_server.health import DEFAULT_BACKEND_URL, check_backend_health

logger = logging.getLogger(__name__)


def _get(endpoint: str, base_url: str = DEFAULT_BACKEND_URL) -> Dict[str, Any]:
    healthy, msg = check_backend_health(base_url)
    if not healthy:
        return {"error": msg, "success": False}
    url = f"{base_url}{endpoint}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e), "success": False}


# ── Tool implementations ─────────────────────────────────────────


def review_query_state(session_id: str) -> Dict[str, Any]:
    """Get session metadata + current version (read-only)."""
    return _get(f"/api/review/{session_id}/state")


def review_query_comments(session_id: str) -> Dict[str, Any]:
    """Get all comments for a review session (read-only)."""
    return _get(f"/api/review/{session_id}/comments")


def review_query_diagnostics(session_id: str) -> Dict[str, Any]:
    """Get VLM diagnostics results for a session (read-only)."""
    return _get(f"/api/review/{session_id}/vlm/diagnostics")


def review_query_versions(session_id: str) -> Dict[str, Any]:
    """Get version history for a session (read-only)."""
    return _get(f"/api/review/{session_id}/versions")
