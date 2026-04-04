"""Smoke tests — verify all v0.16.0 review_engine modules import and are callable."""

import pytest


class TestV016Imports:
    """All v0.16.0 review_engine modules must import without errors."""

    def test_smoke_import_comment_resolver(self):
        from modules.review_engine.comment_resolver import (
            resolve_comment, detect_gaps, ResolvedComment, GapInfo,
        )
        assert callable(resolve_comment)
        assert callable(detect_gaps)

    def test_smoke_import_intent_router(self):
        from modules.review_engine.intent_router import (
            route_comment, validate_instruction, INSTRUCTION_SCHEMAS,
        )
        assert callable(route_comment)
        assert callable(validate_instruction)
        assert len(INSTRUCTION_SCHEMAS) >= 14

    def test_smoke_import_edit_planner(self):
        from modules.review_engine.edit_planner import (
            apply_instructions, detect_conflicts, EditPlan,
        )
        assert callable(apply_instructions)
        assert callable(detect_conflicts)

    def test_smoke_import_node_manager(self):
        from modules.review_engine.node_manager import NodeManager, NODE_GRAPH
        nm = NodeManager()
        order = nm.get_execution_order()
        assert len(order) == len(NODE_GRAPH)
        assert order[0] == "transcode"  # source node first

    def test_smoke_import_render_incremental(self):
        from modules.review_engine.render_pipeline import render_incremental
        assert callable(render_incremental)

    def test_smoke_import_audio_enhancer(self):
        from modules.review_engine.audio_enhancer import (
            enhance_audio, AudioConfig,
        )
        assert callable(enhance_audio)
        cfg = AudioConfig()
        assert cfg.denoise is True

    def test_smoke_import_tts_voiceover(self):
        from modules.review_engine.tts_voiceover import (
            generate_voiceover, VOICE_PRESETS,
        )
        assert callable(generate_voiceover)
        assert "zh-female" in VOICE_PRESETS

    def test_smoke_import_bgm_selector(self):
        from modules.review_engine.bgm_selector import (
            analyze_beats, beat_sync_edits, mix_bgm,
        )
        assert callable(analyze_beats)
        assert callable(beat_sync_edits)
        assert callable(mix_bgm)

    def test_smoke_import_transition_effects(self):
        from modules.review_engine.transition_effects import (
            apply_transition, EFFECTS,
        )
        assert callable(apply_transition)
        assert len(EFFECTS) >= 12

    def test_smoke_import_stock_media(self):
        from modules.review_engine.stock_media import search_stock, download_stock
        assert callable(search_stock)
        assert callable(download_stock)

    def test_smoke_import_social_reframe(self):
        from modules.review_engine.social_reframe import reframe, PLATFORMS
        assert callable(reframe)
        assert "tiktok" in PLATFORMS
        assert "youtube" in PLATFORMS

    def test_smoke_import_style_skills(self):
        from modules.review_engine.style_skills import (
            save_style, load_style, list_styles, StyleConfig,
        )
        assert callable(save_style)
        assert callable(load_style)
        cfg = StyleConfig(name="test")
        assert cfg.color_grade == "natural"

    def test_smoke_import_comment_exporter(self):
        from modules.review_engine.comment_exporter import export_comments
        assert callable(export_comments)

    def test_smoke_import_enhance_routes(self):
        from modules.app_api.routes.enhance_routes import create_enhance_blueprint
        assert callable(create_enhance_blueprint)

    def test_smoke_import_stock_routes(self):
        from modules.app_api.routes.stock_routes import create_stock_blueprint
        assert callable(create_stock_blueprint)

    def test_smoke_import_style_routes(self):
        from modules.app_api.routes.style_routes import create_style_blueprint
        assert callable(create_style_blueprint)
