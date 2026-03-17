"""Tests for S1: 退化行为显式通知 — degradation collection in render pipeline.

验证点:
1. beauty.py   — mediapipe 不可用时写入 degradation
2. pipeline.py — 磨皮 fallback / 字幕 fallback / 字体 fallback 写入 degradation
3. pipeline.py — render() 透传 degradations 到各阶段
4. workflow.py — _finish_render 将 degradations 写入 step status
5. 回归: 无退化时 degradations 为空列表
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════════════
# 1. beauty.py 退化收集
# ═══════════════════════════════════════════════════════════════════════


class TestBeautyDegradation:
    """AdvancedBeautyFilter 在 mediapipe 不可用时正确记录退化。"""

    def test_detect_face_no_mediapipe_records_degradation(self):
        """mediapipe 不可用 → degradation 记录 center_region。"""
        import numpy as np
        from modules.step7_final_render import beauty

        # 强制 mediapipe 不可用
        orig = beauty.HAS_MEDIAPIPE
        beauty.HAS_MEDIAPIPE = False
        try:
            bf = beauty.AdvancedBeautyFilter.__new__(beauty.AdvancedBeautyFilter)
            bf.smooth_strength = 0.8
            bf.pore_reduction = 0.6
            bf.acne_threshold = 0.3
            bf._face_detector = None

            img = np.zeros((480, 640, 3), dtype=np.uint8)
            degs: List = []
            regions = bf.detect_face_regions(img, degradations=degs)

            assert len(regions) == 1, "应返回中心区域"
            assert len(degs) == 1
            d = degs[0]
            assert d["feature"] == "face_detection"
            assert d["expected"] == "mediapipe"
            assert d["actual"] == "center_region"
            assert d["severity"] == "warning"
        finally:
            beauty.HAS_MEDIAPIPE = orig

    def test_detect_face_no_mediapipe_no_list_no_crash(self):
        """degradations=None 时不崩溃。"""
        import numpy as np
        from modules.step7_final_render import beauty

        orig = beauty.HAS_MEDIAPIPE
        beauty.HAS_MEDIAPIPE = False
        try:
            bf = beauty.AdvancedBeautyFilter.__new__(beauty.AdvancedBeautyFilter)
            bf.smooth_strength = 0.8
            bf.pore_reduction = 0.6
            bf.acne_threshold = 0.3
            bf._face_detector = None

            img = np.zeros((480, 640, 3), dtype=np.uint8)
            regions = bf.detect_face_regions(img)  # degradations 默认 None
            assert len(regions) == 1
        finally:
            beauty.HAS_MEDIAPIPE = orig

    def test_apply_beauty_filter_passes_degradations(self):
        """apply_beauty_filter 正确透传 degradations 到 detect_face_regions。"""
        import numpy as np
        from modules.step7_final_render import beauty

        orig = beauty.HAS_MEDIAPIPE
        beauty.HAS_MEDIAPIPE = False
        try:
            bf = beauty.AdvancedBeautyFilter.__new__(beauty.AdvancedBeautyFilter)
            bf.smooth_strength = 0.8
            bf.pore_reduction = 0.6
            bf.acne_threshold = 0.0  # 禁用痘印检测简化测试
            bf._face_detector = None

            img = np.zeros((100, 100, 3), dtype=np.uint8)
            degs: List = []
            bf.apply_beauty_filter(img, degradations=degs)

            assert len(degs) == 1
            assert degs[0]["feature"] == "face_detection"
        finally:
            beauty.HAS_MEDIAPIPE = orig

    def test_no_degradation_when_mediapipe_available(self):
        """mediapipe 可用但未检测到人脸 → 无退化（正常空结果）。"""
        import numpy as np
        from modules.step7_final_render import beauty

        if not beauty.HAS_MEDIAPIPE:
            pytest.skip("mediapipe 未安装，跳过此测试")

        bf = beauty.AdvancedBeautyFilter()
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        degs: List = []
        regions = bf.detect_face_regions(img, degradations=degs)
        # mediapipe 存在，即使没有检测到人脸也不应记录退化
        assert len(degs) == 0


# ═══════════════════════════════════════════════════════════════════════
# 2. pipeline.py 退化收集
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineDegradation:
    """RenderPipeline 各阶段退化收集。"""

    def _make_pipeline(self):
        from modules.step7_final_render.pipeline import RenderPipeline
        config = {"width": 320, "height": 240, "fps": 30, "crf": 28, "preset": "ultrafast"}
        return RenderPipeline(config)

    def test_apply_beauty_fallback_records_degradation(self):
        """磨皮异常 → fallback 到 smartblur → 记录退化。"""
        pipeline = self._make_pipeline()
        degs: List = []

        # 让 AdvancedBeautyFilter 构造就抛异常
        with patch("modules.step7_final_render.pipeline.AdvancedBeautyFilter",
                    side_effect=ImportError("test")):
            # 同时 mock _apply_beauty_fallback 避免真实 FFmpeg 调用
            with patch.object(pipeline, "_apply_beauty_fallback", return_value="/fake/beauty.mp4"):
                result = pipeline._apply_beauty("/fake/input.mp4", "/fake/base", True,
                                                degradations=degs)

        assert result == "/fake/beauty.mp4"
        assert len(degs) == 1
        d = degs[0]
        assert d["feature"] == "skin_smooth"
        assert d["expected"] == "frequency_separation"
        assert d["actual"] == "smartblur"
        assert d["severity"] == "warning"

    def test_apply_beauty_no_face_no_degradation(self):
        """has_face=False → 跳过磨皮 → 无退化。"""
        pipeline = self._make_pipeline()
        degs: List = []
        result = pipeline._apply_beauty("/fake/input.mp4", "/fake/base", False,
                                        degradations=degs)
        assert result == "/fake/input.mp4"
        assert len(degs) == 0

    def test_apply_subtitles_pil_fallback_records_degradation(self):
        """libass 不可用 → PIL fallback → 记录退化。"""
        pipeline = self._make_pipeline()
        degs: List = []

        # mock: ffmpeg_has_filter("subtitles") 返回 False
        with patch.object(pipeline, "_ffmpeg_has_filter", return_value=False):
            # mock: HAS_CV2=True, HAS_PIL=True (全局)
            with patch("modules.step7_final_render.pipeline.HAS_CV2", True), \
                 patch("modules.step7_final_render.pipeline.HAS_PIL", True):
                # mock _apply_subtitles_cv2 避免真实处理
                with patch.object(pipeline, "_apply_subtitles_cv2",
                                  return_value="/fake/sub.mp4") as mock_cv2:
                    result = pipeline._apply_subtitles(
                        "/fake/input.mp4",
                        [{"start_time": 0, "end_time": 1, "cn_text": "测试"}],
                        "/fake/base",
                        degradations=degs,
                    )

        assert result == "/fake/sub.mp4"
        assert any(d["feature"] == "subtitle_render" and d["actual"] == "pil_cv2"
                    for d in degs)
        # 确认 degradations 被传递到 _apply_subtitles_cv2
        _, kwargs = mock_cv2.call_args
        assert kwargs.get("degradations") is degs

    def test_apply_subtitles_skip_records_error(self):
        """libass 和 PIL/cv2 都不可用 → 字幕跳过 → 记录 severity=error。"""
        pipeline = self._make_pipeline()
        degs: List = []

        with patch.object(pipeline, "_ffmpeg_has_filter", return_value=False), \
             patch("modules.step7_final_render.pipeline.HAS_CV2", False), \
             patch("modules.step7_final_render.pipeline.HAS_PIL", False):
            result = pipeline._apply_subtitles(
                "/fake/input.mp4",
                [{"start_time": 0, "end_time": 1, "cn_text": "测试"}],
                "/fake/base",
                degradations=degs,
            )

        assert result == "/fake/input.mp4"  # 无字幕，返回原文件
        assert len(degs) == 1
        d = degs[0]
        assert d["feature"] == "subtitle_render"
        assert d["actual"] == "skipped"
        assert d["severity"] == "error"

    def test_apply_subtitles_empty_no_degradation(self):
        """字幕列表为空 → 直接返回 → 无退化。"""
        pipeline = self._make_pipeline()
        degs: List = []
        result = pipeline._apply_subtitles("/fake/input.mp4", [], "/fake/base",
                                           degradations=degs)
        assert result == "/fake/input.mp4"
        assert len(degs) == 0

    def test_public_api_passes_degradations(self):
        """Public API (apply_beauty / apply_subtitles) 正确透传 degradations。"""
        pipeline = self._make_pipeline()
        degs: List = []

        # mock _apply_beauty 的内部调用来验证透传
        with patch.object(pipeline, "_apply_beauty", return_value="/fake/out.mp4") as mock_b:
            pipeline.apply_beauty("/fake/in.mp4", "/fake/base", True, degradations=degs)
            _, kwargs = mock_b.call_args
            assert kwargs["degradations"] is degs

        with patch.object(pipeline, "_apply_subtitles", return_value="/fake/out.mp4") as mock_s:
            pipeline.apply_subtitles("/fake/in.mp4", [], "/fake/base", degradations=degs)
            _, kwargs = mock_s.call_args
            assert kwargs["degradations"] is degs


# ═══════════════════════════════════════════════════════════════════════
# 3. workflow.py _finish_render 退化传递
# ═══════════════════════════════════════════════════════════════════════


class TestWorkflowDegradation:
    """WorkflowRunner._finish_render 将 degradations 写入 step status。"""

    def _make_runner(self, tmp_path):
        """构造最小可运行的 WorkflowRunner。"""
        from modules.workflow_engine.workflow import WorkflowRunner, WorkflowState

        # 构造最小 project state
        project_dir = tmp_path / "test_project"
        project_dir.mkdir()
        state_data = {
            "version": 1,
            "project_dir": str(project_dir),
            "videos_dir": str(tmp_path / "videos"),
            "config": {},
            "current_step": 7,
            "steps": {str(i): {"status": "done", "review_status": None} for i in range(1, 8)},
        }
        state_file = project_dir / "workflow.json"
        state_file.write_text(json.dumps(state_data), encoding="utf-8")

        state = WorkflowState(project_dir)
        state.load()

        runner = WorkflowRunner.__new__(WorkflowRunner)
        runner.project_dir = project_dir
        runner.state = state
        runner._cancelled = False
        return runner

    def test_finish_render_stores_degradations(self, tmp_path):
        """degradations 非空 → 写入 step[7]。"""
        runner = self._make_runner(tmp_path)
        out_dir = tmp_path / "test_project" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final.mp4").touch()

        degs = [
            {"feature": "subtitle_render", "expected": "libass", "actual": "pil_cv2",
             "reason": "test", "severity": "warning"},
        ]

        with patch("subprocess.run"):  # mock open final.mp4
            runner._finish_render(out_dir, degradations=degs)

        step = runner.state.get_step(7)
        assert step["status"] == "done"
        assert "degradations" in step
        assert len(step["degradations"]) == 1
        assert step["degradations"][0]["feature"] == "subtitle_render"

    def test_finish_render_no_degradations_no_field(self, tmp_path):
        """degradations 为空 → step 中无 degradations 字段。"""
        runner = self._make_runner(tmp_path)
        out_dir = tmp_path / "test_project" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final.mp4").touch()

        with patch("subprocess.run"):
            runner._finish_render(out_dir, degradations=[])

        step = runner.state.get_step(7)
        assert step["status"] == "done"
        assert "degradations" not in step

    def test_finish_render_none_degradations_no_field(self, tmp_path):
        """degradations=None → step 中无 degradations 字段。"""
        runner = self._make_runner(tmp_path)
        out_dir = tmp_path / "test_project" / "output"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "final.mp4").touch()

        with patch("subprocess.run"):
            runner._finish_render(out_dir)

        step = runner.state.get_step(7)
        assert step["status"] == "done"
        assert "degradations" not in step


# ═══════════════════════════════════════════════════════════════════════
# 4. 退化事件结构验证
# ═══════════════════════════════════════════════════════════════════════


class TestDegradationStructure:
    """验证退化事件 dict 结构完整性。"""

    REQUIRED_KEYS = {"feature", "expected", "actual", "reason", "severity"}
    VALID_SEVERITIES = {"info", "warning", "error"}

    def _collect_all_degradation_events(self):
        """触发所有已知退化路径，收集事件。"""
        import numpy as np
        from modules.step7_final_render import beauty
        from modules.step7_final_render.pipeline import RenderPipeline

        all_degs = []

        # 1. beauty: mediapipe 不可用
        orig_mp = beauty.HAS_MEDIAPIPE
        beauty.HAS_MEDIAPIPE = False
        try:
            bf = beauty.AdvancedBeautyFilter.__new__(beauty.AdvancedBeautyFilter)
            bf.smooth_strength = 0.8
            bf.pore_reduction = 0.6
            bf.acne_threshold = 0.3
            bf._face_detector = None
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            degs: list = []
            bf.detect_face_regions(img, degradations=degs)
            all_degs.extend(degs)
        finally:
            beauty.HAS_MEDIAPIPE = orig_mp

        # 2. pipeline: beauty fallback
        pipeline = RenderPipeline({"width": 320, "height": 240, "fps": 30})
        degs2: list = []
        with patch("modules.step7_final_render.pipeline.AdvancedBeautyFilter",
                    side_effect=RuntimeError("test")):
            with patch.object(pipeline, "_apply_beauty_fallback", return_value="/x"):
                pipeline._apply_beauty("/x", "/b", True, degradations=degs2)
        all_degs.extend(degs2)

        # 3. pipeline: subtitle skip
        degs3: list = []
        with patch.object(pipeline, "_ffmpeg_has_filter", return_value=False), \
             patch("modules.step7_final_render.pipeline.HAS_CV2", False), \
             patch("modules.step7_final_render.pipeline.HAS_PIL", False):
            pipeline._apply_subtitles("/x", [{"start_time": 0, "end_time": 1, "cn_text": "t"}],
                                      "/b", degradations=degs3)
        all_degs.extend(degs3)

        return all_degs

    def test_all_events_have_required_keys(self):
        """所有退化事件必须包含 feature/expected/actual/reason/severity。"""
        events = self._collect_all_degradation_events()
        assert len(events) >= 3, f"期望至少 3 个退化事件，实际 {len(events)}"
        for i, d in enumerate(events):
            missing = self.REQUIRED_KEYS - set(d.keys())
            assert not missing, f"事件 {i} 缺少字段: {missing}, event={d}"

    def test_all_events_have_valid_severity(self):
        """severity 必须是 info/warning/error 之一。"""
        events = self._collect_all_degradation_events()
        for i, d in enumerate(events):
            assert d["severity"] in self.VALID_SEVERITIES, \
                f"事件 {i} severity 无效: {d['severity']}"

    def test_all_events_have_nonempty_reason(self):
        """reason 必须非空字符串。"""
        events = self._collect_all_degradation_events()
        for i, d in enumerate(events):
            assert isinstance(d["reason"], str) and len(d["reason"]) > 0, \
                f"事件 {i} reason 为空: {d}"


# ═══════════════════════════════════════════════════════════════════════
# 5. 回归：正常路径无退化
# ═══════════════════════════════════════════════════════════════════════


class TestNoDegradationRegression:
    """正常路径不应产生退化记录。"""

    def test_beauty_skip_no_face(self):
        from modules.step7_final_render.pipeline import RenderPipeline
        pipeline = RenderPipeline({"width": 320, "height": 240, "fps": 30})
        degs: list = []
        result = pipeline._apply_beauty("/fake", "/base", False, degradations=degs)
        assert len(degs) == 0

    def test_subtitles_empty_list(self):
        from modules.step7_final_render.pipeline import RenderPipeline
        pipeline = RenderPipeline({"width": 320, "height": 240, "fps": 30})
        degs: list = []
        result = pipeline._apply_subtitles("/fake", [], "/base", degradations=degs)
        assert len(degs) == 0

    def test_beauty_success_no_degradation(self):
        """磨皮成功时不应记录退化。"""
        from modules.step7_final_render.pipeline import RenderPipeline
        pipeline = RenderPipeline({"width": 320, "height": 240, "fps": 30})
        degs: list = []

        mock_beauty = MagicMock()
        mock_beauty.process_video.return_value = "/fake/beauty.mp4"

        with patch("modules.step7_final_render.pipeline.AdvancedBeautyFilter",
                    return_value=mock_beauty):
            result = pipeline._apply_beauty("/fake/in.mp4", "/fake/base", True,
                                            degradations=degs)

        assert result == "/fake/base_beauty.mp4"
        assert len(degs) == 0
