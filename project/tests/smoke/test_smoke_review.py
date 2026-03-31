"""Smoke tests — verify core modules import and basic contracts work."""

import pytest


class TestImports:
    """All review_engine modules must import without errors."""

    def test_smoke_import_contracts(self):
        from modules.review_engine.contracts import (
            VideoType, DetectionResult, TranscriptDoc, Paragraph, Word,
            Segment, FillerMark, RetakeMark, SceneInfo, EditInstruction,
        )
        assert VideoType.SPEECH.value == "speech"

    def test_smoke_import_exceptions(self):
        from modules.review_engine.exceptions import (
            ReviewEngineError, VideoDetectionError, TranscriptError,
            RenderError, ArtifactNotFoundError,
        )
        assert issubclass(ReviewEngineError, Exception)

    def test_smoke_import_video_detector(self):
        from modules.review_engine.video_detector import detect_video_type
        assert callable(detect_video_type)

    def test_smoke_import_transcript_editor(self):
        from modules.review_engine.transcript_editor import transcribe_to_doc
        assert callable(transcribe_to_doc)

    def test_smoke_import_filler_detector(self):
        from modules.review_engine.filler_detector import auto_mark_fillers
        assert callable(auto_mark_fillers)

    def test_smoke_import_bad_take_detector(self):
        from modules.review_engine.bad_take_detector import auto_detect_bad_takes
        assert callable(auto_detect_bad_takes)

    def test_smoke_import_scene_segmenter(self):
        from modules.review_engine.scene_segmenter import segment_scenes
        assert callable(segment_scenes)

    def test_smoke_import_mixed_editor(self):
        from modules.review_engine.mixed_editor import separate_segments, merge_segments
        assert callable(separate_segments)

    def test_smoke_import_render_pipeline(self):
        from modules.review_engine.render_pipeline import render_rough_cut
        assert callable(render_rough_cut)

    def test_smoke_import_review_store(self):
        from modules.review_engine.review_store import ReviewStore
        assert callable(ReviewStore)

    def test_smoke_import_artifact_store(self):
        from modules.review_engine.artifact_store import ArtifactStore
        assert callable(ArtifactStore)

    def test_smoke_import_public_api(self):
        """The __init__.py exports all contracts and exceptions."""
        from modules.review_engine import (
            VideoType, DetectionResult, Segment, SceneInfo,
            ReviewEngineError, RenderError, ArtifactNotFoundError,
        )
        assert VideoType.SCENIC.value == "scenic"


class TestContractCreation:
    """Verify dataclass contracts are constructable."""

    def test_smoke_create_word(self):
        from modules.review_engine.contracts import Word
        w = Word(text="hello", start_ms=0, end_ms=500)
        assert w.text == "hello"
        assert w.confidence == 1.0  # default confidence

    def test_smoke_create_segment(self):
        from modules.review_engine.contracts import Segment
        s = Segment(source_path="/v.mp4", start_ms=0, end_ms=5000, segment_type="keep")
        assert s.label is None

    def test_smoke_create_scene_info(self):
        from modules.review_engine.contracts import SceneInfo
        s = SceneInfo(scene_idx=0, start_ms=0, end_ms=3000, duration_ms=3000)
        assert s.selected is False

    def test_smoke_exception_hierarchy(self):
        from modules.exceptions import VideoEditorError
        from modules.review_engine.exceptions import ReviewEngineError, RenderError
        assert issubclass(ReviewEngineError, VideoEditorError)
        assert issubclass(RenderError, ReviewEngineError)
