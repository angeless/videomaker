#!/usr/bin/env python3
"""Capability routes: subtitle calibration, image semantic, article expansion."""

from __future__ import annotations

from typing import Any, Callable, Dict, List
import json

from flask import Blueprint, jsonify, request

from modules.step2_topic_planning.ai_client import AIClient


def create_text_semantic_capability_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    parse_capability_input_mode: Callable[[Any, str], str],
    read_script_json: Callable[[], Dict[str, Any]],
    extract_subtitles_from_script: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
    script_to_text_blocks: Callable[[Dict[str, Any]], Dict[str, str]],
    load_ai_settings: Callable[[], Dict[str, Any]],
    library_getter: Callable[[], Any],
    project_data_path: Callable[[str], Any],
) -> Blueprint:
    bp = Blueprint("cap_text_semantic_api", __name__)

    def _build_subtitle_translator(payload: Dict[str, Any], warnings: List[str]):
        use_llm = bool(payload.get("use_llm", False))
        if not use_llm:
            return None, {"enabled": False, "provider": "", "model": "", "fallback": True}

        ai = load_ai_settings()
        provider = str(payload.get("llm_provider") or ai.get("provider") or "").strip().lower()
        model = str(payload.get("llm_model") or ai.get("ai_model") or "").strip()
        base_url = str(payload.get("llm_base_url") or ai.get("ai_base_url") or "").strip()
        api_key = str(payload.get("llm_api_key") or "").strip()
        if not api_key:
            if provider == "anthropic":
                api_key = str(ai.get("anthropic_api_key") or "").strip()
            else:
                api_key = str(ai.get("openai_api_key") or "").strip()
        if not provider:
            provider = "openai" if api_key else ""
        if not api_key:
            warnings.append("字幕翻译 use_llm=true 但未配置 API Key，已降级为规则翻译。")
            return None, {"enabled": True, "provider": provider, "model": model, "fallback": True}

        client = AIClient(
            provider=provider or None,
            api_key=api_key or None,
            base_url=base_url or None,
            model=model or None,
            temperature=0.2,
            max_tokens=240,
        )

        warn_once = {"emitted": False}

        def _translator(text: str, target_lang: str) -> str:
            target = "English" if str(target_lang).lower().startswith("en") else "中文"
            prompt = (
                f"请将以下字幕翻译为 {target}。只输出翻译结果，不要解释，不要加引号。\\n"
                f"字幕：{text}"
            )
            try:
                result = client.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system="你是字幕翻译助手，优先口语化、自然、简短。",
                )
                return str(result or "").strip()
            except Exception as exc:
                if not warn_once["emitted"]:
                    warnings.append(f"字幕翻译 LLM 调用失败，已降级规则翻译: {exc}")
                    warn_once["emitted"] = True
                from modules.capabilities.subtitle_calibration import _fallback_translate  # lazy import

                return _fallback_translate(text, "en" if str(target_lang).lower().startswith("en") else "zh")

        return _translator, {
            "enabled": True,
            "provider": str(client.provider or ""),
            "model": str(client.model or ""),
            "fallback": False,
        }

    @bp.route("/api/capabilities/subtitle_calibration/plan", methods=["POST"])
    def api_subtitle_calibration_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        subtitles = payload.get("subtitles", [])
        if not isinstance(subtitles, list):
            subtitles = []
        if input_mode == "project" and not subtitles:
            subtitles = extract_subtitles_from_script(read_script_json())
        if not subtitles:
            return jsonify({"error": "缺少 subtitles，input_mode=project 时可自动读取脚本字幕"}), 400

        mode = str(payload.get("mode", "text_only") or "text_only").strip().lower()
        if mode not in {"text_only", "timeline_align"}:
            mode = "text_only"
        translation = str(payload.get("translation", "off") or "off").strip().lower()
        if translation not in {"off", "zh2en", "en2zh", "bilingual"}:
            translation = "off"

        from modules.capabilities.subtitle_calibration import calibrate_subtitles

        preview = calibrate_subtitles(
            subtitles=subtitles,
            mode=mode,
            translation="off",
            source_audio=str(payload.get("source_audio", "") or "").strip(),
            translator=None,
        )
        plan = {
            "mode": mode,
            "translation": translation,
            "total_subtitles": int(preview.get("quality_report", {}).get("total_subtitles", 0) or 0),
            "timeline_change_estimate": int(preview.get("quality_report", {}).get("timeline_changed_count", 0) or 0),
            "overlap_before": int(preview.get("quality_report", {}).get("overlap_before", 0) or 0),
            "overlap_after": int(preview.get("quality_report", {}).get("overlap_after", 0) or 0),
        }
        return jsonify({"ok": True, "input_mode": input_mode, "plan": plan, "preview": preview})

    @bp.route("/api/capabilities/subtitle_calibration/run", methods=["POST"])
    def api_subtitle_calibration_run():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        subtitles = payload.get("subtitles", [])
        if not isinstance(subtitles, list):
            subtitles = []
        if input_mode == "project" and not subtitles:
            subtitles = extract_subtitles_from_script(read_script_json())
        if not subtitles:
            return jsonify({"error": "缺少 subtitles，input_mode=project 时可自动读取脚本字幕"}), 400

        mode = str(payload.get("mode", "text_only") or "text_only").strip().lower()
        if mode not in {"text_only", "timeline_align"}:
            mode = "text_only"
        translation = str(payload.get("translation", "off") or "off").strip().lower()
        if translation not in {"off", "zh2en", "en2zh", "bilingual"}:
            translation = "off"
        source_audio = str(payload.get("source_audio", "") or "").strip()

        from modules.capabilities.subtitle_calibration import calibrate_subtitles

        warnings: List[str] = []
        translator, llm_meta = _build_subtitle_translator(payload, warnings)
        result = calibrate_subtitles(
            subtitles=subtitles,
            mode=mode,
            translation=translation,
            source_audio=source_audio,
            translator=translator,
        )
        if project_dir_getter() is not None and bool(payload.get("store_result", True)):
            out_path = project_data_path("subtitle_calibration_last.json")
            if out_path is not None:
                out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "llm": llm_meta,
                "result": result,
                "warnings": warnings,
            }
        )

    @bp.route("/api/capabilities/image_semantic/analyze", methods=["POST"])
    def api_image_semantic_analyze():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "inline"), default="inline")
        try:
            max_images = int(payload.get("max_images", payload.get("limit", 1200)) or 1200)
        except Exception:
            max_images = 1200
        max_images = max(1, min(max_images, 8000))

        image_paths_raw = payload.get("image_paths", payload.get("images", payload.get("paths", [])))
        if isinstance(image_paths_raw, str):
            image_paths = [x.strip() for x in image_paths_raw.replace("，", ",").split(",") if x.strip()]
        elif isinstance(image_paths_raw, list):
            image_paths = [str(x).strip() for x in image_paths_raw if str(x).strip()]
        else:
            image_paths = []
        if input_mode == "project" and not image_paths:
            latest = library_getter().search_assets(
                query="",
                limit=min(max_images, 500),
                offset=0,
                retrieval_mode="hybrid",
                media_type="image",
            )
            image_paths = [str(x.get("path") or "").strip() for x in latest if isinstance(x, dict) and str(x.get("path") or "").strip()]

        from modules.capabilities.image_semantic import analyze_images

        result = analyze_images(
            image_paths,
            library=library_getter(),
            max_images=max_images,
            retrieval_mode=str(payload.get("retrieval_mode", "hybrid") or "hybrid"),
            auto_ingest=bool(payload.get("auto_ingest", True)),
        )
        if project_dir_getter() is not None and bool(payload.get("store_result", True)):
            out = project_data_path("image_semantic_analyze_last.json")
            if out is not None:
                out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "input_mode": input_mode, "max_images": max_images, "result": result})

    @bp.route("/api/capabilities/image_semantic/search", methods=["POST"])
    def api_image_semantic_search():
        payload = request.json or {}
        query = str(payload.get("query", "") or "").strip()
        from modules.capabilities.image_semantic import search_images

        result = search_images(
            query,
            library=library_getter(),
            limit=int(payload.get("limit", 30) or 30),
            offset=int(payload.get("offset", 0) or 0),
            retrieval_mode=str(payload.get("retrieval_mode", "hybrid") or "hybrid"),
        )
        if project_dir_getter() is not None and bool(payload.get("store_result", True)):
            out = project_data_path("image_semantic_search_last.json")
            if out is not None:
                out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "result": result})

    @bp.route("/api/capabilities/article_expand/generate", methods=["POST"])
    def api_article_expand_generate():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "inline"), default="inline")
        source_text = str(payload.get("source_text", payload.get("text", "")) or "").strip()
        key_points = payload.get("key_points", payload.get("points", []))
        if input_mode == "project" and not source_text:
            script_blocks = script_to_text_blocks(read_script_json())
            source_text = str(script_blocks.get("script_text", "") or "").strip()
            if not key_points:
                key_points = script_blocks.get("voiceover_text", "")

        warnings: List[str] = []
        use_llm = bool(payload.get("use_llm", False))
        text_generator = None
        llm_meta = {"enabled": False, "provider": "", "model": "", "fallback": True}
        if use_llm:
            ai = load_ai_settings()
            provider = str(payload.get("llm_provider") or ai.get("provider") or "").strip().lower()
            model = str(payload.get("llm_model") or ai.get("ai_model") or "").strip()
            base_url = str(payload.get("llm_base_url") or ai.get("ai_base_url") or "").strip()
            api_key = str(payload.get("llm_api_key") or "").strip()
            if not api_key:
                if provider == "anthropic":
                    api_key = str(ai.get("anthropic_api_key") or "").strip()
                else:
                    api_key = str(ai.get("openai_api_key") or "").strip()
            if api_key:
                client = AIClient(
                    provider=provider or None,
                    api_key=api_key,
                    base_url=base_url or None,
                    model=model or None,
                    temperature=0.4,
                    max_tokens=800,
                )
                llm_meta = {
                    "enabled": True,
                    "provider": str(client.provider or ""),
                    "model": str(client.model or ""),
                    "fallback": False,
                }

                warn_once = {"emitted": False}

                def _gen(field: str, prompt: str) -> str:
                    try:
                        return str(
                            client.chat(
                                messages=[{"role": "user", "content": prompt}],
                                system=f"你是微信公众号文章编辑助手，当前字段={field}。",
                            )
                            or ""
                        ).strip()
                    except Exception as exc:
                        if not warn_once["emitted"]:
                            warnings.append(f"article_expand LLM 调用失败，已降级规则生成: {exc}")
                            warn_once["emitted"] = True
                        return ""

                text_generator = _gen
            else:
                warnings.append("article_expand use_llm=true 但未配置 API Key，已降级规则生成。")
                llm_meta = {"enabled": True, "provider": provider, "model": model, "fallback": True}

        from modules.capabilities.article_expand import generate_article_expansion

        result = generate_article_expansion(
            source_text=source_text,
            key_points=key_points,
            tone=str(payload.get("tone", "professional") or "professional"),
            length_target=int(payload.get("length_target", 1200) or 1200),
            title_count=int(payload.get("title_count", 5) or 5),
            text_generator=text_generator,
        )
        if project_dir_getter() is not None and bool(payload.get("store_result", True)):
            out = project_data_path("article_expand_last.json")
            if out is not None:
                out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "input_mode": input_mode, "llm": llm_meta, "result": result, "warnings": warnings})

    return bp
