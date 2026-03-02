#!/usr/bin/env python3
"""Capability idempotency cache routes extracted from server.py."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Dict

from flask import Blueprint, jsonify, request


def create_idempotency_blueprint(
    *,
    parse_boolish: Callable[[Any, bool], bool],
    normalize_filter_text: Callable[[Any], str],
    normalize_ttl: Callable[[Any, int], int],
    collect_records: Callable[..., Dict[str, Any]],
    capability_idempotency_ttl_getter: Callable[[], int],
    capability_idempotency_limit_getter: Callable[[], int],
    capability_cache_getter: Callable[[], Dict[str, Dict[str, Any]]],
    capability_lock_getter: Callable[[], Any],
    filter_entries: Callable[..., Dict[str, Dict[str, Any]]],
    trim_entries_with_limit: Callable[..., Dict[str, Dict[str, Any]]],
    limit_entries: Callable[..., Dict[str, Dict[str, Any]]],
    load_store: Callable[..., Dict[str, Dict[str, Any]]],
    save_store: Callable[[Dict[str, Dict[str, Any]]], None],
) -> Blueprint:
    bp = Blueprint("idempotency_api", __name__)

    @bp.route("/api/capabilities/idempotency/cache", methods=["GET"])
    def api_capability_idempotency_cache():
        source = str(request.args.get("source", "merged") or "merged").strip().lower()
        if source not in {"memory", "persisted", "merged"}:
            return jsonify({"error": "source 仅支持 memory/persisted/merged"}), 400
        include_expired = parse_boolish(request.args.get("include_expired", "false"), default=False)
        match_mode = str(request.args.get("match_mode", "contains") or "contains").strip().lower()
        if match_mode not in {"contains", "exact"}:
            return jsonify({"error": "match_mode 仅支持 contains/exact"}), 400
        actor_id_filter = normalize_filter_text(request.args.get("actor_id", ""))
        endpoint_filter = normalize_filter_text(request.args.get("endpoint", ""))
        idempotency_key_filter = normalize_filter_text(request.args.get("idempotency_key", ""))
        project_path_filter = normalize_filter_text(request.args.get("project_path", ""))
        ttl_seconds = normalize_ttl(
            request.args.get("ttl_seconds", capability_idempotency_ttl_getter()),
            default=capability_idempotency_ttl_getter(),
        )
        try:
            limit = int(request.args.get("limit", "200") or "200")
        except Exception:
            limit = 200
        limit = max(1, min(limit, 1000))
        try:
            offset = int(request.args.get("offset", "0") or "0")
        except Exception:
            offset = 0
        offset = max(0, offset)

        payload = collect_records(
            source=source,
            ttl_seconds=ttl_seconds,
            include_expired=include_expired,
            limit=limit,
            offset=offset,
            actor_id_filter=actor_id_filter,
            endpoint_filter=endpoint_filter,
            idempotency_key_filter=idempotency_key_filter,
            project_path_filter=project_path_filter,
            match_mode=match_mode,
        )
        return jsonify({"ok": True, **payload})

    @bp.route("/api/capabilities/idempotency/cache/prune", methods=["POST"])
    def api_capability_idempotency_cache_prune():
        payload = request.json or {}
        ttl_seconds = normalize_ttl(
            payload.get("ttl_seconds", capability_idempotency_ttl_getter()),
            default=capability_idempotency_ttl_getter(),
        )
        remove_expired = parse_boolish(payload.get("remove_expired", True), default=True)
        clear_memory = parse_boolish(payload.get("clear_memory", False), default=False)
        clear_persisted = parse_boolish(payload.get("clear_persisted", False), default=False)

        max_entries_raw = payload.get("max_entries", None)
        max_entries = None
        if max_entries_raw not in {None, ""}:
            try:
                max_entries = max(1, int(max_entries_raw))
            except Exception:
                max_entries = capability_idempotency_limit_getter()

        with capability_lock_getter():
            cache = capability_cache_getter()
            memory_before = len(cache)
            memory_after_map = deepcopy(cache)
            if clear_memory:
                memory_after_map = {}
            else:
                if remove_expired:
                    memory_after_map = filter_entries(
                        memory_after_map,
                        ttl_seconds=ttl_seconds,
                        include_expired=False,
                    )
                else:
                    memory_after_map = filter_entries(
                        memory_after_map,
                        ttl_seconds=ttl_seconds,
                        include_expired=True,
                    )
                if max_entries is not None:
                    if remove_expired:
                        memory_after_map = trim_entries_with_limit(
                            memory_after_map,
                            max_entries=max_entries,
                            ttl_seconds=ttl_seconds,
                        )
                    else:
                        memory_after_map = limit_entries(
                            memory_after_map,
                            max_entries=max_entries,
                        )
                else:
                    if remove_expired:
                        memory_after_map = trim_entries_with_limit(
                            memory_after_map,
                            max_entries=capability_idempotency_limit_getter(),
                            ttl_seconds=ttl_seconds,
                        )
                    else:
                        memory_after_map = limit_entries(
                            memory_after_map,
                            max_entries=capability_idempotency_limit_getter(),
                        )
            cache.clear()
            cache.update(memory_after_map)
            memory_after = len(cache)

        persisted_before_map = load_store(include_expired=True, ttl_seconds=ttl_seconds)
        persisted_before = len(persisted_before_map)
        if clear_persisted:
            persisted_after_map = {}
        else:
            if remove_expired:
                persisted_after_map = filter_entries(
                    persisted_before_map,
                    ttl_seconds=ttl_seconds,
                    include_expired=False,
                )
            else:
                persisted_after_map = filter_entries(
                    persisted_before_map,
                    ttl_seconds=ttl_seconds,
                    include_expired=True,
                )
            if max_entries is not None:
                if remove_expired:
                    persisted_after_map = trim_entries_with_limit(
                        persisted_after_map,
                        max_entries=max_entries,
                        ttl_seconds=ttl_seconds,
                    )
                else:
                    persisted_after_map = limit_entries(
                        persisted_after_map,
                        max_entries=max_entries,
                    )
            else:
                if remove_expired:
                    persisted_after_map = trim_entries_with_limit(
                        persisted_after_map,
                        max_entries=capability_idempotency_limit_getter(),
                        ttl_seconds=ttl_seconds,
                    )
                else:
                    persisted_after_map = limit_entries(
                        persisted_after_map,
                        max_entries=capability_idempotency_limit_getter(),
                    )
        save_store(persisted_after_map)
        persisted_after = len(persisted_after_map)

        snapshot = collect_records(
            source="merged",
            ttl_seconds=ttl_seconds,
            include_expired=False,
            limit=200,
        )
        return jsonify(
            {
                "ok": True,
                "prune": {
                    "ttl_seconds": ttl_seconds,
                    "remove_expired": remove_expired,
                    "clear_memory": clear_memory,
                    "clear_persisted": clear_persisted,
                    "max_entries": max_entries,
                    "memory_before": memory_before,
                    "memory_after": memory_after,
                    "memory_removed": max(memory_before - memory_after, 0),
                    "persisted_before": persisted_before,
                    "persisted_after": persisted_after,
                    "persisted_removed": max(persisted_before - persisted_after, 0),
                },
                **snapshot,
            }
        )

    return bp

