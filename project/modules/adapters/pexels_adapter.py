"""Pexels stock media API adapter.

All Pexels API calls go through this adapter. The review_engine module
must not import the Pexels SDK directly.

Implementation deferred to v0.16.0 R18.
"""

import os
from typing import Dict, List, Optional


PEXELS_API_KEY_ENV = "VIDEOEDITOR_PEXELS_API_KEY"


def get_api_key() -> Optional[str]:
    """Return the Pexels API key from environment, or None."""
    return os.environ.get(PEXELS_API_KEY_ENV)


def search_videos(
    query: str,
    per_page: int = 10,
    orientation: Optional[str] = None,
    min_duration: Optional[int] = None,
    max_duration: Optional[int] = None,
) -> Dict:
    """Search Pexels for stock videos.

    Args:
        query: Search keywords.
        per_page: Results per page (max 80).
        orientation: "landscape", "portrait", or "square".
        min_duration: Minimum duration in seconds.
        max_duration: Maximum duration in seconds.

    Returns:
        Dict with keys: results (list), total_results (int), page (int).

    Raises:
        modules.review_engine.exceptions.StockMediaError: On API failure.
    """
    raise NotImplementedError("Pexels adapter: implementation in v0.16.0")


def download_video(video_id: str, output_dir: str, quality: str = "hd") -> str:
    """Download a Pexels video to local storage.

    Args:
        video_id: Pexels video ID.
        output_dir: Directory to save the file.
        quality: "hd" or "sd".

    Returns:
        Path to downloaded file.

    Raises:
        modules.review_engine.exceptions.StockMediaError: On download failure.
    """
    raise NotImplementedError("Pexels adapter: implementation in v0.16.0")
