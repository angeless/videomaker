"""Health check for VideoEditor backend."""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)

DEFAULT_BACKEND_URL = "http://127.0.0.1:9876"


def check_backend_health(base_url: str = DEFAULT_BACKEND_URL) -> Tuple[bool, str]:
    """Check if the VideoEditor backend is reachable.

    Returns:
        (is_healthy, message)
    """
    try:
        import urllib.request
        url = f"{base_url}/api/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                return True, "Backend is healthy"
            return False, f"Backend returned status {resp.status}"
    except Exception as e:
        return False, (
            f"Backend offline ({e}). "
            f"Start it with: python3 -m apps.desktop.launcher "
            f"or cd project && python3 apps/desktop/launcher.py"
        )
