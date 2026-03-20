"""Compatibility exports for step1_material_analysis.indexer."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.step1_material_analysis.indexer.fingerprint import FingerprintDB, VideoHasher
from modules.step1_material_analysis.indexer.semantic import CLIPEncoder, SemanticIndex

__all__ = [
    "VideoHasher",
    "FingerprintDB",
    "CLIPEncoder",
    "SemanticIndex",
]
