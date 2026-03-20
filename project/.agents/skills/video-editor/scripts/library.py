#!/usr/bin/env python3
"""Compatibility wrapper for modules.library.global_media_library."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.library.global_media_library import *  # noqa: F401,F403
