#!/usr/bin/env python3
"""Compatibility wrapper for modules.step2_topic_planning.ai_client."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.step2_topic_planning.ai_client import *  # noqa: F401,F403
