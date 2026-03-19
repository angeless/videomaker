"""Agent governance, cost model, and skill normalization helpers.

Extracted from server.py (Roadmap L1) — pure functions only, no IO.
"""
from __future__ import annotations
from copy import deepcopy
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AGENT_GOVERNANCE_DEFAULT: Dict[str, Any] = {
    "default_limits": {
        "max_steps": 40,
        "max_failures": 12,
        "max_duration_seconds": 1800,
        "max_parallel": 4,
    },
    "actor_limits": {},
    "capability_limits": {},
    "actor_capability_limits": {},
    "blocked_skills": [],
    "blocked_capabilities": [],
    "blocked_skills_by_actor": {},
    "blocked_capabilities_by_actor": {},
}

AGENT_GOVERNANCE_USAGE_DEFAULT: Dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "actors": {},
}

AGENT_USAGE_RECENT_RUNS_MAX = 16

AGENT_TASK_HISTORY_MAX = 600

AGENT_COST_MODEL_DEFAULT: Dict[str, Any] = {
    "default_rates": {
        "prompt_usd_per_1k_tokens": 0.002,
        "completion_usd_per_1k_tokens": 0.006,
        "compute_usd_per_second": 0.00005,
    },
    "providers": {},
}


# ---------------------------------------------------------------------------
# Private helpers (not part of public API, used by extracted functions)
# ---------------------------------------------------------------------------

def _coerce_bool(value, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


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


def _normalize_agent_template_id(value: str) -> str:
    return _normalize_export_template_id(value)


# ---------------------------------------------------------------------------
# Pure normalisation / computation functions
# ---------------------------------------------------------------------------

def normalize_skill_retry_policy(policy_raw: Any) -> Dict[str, Any]:
    raw = policy_raw if isinstance(policy_raw, dict) else {}
    try:
        max_retries = int(raw.get("max_retries", 0) or 0)
    except Exception:
        max_retries = 0
    try:
        backoff_ms = int(raw.get("backoff_ms", 0) or 0)
    except Exception:
        backoff_ms = 0
    retry_on_http_raw = raw.get("retry_on_http", [429, 500, 502, 503, 504])
    retry_on_http: List[int] = []
    if isinstance(retry_on_http_raw, list):
        for item in retry_on_http_raw:
            try:
                code = int(item)
            except Exception:
                continue
            if 100 <= code <= 599:
                retry_on_http.append(code)
    if not retry_on_http:
        retry_on_http = [429, 500, 502, 503, 504]
    return {
        "max_retries": max(0, min(max_retries, 3)),
        "backoff_ms": max(0, min(backoff_ms, 5000)),
        "retry_on_http": sorted(set(retry_on_http)),
    }


def normalize_skill_timeout_seconds(value: Any, default: float = 120.0) -> float:
    try:
        timeout_seconds = float(value if value is not None else default)
    except Exception:
        timeout_seconds = float(default)
    return max(1.0, min(timeout_seconds, 3600.0))


def normalize_skill_budget_limit(raw: Any) -> Dict[str, int]:
    src = raw if isinstance(raw, dict) else {}
    try:
        max_steps = int(src.get("max_steps", 0) or 0)
    except Exception:
        max_steps = 0
    try:
        max_failures = int(src.get("max_failures", 0) or 0)
    except Exception:
        max_failures = 0
    try:
        max_duration_seconds = int(src.get("max_duration_seconds", 0) or 0)
    except Exception:
        max_duration_seconds = 0
    return {
        "max_steps": max(0, min(max_steps, 200)),
        "max_failures": max(0, min(max_failures, 200)),
        "max_duration_seconds": max(0, min(max_duration_seconds, 7200)),
    }


def normalize_governance_limit_item(raw: Any) -> Dict[str, int]:
    src = raw if isinstance(raw, dict) else {}
    base = normalize_skill_budget_limit(src)
    try:
        max_parallel = int(src.get("max_parallel", 0) or 0)
    except Exception:
        max_parallel = 0
    base["max_parallel"] = max(0, min(max_parallel, 8))
    return base


def normalize_governance_string_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return list(dict.fromkeys(out))


def normalize_agent_governance_policy(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    default_raw = deepcopy(AGENT_GOVERNANCE_DEFAULT)
    merged: Dict[str, Any] = deepcopy(default_raw)
    for key in (
        "default_limits",
        "actor_limits",
        "capability_limits",
        "actor_capability_limits",
        "blocked_skills",
        "blocked_capabilities",
        "blocked_skills_by_actor",
        "blocked_capabilities_by_actor",
    ):
        if key in src:
            merged[key] = src.get(key)

    out: Dict[str, Any] = {
        "default_limits": normalize_governance_limit_item(merged.get("default_limits", {})),
        "actor_limits": {},
        "capability_limits": {},
        "actor_capability_limits": {},
        "blocked_skills": normalize_governance_string_list(merged.get("blocked_skills", [])),
        "blocked_capabilities": normalize_governance_string_list(merged.get("blocked_capabilities", [])),
        "blocked_skills_by_actor": {},
        "blocked_capabilities_by_actor": {},
    }

    actor_limits_raw = merged.get("actor_limits", {})
    if isinstance(actor_limits_raw, dict):
        for actor_key, item in actor_limits_raw.items():
            actor_id = str(actor_key or "").strip()
            if actor_id:
                out["actor_limits"][actor_id] = normalize_governance_limit_item(item)

    capability_limits_raw = merged.get("capability_limits", {})
    if isinstance(capability_limits_raw, dict):
        for capability_key, item in capability_limits_raw.items():
            capability_id = str(capability_key or "").strip()
            if capability_id:
                out["capability_limits"][capability_id] = normalize_governance_limit_item(item)

    actor_cap_raw = merged.get("actor_capability_limits", {})
    if isinstance(actor_cap_raw, dict):
        for actor_key, cap_map in actor_cap_raw.items():
            actor_id = str(actor_key or "").strip()
            if not actor_id or not isinstance(cap_map, dict):
                continue
            bucket: Dict[str, Dict[str, int]] = {}
            for capability_key, item in cap_map.items():
                capability_id = str(capability_key or "").strip()
                if not capability_id:
                    continue
                bucket[capability_id] = normalize_governance_limit_item(item)
            if bucket:
                out["actor_capability_limits"][actor_id] = bucket

    for field in ("blocked_skills_by_actor", "blocked_capabilities_by_actor"):
        raw_map = merged.get(field, {})
        if isinstance(raw_map, dict):
            bucket: Dict[str, List[str]] = {}
            for actor_key, values in raw_map.items():
                actor_id = str(actor_key or "").strip()
                if not actor_id:
                    continue
                bucket[actor_id] = normalize_governance_string_list(values)
            out[field] = bucket
    return out


def normalize_cost_rate_item(raw: Any, fallback: Optional[Dict[str, float]] = None) -> Dict[str, float]:
    base = {
        "prompt_usd_per_1k_tokens": 0.0,
        "completion_usd_per_1k_tokens": 0.0,
        "compute_usd_per_second": 0.0,
    }
    if isinstance(fallback, dict):
        for key in base.keys():
            try:
                base[key] = max(float(fallback.get(key, base[key]) or 0.0), 0.0)
            except Exception:
                base[key] = max(float(base[key]), 0.0)
    src = raw if isinstance(raw, dict) else {}
    for key in base.keys():
        if key not in src:
            continue
        try:
            base[key] = max(float(src.get(key, base[key]) or 0.0), 0.0)
        except Exception:
            continue
    return base


def normalize_agent_cost_model_config(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    out = deepcopy(AGENT_COST_MODEL_DEFAULT)
    fallback_rates = normalize_cost_rate_item(out.get("default_rates", {}))

    default_rates_raw = src.get("default_rates", src)
    out["default_rates"] = normalize_cost_rate_item(default_rates_raw, fallback=fallback_rates)
    out["providers"] = {}

    providers_raw = src.get("providers", {})
    if not isinstance(providers_raw, dict):
        return out

    for provider_key, provider_item_raw in providers_raw.items():
        provider_id = str(provider_key or "").strip().lower()
        if not provider_id:
            continue
        provider_item = provider_item_raw if isinstance(provider_item_raw, dict) else {}
        provider_default = normalize_cost_rate_item(
            provider_item.get("default_rates", provider_item),
            fallback=out["default_rates"],
        )
        models_out: Dict[str, Dict[str, float]] = {}
        models_raw = provider_item.get("models", {})
        if isinstance(models_raw, dict):
            for model_key, model_rate_raw in models_raw.items():
                model_id = str(model_key or "").strip()
                if not model_id:
                    continue
                models_out[model_id] = normalize_cost_rate_item(model_rate_raw, fallback=provider_default)
        out["providers"][provider_id] = {
            "default_rates": provider_default,
            "models": models_out,
        }
    return out


def extract_pricing_hint_from_response(payload: Dict[str, Any]) -> Dict[str, str]:
    data = payload if isinstance(payload, dict) else {}

    def _pick_text(root: Dict[str, Any], keys: List[str]) -> str:
        for key in keys:
            val = root.get(key)
            if isinstance(val, str):
                t = val.strip()
                if t:
                    return t
        return ""

    provider_keys = ["provider", "ai_provider", "llm_provider", "model_provider"]
    model_keys = ["model", "ai_model", "model_name", "llm_model"]
    roots: List[Dict[str, Any]] = [data]
    for key in ("response", "meta", "metadata", "llm", "model_info"):
        item = data.get(key)
        if isinstance(item, dict):
            roots.append(item)
            for sub_key in ("meta", "metadata", "llm", "model_info"):
                sub_item = item.get(sub_key)
                if isinstance(sub_item, dict):
                    roots.append(sub_item)

    provider = ""
    model = ""
    for root in roots:
        if not provider:
            provider = _pick_text(root, provider_keys)
        if not model:
            model = _pick_text(root, model_keys)
        if provider and model:
            break
    return {"provider": provider.lower(), "model": model}


def resolve_cost_rates(
    *,
    provider: str,
    model: str,
    cost_model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = normalize_agent_cost_model_config(cost_model) if isinstance(cost_model, dict) else normalize_agent_cost_model_config({})
    default_rates = normalize_cost_rate_item(cfg.get("default_rates", {}))
    providers = cfg.get("providers", {})
    if not isinstance(providers, dict):
        providers = {}

    provider_norm = str(provider or "").strip().lower()
    model_req = str(model or "").strip()
    selected_rates = deepcopy(default_rates)
    rate_source = "default"
    resolved_model = model_req
    if provider_norm:
        provider_item = providers.get(provider_norm)
        if isinstance(provider_item, dict):
            provider_default = normalize_cost_rate_item(provider_item.get("default_rates", {}), fallback=selected_rates)
            selected_rates = provider_default
            rate_source = f"provider:{provider_norm}:default"
            models = provider_item.get("models", {})
            if isinstance(models, dict) and model_req:
                if model_req in models and isinstance(models.get(model_req), dict):
                    selected_rates = normalize_cost_rate_item(models.get(model_req), fallback=selected_rates)
                    rate_source = f"provider:{provider_norm}:model:{model_req}"
                else:
                    lower_map = {
                        str(k).strip().lower(): str(k).strip()
                        for k in models.keys()
                        if str(k).strip()
                    }
                    match_key = lower_map.get(model_req.lower())
                    if match_key and isinstance(models.get(match_key), dict):
                        selected_rates = normalize_cost_rate_item(models.get(match_key), fallback=selected_rates)
                        resolved_model = match_key
                        rate_source = f"provider:{provider_norm}:model:{match_key}"
    return {
        "provider": provider_norm,
        "model": resolved_model,
        "rate_source": rate_source,
        "rates": selected_rates,
    }


def extract_usage_tokens_from_response(payload: Dict[str, Any]) -> Dict[str, int]:
    data = payload if isinstance(payload, dict) else {}

    def _pick_usage_obj(root: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("usage", "token_usage", "llm_usage"):
            val = root.get(key)
            if isinstance(val, dict):
                return val
        return {}

    usage = _pick_usage_obj(data)
    if not usage:
        response_data = data.get("response")
        if isinstance(response_data, dict):
            usage = _pick_usage_obj(response_data)

    def _to_int(value) -> int:
        try:
            parsed = int(value)
        except Exception:
            parsed = 0
        return max(parsed, 0)

    prompt_tokens = _to_int(usage.get("prompt_tokens", usage.get("input_tokens", usage.get("prompt_tokens_total", 0))))
    completion_tokens = _to_int(usage.get("completion_tokens", usage.get("output_tokens", usage.get("completion_tokens_total", 0))))
    total_tokens_raw = usage.get("total_tokens", usage.get("total", 0))
    total_tokens = _to_int(total_tokens_raw)
    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def estimate_step_cost_metrics(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    duration_seconds: float,
    provider: str = "",
    model: str = "",
    cost_model: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    p = max(int(prompt_tokens or 0), 0)
    c = max(int(completion_tokens or 0), 0)
    d = max(float(duration_seconds or 0.0), 0.0)
    resolved = resolve_cost_rates(provider=provider, model=model, cost_model=cost_model)
    rates = resolved.get("rates", {}) if isinstance(resolved.get("rates"), dict) else {}
    prompt_rate = float(rates.get("prompt_usd_per_1k_tokens", 0.0) or 0.0)
    completion_rate = float(rates.get("completion_usd_per_1k_tokens", 0.0) or 0.0)
    compute_rate = float(rates.get("compute_usd_per_second", 0.0) or 0.0)
    prompt_cost = (p / 1000.0) * prompt_rate
    completion_cost = (c / 1000.0) * completion_rate
    compute_cost = d * compute_rate
    total_cost = prompt_cost + completion_cost + compute_cost
    return {
        "prompt_cost_usd": round(prompt_cost, 8),
        "completion_cost_usd": round(completion_cost, 8),
        "compute_cost_usd": round(compute_cost, 8),
        "total_cost_usd": round(total_cost, 8),
        "compute_seconds": round(d, 4),
        "rate_source": str(resolved.get("rate_source", "default") or "default"),
        "provider": str(resolved.get("provider", "") or ""),
        "model": str(resolved.get("model", "") or ""),
        "rates": {
            "prompt_usd_per_1k_tokens": round(prompt_rate, 8),
            "completion_usd_per_1k_tokens": round(completion_rate, 8),
            "compute_usd_per_second": round(compute_rate, 8),
        },
    }


def normalize_usage_bucket(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}

    def _normalize_recent_run_item(item_raw: Any) -> Optional[Dict[str, Any]]:
        item = item_raw if isinstance(item_raw, dict) else {}
        run_at = str(item.get("run_at", "") or "").strip()
        status_raw = str(item.get("status", "") or "").strip().lower()
        status = status_raw if status_raw in {"ok", "partial", "failed"} else "partial"

        def _to_int(v: Any) -> int:
            try:
                parsed = int(v)
            except Exception:
                parsed = 0
            return max(parsed, 0)

        def _to_float(v: Any) -> float:
            try:
                parsed = float(v)
            except Exception:
                parsed = 0.0
            return max(parsed, 0.0)

        steps_total = _to_int(item.get("steps_total", 0))
        steps_success = _to_int(item.get("steps_success", 0))
        steps_failed = _to_int(item.get("steps_failed", 0))
        steps_skipped = _to_int(item.get("steps_skipped", 0))
        prompt_tokens = _to_int(item.get("prompt_tokens", 0))
        completion_tokens = _to_int(item.get("completion_tokens", 0))
        total_tokens = _to_int(item.get("total_tokens", prompt_tokens + completion_tokens))
        failure_rate_raw = _to_float(item.get("failure_rate", 0.0))
        failure_rate = min(max(failure_rate_raw, 0.0), 1.0)
        if steps_total > 0:
            failure_rate = min(max(float(steps_failed) / float(max(steps_total, 1)), 0.0), 1.0)

        if not run_at and steps_total <= 0 and total_tokens <= 0 and _to_float(item.get("estimated_cost_usd", 0.0)) <= 0.0:
            return None
        return {
            "run_at": run_at,
            "status": status,
            "steps_total": steps_total,
            "steps_success": steps_success,
            "steps_failed": steps_failed,
            "steps_skipped": steps_skipped,
            "failure_rate": round(failure_rate, 4),
            "duration_seconds": round(_to_float(item.get("duration_seconds", 0.0)), 4),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(_to_float(item.get("estimated_cost_usd", 0.0)), 8),
        }

    recent_runs_raw = src.get("recent_runs", [])
    recent_runs: List[Dict[str, Any]] = []
    if isinstance(recent_runs_raw, list):
        for item_raw in recent_runs_raw:
            normalized = _normalize_recent_run_item(item_raw)
            if isinstance(normalized, dict):
                recent_runs.append(normalized)
            if len(recent_runs) >= AGENT_USAGE_RECENT_RUNS_MAX:
                recent_runs = recent_runs[-AGENT_USAGE_RECENT_RUNS_MAX:]

    out = {
        "run_count": int(src.get("run_count", 0) or 0),
        "step_count": int(src.get("step_count", 0) or 0),
        "success_step_count": int(src.get("success_step_count", 0) or 0),
        "failed_step_count": int(src.get("failed_step_count", 0) or 0),
        "skipped_step_count": int(src.get("skipped_step_count", 0) or 0),
        "total_duration_seconds": float(src.get("total_duration_seconds", 0.0) or 0.0),
        "last_duration_seconds": float(src.get("last_duration_seconds", 0.0) or 0.0),
        "avg_duration_seconds": float(src.get("avg_duration_seconds", 0.0) or 0.0),
        "total_prompt_tokens": int(src.get("total_prompt_tokens", 0) or 0),
        "total_completion_tokens": int(src.get("total_completion_tokens", 0) or 0),
        "total_tokens": int(src.get("total_tokens", 0) or 0),
        "total_estimated_cost_usd": float(src.get("total_estimated_cost_usd", 0.0) or 0.0),
        "avg_estimated_cost_usd": float(src.get("avg_estimated_cost_usd", 0.0) or 0.0),
        "last_estimated_cost_usd": float(src.get("last_estimated_cost_usd", 0.0) or 0.0),
        "last_run_at": str(src.get("last_run_at", "") or ""),
        "recent_runs": recent_runs,
        "suggested_limits": normalize_governance_limit_item(src.get("suggested_limits", {})),
    }
    out["run_count"] = max(out["run_count"], 0)
    out["step_count"] = max(out["step_count"], 0)
    out["success_step_count"] = max(out["success_step_count"], 0)
    out["failed_step_count"] = max(out["failed_step_count"], 0)
    out["skipped_step_count"] = max(out["skipped_step_count"], 0)
    out["total_duration_seconds"] = max(out["total_duration_seconds"], 0.0)
    out["last_duration_seconds"] = max(out["last_duration_seconds"], 0.0)
    out["avg_duration_seconds"] = max(out["avg_duration_seconds"], 0.0)
    out["total_prompt_tokens"] = max(out["total_prompt_tokens"], 0)
    out["total_completion_tokens"] = max(out["total_completion_tokens"], 0)
    out["total_tokens"] = max(out["total_tokens"], 0)
    out["total_estimated_cost_usd"] = max(out["total_estimated_cost_usd"], 0.0)
    out["avg_estimated_cost_usd"] = max(out["avg_estimated_cost_usd"], 0.0)
    out["last_estimated_cost_usd"] = max(out["last_estimated_cost_usd"], 0.0)
    return out


def compute_usage_suggested_limits(bucket: Dict[str, Any]) -> Dict[str, int]:
    run_count = int(bucket.get("run_count", 0) or 0)
    step_count = int(bucket.get("step_count", 0) or 0)
    failed_steps = int(bucket.get("failed_step_count", 0) or 0)
    total_duration = float(bucket.get("total_duration_seconds", 0.0) or 0.0)
    total_cost = float(bucket.get("total_estimated_cost_usd", 0.0) or 0.0)
    total_tokens = int(bucket.get("total_tokens", 0) or 0)
    if run_count <= 0 or step_count <= 0:
        return {"max_steps": 0, "max_failures": 0, "max_duration_seconds": 0, "max_parallel": 0}

    avg_steps = step_count / max(run_count, 1)
    avg_failed_per_run = failed_steps / max(run_count, 1)
    avg_duration = total_duration / max(run_count, 1)
    avg_cost = total_cost / max(run_count, 1)
    avg_tokens = total_tokens / max(run_count, 1)
    failure_rate = failed_steps / max(step_count, 1)

    suggested_max_steps = max(2, min(int(max(avg_steps * 2.0, 2.0)), 200))
    suggested_max_failures = max(1, min(int(max(avg_failed_per_run * 2.0 + 1.0, 1.0)), 200))
    suggested_max_duration = max(30, min(int(max(avg_duration * 2.0, 30.0)), 7200))
    if failure_rate >= 0.35:
        suggested_max_parallel = 1
    elif failure_rate >= 0.20:
        suggested_max_parallel = 2
    else:
        suggested_max_parallel = 4
    if avg_cost >= 0.20 or avg_tokens >= 120000:
        suggested_max_parallel = min(suggested_max_parallel, 1)
        suggested_max_steps = max(2, min(suggested_max_steps, int(max(avg_steps * 1.2, 2))))
    elif avg_cost >= 0.08 or avg_tokens >= 50000:
        suggested_max_parallel = min(suggested_max_parallel, 2)
        suggested_max_steps = max(2, min(suggested_max_steps, int(max(avg_steps * 1.5, 2))))

    recent_runs_raw = bucket.get("recent_runs", [])
    recent_runs: List[Dict[str, Any]] = recent_runs_raw if isinstance(recent_runs_raw, list) else []
    if len(recent_runs) >= 3:
        window = recent_runs[-min(len(recent_runs), 8):]
        total_window = max(len(window), 1)

        recent_failure_rate = sum(float(x.get("failure_rate", 0.0) or 0.0) for x in window) / float(total_window)
        recent_avg_cost = sum(float(x.get("estimated_cost_usd", 0.0) or 0.0) for x in window) / float(total_window)
        recent_avg_duration = sum(float(x.get("duration_seconds", 0.0) or 0.0) for x in window) / float(total_window)
        recent_avg_tokens = sum(int(x.get("total_tokens", 0) or 0) for x in window) / float(total_window)

        success_streak = 0
        for item in reversed(recent_runs):
            if str(item.get("status", "")).lower() == "ok":
                success_streak += 1
            else:
                break

        # High pressure runs should tighten quickly to reduce retries/cost.
        high_pressure = (
            recent_failure_rate >= 0.30
            or recent_avg_cost >= 0.12
            or recent_avg_tokens >= 80000
            or recent_avg_duration >= 300.0
        )
        severe_pressure = (
            recent_failure_rate >= 0.45
            or recent_avg_cost >= 0.20
            or recent_avg_tokens >= 120000
            or recent_avg_duration >= 600.0
        )
        stable_window = (
            recent_failure_rate <= 0.05
            and recent_avg_cost <= 0.03
            and recent_avg_tokens <= 25000
            and recent_avg_duration <= 120.0
        )

        if high_pressure:
            suggested_max_parallel = min(suggested_max_parallel, 1 if severe_pressure else 2)
            suggested_max_steps = max(2, min(suggested_max_steps, int(max(avg_steps * (1.1 if severe_pressure else 1.3), 2))))
            suggested_max_duration = max(30, min(suggested_max_duration, int(max(avg_duration * 1.4, 30.0))))
        elif stable_window and success_streak >= 3:
            # Stable successful window can cautiously loosen dynamic suggestions.
            suggested_max_parallel = min(6, suggested_max_parallel + 1)
            suggested_max_steps = min(200, max(suggested_max_steps, int(max(avg_steps * 2.5, 3.0))))
            suggested_max_failures = min(200, max(suggested_max_failures, int(max(avg_failed_per_run * 2.5 + 1.0, 1.0))))
            suggested_max_duration = min(7200, max(suggested_max_duration, int(max(avg_duration * 2.2, 45.0))))

    return {
        "max_steps": suggested_max_steps,
        "max_failures": suggested_max_failures,
        "max_duration_seconds": suggested_max_duration,
        "max_parallel": suggested_max_parallel,
    }


def update_usage_bucket(
    bucket_raw: Any,
    *,
    steps_total: int,
    steps_success: int,
    steps_failed: int,
    steps_skipped: int,
    duration_seconds: float,
    prompt_tokens: int,
    completion_tokens: int,
    estimated_cost_usd: float,
    now_iso: str,
) -> Dict[str, Any]:
    bucket = normalize_usage_bucket(bucket_raw)
    steps_total_i = max(int(steps_total), 0)
    steps_success_i = max(int(steps_success), 0)
    steps_failed_i = max(int(steps_failed), 0)
    steps_skipped_i = max(int(steps_skipped), 0)
    duration_f = max(float(duration_seconds), 0.0)
    prompt_tokens_i = max(int(prompt_tokens), 0)
    completion_tokens_i = max(int(completion_tokens), 0)
    estimated_cost_f = max(float(estimated_cost_usd), 0.0)
    total_tokens_i = prompt_tokens_i + completion_tokens_i
    failure_rate = float(steps_failed_i) / float(max(steps_total_i, 1)) if steps_total_i > 0 else 0.0
    if steps_failed_i <= 0:
        run_status = "ok"
    elif steps_success_i <= 0:
        run_status = "failed"
    else:
        run_status = "partial"

    bucket["run_count"] = int(bucket.get("run_count", 0) or 0) + 1
    bucket["step_count"] = int(bucket.get("step_count", 0) or 0) + steps_total_i
    bucket["success_step_count"] = int(bucket.get("success_step_count", 0) or 0) + steps_success_i
    bucket["failed_step_count"] = int(bucket.get("failed_step_count", 0) or 0) + steps_failed_i
    bucket["skipped_step_count"] = int(bucket.get("skipped_step_count", 0) or 0) + steps_skipped_i
    bucket["total_duration_seconds"] = float(bucket.get("total_duration_seconds", 0.0) or 0.0) + duration_f
    bucket["last_duration_seconds"] = duration_f
    bucket["avg_duration_seconds"] = float(bucket["total_duration_seconds"]) / max(int(bucket["run_count"]), 1)
    bucket["total_prompt_tokens"] = int(bucket.get("total_prompt_tokens", 0) or 0) + prompt_tokens_i
    bucket["total_completion_tokens"] = int(bucket.get("total_completion_tokens", 0) or 0) + completion_tokens_i
    bucket["total_tokens"] = int(bucket.get("total_tokens", 0) or 0) + total_tokens_i
    bucket["total_estimated_cost_usd"] = float(bucket.get("total_estimated_cost_usd", 0.0) or 0.0) + estimated_cost_f
    bucket["last_estimated_cost_usd"] = estimated_cost_f
    bucket["avg_estimated_cost_usd"] = float(bucket["total_estimated_cost_usd"]) / max(int(bucket["run_count"]), 1)
    bucket["last_run_at"] = now_iso
    recent_runs_raw = bucket.get("recent_runs", [])
    recent_runs = list(recent_runs_raw) if isinstance(recent_runs_raw, list) else []
    recent_runs.append({
        "run_at": now_iso,
        "status": run_status,
        "steps_total": steps_total_i,
        "steps_success": steps_success_i,
        "steps_failed": steps_failed_i,
        "steps_skipped": steps_skipped_i,
        "failure_rate": round(min(max(failure_rate, 0.0), 1.0), 4),
        "duration_seconds": round(duration_f, 4),
        "prompt_tokens": prompt_tokens_i,
        "completion_tokens": completion_tokens_i,
        "total_tokens": total_tokens_i,
        "estimated_cost_usd": round(estimated_cost_f, 8),
    })
    if len(recent_runs) > AGENT_USAGE_RECENT_RUNS_MAX:
        recent_runs = recent_runs[-AGENT_USAGE_RECENT_RUNS_MAX:]
    bucket["recent_runs"] = recent_runs
    bucket["suggested_limits"] = compute_usage_suggested_limits(bucket)
    return bucket


def extract_dynamic_limits_from_usage(
    *,
    actor_id: str,
    capability_ids: List[str],
    usage: Dict[str, Any],
) -> Dict[str, Any]:
    """Extract dynamic suggested limits from a pre-loaded usage dict.

    The caller is responsible for reading usage data (IO) and passing it in
    via the *usage* parameter.
    """
    actor = str(actor_id or "").strip()
    if not actor:
        return {"summary": None, "by_capability": {}}
    actors = usage.get("actors", {})
    if not isinstance(actors, dict):
        return {"summary": None, "by_capability": {}}
    actor_entry = actors.get(actor, {})
    if not isinstance(actor_entry, dict):
        return {"summary": None, "by_capability": {}}
    summary_bucket = actor_entry.get("summary", {})
    summary_limits = normalize_governance_limit_item(
        summary_bucket.get("suggested_limits", {}) if isinstance(summary_bucket, dict) else {}
    )
    cap_map = actor_entry.get("capabilities", {})
    out_caps: Dict[str, Dict[str, int]] = {}
    if isinstance(cap_map, dict):
        for capability_id in capability_ids:
            b = cap_map.get(capability_id, {})
            if not isinstance(b, dict):
                continue
            out_caps[capability_id] = normalize_governance_limit_item(b.get("suggested_limits", {}))
    return {"summary": summary_limits, "by_capability": out_caps}


def pick_actor_rule(mapping: Any, actor_id: str):
    if not isinstance(mapping, dict):
        return None
    actor = str(actor_id or "").strip()
    if not actor:
        return None
    if actor in mapping:
        return mapping.get(actor)
    lower = actor.lower()
    if lower in mapping:
        return mapping.get(lower)
    return None


def tighten_governance_limit(base: Dict[str, int], incoming: Dict[str, int], *, source: str, trace: Dict[str, str]):
    if not isinstance(base, dict) or not isinstance(incoming, dict):
        return
    for key in ("max_steps", "max_failures", "max_duration_seconds", "max_parallel"):
        val = int(incoming.get(key, 0) or 0)
        if val <= 0:
            continue
        cur = int(base.get(key, 0) or 0)
        if cur <= 0 or val < cur:
            base[key] = val
            trace[key] = source


def resolve_agent_governance_for_skill_flow(
    *,
    actor_id: str,
    steps: List[Dict[str, Any]],
    policy: Dict[str, Any],
    usage: Dict[str, Any],
) -> Dict[str, Any]:
    """Resolve effective governance limits for a skill flow.

    The caller must supply *policy* (normalised governance policy) and *usage*
    (raw governance-usage dict) so that this function remains IO-free.
    """
    effective = normalize_governance_limit_item(policy.get("default_limits", {}))
    trace = {k: "default_limits" for k in effective.keys()}
    actor_rule = pick_actor_rule(policy.get("actor_limits", {}), actor_id)
    if isinstance(actor_rule, dict):
        tighten_governance_limit(effective, actor_rule, source=f"actor:{actor_id}", trace=trace)

    capability_ids = sorted({
        str(x.get("capability_id", "") or "").strip()
        for x in (steps or [])
        if isinstance(x, dict) and str(x.get("capability_id", "") or "").strip()
    })
    for capability_id in capability_ids:
        cap_rule = policy.get("capability_limits", {}).get(capability_id) if isinstance(policy.get("capability_limits", {}), dict) else None
        if isinstance(cap_rule, dict):
            tighten_governance_limit(effective, cap_rule, source=f"capability:{capability_id}", trace=trace)

        actor_cap_map = pick_actor_rule(policy.get("actor_capability_limits", {}), actor_id)
        actor_cap_rule = actor_cap_map.get(capability_id) if isinstance(actor_cap_map, dict) else None
        if isinstance(actor_cap_rule, dict):
            tighten_governance_limit(
                effective,
                actor_cap_rule,
                source=f"actor_capability:{actor_id}:{capability_id}",
                trace=trace,
            )

    dynamic_limits = extract_dynamic_limits_from_usage(
        actor_id=actor_id,
        capability_ids=capability_ids,
        usage=usage,
    )
    dyn_summary = dynamic_limits.get("summary") if isinstance(dynamic_limits, dict) else None
    if isinstance(dyn_summary, dict):
        tighten_governance_limit(effective, dyn_summary, source=f"dynamic_actor:{actor_id}", trace=trace)
    dyn_caps = dynamic_limits.get("by_capability") if isinstance(dynamic_limits, dict) else {}
    if isinstance(dyn_caps, dict):
        for capability_id, cap_dyn in dyn_caps.items():
            if isinstance(cap_dyn, dict):
                tighten_governance_limit(
                    effective,
                    cap_dyn,
                    source=f"dynamic_actor_capability:{actor_id}:{capability_id}",
                    trace=trace,
                )

    blocked_skills = set(normalize_governance_string_list(policy.get("blocked_skills", [])))
    blocked_caps = set(normalize_governance_string_list(policy.get("blocked_capabilities", [])))
    blocked_skills_actor = pick_actor_rule(policy.get("blocked_skills_by_actor", {}), actor_id)
    blocked_caps_actor = pick_actor_rule(policy.get("blocked_capabilities_by_actor", {}), actor_id)
    blocked_skills.update(normalize_governance_string_list(blocked_skills_actor))
    blocked_caps.update(normalize_governance_string_list(blocked_caps_actor))

    return {
        "effective_limits": effective,
        "limit_trace": trace,
        "dynamic_limits": dynamic_limits,
        "blocked_skills": sorted(blocked_skills),
        "blocked_capabilities": sorted(blocked_caps),
        "capability_ids": capability_ids,
    }


def apply_governance_to_skill_flow(
    *,
    actor_id: str,
    steps: List[Dict[str, Any]],
    requested_budget: Dict[str, int],
    requested_max_parallel: int,
    explicit_max_parallel: bool,
    policy: Dict[str, Any],
    usage: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply governance constraints to a skill flow.

    The caller must supply *policy* and *usage* (see
    :func:`resolve_agent_governance_for_skill_flow`).
    """
    governance = resolve_agent_governance_for_skill_flow(actor_id=actor_id, steps=steps, policy=policy, usage=usage)
    limits = governance.get("effective_limits", {}) if isinstance(governance.get("effective_limits"), dict) else {}
    blocked_skills = set(governance.get("blocked_skills", [])) if isinstance(governance.get("blocked_skills"), list) else set()
    blocked_caps = set(governance.get("blocked_capabilities", [])) if isinstance(governance.get("blocked_capabilities"), list) else set()

    for step in steps:
        skill_id = str(step.get("skill_id", "") or "").strip()
        capability_id = str(step.get("capability_id", "") or "").strip()
        if skill_id and skill_id in blocked_skills:
            raise ValueError(f"skill \u88ab\u6cbb\u7406\u7b56\u7565\u7981\u7528: {skill_id}")
        if capability_id and capability_id in blocked_caps:
            raise ValueError(f"capability \u88ab\u6cbb\u7406\u7b56\u7565\u7981\u7528: {capability_id}")

    final_budget = normalize_skill_budget_limit(requested_budget)
    for field in ("max_steps", "max_failures", "max_duration_seconds"):
        req_val = int(final_budget.get(field, 0) or 0)
        limit_val = int(limits.get(field, 0) or 0)
        if req_val > 0 and limit_val > 0 and req_val > limit_val:
            raise ValueError(f"\u8d85\u51fa\u6cbb\u7406\u989d\u5ea6: {field}={req_val} > {limit_val}")
        if req_val <= 0:
            final_budget[field] = limit_val if limit_val > 0 else 0

    req_mp = max(1, min(int(requested_max_parallel or 1), 8))
    limit_mp = int(limits.get("max_parallel", 0) or 0)
    if explicit_max_parallel and limit_mp > 0 and req_mp > limit_mp:
        raise ValueError(f"\u8d85\u51fa\u6cbb\u7406\u989d\u5ea6: max_parallel={req_mp} > {limit_mp}")
    final_mp = req_mp
    if not explicit_max_parallel and limit_mp > 0:
        final_mp = limit_mp
    if final_budget.get("max_steps", 0) > 0 and len(steps) > int(final_budget.get("max_steps", 0)):
        raise ValueError(f"steps \u8d85\u51fa\u9884\u7b97\u4e0a\u9650: {len(steps)} > {final_budget.get('max_steps')}")

    return {
        "budget_limit": final_budget,
        "max_parallel": final_mp,
        "governance": governance,
    }


def normalize_agent_skill_condition(condition_raw: Any) -> Dict[str, Any]:
    raw = condition_raw if isinstance(condition_raw, dict) else {}
    if not raw:
        return {}
    depends_on_raw = raw.get("depends_on", [])
    depends_on: List[str] = []
    if isinstance(depends_on_raw, list):
        for item in depends_on_raw:
            sid = _normalize_agent_template_id(str(item or "").strip())
            if sid:
                depends_on.append(sid)
    status_in_raw = raw.get("status_in", ["done"])
    status_in: List[str] = []
    if isinstance(status_in_raw, list):
        for item in status_in_raw:
            st = str(item or "").strip().lower()
            if st in {"done", "error", "skipped"}:
                status_in.append(st)
    if not status_in:
        status_in = ["done"]
    return {
        "depends_on": list(dict.fromkeys(depends_on)),
        "status_in": sorted(set(status_in)),
        "require_all": _coerce_bool(raw.get("require_all", True), default=True),
        "if_overall_ok": _coerce_bool(raw.get("if_overall_ok", False), default=False),
    }
