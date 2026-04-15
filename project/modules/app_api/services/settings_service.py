"""Settings / config helpers extracted from server.py (L1-6)."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

# ── Module-level state (defaults; overwritten by init()) ────────────
_library = None        # GlobalMediaLibrary instance
_secret_store = None   # SecretStore instance
_project_dir = None    # Path | None


def init(*, library=None, secret_store=None, project_dir=None):
    global _library, _secret_store, _project_dir
    if library is not None:
        _library = library
    if secret_store is not None:
        _secret_store = secret_store
    if project_dir is not None:
        _project_dir = project_dir


def _get_library():
    """Return library, preferring server module's copy for test compatibility."""
    import modules.app_api.server as _srv
    return getattr(_srv, "_library", None) or _library


def _get_secret_store():
    """Return secret_store, preferring server module's copy for test compatibility."""
    import modules.app_api.server as _srv
    return getattr(_srv, "_secret_store", None) or _secret_store


# ── Constants ───────────────────────────────────────────────────────

_DEFAULT_UI_SETTINGS: Dict[str, Any] = {
    "onboarding_completed": False,
    "creator_mode": True,
    "font_scale": 1.0,
    "preferred_production_view": "hub",
    "default_videos_dir": "",
    "default_project_dir": "",
    "auto_open_last_project": True,
    "last_project_dir": "",
}

_DEFAULT_PUBLISH_SETTINGS: Dict[str, Any] = {
    "connectors": {},
}
_PUBLISH_SECRET_KEEP_SENTINEL = "__KEEP__"

_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_AI_PROVIDER_CATALOG: Dict[str, Dict[str, Any]] = {
    "openai": {
        "label": "OpenAI",
        "aliases": ["openai"],
        "default_base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "o4-mini", "o3-mini"],
        "embedding_models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
    },
    "anthropic": {
        "label": "Anthropic",
        "aliases": ["anthropic", "claude"],
        "default_base_url": "https://api.anthropic.com",
        "models": ["claude-sonnet-4-6", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"],
        "embedding_models": [],
    },
    "moonshot": {
        "label": "Moonshot / Kimi",
        "aliases": ["moonshot", "kimi"],
        "default_base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "embedding_models": [],
    },
    "qwen": {
        "label": "Qwen",
        "aliases": ["qwen"],
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
        "embedding_models": [],
    },
    "gemini": {
        "label": "Gemini",
        "aliases": ["gemini"],
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"],
        "embedding_models": [],
    },
    "maxmini": {
        "label": "MiniMax",
        "aliases": ["maxmini", "minimax"],
        "default_base_url": "https://api.minimax.chat/v1",
        "models": ["abab6.5s-chat", "abab6.5t-chat", "abab6.5g-chat"],
        "embedding_models": [],
    },
}
_AI_PROVIDER_ALIASES: Dict[str, str] = {}
for _provider_id, _provider_cfg in _AI_PROVIDER_CATALOG.items():
    aliases = _provider_cfg.get("aliases", []) if isinstance(_provider_cfg, dict) else []
    for alias in aliases:
        key = str(alias or "").strip().lower()
        if key:
            _AI_PROVIDER_ALIASES[key] = _provider_id
    _AI_PROVIDER_ALIASES[_provider_id] = _provider_id


# ── Functions ───────────────────────────────────────────────────────

def _prepare_project_dirs(project_path: Path):
    for sub in ("data", "reviews", "preview", "output"):
        (project_path / sub).mkdir(parents=True, exist_ok=True)


def _settings_path() -> Path:
    p = _get_library().db_path.parent / "app_settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _read_settings() -> Dict:
    p = _settings_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_settings(data: Dict):
    # Atomic write — a crash between truncate and write here used to wipe
    # ALL settings including openai_api_key_ref / anthropic_api_key_ref
    # pointers (round-12 P0 finding). Now writes via temp + fsync + rename.
    from modules.app_api.param_utils import atomic_write_json
    atomic_write_json(_settings_path(), data)


def _normalize_production_view(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    if key in {"workflow", "graph"}:
        return "workflow"
    return "hub"


def _normalize_font_scale(raw: Any) -> float:
    try:
        value = float(raw)
    except Exception:
        value = 1.0
    return round(max(0.85, min(value, 1.45)), 2)


def _load_ui_settings() -> Dict[str, Any]:
    src = _read_settings().get("ui", {})
    if not isinstance(src, dict):
        src = {}
    out = dict(_DEFAULT_UI_SETTINGS)
    out["onboarding_completed"] = bool(src.get("onboarding_completed", out["onboarding_completed"]))
    out["creator_mode"] = bool(src.get("creator_mode", out["creator_mode"]))
    out["font_scale"] = _normalize_font_scale(src.get("font_scale", out["font_scale"]))
    out["preferred_production_view"] = _normalize_production_view(
        src.get("preferred_production_view", out["preferred_production_view"])
    )
    out["default_videos_dir"] = str(src.get("default_videos_dir", out["default_videos_dir"]) or "").strip()
    out["default_project_dir"] = str(src.get("default_project_dir", out["default_project_dir"]) or "").strip()
    out["auto_open_last_project"] = bool(src.get("auto_open_last_project", out["auto_open_last_project"]))
    out["last_project_dir"] = str(src.get("last_project_dir", out["last_project_dir"]) or "").strip()
    return out


def _save_ui_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    settings = _read_settings()
    ui = settings.get("ui", {})
    if not isinstance(ui, dict):
        ui = {}

    if "onboarding_completed" in src:
        ui["onboarding_completed"] = bool(src.get("onboarding_completed"))
    if "creator_mode" in src:
        ui["creator_mode"] = bool(src.get("creator_mode"))
    if "font_scale" in src:
        ui["font_scale"] = _normalize_font_scale(src.get("font_scale"))
    if "preferred_production_view" in src:
        ui["preferred_production_view"] = _normalize_production_view(src.get("preferred_production_view"))
    if "default_videos_dir" in src:
        ui["default_videos_dir"] = str(src.get("default_videos_dir", "") or "").strip()
    if "default_project_dir" in src:
        ui["default_project_dir"] = str(src.get("default_project_dir", "") or "").strip()
    if "auto_open_last_project" in src:
        ui["auto_open_last_project"] = bool(src.get("auto_open_last_project"))
    if "last_project_dir" in src:
        ui["last_project_dir"] = str(src.get("last_project_dir", "") or "").strip()

    settings["ui"] = ui
    _write_settings(settings)
    return _load_ui_settings()


def _remember_last_project(project_path: Path):
    if not isinstance(project_path, Path):
        return
    try:
        resolved = str(project_path.resolve())
        _save_ui_settings({"last_project_dir": resolved})
        # Also maintain recent_projects list
        _add_to_recent_projects(resolved, project_path.name)
    except Exception:
        pass


def _add_to_recent_projects(path_str: str, name: str):
    """Maintain a recent_projects list (max 20) in settings."""
    try:
        settings = _read_settings()
        recents = settings.get("recent_projects", [])
        if not isinstance(recents, list):
            recents = []
        # Remove existing entry for this path
        recents = [r for r in recents if r.get("path") != path_str]
        # Prepend new entry
        recents.insert(0, {
            "path": path_str,
            "name": name,
            "opened_at": datetime.now().isoformat(timespec="seconds"),
        })
        # Trim to 20
        recents = recents[:20]
        settings["recent_projects"] = recents
        _write_settings(settings)
    except Exception:
        pass


def _get_recent_projects() -> List[Dict[str, Any]]:
    """Return recent projects with status info."""
    settings = _read_settings()
    recents = settings.get("recent_projects", [])
    if not isinstance(recents, list):
        return []
    result = []
    for entry in recents[:20]:
        if not isinstance(entry, dict):
            continue
        p = entry.get("path", "")
        if not p:
            continue
        proj_path = Path(p)
        wf_file = proj_path / "workflow.json"
        status = "unknown"
        current_step = 0
        total_steps = 7
        completed_steps = 0
        if wf_file.exists():
            try:
                wf = json.loads(wf_file.read_text(encoding="utf-8"))
                current_step = int(wf.get("current_step", 0))
                total_steps = int(wf.get("total_steps", 7))
                completed_steps = len(wf.get("completed_steps", []))
                if completed_steps >= total_steps:
                    status = "completed"
                elif current_step > 0:
                    status = "in_progress"
                else:
                    status = "draft"
            except Exception:
                status = "draft"
        else:
            status = "missing"
        if status == "missing" and not proj_path.exists():
            continue  # M3: skip missing/deleted projects
        result.append({
            "path": p,
            "name": entry.get("name", proj_path.name),
            "opened_at": entry.get("opened_at", ""),
            "status": status,
            "current_step": current_step,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "exists": proj_path.exists(),
        })
    return result


def cleanup_missing_projects() -> int:
    """Remove projects whose directories no longer exist from recent list.

    Returns the number of removed entries.
    """
    settings = _read_settings()
    recents = settings.get("recent_projects", [])
    if not isinstance(recents, list):
        return 0
    original_count = len(recents)
    cleaned = [
        entry for entry in recents
        if isinstance(entry, dict) and Path(entry.get("path", "")).exists()
    ]
    settings["recent_projects"] = cleaned
    _write_settings(settings)
    return original_count - len(cleaned)


def _normalize_publish_connectors(raw: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for platform_id, item in raw.items():
        pid = str(platform_id or "").strip().lower()
        if not pid:
            continue
        if not isinstance(item, dict):
            continue
        row = {
            "kind": str(item.get("kind", "webhook") or "webhook").strip().lower() or "webhook",
            "endpoint": str(item.get("endpoint", "") or "").strip(),
            "method": str(item.get("method", "POST") or "POST").strip().upper() or "POST",
            "timeout_s": max(1.0, min(float(item.get("timeout_s", 25) or 25), 120.0)),
            "token": str(item.get("token", "") or "").strip(),
            "headers": item.get("headers", {}) if isinstance(item.get("headers"), dict) else {},
        }
        out[pid] = row
    return out


def _merge_publish_connectors_with_existing(
    existing: Dict[str, Dict[str, Any]],
    incoming: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    old = existing if isinstance(existing, dict) else {}
    new = incoming if isinstance(incoming, dict) else {}
    for pid, row in new.items():
        if not isinstance(row, dict):
            continue
        prev = old.get(pid, {}) if isinstance(old.get(pid), dict) else {}
        token = str(row.get("token", "") or "").strip()
        if token == _PUBLISH_SECRET_KEEP_SENTINEL:
            token = str(prev.get("token", "") or "").strip()

        headers_raw = row.get("headers", {}) if isinstance(row.get("headers"), dict) else {}
        prev_headers = prev.get("headers", {}) if isinstance(prev.get("headers"), dict) else {}
        headers: Dict[str, Any] = {}
        for hk, hv in headers_raw.items():
            key = str(hk or "").strip()
            if not key:
                continue
            value = str(hv or "").strip()
            if value == _PUBLISH_SECRET_KEEP_SENTINEL:
                value = str(prev_headers.get(key, "") or "").strip()
            headers[key] = value

        merged[pid] = {
            "kind": str(row.get("kind", "webhook") or "webhook").strip().lower() or "webhook",
            "endpoint": str(row.get("endpoint", "") or "").strip(),
            "method": str(row.get("method", "POST") or "POST").strip().upper() or "POST",
            "timeout_s": max(1.0, min(float(row.get("timeout_s", 25) or 25), 120.0)),
            "token": token,
            "headers": headers,
        }
    return merged


def _mask_publish_connectors(connectors: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for pid, item in (connectors or {}).items():
        if not isinstance(item, dict):
            continue
        headers_raw = item.get("headers", {}) if isinstance(item.get("headers"), dict) else {}
        headers_masked: Dict[str, Any] = {}
        for hk, hv in headers_raw.items():
            key = str(hk or "")
            val = str(hv or "")
            if key.lower() in {"authorization", "x-api-key", "x-auth-token"}:
                headers_masked[key] = _mask_secret(val)
            else:
                headers_masked[key] = val
        out[str(pid)] = {
            **item,
            "token": _mask_secret(item.get("token", "")),
            "headers": headers_masked,
        }
    return out


def _load_publish_settings() -> Dict[str, Any]:
    src = _read_settings().get("publish", {})
    if not isinstance(src, dict):
        src = {}
    connectors = _normalize_publish_connectors(src.get("connectors", {}))
    return {
        "connectors": connectors,
    }


def _save_publish_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    src = payload if isinstance(payload, dict) else {}
    settings = _read_settings()
    publish = settings.get("publish", {})
    if not isinstance(publish, dict):
        publish = {}
    if "connectors" in src:
        existing_connectors = _normalize_publish_connectors(publish.get("connectors", {}))
        incoming_connectors = _normalize_publish_connectors(src.get("connectors", {}))
        publish["connectors"] = _merge_publish_connectors_with_existing(existing_connectors, incoming_connectors)
    settings["publish"] = publish
    _write_settings(settings)
    return _load_publish_settings()


def _mask_secret(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


def _normalize_ai_provider(provider: Any) -> str:
    key = str(provider or "").strip().lower()
    if not key:
        return ""
    return _AI_PROVIDER_ALIASES.get(key, key)


def _recommended_ai_base_url(provider: Any, model: Any = "") -> str:
    provider_id = _normalize_ai_provider(provider)
    item = _AI_PROVIDER_CATALOG.get(provider_id, {}) if provider_id else {}
    if not isinstance(item, dict):
        return ""
    model_base_urls = item.get("model_base_urls", {})
    if isinstance(model_base_urls, dict):
        picked_model = str(model or "").strip().lower()
        if picked_model:
            for model_id, base_url in model_base_urls.items():
                if picked_model == str(model_id or "").strip().lower():
                    return str(base_url or "").strip()
    return str(item.get("default_base_url", "") or "").strip()


def _ai_catalog_payload() -> Dict[str, Any]:
    providers: List[Dict[str, Any]] = []
    for provider_id, item in _AI_PROVIDER_CATALOG.items():
        if not isinstance(item, dict):
            continue
        providers.append(
            {
                "provider_id": provider_id,
                "label": str(item.get("label", provider_id) or provider_id),
                "aliases": [str(x).strip() for x in item.get("aliases", []) if str(x).strip()],
                "default_base_url": str(item.get("default_base_url", "") or "").strip(),
                "models": [str(x).strip() for x in item.get("models", []) if str(x).strip()],
                "embedding_models": [str(x).strip() for x in item.get("embedding_models", []) if str(x).strip()],
            }
        )
    return {
        "providers": providers,
        "default_provider": "openai",
        "default_embedding_model": _DEFAULT_EMBEDDING_MODEL,
    }


def _ai_secret_ref_name(field_name: str) -> str:
    token = str(field_name or "").strip().lower()
    if not token:
        return ""
    return f"ai.{token}"


def _read_ai_secret_field(settings_ai: Dict[str, Any], field_name: str) -> str:
    if not isinstance(settings_ai, dict):
        return ""
    ref_key = f"{field_name}_ref"
    ref_name = str(settings_ai.get(ref_key, "") or "").strip()
    store_meta = _get_secret_store().info()
    if ref_name and bool(store_meta.available):
        try:
            from_store = _get_secret_store().get(ref_name)
        except Exception:
            from_store = ""
        if from_store:
            return str(from_store).strip()
    return str(settings_ai.get(field_name, "") or "").strip()


def _persist_ai_secret_field(settings_ai: Dict[str, Any], field_name: str, incoming_value: str, clear_flag: bool) -> None:
    if not isinstance(settings_ai, dict):
        return
    name = str(field_name or "").strip()
    if not name:
        return
    ref_key = f"{name}_ref"
    ref_name = str(settings_ai.get(ref_key, "") or _ai_secret_ref_name(name)).strip() or _ai_secret_ref_name(name)
    store_meta = _get_secret_store().info()

    if clear_flag:
        if ref_name and bool(store_meta.available):
            try:
                _get_secret_store().delete(ref_name)
            except Exception:
                pass
        settings_ai.pop(name, None)
        settings_ai.pop(ref_key, None)
        return

    value = str(incoming_value or "").strip()
    if value:
        if ref_name and bool(store_meta.available):
            try:
                stored = _get_secret_store().set(ref_name, value)
            except Exception:
                stored = False
            if stored:
                settings_ai[ref_key] = ref_name
                settings_ai.pop(name, None)
                return
        settings_ai[name] = value
        settings_ai.pop(ref_key, None)
        return

    # No new value passed: try to migrate existing legacy plaintext key into secret store.
    legacy_value = str(settings_ai.get(name, "") or "").strip()
    if legacy_value and ref_name and bool(store_meta.available):
        try:
            migrated = _get_secret_store().set(ref_name, legacy_value)
        except Exception:
            migrated = False
        if migrated:
            settings_ai[ref_key] = ref_name
            settings_ai.pop(name, None)


def _load_ai_settings() -> Dict:
    data = _read_settings().get("ai", {})
    if not isinstance(data, dict):
        data = {}
    provider = _normalize_ai_provider(data.get("provider", ""))
    return {
        "provider": provider or "openai",
        "ai_model": str(data.get("ai_model", "") or "").strip(),
        "embedding_model": str(data.get("embedding_model", "") or "").strip(),
        "ai_base_url": str(data.get("ai_base_url", "") or "").strip(),
        "openai_api_key": _read_ai_secret_field(data, "openai_api_key"),
        "anthropic_api_key": _read_ai_secret_field(data, "anthropic_api_key"),
    }


def _save_ai_settings(payload: Dict) -> Dict:
    settings = _read_settings()
    ai = settings.get("ai", {})
    if not isinstance(ai, dict):
        ai = {}

    provider = _normalize_ai_provider(payload.get("provider", ""))
    model = str(payload.get("ai_model", "") or "").strip()
    embedding_model = str(payload.get("embedding_model", "") or "").strip()
    base_url = str(payload.get("ai_base_url", "") or "").strip()
    if provider:
        ai["provider"] = provider
    elif "provider" in payload:
        ai.pop("provider", None)
    if model:
        ai["ai_model"] = model
    elif "ai_model" in payload:
        ai.pop("ai_model", None)
    if embedding_model:
        ai["embedding_model"] = embedding_model
    elif "embedding_model" in payload:
        ai.pop("embedding_model", None)
    if base_url:
        ai["ai_base_url"] = base_url
    elif "ai_base_url" in payload:
        ai.pop("ai_base_url", None)

    openai_api_key = str(payload.get("openai_api_key", "") or "").strip()
    anthropic_api_key = str(payload.get("anthropic_api_key", "") or "").strip()
    clear_openai = bool(payload.get("clear_openai_api_key", False))
    clear_anthropic = bool(payload.get("clear_anthropic_api_key", False))
    _persist_ai_secret_field(ai, "openai_api_key", openai_api_key, clear_openai)
    _persist_ai_secret_field(ai, "anthropic_api_key", anthropic_api_key, clear_anthropic)

    settings["ai"] = ai
    _write_settings(settings)
    return _load_ai_settings()


def _apply_ai_env(ai: Dict):
    provider = _normalize_ai_provider(ai.get("provider", ""))
    openai_api_key = str(ai.get("openai_api_key", "") or "").strip()
    anthropic_api_key = str(ai.get("anthropic_api_key", "") or "").strip()
    ai_base_url = str(ai.get("ai_base_url", "") or "").strip()
    ai_model = str(ai.get("ai_model", "") or "").strip()
    embedding_model = str(ai.get("embedding_model", "") or "").strip()

    if openai_api_key:
        os.environ["OPENAI_API_KEY"] = openai_api_key
    else:
        os.environ.pop("OPENAI_API_KEY", None)
    if anthropic_api_key:
        os.environ["ANTHROPIC_API_KEY"] = anthropic_api_key
    else:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    openai_compatible_provider = provider in {"", "openai", "moonshot", "qwen", "gemini", "maxmini"}
    if ai_base_url and openai_compatible_provider:
        os.environ["OPENAI_BASE_URL"] = ai_base_url
    else:
        os.environ.pop("OPENAI_BASE_URL", None)
    if ai_model and openai_compatible_provider:
        os.environ["OPENAI_MODEL"] = ai_model
    else:
        os.environ.pop("OPENAI_MODEL", None)
    if embedding_model:
        os.environ["OPENAI_EMBEDDING_MODEL"] = embedding_model
    else:
        os.environ.pop("OPENAI_EMBEDDING_MODEL", None)


def _public_ai_settings(ai: Dict) -> Dict:
    provider = _normalize_ai_provider(ai.get("provider", "")) or "openai"
    model = str(ai.get("ai_model", "") or "").strip()
    base_url = str(ai.get("ai_base_url", "") or "").strip()
    embedding_model = str(ai.get("embedding_model", "") or "").strip()
    secret_status = _get_secret_store().public_status()
    return {
        "provider": provider,
        "ai_model": model,
        "embedding_model": embedding_model,
        "embedding_model_resolved": embedding_model or _DEFAULT_EMBEDDING_MODEL,
        "ai_base_url": base_url,
        "recommended_base_url": _recommended_ai_base_url(provider, model),
        "openai_api_key_set": bool(ai.get("openai_api_key")),
        "anthropic_api_key_set": bool(ai.get("anthropic_api_key")),
        "openai_api_key_masked": _mask_secret(ai.get("openai_api_key", "")),
        "anthropic_api_key_masked": _mask_secret(ai.get("anthropic_api_key", "")),
        "secret_storage": secret_status,
        "catalog": _ai_catalog_payload(),
    }


def _default_project_config(extra: Optional[Dict] = None) -> Dict:
    from modules.app_api.server import RENDER_DEFAULTS
    ai = _load_ai_settings()
    config = {
        "use_semantic_index": False,
        "ai_provider": ai.get("provider") or None,
        "ai_base_url": ai.get("ai_base_url") or None,
        "ai_model": ai.get("ai_model") or None,
        "render": dict(RENDER_DEFAULTS),
    }
    if extra:
        config.update(extra)
    return config


def _project_data_path(filename: str) -> Optional[Path]:
    # Always read _project_dir from server module at call-time so tests that
    # mutate server._project_dir directly are respected.
    import modules.app_api.server as _srv
    pd = getattr(_srv, "_project_dir", None) or _project_dir
    if pd is None:
        return None
    return pd / "data" / filename


def _read_project_json(filename: str, fallback=None):
    p = _project_data_path(filename)
    if p is None or not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}
