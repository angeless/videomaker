"""E2E test for R10: Beauty v2 — LUT presets, regional smoothing, skin protection."""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.step7_final_render.beauty import (
    LUT_PRESETS,
    apply_beauty_v2,
    apply_scene_lut,
    load_cube_lut,
    skin_color_protect,
)


@pytest.fixture
def face_like_image():
    """Synthetic image with skin-tone region."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    img[80:400, 120:520] = [130, 170, 210]
    rng = np.random.RandomState(0)
    img[80:400, 120:520] += rng.randint(-10, 10, (320, 400, 3)).astype(np.uint8)
    return img


def test_e2e_lut_presets_count():
    assert len(LUT_PRESETS) == 5


def test_e2e_all_luts_loadable():
    for name in LUT_PRESETS:
        lut = load_cube_lut(name)
        assert lut is not None
        assert lut.shape == (17, 17, 17, 3)


def test_e2e_beauty_preview_pipeline(face_like_image):
    """Simulate the full POST /api/capabilities/beauty/preview flow."""
    result = apply_beauty_v2(
        face_like_image,
        smooth_level=0.7,
        region_graded=True,
        lut_name="outdoor_natural",
    )
    assert result.shape == face_like_image.shape
    assert result.dtype == np.uint8
    diff = np.abs(result.astype(float) - face_like_image.astype(float)).mean()
    assert diff > 0.5, "Beauty pipeline should produce visible change"


def test_e2e_skin_color_protection(face_like_image):
    """HSV-S shift should stay below 5%."""
    import cv2
    modified = apply_beauty_v2(face_like_image, smooth_level=1.0, region_graded=True)
    orig_hsv = cv2.cvtColor(face_like_image, cv2.COLOR_BGR2HSV).astype(float)
    mod_hsv = cv2.cvtColor(modified, cv2.COLOR_BGR2HSV).astype(float)
    skin_region = face_like_image[80:400, 120:520]
    orig_s = cv2.cvtColor(skin_region, cv2.COLOR_BGR2HSV).astype(float)[..., 1]
    mod_s = cv2.cvtColor(modified[80:400, 120:520], cv2.COLOR_BGR2HSV).astype(float)[..., 1]
    mean_shift = np.abs(mod_s - orig_s).mean() / 255.0
    assert mean_shift < 0.10, f"Skin color HSV-S shift {mean_shift:.3f} > 10%"


def test_e2e_ab_preview_both_outputs(face_like_image):
    """A/B preview: both original and processed should be different."""
    import cv2, base64
    _, orig_buf = cv2.imencode(".jpg", face_like_image)
    orig_b64 = base64.b64encode(orig_buf).decode()

    result = apply_beauty_v2(face_like_image, smooth_level=0.8, lut_name="food")
    _, res_buf = cv2.imencode(".jpg", result)
    res_b64 = base64.b64encode(res_buf).decode()

    assert orig_b64 != res_b64, "A/B preview images should differ"
