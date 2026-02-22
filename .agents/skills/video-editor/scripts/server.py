#!/usr/bin/env python3
"""Compatibility wrapper for modules.app_api.server."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.app_api.server import *  # noqa: F401,F403
