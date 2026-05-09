"""Claude Vision adapter.

v0.19 L8: reads `ANTHROPIC_API_KEY` (Anthropic SDK standard, what Settings
UI writes) preferentially; falls back to legacy `VIDEOEDITOR_CLAUDE_API_KEY`
for backward compatibility (kept 6 version cycles per audit risk-N).
"""

import base64
import io
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

from modules.adapters.vlm_adapter import VLMResponse

logger = logging.getLogger(__name__)

# v0.19 L8: standard env var (matches official Anthropic SDK)
API_KEY_ENV = "ANTHROPIC_API_KEY"
# Legacy env var — kept for backward compat. Will be removed in v0.24+.
LEGACY_API_KEY_ENV = "VIDEOEDITOR_CLAUDE_API_KEY"


def _resolve_api_key() -> str:
    """Resolve Claude API key from primary or legacy env var."""
    return (
        os.environ.get(API_KEY_ENV, "").strip()
        or os.environ.get(LEGACY_API_KEY_ENV, "").strip()
    )
DEFAULT_MODEL = "claude-sonnet-4-20250514"
API_URL = "https://api.anthropic.com/v1/messages"
TIMEOUT_S = 30
MAX_IMAGE_PX = 2048
MAX_RETRIES = 1
# See _vlm_openai.MAX_RESPONSE_BYTES — same cap for the Claude API.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class ClaudeVisionAdapter:
    def __init__(self, model: Optional[str] = None):
        self._model = model or DEFAULT_MODEL

    def is_available(self) -> bool:
        return bool(_resolve_api_key())

    def describe_image(
        self,
        image: Any,
        prompt: str,
        max_tokens: int = 300,
    ) -> Optional[VLMResponse]:
        if not self.is_available():
            return None

        t0 = time.monotonic()
        b64 = self._image_to_base64(image)
        if b64 is None:
            return None

        for attempt in range(1 + MAX_RETRIES):
            try:
                raw = self._call_api(b64, prompt, max_tokens)
                text = raw["content"][0]["text"]
                tokens = raw.get("usage", {}).get("output_tokens", 0)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                return VLMResponse(
                    text=text,
                    model="claude",
                    latency_ms=elapsed_ms,
                    tokens_used=tokens,
                )
            except Exception as exc:
                logger.warning(
                    "Claude Vision API attempt %d failed: %s", attempt + 1, exc
                )
                if attempt >= MAX_RETRIES:
                    return None

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "claude",
            "model": self._model,
            "available": self.is_available(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_api(self, b64_image: str, prompt: str, max_tokens: int) -> Dict:
        """Make the HTTP call. Separated for easy mocking."""
        api_key = _resolve_api_key()
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
        }
        req = Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"VLM response exceeds {MAX_RESPONSE_BYTES} byte cap"
                )
            return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _image_to_base64(image: Any) -> Optional[str]:
        if image is None:
            return None
        try:
            from PIL import Image

            if not isinstance(image, Image.Image):
                return None
            w, h = image.size
            if max(w, h) > MAX_IMAGE_PX:
                ratio = MAX_IMAGE_PX / max(w, h)
                image = image.resize(
                    (int(w * ratio), int(h * ratio)), Image.LANCZOS
                )
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as exc:
            logger.warning("Failed to encode image: %s", exc)
            return None
