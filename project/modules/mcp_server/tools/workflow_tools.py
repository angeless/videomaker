"""7 workflow tools mapping to VideoEditor's 7-step pipeline."""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict

from modules.mcp_server.health import DEFAULT_BACKEND_URL, check_backend_health

logger = logging.getLogger(__name__)

STEP_MAP = {
    "video_step1_analyze": "analyze_materials",
    "video_step2_plan": "topic_planning",
    "video_step3_script": "script_generation",
    "video_step4_match": "material_matching",
    "video_step5_preview": "frame_preview",
    "video_step6_cut": "rough_cut",
    "video_step7_render": "final_render",
}


def _call_backend(endpoint: str, payload: Dict[str, Any], base_url: str = DEFAULT_BACKEND_URL) -> Dict[str, Any]:
    """Call the VideoEditor backend API."""
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


def run_workflow_step(tool_name: str, project_dir: str, config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run a workflow step via the backend API.

    Args:
        tool_name: One of the 7 step tool names (video_step1_analyze, etc.)
        project_dir: Path to the project directory
        config: Optional config overrides for the step
    """
    task_type = STEP_MAP.get(tool_name)
    if not task_type:
        return {"error": f"Unknown tool: {tool_name}. Available: {list(STEP_MAP.keys())}"}

    payload = {"task_type": task_type, "project_dir": project_dir}
    if config:
        payload["config"] = config

    return _call_backend("/api/agent/tasks/run", payload)
