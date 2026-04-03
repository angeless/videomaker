"""TTSVoiceover — text-to-speech generation via adapter pattern.

Generates voiceover audio segments aligned to subtitle timings.
Default provider: edge-tts (free, no API key).
"""

import asyncio
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from .exceptions import RenderError

logger = logging.getLogger(__name__)


class TTSAdapter(Protocol):
    """Protocol for TTS providers."""
    async def synthesize(self, text: str, voice: str, output_path: str) -> str: ...


@dataclass
class VoiceoverSegment:
    """A TTS segment aligned to video timing."""
    text: str
    start_ms: int
    end_ms: int
    audio_path: Optional[str] = None


class EdgeTTSAdapter:
    """Default TTS adapter using edge-tts (free)."""

    async def synthesize(self, text: str, voice: str, output_path: str) -> str:
        try:
            import edge_tts
        except ImportError:
            raise RenderError(
                "edge-tts not installed. Run: pip install edge-tts"
            )

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        return output_path


# Voice presets
VOICE_PRESETS = {
    "zh-female": "zh-CN-XiaoxiaoNeural",
    "zh-male": "zh-CN-YunxiNeural",
    "en-female": "en-US-JennyNeural",
    "en-male": "en-US-GuyNeural",
}


def generate_voiceover(
    segments: List[Dict],
    output_dir: str,
    voice: str = "zh-female",
    adapter: Optional[TTSAdapter] = None,
) -> List[VoiceoverSegment]:
    """Generate TTS audio for each segment.

    Args:
        segments: [{"text": str, "start_ms": int, "end_ms": int}]
        output_dir: Directory to save audio files
        voice: Voice preset key or full voice name
        adapter: TTS adapter (defaults to EdgeTTSAdapter)
    """
    if adapter is None:
        adapter = EdgeTTSAdapter()

    voice_name = VOICE_PRESETS.get(voice, voice)
    os.makedirs(output_dir, exist_ok=True)

    results = []
    for i, seg in enumerate(segments):
        text = seg.get("text", "").strip()
        if not text:
            continue

        output_path = os.path.join(output_dir, f"tts_{i:04d}.mp3")
        try:
            asyncio.run(adapter.synthesize(text, voice_name, output_path))
            results.append(VoiceoverSegment(
                text=text,
                start_ms=seg.get("start_ms", 0),
                end_ms=seg.get("end_ms", 0),
                audio_path=output_path,
            ))
        except Exception as e:
            logger.error("TTS failed for segment %d: %s", i, e)
            raise RenderError(f"TTS generation failed: {e}") from e

    return results
