"""Security utilities for MCP Server — path whitelist, traversal prevention."""

import os
from pathlib import Path
from typing import List

ALLOWED_WRITE_DIRS: List[str] = [
    str(Path.home() / "Movies" / "VideoEditor" / "exports"),
    str(Path("/tmp").resolve()),
]


def is_safe_write_path(path_str: str) -> bool:
    """Check if a write path is within the allowed whitelist."""
    try:
        resolved = str(Path(path_str).expanduser().resolve())
    except (ValueError, OSError):
        return False
    return any(
        resolved == prefix or resolved.startswith(prefix + os.sep)
        for prefix in ALLOWED_WRITE_DIRS
    )


def is_path_traversal(path_str: str) -> bool:
    """Detect path traversal attempts (.. in path)."""
    return ".." in path_str


def validate_source_path(source_path: str) -> str:
    """Validate a source path for ingest operations. Returns error message or empty string."""
    if not source_path:
        return "source_path is required"
    if is_path_traversal(source_path):
        return f"Path traversal detected in source_path: {source_path}"
    resolved = Path(source_path).expanduser().resolve()
    if not resolved.exists():
        return f"Path does not exist: {source_path}"
    return ""
