"""Capability I/O and social export helpers extracted from server.py."""

import json
from pathlib import Path
from typing import Optional, Dict, List, Any

from flask import request

# ── Module-level state (injected via init()) ──
_project_dir = None
_ws = None  # WorkflowState ref


def _get_project_dir():
    """Always read _project_dir from server module to stay in sync with tests."""
    try:
        from modules.app_api import server
        return server._project_dir
    except Exception:
        return _project_dir


def init(*, project_dir=None, ws=None):
    global _project_dir, _ws
    if project_dir is not None:
        _project_dir = project_dir
    if ws is not None:
        _ws = ws


def _slugify(text: str) -> str:
    raw = str(text or "").strip().lower()
    cleaned = []
    for ch in raw:
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {"-", "_", " ", "/"}:
            cleaned.append("-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:64] or "topic"


def _extract_material_semantics(materials: Dict, limit: int = 80) -> List[Dict]:
    out: List[Dict] = []
    for _, vdata in materials.items():
        sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic"), dict) else {}
        scene = (
            vdata.get("analysis", {})
            .get("local_analysis", {})
            .get("scene", {})
        )
        item = {
            "setting": sem.get("setting") or "",
            "activity": sem.get("activity") or "",
            "mood": sem.get("mood") or scene.get("mood") or "",
            "time_of_day": sem.get("time_of_day") or "",
            "weather": sem.get("weather") or "",
            "narrative_role": sem.get("narrative_role") or "",
        }
        if any(str(v).strip() for v in item.values()):
            out.append(item)
        if len(out) >= max(int(limit), 1):
            break
    return out


def _parse_platforms(payload_value) -> List[str]:
    if isinstance(payload_value, list):
        return [str(x).strip().lower() for x in payload_value if str(x).strip()]
    text = str(payload_value or "").strip()
    if not text:
        return []
    return [x.strip().lower() for x in text.replace("\uff0c", ",").split(",") if x.strip()]


def _parse_capability_input_mode(raw_value: Any, default: str = "project") -> str:
    mode = str(raw_value or default).strip().lower()
    if mode not in {"inline", "project"}:
        mode = default if default in {"inline", "project"} else "project"
    return mode


def _request_json_any_method() -> Dict[str, Any]:
    try:
        payload = request.get_json(silent=True)
    except Exception:
        payload = None
    return payload if isinstance(payload, dict) else {}


def _capability_base_dir(input_mode: str) -> Path:
    if input_mode == "project" and _get_project_dir() is not None:
        return _get_project_dir()
    if _get_project_dir() is not None:
        return _get_project_dir()
    return Path.cwd()


def _resolve_path_with_base(path_raw: str, *, base_dir: Optional[Path]) -> Path:
    p = Path(str(path_raw or "").strip()).expanduser()
    if not p.is_absolute():
        anchor = base_dir if base_dir is not None else Path.cwd()
        p = (anchor / p).resolve()
    return p


def _coerce_script_input(payload: Dict[str, Any], *, input_mode: str) -> Dict[str, Any]:
    script_raw = payload.get("script")
    if isinstance(script_raw, dict):
        return script_raw
    clips_raw = payload.get("clips")
    subtitles_raw = payload.get("subtitles")
    if isinstance(clips_raw, list) or isinstance(subtitles_raw, list):
        return {
            "clips": clips_raw if isinstance(clips_raw, list) else [],
            "subtitles": subtitles_raw if isinstance(subtitles_raw, list) else [],
        }
    if input_mode == "project":
        from modules.app_api.services.job_analytics_service import _read_script_json
        return _read_script_json()
    return {}


def _coerce_materials_input(payload: Dict[str, Any], *, input_mode: str) -> Dict[str, Any]:
    materials = payload.get("materials")
    if isinstance(materials, dict):
        return materials
    if input_mode == "project":
        from modules.app_api.server import _read_project_json
        loaded = _read_project_json("materials.json", fallback={})
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _extract_subtitles_from_script(script: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    subtitles = script.get("subtitles", []) if isinstance(script, dict) else []
    for idx, item in enumerate(subtitles, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("cn_text") or "").strip()
        cn_text = str(item.get("cn_text") or text).strip()
        en_text = str(item.get("en_text") or "").strip()
        try:
            start = float(item.get("start_time"))
            end = float(item.get("end_time"))
        except Exception:
            continue
        if end <= start:
            continue
        out.append(
            {
                "index": int(item.get("index", idx) or idx),
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "text": text,
                "cn_text": cn_text,
                "en_text": en_text,
            }
        )
    return out


def _script_to_text_blocks(script: Dict[str, Any]) -> Dict[str, str]:
    clips = script.get("clips", []) if isinstance(script.get("clips"), list) else []
    subtitles = script.get("subtitles", []) if isinstance(script.get("subtitles"), list) else []

    script_parts: List[str] = []
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        for key in ("text", "narration", "voiceover", "description", "summary"):
            val = str(clip.get(key) or "").strip()
            if val:
                script_parts.append(val)
                break

    voice_parts: List[str] = []
    for sub in subtitles:
        if not isinstance(sub, dict):
            continue
        val = str(sub.get("cn_text") or sub.get("text") or "").strip()
        if val:
            voice_parts.append(val)

    return {
        "script_text": "\n".join(script_parts).strip(),
        "voiceover_text": "\n".join(voice_parts).strip(),
    }


def _parse_str_list(payload_value) -> List[str]:
    if isinstance(payload_value, list):
        return [str(x).strip() for x in payload_value if str(x).strip()]
    text = str(payload_value or "").strip()
    if not text:
        return []
    return [x.strip() for x in text.replace("\uff0c", ",").split(",") if x.strip()]


def _default_master_video_path() -> Optional[Path]:
    if _get_project_dir() is None:
        return None
    candidates = [
        _get_project_dir() / "output" / "final.mp4",
        _get_project_dir() / "preview" / "rough_cut.mp4",
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


def _default_bgm_library_dirs(custom_dir: str = "", custom_dirs: Optional[List[str]] = None) -> List[Path]:
    """Resolve candidate BGM library folders with project defaults."""
    if _get_project_dir() is None:
        return []
    seen = set()
    resolved: List[Path] = []

    candidates: List[str] = []
    if str(custom_dir or "").strip():
        candidates.append(str(custom_dir))
    if isinstance(custom_dirs, list):
        candidates.extend(str(x) for x in custom_dirs if str(x).strip())

    defaults = [
        _get_project_dir() / "assets" / "bgm",
        _get_project_dir() / "assets" / "music",
        _get_project_dir() / "data" / "bgm",
        _get_project_dir() / "data" / "music",
        _get_project_dir() / "bgm",
        _get_project_dir() / "music",
    ]
    candidates.extend(str(x) for x in defaults)

    for raw in candidates:
        p = Path(str(raw or "").strip()).expanduser()
        if not p.is_absolute():
            p = (_get_project_dir() / p).resolve()
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists() and p.is_dir():
            resolved.append(p)
    return resolved


def _default_bgm_output_dir(custom_dir: str = "") -> Optional[Path]:
    """Resolve BGM download output dir."""
    if _get_project_dir() is None:
        return None
    raw = str(custom_dir or "").strip()
    if raw:
        p = Path(raw).expanduser()
        if not p.is_absolute():
            p = (_get_project_dir() / p).resolve()
        return p
    return (_get_project_dir() / "data" / "audio_voice" / "bgm").resolve()


def _is_remote_media_url(value: str) -> bool:
    text = str(value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://")


def _append_social_export_history(record: Dict, max_entries: int = 100) -> List[Dict]:
    """Persist social export batch summary into workflow.json and data file."""
    from modules.app_api.server import _project_data_path
    if _ws is None or _get_project_dir() is None:
        return []
    ws = _ws
    history = ws.data.get("social_export_history", [])
    if not isinstance(history, list):
        history = []
    history.append(record)
    if len(history) > max(int(max_entries), 10):
        history = history[-max(int(max_entries), 10):]
    ws.data["social_export_history"] = history
    ws.save()

    p = _project_data_path("social_export_history.json")
    if p is not None:
        p.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    return history


def _get_social_export_history() -> List[Dict]:
    from modules.app_api.server import _project_data_path
    if _ws is not None:
        raw = _ws.data.get("social_export_history", [])
        if isinstance(raw, list):
            return raw
    p = _project_data_path("social_export_history.json")
    if p is not None and p.exists():
        try:
            parsed = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return []
    return []


def _normalize_export_template_id(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    cleaned = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            cleaned.append(ch)
        elif ch in {"-", " ", "/"}:
            cleaned.append("_")
    out = "".join(cleaned).strip("_")
    while "__" in out:
        out = out.replace("__", "_")
    return out[:64]


def _normalize_export_template_payload(payload: Dict) -> Dict:
    if not isinstance(payload, dict):
        raise ValueError("\u6a21\u677f\u53c2\u6570\u5fc5\u987b\u662f\u5bf9\u8c61")
    platform_id_raw = str(payload.get("platform_id", "") or payload.get("template_id", "")).strip()
    name_raw = str(payload.get("name", "") or "").strip()
    platform_id = _normalize_export_template_id(platform_id_raw or name_raw)
    if not platform_id:
        raise ValueError("\u6a21\u677f ID \u4e0d\u80fd\u4e3a\u7a7a")
    if not name_raw:
        raise ValueError("\u6a21\u677f\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")

    def _to_int(value, default: int, min_val: int) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = int(default)
        return max(parsed, min_val)

    return {
        "platform_id": platform_id,
        "name": name_raw,
        "width": _to_int(payload.get("width", 1080), 1080, 16),
        "height": _to_int(payload.get("height", 1920), 1920, 16),
        "fps": _to_int(payload.get("fps", 30), 30, 1),
        "video_bitrate": str(payload.get("video_bitrate", "10M") or "10M").strip() or "10M",
        "audio_bitrate": str(payload.get("audio_bitrate", "192k") or "192k").strip() or "192k",
        "max_duration_s": _to_int(payload.get("max_duration_s", 180), 180, 1),
    }


def _get_social_export_templates() -> Dict[str, Dict]:
    from modules.app_api.server import _read_project_json
    if _get_project_dir() is None:
        return {}
    raw = _read_project_json("social_export_templates.json", fallback={})
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict] = {}
    for _, item in raw.items():
        try:
            normalized = _normalize_export_template_payload(item)
        except Exception:
            continue
        out[normalized["platform_id"]] = normalized
    return out


def _save_social_export_templates(templates: Dict[str, Dict]) -> Dict[str, Dict]:
    from modules.app_api.server import _project_data_path
    if _get_project_dir() is None:
        return {}
    out: Dict[str, Dict] = {}
    if isinstance(templates, dict):
        for _, item in templates.items():
            try:
                normalized = _normalize_export_template_payload(item)
            except Exception:
                continue
            out[normalized["platform_id"]] = normalized
    p = _project_data_path("social_export_templates.json")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _coerce_social_export_overrides(payload: Dict[str, Any], *, input_mode: str) -> Dict[str, Dict]:
    explicit = payload.get("profile_overrides")
    if isinstance(explicit, dict):
        out: Dict[str, Dict] = {}
        for key, value in explicit.items():
            if not isinstance(value, dict):
                continue
            try:
                normalized = _normalize_export_template_payload(value)
            except Exception:
                continue
            out[str(normalized.get("platform_id") or key)] = normalized
        return out

    templates = payload.get("templates")
    if isinstance(templates, dict):
        out: Dict[str, Dict] = {}
        for _, value in templates.items():
            if not isinstance(value, dict):
                continue
            try:
                normalized = _normalize_export_template_payload(value)
            except Exception:
                continue
            out[normalized["platform_id"]] = normalized
        if out:
            return out
    if isinstance(templates, list):
        out: Dict[str, Dict] = {}
        for value in templates:
            if not isinstance(value, dict):
                continue
            try:
                normalized = _normalize_export_template_payload(value)
            except Exception:
                continue
            out[normalized["platform_id"]] = normalized
        if out:
            return out

    if input_mode == "project" and _get_project_dir() is not None:
        return _get_social_export_templates()
    return {}
