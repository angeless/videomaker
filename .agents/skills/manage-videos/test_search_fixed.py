#!/usr/bin/env python3
"""Compatibility wrapper for modules/legacy_lab/manage_videos/tests/test_search_fixed.py."""

from pathlib import Path
import runpy
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if __name__ == "__main__":
    target = REPO_ROOT / "modules/legacy_lab/manage_videos/tests/test_search_fixed.py"
    runpy.run_path(str(target), run_name="__main__")
else:
    import importlib.util

    target = REPO_ROOT / "modules/legacy_lab/manage_videos/tests/test_search_fixed.py"
    spec = importlib.util.spec_from_file_location("legacy_wrapper", str(target))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    for name in dir(module):
        if not name.startswith("_"):
            globals()[name] = getattr(module, name)
