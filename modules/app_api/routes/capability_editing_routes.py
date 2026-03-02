#!/usr/bin/env python3
"""Capability routes: topic/copy, text rough cut, short clip, refinement."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List
import json
import tempfile

from flask import Blueprint, jsonify, request


def _extract_text_rough_subtitle_spans(script: Dict) -> List[Dict]:
    out: List[Dict] = []
    subtitles = script.get("subtitles", []) if isinstance(script, dict) else []
    idx = 0
    for sub in subtitles:
        if not isinstance(sub, dict):
            continue
        text = str(sub.get("cn_text") or sub.get("text") or "").strip()
        if not text:
            continue
        try:
            st = float(sub.get("start_time"))
            et = float(sub.get("end_time"))
        except Exception:
            continue
        if et <= st:
            continue
        idx += 1
        out.append(
            {
                "index": idx,
                "start": round(st, 3),
                "end": round(et, 3),
                "duration_s": round(et - st, 3),
                "text": text,
            }
        )
    return out


def create_editing_capability_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    workflow_state_getter: Callable[[], Any],
    request_json_any_method: Callable[[], Dict[str, Any]],
    parse_capability_input_mode: Callable[[Any, str], str],
    parse_boolish: Callable[[Any, bool], bool],
    project_data_path: Callable[[str], Any],
    slugify: Callable[[str], str],
    read_project_json: Callable[[str, Any], Any],
    coerce_materials_input: Callable[[Dict[str, Any], str], Any],
    extract_material_semantics: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
    coerce_script_input: Callable[[Dict[str, Any], str], Dict[str, Any]],
    capability_base_dir: Callable[[str], Any],
    resolve_path_with_base: Callable[[str, Any], Any],
    parse_str_list: Callable[[Any], List[str]],
) -> Blueprint:
    bp = Blueprint("cap_editing_api", __name__)

    @bp.route("/api/capabilities/topic_library", methods=["GET"])
    def api_topic_library_list():
        payload = request_json_any_method()
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        from modules.capabilities.topic_library import list_topics, search_topics

        query = str(request.args.get("q", payload.get("q", "")) or "").strip()
        category = str(request.args.get("category", payload.get("category", "")) or "").strip() or None
        tags_raw = str(request.args.get("tags", payload.get("tags", "")) or "").strip()
        tags = [x.strip() for x in tags_raw.replace("，", ",").split(",") if x.strip()] if tags_raw else None
        include_disabled = parse_boolish(
            request.args.get("include_disabled", payload.get("include_disabled", "false")),
            default=False,
        )
        try:
            limit = int(request.args.get("limit", payload.get("limit", "60")) or "60")
        except Exception:
            limit = 60
        limit = max(1, min(limit, 300))

        if input_mode == "project":
            db_path = project_data_path("topic_library.db")
            assert db_path is not None
            if query or category or tags:
                items = search_topics(str(db_path), query=query, category=category, tags=tags, limit=limit)
                if not include_disabled:
                    items = [x for x in items if x.get("enabled", True)]
            else:
                items = list_topics(str(db_path), enabled_only=not include_disabled, limit=limit)
            return jsonify({"ok": True, "input_mode": input_mode, "topics": items, "db_path": str(db_path)})

        topics_raw = payload.get("topics", [])
        topic_items = [x for x in topics_raw if isinstance(x, dict)]
        query_l = query.lower()
        matched: List[Dict[str, Any]] = []
        for item in topic_items:
            enabled = bool(item.get("enabled", True))
            if not include_disabled and not enabled:
                continue
            if category and str(item.get("category", "") or "").strip().lower() != category.lower():
                continue
            item_tags = item.get("tags", [])
            item_tags_norm = []
            if isinstance(item_tags, list):
                item_tags_norm = [str(x).strip().lower() for x in item_tags if str(x).strip()]
            if tags:
                wanted = [x.lower() for x in tags]
                if not all(tag in item_tags_norm for tag in wanted):
                    continue
            if query_l:
                hay = " ".join(
                    [
                        str(item.get("slug", "") or ""),
                        str(item.get("title", "") or ""),
                        str(item.get("category", "") or ""),
                        " ".join(item_tags_norm),
                    ]
                ).lower()
                if query_l not in hay:
                    continue
            matched.append(item)
            if len(matched) >= limit:
                break
        return jsonify({"ok": True, "input_mode": input_mode, "topics": matched, "db_path": None})

    @bp.route("/api/capabilities/topic_library", methods=["POST"])
    def api_topic_library_upsert():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        title = str(payload.get("title", "") or "").strip()
        if not title:
            return jsonify({"error": "title 不能为空"}), 400

        from modules.capabilities.topic_library import TopicTemplate, upsert_topic

        slug = str(payload.get("slug", "") or "").strip() or slugify(title)
        topic = TopicTemplate(
            slug=slug,
            title=title,
            category=str(payload.get("category", "travel") or "travel"),
            audience=str(payload.get("audience", "general") or "general"),
            hook_style=str(payload.get("hook_style", "story") or "story"),
            outline_template=str(payload.get("outline_template", "") or ""),
            tags=payload.get("tags", []) if isinstance(payload.get("tags"), list) else [],
            enabled=bool(payload.get("enabled", True)),
        )
        topic_dict = {
            "slug": topic.slug,
            "title": topic.title,
            "category": topic.category,
            "audience": topic.audience,
            "hook_style": topic.hook_style,
            "outline_template": topic.outline_template,
            "tags": list(topic.tags),
            "enabled": bool(topic.enabled),
        }
        if input_mode == "project":
            db_path = project_data_path("topic_library.db")
            assert db_path is not None
            upsert_topic(str(db_path), topic)
            return jsonify({"ok": True, "input_mode": input_mode, "slug": slug, "topic": topic_dict, "db_path": str(db_path)})

        topics_raw = payload.get("topics", [])
        topic_items = [dict(x) for x in topics_raw if isinstance(x, dict)]
        replaced = False
        for idx, item in enumerate(topic_items):
            if str(item.get("slug", "") or "").strip() == slug:
                topic_items[idx] = topic_dict
                replaced = True
                break
        if not replaced:
            topic_items.append(topic_dict)
        return jsonify({"ok": True, "input_mode": input_mode, "slug": slug, "topic": topic_dict, "topics": topic_items, "db_path": None})

    @bp.route("/api/capabilities/topic_library/bootstrap", methods=["POST"])
    def api_topic_library_bootstrap():
        materials = read_project_json("materials.json", fallback={})
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        if isinstance(payload.get("materials"), dict):
            materials = payload.get("materials")
        if not isinstance(materials, dict) or not materials:
            if input_mode == "project":
                return jsonify({"error": "data/materials.json 不存在或为空"}), 400
            return jsonify({"error": "inline 模式缺少 materials"}), 400

        from modules.capabilities.topic_library import TopicTemplate, upsert_topic

        db_path = project_data_path("topic_library.db") if input_mode == "project" else None
        created = 0
        seen = set()
        generated: List[Dict[str, Any]] = []
        for _, vdata in materials.items():
            sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic"), dict) else {}
            setting = str(sem.get("setting", "") or "").strip() or "旅行场景"
            activity = str(sem.get("activity", "") or "").strip() or "探索"
            mood = str(sem.get("mood", "") or "").strip() or "真实"
            title = f"{setting}·{activity}高光"
            slug = slugify(f"{setting}-{activity}")
            if slug in seen:
                continue
            seen.add(slug)
            outline = f"开场给出{setting}强画面，中段呈现{activity}过程，结尾落在{mood}情绪变化。"
            topic = TopicTemplate(
                slug=slug,
                title=title,
                category="travel",
                audience="short_video",
                hook_style="story",
                outline_template=outline,
                tags=[setting, activity, mood],
                enabled=True,
            )
            if db_path is not None:
                upsert_topic(str(db_path), topic)
            generated.append(
                {
                    "slug": topic.slug,
                    "title": topic.title,
                    "category": topic.category,
                    "audience": topic.audience,
                    "hook_style": topic.hook_style,
                    "outline_template": topic.outline_template,
                    "tags": list(topic.tags),
                    "enabled": bool(topic.enabled),
                }
            )
            created += 1
            if created >= 30:
                break

        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "created": created,
                "topics": generated,
                "db_path": str(db_path) if db_path is not None else None,
            }
        )

    @bp.route("/api/capabilities/topic_copy/draft", methods=["POST"])
    def api_topic_copy_draft():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        slug = str(payload.get("slug", "") or "").strip()
        try:
            target_duration_s = int(payload.get("target_duration_s", 60) or 60)
        except (TypeError, ValueError):
            target_duration_s = 60
        target_duration_s = max(1, min(target_duration_s, 600))

        from modules.capabilities.topic_library import TopicTemplate, get_topic, list_topics
        from modules.capabilities.topic_copy import build_copy_payload

        topic_dict = payload.get("topic") if isinstance(payload.get("topic"), dict) else None
        if input_mode == "project":
            db_path = project_data_path("topic_library.db")
            assert db_path is not None
            if not topic_dict:
                topic_dict = get_topic(str(db_path), slug) if slug else None
            if not topic_dict:
                defaults = list_topics(str(db_path), enabled_only=True, limit=1)
                if defaults:
                    topic_dict = defaults[0]
        else:
            topic_pool = payload.get("topics", [])
            if not topic_dict and isinstance(topic_pool, list):
                if slug:
                    topic_dict = next(
                        (x for x in topic_pool if isinstance(x, dict) and str(x.get("slug", "") or "").strip() == slug),
                        None,
                    )
                if not topic_dict:
                    topic_dict = next((x for x in topic_pool if isinstance(x, dict)), None)
        if not topic_dict:
            return jsonify({"error": "未找到 topic，请先创建或传正确 slug"}), 404

        topic = TopicTemplate(
            slug=topic_dict.get("slug", slug),
            title=topic_dict.get("title", "Untitled"),
            category=topic_dict.get("category", "travel"),
            audience=topic_dict.get("audience", "general"),
            hook_style=topic_dict.get("hook_style", "story"),
            outline_template=topic_dict.get("outline_template", ""),
            tags=topic_dict.get("tags", []),
            enabled=bool(topic_dict.get("enabled", True)),
        )
        semantics_raw = payload.get("material_semantics", payload.get("semantics"))
        if isinstance(semantics_raw, list):
            semantics = [x for x in semantics_raw if isinstance(x, dict)]
        else:
            materials = coerce_materials_input(payload, input_mode=input_mode)
            semantics = extract_material_semantics(materials if isinstance(materials, dict) else {})
        draft = build_copy_payload(topic, semantics, target_duration_s=target_duration_s)
        out_path = project_data_path("topic_copy_draft.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            out_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "input_mode": input_mode, "draft": draft, "output": str(out_path) if out_path else None})

    @bp.route("/api/capabilities/text_rough_cut/source", methods=["GET"])
    def api_text_rough_cut_source():
        payload = request_json_any_method()
        input_mode = parse_capability_input_mode(
            request.args.get("input_mode", payload.get("input_mode", "project")),
            default="project",
        )
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400

        script = coerce_script_input(payload, input_mode=input_mode)
        if not script and input_mode == "inline":
            return jsonify({"error": "inline 模式缺少 script/subtitles"}), 400
        spans = _extract_text_rough_subtitle_spans(script)
        out_path = project_data_path("text_rough_source.json") if input_mode == "project" else None
        if out_path is not None and project_dir_getter() is not None:
            out_path.write_text(json.dumps({"spans": spans}, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "spans": spans,
                "total": len(spans),
                "output": str(out_path) if out_path else None,
            }
        )

    @bp.route("/api/capabilities/text_rough_cut/plan", methods=["POST"])
    def api_text_rough_cut_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        removed = payload.get("removed_phrases", None)
        target_duration_raw = payload.get("target_duration_s", 15)
        merge_gap_raw = payload.get("merge_gap_s", 0.15)
        keep_indexes_raw = payload.get("keep_span_indexes", None)
        drop_indexes_raw = payload.get("drop_span_indexes", None)
        apply_removed_phrases = bool(payload.get("apply_removed_phrases", True))

        from modules.capabilities.text_rough_cut import (
            TranscriptSpan,
            build_text_rough_cut_plan,
            coerce_span_indexes,
        )

        span_items: List[Dict[str, Any]] = []
        span_items_raw = payload.get("spans", [])
        if isinstance(span_items_raw, list) and span_items_raw:
            for idx, item in enumerate(span_items_raw, start=1):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or item.get("cn_text") or "").strip()
                if not text:
                    continue
                try:
                    start = float(item.get("start", item.get("start_time", 0.0)))
                    end = float(item.get("end", item.get("end_time", 0.0)))
                except Exception:
                    continue
                if end <= start:
                    continue
                span_items.append({"index": idx, "start": round(start, 3), "end": round(end, 3), "text": text})
        if not span_items:
            script = coerce_script_input(payload, input_mode=input_mode)
            span_items = _extract_text_rough_subtitle_spans(script)
        if not span_items and input_mode == "inline":
            return jsonify({"error": "缺少可用于粗剪的字幕分段（spans/script/subtitles）"}), 400

        spans = [
            TranscriptSpan(
                start=float(item.get("start", 0.0)),
                end=float(item.get("end", 0.0)),
                text=str(item.get("text", "") or ""),
                confidence=1.0,
            )
            for item in span_items
        ]
        if isinstance(removed, str):
            removed = [x.strip() for x in removed.replace("，", ",").split(",") if x.strip()]
        elif not isinstance(removed, list):
            removed = None

        if target_duration_raw in {None, ""}:
            target_duration_s = None
        else:
            try:
                target_duration_s = float(target_duration_raw)
            except Exception:
                target_duration_s = 15.0
        try:
            merge_gap_s = float(merge_gap_raw)
        except Exception:
            merge_gap_s = 0.15
        keep_indexes = coerce_span_indexes(keep_indexes_raw, max_index=len(spans))
        drop_indexes = coerce_span_indexes(drop_indexes_raw, max_index=len(spans))

        plan = build_text_rough_cut_plan(
            spans=spans,
            removed_phrases=removed,
            target_duration_s=target_duration_s,
            merge_gap_s=merge_gap_s,
            keep_span_indexes=keep_indexes,
            drop_span_indexes=drop_indexes,
            apply_removed_phrases=apply_removed_phrases,
        )
        out_path = project_data_path("text_rough_plan.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "input_mode": input_mode, "plan": plan, "output": str(out_path) if out_path else None})

    @bp.route("/api/capabilities/short_clip/plan", methods=["POST"])
    def api_short_clip_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        try:
            target_duration_s = float(payload.get("target_duration_s", 30) or 30)
        except (TypeError, ValueError):
            target_duration_s = 30.0
        target_duration_s = max(1.0, min(target_duration_s, 600.0))
        try:
            max_clips = int(payload.get("max_clips", 8) or 8)
        except (TypeError, ValueError):
            max_clips = 8
        max_clips = max(1, min(max_clips, 50))

        from modules.capabilities.short_clip import HighlightCandidate, highlights_to_timeline, pick_highlights

        candidates: List[HighlightCandidate] = []
        candidate_items = payload.get("candidates", [])
        if isinstance(candidate_items, list) and candidate_items:
            for item in candidate_items:
                if not isinstance(item, dict):
                    continue
                try:
                    start = float(item.get("start", item.get("start_time", 0.0)))
                    end = float(item.get("end", item.get("end_time", 0.0)))
                except Exception:
                    continue
                if end <= start:
                    continue
                try:
                    score = float(item.get("score", item.get("highlight_score", 0.55)) or 0.55)
                except Exception:
                    score = 0.55
                candidates.append(
                    HighlightCandidate(
                        start=start,
                        end=end,
                        score=score,
                        reason=str(item.get("reason", item.get("scene_description", "")) or ""),
                    )
                )
        if not candidates:
            script = coerce_script_input(payload, input_mode=input_mode)
            cursor = 0.0
            for idx, clip in enumerate(script.get("clips", []), start=1):
                if not isinstance(clip, dict):
                    continue
                start = cursor
                try:
                    src_start = float(clip.get("source_start", 0) or 0)
                except Exception:
                    src_start = 0.0
                src_end = clip.get("source_end")
                if src_end is None:
                    try:
                        src_end = src_start + float(clip.get("duration", 5) or 5)
                    except Exception:
                        src_end = src_start + 5.0
                try:
                    duration = max(float(src_end) - src_start, 0.1)
                except Exception:
                    duration = 5.0
                end = start + duration
                cursor = end
                try:
                    score = float(clip.get("highlight_score", 0.55) or 0.55)
                except Exception:
                    score = 0.55
                if idx == 1:
                    score += 0.12
                if clip.get("has_face"):
                    score += 0.08
                candidates.append(HighlightCandidate(start=start, end=end, score=score, reason=str(clip.get("scene_description", ""))))
        if not candidates:
            return jsonify({"error": "缺少候选片段（candidates/script/clips）"}), 400

        picked = pick_highlights(candidates, target_duration_s=target_duration_s, max_clips=max_clips)
        timeline = highlights_to_timeline(picked)
        out_path = project_data_path("short_clip_plan.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            out_path.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "input_mode": input_mode, "plan": timeline, "output": str(out_path) if out_path else None})

    @bp.route("/api/capabilities/refinement/plan", methods=["POST"])
    def api_refinement_plan():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            # keep compatibility: return plan in inline mode when project missing
            input_mode = "inline"
        from modules.capabilities.refinement import build_refine_payload

        plan = build_refine_payload(
            style=str(payload.get("style", "travel_story") or "travel_story"),
            editor=str(payload.get("editor", "internal_ffmpeg") or "internal_ffmpeg"),
            quality=str(payload.get("quality", "high") or "high"),
        )
        if input_mode == "project" and project_dir_getter() is not None and bool(payload.get("store_result", True)):
            out_path = project_data_path("refinement_plan.json")
            if out_path is not None:
                out_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify({"ok": True, "input_mode": input_mode, "plan": plan})

    @bp.route("/api/capabilities/refinement/connectors", methods=["GET"])
    def api_refinement_connectors():
        payload = request_json_any_method()
        editor = str(request.args.get("editor", payload.get("editor", "")) or "").strip()
        from modules.adapters.nle_connector import list_nle_connector_statuses

        statuses = list_nle_connector_statuses([editor] if editor else None)
        return jsonify(
            {
                "ok": True,
                "default_editor": "finalcut",
                "connectors": statuses,
            }
        )

    @bp.route("/api/capabilities/refinement/handoff", methods=["POST"])
    def api_refinement_handoff():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        editor = str(payload.get("editor", "finalcut") or "finalcut").strip().lower()
        title = str(payload.get("title", "VideoEditer Timeline") or "VideoEditer Timeline").strip()
        try:
            fps = int(payload.get("fps", 30) or 30)
        except (TypeError, ValueError):
            fps = 30
        fps = max(1, min(fps, 120))
        from modules.adapters.nle_connector import get_nle_connector, normalize_nle_editor

        script = coerce_script_input(payload, input_mode=input_mode)
        if not script or not script.get("clips"):
            return jsonify({"error": "缺少脚本片段，请先生成 script_draft/script_matched"}), 400
        materials = coerce_materials_input(payload, input_mode=input_mode)
        if not isinstance(materials, dict) or not materials:
            return jsonify({"error": "缺少 materials.json"}), 400

        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        if output_dir_raw:
            out_dir = resolve_path_with_base(output_dir_raw, base_dir=capability_base_dir(input_mode))
        elif input_mode == "project" and project_dir_getter() is not None:
            out_dir = project_dir_getter() / "data" / "nle_handoff" / editor
        else:
            out_dir = Path(tempfile.mkdtemp(prefix=f"videoeditor_nle_handoff_{editor}_"))
        editor_norm = normalize_nle_editor(editor)
        connector = get_nle_connector(editor_norm)
        connector_status = connector.detect().to_dict()
        try:
            ret = connector.create_handoff(
                script=script,
                materials=materials,
                output_dir=str(out_dir),
                title=title,
                fps=fps,
            )
        except Exception as exc:
            return jsonify({"error": f"NLE 交接包生成失败: {exc}"}), 500
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "handoff": ret,
                "connector": connector_status,
            }
        )

    @bp.route("/api/capabilities/refinement/execute", methods=["POST"])
    def api_refinement_execute():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        editor = str(payload.get("editor", "finalcut") or "finalcut").strip().lower()
        title = str(payload.get("title", "VideoEditer Timeline") or "VideoEditer Timeline").strip()
        try:
            fps = int(payload.get("fps", 30) or 30)
        except (TypeError, ValueError):
            fps = 30
        fps = max(1, min(fps, 120))
        launch = bool(payload.get("launch", True))
        app_name = str(payload.get("app_name", "") or "").strip()
        try:
            timeout_seconds = float(payload.get("timeout_seconds", 20) or 20)
        except (TypeError, ValueError):
            timeout_seconds = 20.0
        timeout_seconds = max(1.0, min(timeout_seconds, 300.0))
        from modules.adapters.nle_connector import get_nle_connector, normalize_nle_editor

        script = coerce_script_input(payload, input_mode=input_mode)
        if not script or not script.get("clips"):
            return jsonify({"error": "缺少脚本片段，请先生成 script_draft/script_matched"}), 400
        materials = coerce_materials_input(payload, input_mode=input_mode)
        if not isinstance(materials, dict) or not materials:
            return jsonify({"error": "缺少 materials.json"}), 400

        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        if output_dir_raw:
            out_dir = resolve_path_with_base(output_dir_raw, base_dir=capability_base_dir(input_mode))
        elif input_mode == "project" and project_dir_getter() is not None:
            out_dir = project_dir_getter() / "data" / "nle_handoff" / editor
        else:
            out_dir = Path(tempfile.mkdtemp(prefix=f"videoeditor_nle_execute_{editor}_"))
        editor_norm = normalize_nle_editor(editor)
        connector = get_nle_connector(editor_norm)
        connector_status = connector.detect().to_dict()
        try:
            handoff = connector.create_handoff(
                script=script,
                materials=materials,
                output_dir=str(out_dir),
                title=title,
                fps=fps,
            )
        except Exception as exc:
            return jsonify({"error": f"NLE 交接包生成失败: {exc}"}), 500

        launch_result = None
        if launch:
            try:
                launch_result = connector.launch(
                    handoff,
                    app_name=app_name,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:
                return jsonify({"error": f"NLE 启动失败: {exc}", "handoff": handoff}), 500
            if launch_result.get("status") != "done":
                return jsonify({"error": "NLE 启动失败", "handoff": handoff, "launch": launch_result}), 500

        output = {
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "handoff": handoff,
            "launch": launch_result,
        }
        out_path = project_data_path("refinement_execute_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "handoff": handoff,
                "launch": launch_result,
                "connector": connector_status,
                "output": str(out_path) if out_path else None,
            }
        )

    @bp.route("/api/capabilities/refinement/collect_master", methods=["POST"])
    def api_refinement_collect_master():
        payload = request.json or {}
        input_mode = parse_capability_input_mode(payload.get("input_mode", "project"), default="project")
        if input_mode == "project" and project_dir_getter() is None:
            return jsonify({"error": "项目未加载"}), 400
        base_dir = capability_base_dir(input_mode)
        editor = str(payload.get("editor", "finalcut") or "finalcut").strip().lower()
        source_video_raw = str(payload.get("source_video", "") or "").strip()
        output_name = str(payload.get("output_name", "final.mp4") or "final.mp4").strip() or "final.mp4"
        copy_mode = str(payload.get("copy_mode", "copy") or "copy").strip().lower()
        if copy_mode not in {"copy", "move"}:
            copy_mode = "copy"

        from modules.adapters.nle_connector import get_nle_connector, normalize_nle_editor
        from modules.capabilities.nle_handoff import find_latest_video_candidate

        source_video = None
        if source_video_raw:
            source_video = resolve_path_with_base(source_video_raw, base_dir=base_dir)
        else:
            search_dirs = parse_str_list(payload.get("search_dirs"))
            if not search_dirs:
                if input_mode == "project" and project_dir_getter() is not None:
                    search_dirs = [
                        str(project_dir_getter() / "data" / "nle_handoff" / editor),
                        str(project_dir_getter() / "data" / "nle_handoff"),
                        str(project_dir_getter() / "output"),
                    ]
                else:
                    search_dirs = [
                        str(base_dir / "data" / "nle_handoff" / editor),
                        str(base_dir / "data" / "nle_handoff"),
                        str(base_dir / "output"),
                    ]
            resolved_dirs = []
            for item in search_dirs:
                p = resolve_path_with_base(item, base_dir=base_dir)
                resolved_dirs.append(str(p))
            guessed = find_latest_video_candidate(resolved_dirs)
            if guessed:
                source_video = Path(guessed)
            else:
                return jsonify({"error": "未找到可导回的视频，请手动选择 source_video"}), 404

        output_dir_raw = str(payload.get("output_dir", "") or "").strip()
        if output_dir_raw:
            output_dir = resolve_path_with_base(output_dir_raw, base_dir=base_dir)
        elif input_mode == "project" and project_dir_getter() is not None:
            output_dir = project_dir_getter() / "output"
        else:
            output_dir = (base_dir / "output").resolve()

        editor_norm = normalize_nle_editor(editor)
        connector = get_nle_connector(editor_norm)
        connector_status = connector.detect().to_dict()
        try:
            result = connector.collect_master(
                source_video=str(source_video),
                output_dir=str(output_dir),
                output_name=output_name,
                copy_mode=copy_mode,
            )
        except Exception as exc:
            return jsonify({"error": f"导回成片失败: {exc}"}), 400

        record = {
            "editor": editor,
            "requested_at": datetime.now().isoformat(timespec="seconds"),
            "source_video": result.get("source_video"),
            "output_video": result.get("output_video"),
            "mode": result.get("mode"),
            "size": result.get("size"),
        }
        ws = workflow_state_getter()
        if input_mode == "project" and ws is not None:
            nle_history = ws.data.get("nle_master_history", [])
            if not isinstance(nle_history, list):
                nle_history = []
            nle_history.append(record)
            ws.data["nle_master_history"] = nle_history[-50:]
            ws.save()

        out_path = project_data_path("refinement_collect_last.json") if input_mode == "project" else None
        if out_path is not None and bool(payload.get("store_result", True)):
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "collect": result,
                "record": record,
                "connector": connector_status,
                "output": str(out_path) if out_path else None,
            }
        )

    return bp
