"""3 VLM tools for MCP (A2).

Tools: vlm_describe_region, vlm_diagnose_frame, vlm_status.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

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


# ── Tool implementations ─────────────────────────────────────────


def vlm_describe_region(
    session_id: str,
    frame_base64: str,
    strokes: List[Dict[str, Any]],
    timestamp_ms: int = 0,
) -> Dict[str, Any]:
    """Analyze a brush-selected region using VLM.

    Args:
        session_id: Review session ID.
        frame_base64: Base64-encoded frame image (max 10MB).
        strokes: List of brush stroke dicts (tool, points, etc.).
        timestamp_ms: Frame timestamp in milliseconds.
    """
    return _post(f"/api/review/{session_id}/vlm/describe", {
        "frame_base64": frame_base64,
        "strokes": strokes,
        "timestamp_ms": timestamp_ms,
    })


def vlm_diagnose_frame(
    session_id: str,
    frame_base64: str,
    timestamp_ms: int = 0,
) -> Dict[str, Any]:
    """Run frame diagnostics (composition, exposure, color temp).

    Synchronous — returns diagnostic results directly.
    """
    return _post(f"/api/review/{session_id}/vlm/diagnose", {
        "frame_base64": frame_base64,
        "timestamp_ms": timestamp_ms,
    })


def vlm_status() -> Dict[str, Any]:
    """Check VLM availability and provider status."""
    return _get("/api/vlm/status")
