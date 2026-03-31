"""FCPXML 1.9 schema constants for Final Cut Pro export."""

FCPXML_VERSION = "1.9"
FCPXML_DOCTYPE = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n'

DEFAULT_FPS_TIMEBASE = "30/1s"  # 30fps
DEFAULT_FORMAT_NAME = "FFVideoFormat1080p30"


def ms_to_cmtime(ms: int, fps: int = 30) -> str:
    """Convert milliseconds to CMTime rational string (e.g. '3000/1000s')."""
    return f"{ms}/1000s"


def duration_cmtime(start_ms: int, end_ms: int) -> str:
    """Duration as CMTime."""
    return ms_to_cmtime(max(0, end_ms - start_ms))
