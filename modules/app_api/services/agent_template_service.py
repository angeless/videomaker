"""Agent template functions extracted from server.py (L1-6)."""

import json
from copy import deepcopy
from datetime import datetime
from typing import Optional, Dict, List, Any

# ── Module-level state (defaults; overwritten by init()) ────────────
_project_dir = None
_AGENT_SYSTEM_TEMPLATES: Dict[str, Dict[str, Any]] = {}
_AGENT_TEMPLATE_SCOPE_ORDER: Dict[str, int] = {"system": 0, "project": 1, "agent": 2}


def init(*, project_dir=None, agent_system_templates=None, agent_template_scope_order=None):
    global _project_dir, _AGENT_SYSTEM_TEMPLATES, _AGENT_TEMPLATE_SCOPE_ORDER
    if project_dir is not None:
        _project_dir = project_dir
    if agent_system_templates is not None:
        _AGENT_SYSTEM_TEMPLATES = agent_system_templates
    if agent_template_scope_order is not None:
        _AGENT_TEMPLATE_SCOPE_ORDER = agent_template_scope_order


# ── Lazy imports from server.py for cross-dependencies ──────────────

def _normalize_agent_template_id(value: str) -> str:
    from modules.app_api.server import _normalize_agent_template_id as _impl
    return _impl(value)


def _coerce_bool(value, default: bool = False) -> bool:
    from modules.app_api.server import _coerce_bool as _impl
    return _impl(value, default=default)


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    from modules.app_api.server import _deep_merge_dict as _impl
    return _impl(base, override)


def _get_nested_value(data: Dict[str, Any], path: str):
    from modules.app_api.server import _get_nested_value as _impl
    return _impl(data, path)


def _set_nested_value(data: Dict[str, Any], path: str, value: Any):
    from modules.app_api.server import _set_nested_value as _impl
    return _impl(data, path, value)


def _get_effective_project_dir():
    """Return the effective project dir, checking server module at call-time."""
    import modules.app_api.server as _srv
    return getattr(_srv, "_project_dir", None) or _project_dir


def _read_project_json(filename: str, fallback=None):
    from modules.app_api.server import _read_project_json as _impl
    return _impl(filename, fallback=fallback)


def _project_data_path(filename: str):
    from modules.app_api.server import _project_data_path as _impl
    return _impl(filename)


# ── Functions ───────────────────────────────────────────────────────

def _agent_template_value_matches_type(value: Any, slot_type: str) -> bool:
    t = str(slot_type or "").strip().lower()
    if t == "string":
        return isinstance(value, str)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return True


def _validate_agent_template_slot_value(slot: Dict[str, Any], value: Any) -> Optional[str]:
    slot_type = str(slot.get("type", "string") or "string").strip().lower()
    if not _agent_template_value_matches_type(value, slot_type):
        return f"类型不匹配（期望 {slot_type}）"

    enum_raw = slot.get("enum")
    if isinstance(enum_raw, list) and enum_raw and value not in enum_raw:
        return f"不在 enum 范围内: {enum_raw}"

    if slot_type in {"number", "integer"} and isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = slot.get("minimum")
        maximum = slot.get("maximum")
        if isinstance(minimum, (int, float)) and value < minimum:
            return f"小于最小值 {minimum}"
        if isinstance(maximum, (int, float)) and value > maximum:
            return f"大于最大值 {maximum}"
    return None


def _normalize_agent_template_variables(variables_raw: Any) -> List[Dict[str, Any]]:
    if variables_raw in (None, ""):
        return []
    if not isinstance(variables_raw, list):
        raise ValueError("variables 必须是数组")

    out: List[Dict[str, Any]] = []
    seen_keys = set()
    allowed_types = {"string", "number", "integer", "boolean", "array", "object"}
    for idx, item in enumerate(variables_raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"variables[{idx}] 必须是对象")
        key = str(item.get("key", "") or item.get("name", "")).strip()
        if not key:
            raise ValueError(f"variables[{idx}].key 不能为空")
        if key in seen_keys:
            raise ValueError(f"variables 存在重复 key: {key}")
        seen_keys.add(key)

        slot_type = str(item.get("type", "string") or "string").strip().lower()
        if slot_type not in allowed_types:
            raise ValueError(f"variables[{idx}].type 仅支持 {sorted(allowed_types)}")

        slot: Dict[str, Any] = {
            "key": key,
            "type": slot_type,
            "required": _coerce_bool(item.get("required", False), default=False),
        }
        if "description" in item:
            slot["description"] = str(item.get("description", "") or "").strip()[:240]
        if "enum" in item and item.get("enum") is not None:
            if not isinstance(item.get("enum"), list):
                raise ValueError(f"variables[{idx}].enum 必须是数组")
            slot["enum"] = list(item.get("enum", []))
        if "minimum" in item and item.get("minimum") is not None:
            if not isinstance(item.get("minimum"), (int, float)):
                raise ValueError(f"variables[{idx}].minimum 必须是数字")
            slot["minimum"] = item.get("minimum")
        if "maximum" in item and item.get("maximum") is not None:
            if not isinstance(item.get("maximum"), (int, float)):
                raise ValueError(f"variables[{idx}].maximum 必须是数字")
            slot["maximum"] = item.get("maximum")
        if "minimum" in slot and "maximum" in slot and slot["minimum"] > slot["maximum"]:
            raise ValueError(f"variables[{idx}] minimum 不能大于 maximum")
        if "default" in item:
            default_val = item.get("default")
            err = _validate_agent_template_slot_value(slot, default_val)
            if err:
                raise ValueError(f"variables[{idx}].default 非法: {err}")
            slot["default"] = deepcopy(default_val)
        out.append(slot)
    return out


def _validate_template_slot_values(
    *,
    variables: List[Dict[str, Any]],
    payload: Dict[str, Any],
    source_label: str,
) -> List[str]:
    if not isinstance(payload, dict) or not variables:
        return []
    errors: List[str] = []
    for slot in variables:
        key = str(slot.get("key", "") or "").strip()
        if not key:
            continue
        exists, value = _get_nested_value(payload, key)
        if not exists:
            continue
        err = _validate_agent_template_slot_value(slot, value)
        if err:
            errors.append(f"{source_label}.{key}: {err}")
    return errors


def _hydrate_agent_template_defaults(template_raw: Dict[str, Any]) -> Dict[str, Any]:
    out = deepcopy(template_raw) if isinstance(template_raw, dict) else {}
    out["template_id"] = _normalize_agent_template_id(out.get("template_id", ""))
    out["name"] = str(out.get("name", "") or "").strip()
    out["capability_id"] = str(out.get("capability_id", "") or "").strip() or "generic"
    out["scope"] = str(out.get("scope", "") or "").strip().lower()
    out["actor_id"] = str(out.get("actor_id", "") or "").strip()
    tags_raw = out.get("tags", [])
    out["tags"] = [str(x).strip() for x in tags_raw if str(x).strip()] if isinstance(tags_raw, list) else []
    out["content"] = deepcopy(out.get("content", {})) if isinstance(out.get("content"), dict) else {}
    out["overrides"] = deepcopy(out.get("overrides", {})) if isinstance(out.get("overrides"), dict) else {}
    out["base_template_id"] = _normalize_agent_template_id(str(out.get("base_template_id", "") or ""))
    try:
        out["variables"] = _normalize_agent_template_variables(out.get("variables", []))
    except Exception:
        out["variables"] = []
    out["updated_at"] = str(out.get("updated_at", "") or "")
    if out["scope"] != "agent":
        out["actor_id"] = ""
    if out["scope"] not in {"system", "project", "agent"}:
        out["scope"] = "project"
    if out["base_template_id"] == out["template_id"]:
        out["base_template_id"] = ""
    return out


def _normalize_agent_template_payload(
    payload: Dict,
    *,
    scope_default: str = "agent",
    actor_id_default: str = "",
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("模板参数必须是对象")
    template_id_raw = str(payload.get("template_id", "") or payload.get("id", "")).strip()
    name_raw = str(payload.get("name", "") or "").strip()
    template_id = _normalize_agent_template_id(template_id_raw or name_raw)
    if not template_id:
        raise ValueError("template_id 不能为空")
    if not name_raw:
        raise ValueError("name 不能为空")

    scope = str(payload.get("scope", scope_default) or scope_default).strip().lower()
    if scope not in {"system", "project", "agent"}:
        raise ValueError("scope 仅支持 system/project/agent")

    actor_id = str(payload.get("actor_id", actor_id_default) or actor_id_default).strip()
    if scope == "agent" and not actor_id:
        raise ValueError("agent scope 需要 actor_id")
    if scope != "agent":
        actor_id = ""

    capability_id = str(payload.get("capability_id", "") or "").strip() or "generic"
    base_template_id = _normalize_agent_template_id(str(payload.get("base_template_id", "") or ""))
    if base_template_id == template_id:
        raise ValueError("base_template_id 不能指向自己")

    content_raw = payload.get("content", {})
    if content_raw is None:
        content_raw = {}
    if not isinstance(content_raw, dict):
        raise ValueError("content 必须是对象")
    overrides_raw = payload.get("overrides", {})
    if overrides_raw is None:
        overrides_raw = {}
    if not isinstance(overrides_raw, dict):
        raise ValueError("overrides 必须是对象")
    variables = _normalize_agent_template_variables(payload.get("variables", []))
    slot_errors = _validate_template_slot_values(
        variables=variables,
        payload=content_raw,
        source_label="content",
    ) + _validate_template_slot_values(
        variables=variables,
        payload=overrides_raw,
        source_label="overrides",
    )
    if slot_errors:
        raise ValueError(f"变量约束不满足: {'; '.join(slot_errors[:5])}")

    tags_raw = payload.get("tags", [])
    tags = tags_raw if isinstance(tags_raw, list) else []
    tags = [str(x).strip() for x in tags if str(x).strip()]

    return {
        "template_id": template_id,
        "name": name_raw,
        "capability_id": capability_id,
        "scope": scope,
        "actor_id": actor_id,
        "tags": tags,
        "base_template_id": base_template_id,
        "overrides": deepcopy(overrides_raw),
        "variables": variables,
        "content": content_raw,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _read_agent_template_store() -> Dict[str, Any]:
    raw = _read_project_json("agent_templates.json", fallback={})
    if not isinstance(raw, dict):
        return {"project": {}, "agent": {}}
    project = raw.get("project", {})
    agent = raw.get("agent", {})
    return {
        "project": project if isinstance(project, dict) else {},
        "agent": agent if isinstance(agent, dict) else {},
    }


def _agent_template_lookup_key(scope: str, actor_id: str, template_id: str) -> str:
    return f"{str(scope or '').strip().lower()}|{str(actor_id or '').strip()}|{_normalize_agent_template_id(template_id)}"


def _agent_template_chain_token(template: Dict[str, Any]) -> str:
    scope = str(template.get("scope", "") or "").strip().lower()
    actor_id = str(template.get("actor_id", "") or "").strip()
    template_id = str(template.get("template_id", "") or "").strip()
    if scope == "agent" and actor_id:
        return f"{scope}:{actor_id}:{template_id}"
    return f"{scope}:{template_id}"


def _agent_template_base_candidate_keys(template: Dict[str, Any]) -> List[str]:
    scope = str(template.get("scope", "") or "").strip().lower()
    actor_id = str(template.get("actor_id", "") or "").strip()
    base_id = _normalize_agent_template_id(str(template.get("base_template_id", "") or ""))
    if not base_id:
        return []
    if scope == "agent":
        return [
            _agent_template_lookup_key("agent", actor_id, base_id),
            _agent_template_lookup_key("project", "", base_id),
            _agent_template_lookup_key("system", "", base_id),
        ]
    if scope == "project":
        return [
            _agent_template_lookup_key("project", "", base_id),
            _agent_template_lookup_key("system", "", base_id),
        ]
    return [_agent_template_lookup_key("system", "", base_id)]


def _resolve_agent_template_effective(
    template: Dict[str, Any],
    *,
    lookup: Dict[str, Dict[str, Any]],
    cache: Dict[str, Dict[str, Any]],
    visiting: Optional[set] = None,
) -> Dict[str, Any]:
    hydrated = _hydrate_agent_template_defaults(template)
    own_key = _agent_template_lookup_key(
        hydrated.get("scope", ""),
        hydrated.get("actor_id", ""),
        hydrated.get("template_id", ""),
    )
    cached = cache.get(own_key)
    if isinstance(cached, dict):
        return cached

    if visiting is None:
        visiting = set()
    if own_key in visiting:
        token = _agent_template_chain_token(hydrated)
        ret = {
            "effective_content": deepcopy(hydrated.get("content", {})),
            "template_chain": [token],
            "resolve_warnings": [f"模板继承存在循环引用: {token}"],
        }
        cache[own_key] = ret
        return ret

    visiting.add(own_key)
    warnings: List[str] = []
    chain: List[str] = []
    effective: Dict[str, Any] = {}

    base_template = None
    for candidate_key in _agent_template_base_candidate_keys(hydrated):
        candidate = lookup.get(candidate_key)
        if isinstance(candidate, dict):
            base_template = candidate
            break
    if hydrated.get("base_template_id"):
        if base_template is None:
            warnings.append(f"base_template_id 不存在或不可见: {hydrated.get('base_template_id')}")
        else:
            base_resolved = _resolve_agent_template_effective(
                base_template,
                lookup=lookup,
                cache=cache,
                visiting=visiting,
            )
            effective = deepcopy(base_resolved.get("effective_content", {}))
            chain.extend(base_resolved.get("template_chain", []))
            warnings.extend(base_resolved.get("resolve_warnings", []))

    effective = _deep_merge_dict(effective, hydrated.get("content", {}))
    effective = _deep_merge_dict(effective, hydrated.get("overrides", {}))

    for slot in hydrated.get("variables", []):
        key = str(slot.get("key", "") or "").strip()
        if not key:
            continue
        exists, _ = _get_nested_value(effective, key)
        if not exists and "default" in slot:
            _set_nested_value(effective, key, slot.get("default"))

    for slot in hydrated.get("variables", []):
        key = str(slot.get("key", "") or "").strip()
        if not key:
            continue
        exists, value = _get_nested_value(effective, key)
        if not exists:
            if _coerce_bool(slot.get("required", False), default=False):
                warnings.append(f"变量缺失(required): {key}")
            continue
        err = _validate_agent_template_slot_value(slot, value)
        if err:
            warnings.append(f"变量约束不满足 {key}: {err}")

    chain.append(_agent_template_chain_token(hydrated))
    ret = {
        "effective_content": effective,
        "template_chain": list(dict.fromkeys(str(x) for x in chain if str(x).strip())),
        "resolve_warnings": list(dict.fromkeys(str(x) for x in warnings if str(x).strip())),
    }
    cache[own_key] = ret
    visiting.discard(own_key)
    return ret


def _collect_agent_templates(
    *,
    store: Optional[Dict[str, Any]] = None,
    actor_id: str = "",
    include_system: bool = True,
) -> List[Dict[str, Any]]:
    actor_norm = str(actor_id or "").strip()
    current_store = store if isinstance(store, dict) else _read_agent_template_store()
    out: List[Dict[str, Any]] = []
    if include_system:
        out.extend(_hydrate_agent_template_defaults(x) for x in _AGENT_SYSTEM_TEMPLATES.values())

    project_templates = current_store.get("project", {})
    if isinstance(project_templates, dict):
        for item in project_templates.values():
            out.append(_hydrate_agent_template_defaults(item))

    if actor_norm:
        agent_bucket = current_store.get("agent", {})
        actor_templates = agent_bucket.get(actor_norm, {}) if isinstance(agent_bucket, dict) else {}
        if isinstance(actor_templates, dict):
            for item in actor_templates.values():
                out.append(_hydrate_agent_template_defaults(item))
    return out


def _validate_agent_template_base_reference(template: Dict[str, Any], *, store: Dict[str, Any]) -> Optional[str]:
    hydrated = _hydrate_agent_template_defaults(template)
    base_id = str(hydrated.get("base_template_id", "") or "").strip()
    if not base_id:
        return None

    actor_id = str(hydrated.get("actor_id", "") or "").strip()
    pool = _collect_agent_templates(store=store, actor_id=actor_id, include_system=True)
    lookup: Dict[str, Dict[str, Any]] = {}
    own_key = _agent_template_lookup_key(
        hydrated.get("scope", ""),
        hydrated.get("actor_id", ""),
        hydrated.get("template_id", ""),
    )
    for item in pool:
        key = _agent_template_lookup_key(item.get("scope", ""), item.get("actor_id", ""), item.get("template_id", ""))
        if key == own_key:
            continue
        lookup[key] = item
    lookup[own_key] = hydrated

    if not any(candidate_key in lookup for candidate_key in _agent_template_base_candidate_keys(hydrated)):
        return f"base_template_id 不存在或不可见: {base_id}"

    cache: Dict[str, Dict[str, Any]] = {}
    resolved = _resolve_agent_template_effective(hydrated, lookup=lookup, cache=cache, visiting=set())
    for msg in resolved.get("resolve_warnings", []):
        if "循环引用" in str(msg):
            return str(msg)
    return None


def _save_agent_template_store(store: Dict[str, Any]) -> Dict[str, Any]:
    if _get_effective_project_dir() is None:
        return {"project": {}, "agent": {}}
    project_raw = store.get("project", {}) if isinstance(store, dict) else {}
    agent_raw = store.get("agent", {}) if isinstance(store, dict) else {}

    project_out: Dict[str, Dict] = {}
    if isinstance(project_raw, dict):
        for _, item in project_raw.items():
            try:
                tmpl = _normalize_agent_template_payload(item, scope_default="project")
            except Exception:
                continue
            if tmpl.get("scope") != "project":
                tmpl["scope"] = "project"
                tmpl["actor_id"] = ""
            project_out[tmpl["template_id"]] = tmpl

    agent_out: Dict[str, Dict[str, Dict]] = {}
    if isinstance(agent_raw, dict):
        for actor_key, actor_templates in agent_raw.items():
            actor_id = str(actor_key or "").strip()
            if not actor_id or not isinstance(actor_templates, dict):
                continue
            bucket: Dict[str, Dict] = {}
            for _, item in actor_templates.items():
                try:
                    tmpl = _normalize_agent_template_payload(
                        item,
                        scope_default="agent",
                        actor_id_default=actor_id,
                    )
                except Exception:
                    continue
                tmpl["scope"] = "agent"
                tmpl["actor_id"] = actor_id
                bucket[tmpl["template_id"]] = tmpl
            if bucket:
                agent_out[actor_id] = bucket

    out = {"project": project_out, "agent": agent_out}
    p = _project_data_path("agent_templates.json")
    if p is not None:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _list_agent_templates(
    *,
    capability_id: str = "",
    scope: str = "",
    actor_id: str = "",
    include_system: bool = True,
    resolve: bool = True,
) -> List[Dict[str, Any]]:
    capability_norm = str(capability_id or "").strip()
    scope_norm = str(scope or "").strip().lower()
    actor_norm = str(actor_id or "").strip()
    store = _read_agent_template_store()
    full_pool = _collect_agent_templates(store=store, actor_id=actor_norm, include_system=True)
    out: List[Dict[str, Any]] = []
    for item in full_pool:
        scope_item = str(item.get("scope", "") or "").strip().lower()
        if scope_norm and scope_item != scope_norm:
            continue
        if not include_system and scope_item == "system":
            continue
        out.append(deepcopy(item))

    if capability_norm:
        out = [x for x in out if str(x.get("capability_id", "") or "") == capability_norm]

    if resolve:
        lookup = {
            _agent_template_lookup_key(item.get("scope", ""), item.get("actor_id", ""), item.get("template_id", "")): item
            for item in full_pool
        }
        cache: Dict[str, Dict[str, Any]] = {}
        for item in out:
            resolved = _resolve_agent_template_effective(item, lookup=lookup, cache=cache, visiting=set())
            item["effective_content"] = deepcopy(resolved.get("effective_content", item.get("content", {})))
            item["template_chain"] = list(resolved.get("template_chain", []))
            item["resolve_warnings"] = list(resolved.get("resolve_warnings", []))

    def _sort_key(item: Dict[str, Any]):
        return (
            _AGENT_TEMPLATE_SCOPE_ORDER.get(str(item.get("scope", "")).lower(), 99),
            str(item.get("name", "")).lower(),
            str(item.get("template_id", "")).lower(),
        )

    out.sort(key=_sort_key)
    for item in out:
        scope_item = str(item.get("scope", "")).lower()
        item["readonly"] = scope_item == "system"
    return out
