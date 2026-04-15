"""5 capability tools: library search, ingest, project list/create, workflow run."""

import json
import logging
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, List, Optional

from modules.mcp_server.health import DEFAULT_BACKEND_URL, check_backend_health
from modules.mcp_server.security import is_path_traversal, validate_source_path

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


def _post(endpoint: str, payload: Dict[str, Any], base_url: str = DEFAULT_BACKEND_URL) -> Dict[str, Any]:
    healthy, msg = check_backend_health(base_url)
    if not healthy:
        return {"error": msg, "success": False}
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


def library_search(query: str, top_k: int = 10, mode: str = "hybrid") -> Dict[str, Any]:
    """Search the video library by semantic query."""
    top_k = max(1, min(top_k, 1000))
    if mode not in ("hybrid", "semantic", "keyword"):
        mode = "hybrid"
    # Fix: `urllib.request.quote` does NOT exist — `quote` lives in
    # `urllib.parse`. The previous typo caused AttributeError on every
    # call; the bare `except Exception` in _get silently returned
    # {"error": ..., "success": False}, hiding the fact that library
    # search has been broken since this MCP tool shipped.
    return _get(f"/api/library/search?q={urllib.parse.quote(query, safe='')}&top_k={top_k}&mode={mode}")


def library_ingest(source_path: str, recursive: bool = True) -> Dict[str, Any]:
    """Ingest local video files into the library.

    Security: source_path must not contain '..' traversal.
    """
    err = validate_source_path(source_path)
    if err:
        return {"error": f"Permission denied: {err}", "success": False}
    return _post("/api/library/ingest/local", {"source_path": source_path, "recursive": recursive})


def project_list() -> Dict[str, Any]:
    """List all projects."""
    return _get("/api/projects")


def project_create(name: str, source_dir: str) -> Dict[str, Any]:
    """Create a new project from a source directory."""
    # Match the validation library_ingest uses (existence + traversal check),
    # instead of the weaker traversal-substring-only check — otherwise
    # absolute paths like "/etc" are accepted here but rejected there.
    err = validate_source_path(source_dir)
    if err:
        return {"error": f"Permission denied: {err}", "success": False}
    return _post("/api/projects", {"name": name, "source_dir": source_dir})


def workflow_run(workflow_id: str, project_dir: str, config: Optional[Dict] = None) -> Dict[str, Any]:
    """Run a custom workflow."""
    payload: Dict[str, Any] = {"workflow_id": workflow_id, "project_dir": project_dir}
    if config:
        payload["config"] = config
    return _post("/api/workflows/run", payload)
