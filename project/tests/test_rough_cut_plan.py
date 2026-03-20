from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.step6_rough_cut import build_rough_segment_plan


def test_build_rough_segment_plan_uses_text_and_highlight():
    script = {
        "clips": [
            {"clip_index": 1, "video_id": "a", "source_start": 0, "source_end": 4, "scene_description": "开场航拍"},
            {"clip_index": 2, "video_id": "b", "source_start": 0, "source_end": 5, "scene_description": "人物特写"},
            {"clip_index": 3, "video_id": "c", "source_start": 1, "source_end": 6, "scene_description": "夜景转场"},
        ],
        "subtitles": [
            {"clip_index": 1, "cn_text": "嗯 我们到了", "start_time": 0.0, "end_time": 1.8},
            {"clip_index": 2, "cn_text": "第一眼就很震撼！", "start_time": 3.9, "end_time": 6.0},
            {"clip_index": 3, "cn_text": "然后继续往前走", "start_time": 8.2, "end_time": 10.0},
        ],
    }
    plan = build_rough_segment_plan(
        script,
        {
            "rough_target_seconds": 6,
            "rough_remove_phrases": "嗯,然后",
        },
    )
    assert plan["strategy"] in {"text+highlight", "highlight", "text"}
    assert len(plan["segment_plan"]) >= 1
    used = sum(seg["duration"] for seg in plan["segment_plan"])
    assert used <= 6.05


def test_build_rough_segment_plan_falls_back_to_highlight_without_subtitles():
    script = {
        "clips": [
            {"clip_index": 1, "video_id": "x", "source_start": 0, "source_end": 3, "scene_description": "开场"},
            {"clip_index": 2, "video_id": "y", "source_start": 1, "source_end": 5, "scene_description": "中段"},
        ],
        "subtitles": [],
    }
    plan = build_rough_segment_plan(script, {"rough_target_seconds": 4})
    assert plan["strategy"] in {"highlight", "fallback"}
    if plan["segment_plan"]:
        assert all(seg["video_id"] for seg in plan["segment_plan"])
