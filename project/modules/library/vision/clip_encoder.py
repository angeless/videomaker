"""CLIP image-text encoder with lazy loading and graceful degradation."""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

# Prevent OMP conflict with FAISS/torch
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    import cv2
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

try:
    import torch
    from transformers import CLIPProcessor, CLIPModel
    from PIL import Image
    _HAS_CLIP = True
except ImportError:
    _HAS_CLIP = False

_log = logging.getLogger(__name__)


class CLIPEncoder:
    """Lazy-loading CLIP encoder for image and text embedding (512 dim).

    All methods return ``None`` when CLIP dependencies are unavailable,
    enabling graceful degradation to text-only search.
    """

    DIMENSION = 512
    DEFAULT_MODEL = "openai/clip-vit-base-patch32"

    def __init__(self, model_name: str | None = None):
        self._model_name = model_name or self.DEFAULT_MODEL
        self._model: Any = None
        self._processor: Any = None
        self._device: str = ""

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        return _HAS_CLIP and np is not None

    def encode_image(self, image: Any) -> Optional[List[float]]:
        """Encode a PIL Image or numpy BGR array → 512-dim unit vector."""
        if not self.is_available() or np is None:
            return None
        self._ensure_loaded()

        if _HAS_CV2 and isinstance(image, np.ndarray):
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        else:
            pil_img = image

        try:
            inputs = self._processor(images=pil_img, return_tensors="pt").to(self._device)
            with torch.no_grad():
                features = self._model.get_image_features(**inputs)
            vec = features.cpu().numpy()[0]
            norm = float(np.linalg.norm(vec))
            if norm < 1e-8:
                return None
            return (vec / norm).tolist()
        except Exception:
            _log.warning("CLIP image encoding failed", exc_info=True)
            return None

    def encode_text(self, text: str) -> Optional[List[float]]:
        """Encode text query → 512-dim unit vector (cross-modal search)."""
        if not self.is_available() or np is None:
            return None
        text = str(text or "").strip()
        if not text:
            return None
        self._ensure_loaded()

        try:
            inputs = self._processor(text=[text], return_tensors="pt", padding=True).to(self._device)
            with torch.no_grad():
                features = self._model.get_text_features(**inputs)
            vec = features.cpu().numpy()[0]
            norm = float(np.linalg.norm(vec))
            if norm < 1e-8:
                return None
            return (vec / norm).tolist()
        except Exception:
            _log.warning("CLIP text encoding failed", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # keyframe extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_keyframes(video_path: str, num_frames: int = 3) -> list:
        """Extract *num_frames* uniformly-spaced keyframes as PIL Images.

        Returns an empty list if cv2 is unavailable or the video cannot
        be read.
        """
        if not _HAS_CV2 or not _HAS_CLIP:
            return []
        cap = cv2.VideoCapture(video_path)
        frames: list = []
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total <= 0:
                return []
            indices = [int(i * total / num_frames) for i in range(num_frames)]
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        except Exception:
            _log.warning("Keyframe extraction failed for %s", video_path, exc_info=True)
        finally:
            cap.release()
        return frames

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        _log.info("Loading CLIP model: %s (device=%s)", self._model_name, self._device)
        self._model = CLIPModel.from_pretrained(self._model_name).to(self._device)
        self._processor = CLIPProcessor.from_pretrained(self._model_name)
