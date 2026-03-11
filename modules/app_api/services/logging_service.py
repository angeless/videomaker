"""Centralized logging with persistent RotatingFileHandler.

Call ``init_logging()`` once at startup.  All existing modules that use
``logging.getLogger(__name__)`` will automatically write to the log file.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

_LOG_DIR_DEFAULT = Path(__file__).resolve().parents[3] / "logs"
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_initialized = False
_log_dir: Optional[Path] = None


def _resolve_log_dir(log_dir: str | Path | None) -> Path:
    if log_dir:
        return Path(log_dir).expanduser().resolve()
    env_dir = os.environ.get("VIDEOEDITOR_LOG_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return _LOG_DIR_DEFAULT


def init_logging(log_dir: str | Path | None = None, level: int = logging.INFO) -> Path:
    """Attach a RotatingFileHandler to the root logger (idempotent)."""
    global _initialized, _log_dir
    resolved = _resolve_log_dir(log_dir)
    if _initialized:
        return resolved
    resolved.mkdir(parents=True, exist_ok=True)
    log_file = resolved / "videoeditor.log"
    handler = RotatingFileHandler(
        str(log_file), maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.WARNING or root.level == 0:
        root.setLevel(level)
    _initialized = True
    _log_dir = resolved
    return resolved


def current_log_file() -> Optional[Path]:
    """Return the active log file path, or *None* if not initialised."""
    if not _initialized or _log_dir is None:
        return None
    return _log_dir / "videoeditor.log"
