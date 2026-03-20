"""Minimal Flask server launcher for Playwright E2E tests.

Starts the Flask app on port 9527 with security checks disabled,
so Playwright tests can call /api endpoints without token negotiation.
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.app_api.server import create_app

app = create_app()

# Disable security for E2E tests — no token / CSRF required
import modules.app_api.server as server
server._REQUIRE_LOCAL_API_TOKEN = False
server._REQUIRE_CSRF_PROTECTION = False

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=9527, debug=False, use_reloader=False)
