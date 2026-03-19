"""Settings normalization and masking helpers.

Extracted from server.py (Roadmap L1) — pure functions only, no IO.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants (copied from server.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def normalize_production_view(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    if key in {"workflow", "graph"}:
        return "workflow"
    return "hub"


def normalize_font_scale(raw: Any) -> float:
    try:
        value = float(raw)
    except Exception:
        value = 1.0
    return round(max(0.85, min(value, 1.45)), 2)


def mask_secret(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}{'*' * (len(s) - 8)}{s[-4:]}"


def normalize_publish_connectors(raw: Any) -> Dict[str, Dict[str, Any]]:
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


def merge_publish_connectors_with_existing(
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


def mask_publish_connectors(connectors: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
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
                headers_masked[key] = mask_secret(val)
            else:
                headers_masked[key] = val
        out[str(pid)] = {
            **item,
            "token": mask_secret(item.get("token", "")),
            "headers": headers_masked,
        }
    return out


def normalize_ai_provider(provider: Any) -> str:
    key = str(provider or "").strip().lower()
    if not key:
        return ""
    return _AI_PROVIDER_ALIASES.get(key, key)


def recommended_ai_base_url(provider: Any, model: Any = "") -> str:
    provider_id = normalize_ai_provider(provider)
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


def ai_catalog_payload() -> Dict[str, Any]:
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


def ai_secret_ref_name(field_name: str) -> str:
    token = str(field_name or "").strip().lower()
    if not token:
        return ""
    return f"ai.{token}"
