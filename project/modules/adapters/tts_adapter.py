"""TTS (Text-to-Speech) provider adapter.

All TTS API calls go through this adapter. The review_engine module
must not import provider SDKs directly.

Implementation deferred to v0.16.0 R15.
"""

import os
from typing import Dict, List, Optional


TTS_PROVIDER_ENV = "VIDEOEDITOR_TTS_PROVIDER"
TTS_API_KEY_ENV = "VIDEOEDITOR_TTS_API_KEY"

SUPPORTED_PROVIDERS = {
    "edge_tts": {"desc": "Microsoft Edge TTS (free)", "needs_key": False},
    "cosy_voice": {"desc": "CosyVoice (Alibaba)", "needs_key": True},
    "fish_speech": {"desc": "Fish Speech (open source)", "needs_key": True},
}


def get_provider() -> str:
    """Return configured TTS provider, default 'edge_tts'."""
    return os.environ.get(TTS_PROVIDER_ENV, "edge_tts")


def get_api_key() -> Optional[str]:
    """Return the TTS API key from environment, or None."""
    return os.environ.get(TTS_API_KEY_ENV)


def generate_speech(
    text: str,
    voice: str = "zh-CN-XiaoxiaoNeural",
    provider: Optional[str] = None,
    output_path: Optional[str] = None,
) -> str:
    """Generate speech audio from text.

    Args:
        text: Text to speak.
        voice: Voice identifier (provider-specific).
        provider: TTS provider name (defaults to env config).
        output_path: Output audio file path.

    Returns:
        Path to generated audio file.

    Raises:
        modules.review_engine.exceptions.ReviewEngineError: On TTS failure.
    """
    raise NotImplementedError("TTS adapter: implementation in v0.16.0")


def list_voices(provider: Optional[str] = None) -> List[Dict]:
    """List available voices for the given provider.

    Returns:
        List of dicts with keys: id, name, language, gender.
    """
    raise NotImplementedError("TTS adapter: implementation in v0.16.0")
