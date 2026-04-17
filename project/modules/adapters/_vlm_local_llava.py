"""Local LLaVA VLM adapter — offline image understanding.

Uses LLaVA-v1.5-7B via transformers pipeline. Falls back gracefully
when model weights or dependencies are not installed.

Dependencies (optional):
    pip install transformers>=4.36 torch accelerate pillow
    # Model auto-downloads on first use (~4GB)
"""

import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import torch
    from PIL import Image
    _HAS_LLAVA = True
except ImportError:
    _HAS_LLAVA = False

from modules.adapters.vlm_adapter import VLMResponse

DEFAULT_MODEL = "llava-hf/llava-1.5-7b-hf"

# Round-15 P2: allowlist known-safe LLaVA/LLaVA-Next model repos.
# model_name flows from workflow config into HF pipeline, which downloads
# the repo and runs its `configuration.py`/modeling code — untrusted repo
# names can execute arbitrary code during model loading.
_ALLOWED_LLAVA_MODELS = {
    "llava-hf/llava-1.5-7b-hf",
    "llava-hf/llava-1.5-13b-hf",
    "llava-hf/llava-v1.6-mistral-7b-hf",
    "llava-hf/llava-v1.6-vicuna-7b-hf",
    "llava-hf/llava-v1.6-vicuna-13b-hf",
    "llava-hf/llava-v1.6-34b-hf",
    "llava-hf/llava-next-72b-hf",
    "llava-hf/llava-next-interleave-qwen-7b-hf",
}


class LocalLlavaAdapter:
    """Local LLaVA inference adapter with lazy model loading."""

    def __init__(self, model_name: Optional[str] = None):
        raw = model_name or DEFAULT_MODEL
        if raw not in _ALLOWED_LLAVA_MODELS:
            logger.warning(
                "LLaVA model_name %r not on allowlist; falling back to %s",
                raw, DEFAULT_MODEL,
            )
            raw = DEFAULT_MODEL
        self._model_name = raw
        self._pipe: Any = None
        self._loaded = False

    def is_available(self) -> bool:
        return _HAS_LLAVA

    def describe_image(
        self,
        image: Any,
        prompt: str,
        max_tokens: int = 300,
    ) -> Optional[VLMResponse]:
        if not self.is_available():
            return None

        t0 = time.monotonic()

        if not self._loaded:
            self._ensure_loaded()

        text = self._generate(image, prompt, max_tokens)
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        return VLMResponse(
            text=text,
            model="local_llava",
            latency_ms=elapsed_ms,
            tokens_used=len(text.split()),
        )

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "local_llava",
            "model": self._model_name,
            "available": self.is_available(),
            "loaded": self._loaded,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Lazy-load the LLaVA model pipeline."""
        if self._loaded:
            return
        if not _HAS_LLAVA:
            return

        try:
            from transformers import pipeline as hf_pipeline

            device = "cuda" if torch.cuda.is_available() else "cpu"
            dtype = torch.float16 if device == "cuda" else torch.float32

            logger.info(
                "Loading LLaVA model '%s' on %s (this may take 30-60s)...",
                self._model_name,
                device,
            )
            self._pipe = hf_pipeline(
                "image-to-text",
                model=self._model_name,
                device=device,
                torch_dtype=dtype,
            )
            self._loaded = True
            logger.info("LLaVA model loaded successfully")
        except Exception as exc:
            logger.warning("Failed to load LLaVA model: %s", exc)
            self._loaded = False

    def _generate(self, image: Any, prompt: str, max_tokens: int = 300) -> str:
        """Run inference. Separated for easy mocking in tests."""
        if self._pipe is None:
            return "[LLaVA model not loaded]"

        try:
            full_prompt = f"USER: <image>\n{prompt}\nASSISTANT:"
            outputs = self._pipe(
                image,
                prompt=full_prompt,
                generate_kwargs={"max_new_tokens": max_tokens},
            )
            if outputs and isinstance(outputs, list):
                return outputs[0].get("generated_text", "").strip()
            return str(outputs)
        except Exception as exc:
            logger.warning("LLaVA inference failed: %s", exc)
            return f"[VLM inference error: {exc}]"
