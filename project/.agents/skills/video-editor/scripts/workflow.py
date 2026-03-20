#!/usr/bin/env python3
"""Compatibility wrapper for modules.workflow_engine.workflow."""

from pathlib import Path
import runpy
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if __name__ == "__main__":
    target = REPO_ROOT / "modules" / "workflow_engine" / "workflow.py"
    runpy.run_path(str(target), run_name="__main__")
else:
    from modules.workflow_engine.workflow import *  # noqa: F401,F403
