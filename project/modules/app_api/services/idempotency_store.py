#!/usr/bin/env python3
"""Capability idempotency cache/persistence service."""

from __future__ import annotations

import json
import threading
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


class CapabilityIdempotencyStore:
    def __init__(
        self,
        *,
        store_path_getter: Callable[[], Optional[Path]],
        project_anchor_getter: Callable[[], str],
        default_ttl_seconds: int,
        default_limit: int,
        memory_cache: Optional[Dict[str, Dict[str, Any]]] = None,
        lock: Optional[threading.Lock] = None,
    ):
        self._store_path_getter = store_path_getter
        self._project_anchor_getter = project_anchor_getter
        self.default_ttl_seconds = max(int(default_ttl_seconds or 0), 0)
        self.default_limit = max(int(default_limit or 0), 1)
        self.cache = memory_cache if isinstance(memory_cache, dict) else {}
        self.lock = lock if lock is not None else threading.Lock()

    def store_path(self) -> Optional[Path]:
        return self._store_path_getter()

    def normalize_entry(self, raw: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(raw, dict):
            return None
        body = raw.get("body")
        if not isinstance(body, dict):
            return None
        try:
            status = int(raw.get("status", 200) or 200)
        except Exception:
            status = 200
        created_at = str(raw.get("created_at", "") or "")
        return {
            "status": status,
            "body": deepcopy(body),
            "created_at": created_at,
        }

    def _parse_iso_datetime(self, value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except Exception:
            try:
                if text.endswith("Z"):
                    return datetime.fromisoformat(text[:-1] + "+00:00")
            except Exception:
                return None
        return None

    def entry_expired(
        self,
        entry: Dict[str, Any],
        *,
        ttl_seconds: Optional[int] = None,
        now_epoch: Optional[float] = None,
    ) -> bool:
        ttl = self.default_ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        if ttl <= 0:
            return False
        created = self._parse_iso_datetime(str((entry or {}).get("created_at", "") or ""))
        if created is None:
            return False
        ts_now = time.time() if now_epoch is None else float(now_epoch)
        return (ts_now - created.timestamp()) > float(ttl)

    def filter_entries(
        self,
        entries: Dict[str, Dict[str, Any]],
        *,
        ttl_seconds: Optional[int] = None,
        include_expired: bool = False,
    ) -> Dict[str, Dict[str, Any]]:
        ttl = self.default_ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        now_epoch = time.time()
        out: Dict[str, Dict[str, Any]] = {}
        for key, entry in (entries or {}).items():
            normalized = self.normalize_entry(entry)
            if normalized is None:
                continue
            expired = self.entry_expired(normalized, ttl_seconds=ttl, now_epoch=now_epoch)
            if expired and not include_expired:
                continue
            out[str(key)] = normalized
        return out

    def load_store(
        self,
        *,
        include_expired: bool = False,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        p = self.store_path()
        if p is None or not p.exists():
            return {}
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

        out: Dict[str, Dict[str, Any]] = {}
        if isinstance(raw, dict) and isinstance(raw.get("records"), list):
            for item in raw.get("records", []):
                if not isinstance(item, dict):
                    continue
                cache_key = str(item.get("cache_key", "") or "").strip()
                if not cache_key:
                    continue
                normalized = self.normalize_entry(item)
                if normalized is None:
                    continue
                out[cache_key] = normalized
            return self.filter_entries(
                out,
                ttl_seconds=self.default_ttl_seconds if ttl_seconds is None else ttl_seconds,
                include_expired=include_expired,
            )

        if isinstance(raw, dict):
            for cache_key, item in raw.items():
                key = str(cache_key or "").strip()
                if not key:
                    continue
                normalized = self.normalize_entry(item)
                if normalized is None:
                    continue
                out[key] = normalized
        return self.filter_entries(
            out,
            ttl_seconds=self.default_ttl_seconds if ttl_seconds is None else ttl_seconds,
            include_expired=include_expired,
        )

    def save_store(self, records: Dict[str, Dict[str, Any]]) -> None:
        p = self.store_path()
        if p is None:
            return
        p.parent.mkdir(parents=True, exist_ok=True)
        items = []
        for cache_key, entry in (records or {}).items():
            normalized = self.normalize_entry(entry)
            if normalized is None:
                continue
            if not str(normalized.get("created_at", "") or "").strip():
                normalized["created_at"] = datetime.now().isoformat(timespec="seconds")
            items.append({
                "cache_key": str(cache_key),
                **normalized,
            })
        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "records": items,
        }
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def trim_entries(
        self,
        entries: Dict[str, Dict[str, Any]],
        *,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        filtered = self.filter_entries(
            entries,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds,
            include_expired=False,
        )
        if len(filtered) <= self.default_limit:
            return filtered
        ordered = sorted(
            filtered.items(),
            key=lambda kv: str((kv[1] or {}).get("created_at", "") or ""),
        )
        kept = ordered[-self.default_limit:]
        return {k: v for k, v in kept}

    def trim_entries_with_limit(
        self,
        entries: Dict[str, Dict[str, Any]],
        *,
        max_entries: int,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        max_n = max(int(max_entries or 0), 1)
        filtered = self.filter_entries(
            entries,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds,
            include_expired=False,
        )
        if len(filtered) <= max_n:
            return filtered
        ordered = sorted(
            filtered.items(),
            key=lambda kv: str((kv[1] or {}).get("created_at", "") or ""),
        )
        kept = ordered[-max_n:]
        return {k: v for k, v in kept}

    def limit_entries(
        self,
        entries: Dict[str, Dict[str, Any]],
        *,
        max_entries: int,
    ) -> Dict[str, Dict[str, Any]]:
        max_n = max(int(max_entries or 0), 1)
        normalized_map: Dict[str, Dict[str, Any]] = {}
        for key, entry in (entries or {}).items():
            normalized = self.normalize_entry(entry)
            if normalized is None:
                continue
            normalized_map[str(key)] = normalized
        if len(normalized_map) <= max_n:
            return normalized_map
        ordered = sorted(
            normalized_map.items(),
            key=lambda kv: str((kv[1] or {}).get("created_at", "") or ""),
        )
        kept = ordered[-max_n:]
        return {k: v for k, v in kept}

    def get_persisted_entry(self, cache_key: str, *, ttl_seconds: Optional[int] = None) -> Optional[Dict[str, Any]]:
        records = self.load_store(
            include_expired=False,
            ttl_seconds=self.default_ttl_seconds if ttl_seconds is None else ttl_seconds,
        )
        item = records.get(str(cache_key or ""))
        normalized = self.normalize_entry(item)
        return deepcopy(normalized) if normalized is not None else None

    def compact_persisted_store(
        self,
        *,
        ttl_seconds: Optional[int] = None,
        max_entries: Optional[int] = None,
    ) -> Dict[str, Dict[str, Any]]:
        records_all = self.load_store(
            include_expired=True,
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds,
        )
        if max_entries is None:
            compacted = self.trim_entries(records_all, ttl_seconds=ttl_seconds)
        else:
            compacted = self.trim_entries_with_limit(
                records_all,
                max_entries=max_entries,
                ttl_seconds=ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds,
            )
        if compacted != records_all:
            self.save_store(compacted)
        return compacted

    def upsert_persisted_entry(
        self,
        cache_key: str,
        entry: Dict[str, Any],
        *,
        ttl_seconds: Optional[int] = None,
        max_entries: Optional[int] = None,
    ) -> None:
        records = self.compact_persisted_store(
            ttl_seconds=ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds,
            max_entries=max_entries if max_entries is not None else self.default_limit,
        )
        normalized = self.normalize_entry(entry)
        if normalized is None:
            return
        records[str(cache_key)] = normalized
        trimmed = self.trim_entries(records, ttl_seconds=ttl_seconds)
        self.save_store(trimmed)

    def make_cache_key(self, path: str, ctx: Dict[str, str]) -> str:
        project_anchor = str(self._project_anchor_getter() or "")
        return (
            f"{project_anchor}|"
            f"{path}|"
            f"{ctx.get('actor_id', '')}|"
            f"{ctx.get('idempotency_key', '')}"
        )

    def trim_memory_cache(self) -> None:
        if len(self.cache) <= self.default_limit:
            return
        trimmed = self.trim_entries(self.cache)
        self.cache.clear()
        self.cache.update(trimmed)

    def lookup(self, cache_key: str) -> Tuple[Optional[Dict[str, Any]], str]:
        replay_source = "memory"
        with self.lock:
            hit = self.cache.get(cache_key)
            if isinstance(hit, dict) and self.entry_expired(hit, ttl_seconds=self.default_ttl_seconds):
                self.cache.pop(cache_key, None)
                hit = None
            if not isinstance(hit, dict):
                hit = self.get_persisted_entry(cache_key, ttl_seconds=self.default_ttl_seconds)
                if isinstance(hit, dict):
                    self.cache[cache_key] = deepcopy(hit)
                    self.trim_memory_cache()
                    replay_source = "persisted"
            if isinstance(hit, dict) and self.entry_expired(hit, ttl_seconds=self.default_ttl_seconds):
                self.cache.pop(cache_key, None)
                hit = None
        return (deepcopy(hit) if isinstance(hit, dict) else None, replay_source)

    def put_success(self, cache_key: str, *, status: int, body: Dict[str, Any], created_at: Optional[str] = None) -> None:
        entry = {
            "status": int(status),
            "body": deepcopy(body) if isinstance(body, dict) else {},
            "created_at": str(created_at or datetime.now().isoformat(timespec="seconds")),
        }
        with self.lock:
            self.cache[cache_key] = deepcopy(entry)
            self.trim_memory_cache()
            self.upsert_persisted_entry(
                cache_key,
                entry,
                ttl_seconds=self.default_ttl_seconds,
                max_entries=self.default_limit,
            )
