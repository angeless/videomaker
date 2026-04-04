"""Integration tests for VLM pipeline — end-to-end (v0.17.0 R18)."""

import json

import pytest

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(not _HAS_PIL, reason="PIL not available")

from modules.adapters.vlm_adapter import StubVLMAdapter, VLMResponse
from modules.review_engine.region_extractor import RegionExtractor
from modules.review_engine.vlm_analyzer import AnalysisContext, VLMAnalyzer
from modules.review_engine.intent_router import route_comment
from modules.review_engine.frame_diagnostics import FrameDiagnostics
from modules.review_engine.review_store import ReviewStore


class TestE2EPipeline:
    """End-to-end: strokes → extract → VLM → describe → intent route."""

    def test_full_pipeline(self):
        # 1. Create a frame
        frame = Image.new("RGB", (1920, 1080), "gray")

        # 2. Simulate strokes (user drew a rectangle)
        strokes = [{
            "tool": "rect",
            "points": [{"x": 0.3, "y": 0.3}, {"x": 0.6, "y": 0.6}],
            "color": "#ff0000",
            "lineWidth": 3,
        }]

        # 3. Extract region
        extractor = RegionExtractor()
        extraction = extractor.extract(frame, strokes, canvas_size=(1920, 1080))
        assert extraction.tool_type == "rect"
        assert extraction.region_image.size[0] > 0

        # 4. VLM analyze (stub)
        adapter = StubVLMAdapter(fixed_response=json.dumps({
            "summary": "一个红色的logo",
            "objects": ["logo"],
            "scene_type": "graphic",
            "visual_issues": [],
        }))
        analyzer = VLMAnalyzer(adapter=adapter)
        ctx = AnalysisContext(video_type="speech", timestamp_ms=5000)
        desc = analyzer.describe_region(extraction.region_image, ctx)
        assert "logo" in desc.objects

        # 5. Reference resolution
        resolved = VLMAnalyzer.resolve_references("这个太大了", desc)
        assert "logo" in resolved

        # 6. Route through IntentRouter with visual context
        visual_ctx = {
            "summary": desc.summary,
            "objects": desc.objects,
            "scene_type": desc.scene_type,
            "visual_issues": desc.visual_issues,
        }

        captured_prompts = []
        def mock_llm(system, user):
            captured_prompts.append(user)
            return '[{"type": "trim", "segment_idx": 1}]'

        instructions = route_comment(
            resolved, segment_idx=1,
            llm_caller=mock_llm,
            visual_context=visual_ctx,
        )
        assert len(instructions) >= 1
        assert "logo" in captured_prompts[0]


class TestDegradationPath:
    """All features degrade gracefully when VLM unavailable."""

    def test_full_degradation(self):
        frame = Image.new("RGB", (800, 600), "white")

        # VLM not available — all should still work
        analyzer = VLMAnalyzer(adapter=None)
        desc = analyzer.describe_region(frame, AnalysisContext())
        assert desc.summary == "[画面区域]"

        # IntentRouter without visual context
        result = route_comment("删掉这段", segment_idx=0)
        assert len(result) >= 1

        # Diagnostics without VLM — exposure check still works
        diag = FrameDiagnostics(vlm_adapter=None)
        issues = diag.diagnose_frame(frame)
        # May or may not find issues, but should not crash
        assert isinstance(issues, list)


class TestAPIDescribe:
    """API integration: POST describe → structured response."""

    def test_api_describe_integration(self, tmp_path):
        import base64
        import io
        from flask import Flask
        from modules.app_api.routes.vlm_routes import create_vlm_blueprint

        store = ReviewStore(str(tmp_path / "test.db"))
        sid = store.create_session(
            project_path="/tmp", video_path="/tmp/v.mp4", video_type="speech",
        )
        adapter = StubVLMAdapter(fixed_response=json.dumps({
            "summary": "test", "objects": [], "scene_type": "", "visual_issues": [],
        }))

        app = Flask(__name__)
        bp = create_vlm_blueprint(
            review_store_getter=lambda: store,
            vlm_adapter_getter=lambda: adapter,
        )
        app.register_blueprint(bp)
        app.config["TESTING"] = True

        img = Image.new("RGB", (100, 100), "blue")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        with app.test_client() as client:
            resp = client.post(
                f"/api/review/{sid}/vlm/describe",
                json={"frame_base64": b64, "strokes": []},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"]
            assert "description" in data


class TestAPIDiagnose:
    """API integration: POST diagnose → diagnostics list."""

    def test_api_diagnose_integration(self, tmp_path):
        import base64
        import io
        from flask import Flask
        from modules.app_api.routes.vlm_routes import create_vlm_blueprint

        store = ReviewStore(str(tmp_path / "test.db"))
        sid = store.create_session(
            project_path="/tmp", video_path="/tmp/v.mp4", video_type="speech",
        )

        app = Flask(__name__)
        bp = create_vlm_blueprint(
            review_store_getter=lambda: store,
            vlm_adapter_getter=lambda: None,  # No VLM
        )
        app.register_blueprint(bp)
        app.config["TESTING"] = True

        # Even without VLM, exposure check runs
        img = Image.new("RGB", (100, 100), (250, 250, 250))  # bright
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode()

        with app.test_client() as client:
            resp = client.post(
                f"/api/review/{sid}/vlm/diagnose",
                json={"frame_base64": b64},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert "diagnostics" in data


class TestBackwardCompat:
    """Existing review_store functionality unaffected by migration."""

    def test_existing_comment_flow(self, tmp_path):
        store = ReviewStore(str(tmp_path / "test.db"))
        sid = store.create_session(
            project_path="/tmp", video_path="/tmp/v.mp4", video_type="mixed",
        )
        # Old-style comment (no visual_context)
        cid = store.add_comment(
            session_id=sid, version=1, time_start_ms=1000,
            comment_type="note", text="old style",
        )
        comments = store.list_comments(sid)
        assert len(comments) == 1
        assert comments[0]["visual_context"] is None
