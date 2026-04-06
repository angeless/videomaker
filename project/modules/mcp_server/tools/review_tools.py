"""6 review operation tools for MCP (A1).

Tools: review_init, review_add_comment, review_resolve_comment,
       review_ai_reedit, review_ai_reedit_dry_run, review_export_comments.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from modules.mcp_server.health import DEFAULT_BACKEND_URL, check_backend_health

logger = logging.getLogger(__name__)


def _post(endpoint: str, payload: Dict[str, Any],
          base_url: str = DEFAULT_BACKEND_URL) -> Dict[str, Any]:
    healthy, msg = check_backend_health(base_url)
    if not healthy:
        return {"error": msg, "success": False}
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


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


def _patch(endpoint: str, payload: Dict[str, Any],
           base_url: str = DEFAULT_BACKEND_URL) -> Dict[str, Any]:
    healthy, msg = check_backend_health(base_url)
    if not healthy:
        return {"error": msg, "success": False}
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}, method="PATCH",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


# ── Tool implementations ─────────────────────────────────────────


def review_init(project_dir: str, video_path: str) -> Dict[str, Any]:
    """Create a review session for a video project.

    Returns session_id on success.
    """
    return _post("/api/review/init", {
        "project_dir": project_dir,
        "video_path": video_path,
    })


def review_add_comment(
    session_id: str,
    text: str,
    timestamp_ms: int = 0,
    visual_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add a comment to a review session.

    Args:
        session_id: Review session ID.
        text: Comment text.
        timestamp_ms: Video timestamp in milliseconds.
        visual_context: Optional VLM visual context dict.
    """
    payload: Dict[str, Any] = {
        "text": text,
        "timestamp_ms": timestamp_ms,
    }
    if visual_context is not None:
        payload["visual_context"] = visual_context
    return _post(f"/api/review/{session_id}/comments", payload)


def review_resolve_comment(comment_id: str) -> Dict[str, Any]:
    """Mark a comment as resolved."""
    return _patch(f"/api/review/comments/{comment_id}", {"resolved": True})


def review_ai_reedit(session_id: str) -> Dict[str, Any]:
    """Trigger AI re-edit based on review comments."""
    return _post(f"/api/review/{session_id}/ai-reedit", {})


def review_ai_reedit_dry_run(session_id: str) -> Dict[str, Any]:
    """Preview AI re-edit changes without applying (dry-run)."""
    return _post(f"/api/review/{session_id}/ai-reedit/dry-run", {})


def review_export_comments(session_id: str) -> Dict[str, Any]:
    """Export all comments from a review session."""
    return _get(f"/api/review/{session_id}/comments/export")
