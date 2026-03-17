"""Image semantic capability wrappers for analysis and retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol


class SupportsImageSemanticLibrary(Protocol):
    def ingest_local_images(self, source_path: str, max_images: int = 200, progress_callback=None, should_cancel=None) -> Dict:
        ...

    def search_assets(
        self,
        query: str = "",
        limit: int = 100,
        offset: int = 0,
        retrieval_mode: str = "hybrid",
        media_type: str = "all",
    ) -> List[Dict]:
        ...


def _normalize_path_items(image_paths: Iterable[Any]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in image_paths or []:
        if isinstance(raw, dict):
            text = str(raw.get("path") or raw.get("image_path") or "").strip()
        else:
            text = str(raw or "").strip()
        if not text:
            continue
        p = Path(text).expanduser()
        try:
            resolved = str(p.resolve())
        except Exception:
            resolved = str(p)
        key = resolved.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(resolved)
    return out


def _is_image_path(path_text: str) -> bool:
    suffix = Path(path_text).suffix.lower()
    return suffix in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".heic", ".gif", ".tiff"}


def _collect_semantic_terms(item: Dict[str, Any]) -> List[str]:
    terms: List[str] = []

    def _add(values):
        if isinstance(values, str):
            v = values.strip()
            if v:
                terms.append(v)
            return
        if isinstance(values, list):
            for one in values:
                _add(one)

    semantic = item.get("semantic", {}) if isinstance(item.get("semantic"), dict) else {}
    index_layers = semantic.get("index_layers", {}) if isinstance(semantic.get("index_layers"), dict) else {}
    core = index_layers.get("core_search_tags", {}) if isinstance(index_layers.get("core_search_tags"), dict) else {}
    secondary = index_layers.get("secondary_tags", {}) if isinstance(index_layers.get("secondary_tags"), dict) else {}
    for node in (core, secondary):
        if isinstance(node, dict):
            _add(node.get("zh", []))
            _add(node.get("en", []))
    _add(item.get("semantic_keywords", []))
    _add(item.get("objects", []))
    _add(item.get("scene_description", ""))
    _add(item.get("mood", ""))

    dedup: List[str] = []
    seen = set()
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(term)
    return dedup


def _normalize_search_hit(item: Dict[str, Any]) -> Dict[str, Any]:
    path_text = str(item.get("path") or "").strip()
    tags = _collect_semantic_terms(item)
    return {
        "uid": str(item.get("uid") or "").strip(),
        "filename": str(item.get("filename") or Path(path_text).name or "").strip(),
        "path": path_text,
        "available": bool(item.get("available", False)),
        "scene_description": str(item.get("scene_description") or "").strip(),
        "mood": str(item.get("mood") or "").strip(),
        "objects": item.get("objects", []) if isinstance(item.get("objects"), list) else [],
        "semantic_keywords": item.get("semantic_keywords", []) if isinstance(item.get("semantic_keywords"), list) else [],
        "semantic_tags": tags,
        "quality_score": item.get("quality_score"),
        "match_score": item.get("match_score"),
        "keyword_score": item.get("keyword_score"),
        "vector_score": item.get("vector_score"),
    }


def check_ai_status(library: Optional[Any] = None) -> Dict[str, Any]:
    """Check whether vision enrichment and vector search are available."""
    vision_ok = False
    vector_ok = False
    reasons: List[str] = []

    if library is None:
        reasons.append("未注入全局媒体库")
    else:
        if hasattr(library, "_vision_enrich_enabled"):
            vision_ok = library._vision_enrich_enabled()
        if hasattr(library, "_embedding_runtime_status"):
            emb = library._embedding_runtime_status()
            vector_ok = bool(emb.get("enabled"))
            if not vector_ok:
                reasons.append(emb.get("message") or emb.get("reason") or "向量搜索不可用")
        if not vision_ok:
            if not any("API Key" in r for r in reasons):
                reasons.append("视觉分析需要 OpenAI API Key")

    degraded = not vision_ok or not vector_ok
    return {
        "degraded": degraded,
        "vision_available": vision_ok,
        "vector_available": vector_ok,
        "keyword_available": True,
        "reasons": reasons,
        "message": "；".join(reasons) if reasons else "",
    }


def analyze_images(
    image_paths: Iterable[Any],
    *,
    library: Optional[SupportsImageSemanticLibrary] = None,
    max_images: int = 200,
    retrieval_mode: str = "hybrid",
    auto_ingest: bool = True,
) -> Dict[str, Any]:
    """Analyze single/batch image semantic signals using global media library."""
    paths = _normalize_path_items(image_paths)
    warnings: List[str] = []
    ingest_reports: List[Dict[str, Any]] = []

    if not paths:
        return {
            "input_count": 0,
            "analyzed_count": 0,
            "items": [],
            "ingest_reports": [],
            "warnings": ["未提供有效图片路径"],
        }

    if library is None:
        fallback_items = []
        for path in paths:
            fallback_items.append(
                {
                    "uid": "",
                    "filename": Path(path).name,
                    "path": path,
                    "available": Path(path).exists(),
                    "scene_description": "",
                    "mood": "",
                    "objects": [],
                    "semantic_keywords": [Path(path).stem],
                    "semantic_tags": [Path(path).stem],
                    "quality_score": None,
                    "match_score": None,
                    "keyword_score": None,
                    "vector_score": None,
                }
            )
        return {
            "input_count": len(paths),
            "analyzed_count": len(fallback_items),
            "items": fallback_items,
            "ingest_reports": [],
            "warnings": ["未注入全局媒体库，已返回基础占位语义结果"],
        }

    max_n = max(int(max_images or 1), 1)
    if auto_ingest:
        for path in paths:
            p = Path(path)
            if not p.exists():
                warnings.append(f"路径不存在，已跳过入库: {path}")
                continue
            if p.is_file() and not _is_image_path(str(p)):
                warnings.append(f"非图片文件，已跳过: {path}")
                continue
            try:
                report = library.ingest_local_images(str(p), max_images=1 if p.is_file() else max_n)
                ingest_reports.append(
                    {
                        "path": str(p),
                        "indexed": int(report.get("indexed", 0) or 0),
                        "duplicates": int(report.get("duplicates", 0) or 0),
                        "failed": int(report.get("failed", 0) or 0),
                        "total_candidates": int(report.get("total_candidates", 0) or 0),
                    }
                )
            except Exception as exc:
                warnings.append(f"图片入库失败 {path}: {exc}")

    try:
        search_limit = min(max(max_n, len(paths), 200), 8000)
        search_hits = library.search_assets(
            query="",
            limit=search_limit,
            offset=0,
            retrieval_mode=retrieval_mode,
            media_type="image",
        )
    except Exception as exc:
        search_hits = []
        warnings.append(f"媒体库检索失败: {exc}")

    hit_by_path: Dict[str, Dict[str, Any]] = {}
    for hit in search_hits or []:
        if not isinstance(hit, dict):
            continue
        path_text = str(hit.get("path") or "").strip()
        if not path_text:
            continue
        key = Path(path_text).expanduser().as_posix().lower()
        if key not in hit_by_path:
            hit_by_path[key] = hit

    items: List[Dict[str, Any]] = []
    for path in paths:
        key = Path(path).expanduser().as_posix().lower()
        hit = hit_by_path.get(key)
        if hit is not None:
            items.append(_normalize_search_hit(hit))
            continue

        # fallback by filename when path relocation happened in library
        fallback = None
        file_name = Path(path).name.lower()
        for one in search_hits or []:
            if not isinstance(one, dict):
                continue
            if str(one.get("filename") or "").strip().lower() == file_name:
                fallback = one
                break
        if fallback is not None:
            items.append(_normalize_search_hit(fallback))
            continue

        items.append(
            {
                "uid": "",
                "filename": Path(path).name,
                "path": path,
                "available": Path(path).exists(),
                "scene_description": "",
                "mood": "",
                "objects": [],
                "semantic_keywords": [],
                "semantic_tags": [],
                "quality_score": None,
                "match_score": None,
                "keyword_score": None,
                "vector_score": None,
            }
        )

    return {
        "input_count": len(paths),
        "analyzed_count": len(items),
        "items": items,
        "ingest_reports": ingest_reports,
        "warnings": warnings,
    }


def search_images(
    query: str,
    *,
    library: Optional[SupportsImageSemanticLibrary] = None,
    limit: int = 30,
    offset: int = 0,
    retrieval_mode: str = "hybrid",
) -> Dict[str, Any]:
    """Search image assets by semantic query."""
    q = str(query or "").strip()
    max_limit = max(min(int(limit or 30), 400), 1)
    start = max(int(offset or 0), 0)

    if library is None:
        return {
            "query": q,
            "limit": max_limit,
            "offset": start,
            "retrieval_mode": retrieval_mode,
            "hits": [],
            "warnings": ["未注入全局媒体库，无法执行语义检索"],
        }

    try:
        hits = library.search_assets(
            query=q,
            limit=max_limit,
            offset=start,
            retrieval_mode=str(retrieval_mode or "hybrid").strip().lower() or "hybrid",
            media_type="image",
        )
    except Exception as exc:
        return {
            "query": q,
            "limit": max_limit,
            "offset": start,
            "retrieval_mode": retrieval_mode,
            "hits": [],
            "warnings": [f"语义检索失败: {exc}"],
        }

    normalized_hits = [_normalize_search_hit(item) for item in hits if isinstance(item, dict)]
    return {
        "query": q,
        "limit": max_limit,
        "offset": start,
        "retrieval_mode": retrieval_mode,
        "hits": normalized_hits,
        "total_hits": len(normalized_hits),
        "warnings": [],
    }
