#!/usr/bin/env python3
"""Legacy project workflow routes."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict
import json
import subprocess
import uuid

from flask import Blueprint, abort, jsonify, request, send_file

from modules.app_api.param_utils import parse_str_param, write_json_result
from modules.workflow_engine.workflow import WorkflowRunner, WorkflowState


def create_legacy_project_blueprint(
    *,
    project_dir_getter: Callable[[], Any],
    workflow_state_getter: Callable[[], Any],
    jobs_getter: Callable[[], Dict[str, Dict[str, Any]]],
    prepare_project_dirs: Callable[[Path], None],
    library_getter: Callable[[], Any],
    default_project_config: Callable[[Any], Dict[str, Any]],
    load_state: Callable[[Path], None],
    remember_last_project: Callable[[Path], None],
    recent_projects_getter: Callable[[], list] = lambda: [],
    state_dict: Callable[[], Dict[str, Any]],
    run_in_bg: Callable[..., None],
    choose_path: Callable[[str], Dict[str, Any]],
) -> Blueprint:
    bp = Blueprint("legacy_project_api", __name__)

    @bp.route("/api/project/list")
    def api_project_list():
        return jsonify({"ok": True, "projects": recent_projects_getter()})

    @bp.route("/api/init", methods=["POST"])
    def api_init():
        data = request.json or {}
        videos_dir = (data.get("videos_dir", "") or "").strip()
        project_dir = (data.get("project_dir", "") or "").strip()
        selected_uids = data.get("selected_video_uids") or []
        if isinstance(selected_uids, str):
            selected_uids = [x.strip() for x in selected_uids.split(",") if x.strip()]

        if selected_uids:
            if len(selected_uids) > 50:
                return jsonify({"error": "一次最多选择 50 个视频素材"}), 400

            if not project_dir:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                project_dir = str(Path.cwd() / f"proj_selected_{ts}")

            project_path = Path(project_dir).expanduser().resolve()
            prepare_project_dirs(project_path)

            materials = library_getter().build_workflow_materials(selected_uids)
            if not materials:
                return jsonify({"error": "未找到可用素材，请先在素材库分析并选择素材"}), 400

            resolved_uids = [uid for uid in selected_uids if uid in materials]
            if not resolved_uids:
                return jsonify({"error": "所选素材均不可用（仅支持视频素材，且需本地路径可访问）"}), 400
            if len(resolved_uids) != len(selected_uids):
                return jsonify({"error": "所选素材中包含图片或不可用文件；制作流程当前仅支持视频"}), 400

            selected_paths = [materials[uid]["path"] for uid in resolved_uids]
            config = default_project_config({
                "material_source": "global_library",
                "selected_video_uids": resolved_uids,
                "selected_video_paths": selected_paths,
            })
            ws = WorkflowState.create(project_path, "", config)

            materials_path = project_path / "data" / "materials.json"
            write_json_result(materials_path, materials)

            ws.data["steps"]["1"].update({
                "status": "done",
                "review_status": "approved",
                "output": "data/materials.json",
                "video_count": len(resolved_uids),
                "completed_at": datetime.now().isoformat(),
            })
            ws.data["steps"]["2"]["status"] = "pending"
            ws.data["current_step"] = 2
            ws.save()

            load_state(project_path)
            remember_last_project(project_path)
            return jsonify({
                "ok": True,
                "project_dir": str(project_path),
                "selected_count": len(resolved_uids),
                **state_dict(),
            })

        if not videos_dir:
            return jsonify({"error": "videos_dir 不能为空（或传 selected_video_uids）"}), 400

        videos_path = Path(videos_dir).expanduser().resolve()
        if not videos_path.exists():
            return jsonify({"error": f"素材目录不存在: {videos_dir}"}), 400

        if not project_dir:
            project_dir = str(videos_path.parent / f"proj_{videos_path.name}")

        project_path = Path(project_dir).expanduser().resolve()
        prepare_project_dirs(project_path)
        ws = WorkflowState.create(project_path, str(videos_path), default_project_config())
        ws.save()
        load_state(project_path)
        remember_last_project(project_path)
        return jsonify({"ok": True, "project_dir": str(project_path), **state_dict()})

    @bp.route("/api/open_project", methods=["POST"])
    def api_open_project():
        data = request.json or {}
        project_dir = data.get("project_dir", "").strip()
        if not project_dir:
            return jsonify({"error": "project_dir 不能为空"}), 400
        p = Path(project_dir)
        if not (p / "workflow.json").exists():
            return jsonify({"error": "目录内没有 workflow.json，不是有效项目"}), 400
        load_state(p)
        remember_last_project(p)
        return jsonify({"ok": True, **state_dict()})

    @bp.route("/api/approve/<int:step>", methods=["POST"])
    def api_approve(step: int):
        """
        审核通过某一步骤。
        Body JSON 包含该步骤 review 文件需要的字段，
        服务端直接写入 review 文件 YAML 块并触发运行。
        """
        ws = workflow_state_getter()
        project_dir = project_dir_getter()
        if ws is None or project_dir is None:
            return jsonify({"error": "项目未加载"}), 400

        data = request.json or {}
        review_map = {
            1: "reviews/01_materials.md",
            2: "reviews/02_topics.md",
            3: "reviews/03_script.md",
            4: "reviews/04_matching.md",
            5: None,   # 自动通过
            6: "reviews/05_render_options.md",
        }
        review_rel = review_map.get(step)

        if review_rel:
            review_path = project_dir / review_rel
            if not review_path.exists():
                return jsonify({
                    "error": f"审核文件不存在: {review_rel}（请先运行 Step {step} 生成审核文件）"
                }), 404

            content = review_path.read_text(encoding="utf-8")

            yaml_lines = ["approved: true"]
            for k, v in data.items():
                if k == "approved":
                    continue
                if isinstance(v, str):
                    safe = v.replace('"', '\\"')
                    yaml_lines.append(f'{k}: "{safe}"')
                elif isinstance(v, bool):
                    yaml_lines.append(f"{k}: {'true' if v else 'false'}")
                else:
                    yaml_lines.append(f"{k}: {v}")
            new_yaml = "\n".join(yaml_lines)

            import re
            new_content = re.sub(
                r"```yaml\n.*?```",
                f"```yaml\n{new_yaml}\n```",
                content,
                count=1,
                flags=re.DOTALL,
            )
            review_path.write_text(new_content, encoding="utf-8")

        if step == 6 and isinstance(data, dict):
            render_cfg = ws.data.setdefault("config", {}).setdefault("render", {})
            for k, v in data.items():
                if k == "approved":
                    continue
                render_cfg[k] = v
            ws.save()

        job_id = str(uuid.uuid4())[:8]
        jobs = jobs_getter()

        def _do_run():
            def _should_cancel():
                return bool(jobs.get(job_id, {}).get("cancel_requested"))

            def _progress(payload: Dict):
                if not isinstance(payload, dict):
                    return
                progress = payload.get("progress")
                message = parse_str_param(payload.get("message", ""))
                if isinstance(progress, (int, float)):
                    jobs[job_id]["progress"] = max(0, min(99, int(progress)))
                if message:
                    jobs[job_id]["log"].append(message)
                    jobs[job_id]["log"] = jobs[job_id]["log"][-120:]

            runner = WorkflowRunner(ws, should_cancel=_should_cancel, progress_callback=_progress)
            if review_rel:
                approved, parsed = runner.parse_review(step)
                if approved:
                    ws.approve_review(step, parsed)
            target = ws.data.get("current_step", step + 1)
            method_name = f"step{target}_{'analyze' if target==1 else 'topics' if target==2 else 'script' if target==3 else 'match' if target==4 else 'frames' if target==5 else 'rough' if target==6 else 'render'}"
            method = getattr(runner, method_name, None)
            if method:
                method()
            ws.load()

        run_in_bg(job_id, _do_run, kind="workflow_step")
        return jsonify({"ok": True, "job_id": job_id})

    @bp.route("/api/run_step", methods=["POST"])
    def api_run_step():
        """后台运行当前步骤（无需先写 review 文件）。"""
        ws = workflow_state_getter()
        if ws is None:
            return jsonify({"error": "项目未加载"}), 400

        data = request.json or {}
        raw_step = data.get("step")
        if raw_step is not None:
            try:
                target = int(raw_step)
            except (TypeError, ValueError):
                return jsonify({"error": f"step 参数不合法: {raw_step}"}), 400
        else:
            target = ws.data.get("current_step", 1)

        if not isinstance(target, int) or target < 1 or target > 7:
            return jsonify({"error": f"step 超出合法范围 1-7: {target}"}), 400

        job_id = str(uuid.uuid4())[:8]

        step_method_map = {
            1: "step1_analyze",
            2: "step2_topics",
            3: "step3_script",
            4: "step4_match",
            5: "step5_frames",
            6: "step6_rough",
            7: "step7_render",
        }
        method_name = step_method_map.get(target)
        if not method_name:
            return jsonify({"error": f"未知步骤: {target}"}), 400

        jobs = jobs_getter()

        def _do():
            def _should_cancel():
                return bool(jobs.get(job_id, {}).get("cancel_requested"))

            def _progress(payload: Dict):
                if not isinstance(payload, dict):
                    return
                progress = payload.get("progress")
                message = parse_str_param(payload.get("message", ""))
                if isinstance(progress, (int, float)):
                    jobs[job_id]["progress"] = max(0, min(99, int(progress)))
                if message:
                    jobs[job_id]["log"].append(message)
                    jobs[job_id]["log"] = jobs[job_id]["log"][-120:]

            runner = WorkflowRunner(ws, should_cancel=_should_cancel, progress_callback=_progress)
            getattr(runner, method_name)()
            ws.load()

        run_in_bg(job_id, _do, kind="workflow_step")
        return jsonify({"ok": True, "job_id": job_id, "step": target})

    @bp.route("/api/frames")
    def api_frames():
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify([])
        frames_dir = project_dir / "preview" / "frames"
        if not frames_dir.exists():
            return jsonify([])
        files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.png"))
        return jsonify([
            {"name": f.name, "url": f"/api/files/preview/frames/{f.name}"}
            for f in files
        ])

    @bp.route("/api/stage_files")
    def api_stage_files():
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({})
        out_dir = project_dir / "output"
        stages = {
            "stage_01_concat.mp4": 1,
            "stage_02_beauty.mp4": 2,
            "stage_03_color.mp4": 3,
            "stage_04_subtitle.mp4": 4,
            "final.mp4": 5,
        }
        result = {}
        for fname, n in stages.items():
            p = out_dir / fname
            result[fname] = {
                "exists": p.exists(),
                "size": p.stat().st_size if p.exists() else 0,
                "url": f"/api/files/output/{fname}" if p.exists() else None,
                "stage": n,
            }
        return jsonify(result)

    @bp.route("/api/files/<path:rel>")
    def api_files(rel: str):
        """提供项目目录内的静态文件（视频/图片）。"""
        project_dir = project_dir_getter()
        if project_dir is None:
            abort(404)
        target = (project_dir / rel).resolve()
        if not str(target).startswith(str(project_dir.resolve())):
            abort(403)
        if not target.exists():
            abort(404)
        return send_file(str(target))

    @bp.route("/api/open_in_finder", methods=["POST"])
    def api_open_in_finder():
        data = request.json or {}
        path = data.get("path", "")
        if path and Path(path).exists():
            p = Path(path)
            if p.is_file():
                subprocess.run(["open", "-R", str(p)], timeout=5, check=False)
            else:
                subprocess.run(["open", str(p)], timeout=5, check=False)
        return jsonify({"ok": True})

    @bp.route("/api/dialog/folder", methods=["POST"])
    def api_dialog_folder():
        result = choose_path("folder")
        if result.get("path"):
            return jsonify({"path": result.get("path"), "cancelled": False})
        if result.get("cancelled"):
            return jsonify({"path": None, "cancelled": True})
        return jsonify({
            "path": None,
            "cancelled": False,
            "error": result.get("error") or "无法打开文件夹选择对话框",
        }), 400

    @bp.route("/api/dialog/file", methods=["POST"])
    def api_dialog_file():
        result = choose_path("file")
        if result.get("path"):
            return jsonify({"path": result.get("path"), "cancelled": False})
        if result.get("cancelled"):
            return jsonify({"path": None, "cancelled": True})
        return jsonify({
            "path": None,
            "cancelled": False,
            "error": result.get("error") or "无法打开文件选择对话框",
        }), 400

    @bp.route("/api/script", methods=["GET"])
    def api_get_script():
        """读取 script_matched.json 或 script_draft.json。"""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({}), 400
        for name in ["script_matched.json", "script_draft.json"]:
            p = project_dir / "data" / name
            if p.exists():
                try:
                    return jsonify(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return jsonify({})

    @bp.route("/api/script", methods=["POST"])
    def api_save_script():
        """保存修改后的脚本到 script_draft.json。"""
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({"error": "项目未加载"}), 400
        data = request.json
        if not data:
            return jsonify({"error": "无效 JSON"}), 400
        p = project_dir / "data" / "script_draft.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        write_json_result(p, data)
        return jsonify({"ok": True})

    @bp.route("/api/materials")
    def api_materials():
        project_dir = project_dir_getter()
        if project_dir is None:
            return jsonify({}), 400
        p = project_dir / "data" / "materials.json"
        if not p.exists():
            return jsonify({})
        try:
            return jsonify(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            return jsonify({})

    # ── 项目元数据 (T-0604) ──────────────────────────────────────────

    _ILLEGAL_CHARS = set('/:*?"<>|\\')

    def _read_project_meta(proj: Path) -> dict:
        meta_path = proj / "data" / "project_meta.json"
        if meta_path.exists():
            try:
                return json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _fallback_display_name(proj: Path) -> str:
        """从目录名提取可读名称：proj_selected_20260312_193013 → 项目 2026-03-12"""
        import re
        name = proj.name
        m = re.match(r"^proj_selected_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})", name)
        if m:
            return f"项目 {m.group(1)}-{m.group(2)}-{m.group(3)}"
        return name

    @bp.route("/api/project/meta")
    def api_project_meta():
        raw_dir = request.args.get("project_dir", "").strip()
        proj = Path(raw_dir).expanduser().resolve() if raw_dir else project_dir_getter()
        if proj is None:
            return jsonify({"error": "项目未加载"}), 400
        meta = _read_project_meta(proj)
        if not meta.get("display_name"):
            meta["display_name"] = _fallback_display_name(proj)
        return jsonify({"ok": True, "meta": meta})

    @bp.route("/api/project/rename", methods=["POST"])
    def api_project_rename():
        data = request.json or {}
        raw_dir = (data.get("project_dir") or "").strip()
        proj = Path(raw_dir).expanduser().resolve() if raw_dir else project_dir_getter()
        if proj is None:
            return jsonify({"error": "项目未加载"}), 400

        display_name = parse_str_param(data.get("display_name", ""))
        if not display_name:
            return jsonify({"error": "项目名不能为空"}), 400
        if len(display_name) > 100:
            return jsonify({"error": "项目名不能超过 100 个字符"}), 400
        if any(ch in _ILLEGAL_CHARS for ch in display_name):
            return jsonify({"error": '项目名不能包含特殊字符 / \\ : * ? " < > |'}), 400

        meta = _read_project_meta(proj)
        meta["display_name"] = display_name
        if not meta.get("created_at"):
            meta["created_at"] = datetime.now().isoformat()
        meta["updated_at"] = datetime.now().isoformat()

        meta_path = proj / "data" / "project_meta.json"
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_result(meta_path, meta)

        from modules.app_api.services.audit_log import audit as _audit
        _audit("project_rename", "project", str(proj),
               actor=f"local:{request.remote_addr}",
               detail={"display_name": display_name})

        return jsonify({"ok": True, "meta": meta})

    return bp
