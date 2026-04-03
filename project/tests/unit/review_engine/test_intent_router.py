"""Tests for IntentRouter — R3 + R4."""

import json

import pytest

from modules.review_engine.contracts import EditInstruction
from modules.review_engine.exceptions import IntentRouterError
from modules.review_engine.intent_router import (
    INSTRUCTION_SCHEMAS,
    parse_llm_response,
    route_comment,
    validate_instruction,
)


# ── R3: LLM intent parsing + schema validation ──

class TestParseLlmResponse:

    def test_plain_json_array(self):
        text = '[{"type": "remove", "segment_idx": 3}]'
        result = parse_llm_response(text)
        assert len(result) == 1
        assert result[0]["type"] == "remove"

    def test_markdown_code_block(self):
        text = '```json\n[{"type": "extend"}]\n```'
        result = parse_llm_response(text)
        assert len(result) == 1

    def test_single_dict(self):
        text = '{"type": "trim"}'
        result = parse_llm_response(text)
        assert len(result) == 1

    def test_invalid_json(self):
        with pytest.raises(IntentRouterError, match="Cannot parse"):
            parse_llm_response("this is not json at all")


class TestValidateInstruction:

    def test_valid_remove(self):
        inst = validate_instruction({"type": "remove", "segment_idx": 2})
        assert inst.instruction_type == "remove"
        assert inst.segment_idx == 2

    def test_valid_transition_with_params(self):
        inst = validate_instruction({
            "type": "transition",
            "effect": "cross_dissolve",
            "duration_ms": 500,
        })
        assert inst.instruction_type == "transition"
        assert inst.params["effect"] == "cross_dissolve"

    def test_unknown_type(self):
        with pytest.raises(IntentRouterError, match="Unknown instruction type"):
            validate_instruction({"type": "explode"})

    def test_missing_required_param(self):
        with pytest.raises(IntentRouterError, match="missing required param"):
            validate_instruction({"type": "insert"})

    def test_valid_insert(self):
        inst = validate_instruction({
            "type": "insert",
            "source_start_ms": 1000,
            "source_end_ms": 3000,
        })
        assert inst.params["source_start_ms"] == 1000


class TestRouteComment:

    def test_extend_via_llm(self):
        """LLM returns extend instruction."""
        def mock_llm(system, user):
            return '[{"type": "extend", "segment_idx": 3}]'

        result = route_comment("这里砍了", segment_idx=3, llm_caller=mock_llm)
        assert len(result) == 1
        assert result[0].instruction_type == "extend"
        assert result[0].segment_idx == 3

    def test_remove_via_llm(self):
        def mock_llm(system, user):
            return '[{"type": "remove"}]'

        result = route_comment("这段删掉", segment_idx=5, llm_caller=mock_llm)
        assert len(result) == 1
        assert result[0].instruction_type == "remove"
        assert result[0].segment_idx == 5

    def test_multi_instruction(self):
        """Single comment → multiple instructions."""
        def mock_llm(system, user):
            return json.dumps([
                {"type": "remove", "segment_idx": 2},
                {"type": "transition", "effect": "fade_black"},
            ])

        result = route_comment("删掉这段加转场", segment_idx=2, llm_caller=mock_llm)
        assert len(result) == 2
        assert result[0].instruction_type == "remove"
        assert result[1].instruction_type == "transition"

    def test_invalid_schema_from_llm(self):
        def mock_llm(system, user):
            return '[{"type": "banana"}]'

        with pytest.raises(IntentRouterError, match="Unknown instruction type"):
            route_comment("whatever", segment_idx=0, llm_caller=mock_llm)

    def test_llm_call_failure(self):
        def mock_llm(system, user):
            raise ConnectionError("API down")

        with pytest.raises(IntentRouterError, match="LLM call failed"):
            route_comment("test", segment_idx=0, llm_caller=mock_llm)

    def test_keyword_fallback(self):
        """No LLM → keyword matching."""
        result = route_comment("加个转场", segment_idx=1)
        assert len(result) == 1
        assert result[0].instruction_type == "transition"


# ── R4: 14 instruction types ──

class TestAllInstructionTypes:

    @pytest.mark.parametrize("itype", list(INSTRUCTION_SCHEMAS.keys()))
    def test_instruction_type_has_schema(self, itype):
        """Every instruction type has a defined schema."""
        schema = INSTRUCTION_SCHEMAS[itype]
        assert "required" in schema
        assert "optional" in schema

    def test_extend(self):
        inst = validate_instruction({"type": "extend", "duration_ms": 2000})
        assert inst.instruction_type == "extend"

    def test_trim(self):
        inst = validate_instruction({"type": "trim", "trim_start_ms": 500})
        assert inst.instruction_type == "trim"

    def test_split(self):
        inst = validate_instruction({"type": "split", "split_at_ms": 5000})
        assert inst.instruction_type == "split"

    def test_merge(self):
        inst = validate_instruction({"type": "merge", "merge_with_idx": 3})
        assert inst.instruction_type == "merge"

    def test_speed(self):
        inst = validate_instruction({"type": "speed", "factor": 2.0})
        assert inst.instruction_type == "speed"

    def test_broll(self):
        inst = validate_instruction({"type": "broll", "query": "sunset beach"})
        assert inst.instruction_type == "broll"

    def test_subtitle(self):
        inst = validate_instruction({"type": "subtitle", "text": "hello"})
        assert inst.instruction_type == "subtitle"

    def test_speaker(self):
        inst = validate_instruction({"type": "speaker", "action": "switch"})
        assert inst.instruction_type == "speaker"

    def test_hook(self):
        inst = validate_instruction({"type": "hook", "strategy": "auto"})
        assert inst.instruction_type == "hook"

    def test_audio(self):
        inst = validate_instruction({"type": "audio", "action": "denoise"})
        assert inst.instruction_type == "audio"

    def test_reorder(self):
        inst = validate_instruction({"type": "reorder", "target_idx": 0})
        assert inst.instruction_type == "reorder"

    def test_insert(self):
        inst = validate_instruction({
            "type": "insert",
            "source_start_ms": 0,
            "source_end_ms": 5000,
        })
        assert inst.instruction_type == "insert"
