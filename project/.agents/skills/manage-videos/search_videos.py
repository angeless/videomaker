#!/usr/bin/env python3
"""Compatibility wrapper for modules.step4_material_matching.search_videos."""

from pathlib import Path
import runpy
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if __name__ == "__main__":
    target = REPO_ROOT / "modules" / "step4_material_matching" / "search_videos.py"
    runpy.run_path(str(target), run_name="__main__")
else:
    from modules.step4_material_matching.search_videos import *  # noqa: F401,F403
