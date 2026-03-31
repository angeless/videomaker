"""Tests for R10: Beauty v2 — regional smoothing, skin color protection, LUT presets."""

import sys
from pathlib import Path

import pytest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.step7_final_render.beauty import (
    AdvancedBeautyFilter,
    LUT_PRESETS,
    apply_beauty_v2,
    apply_regional_smooth,
    apply_scene_lut,
    load_cube_lut,
    skin_color_protect,
)


@pytest.fixture
def synthetic_image():
    """480x640 BGR image with skin-like colors in center."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    # Fill with skin-like color (BGR)
    img[100:380, 150:490] = [130, 170, 210]  # warm skin tone
    # Add some texture variation
    rng = np.random.RandomState(42)
    noise = rng.randint(-15, 15, img[100:380, 150:490].shape).astype(np.int16)
    img[100:380, 150:490] = np.clip(
        img[100:380, 150:490].astype(np.int16) + noise, 0, 255
    ).astype(np.uint8)
    return img


class TestLUTPresets:
    def test_five_presets_exist(self):
        assert len(LUT_PRESETS) == 5
        assert "outdoor_natural" in LUT_PRESETS
        assert "indoor_warm" in LUT_PRESETS
        assert "food" in LUT_PRESETS
        assert "night" in LUT_PRESETS
        assert "travel" in LUT_PRESETS

    def test_load_cube_lut(self):
        for name in LUT_PRESETS:
            lut = load_cube_lut(name)
            assert lut is not None, f"Failed to load LUT: {name}"
            assert lut.shape == (17, 17, 17, 3)
            assert lut.dtype == np.float64
            assert lut.min() >= 0.0
            assert lut.max() <= 1.0

    def test_load_nonexistent_lut(self):
        result = load_cube_lut("nonexistent_lut_xyz")
        assert result is None

    def test_apply_scene_lut_produces_visible_change(self, synthetic_image):
        for name in LUT_PRESETS:
            result = apply_scene_lut(synthetic_image, name)
            assert result.shape == synthetic_image.shape
            assert result.dtype == np.uint8
            diff = np.abs(result.astype(float) - synthetic_image.astype(float)).mean()
            assert diff > 0.5, f"LUT {name} produced no visible change (diff={diff:.2f})"

    def test_apply_lut_identity_like(self):
        """Identity-ish: applying a near-identity LUT should change very little."""
        img = np.full((100, 100, 3), 128, dtype=np.uint8)
        result = apply_scene_lut(img, "outdoor_natural")
        diff = np.abs(result.astype(float) - img.astype(float)).mean()
        assert diff < 30, f"LUT change too large for uniform image: {diff:.2f}"


class TestSkinColorProtection:
    def test_limits_saturation_shift(self, synthetic_image):
        import cv2

        # Create an aggressively modified version
        modified = synthetic_image.copy()
        modified[:, :, 2] = np.clip(modified[:, :, 2].astype(int) + 50, 0, 255).astype(np.uint8)

        protected = skin_color_protect(synthetic_image, modified, threshold=0.05)

        # Check HSV-S channel shift is limited
        orig_hsv = cv2.cvtColor(synthetic_image, cv2.COLOR_BGR2HSV).astype(float)
        prot_hsv = cv2.cvtColor(protected, cv2.COLOR_BGR2HSV).astype(float)
        s_shift = np.abs(prot_hsv[..., 1] - orig_hsv[..., 1]) / 255.0
        mean_shift = s_shift.mean()
        assert mean_shift < 0.10, f"Mean saturation shift too high: {mean_shift:.3f}"


class TestRegionalSmoothing:
    def test_graded_vs_uniform(self, synthetic_image):
        face_regions = [(150, 100, 340, 280)]

        graded = apply_regional_smooth(
            synthetic_image, face_regions, smooth_level=0.8, region_graded=True
        )
        uniform = apply_regional_smooth(
            synthetic_image, face_regions, smooth_level=0.8, region_graded=False
        )

        # Graded and uniform should produce different results
        diff = np.abs(graded.astype(float) - uniform.astype(float)).mean()
        assert diff > 0.1, "Graded and uniform smoothing should differ"

    def test_empty_regions_noop(self, synthetic_image):
        result = apply_regional_smooth(synthetic_image, [], smooth_level=0.8)
        np.testing.assert_array_equal(result, synthetic_image)


class TestBeautyV2Pipeline:
    def test_full_pipeline_no_crash(self, synthetic_image):
        result = apply_beauty_v2(
            synthetic_image, smooth_level=0.5, region_graded=True, lut_name="travel"
        )
        assert result.shape == synthetic_image.shape
        assert result.dtype == np.uint8

    def test_pipeline_without_lut(self, synthetic_image):
        result = apply_beauty_v2(synthetic_image, smooth_level=0.8, lut_name=None)
        assert result.shape == synthetic_image.shape

    def test_pipeline_degradation_tracking(self, synthetic_image):
        degradations = []
        apply_beauty_v2(synthetic_image, degradations=degradations)
        # Without mediapipe, should have face_detection degradation
        assert any(d["feature"] == "face_detection" for d in degradations)

    def test_pipeline_all_luts(self, synthetic_image):
        for name in LUT_PRESETS:
            result = apply_beauty_v2(synthetic_image, lut_name=name)
            assert result.shape == synthetic_image.shape

    def test_smooth_level_range(self, synthetic_image):
        for level in [0.0, 0.3, 0.5, 0.8, 1.0]:
            result = apply_beauty_v2(synthetic_image, smooth_level=level)
            assert result.shape == synthetic_image.shape
