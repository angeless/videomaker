"""4 enhancement tools for MCP (A3).

Tools: enhance_audio, enhance_tts, enhance_bgm, enhance_transition.
"""

import json
import logging
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from modules.mcp_server.health import DEFAULT_BACKEND_URL, check_backend_health

logger = logging.getLogger(__name__)


def _post(endpoint: str, payload: Dict[str, Any],
          base_url: str = DEFAULT_BACKEND_URL) -> Dict[str, Any]:
    healthy, msg = check_backend_health(base_url)
    if not healthy:
        return {"error": msg, "success": False}
    url = f"{base_url}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}: {body}", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


# ── Tool implementations ─────────────────────────────────────────


def enhance_audio(
    session_id: str,
    denoise: bool = True,
    eq: bool = True,
    compressor: bool = True,
    loudness_target: float = -16.0,
) -> Dict[str, Any]:
    """Apply audio enhancement (denoise, EQ, compression, loudness normalization).

    Args:
        session_id: Review session ID.
        denoise: Enable noise reduction.
        eq: Enable equalization.
        compressor: Enable dynamic range compression.
        loudness_target: Target loudness in LUFS (default -16).
    """
    return _post("/api/review/enhance/audio", {
        "session_id": session_id,
        "denoise": denoise,
        "eq": eq,
        "compressor": compressor,
        "loudness_target": loudness_target,
    })


def enhance_tts(
    session_id: str,
    text: str,
    voice: str = "default",
    language: str = "zh",
) -> Dict[str, Any]:
    """Generate text-to-speech voiceover.

    Args:
        session_id: Review session ID.
        text: Text to synthesize.
        voice: Voice ID or name.
        language: Language code (default: zh).
    """
    return _post("/api/review/enhance/tts", {
        "session_id": session_id,
        "text": text,
        "voice": voice,
        "language": language,
    })


def enhance_bgm(
    session_id: str,
    genre: str = "ambient",
    beat_align: bool = True,
) -> Dict[str, Any]:
    """Select and apply background music with optional beat alignment.

    Args:
        session_id: Review session ID.
        genre: Music genre/mood.
        beat_align: Align cuts to beat markers.
    """
    return _post("/api/review/enhance/bgm", {
        "session_id": session_id,
        "genre": genre,
        "beat_align": beat_align,
    })


def enhance_transition(
    session_id: str,
    effect: str = "cross_dissolve",
    duration_ms: int = 500,
) -> Dict[str, Any]:
    """Add transition effect between segments.

    Args:
        session_id: Review session ID.
        effect: Transition effect name (e.g., cross_dissolve, fade_black).
        duration_ms: Transition duration in milliseconds.
    """
    return _post("/api/review/enhance/transition", {
        "session_id": session_id,
        "effect": effect,
        "duration_ms": duration_ms,
    })
