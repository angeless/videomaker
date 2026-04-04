"""VLM (Vision-Language Model) provider adapter.

All VLM API calls go through this adapter layer. The review_engine module
must not import provider SDKs directly.

Supports multiple providers:
- stub: Fixed-response adapter for testing
- local_llava: Local LLaVA model (v0.17.0 R2)
- openai: GPT-4o Vision API (v0.17.0 R3)
- claude: Claude Vision API (v0.17.0 R3)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class VLMResponse:
    """Structured response from a VLM provider."""

    text: str
    model: str = ""
    latency_ms: int = 0
    tokens_used: int = 0


class StubVLMAdapter:
    """Fixed-response VLM adapter for testing and fallback."""

    def __init__(self, fixed_response: Optional[str] = None):
        self._fixed = fixed_response or (
            "[画面区域] 标注区域包含可识别的视觉内容。"
        )

    def is_available(self) -> bool:
        return True

    def describe_image(
        self,
        image: Any,
        prompt: str,
        max_tokens: int = 300,
    ) -> VLMResponse:
        return VLMResponse(
            text=self._fixed,
            model="stub",
            latency_ms=0,
            tokens_used=0,
        )

    def get_model_info(self) -> Dict[str, Any]:
        return {
            "provider": "stub",
            "model": "stub-v1",
            "available": True,
        }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

# Registry of lazy-loaded adapter constructors.
# R2/R3 will add entries here.
_ADAPTER_REGISTRY: Dict[str, Any] = {
    "stub": lambda: StubVLMAdapter(),
}


def _try_build_local_llava():
    """Attempt to build LocalLlavaAdapter; return None if deps missing."""
    try:
        from modules.adapters._vlm_local_llava import LocalLlavaAdapter
        adapter = LocalLlavaAdapter()
        if adapter.is_available():
            return adapter
    except (ImportError, Exception) as exc:
        logger.debug("LocalLlavaAdapter unavailable: %s", exc)
    return None


def _try_build_openai_vision():
    """Attempt to build OpenAI Vision adapter; return None if deps missing."""
    try:
        from modules.adapters._vlm_openai import OpenAIVisionAdapter
        adapter = OpenAIVisionAdapter()
        if adapter.is_available():
            return adapter
    except (ImportError, Exception) as exc:
        logger.debug("OpenAIVisionAdapter unavailable: %s", exc)
    return None


def _try_build_claude_vision():
    """Attempt to build Claude Vision adapter; return None if deps missing."""
    try:
        from modules.adapters._vlm_claude import ClaudeVisionAdapter
        adapter = ClaudeVisionAdapter()
        if adapter.is_available():
            return adapter
    except (ImportError, Exception) as exc:
        logger.debug("ClaudeVisionAdapter unavailable: %s", exc)
    return None


_ADAPTER_REGISTRY["local_llava"] = _try_build_local_llava
_ADAPTER_REGISTRY["openai"] = _try_build_openai_vision
_ADAPTER_REGISTRY["claude"] = _try_build_claude_vision


def get_vlm_adapter(provider: Optional[str] = None) -> Optional[Any]:
    """Return a VLM adapter for the given provider, or None.

    Args:
        provider: One of "stub", "local_llava", "openai", "claude".
                  None returns None (explicit no-op).

    Returns:
        An adapter instance with ``describe_image()`` / ``is_available()``
        methods, or ``None`` if the provider is unknown or unavailable.
    """
    if provider is None:
        return None

    builder = _ADAPTER_REGISTRY.get(provider)
    if builder is None:
        logger.warning("Unknown VLM provider: %s", provider)
        return None

    try:
        result = builder()
        if result is None:
            logger.info("VLM provider '%s' not available, graceful degradation", provider)
        return result
    except Exception as exc:
        logger.warning("Failed to initialize VLM provider '%s': %s", provider, exc)
        return None
