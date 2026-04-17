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
        import urllib.parse
        import json

        per_page = int(kwargs.get("per_page", 15) or 15)
        per_page = max(1, min(per_page, 80))  # Pexels API cap is 80
        orientation = str(kwargs.get("orientation", "") or "").strip().lower()
        if orientation and orientation not in ("landscape", "portrait", "square"):
            orientation = ""
        min_duration = int(kwargs.get("min_duration", 0) or 0)
        max_duration = int(kwargs.get("max_duration", 0) or 0)

        # Round-14 P2: urlencode query — previously an unescaped query could
        # inject additional Pexels params (e.g. "&api_key=attacker").
        params = {
            "query": str(query or ""),
            "per_page": str(per_page),
        }
        if orientation:
            params["orientation"] = orientation
        if min_duration:
            params["min_duration"] = str(min_duration)
        if max_duration:
            params["max_duration"] = str(max_duration)
        url = f"{self.API_BASE}/search?{urllib.parse.urlencode(params)}"

        req = urllib.request.Request(url)
        req.add_header("Authorization", self.api_key)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                # Cap body to 16MB — malicious/compromised endpoint could
                # otherwise return a multi-GB payload to OOM the process.
                raw = resp.read(16 * 1024 * 1024 + 1)
                if len(raw) > 16 * 1024 * 1024:
                    raise StockMediaError("Pexels search response too large")
                return json.loads(raw)
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            raise StockMediaError(f"Pexels search failed: {e}") from e

    def download(self, video_url: str, output_path: str) -> str:
        import urllib.request
        import urllib.parse

        # Round-14 P2: validate download URL. Previously accepted ANY URL
        # (SSRF via http://169.254.169.254 / http://127.0.0.1/ etc.)
        parsed = urllib.parse.urlparse(str(video_url or ""))
        if parsed.scheme != "https":
            raise StockMediaError(f"stock download must be https://, got {parsed.scheme!r}")
        host = (parsed.hostname or "").lower()
        if not (host == "videos.pexels.com" or host.endswith(".pexels.com")):
            raise StockMediaError(
                f"stock download host must be *.pexels.com, got {host!r}"
            )

        # Atomic write via .part → rename so a crash mid-download doesn't
        # leave a truncated file that ffmpeg might silently accept.
        import os as _os
        tmp_path = f"{output_path}.part"
        try:
            req = urllib.request.Request(video_url)
            with urllib.request.urlopen(req, timeout=120) as resp:
                with open(tmp_path, "wb") as f:
                    while True:
                        chunk = resp.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            _os.replace(tmp_path, output_path)
            return output_path
        except (urllib.error.URLError, OSError) as e:
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass
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
