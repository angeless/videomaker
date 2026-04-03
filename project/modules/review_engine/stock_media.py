"""StockMedia — search and download stock video from Pexels.

Uses an adapter pattern to isolate the Pexels API dependency.
Requires PEXELS_API_KEY environment variable.
"""

import json
import logging
import os
import shutil
import urllib.error
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from .exceptions import StockMediaError

logger = logging.getLogger(__name__)


class StockAdapter(Protocol):
    """Protocol for stock media providers."""
    def search(self, query: str, **kwargs) -> Dict: ...
    def download(self, video_id: str, output_path: str) -> str: ...


@dataclass
class StockResult:
    """A single stock media search result."""
    id: str
    url: str
    preview_url: str
    duration: float
    photographer: str
    width: int = 0
    height: int = 0


class PexelsAdapter:
    """Pexels API adapter."""

    API_BASE = "https://api.pexels.com/videos"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("PEXELS_API_KEY")
        if not self.api_key:
            raise StockMediaError(
                "Pexels API key not configured. "
                "Set PEXELS_API_KEY environment variable."
            )

    def search(self, query: str, **kwargs) -> Dict:
        import urllib.request
        import json

        per_page = kwargs.get("per_page", 15)
        orientation = kwargs.get("orientation", "")
        min_duration = kwargs.get("min_duration", 0)
        max_duration = kwargs.get("max_duration", 0)

        url = f"{self.API_BASE}/search?query={query}&per_page={per_page}"
        if orientation:
            url += f"&orientation={orientation}"
        if min_duration:
            url += f"&min_duration={min_duration}"
        if max_duration:
            url += f"&max_duration={max_duration}"

        req = urllib.request.Request(url)
        req.add_header("Authorization", self.api_key)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            raise StockMediaError(f"Pexels search failed: {e}") from e

    def download(self, video_url: str, output_path: str) -> str:
        import urllib.request

        try:
            req = urllib.request.Request(video_url)
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(output_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            return output_path
        except (urllib.error.URLError, OSError) as e:
            raise StockMediaError(f"Download failed: {e}") from e


def search_stock(
    query: str,
    adapter: Optional[StockAdapter] = None,
    **kwargs,
) -> List[StockResult]:
    """Search for stock videos.

    Args:
        query: Search keywords
        adapter: Stock media adapter (defaults to PexelsAdapter)
        **kwargs: Additional search params (orientation, per_page, etc.)

    Returns:
        List of StockResult objects
    """
    if adapter is None:
        adapter = PexelsAdapter()

    data = adapter.search(query, **kwargs)
    results = []

    for video in data.get("videos", []):
        # Get best quality video file
        files = video.get("video_files", [])
        best = max(files, key=lambda f: f.get("width", 0)) if files else {}

        results.append(StockResult(
            id=str(video.get("id", "")),
            url=best.get("link", ""),
            preview_url=video.get("video_pictures", [{}])[0].get("picture", "")
            if video.get("video_pictures") else "",
            duration=video.get("duration", 0),
            photographer=video.get("user", {}).get("name", ""),
            width=best.get("width", 0),
            height=best.get("height", 0),
        ))

    return results


def download_stock(
    video_url: str,
    output_dir: str,
    filename: Optional[str] = None,
    adapter: Optional[StockAdapter] = None,
) -> str:
    """Download a stock video to the project directory."""
    if adapter is None:
        adapter = PexelsAdapter()

    os.makedirs(output_dir, exist_ok=True)
    if filename is None:
        filename = os.path.basename(video_url).split("?")[0] or "stock_video.mp4"

    output_path = os.path.join(output_dir, filename)
    return adapter.download(video_url, output_path)
