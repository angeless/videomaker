"""usability_scorer 单元测试"""

import pytest
from modules.step1_material_analysis.usability_scorer import (
    score_asset,
    _detect_material_type,
    _compute_tech_score,
    _compute_aesthetic_score,
    _compute_audio_score,
    _compute_narrative_score,
    _compute_edit_fitness,
    _compute_content_richness,
    _evaluate_trash,
    _resolve_tier,
    WEIGHT_PROFILES,
)


# ========== Fixtures ==========

@pytest.fixture
def high_quality_broll_visual_stats():
    return {
        "sample_count": 18,
        "brightness": 0.55, "brightness_std": 0.15,
        "saturation": 0.45, "saturation_std": 0.06,
        "blue_ratio": 0.28, "green_ratio": 0.38, "red_ratio": 0.34,
        "edge_density": 0.12, "edge_density_std": 0.03,
        "motion_score": 5.0, "motion_std": 2.0,
        "face_ratio": 0.0,
        "color_temp": 0.06,
        "texture_complexity": 0.14,
        "hue_dominant": 120,
    }

@pytest.fixture
def trash_broll_visual_stats():
    return {
        "sample_count": 5,
        "brightness": 0.08, "brightness_std": 0.02,
        "saturation": 0.10, "saturation_std": 0.03,
        "blue_ratio": 0.34, "green_ratio": 0.33, "red_ratio": 0.33,
        "edge_density": 0.02, "edge_density_std": 0.01,
        "motion_score": 42.0, "motion_std": 15.0,
        "face_ratio": 0.0,
        "color_temp": 0.0,
        "texture_complexity": 0.02,
        "hue_dominant": 0,
    }

@pytest.fixture
def talking_head_visual_stats():
    return {
        "sample_count": 18,
        "brightness": 0.60, "brightness_std": 0.10,
        "saturation": 0.35, "saturation_std": 0.05,
        "blue_ratio": 0.30, "green_ratio": 0.34, "red_ratio": 0.36,
        "edge_density": 0.10, "edge_density_std": 0.02,
        "motion_score": 3.0, "motion_std": 1.0,
        "face_ratio": 0.65,
        "color_temp": 0.06,
        "texture_complexity": 0.12,
        "hue_dominant": 30,
    }

@pytest.fixture
def base_asset_row():
    return {
        "uid": "test_uid_001",
        "duration": 8.0,
        "width": 1920, "height": 1080,
        "fps": 30.0, "codec": "h264",
        "quality_score": 0.85,
        "phash": "a1b2c3d4e5f60718",
    }

@pytest.fixture
def good_audio_info():
    return {
        "snr_db": 32.0,
        "noise_floor_db": -48.0,
        "clipping_ratio": 0.0001,
        "loudness_lufs": -16.0,
        "peak_db": -1.5,
        "dynamic_range_db": 20.0,
        "quality_score": 0.85,
        "quality_level": "excellent",
        "issues": [],
        "method": "ffmpeg+numpy",
    }


# ========== 素材类型检测 ==========

class TestDetectMaterialType:
    def test_talking_head(self, talking_head_visual_stats):
        result = _detect_material_type(
            talking_head_visual_stats,
            {"asr_text": "这是一段很长的旁白文本" * 5, "semantic": {}}
        )
        assert result == "talking_head"

    def test_broll_scenery(self, high_quality_broll_visual_stats):
        result = _detect_material_type(
            high_quality_broll_visual_stats,
            {"asr_text": "", "semantic": {"narrative_role": "atmospheric_broll"}}
        )
        assert result == "broll_scenery"

    def test_broll_action(self):
        stats = {"face_ratio": 0.05, "motion_score": 25.0}
        result = _detect_material_type(stats, {"asr_text": "", "semantic": {}})
        assert result == "broll_action"

    def test_interview(self):
        stats = {"face_ratio": 0.35, "motion_score": 2.0}
        result = _detect_material_type(
            stats,
            {"asr_text": "这是一段非常长的采访文本内容，包含了很多详细的信息和观点分享" * 2, "semantic": {}}
        )
        assert result == "interview"

    def test_silent_no_face_is_broll_scenery(self):
        stats = {"face_ratio": 0.02, "motion_score": 3.0}
        result = _detect_material_type(stats, {"asr_text": "", "semantic": {}})
        assert result == "broll_scenery"

    def test_default_fallback(self):
        stats = {"face_ratio": 0.25, "motion_score": 5.0}
        result = _detect_material_type(stats, {"asr_text": "短文本", "semantic": {}})
        assert result == "default"


# ========== 各维度评分 ==========

class TestTechScore:
    def test_4k_high_bitrate(self):
        result = _compute_tech_score(
            {"width": 3840, "height": 2160, "fps": 60, "quality_score": 0.95, "codec": "h265"},
            {"motion_score": 2.0, "edge_density": 0.15, "texture_complexity": 0.18}
        )
        assert result["score"] >= 0.85
        assert result["sub"]["resolution"] >= 0.90
        assert result["sub"]["stability"] >= 0.90

    def test_480p_shaky(self):
        result = _compute_tech_score(
            {"width": 640, "height": 480, "fps": 24, "quality_score": 0.30, "codec": "h264"},
            {"motion_score": 30.0, "edge_density": 0.02, "texture_complexity": 0.03}
        )
        assert result["score"] < 0.40

    def test_1080p_stable(self):
        result = _compute_tech_score(
            {"width": 1920, "height": 1080, "fps": 30, "quality_score": 0.70, "codec": "h264"},
            {"motion_score": 5.0, "edge_density": 0.08, "texture_complexity": 0.12}
        )
        assert 0.60 <= result["score"] <= 0.90

    def test_missing_fields_use_defaults(self):
        result = _compute_tech_score({}, {})
        assert 0.0 <= result["score"] <= 1.0
        assert "resolution" in result["sub"]


class TestAestheticScore:
    def test_beautiful_scenery(self, high_quality_broll_visual_stats):
        result = _compute_aesthetic_score(high_quality_broll_visual_stats)
        assert result["score"] >= 0.70
        assert result["tier"] in ("stunning", "beautiful")

    def test_dark_blurry(self, trash_broll_visual_stats):
        result = _compute_aesthetic_score(trash_broll_visual_stats)
        # brightness=0.08 极暗，但 color_harmony/composition 有基础分，总分约 0.41
        assert result["score"] < 0.45
        assert result["tier"] in ("mediocre", "poor", "decent")

    def test_all_sub_dimensions_present(self, high_quality_broll_visual_stats):
        result = _compute_aesthetic_score(high_quality_broll_visual_stats)
        expected_subs = {"exposure", "color_harmony", "composition", "motion_aesthetic", "lighting"}
        assert set(result["sub"].keys()) == expected_subs

    def test_default_values(self):
        result = _compute_aesthetic_score({})
        assert 0.0 <= result["score"] <= 1.0


class TestAudioScore:
    def test_no_audio(self):
        result = _compute_audio_score(None)
        assert result["score"] == 0.5
        assert "无音轨" in result["note"]

    def test_excellent_audio(self, good_audio_info):
        result = _compute_audio_score(good_audio_info)
        assert result["score"] >= 0.80

    def test_audio_with_issues(self):
        result = _compute_audio_score({
            "quality_score": 0.60,
            "quality_level": "fair",
            "issues": ["clipping", "noise", "hum"],
            "snr_db": 15.0,
        })
        assert result["score"] < 0.60
        assert "问题" in result["note"]


class TestNarrativeScore:
    def test_with_voiceover(self, base_asset_row):
        result = _compute_narrative_score(
            base_asset_row,
            {"asr_text": "今天我们来到了美丽的海边 这里风景非常壮观",
             "ocr_text": "", "objects": ["ocean", "sky"],
             "semantic": {"mood": "壮观", "emotion_intensity": 0.8,
                          "narrative_role": "hero_shot"}, "tags": []}
        )
        assert result["score"] >= 0.65
        assert result["has_voiceover"] is True

    def test_pure_broll_no_voice(self, base_asset_row):
        result = _compute_narrative_score(
            base_asset_row,
            {"asr_text": "", "ocr_text": "", "objects": [],
             "semantic": {"mood": "", "emotion_intensity": 0.3,
                          "narrative_role": "general_broll"}, "tags": []}
        )
        assert result["score"] < 0.40
        assert result["is_pure_broll"] is True

    def test_short_duration_penalty(self):
        result = _compute_narrative_score(
            {"duration": 0.3, "uid": "x"},
            {"asr_text": "", "ocr_text": "", "objects": [],
             "semantic": {"narrative_role": "filler", "emotion_intensity": 0.2}, "tags": []}
        )
        assert result["sub"]["duration_fit"] == 0.15

    def test_all_sub_dimensions_present(self, base_asset_row):
        result = _compute_narrative_score(
            base_asset_row,
            {"asr_text": "", "semantic": {}}
        )
        expected_subs = {"voiceover", "info_density", "emotion", "role", "duration_fit"}
        assert set(result["sub"].keys()) == expected_subs


class TestEditFitness:
    def test_high_fps_4k(self):
        result = _compute_edit_fitness(
            {"fps": 60, "width": 3840, "height": 2160},
            {"motion_score": 5.0, "brightness": 0.50, "saturation": 0.40},
            {"quality_score": 0.85}
        )
        assert result["score"] >= 0.80

    def test_low_fps_low_res(self):
        result = _compute_edit_fitness(
            {"fps": 15, "width": 480, "height": 360},
            {"motion_score": 30.0, "brightness": 0.10, "saturation": 0.80},
            None
        )
        assert result["score"] < 0.45


class TestContentRichness:
    def test_rich_content(self):
        result = _compute_content_richness(
            {
                "asr_text": "long text " * 20,
                "ocr_text": "some ocr text here",
                "objects": ["a", "b", "c", "d"],
                "gps": {"lat": 25.0, "lon": 121.0},
                "semantic": {f"dim_{i}": f"val_{i}" for i in range(30)},
                "scene_description": "ocean sunset",
            },
            [{"tag_name": f"tag_{i}", "score": 0.80, "source": "vision"} for i in range(12)]
        )
        assert result["score"] >= 0.60

    def test_empty_content(self):
        result = _compute_content_richness(
            {"asr_text": "", "ocr_text": "", "objects": [], "semantic": {}},
            []
        )
        assert result["score"] < 0.35


# ========== 综合评分 ==========

class TestScoreAsset:
    def test_high_quality_broll_gets_high_score(
        self, base_asset_row, high_quality_broll_visual_stats
    ):
        result = score_asset(
            asset_row=base_asset_row,
            visual_stats=high_quality_broll_visual_stats,
            audio_info=None,
            analysis_json={
                "asr_text": "", "ocr_text": "", "objects": ["sky", "ocean", "sunset"],
                "semantic": {
                    "narrative_role": "atmospheric_broll", "mood": "治愈",
                    "emotion_intensity": 0.7, "time_of_day": "golden_hour",
                    "scene_description": "ocean sunset",
                },
                "gps": {"lat": 25.0, "lon": 121.0},
            },
            tag_results=[
                {"tag_name": "海边", "score": 0.90, "source": "vision"},
                {"tag_name": "日落", "score": 0.85, "source": "vision"},
                {"tag_name": "治愈", "score": 0.80, "source": "llm"},
                {"tag_name": "空镜", "score": 0.75, "source": "rule"},
                {"tag_name": "风景", "score": 0.70, "source": "vision"},
            ],
        )
        assert result["usability_score"] >= 0.60
        assert result["material_type"] == "broll_scenery"
        assert result["trash_evaluation"]["is_trash"] is False
        assert "schema_version" in result

    def test_trash_broll_gets_flagged(
        self, base_asset_row, trash_broll_visual_stats
    ):
        asset = {**base_asset_row, "duration": 0.5, "width": 640, "height": 480}
        # 提供 library_stats 使独特性降低，避免救赎机制将 trash_level 降为 warn
        result = score_asset(
            asset_row=asset,
            visual_stats=trash_broll_visual_stats,
            audio_info=None,
            analysis_json={
                "asr_text": "", "ocr_text": "", "objects": [],
                "semantic": {"narrative_role": "broll", "mood": "",
                             "emotion_intensity": 0.2},
            },
            tag_results=[],
            library_stats={
                "total_assets": 100,
                "scene_type_counts": {"unknown": 40},
                "similar_assets_count": 5,
            },
        )
        assert result["trash_evaluation"]["is_trash"] is True
        assert result["trash_evaluation"]["trash_level"] in (
            "suggest_delete", "strong_suggest_delete", "warn"
        )
        assert result["usability_tier"] in ("C", "D", "F")

    def test_talking_head_with_good_audio(
        self, talking_head_visual_stats, good_audio_info
    ):
        result = score_asset(
            asset_row={
                "uid": "test_002", "duration": 12.0,
                "width": 1920, "height": 1080,
                "fps": 30.0, "codec": "h264",
                "quality_score": 0.80, "phash": "abc123",
            },
            visual_stats=talking_head_visual_stats,
            audio_info=good_audio_info,
            analysis_json={
                "asr_text": "这是一段详细的讲解内容 " * 10,
                "ocr_text": "",
                "objects": ["person", "desk"],
                "semantic": {
                    "narrative_role": "explanation",
                    "mood": "neutral",
                    "emotion_intensity": 0.5,
                },
            },
            tag_results=[
                {"tag_name": "讲解", "score": 0.85, "source": "llm"},
                {"tag_name": "人物", "score": 0.90, "source": "vision"},
            ],
        )
        assert result["material_type"] == "talking_head"
        assert result["usability_score"] >= 0.55

    def test_output_schema_completeness(self, base_asset_row, high_quality_broll_visual_stats):
        result = score_asset(
            asset_row=base_asset_row,
            visual_stats=high_quality_broll_visual_stats,
            audio_info=None,
            analysis_json={"asr_text": "", "semantic": {}},
            tag_results=[],
        )
        assert "schema_version" in result
        assert "usability_score" in result
        assert "usability_tier" in result
        assert "usability_tier_label" in result
        assert "material_type" in result
        assert "weight_profile_used" in result
        assert "dimensions" in result
        assert "trash_evaluation" in result
        assert "comment" in result
        assert "suggested_use" in result
        assert "improvement_hints" in result

        dims = result["dimensions"]
        assert set(dims.keys()) == {
            "tech", "aesthetic", "audio", "narrative",
            "uniqueness", "edit_fitness", "content_richness",
        }

    def test_score_in_valid_range(self, base_asset_row, high_quality_broll_visual_stats):
        result = score_asset(
            asset_row=base_asset_row,
            visual_stats=high_quality_broll_visual_stats,
            audio_info=None,
            analysis_json={"asr_text": "", "semantic": {}},
            tag_results=[],
        )
        assert 0.0 <= result["usability_score"] <= 1.0
        for dim in result["dimensions"].values():
            assert 0.0 <= dim["score"] <= 1.0


# ========== 分级 ==========

class TestTierResolution:
    @pytest.mark.parametrize("score,expected_tier", [
        (0.95, "S+"), (0.88, "S"), (0.80, "A+"), (0.72, "A"),
        (0.65, "B+"), (0.55, "B"), (0.42, "C"), (0.28, "D"), (0.10, "F"),
    ])
    def test_tier_boundaries(self, score, expected_tier):
        tier_code, _ = _resolve_tier(score)
        assert tier_code == expected_tier

    def test_zero_score(self):
        tier_code, tier_label = _resolve_tier(0.0)
        assert tier_code == "F"
        assert tier_label == "垃圾"

    def test_perfect_score(self):
        tier_code, tier_label = _resolve_tier(1.0)
        assert tier_code == "S+"
        assert tier_label == "殿堂级"


# ========== 权重配置完整性 ==========

class TestWeightProfiles:
    @pytest.mark.parametrize("profile_name", WEIGHT_PROFILES.keys())
    def test_weights_sum_to_one(self, profile_name):
        weights = WEIGHT_PROFILES[profile_name]
        total = sum(weights.values())
        assert abs(total - 1.0) < 0.001, f"{profile_name} weights sum to {total}"

    @pytest.mark.parametrize("profile_name", WEIGHT_PROFILES.keys())
    def test_all_dimensions_present(self, profile_name):
        expected_keys = {"tech", "aesthetic", "audio", "narrative", "unique", "edit", "content"}
        assert set(WEIGHT_PROFILES[profile_name].keys()) == expected_keys


# ========== 垃圾判定 ==========

class TestTrashEvaluation:
    def test_no_trash(self):
        result = _evaluate_trash({
            "tech_score": 0.80, "aesthetic_score": 0.75, "audio_score": 0.70,
            "narrative_score": 0.65, "unique": 0.60, "edit": 0.70, "content": 0.60,
            "usability_score": 0.70, "material_type": "default",
            "duration": 8.0, "has_voiceover": True, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.80}, "uniqueness_score": 0.60,
        })
        assert result["is_trash"] is False

    def test_trash_001_critical_tech(self):
        result = _evaluate_trash({
            "tech_score": 0.20, "aesthetic_score": 0.50, "audio_score": 0.50,
            "narrative_score": 0.50, "usability_score": 0.40,
            "material_type": "default", "duration": 5.0,
            "has_voiceover": False, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.60}, "uniqueness_score": 0.50,
        })
        assert result["is_trash"] is True
        assert "TRASH_001" in result["triggered_rules"]

    def test_trash_005_short_fragment(self):
        result = _evaluate_trash({
            "tech_score": 0.50, "aesthetic_score": 0.50, "audio_score": 0.50,
            "narrative_score": 0.30, "usability_score": 0.40,
            "material_type": "default", "duration": 0.5,
            "has_voiceover": False, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.60}, "uniqueness_score": 0.50,
        })
        assert result["is_trash"] is True
        assert "TRASH_005" in result["triggered_rules"]

    def test_trash_008_empty_broll(self):
        result = _evaluate_trash({
            "tech_score": 0.40, "aesthetic_score": 0.28, "audio_score": 0.50,
            "narrative_score": 0.20, "unique": 0.30, "edit": 0.40, "content": 0.20,
            "usability_score": 0.30, "material_type": "broll_scenery",
            "duration": 5.0, "has_voiceover": False, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.40}, "uniqueness_score": 0.30,
        })
        assert result["is_trash"] is True
        assert "TRASH_008" in result["triggered_rules"]

    def test_saveable_by_uniqueness(self):
        result = _evaluate_trash({
            "tech_score": 0.40, "aesthetic_score": 0.30, "audio_score": 0.50,
            "narrative_score": 0.25, "unique": 0.90, "edit": 0.40, "content": 0.30,
            "usability_score": 0.35, "material_type": "broll_scenery",
            "duration": 5.0, "has_voiceover": False, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.40}, "uniqueness_score": 0.90,
        })
        assert result["trash_level"] == "warn"
        assert len(result["can_be_saved_by"]) > 0

    def test_trash_007_bad_audio_talking_head(self):
        result = _evaluate_trash({
            "tech_score": 0.60, "aesthetic_score": 0.50, "audio_score": 0.15,
            "narrative_score": 0.50, "usability_score": 0.40,
            "material_type": "talking_head", "duration": 10.0,
            "has_voiceover": True, "is_duplicate": False,
            "aesthetic_sub": {"exposure": 0.60}, "uniqueness_score": 0.50,
        })
        assert result["is_trash"] is True
        assert "TRASH_007" in result["triggered_rules"]

    def test_duplicate_detected(self):
        result = _evaluate_trash({
            "tech_score": 0.60, "aesthetic_score": 0.50, "audio_score": 0.50,
            "narrative_score": 0.50, "usability_score": 0.50,
            "material_type": "default", "duration": 5.0,
            "has_voiceover": False, "is_duplicate": True,
            "aesthetic_sub": {"exposure": 0.60}, "uniqueness_score": 0.30,
        })
        assert result["is_trash"] is True
        assert "TRASH_004" in result["triggered_rules"]
