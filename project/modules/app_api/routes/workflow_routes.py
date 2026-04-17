#!/usr/bin/env python3
"""Custom workflow API routes extracted from server.py."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict, List

from flask import Blueprint, jsonify, request

from modules.app_api.param_utils import parse_int_param, parse_str_param, safe_error_response


# ═══════════════════════════════════════════════════════════════
# 工作流模板（Workflow Templates）
# 预置的工作流模板，用户可以实例化后自行编辑
# ═══════════════════════════════════════════════════════════════

_WORKFLOW_TEMPLATES: List[Dict[str, Any]] = [
    {
        "template_id": "material_first_video",
        "name": "素材先行视频制作（10步）",
        "description": (
            "适合 vlog/纪录片/UGC 等先有素材再找故事的制作流程。"
            "10 个阶段覆盖从素材入库到终版导出的完整链路。"
        ),
        "tags": ["video", "vlog", "material-first", "template"],
        "phases": [
            {"phase": 1, "name": "素材入库与深度理解", "name_en": "Material Ingestion & Deep Analysis"},
            {"phase": 2, "name": "叙事发现（选题）", "name_en": "Narrative Discovery"},
            {"phase": 3, "name": "纸面粗剪", "name_en": "Paper Cut"},
            {"phase": 4, "name": "第一次粗剪", "name_en": "First Assembly"},
            {"phase": 5, "name": "脚本细化 + 旁白设计", "name_en": "Script Refinement"},
            {"phase": 6, "name": "第二次粗剪", "name_en": "Revised Assembly"},
            {"phase": 7, "name": "精剪", "name_en": "Fine Cut"},
            {"phase": 8, "name": "声音设计", "name_en": "Sound Design"},
            {"phase": 9, "name": "字幕 + 导出 V1", "name_en": "Subtitles & Export V1"},
            {"phase": 10, "name": "审片 + 精调", "name_en": "Review & Polish"},
        ],
        "workflow": {
            "workflow_id": "material_first_video",
            "name": "素材先行视频制作（10步）",
            "description": (
                "素材先行工作流：深度分析 → 选题 → 纸面粗剪 → 粗剪A → 脚本细化 → "
                "粗剪B → 精剪 → 声音设计 → 字幕导出 → 审片精调"
            ),
            "input_mode": "project",
            "tags": ["video", "vlog", "material-first"],
            "start_step_id": "phase_1_analyze",
            "steps": [
                # ── Phase 1: 素材入库与深度理解 ──
                {
                    "index": 1,
                    "step_id": "phase_1_analyze",
                    "node_type": "action",
                    "name": "1.1 视觉语义分析",
                    "description": "批量分析素材：场景分类、物体检测、构图、光线、运动评分",
                    "capability_id": "image_semantic",
                    "action": "analyze",
                    "input": {"batch": True, "include_visual_features": True},
                    "save_as": "visual_analysis",
                    "next_step_id": "phase_1_transcribe",
                },
                {
                    "index": 2,
                    "step_id": "phase_1_transcribe",
                    "node_type": "action",
                    "name": "1.2 语音转录 + 音频质量评分",
                    "description": "ASR 语音识别、音量/信噪比评分、情绪标注",
                    "capability_id": "subtitle_calibration",
                    "action": "plan",
                    "input": {"mode": "transcribe_and_score", "include_audio_quality": True},
                    "save_as": "transcription_result",
                    "next_step_id": "phase_2_discover",
                },
                # ── Phase 2: 叙事发现（选题） ──
                {
                    "index": 3,
                    "step_id": "phase_2_discover",
                    "node_type": "action",
                    "name": "2. 叙事发现：AI 主题聚类与选题推荐",
                    "description": (
                        "基于视觉+转录结果，聚类素材主题，识别'高光时刻'，"
                        "推荐 1-3 个有完整叙事弧的选题方向"
                    ),
                    "capability_id": "topic_copy",
                    "action": "draft",
                    "input": {
                        "mode": "narrative_discovery",
                        "source": "$visual_analysis",
                        "transcriptions": "$transcription_result",
                        "max_topics": 3,
                    },
                    "save_as": "selected_topic",
                    "next_step_id": "phase_3_paper_cut",
                },
                # ── Phase 3: 纸面粗剪（Paper Cut） ──
                {
                    "index": 4,
                    "step_id": "phase_3_paper_cut",
                    "node_type": "action",
                    "name": "3. 纸面粗剪：生成选片单（不渲染）",
                    "description": (
                        "基于选题，输出 JSON 选片单：哪些片段、精确时间戳、"
                        "在故事中的角色（hook/setup/conflict/climax/resolution）、预估总时长"
                    ),
                    "capability_id": "text_rough_cut",
                    "action": "plan",
                    "input": {
                        "topic": "$selected_topic",
                        "materials": "$visual_analysis",
                        "output_format": "shot_list_json",
                    },
                    "save_as": "paper_cut",
                    "next_step_id": "phase_4_assembly",
                },
                # ── Phase 4: 第一次粗剪（First Assembly） ──
                {
                    "index": 5,
                    "step_id": "phase_4_assembly",
                    "node_type": "action",
                    "name": "4. 第一次粗剪：按选片单裁剪拼接",
                    "description": (
                        "按纸面粗剪的选片单裁剪素材，统一格式（分辨率/帧率/采样率），"
                        "保留原声，音频归一化（loudnorm -16 LUFS + 强制 44100Hz），"
                        "B-roll 静音处理，顺序拼接"
                    ),
                    "capability_id": "short_clip",
                    "action": "plan",
                    "input": {
                        "shot_list": "$paper_cut",
                        "audio_normalize": True,
                        "sample_rate": 44100,
                        "broll_audio": "mute",
                    },
                    "save_as": "first_assembly",
                    "next_step_id": "phase_5_script",
                },
                # ── Phase 5: 脚本细化 + 旁白设计 ──
                {
                    "index": 6,
                    "step_id": "phase_5_script",
                    "node_type": "action",
                    "name": "5. 脚本细化：逐段写文案 + 旁白/字幕文本",
                    "description": (
                        "基于粗剪结果，逐个片段细化脚本："
                        "转录文案校正（ASR 错误修正）、过渡性旁白设计、"
                        "B-roll 的文字说明、双语字幕文本"
                    ),
                    "capability_id": "topic_copy",
                    "action": "draft",
                    "input": {
                        "mode": "script_refinement",
                        "assembly": "$first_assembly",
                        "transcriptions": "$transcription_result",
                        "include_correction": True,
                    },
                    "save_as": "refined_script",
                    "next_step_id": "phase_6_revised",
                },
                # ── Phase 6: 第二次粗剪（Revised Assembly） ──
                {
                    "index": 7,
                    "step_id": "phase_6_revised",
                    "node_type": "action",
                    "name": "6. 第二次粗剪：按细化脚本重新剪辑",
                    "description": (
                        "按细化后的脚本调整片段顺序/时长、插入 B-roll、"
                        "加入 crossfade 转场（0.3s）、检查叙事节奏"
                    ),
                    "capability_id": "refinement",
                    "action": "plan",
                    "input": {
                        "script": "$refined_script",
                        "assembly": "$first_assembly",
                        "crossfade_duration": 0.3,
                    },
                    "save_as": "revised_assembly",
                    "next_step_id": "phase_7_fine_cut",
                },
                # ── Phase 7: 精剪（Fine Cut） ──
                {
                    "index": 8,
                    "step_id": "phase_7_fine_cut",
                    "node_type": "action",
                    "name": "7. 精剪：Hook + 结尾 + 美颜 + 调色",
                    "description": (
                        "添加 3 秒开场 Hook、结尾 CTA/转化元素、"
                        "人物磨皮滤镜（频率分解）、色调统一、"
                        "逻辑性检查（每个转场是否合理）"
                    ),
                    "capability_id": "refinement",
                    "action": "execute",
                    "input": {
                        "source": "$revised_assembly",
                        "add_hook": True,
                        "add_cta": True,
                        "beauty_filter": True,
                        "color_grade": True,
                    },
                    "save_as": "fine_cut",
                    "next_step_id": "phase_8_sound",
                },
                # ── Phase 8: 声音设计（Sound Design） ──
                {
                    "index": 9,
                    "step_id": "phase_8_sound",
                    "node_type": "action",
                    "name": "8. 声音设计：BGM + ducking + 音效",
                    "description": (
                        "选择并混入 BGM（8-12% 音量）、sidechain ducking "
                        "（有人声时 BGM 自动压低）、片段衔接处音频 crossfade、"
                        "首尾 fade in/out、可选音效"
                    ),
                    "capability_id": "audio_voice",
                    "action": "mix_master",
                    "input": {
                        "source": "$fine_cut",
                        "bgm_volume": 0.10,
                        "ducking": True,
                        "crossfade": True,
                        "fade_in": 1.0,
                        "fade_out": 2.0,
                        "sample_rate": 44100,
                    },
                    "save_as": "sound_designed",
                    "next_step_id": "phase_9_subtitle",
                },
                # ── Phase 9: 字幕 + 导出 V1 ──
                {
                    "index": 10,
                    "step_id": "phase_9_subtitle",
                    "node_type": "action",
                    "name": "9. 字幕叠加 + 导出第一版",
                    "description": (
                        "基于校正后的转录文本，按时间戳叠加中文字幕（可选双语）、"
                        "PingFang 字体白字黑边、底部居中、导出 H.264 MP4"
                    ),
                    "capability_id": "subtitle_calibration",
                    "action": "run",
                    "input": {
                        "source": "$sound_designed",
                        "script": "$refined_script",
                        "style": "white_outline",
                        "font": "PingFang",
                        "position": "bottom_center",
                    },
                    "save_as": "v1_export",
                    "next_step_id": "phase_10_review",
                },
                # ── Phase 10: 审片 + 精调 ──
                {
                    "index": 11,
                    "step_id": "phase_10_review",
                    "node_type": "action",
                    "name": "10. 审片清单 + 精调",
                    "description": (
                        "自动检查清单：3秒Hook是否抓人、故事弧完整性、"
                        "音频无跳变/电子噪音、字幕同步、视觉质量一致、"
                        "CTA/转化元素。标记问题后可回退到对应阶段修改"
                    ),
                    "capability_id": "refinement",
                    "action": "collect_master",
                    "input": {
                        "source": "$v1_export",
                        "checklist": [
                            "hook_3s",
                            "story_arc_complete",
                            "audio_no_jumps",
                            "subtitle_sync",
                            "visual_consistency",
                            "cta_present",
                        ],
                    },
                    "save_as": "final_review",
                    "continue_on_error": True,
                },
            ],
        },
    },
]


def get_workflow_templates() -> List[Dict[str, Any]]:
    """返回所有可用的工作流模板（不含完整 workflow 定义）"""
    return [
        {
            "template_id": t["template_id"],
            "name": t["name"],
            "description": t["description"],
            "tags": t.get("tags", []),
            "phases": t.get("phases", []),
            "step_count": len(t.get("workflow", {}).get("steps", [])),
        }
        for t in _WORKFLOW_TEMPLATES
    ]


def get_workflow_template_by_id(template_id: str) -> Dict[str, Any] | None:
    for t in _WORKFLOW_TEMPLATES:
        if t["template_id"] == template_id:
            return deepcopy(t)
    return None


def create_workflow_blueprint(
    *,
    parse_request_context: Callable[[], Dict[str, str]],
    build_custom_workflow_catalog: Callable[[], list],
    normalize_agent_template_id: Callable[[Any], str],
    parse_boolish: Callable[[Any, bool], bool],
    coerce_bool: Callable[[Any, bool], bool],
    custom_workflow_lock_getter: Callable[[], Any],
    read_custom_workflow_store: Callable[[], Dict[str, Dict[str, Any]]],
    save_custom_workflow_store: Callable[[Dict[str, Dict[str, Any]]], Dict[str, Dict[str, Any]]],
    normalize_custom_workflow_payload: Callable[..., Dict[str, Any]],
    resolve_custom_workflow_from_payload: Callable[[Dict[str, Any]], Dict[str, Any]],
    build_custom_workflow_plan: Callable[..., Dict[str, Any]],
    start_custom_workflow_run: Callable[..., Dict[str, Any]],
    read_custom_workflow_runs: Callable[[], list],
    find_custom_workflow_run: Callable[[str], Dict[str, Any] | None],
    build_failed_only_workflow_subset: Callable[..., Dict[str, Any]],
    project_dir_getter: Callable[[], Any],
) -> Blueprint:
    bp = Blueprint("workflow_api", __name__)

    @bp.route("/api/workflows/catalog", methods=["GET"])
    def api_workflows_catalog():
        ctx = parse_request_context()
        catalog = build_custom_workflow_catalog()
        return jsonify({"ok": True, "catalog": catalog, "count": len(catalog), "request_context": ctx})

    @bp.route("/api/workflows", methods=["GET"])
    def api_workflows_list():
        ctx = parse_request_context()
        workflow_id = normalize_agent_template_id(request.args.get("workflow_id", ""))
        include_steps = parse_boolish(request.args.get("include_steps", "true"), default=True)
        with custom_workflow_lock_getter():
            store = read_custom_workflow_store()
        items = list(store.values())
        items.sort(key=lambda x: str(x.get("updated_at", "") or ""), reverse=True)
        if workflow_id:
            items = [x for x in items if str(x.get("workflow_id", "") or "") == workflow_id]
        if not include_steps:
            for item in items:
                item.pop("steps", None)
        return jsonify(
            {
                "ok": True,
                "workflows": items,
                "count": len(items),
                "persisted": project_dir_getter() is not None,
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows", methods=["POST"])
    def api_workflows_upsert():
        payload = request.json or {}
        ctx = parse_request_context()
        try:
            workflow_id = normalize_agent_template_id(payload.get("workflow_id", ""))
            with custom_workflow_lock_getter():
                store = read_custom_workflow_store()
                existing = store.get(workflow_id) if workflow_id else None
                workflow = normalize_custom_workflow_payload(payload, existing=existing)
                old_id = workflow_id if workflow_id and workflow_id in store else ""
                store[workflow["workflow_id"]] = workflow
                if old_id and old_id != workflow["workflow_id"]:
                    store.pop(old_id, None)
                saved = save_custom_workflow_store(store)
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "workflow 保存失败")}), 400
        return jsonify(
            {
                "ok": True,
                "workflow": workflow,
                "count": len(saved),
                "persisted": project_dir_getter() is not None,
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows/plan", methods=["POST"])
    def api_workflows_plan():
        payload = request.json or {}
        ctx = parse_request_context()
        dry_run = coerce_bool(payload.get("dry_run", True), default=True)
        try:
            workflow = resolve_custom_workflow_from_payload(payload)
            plan = build_custom_workflow_plan(workflow=workflow, payload=payload, dry_run=dry_run)
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "workflow 规划失败")}), 400
        return jsonify(
            {
                "ok": True,
                "workflow": {
                    "workflow_id": plan.get("workflow_id"),
                    "name": plan.get("name"),
                    "description": plan.get("description"),
                },
                "plan": plan,
                "plan_summary": {
                    "workflow_id": plan.get("workflow_id"),
                    "total_steps": plan.get("total_steps", 0),
                    "dry_run": dry_run,
                    "start_step_id": (plan.get("graph", {}) or {}).get("start_step_id", ""),
                    "edge_count": (plan.get("graph", {}) or {}).get("edge_count", 0),
                    "has_cycle": bool((plan.get("graph", {}) or {}).get("has_cycle", False)),
                    "enabled_steps": sum(
                        1
                        for step in (plan.get("steps", []) if isinstance(plan.get("steps"), list) else [])
                        if coerce_bool(step.get("enabled", True), default=True)
                    ),
                },
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows/run", methods=["POST"])
    def api_workflows_run():
        from modules.app_api.services.audit_log import audit as _audit
        payload = request.json or {}
        ctx = parse_request_context()
        _actor = f"{ctx.get('actor_type', 'human')}:{ctx.get('actor_id', '')}"
        try:
            workflow = resolve_custom_workflow_from_payload(payload)
            ret = start_custom_workflow_run(
                workflow=workflow,
                payload=payload,
                request_context=ctx,
                source="api/workflows/run",
            )
        except Exception as exc:
            _audit("run", "workflow", None, actor=_actor, status="error", detail={"error": str(exc)})
            return jsonify({"error": safe_error_response(exc, "workflow 执行失败")}), 400
        _audit("run", "workflow", str(ret.get("run_id", "")), actor=_actor)
        ret["request_context"] = ctx
        return jsonify(ret)

    @bp.route("/api/workflows/runs", methods=["GET"])
    def api_workflows_runs():
        ctx = parse_request_context()
        workflow_id = normalize_agent_template_id(request.args.get("workflow_id", ""))
        include_steps = parse_boolish(request.args.get("include_steps", "false"), default=False)
        limit = parse_int_param(request.args.get("limit", "50"), default=50, min_val=1, max_val=200)
        offset = parse_int_param(request.args.get("offset", "0"), default=0, min_val=0)

        with custom_workflow_lock_getter():
            runs = read_custom_workflow_runs()
        if workflow_id:
            runs = [x for x in runs if str(x.get("workflow_id", "") or "") == workflow_id]
        ordered = list(reversed(runs))
        page = ordered[offset : offset + limit]
        has_more = (offset + limit) < len(ordered)
        if not include_steps:
            for item in page:
                item.pop("steps", None)
                item.pop("workflow", None)
                item.pop("plan", None)
        return jsonify(
            {
                "ok": True,
                "items": page,
                "total_count": len(ordered),
                "offset": offset,
                "limit": limit,
                "has_more": has_more,
                "request_context": ctx,
            }
        )

    @bp.route("/api/workflows/runs/<run_id>", methods=["GET"])
    def api_workflows_run_detail(run_id: str):
        ctx = parse_request_context()
        record = find_custom_workflow_run(run_id)
        if not isinstance(record, dict):
            return jsonify({"error": f"run 不存在: {run_id}"}), 404
        return jsonify({"ok": True, "run": record, "request_context": ctx})

    @bp.route("/api/workflows/runs/<run_id>/rerun", methods=["POST"])
    def api_workflows_run_rerun(run_id: str):
        payload = request.json or {}
        ctx = parse_request_context()
        base = find_custom_workflow_run(run_id)
        if not isinstance(base, dict):
            return jsonify({"error": f"run 不存在: {run_id}"}), 404

        workflow_raw = base.get("workflow", {})
        if not isinstance(workflow_raw, dict):
            workflow_raw = {}
        if not workflow_raw:
            workflow_id = normalize_agent_template_id(base.get("workflow_id", ""))
            with custom_workflow_lock_getter():
                workflow_raw = read_custom_workflow_store().get(workflow_id, {})
        if not isinstance(workflow_raw, dict) or not workflow_raw:
            return jsonify({"error": "历史 run 缺少可复用 workflow 定义"}), 400

        rerun_failed_only = coerce_bool(payload.get("rerun_failed_only", False), default=False)
        failed_step_ids = [
            normalize_agent_template_id(step.get("step_id", ""))
            for step in (base.get("steps", []) if isinstance(base.get("steps"), list) else [])
            if parse_str_param(step.get("status", "")).lower() == "error"
        ]
        failed_step_ids = [sid for sid in failed_step_ids if sid]
        try:
            workflow = normalize_custom_workflow_payload(workflow_raw, existing=workflow_raw)
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "workflow 解析失败")}), 400

        if rerun_failed_only:
            try:
                workflow = build_failed_only_workflow_subset(workflow=workflow, base_run=base)
            except Exception as exc:
                return jsonify({"error": safe_error_response(exc, "工作流构建失败")}), 400

        run_payload = deepcopy(payload)
        run_payload["workflow"] = workflow
        included_step_ids = [
            normalize_agent_template_id(step.get("step_id", ""))
            for step in (workflow.get("steps", []) if isinstance(workflow.get("steps"), list) else [])
        ]
        included_step_ids = [sid for sid in included_step_ids if sid]
        run_payload["rerun_context"] = {
            "mode": "failed_with_dependencies" if rerun_failed_only else "full",
            "source_run_id": run_id,
            "failed_step_ids": failed_step_ids,
            "included_step_ids": included_step_ids,
            "start_step_id": normalize_agent_template_id(workflow.get("start_step_id", "")),
        }
        if "input" not in run_payload:
            plan_raw = base.get("plan", {})
            if isinstance(plan_raw, dict) and isinstance(plan_raw.get("input"), dict):
                run_payload["input"] = deepcopy(plan_raw.get("input", {}))
        try:
            ret = start_custom_workflow_run(
                workflow=workflow,
                payload=run_payload,
                request_context=ctx,
                source=f"api/workflows/runs/{run_id}/rerun",
            )
        except Exception as exc:
            from modules.app_api.services.audit_log import audit as _audit
            _audit("rerun", "workflow", run_id, actor=f"{ctx.get('actor_type', 'human')}:{ctx.get('actor_id', '')}", status="error", detail={"error": str(exc)})
            return jsonify({"error": safe_error_response(exc, "workflow 重跑失败")}), 400
        from modules.app_api.services.audit_log import audit as _audit
        _audit("rerun", "workflow", str(ret.get("run_id", "")), actor=f"{ctx.get('actor_type', 'human')}:{ctx.get('actor_id', '')}", detail={"source_run_id": run_id})
        ret["source_run_id"] = run_id
        ret["rerun_context"] = deepcopy(run_payload.get("rerun_context", {}))
        ret["request_context"] = ctx
        return jsonify(ret)

    # ── Workflow Templates ──

    @bp.route("/api/workflows/templates", methods=["GET"])
    def api_workflows_templates():
        """列出所有可用的工作流模板"""
        ctx = parse_request_context()
        templates = get_workflow_templates()
        return jsonify({
            "ok": True,
            "templates": templates,
            "count": len(templates),
            "request_context": ctx,
        })

    @bp.route("/api/workflows/templates/<template_id>", methods=["GET"])
    def api_workflows_template_detail(template_id: str):
        """查看模板详情（含完整 workflow 定义）"""
        ctx = parse_request_context()
        tpl = get_workflow_template_by_id(template_id)
        if not tpl:
            return jsonify({"error": f"模板不存在: {template_id}"}), 404
        return jsonify({
            "ok": True,
            "template": tpl,
            "request_context": ctx,
        })

    @bp.route("/api/workflows/templates/<template_id>/instantiate", methods=["POST"])
    def api_workflows_template_instantiate(template_id: str):
        """
        实例化模板：将模板复制为用户的自定义工作流。
        用户可以在 payload 中覆盖 name/description/tags。
        """
        from modules.app_api.services.audit_log import audit as _audit
        ctx = parse_request_context()
        _actor = f"{ctx.get('actor_type', 'human')}:{ctx.get('actor_id', '')}"
        tpl = get_workflow_template_by_id(template_id)
        if not tpl:
            return jsonify({"error": f"模板不存在: {template_id}"}), 404

        payload = request.json or {}
        workflow_data = deepcopy(tpl["workflow"])

        # 允许用户覆盖名称/描述
        if payload.get("name"):
            workflow_data["name"] = str(payload["name"]).strip()
        if payload.get("description"):
            workflow_data["description"] = str(payload["description"]).strip()
        if payload.get("tags"):
            workflow_data["tags"] = payload["tags"]

        # 生成新的 workflow_id 避免冲突
        import uuid
        workflow_data["workflow_id"] = f"{template_id}_{uuid.uuid4().hex[:6]}"

        try:
            with custom_workflow_lock_getter():
                store = read_custom_workflow_store()
                workflow = normalize_custom_workflow_payload(workflow_data)
                store[workflow["workflow_id"]] = workflow
                saved = save_custom_workflow_store(store)
        except Exception as exc:
            return jsonify({"error": safe_error_response(exc, "模板实例化失败")}), 400

        _audit("instantiate_template", "workflow", workflow["workflow_id"],
               actor=_actor, detail={"template_id": template_id})
        return jsonify({
            "ok": True,
            "workflow": workflow,
            "template_id": template_id,
            "count": len(saved),
            "persisted": project_dir_getter() is not None,
            "request_context": ctx,
        })

    @bp.route("/api/workflows/<workflow_id>", methods=["DELETE"])
    def api_workflows_delete(workflow_id: str):
        from modules.app_api.services.audit_log import audit as _audit
        ctx = parse_request_context()
        _actor = f"{ctx.get('actor_type', 'human')}:{ctx.get('actor_id', '')}"
        workflow_key = normalize_agent_template_id(workflow_id)
        if not workflow_key:
            return jsonify({"error": "workflow_id 无效"}), 400
        with custom_workflow_lock_getter():
            store = read_custom_workflow_store()
            deleted = store.pop(workflow_key, None)
            if deleted is None:
                _audit("delete", "workflow", workflow_key, actor=_actor, status="error", detail={"error": "not found"})
                return jsonify({"error": f"workflow 不存在: {workflow_key}"}), 404
            save_custom_workflow_store(store)
        _audit("delete", "workflow", workflow_key, actor=_actor)
        return jsonify({"ok": True, "deleted": deleted, "request_context": ctx})

    return bp

