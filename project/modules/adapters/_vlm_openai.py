"""OpenAI GPT-4o Vision adapter.

Requires VIDEOEDITOR_OPENAI_API_KEY env variable.
"""

import base64
import io
import json
import logging
import os
import time
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

from modules.adapters.vlm_adapter import VLMResponse

logger = logging.getLogger(__name__)

API_KEY_ENV = "VIDEOEDITOR_OPENAI_API_KEY"
DEFAULT_MODEL = "gpt-4o"
API_URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT_S = 30
MAX_IMAGE_PX = 2048
MAX_RETRIES = 1
# Cap VLM response body size to prevent OOM if upstream returns multi-GB
# payload (e.g. API-key-compromise redirect, proxy misconfig, or a malicious
# endpoint set via VIDEOEDITOR_OPENAI_API_BASE env poisoning). 4 MB is
# plenty for a typical JSON response (usually <50 KB).
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class OpenAIVisionAdapter:
    def __init__(self, model: Optional[str] = None):
        self._model = model or DEFAULT_MODEL

    def is_available(self) -> bool:
        return bool(os.environ.get(API_KEY_ENV))

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
                text = raw["choices"][0]["message"]["content"]
                tokens = raw.get("usage", {}).get("completion_tokens", 0)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                return VLMResponse(
                    text=text,
                    model="openai",
                    latency_ms=elapsed_ms,
                    tokens_used=tokens,
                )
            except Exception as exc:
                logger.warning(
                    "OpenAI Vision API attempt %d failed: %s", attempt + 1, exc
                )
                if attempt >= MAX_RETRIES:
                    return None

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "openai",
            "model": self._model,
            "available": self.is_available(),
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _call_api(self, b64_image: str, prompt: str, max_tokens: int) -> Dict:
        """Make the HTTP call. Separated for easy mocking."""
        api_key = os.environ.get(API_KEY_ENV, "")
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                            },
                        },
                    ],
                }
            ],
        }
        req = Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urlopen(req, timeout=TIMEOUT_S) as resp:
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"VLM response exceeds {MAX_RESPONSE_BYTES} byte cap "
                    f"(possible misconfigured API endpoint)"
                )
            return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _image_to_base64(image: Any) -> Optional[str]:
        """Convert PIL Image to base64 JPEG, resizing if needed."""
        if image is None:
            return None
        try:
            from PIL import Image

            if not isinstance(image, Image.Image):
                return None

            # Resize if too large
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
