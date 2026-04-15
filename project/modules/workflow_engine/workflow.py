#!/usr/bin/env python3
"""
VideoEditer 7步工作流编排器

用法：
  python workflow.py init   --videos /path/to/videos --project ./my_project [--ai anthropic]
  python workflow.py run    --project ./my_project [--step N] [--force]
  python workflow.py status --project ./my_project
"""

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# 退化事件审计 — 结构化记录所有降级行为（R2 W-002）
# ═══════════════════════════════════════════════════════════════════════

def _log_degradation(module: str, reason: str, fallback_path: str,
                     severity: str = "warning") -> None:
    """Write a structured degradation event to audit log. Best-effort, never raises."""
    try:
        from modules.app_api.services.audit_log import audit as _audit
        _audit(
            "degradation", module, None,
            actor="workflow_engine",
            status="degraded",
            detail={
                "reason": reason,
                "fallback_path": fallback_path,
                "severity": severity,
            },
        )
    except Exception:
        pass  # 审计不可用时不影响主流程


# ═══════════════════════════════════════════════════════════════════════
# 原子写入工具 — write-to-temp + os.replace，防止崩溃导致文件损坏
# ═══════════════════════════════════════════════════════════════════════

def _atomic_write_text(path, content, encoding="utf-8"):
    """原子写入文本文件：先写临时文件，fsync 后 rename 覆盖目标。"""
    import tempfile as _tf
    target = Path(path) if not isinstance(path, Path) else path
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = _tf.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(target))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ═══════════════════════════════════════════════════════════════════════
# WorkflowState — workflow.json 的读写
# ═══════════════════════════════════════════════════════════════════════

class WorkflowState:
    STEP_NAMES = {
        1: "选择素材",
        2: "脚本脑爆（选题）",
        3: "生成完整脚本",
        4: "素材匹配",
        5: "帧预览",
        6: "粗剪预览",
        7: "分阶段精渲染",
    }
    STATUS_ICON = {
        "not_started": "  ", "pending": " >",
        "running": ">>",    "waiting_review": "?!",
        "done": "OK",       "error": "!!",
    }

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir.resolve()
        self.state_file = self.project_dir / "workflow.json"
        self.data: Dict = {}

    # ------------------------------------------------------------------
    # 加载 / 保存

    def load(self) -> "WorkflowState":
        with open(self.state_file, encoding="utf-8") as f:
            self.data = json.load(f)
        return self

    def save(self):
        _atomic_write_text(
            self.state_file,
            json.dumps(self.data, ensure_ascii=False, indent=2),
        )

    @classmethod
    def create(cls, project_dir: Path, videos_dir: str, config: Dict) -> "WorkflowState":
        videos = str(Path(videos_dir).resolve()) if videos_dir else ""
        ws = cls(project_dir)
        ws.data = {
            "version": 1,
            "project_dir": str(project_dir.resolve()),
            "videos_dir": videos,
            "current_step": 1,
            "steps": {
                str(n): {"status": "not_started", "review_status": None}
                for n in range(1, 8)
            },
            "config": config,
        }
        ws.data["steps"]["1"]["status"] = "pending"
        return ws

    # ------------------------------------------------------------------
    # 步骤访问

    def get_step(self, n: int) -> Dict:
        return self.data["steps"][str(n)]

    def set_step_status(self, n: int, status: str, **kwargs):
        step = self.data["steps"][str(n)]
        step["status"] = status
        if status == "done":
            step["completed_at"] = datetime.now().isoformat()
        step.update(kwargs)
        self.save()

    def approve_review(self, n: int, parsed: Dict):
        step = self.data["steps"][str(n)]
        step["review_status"] = "approved"
        step.update(parsed)
        self.data["current_step"] = n + 1
        self.save()

    # ------------------------------------------------------------------
    # 属性

    @property
    def config(self) -> Dict:
        return self.data.get("config", {})

    @property
    def videos_dir(self) -> str:
        return self.data.get("videos_dir", "")

    @property
    def render_config(self) -> Dict:
        return self.data.get("config", {}).get("render", {})


# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def _find_ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("FFmpeg 未安装或未在 PATH 中")
    return ff


def _find_ffprobe() -> str:
    fp = shutil.which("ffprobe")
    if not fp:
        raise RuntimeError("FFprobe 未安装或未在 PATH 中")
    return fp


def _parse_yaml_block(text: str) -> Dict:
    """从 Markdown 中提取第一个 ```yaml 块并解析 key: value。"""
    match = re.search(r"```yaml\s*\n([\s\S]+?)\n```", text)
    if not match:
        return {}
    result: Dict = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.split("#")[0].strip().strip('"').strip("'")
        if val.lower() == "true":
            result[key] = True
        elif val.lower() == "false":
            result[key] = False
        else:
            try:
                result[key] = int(val)
            except ValueError:
                try:
                    result[key] = float(val)
                except ValueError:
                    result[key] = val if val else None
    return result


def _path(project_dir: Path, *parts) -> Path:
    return project_dir.joinpath(*parts)


# ═══════════════════════════════════════════════════════════════════════
# WorkflowRunner — 7步执行逻辑
# ═══════════════════════════════════════════════════════════════════════

class WorkflowRunner:

    def __init__(self, state: WorkflowState, should_cancel=None, progress_callback=None):
        self.state = state
        self.project_dir = state.project_dir
        self._should_cancel = should_cancel
        self._progress_callback = progress_callback
        self._last_progress = -1

    def p(self, *parts) -> Path:
        return _path(self.project_dir, *parts)

    def _is_cancelled(self) -> bool:
        if callable(self._should_cancel):
            try:
                return bool(self._should_cancel())
            except Exception:
                return False
        return False

    def _check_cancel(self):
        if self._is_cancelled():
            raise RuntimeError("__CANCELLED__")

    def _emit_progress(self, progress: Optional[float] = None, message: Optional[str] = None):
        payload: Dict = {}
        if progress is not None:
            p = max(0, min(99, int(progress)))
            payload["progress"] = p
        if message:
            payload["message"] = str(message)
        if not payload or not callable(self._progress_callback):
            return
        if "progress" in payload and "message" not in payload and payload["progress"] == self._last_progress:
            return
        self._last_progress = payload.get("progress", self._last_progress)
        try:
            self._progress_callback(payload)
        except Exception:
            pass

    @staticmethod
    def _system_load_ratio() -> float:
        cpu = os.cpu_count() or 1
        try:
            load_1m = float(os.getloadavg()[0])
        except Exception:
            return 0.0
        return load_1m / max(cpu, 1)

    def _is_overloaded(self, threshold: float = 1.6) -> bool:
        return self._system_load_ratio() >= threshold

    @staticmethod
    def _degrade_render_config(rc: Dict, level: int = 1) -> Dict:
        level = max(1, int(level))
        degraded = dict(rc)
        degraded["preset"] = "ultrafast"
        degraded["crf"] = min(35, int(float(rc.get("crf", 18))) + 6)
        degraded["fps"] = min(int(rc.get("fps", 30)), 24)
        degraded["enable_skin_smooth"] = False
        degraded["transition_style"] = "none"
        degraded["transition_duration"] = 0.0
        if level >= 2:
            w = int(rc.get("width", 1080))
            h = int(rc.get("height", 1920))
            scale = 0.75
            degraded["width"] = max(480, int((w * scale) // 2 * 2))
            degraded["height"] = max(854, int((h * scale) // 2 * 2))
            degraded["fps"] = min(int(degraded.get("fps", 24)), 20)
            degraded["enable_color_grading"] = False
            degraded["enable_skill_enhance"] = False
        return degraded

    # ==================================================================
    # Step 1: 素材语义分析
    # ==================================================================

    def step1_analyze(self):
        logger.info("[Step 1] 素材语义分析")
        self._check_cancel()
        try:
            from modules.step1_material_analysis.video_asset_toolkit import VideoAssetToolkit
        except ImportError as e:
            raise RuntimeError(f"无法导入 VideoAssetToolkit: {e}") from e

        selected_paths = self.state.config.get("selected_video_paths") or []
        if selected_paths:
            video_files = sorted(
                str(Path(p).resolve()) for p in selected_paths
                if Path(p).exists()
            )
            logger.info("使用已选素材: %d 个视频文件", len(video_files))
        else:
            videos_dir = Path(self.state.videos_dir) if self.state.videos_dir else None
            if videos_dir is None:
                raise RuntimeError("未配置素材目录，请重新初始化项目或使用已选素材模式")

            exts = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".hevc"}
            video_files = sorted(
                str(p) for p in videos_dir.rglob("*")
                if p.suffix.lower() in exts
            )
        logger.info("找到 %d 个视频文件", len(video_files))
        if not video_files:
            if selected_paths:
                raise RuntimeError("已选素材均不存在，请重新选择")
            raise RuntimeError(f"在 {videos_dir} 中未找到视频文件")

        toolkit = VideoAssetToolkit()
        results = toolkit.analyze_videos(video_files, output_format="json")

        # 保存 materials.json
        mat_path = self.p("data", "materials.json")
        _atomic_write_text(
            mat_path,
            json.dumps(results, ensure_ascii=False, indent=2),
        )
        logger.info("素材索引已保存: %s", mat_path)

        # 可选语义索引
        use_semantic = self.state.config.get("use_semantic_index", False)
        if use_semantic:
            self._build_semantic_index(video_files)

        # 生成审核文件
        self._write_review_01(results)
        self.state.set_step_status(
            1, "waiting_review",
            output="data/materials.json",
            review_file="reviews/01_materials.md",
            video_count=len(video_files),
        )
        logger.info("Step 1 完成")
        logger.info("请审核: %s", self.p("reviews", "01_materials.md"))
        logger.info("将 approved: false 改为 approved: true 后重跑 run")

    def _build_semantic_index(self, video_files: List[str]):
        try:
            from modules.step1_material_analysis.indexer.semantic import SemanticIndex
            idx_path = self.p("data", "semantic_index.json")
            idx = SemanticIndex(str(idx_path))
            logger.info("建立语义索引（CLIP）...")
            count = idx.batch_index(
                video_files,
                progress_callback=lambda c, t: logger.info("语义索引 [%d/%d]", c, t),
            )
            logger.info("语义索引完成: %d 个视频", count)
        except ImportError:
            logger.warning("CLIP 不可用（需 pip install torch transformers），跳过语义索引")
            _log_degradation("step1_clip", "CLIP 不可用（需 torch + transformers）", "跳过语义索引")

    def _write_review_01(self, results: Dict):
        lines = [
            "# 第1步审核：素材分析结果",
            "",
            "> 请审核后将 `approved: false` 改为 `approved: true`，",
            "> 然后重新运行 `python workflow.py run --project <项目路径>` 继续。",
            "",
            "```yaml",
            "approved: false",
            'notes: ""',
            "```",
            "",
            f"## 素材总览（共 {len(results)} 个视频）",
            "",
            "| # | 文件名 | 时长(s) | 分辨率 | 质量 | 场景描述 |",
            "|---|--------|---------|--------|------|----------|",
        ]
        for i, (vid_hash, vdata) in enumerate(results.items(), 1):
            fname = vdata.get("filename", "?")
            an = vdata.get("analysis", {})
            meta = an.get("metadata", {})
            tech = an.get("local_analysis", {}).get("technical", {})
            scene = an.get("local_analysis", {}).get("scene", {})
            dur = meta.get("duration", "?")
            res = tech.get("resolution", "?")
            score = tech.get("overall_quality", 0)
            desc = (scene.get("description") or "")[:40].replace("|", "\\|")
            lines.append(f"| {i} | {fname} | {dur} | {res} | {score:.1f} | {desc} |")

        lines += ["", "## 详细信息", ""]
        for vid_hash, vdata in results.items():
            fname = vdata.get("filename", "?")
            recs = vdata.get("analysis", {}).get("recommendations", [])
            lines += [f"### {fname}", f"- **ID**: `{vid_hash}`",
                      f"- **路径**: `{vdata.get('path', '')}`"]
            for r in recs:
                lines.append(f"- [{r.get('priority','').upper()}] {r.get('message','')}")
            lines.append("")

        self.p("reviews").mkdir(exist_ok=True)
        _atomic_write_text(self.p("reviews", "01_materials.md"), "\n".join(lines))

    # ==================================================================
    # Step 2: 脚本脑爆（选题）
    # ==================================================================

    def step2_topics(self):
        logger.info("[Step 2] 脚本脑爆 — AI 生成选题建议")
        self._check_cancel()
        from modules.step2_topic_planning.ai_client import (
            AIClient,
            SYSTEM_PROMPT_VLOG,
            PROMPT_TOPICS,
        )

        materials = self._load_json("data/materials.json")
        self._sync_topic_library_from_materials(materials)
        summary = self._build_material_summary(materials)
        topic_library_summary = self._build_topic_library_summary(limit=10)
        if topic_library_summary:
            summary = f"{summary}\n\n## 选题库模板（可复用）\n{topic_library_summary}"

        ai = AIClient.from_workflow_config(self.state.config)
        logger.info("AI: %s", ai)
        prompt = PROMPT_TOPICS.format(material_summary=summary)
        response = ai.chat([{"role": "user", "content": prompt}], system=SYSTEM_PROMPT_VLOG)
        topics = self._extract_topics_from_response(response, materials)

        # S4: detect AI degradation
        ai_degraded = False
        ai_degraded_reason = ""
        if not ai.provider or not ai.api_key:
            ai_degraded = True
            ai_degraded_reason = "未配置 AI API Key，使用素材分析生成选题"
        elif all(t.get("_from_materials") for t in topics):
            ai_degraded = True
            ai_degraded_reason = "AI 返回内容解析失败，已退化为素材驱动选题"

        self._write_review_02(response, summary, topics)
        extra = {}
        if ai_degraded:
            extra["ai_degraded"] = True
            extra["ai_degraded_reason"] = ai_degraded_reason
            logger.warning("Step 2 AI 退化: %s", ai_degraded_reason)
            _log_degradation("step2_topic", ai_degraded_reason, "素材驱动选题")
        self.state.set_step_status(
            2, "waiting_review",
            output=json.dumps({"topics": topics}, ensure_ascii=False),
            review_file="reviews/02_topics.md",
            ai_response_raw=response,
            topics=topics,
            **extra,
        )
        logger.info("Step 2 完成")
        logger.info("请在审核文件中填写选题序号和想法:")
        logger.info("%s", self.p("reviews", "02_topics.md"))

    def _build_material_summary(self, materials: Dict) -> str:
        lines = []
        for vid_hash, vdata in materials.items():
            an = vdata.get("analysis", {})
            meta = an.get("metadata", {})
            tech = an.get("local_analysis", {}).get("technical", {})
            scene = an.get("local_analysis", {}).get("scene", {})
            objs = an.get("local_analysis", {}).get("objects", {})
            trans = an.get("transcription", {})
            fname = vdata.get("filename", vid_hash[:8])
            dur = meta.get("duration", "?")
            res = tech.get("resolution", "?")
            desc = (scene.get("description") or "")[:50]
            mood = scene.get("mood", "")
            obj_list = ", ".join((objs.get("detected_objects") or [])[:5])
            sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
            sem_hint = " ".join(
                str(sem.get(k, "")) for k in ("setting", "activity", "time_of_day", "weather", "narrative_role")
                if sem.get(k)
            )
            # 包含转录文本（截取前 200 字）
            transcript = (trans.get("transcript") or "").strip()[:200]
            has_speech = trans.get("has_speech", False)

            parts = [f"- {fname} | {dur}s | {res}"]
            if desc:
                parts.append(f"场景:{desc}")
            if mood:
                parts.append(f"情绪:{mood}")
            if obj_list:
                parts.append(f"物体:{obj_list}")
            if sem_hint:
                parts.append(f"语义:{sem_hint}")
            if has_speech and transcript:
                parts.append(f"语音内容:「{transcript}」")
            elif not has_speech:
                parts.append("语音:无人声")
            lines.append(" | ".join(parts))
        return "\n".join(lines) if lines else "（未找到素材信息）"

    def _sync_topic_library_from_materials(self, materials: Dict) -> None:
        """
        Seed topic library database from material semantics.

        Safe to call repeatedly (upsert by slug).
        """
        try:
            from modules.capabilities.topic_library import TopicTemplate, upsert_topic
        except Exception:
            return

        db_path = self.p("data", "topic_library.db")
        seen = set()
        for _, vdata in materials.items():
            sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic"), dict) else {}
            setting = str(sem.get("setting", "") or "").strip() or "旅行场景"
            activity = str(sem.get("activity", "") or "").strip() or "探索"
            mood = str(sem.get("mood", "") or "").strip() or "真实"
            slug = self._slugify(f"{setting}-{activity}")
            if slug in seen:
                continue
            seen.add(slug)
            outline = f"开场展示{setting}，中段推进{activity}，结尾回到{mood}情绪。"
            topic = TopicTemplate(
                slug=slug,
                title=f"{setting}·{activity}高光",
                category="travel",
                audience="short_video",
                hook_style="story",
                outline_template=outline,
                tags=[setting, activity, mood],
                enabled=True,
            )
            try:
                upsert_topic(str(db_path), topic)
            except Exception:
                continue

    def _build_topic_library_summary(self, limit: int = 10) -> str:
        try:
            from modules.capabilities.topic_library import list_topics
            rows = list_topics(str(self.p("data", "topic_library.db")), enabled_only=True, limit=limit)
        except Exception:
            return ""
        if not rows:
            return ""

        lines = []
        for item in rows:
            tags = ", ".join((item.get("tags") or [])[:4]) or "-"
            lines.append(
                f"- {item.get('title', '未命名')} | 风格:{item.get('hook_style', 'story')} | 标签:{tags}"
            )
        return "\n".join(lines)

    @staticmethod
    def _slugify(text: str) -> str:
        raw = str(text or "").strip().lower()
        cleaned = []
        for ch in raw:
            if ch.isalnum():
                cleaned.append(ch)
            elif ch in {" ", "-", "_", "/"}:
                cleaned.append("-")
        slug = "".join(cleaned).strip("-")
        while "--" in slug:
            slug = slug.replace("--", "-")
        return slug[:64] or "topic"

    def _extract_topics_from_response(self, ai_response: str, materials: Dict) -> List[Dict]:
        text = str(ai_response or "")
        topics = []
        pattern = re.compile(
            r"\*\*选题\s*(\d+)\s*[：:]\s*[《\"]?([^》\"\n]+)[》\"]?\*\*([\s\S]*?)(?=\n\*\*选题\s*\d+\s*[：:]|$)"
        )
        for m in pattern.finditer(text):
            idx = int(m.group(1))
            title = (m.group(2) or "").strip()
            body = (m.group(3) or "").strip()
            theme = ""
            duration = "60秒"
            emotion = ""
            hook = ""
            recommended_assets = []
            for line in body.splitlines():
                clean = line.strip().lstrip("-").strip()
                if clean.startswith("主题"):
                    theme = clean.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif "建议时长" in clean:
                    duration = clean.split("：", 1)[-1].split(":", 1)[-1].strip() or duration
                elif "核心情绪" in clean:
                    emotion = clean.split("：", 1)[-1].split(":", 1)[-1].strip()
                elif "开场钩子" in clean:
                    hook = clean.split("\uff1a", 1)[-1].split(":", 1)[-1].strip().strip('"\'  ')
                elif "推荐素材" in clean:
                    raw_assets = clean.split("：", 1)[-1].split(":", 1)[-1].strip()
                    recommended_assets = [
                        x.strip()
                        for x in re.split(r"[，,、;/\|]+", raw_assets)
                        if x.strip()
                    ][:6]
            topics.append({
                "index": idx,
                "title": title or f"选题{idx}",
                "theme": theme or "内容向",
                "emotion": emotion or "真实",
                "duration": duration,
                "hook": hook,
                "recommended_assets": recommended_assets,
            })
        if topics:
            return topics[:5]
        return self._generate_topics_from_materials(materials)

    @staticmethod
    def _material_scene_hint(vdata: Dict) -> str:
        sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
        if sem:
            setting = sem.get("setting")
            activity = sem.get("activity")
            mood = sem.get("mood")
            return " ".join(x for x in [setting, activity, mood] if x)
        local_scene = (
            vdata.get("analysis", {})
            .get("local_analysis", {})
            .get("scene", {})
        )
        return str(local_scene.get("description", "") or "")

    def _generate_topics_from_materials(self, materials: Dict) -> List[Dict]:
        clusters = {}
        all_files = []
        hooks = []
        all_transcripts = []  # 收集所有转录文本

        for _, vdata in materials.items():
            fname = str(vdata.get("filename", "") or "").strip()
            if fname:
                all_files.append(fname)

            an = vdata.get("analysis", {})
            trans = an.get("transcription", {})
            transcript = (trans.get("transcript") or "").strip()
            has_speech = trans.get("has_speech", False)
            if has_speech and transcript:
                all_transcripts.append({"file": fname, "text": transcript})

            sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
            scene = an.get("local_analysis", {}).get("scene", {})
            # 从多个来源推断 setting/activity，不再硬编码默认值
            setting = (str(sem.get("setting", "") or "").strip()
                       or str(scene.get("description", "") or "").strip()[:20]
                       or "")
            activity = str(sem.get("activity", "") or "").strip() or ""
            mood = str(sem.get("mood", "") or scene.get("mood", "") or "").strip() or ""

            # 如果有转录文本，用前 30 字作为 setting 补充
            if not setting and has_speech and transcript:
                setting = transcript[:30]
            if not setting:
                setting = fname.rsplit(".", 1)[0][:20] if fname else "未知场景"
            if not activity:
                activity = "记录"
            if not mood:
                mood = "真实"

            key = (setting, activity)
            info = clusters.setdefault(key, {"count": 0, "mood": {}, "files": [], "transcripts": []})
            info["count"] += 1
            info["mood"][mood] = info["mood"].get(mood, 0) + 1
            if fname:
                info["files"].append(fname)
            if has_speech and transcript:
                info["transcripts"].append(transcript[:100])

            hint = self._material_scene_hint(vdata)
            if hint:
                hooks.append(hint)

        # 如果有转录文本，优先基于内容生成选题
        if all_transcripts:
            return self._generate_topics_from_transcripts(all_transcripts, all_files, materials)

        # 无转录文本 → 基于视觉分析生成
        ranked = sorted(
            clusters.items(),
            key=lambda kv: kv[1]["count"],
            reverse=True,
        )
        topics = []
        for idx, ((setting, activity), info) in enumerate(ranked[:5], 1):
            mood = max(info["mood"], key=info["mood"].get) if info["mood"] else "真实"
            picks = info.get("files", [])[:5]
            hook = hooks[idx - 1][:24] if idx - 1 < len(hooks) else f"最抓人的一幕"
            topics.append({
                "index": idx,
                "title": f"{setting}·{activity}高光合集",
                "theme": f"围绕\u300c{setting}+{activity}\u300d展开，突出真实现场感和人物情绪起伏。",
                "emotion": mood,
                "duration": "60秒" if info["count"] >= 3 else "45秒",
                "hook": hook,
                "recommended_assets": picks,
                "_from_materials": True,
            })

        while len(topics) < 3:
            idx = len(topics) + 1
            fallback_files = all_files[(idx - 1) * 2:(idx - 1) * 2 + 4] or all_files[:4]
            topics.append({
                "index": idx,
                "title": f"素材混剪方案{idx}",
                "theme": "基于现有素材做节奏剪辑，突出前3秒钩子和结尾记忆点。",
                "emotion": "真实",
                "duration": "45秒",
                "hook": "先看这一秒，再决定要不要划走",
                "recommended_assets": fallback_files[:5],
                "_from_materials": True,
            })

        return topics[:5]

    def _generate_topics_from_transcripts(self, transcripts: List[Dict], all_files: List[str], materials: Dict) -> List[Dict]:
        """基于转录文本生成选题（有人声的情况）"""
        # 合并所有转录文本
        combined = " ".join(t["text"] for t in transcripts)

        # 提取关键词（简单频率分析）
        import re as _re
        # 去掉标点和常见停用词
        stopwords = {"的", "了", "在", "是", "我", "你", "他", "她", "们", "这", "那",
                     "有", "就", "不", "都", "也", "很", "到", "说", "会", "去", "能",
                     "和", "着", "地", "得", "把", "被", "让", "给", "但", "而", "又",
                     "一个", "一", "什么", "怎么", "嗯", "啊", "哦", "吧", "呢", "吗",
                     "然后", "所以", "因为", "如果", "可以", "没有", "这个", "那个"}
        words = _re.findall(r'[\u4e00-\u9fff]{2,4}', combined)
        freq = {}
        for w in words:
            if w not in stopwords and len(w) >= 2:
                freq[w] = freq.get(w, 0) + 1
        top_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:15]
        keywords = [w for w, _ in top_words[:8]]

        # 生成基于内容的选题
        topics = []

        # 选题 1：基于核心内容
        core_keywords = keywords[:3] if keywords else ["精彩瞬间"]
        topic1_title = "·".join(core_keywords[:2]) if len(core_keywords) >= 2 else core_keywords[0]
        first_sentence = transcripts[0]["text"][:50].strip()
        topics.append({
            "index": 1,
            "title": f"{topic1_title}｜真实记录",
            "theme": f"围绕「{'、'.join(core_keywords)}」展开叙事，用第一人称视角讲述真实体验。",
            "emotion": "真实",
            "duration": "60秒",
            "hook": f"「{first_sentence[:20]}」",
            "recommended_assets": [t["file"] for t in transcripts[:5]],
            "_from_materials": True,
        })

        # 选题 2：情绪向剪辑
        if len(keywords) >= 4:
            emotion_keywords = keywords[2:5]
            topics.append({
                "index": 2,
                "title": f"{'·'.join(emotion_keywords[:2])}｜氛围感混剪",
                "theme": f"以情绪为线索，围绕「{'、'.join(emotion_keywords)}」营造沉浸氛围。",
                "emotion": "共鸣",
                "duration": "45秒",
                "hook": "有些画面，看一眼就忘不掉",
                "recommended_assets": all_files[:5],
                "_from_materials": True,
            })

        # 选题 3：叙事向
        if len(transcripts) >= 2:
            topics.append({
                "index": len(topics) + 1,
                "title": "完整叙事版｜从头到尾",
                "theme": "按时间线完整呈现，保留原声对话和环境音，最大化故事完整度。",
                "emotion": "真实",
                "duration": "90秒" if len(transcripts) >= 3 else "60秒",
                "hook": f"「{first_sentence[:20]}」",
                "recommended_assets": [t["file"] for t in transcripts],
                "_from_materials": True,
            })

        # 填充到至少 3 个
        while len(topics) < 3:
            idx = len(topics) + 1
            topics.append({
                "index": idx,
                "title": f"节奏混剪方案{idx}",
                "theme": "基于素材内容做节奏剪辑，突出前3秒钩子和结尾记忆点。",
                "emotion": "真实",
                "duration": "45秒",
                "hook": "先看这一秒，再决定要不要划走",
                "recommended_assets": all_files[:5],
                "_from_materials": True,
            })

        # 重新编号
        for i, t in enumerate(topics, 1):
            t["index"] = i
        return topics[:5]

    def _write_review_02(self, ai_response: str, summary: str, topics: List[Dict]):
        topics_md = []
        for t in topics:
            rec_assets = t.get("recommended_assets") or []
            rec_line = ", ".join(rec_assets[:5]) if isinstance(rec_assets, list) and rec_assets else "自动按语义匹配"
            topics_md.append(
                f"**选题{t.get('index', '?')}：《{t.get('title', '')}》**\n"
                f"- 主题：{t.get('theme', '')}\n"
                f"- 建议时长：{t.get('duration', '')}\n"
                f"- 核心情绪：{t.get('emotion', '')}\n"
                f"- 推荐素材：{rec_line}\n"
                f"- 开场钩子：「{t.get('hook', '')}」\n"
            )
        topics_block = "\n".join(topics_md).strip() or ai_response

        content = f"""# 第2步审核：选题建议

> **操作说明**：
> 1. 查看下方 AI 生成的选题建议
> 2. 在 `chosen_topic` 填写您选择的序号（1-5）
> 3. 在 `user_ideas` 填写您的补充想法和创作方向
> 4. 将 `approved: false` 改为 `approved: true`
> 5. 重新运行 `python workflow.py run --project <项目路径>` 继续

```yaml
approved: false
chosen_topic: 1
user_ideas: ""
target_duration: 60
```

## AI 生成的选题建议

{topics_block}

---

## 素材概览（供参考）

{summary}
"""
        _atomic_write_text(self.p("reviews", "02_topics.md"), content)

    # ==================================================================
    # Step 3: 生成完整脚本
    # ==================================================================

    def step3_script(self):
        logger.info("[Step 3] 生成完整脚本")
        self._check_cancel()
        from modules.step2_topic_planning.ai_client import (
            AIClient,
            SYSTEM_PROMPT_VLOG,
            PROMPT_SCRIPT,
        )

        step2 = self.state.get_step(2)
        chosen = step2.get("chosen_topic", 1)
        ideas = step2.get("user_ideas", "")
        duration = step2.get("target_duration", 60)
        topics_list = step2.get("topics") if isinstance(step2.get("topics"), list) else []
        if topics_list:
            topics_raw = json.dumps(topics_list, ensure_ascii=False, indent=2)
        else:
            topics_raw = step2.get("ai_response_raw", "（未获取选题内容）")

        selected_topic_data = {}
        try:
            chosen_i = int(chosen)
            selected_topic_data = next(
                (t for t in topics_list if int(t.get("index", 0)) == chosen_i),
                {},
            )
        except Exception:
            selected_topic_data = topics_list[0] if topics_list else {}

        materials = self._load_json("data/materials.json")
        summary = self._build_material_summary(materials)

        ai = AIClient.from_workflow_config(self.state.config)
        logger.info("AI: %s  选题: #%s  时长: %ss", ai, chosen, duration)
        prompt = PROMPT_SCRIPT.format(
            chosen_topic=chosen,
            topics_suggestions=topics_raw,
            user_ideas=ideas or "（无特别要求）",
            target_duration=duration,
            material_summary=summary,
        )
        response = ai.chat([{"role": "user", "content": prompt}], system=SYSTEM_PROMPT_VLOG)

        script_json = self._parse_script_json(response, materials)
        ai_degraded = False
        ai_degraded_reason = ""
        if not ai.provider or not ai.api_key:
            ai_degraded = True
            ai_degraded_reason = "未配置 AI API Key，脚本使用模板生成"
        if script_json.get("_parse_failed") or not script_json.get("clips"):
            logger.warning("AI 脚本解析失败，使用内容驱动兜底脚本生成")
            script_json = self._build_fallback_script(materials, duration, chosen, selected_topic_data)
            if not ai_degraded:
                ai_degraded = True
                ai_degraded_reason = "AI 返回的脚本 JSON 解析失败，已退化为模板脚本"
        _atomic_write_text(
            self.p("data", "script_draft.json"),
            json.dumps(script_json, ensure_ascii=False, indent=2),
        )

        self._write_review_03(response, script_json)
        extra = {}
        if ai_degraded:
            extra["ai_degraded"] = True
            extra["ai_degraded_reason"] = ai_degraded_reason
            logger.warning("Step 3 AI 退化: %s", ai_degraded_reason)
            _log_degradation("step3_script", ai_degraded_reason, "模板脚本生成")
        self.state.set_step_status(
            3, "waiting_review",
            output="data/script_draft.json",
            review_file="reviews/03_script.md",
            **extra,
        )
        logger.info("Step 3 完成")
        logger.info("脚本: %s", self.p("data", "script_draft.json"))
        logger.info("审核: %s", self.p("reviews", "03_script.md"))

    def _parse_script_json(self, text: str, materials: Dict) -> Dict:
        # 尝试提取 ```json 块
        m = re.search(r"```json\s*\n([\s\S]+?)\n```", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试直接解析
        try:
            return json.loads(text)
        except Exception:
            pass
        # 返回骨架，让用户手动填写
        return {
            "title": "待填写",
            "total_duration": 60,
            "clips": [],
            "subtitles": [],
            "bgm": {"path": None},
            "narration": {"path": None},
            "_parse_failed": True,
            "_raw_ai_response": text[:2000],
        }

    def _build_fallback_script(self, materials: Dict, target_duration: int, chosen_topic, selected_topic: Optional[Dict] = None) -> Dict:
        selected_topic = selected_topic if isinstance(selected_topic, dict) else {}
        topic_terms = []
        for key in ("title", "theme", "emotion", "hook"):
            v = str(selected_topic.get(key, "") or "").strip()
            if v:
                topic_terms.append(v)
        topic_text = " ".join(topic_terms).lower()
        topic_tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}", topic_text)
        rec_assets = set(
            str(x).strip().lower()
            for x in (selected_topic.get("recommended_assets") or [])
            if str(x).strip()
        )

        candidates = []
        for vid_id, vdata in materials.items():
            analysis = vdata.get("analysis", {})
            meta = analysis.get("metadata", {}) if isinstance(analysis, dict) else {}
            local_scene = (
                analysis.get("local_analysis", {}).get("scene", {})
                if isinstance(analysis, dict)
                else {}
            )
            sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
            try:
                duration = float(meta.get("duration") or 0.0)
            except Exception:
                duration = 0.0
            scene_desc = (
                str(sem.get("scene_description") or "")
                or str(local_scene.get("description") or "")
                or vdata.get("filename", vid_id)
            )
            mood = str(sem.get("mood") or local_scene.get("mood") or "真实")
            sem_keywords = sem.get("search_keywords", []) if isinstance(sem, dict) else []
            sem_text = " ".join(str(x) for x in sem_keywords if str(x).strip())
            filename = str(vdata.get("filename", vid_id) or "")
            match_text = f"{filename} {scene_desc} {mood} {sem_text}".lower()
            score = 0.0
            if topic_tokens:
                for t in topic_tokens:
                    if t in match_text:
                        score += 2.0
            if filename.lower() in rec_assets:
                score += 8.0
            if str(sem.get("narrative_role", "") or "") in {"hook", "climax", "establishing"}:
                score += 1.2
            score += min(max(duration, 0.0), 12.0) * 0.08
            candidates.append({
                "video_id": vid_id,
                "filename": filename,
                "duration": max(duration, 4.0),
                "scene": scene_desc[:80],
                "mood": mood[:24],
                "score": round(score, 3),
            })

        if not candidates:
            return {
                "title": "空素材兜底脚本",
                "total_duration": target_duration,
                "clips": [],
                "subtitles": [],
                "bgm": {"path": None, "style": "轻氛围"},
                "narration": {"path": None, "tone": "自然"},
                "_fallback": True,
            }

        try:
            td = int(target_duration)
        except Exception:
            td = 60
        td = max(15, min(td, 180))
        clip_count = min(len(candidates), max(3, min(10, td // 6)))

        selected = sorted(candidates, key=lambda x: (x["score"], x["duration"]), reverse=True)[:clip_count]
        clips = []
        subtitles = []
        elapsed = 0.0
        for i, item in enumerate(selected, 1):
            remaining = max(td - elapsed, 3.0)
            remaining_slots = max(clip_count - i + 1, 1)
            allot = max(3.0, min(9.0, remaining / remaining_slots))
            source_end = min(item["duration"], allot)
            clips.append({
                "clip_index": i,
                "video_id": item["video_id"],
                "source_start": 0,
                "source_end": round(source_end, 2),
                "duration": round(allot, 2),
                "scene_description": item["scene"],
                "has_face": False,
                "camera_note": "保持节奏，优先稳定画面",
            })
            start_t = round(elapsed, 2)
            end_t = round(elapsed + allot, 2)
            subtitles.append({
                "clip_index": i,
                "cn_text": f"{item['mood']} · {item['scene'][:16]}",
                "en_text": "Travel moment",
                "start_time": start_t,
                "end_time": end_t,
            })
            elapsed += allot

        title_seed = str(selected_topic.get("title", "") or "").strip()
        title = title_seed or (f"选题{chosen_topic} 内容向剪辑" if chosen_topic else "内容向剪辑")
        return {
            "title": title,
            "total_duration": td,
            "clips": clips,
            "subtitles": subtitles,
            "bgm": {"path": None, "style": "治愈电子/轻节奏"},
            "narration": {"path": None, "tone": "自然叙述"},
            "_fallback": True,
        }

    def _write_review_03(self, ai_response: str, script: Dict):
        clips = script.get("clips", [])
        subs = {s.get("clip_index", i): s for i, s in enumerate(script.get("subtitles", []))}
        table = ["| # | 场景描述 | 素材文件 | 时长(s) | 字幕 |",
                 "|---|----------|----------|---------|------|"]
        for clip in clips:
            idx = clip.get("clip_index", "?")
            desc = clip.get("scene_description", "")[:35]
            vid = clip.get("video_id", "待匹配")[:25]
            dur = clip.get("duration", "?")
            cn = subs.get(idx, {}).get("cn_text", "")[:30]
            table.append(f"| {idx} | {desc} | {vid} | {dur} | {cn} |")

        content = f"""# 第3步审核：脚本审核

> **操作说明**：
> - 如需修改脚本，直接编辑 `data/script_draft.json`
> - 将 `approved: false` 改为 `approved: true`
> - 重新运行 `python workflow.py run --project <项目路径>` 继续

```yaml
approved: false
notes: ""
```

## 脚本摘要

- **标题**: {script.get("title", "?")}
- **总时长**: {script.get("total_duration", "?")} 秒
- **片段数**: {len(clips)}

### 分镜列表

{chr(10).join(table)}

---

## AI 原始输出

{ai_response[:3000]}
"""
        _atomic_write_text(self.p("reviews", "03_script.md"), content)

    # ==================================================================
    # Step 4: 素材匹配
    # ==================================================================

    def step4_match(self):
        logger.info("[Step 4] 素材匹配")
        self._check_cancel()

        script = self._load_json("data/script_draft.json")
        materials = self._load_json("data/materials.json")

        # 尝试使用 AdaptiveRewriter，失败则用简单关键词匹配
        try:
            from modules.step4_material_matching.adaptive_rewriter import (
                AdaptiveRewriter,
                ScriptGapAnalyzer,
            )
            rewriter = AdaptiveRewriter(similarity_threshold=0.5)
            search_fn = self._make_search_func(materials)
            rewritten, changes = rewriter.rewrite_script(script, materials, search_fn)
            coverage = ScriptGapAnalyzer().analyze_coverage(script, materials)
        except Exception as e:
            logger.warning("AdaptiveRewriter 异常 (%s)，使用基础匹配", e)
            rewritten = script
            changes = []
            coverage = {"total_segments": len(script.get("clips", [])),
                        "coverage_rate": 0, "covered_segments": 0, "missing_segments": []}

        # 补全缺失的 video_id
        self._fill_video_ids(rewritten, materials)

        _atomic_write_text(
            self.p("data", "script_matched.json"),
            json.dumps(rewritten, ensure_ascii=False, indent=2),
        )
        self._write_review_04(coverage, changes, rewritten, materials)
        self.state.set_step_status(
            4, "waiting_review",
            output="data/script_matched.json",
            review_file="reviews/04_matching.md",
            coverage_rate=coverage.get("coverage_rate", 0),
        )
        logger.info("Step 4 完成  覆盖率: %.0f%%", coverage.get("coverage_rate", 0) * 100)
        logger.info("审核: %s", self.p("reviews", "04_matching.md"))

    @staticmethod
    def _to_search_index(materials: Dict) -> Dict:
        """将 workflow materials 转成 VideoSearch 期望结构。"""
        from modules.adapters.materials_mapper import materials_to_search_index

        return materials_to_search_index(materials)

    def _make_search_func(self, materials: Dict):
        """构造供 AdaptiveRewriter 使用的搜索闭包。"""
        from modules.step4_material_matching.search_videos import VideoSearch

        converted_index = self._to_search_index(materials)

        class _FakeSearch(VideoSearch):
            def __init__(self):  # noqa: N807
                self.index = converted_index

        searcher = _FakeSearch()

        try:
            from modules.step4_material_matching.adaptive_rewriter import MaterialMatch
            def search_fn(clip, subtitle, materials_index):
                query = ""
                if subtitle:
                    query = f"{subtitle.get('cn_text','')} {subtitle.get('en_text','')}"
                else:
                    query = clip.get("scene_description", clip.get("description", ""))
                results = searcher.search(query)
                matches = []
                for r in results[:5]:
                    vid_id = r.get("video_id", "")
                    score = min(r.get("match_score", 0) / 2.0, 10.0)
                    matches.append(MaterialMatch(
                        video_id=vid_id, score=score,
                        reasons=r.get("match_details", []),
                        data=materials_index.get(vid_id, {}),
                    ))
                return matches
        except ImportError:
            def search_fn(clip, subtitle, materials_index):
                return []

        return search_fn

    def _fill_video_ids(self, script: Dict, materials: Dict):
        """为没有 video_id 的片段用关键词搜索补全；将文件名 video_id 规范化为 hash。"""
        # 构建 filename -> hash 和 hash -> filename 双向映射
        fn_to_id = {vdata.get("filename", ""): vid_id for vid_id, vdata in materials.items()}

        used_ids: set = set()

        # 第一遍：规范化已有的 video_id（可能是文件名或 hash）
        for clip in script.get("clips", []):
            existing = clip.get("video_id", "")
            if existing in materials:
                used_ids.add(existing)
            elif existing in fn_to_id:
                resolved = fn_to_id[existing]
                clip["video_id"] = resolved
                used_ids.add(resolved)

        # 第二遍：补全缺失或无法解析的 video_id
        searcher = None
        try:
            from modules.step4_material_matching.search_videos import VideoSearch
            converted_index = self._to_search_index(materials)

            class _FS(VideoSearch):
                def __init__(self):  # noqa: N807
                    self.index = converted_index

            searcher = _FS()
        except Exception:
            pass

        for clip in script.get("clips", []):
            existing = clip.get("video_id", "")
            if existing and existing in materials:
                clip.setdefault("source_start", 0)
                clip.setdefault("source_end", clip.get("duration", 5))
                continue

            assigned = False
            if searcher is not None:
                query = clip.get("scene_description", clip.get("description", ""))
                try:
                    results = searcher.search(query)
                    for r in results:
                        vid_id = r.get("video_id", "")
                        if vid_id and vid_id not in used_ids:
                            clip["video_id"] = vid_id
                            clip["_match_score"] = r.get("match_score", 0)
                            used_ids.add(vid_id)
                            assigned = True
                            break
                except Exception:
                    pass

            if not assigned and materials:
                for vid_id in materials:
                    if vid_id not in used_ids:
                        clip["video_id"] = vid_id
                        used_ids.add(vid_id)
                        break

            clip.setdefault("source_start", 0)
            clip.setdefault("source_end", clip.get("duration", 5))

    def _write_review_04(self, coverage: Dict, changes: List, script: Dict, materials: Dict):
        vid_names = {h: materials[h].get("filename", h) for h in materials}
        table = ["| # | 场景描述 | 分配素材 | 匹配分 | 时间段 |",
                 "|---|----------|----------|--------|--------|"]
        for clip in script.get("clips", []):
            idx = clip.get("clip_index", "?")
            desc = clip.get("scene_description", "")[:35]
            vid = clip.get("video_id", "未匹配")
            vname = vid_names.get(vid, vid)[:25]
            score = f"{clip.get('_match_score', 0):.1f}"
            ss = clip.get("source_start", 0)
            se = clip.get("source_end", "?")
            table.append(f"| {idx} | {desc} | {vname} | {score} | {ss}s-{se}s |")

        changes_md = ""
        if changes:
            lines = ["### 自动重写片段", ""]
            for c in changes:
                lines += [
                    f"- **[{c['clip_index']}]** {c.get('reason','')}",
                    f"  - 原文: {c.get('original','')[:60]}",
                    f"  - 改写: {c.get('rewritten','')[:60]}",
                    "",
                ]
            changes_md = "\n".join(lines)

        content = f"""# 第4步审核：素材匹配结果

> **操作说明**：
> - 如需替换素材，直接编辑 `data/script_matched.json` 中的 `video_id`
> - 将 `approved: false` 改为 `approved: true`
> - 重新运行 `python workflow.py run --project <项目路径>` 继续

```yaml
approved: false
notes: ""
```

## 匹配统计

- **总片段**: {coverage.get('total_segments', 0)}
- **覆盖率**: {coverage.get('coverage_rate', 0)*100:.1f}%
- **缺失片段**: {len(coverage.get('missing_segments', []))}

## 匹配详情

{chr(10).join(table)}

{changes_md}

## 可用素材列表（供替换参考）

| 文件名 | ID |
|--------|----|
"""
        for vid_id, vdata in materials.items():
            content += f"| {vdata.get('filename','?')} | `{vid_id[:12]}` |\n"

        _atomic_write_text(self.p("reviews", "04_matching.md"), content)

    # ==================================================================
    # Step 5: 帧预览
    # ==================================================================

    def step5_frames(self):
        logger.info("[Step 5] 帧预览")
        self._emit_progress(5, "开始生成帧预览")
        self._check_cancel()
        script = self._load_json("data/script_matched.json")
        materials = self._load_json("data/materials.json")
        from modules.step5_frame_preview import generate_frame_previews

        frames_dir = self.p("preview", "frames")
        ffmpeg = _find_ffmpeg()
        result = generate_frame_previews(
            script=script,
            materials=materials,
            frames_dir=frames_dir,
            ffmpeg=ffmpeg,
            resolve_video_path=lambda vid_id: self._resolve_video_path(vid_id, materials),
            check_cancel=self._check_cancel,
            emit_progress=self._emit_progress,
        )
        extracted = int(result.get("extracted", 0))

        if sys.platform == "darwin" and frames_dir.exists():
            subprocess.run(["open", str(frames_dir)], timeout=5, check=False)

        self.state.set_step_status(
            5, "done",
            review_status="approved",
            output=f"preview/frames/ ({extracted} 帧)",
        )
        logger.info("Step 5 完成  提取了 %d 帧", extracted)
        logger.info("目录: %s", frames_dir)

    # ==================================================================
    # Step 6: 粗剪
    # ==================================================================

    def step6_rough(self):
        logger.info("[Step 6] 粗剪预览（文字粗剪 + 高光快剪）")
        self._emit_progress(15, "开始粗剪预览")
        self._check_cancel()
        script = self._load_json("data/script_matched.json")
        materials = self._load_json("data/materials.json")
        from modules.step6_rough_cut import build_rough_cut

        self.p("preview").mkdir(exist_ok=True)
        rough_path = self.p("preview", "rough_cut.mp4")
        ffmpeg = _find_ffmpeg()
        rc = self.state.render_config
        rough_result = build_rough_cut(
            script=script,
            materials=materials,
            rough_path=rough_path,
            ffmpeg=ffmpeg,
            render_config=rc,
            resolve_video_path=lambda vid_id: self._resolve_video_path(vid_id, materials),
            check_cancel=self._check_cancel,
            emit_progress=self._emit_progress,
        )
        rough_plan_path = self.p("preview", "rough_plan.json")
        _atomic_write_text(
            rough_plan_path,
            json.dumps(rough_result, ensure_ascii=False, indent=2),
        )

        if sys.platform == "darwin":
            subprocess.run(["open", str(rough_path)], timeout=5, check=False)

        self._write_review_05()
        self.state.set_step_status(
            6, "waiting_review",
            output="preview/rough_cut.mp4",
            review_file="reviews/05_render_options.md",
            rough_strategy=rough_result.get("strategy"),
            rough_used_seconds=rough_result.get("used_seconds"),
            rough_segment_count=rough_result.get("segment_count"),
            rough_plan_file="preview/rough_plan.json",
        )
        logger.info("Step 6 完成  粗剪: %s", rough_path)
        logger.info(
            "策略: %s | 片段: %s | 时长: %ss",
            rough_result.get("strategy", "unknown"),
            rough_result.get("segment_count", 0),
            rough_result.get("used_seconds", 0),
        )
        logger.info("计划: %s", rough_plan_path)
        logger.info("请设置渲染选项: %s", self.p("reviews", "05_render_options.md"))

    def _write_review_05(self):
        rc = self.state.render_config
        content = f"""# 第6步审核：粗剪确认 + 渲染选项

> **操作说明**：
> 1. 查看粗剪: `preview/rough_cut.mp4`
> 2. 如需检查粗剪策略，查看 `preview/rough_plan.json`
> 3. 调整下方参数
> 4. 将 `approved: false` 改为 `approved: true`
> 5. 重新运行 `python workflow.py run --project <项目路径>` 开始精渲染

```yaml
approved: false

# 视频
width: {rc.get('width', 1080)}
height: {rc.get('height', 1920)}
fps: {rc.get('fps', 30)}
crf: {rc.get('crf_final', 18)}
preset: {rc.get('preset_final', 'slow')}

# 滤镜
enable_skin_smooth: {str(rc.get('enable_skin_smooth', True)).lower()}
enable_color_grading: {str(rc.get('enable_color_grading', True)).lower()}
enable_skill_enhance: {str(rc.get('enable_skill_enhance', True)).lower()}
aesthetic_preset: "{rc.get('aesthetic_preset', 'travel_story')}"
transition_style: "{rc.get('transition_style', 'fade')}"
transition_duration: {rc.get('transition_duration', 0.35)}
rough_target_seconds: {rc.get('rough_target_seconds', 15)}
rough_max_clips: {rc.get('rough_max_clips', 8)}
rough_merge_gap_s: {rc.get('rough_merge_gap_s', 0.15)}
rough_remove_phrases: "{rc.get('rough_remove_phrases', '嗯,啊,然后,就是,那个')}"
skin_smooth_strength: 0.5

# 音频（填写绝对路径，留空则跳过）
bgm_path: ""
bgm_volume: {rc.get('bgm_volume', 0.3)}
narration_path: ""

# 字幕
subtitle_font: "{rc.get('subtitle_font', 'PingFangSC-Regular')}"
subtitle_size: {rc.get('subtitle_size', 56)}

# watchdog（秒）
timeout_concat_sec: {rc.get('timeout_concat_sec', 1500)}
timeout_stage_sec: {rc.get('timeout_stage_sec', 900)}
timeout_audio_sec: {rc.get('timeout_audio_sec', 480)}
```
"""
        _atomic_write_text(self.p("reviews", "05_render_options.md"), content)

    # ==================================================================
    # Step 7: 分阶段精渲染
    # ==================================================================

    def step7_render(self):
        logger.info("[Step 7] 分阶段精渲染")
        self._emit_progress(30, "开始精渲染")
        self._check_cancel()

        script = self._load_json("data/script_matched.json")
        materials = self._load_json("data/materials.json")
        render_opts = _parse_yaml_block(
            self.p("reviews", "05_render_options.md").read_text(encoding="utf-8")
            if self.p("reviews", "05_render_options.md").exists() else ""
        )

        out_dir = self.p("output")
        out_dir.mkdir(exist_ok=True)

        # 合并配置
        rc = dict(self.state.render_config)
        rc.update({k: v for k, v in render_opts.items()
                   if k in ("crf", "preset", "enable_skin_smooth", "enable_color_grading",
                            "enable_skill_enhance", "aesthetic_preset",
                            "transition_style", "transition_duration",
                            "skin_smooth_strength", "bgm_volume", "subtitle_font",
                            "subtitle_size", "width", "height", "fps",
                            "audio_bitrate", "bgm_path", "narration_path",
                            "timeout_concat_sec", "timeout_stage_sec", "timeout_audio_sec")})

        bgm_path = render_opts.get("bgm_path") or None
        narration_path = render_opts.get("narration_path") or None

        try:
            from modules.step7_final_render.pipeline import RenderPipeline
            self._staged_render_pipeline(script, materials, rc, out_dir,
                                         bgm_path, narration_path)
        except ImportError:
            logger.warning("render.pipeline 不可用，使用 auto_render.py 替代")
            self._staged_render_fallback(script, materials, rc, out_dir,
                                         bgm_path, narration_path)

    @staticmethod
    def _convert_materials_for_pipeline(materials: Dict) -> Dict:
        """将 workflow materials 格式转为 pipeline._resolve_material_path 期望的格式。"""
        converted = {}
        for vid_id, vdata in materials.items():
            path = vdata.get("path") or (
                vdata.get("analysis", {}).get("metadata", {}).get("path", "")
            )
            converted[vid_id] = {"file_info": {"path": path, "filename": vdata.get("filename", "")}}
        return {"videos": converted}

    def _staged_render_pipeline(self, script: Dict, materials: Dict, rc: Dict,
                                  out_dir: Path, bgm_path, narration_path):
        from modules.step7_final_render.pipeline import RenderPipeline

        stage_idx_map = {
            "素材拼接": 1,
            "素材拼接 + 转场": 1,
            "简易磨皮": 2,
            "调色": 3,
            "字幕压制": 4,
            "音频混合": 5,
            "输出封装": 5,
        }

        def _pipeline_progress(stage_name: str, stage_progress: float, detail: str = ""):
            idx = stage_idx_map.get(stage_name, 1)
            try:
                stage_progress_f = max(0.0, min(float(stage_progress), 100.0))
            except Exception:
                stage_progress_f = 0.0
            overall = int(((idx - 1) * 20) + (stage_progress_f * 0.2))
            msg = f"[渲染] {stage_name} {int(stage_progress_f)}%"
            if detail and int(stage_progress_f) % 25 == 0:
                msg = f"{msg} ({detail})"
            self._emit_progress(overall, msg)

        pipeline = RenderPipeline(rc, on_progress=_pipeline_progress, should_cancel=self._is_cancelled)
        base = str(out_dir / "stage")
        clips = script.get("clips") or script.get("segments") or []
        subtitles = script.get("subtitles", [])
        has_face = any(c.get("has_face", False) for c in clips)
        pipeline_materials = self._convert_materials_for_pipeline(materials)
        render_degradations: list = []  # S1: 收集渲染退化事件

        degrade_level = 0
        if self._is_overloaded():
            degrade_level = 1
            degraded = self._degrade_render_config(rc, level=1)
            rc.update(degraded)
            pipeline.config.update(degraded)
            self._emit_progress(
                1,
                f"检测到高负载(load_ratio={self._system_load_ratio():.2f})，预先启用渲染降级 L1",
            )

        stages = [
            ("stage_01_concat.mp4",   lambda inp: pipeline.concat_materials(clips, pipeline_materials, base)),
            ("stage_02_beauty.mp4",   lambda inp: pipeline.apply_beauty(inp, base, has_face, degradations=render_degradations)),
            ("stage_03_color.mp4",    lambda inp: pipeline.apply_color_grading(inp, base)),
            ("stage_04_subtitle.mp4", lambda inp: pipeline.apply_subtitles(inp, subtitles, base, degradations=render_degradations)),
        ]

        def _run_stage_with_retry(stage_i: int, fn, current_input):
            nonlocal degrade_level
            self._check_cancel()
            for attempt in (1, 2):
                try:
                    return fn(current_input) if current_input else fn(None)
                except Exception as stage_err:
                    err_text = str(stage_err or "")
                    if "__CANCELLED__" in err_text:
                        raise
                    timeout_like = "timeout" in err_text.lower() or "超时" in err_text
                    overload_like = self._is_overloaded()
                    if attempt == 1 and (timeout_like or overload_like):
                        next_level = min(2, max(degrade_level + 1, 1))
                        if next_level > degrade_level:
                            degraded = self._degrade_render_config(rc, level=next_level)
                            rc.update(degraded)
                            pipeline.config.update(degraded)
                            degrade_level = next_level
                        self._emit_progress(
                            (stage_i - 1) * 20 + 2,
                            f"Stage {stage_i} 超时/高负载，自动降级到 L{degrade_level} 并重试",
                        )
                        continue
                    raise

        # 初始化 current_input：优先使用粗剪结果作为兜底输入
        rough_cut_path = self.p("preview", "rough_cut.mp4")
        current_input = str(rough_cut_path) if rough_cut_path.exists() else None
        for i, (fname, fn) in enumerate(stages, 1):
            self._check_cancel()
            out_file = out_dir / fname
            if out_file.exists():
                logger.info("[Stage %d/5] %s 已存在，跳过", i, fname)
                current_input = str(out_file)
                self._emit_progress(i * 20, f"Stage {i}/5 复用已有结果")
                continue
            logger.info("[Stage %d/5] %s 处理中...", i, fname)
            try:
                result = _run_stage_with_retry(i, fn, current_input)
            except Exception as stage_err:
                if "__CANCELLED__" in str(stage_err or ""):
                    raise
                logger.warning("Stage %d 失败 (%s: %s)，使用上一阶段结果继续", i, stage_err.__class__.__name__, str(stage_err)[:80])
                self._emit_progress((i - 1) * 20 + 5, f"Stage {i} 失败，使用上一阶段结果兜底")
                result = current_input
            # pipeline 的 _* 方法输出到 base + suffix；重命名到 stage_0N_*.mp4
            if result and result != str(out_file) and Path(result).exists():
                if result != current_input:
                    shutil.move(result, str(out_file))
                else:
                    shutil.copy(result, str(out_file))
            elif not out_file.exists() and current_input:
                shutil.copy(current_input, str(out_file))
            current_input = str(out_file)
            logger.info("-> %s", out_file)
            self._emit_progress(i * 20, f"Stage {i}/5 完成")

        self._check_cancel()
        # Stage 5: audio mix → final.mp4
        final = str(out_dir / "final.mp4")
        if Path(final).exists():
            logger.info("[Stage 5/5] final.mp4 已存在，跳过")
            self._emit_progress(98, "Stage 5/5 复用已有 final.mp4")
        else:
            logger.info("[Stage 5/5] 音频混合 → final.mp4")
            if not current_input:
                raise RuntimeError("Stage 5 无可用输入文件")
            try:
                self._check_cancel()
                try:
                    pipeline.mix_audio(current_input, final, bgm_path, narration_path)
                except Exception as stage_err:
                    if "__CANCELLED__" in str(stage_err or ""):
                        raise
                    timeout_like = "timeout" in str(stage_err).lower() or "超时" in str(stage_err)
                    if timeout_like or self._is_overloaded():
                        next_level = min(2, max(degrade_level + 1, 1))
                        if next_level > degrade_level:
                            degraded = self._degrade_render_config(rc, level=next_level)
                            rc.update(degraded)
                            pipeline.config.update(degraded)
                            degrade_level = next_level
                        self._emit_progress(86, f"Stage 5 触发降级 L{degrade_level} 后重试")
                        pipeline.mix_audio(current_input, final, bgm_path, narration_path)
                    else:
                        raise
            except Exception as stage_err:
                if "__CANCELLED__" in str(stage_err or ""):
                    raise
                logger.warning("Stage 5 失败 (%s: %s)，复制上一阶段结果", stage_err.__class__.__name__, str(stage_err)[:120])
                if current_input and Path(current_input).exists():
                    shutil.copy(current_input, final)
                else:
                    raise RuntimeError("Stage 5 失败且无可用的上一阶段文件") from stage_err

        self._emit_progress(99, "精渲染完成")
        self._finish_render(out_dir, degradations=render_degradations)

    def _staged_render_fallback(self, script: Dict, materials: Dict, rc: Dict,
                                 out_dir: Path, bgm_path, narration_path):
        """当 render.pipeline 不可用时，直接用 auto_render.VideoPipeline。"""
        from modules.step7_final_render.auto_render import VideoPipeline, RenderConfig

        fallback_degradations: list = [{
            "feature": "render_pipeline",
            "expected": "RenderPipeline",
            "actual": "auto_render_fallback",
            "reason": "render.pipeline 不可用，整体退化为 auto_render.py",
            "severity": "warning",
        }]

        config = RenderConfig(
            width=rc.get("width", 1080),
            height=rc.get("height", 1920),
            fps=rc.get("fps", 30),
            crf=rc.get("crf", 18),
            preset=rc.get("preset", "slow"),
            enable_skin_smooth=rc.get("enable_skin_smooth", True),
            enable_color_grading=rc.get("enable_color_grading", True),
            skin_smooth_strength=rc.get("skin_smooth_strength", 0.5),
            bgm_volume=rc.get("bgm_volume", 0.3),
        )

        # 注入 BGM / narration 到 script
        if bgm_path:
            script = dict(script)
            script["bgm"] = {"path": bgm_path}
        if narration_path:
            script = dict(script)
            script["narration"] = {"path": narration_path}

        # 转换 materials 为 auto_render._find_video_path 期望的格式
        pipeline_mat = self._convert_materials_for_pipeline(materials)

        # 写临时 script / materials 文件
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        tmp_script = tmp / "script.json"
        tmp_mat = tmp / "materials.json"
        _atomic_write_text(tmp_script, json.dumps(script, ensure_ascii=False))
        _atomic_write_text(tmp_mat, json.dumps(pipeline_mat, ensure_ascii=False))

        final = str(out_dir / "final.mp4")
        pipeline = VideoPipeline(config)
        self._check_cancel()
        try:
            pipeline.render_from_script(str(tmp_script), str(tmp_mat), final)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._finish_render(out_dir, degradations=fallback_degradations)

    def _finish_render(self, out_dir: Path, *, degradations: Optional[list] = None):
        final = out_dir / "final.mp4"
        if sys.platform == "darwin" and final.exists():
            subprocess.run(["open", str(final)], timeout=5, check=False)

        extra: Dict = {}
        if degradations:
            extra["degradations"] = degradations
            logger.warning(
                "渲染退化通知 (%d 项): %s",
                len(degradations),
                ", ".join(d.get("feature", "?") for d in degradations),
            )
            # S1: 退化事件写入审计日志
            try:
                from modules.app_api.services.audit_log import audit as _audit
                _audit(
                    "render_degradation", "workflow", None,
                    actor="system:render",
                    detail={
                        "count": len(degradations),
                        "features": [d.get("feature", "?") for d in degradations],
                        "items": degradations,
                    },
                )
            except Exception:
                pass  # 审计不可用时不影响渲染

        self.state.set_step_status(
            7, "done",
            review_status="approved",
            output="output/final.mp4",
            **extra,
        )
        logger.info("Step 7 完成  最终视频: %s", final)

        # 列出所有阶段文件
        stages = sorted(out_dir.glob("stage_*.mp4"))
        if stages:
            logger.info("   中间文件（可回滚）:")
            for s in stages:
                size_mb = s.stat().st_size / 1048576
                logger.info("     %s  %.1f MB", s.name, size_mb)

    # ==================================================================
    # 工具
    # ==================================================================

    def _load_json(self, rel: str) -> Dict:
        p = self.p(rel)
        if not p.exists():
            raise FileNotFoundError(f"找不到文件: {p}")
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _resolve_video_path(self, vid_id: str, materials: Dict) -> Optional[str]:
        if Path(vid_id).exists():
            return vid_id
        vdata = materials.get(vid_id, {})
        path = vdata.get("path") or (
            vdata.get("analysis", {}).get("metadata", {}).get("path")
        )
        if path and Path(path).exists():
            return path
        # Path-traversal guard: workflow.json is user-editable, so a tampered
        # filename like "../../../etc/passwd" would escape videos_dir and
        # flow into downstream steps (ffprobe/ffmpeg) that read the path.
        # Use relative_to to reject any resolved path outside the base.
        filename = vdata.get("filename", "")
        if filename:
            videos_base = Path(self.state.videos_dir).resolve()
            guess = (Path(self.state.videos_dir) / filename).resolve()
            try:
                guess.relative_to(videos_base)
            except ValueError:
                return None  # traversal attempt — refuse to resolve
            if guess.exists():
                return str(guess)
        return None

    def parse_review(self, step_n: int) -> Tuple[bool, Dict]:
        """解析某步的审核文件，返回 (is_approved, parsed_dict)。"""
        step = self.state.get_step(step_n)
        review_file = step.get("review_file")
        if not review_file:
            return True, {}
        rpath = self.p(review_file)
        if not rpath.exists():
            return False, {}
        parsed = _parse_yaml_block(rpath.read_text(encoding="utf-8"))
        is_approved = parsed.get("approved", False) is True
        return is_approved, parsed


# ═══════════════════════════════════════════════════════════════════════
# CLI 命令
# ═══════════════════════════════════════════════════════════════════════

STEP_METHODS = {
    1: "step1_analyze",
    2: "step2_topics",
    3: "step3_script",
    4: "step4_match",
    5: "step5_frames",
    6: "step6_rough",
    7: "step7_render",
}


def cmd_init(args):
    project_dir = Path(args.project).resolve()
    for sub in ("data", "reviews", "preview", "output"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    config = {
        "use_semantic_index": getattr(args, "semantic", False),
        "ai_provider": getattr(args, "ai", None),
        "ai_base_url": getattr(args, "ai_base_url", None),
        "ai_model": getattr(args, "ai_model", None),
        "render": {
            "width": 1080, "height": 1920, "fps": 30,
            "crf_rough": 28, "crf_final": 18,
            "preset_rough": "ultrafast", "preset_final": "slow",
            "enable_skin_smooth": True, "enable_color_grading": True,
            "enable_skill_enhance": True,
            "aesthetic_preset": "travel_story",
            "transition_style": "fade",
            "transition_duration": 0.35,
            "timeout_concat_sec": 1500,
            "timeout_stage_sec": 900,
            "timeout_audio_sec": 480,
            "bgm_volume": 0.3,
            "subtitle_font": "PingFangSC-Regular", "subtitle_size": 56,
            "audio_bitrate": "192k",
            "rough_target_seconds": 15,
            "rough_max_clips": 8,
            "rough_min_gap_s": 0.25,
            "rough_merge_gap_s": 0.15,
            "rough_remove_phrases": "嗯,啊,然后,就是,那个",
        },
    }
    ws = WorkflowState.create(project_dir, args.videos, config)
    ws.save()
    logger.info("项目初始化完成: %s", project_dir)
    logger.info("   视频目录: %s", args.videos)
    logger.info("   下一步: python workflow.py run --project %s", args.project)


def cmd_run(args):
    project_dir = Path(args.project).resolve()
    ws = WorkflowState(project_dir).load()
    runner = WorkflowRunner(ws)

    target = args.step or ws.data.get("current_step", 1)

    # 检查上一步是否已审核通过
    if target > 1 and not args.force:
        prior = target - 1
        prior_step = ws.get_step(prior)
        if prior_step.get("review_status") != "approved":
            # 尝试自动解析审核文件
            approved, parsed = runner.parse_review(prior)
            if approved:
                field_remap = {
                    2: {"chosen_topic": "chosen_topic", "user_ideas": "user_ideas",
                        "target_duration": "target_duration"},
                }
                remapped = {field_remap.get(prior, {}).get(k, k): v for k, v in parsed.items()}
                ws.approve_review(prior, remapped)
                logger.info("第%s步审核文件已确认通过，继续...", prior)
            else:
                review_path = project_dir / prior_step.get("review_file", "")
                logger.warning("第%s步尚未通过审核。", prior)
                logger.warning("   请编辑: %s", review_path)
                logger.warning("   将 `approved: false` 改为 `approved: true` 后重跑 run")
                sys.exit(1)

    # 检查当前步是否已完成（自动审核通过的步骤在前一次运行时未推进 current_step）
    current_step_data = ws.get_step(target)
    if (current_step_data.get("status") == "done"
            and current_step_data.get("review_status") == "approved"
            and not args.force):
        ws.data["current_step"] = target + 1
        ws.save()
        target = target + 1
        if target > 7:
            logger.info("所有步骤已完成！")
            cmd_status_print(ws)
            return
        current_step_data = ws.get_step(target)

    # 检查当前步是否处于等待审核状态（用户刚改完文件重跑）
    if current_step_data.get("status") == "waiting_review" and not args.force:
        approved, parsed = runner.parse_review(target)
        if approved:
            field_remap = {
                2: {"chosen_topic": "chosen_topic", "user_ideas": "user_ideas",
                    "target_duration": "target_duration"},
            }
            remapped = {field_remap.get(target, {}).get(k, k): v for k, v in parsed.items()}
            ws.approve_review(target, remapped)
            logger.info("第%s步审核通过，进入第%s步", target, target + 1)
            # 自动执行下一步
            target = target + 1
            if target > 7:
                logger.info("所有步骤已完成！")
                cmd_status_print(ws)
                return
        else:
            review_path = project_dir / current_step_data.get("review_file", "")
            logger.info("第%s步等待审核中。", target)
            logger.info("   请编辑: %s", review_path)
            sys.exit(0)

    if target not in STEP_METHODS:
        logger.error("步骤 %s 不存在（有效范围 1-7）", target)
        sys.exit(1)

    ws.set_step_status(target, "running")
    try:
        method = getattr(runner, STEP_METHODS[target])
        method()
        # 若步骤自动审核通过（无需用户改文件），自动推进 current_step
        ws.load()  # 重新加载（method 内部可能已保存状态）
        step_data = ws.get_step(target)
        if (step_data.get("status") == "done"
                and step_data.get("review_status") == "approved"
                and ws.data.get("current_step") == target):
            ws.data["current_step"] = target + 1
            ws.save()
    except Exception as e:
        ws.set_step_status(target, "error", error=str(e))
        raise


def cmd_status(args):
    project_dir = Path(args.project).resolve()
    ws = WorkflowState(project_dir).load()
    cmd_status_print(ws)


def cmd_status_print(ws: WorkflowState):
    logger.info("工作流状态: %s", ws.project_dir)
    logger.info("─" * 55)
    for n in range(1, 8):
        step = ws.get_step(n)
        status = step.get("status", "not_started")
        review = step.get("review_status") or ""
        icon = WorkflowState.STATUS_ICON.get(status, "  ")
        name = WorkflowState.STEP_NAMES.get(n, f"Step {n}")
        review_str = f"  [审核:{review}]" if review else ""
        current = " ←" if ws.data.get("current_step") == n else ""
        logger.info("  [%s] Step %s: %s%s%s", icon, n, name, review_str, current)


# ═══════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="workflow.py",
        description="VideoEditer 7步工作流",
    )
    sub = parser.add_subparsers(dest="command")

    # init
    p_init = sub.add_parser("init", help="初始化新项目")
    p_init.add_argument("--videos", required=True, help="源视频目录")
    p_init.add_argument("--project", required=True, help="项目目录（将被创建）")
    p_init.add_argument("--semantic", action="store_true", help="启用 CLIP 语义索引（可选）")
    p_init.add_argument("--ai", default=None,
                        choices=["anthropic", "openai", "moonshot", "kimi", "qwen", "gemini", "maxmini"],
                        help="AI 提供方（默认自动检测环境变量）")
    p_init.add_argument("--ai-base-url", default=None, help="OpenAI 兼容 API 的 base_url")
    p_init.add_argument("--ai-model", default=None, help="AI 模型名称")

    # run
    p_run = sub.add_parser("run", help="运行工作流步骤")
    p_run.add_argument("--project", required=True, help="项目目录")
    p_run.add_argument("--step", type=int, default=None, help="指定步骤 (1-7)，省略则自动推进")
    p_run.add_argument("--force", action="store_true", help="强制重新执行（忽略已完成状态）")

    # status
    p_status = sub.add_parser("status", help="查看工作流状态")
    p_status.add_argument("--project", required=True, help="项目目录")

    args = parser.parse_args()

    if args.command == "init":
        cmd_init(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
