#!/usr/bin/env python3
"""Compatibility wrapper for modules.step7_final_render.beauty."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.step7_final_render.beauty import *  # noqa: F401,F403
