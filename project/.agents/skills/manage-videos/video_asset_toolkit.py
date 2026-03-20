#!/usr/bin/env python3
"""Compatibility wrapper for step1_material_analysis.video_asset_toolkit."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.step1_material_analysis.video_asset_toolkit import *  # noqa: F401,F403
