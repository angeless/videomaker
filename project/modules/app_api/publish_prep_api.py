"""Independent API routes for publish preparation capability."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import json

from flask import Blueprint, jsonify, request

from modules.capabilities.publish_prep import (
    list_publish_profiles,
    normalize_platform_id,
    prepare_publish_package,
)
from modules.step2_topic_planning.ai_client import AIClient


def create_publish_prep_blueprint(
    *,
    project_dir_getter: Callable[[], Optional[Path]],
    ai_settings_getter: Optional[Callable[[], Dict[str, Any]]] = None,
) -> Blueprint:
    """Create standalone publish-prep capability routes."""
    bp = Blueprint("publish_prep_api", __name__)

    def _profiles_path() -> Optional[Path]:
        project_dir = project_dir_getter()
        if project_dir is None:
            return None
        return Path(project_dir) / "data" / "publish_prep_profiles.json"

    def _result_path() -> Optional[Path]:
        project_dir = project_dir_getter()
        if project_dir is None:
            return None
        return Path(project_dir) / "data" / "publish_prep_last.json"

    def _load_saved_profiles() -> Dict[str, Dict]:
        path = _profiles_path()
        if path is None or not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return _coerce_profile_overrides(payload)

    def _save_profiles(overrides: Dict[str, Dict]) -> Optional[Path]:
        path = _profiles_path()
        if path is None:
            return None
        # Round-15: atomic write — crash mid-save used to zero the
        # profiles file, wiping user-saved platform overrides.
        from modules.app_api.param_utils import atomic_write_json
        atomic_write_json(path, overrides)
        return path

    @bp.route("/api/capabilities/publish_prep/profiles", methods=["GET"])
    def api_publish_prep_profiles():
        saved = _load_saved_profiles()
        profiles = list_publish_profiles(saved)
        return jsonify(
            {
                "ok": True,
                "profiles": profiles,
                "profile_count": len(profiles),
                "override_count": len(saved),
                "profiles_file": str(_profiles_path()) if _profiles_path() else None,
            }
        )

    @bp.route("/api/capabilities/publish_prep/profiles", methods=["POST"])
    def api_publish_prep_profiles_upsert():
        payload = request.json or {}
        incoming = _coerce_profile_overrides(payload.get("profiles", payload))
        if not incoming:
            return jsonify({"error": "profiles 不能为空，且需包含 platform_id 或平台键名"}), 400

        merge = bool(payload.get("merge", True))
        existing = _load_saved_profiles()
        merged = dict(existing) if merge else {}
        merged.update(incoming)

        out_path = _save_profiles(merged)
        profiles = list_publish_profiles(merged)
        return jsonify(
            {
                "ok": True,
                "profiles": profiles,
                "profile_count": len(profiles),
                "override_count": len(merged),
                "profiles_file": str(out_path) if out_path else None,
            }
        )

    @bp.route("/api/capabilities/publish_prep/generate", methods=["POST"])
    def api_publish_prep_generate():
        payload = request.json or {}
        input_mode = _parse_input_mode(payload.get("input_mode", "project"))

        script_text = str(payload.get("script_text", "") or "").strip()
        voiceover_text = str(payload.get("voiceover_text", "") or "").strip()
        if input_mode == "project" and (not script_text or not voiceover_text):
            project_dir = project_dir_getter()
            script_fallback, voiceover_fallback = _load_project_script_text(project_dir)
            if not script_text:
                script_text = script_fallback
            if not voiceover_text:
                voiceover_text = voiceover_fallback

        if not script_text and not voiceover_text:
            return jsonify({"error": "script_text 和 voiceover_text 不能同时为空"}), 400

        platforms = _coerce_platforms(payload.get("platforms", payload.get("platform_ids", [])))
        if not platforms:
            platforms = ["generic"]

        platform_content_type = str(payload.get("platform_content_type", "video_post") or "video_post").strip().lower()
        if platform_content_type not in {"video_post", "article_post"}:
            platform_content_type = "video_post"

        use_saved_profiles = bool(payload.get("use_saved_profiles", True))
        request_overrides = _coerce_profile_overrides(payload.get("profile_overrides", {}))
        merged_overrides: Dict[str, Dict] = {}
        if use_saved_profiles:
            merged_overrides.update(_load_saved_profiles())
        merged_overrides.update(request_overrides)

        warnings: List[str] = []
        use_llm = bool(payload.get("use_llm", False))
        text_generator, llm_meta = _build_llm_text_generator(
            payload=payload,
            use_llm=use_llm,
            warnings=warnings,
            ai_settings_getter=ai_settings_getter,
        )

        result = prepare_publish_package(
            script_text=script_text,
            voiceover_text=voiceover_text,
            platform_ids=platforms,
            platform_content_type=platform_content_type,
            profile_overrides=merged_overrides,
            text_generator=text_generator,
        )

        store_result = bool(payload.get("store_result", True))
        out_path = None
        if store_result:
            out_path = _result_path()
            if out_path is not None:
                from modules.app_api.param_utils import atomic_write_json
                atomic_write_json(out_path, result)

        return jsonify(
            {
                "ok": True,
                "input_mode": input_mode,
                "platforms": platforms,
                "platform_content_type": platform_content_type,
                "use_llm": use_llm,
                "llm": llm_meta,
                "result": result,
                "warnings": warnings,
                "output": str(out_path) if out_path else None,
            }
        )

    return bp


def _parse_input_mode(raw: Any) -> str:
    mode = str(raw or "project").strip().lower()
    return mode if mode in {"inline", "project"} else "project"


def _load_project_script_text(project_dir: Optional[Path]) -> Tuple[str, str]:
    if project_dir is None:
        return "", ""

    for file_name in ("script_matched.json", "script_draft.json"):
        path = Path(project_dir) / "data" / file_name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        clips = payload.get("clips", []) if isinstance(payload.get("clips"), list) else []
        subtitles = payload.get("subtitles", []) if isinstance(payload.get("subtitles"), list) else []

        script_parts: List[str] = []
        for clip in clips:
            if not isinstance(clip, dict):
                continue
            for key in ("text", "narration", "voiceover", "description", "summary"):
                text = str(clip.get(key) or "").strip()
                if text:
                    script_parts.append(text)
                    break

        voice_parts: List[str] = []
        for sub in subtitles:
            if not isinstance(sub, dict):
                continue
            text = str(sub.get("cn_text") or sub.get("text") or "").strip()
            if text:
                voice_parts.append(text)

        script_text = "\n".join(script_parts).strip()
        voiceover_text = "\n".join(voice_parts).strip()
        if script_text or voiceover_text:
            return script_text, voiceover_text

    return "", ""


def _build_llm_text_generator(
    *,
    payload: Dict[str, Any],
    use_llm: bool,
    warnings: List[str],
    ai_settings_getter: Optional[Callable[[], Dict[str, Any]]],
):
    if not use_llm:
        return None, {"enabled": False, "provider": "", "model": "", "fallback": True}

    settings = ai_settings_getter() if callable(ai_settings_getter) else {}
    settings = settings if isinstance(settings, dict) else {}

    provider = str(payload.get("llm_provider") or settings.get("provider") or "").strip().lower()
    model = str(payload.get("llm_model") or settings.get("ai_model") or "").strip()
    base_url = str(payload.get("llm_base_url") or settings.get("ai_base_url") or "").strip()
    api_key = str(payload.get("llm_api_key") or "").strip()

    if not api_key:
        if provider == "anthropic":
            api_key = str(settings.get("anthropic_api_key") or "").strip()
        else:
            api_key = str(settings.get("openai_api_key") or "").strip()

    if not provider:
        provider = "openai" if api_key else ""

    if not api_key:
        warnings.append("use_llm=true 但未配置可用 API Key，已降级为规则引擎。")
        return None, {"enabled": True, "provider": provider, "model": model, "fallback": True}

    client = AIClient(
        provider=provider or None,
        api_key=api_key,
        base_url=base_url or None,
        model=model or None,
        temperature=0.35,
        max_tokens=500,
    )
    warn_once = {"emitted": False}

    def _generator(platform_id: str, field: str, prompt: str) -> str:
        user_prompt = (
            f"平台: {platform_id}\n"
            f"字段: {field}\n"
            f"请严格返回该字段结果，不要额外说明。\n\n{prompt}"
        )
        try:
            return str(
                client.chat(
                    messages=[{"role": "user", "content": user_prompt}],
                    system="你是社媒内容编辑助手，输出需简洁、结构明确。",
                )
                or ""
            ).strip()
        except Exception as exc:
            if not warn_once["emitted"]:
                warnings.append(f"publish_prep LLM 调用失败，已降级规则引擎: {exc}")
                warn_once["emitted"] = True
            return ""

    return _generator, {
        "enabled": True,
        "provider": str(client.provider or ""),
        "model": str(client.model or ""),
        "fallback": False,
    }


def _coerce_platforms(raw: Any) -> List[str]:
    if isinstance(raw, str):
        items = [x.strip() for x in raw.replace("，", ",").split(",") if x and x.strip()]
    elif isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
    else:
        items = []

    out: List[str] = []
    seen = set()
    for item in items:
        pid = normalize_platform_id(item)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def _coerce_profile_overrides(raw: Any) -> Dict[str, Dict]:
    if isinstance(raw, list):
        out: Dict[str, Dict] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            pid = normalize_platform_id(item.get("platform_id"))
            if not pid:
                continue
            out[pid] = item
        return out

    if not isinstance(raw, dict):
        return {}

    if isinstance(raw.get("platform_id"), str):
        pid = normalize_platform_id(raw.get("platform_id"))
        if pid:
            payload = dict(raw)
            payload["platform_id"] = pid
            return {pid: payload}

    source = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else raw
    out: Dict[str, Dict] = {}
    for key, value in source.items():
        if not isinstance(value, dict):
            continue
        pid = normalize_platform_id(key or value.get("platform_id"))
        if not pid:
            continue
        payload = dict(value)
        payload["platform_id"] = pid
        out[pid] = payload
    return out
