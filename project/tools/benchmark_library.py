#!/usr/bin/env python3
"""Benchmark library ingest / search paths and emit acceptance report.

Usage::

    python tools/benchmark_library.py
    python tools/benchmark_library.py --iterations 20 --counts 10,50 --output docs/benchmark_library_report.json
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.benchmark_render_publish import _quantile, _ms_stats  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_asset(idx: int) -> Dict[str, Any]:
    """Return a minimal asset dict suitable for direct DB insert."""
    return {
        "uid": f"bench_{idx:06d}",
        "filename": f"clip_{idx:06d}.mp4",
        "sha256": f"bench_sha_{idx:06d}",
        "primary_path": f"/bench/videos/clip_{idx:06d}.mp4",
        "source_type": "local",
        "duration": 10.0 + (idx % 20),
        "resolution": "1920x1080",
        "quality_score": 70 + (idx % 25),
        "scene_description": f"Benchmark scene {idx}, outdoor landscape, blue sky",
        "size_bytes": 5_000_000 + idx * 1000,
    }


def _seed_library(gml, count: int) -> int:
    """Insert *count* synthetic assets. Returns number actually inserted."""
    now = gml._now()
    inserted = 0
    with gml._connect() as conn:
        for i in range(count):
            a = _make_fake_asset(i)
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO assets
                       (uid, filename, sha256, primary_path, source_type,
                        duration, resolution, quality_score, scene_description,
                        size_bytes, created_at, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        a["uid"], a["filename"], a["sha256"], a["primary_path"],
                        a["source_type"], a["duration"], a["resolution"],
                        a["quality_score"], a["scene_description"],
                        a["size_bytes"], now, now,
                    ),
                )
                inserted += 1
            except Exception:
                pass
        conn.commit()
    return inserted


# ---------------------------------------------------------------------------
# Benchmarks
# ---------------------------------------------------------------------------


def bench_search(gml, queries: List[str], iterations: int) -> Dict[str, Any]:
    costs: List[float] = []
    for _ in range(iterations):
        for q in queries:
            t0 = perf_counter()
            gml.search_assets(query=q, limit=50)
            costs.append((perf_counter() - t0) * 1000)
    return {"iterations": len(costs), "latency_ms": _ms_stats(costs)}


def bench_ingest_synthetic(counts: List[int]) -> Dict[str, Any]:
    """Benchmark direct DB insert (no real files) at various scales."""
    from modules.library.global_media_library import GlobalMediaLibrary

    results = {}
    for n in counts:
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "bench.db")
            gml = GlobalMediaLibrary(db_path=db)
            t0 = perf_counter()
            inserted = _seed_library(gml, n)
            elapsed = (perf_counter() - t0) * 1000
            per_item = elapsed / max(inserted, 1)
            results[f"ingest_{n}"] = {
                "count": n,
                "inserted": inserted,
                "total_ms": round(elapsed, 1),
                "per_item_ms": round(per_item, 1),
            }
    return results


def bench_search_at_scale(count: int, iterations: int) -> Dict[str, Any]:
    """Seed *count* assets then run search queries."""
    from modules.library.global_media_library import GlobalMediaLibrary

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "bench.db")
        gml = GlobalMediaLibrary(db_path=db)
        _seed_library(gml, count)
        queries = ["outdoor", "landscape", "clip", "scene 5", "blue sky"]
        return bench_search(gml, queries, iterations)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Benchmark library ingest/search")
    parser.add_argument("--iterations", type=int, default=10, help="Search iterations per query")
    parser.add_argument("--counts", default="10,100", help="Comma-separated ingest counts")
    parser.add_argument("--search-scale", type=int, default=100, help="Asset count for search bench")
    parser.add_argument("--output", default="docs/benchmark_library_report.json")
    args = parser.parse_args()

    counts = [int(x.strip()) for x in args.counts.split(",") if x.strip()]

    print(f"=== Library Benchmark (counts={counts}, search_scale={args.search_scale}, iters={args.iterations}) ===")

    print("  ingest benchmarks...")
    ingest_results = bench_ingest_synthetic(counts)
    for k, v in ingest_results.items():
        print(f"    {k}: {v['total_ms']:.1f}ms total, {v['per_item_ms']:.1f}ms/item")

    print("  search benchmarks...")
    search_results = bench_search_at_scale(args.search_scale, args.iterations)
    stats = search_results["latency_ms"]
    print(f"    {search_results['iterations']} queries: avg={stats['avg']:.1f}ms p50={stats['p50']:.1f}ms p95={stats['p95']:.1f}ms")

    # Acceptance thresholds (report only, not CI-blocking)
    acceptance = {
        "search_p95_ms": {"threshold": 500.0, "actual": stats["p95"]},
        "ingest_10_per_item_ms": {
            "threshold": 2000.0,
            "actual": ingest_results.get("ingest_10", {}).get("per_item_ms", 0),
        },
    }
    for k, v in acceptance.items():
        v["pass"] = v["actual"] <= v["threshold"]

    report = {
        "generated_at": datetime.now().isoformat(),
        "env": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "benchmarks": {
            "ingest": ingest_results,
            "search": search_results,
        },
        "acceptance": acceptance,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {out_path}")

    all_pass = all(v["pass"] for v in acceptance.values())
    print(f"Acceptance: {'ALL PASS' if all_pass else 'SOME FAILED (report only)'}")


if __name__ == "__main__":
    main()
