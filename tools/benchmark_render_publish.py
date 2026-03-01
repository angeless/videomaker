#!/usr/bin/env python3
"""Benchmark render/publish capability paths and emit acceptance report."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Dict, List
import json
import platform
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.capabilities.content_publish import (
    bootstrap_publish_session,
    build_publish_plan,
    run_publish_plan,
)
from modules.capabilities.social_export import build_export_plan


def _quantile(sorted_values: List[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if q <= 0:
        return sorted_values[0]
    if q >= 1:
        return sorted_values[-1]
    idx = (len(sorted_values) - 1) * q
    low = int(idx)
    high = min(low + 1, len(sorted_values) - 1)
    frac = idx - low
    return (sorted_values[low] * (1 - frac)) + (sorted_values[high] * frac)


def _ms_stats(samples: List[float]) -> Dict[str, float]:
    values = sorted(float(x) for x in samples if float(x) >= 0)
    if not values:
        return {"count": 0, "min": 0.0, "max": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0}
    return {
        "count": len(values),
        "min": round(values[0], 3),
        "max": round(values[-1], 3),
        "avg": round(mean(values), 3),
        "p50": round(_quantile(values, 0.5), 3),
        "p95": round(_quantile(values, 0.95), 3),
    }


def _run_export_plan_bench(iterations: int, input_video: str, output_dir: str, platforms: List[str]) -> Dict[str, Any]:
    costs: List[float] = []
    sample_jobs = 0
    for _ in range(iterations):
        start = perf_counter()
        plan = build_export_plan(
            input_video=input_video,
            output_dir=output_dir,
            platform_ids=platforms,
            quality="high",
            strict_duration_limit=True,
        )
        elapsed_ms = (perf_counter() - start) * 1000.0
        costs.append(elapsed_ms)
        sample_jobs = max(sample_jobs, len(plan.get("jobs", [])))
    return {
        "iterations": iterations,
        "platforms": list(platforms),
        "sample_jobs": sample_jobs,
        "latency_ms": _ms_stats(costs),
    }


def _run_publish_dry_bench(iterations: int) -> Dict[str, Any]:
    content = {
        "title": "旅行短片：雪山云海",
        "description": "今天带你看雪山云海和公路风光。",
        "keywords": ["旅行", "雪山", "公路片"],
    }
    session = bootstrap_publish_session(actor_id="bench", authenticated=True)
    costs_plan: List[float] = []
    costs_run: List[float] = []

    for _ in range(iterations):
        t0 = perf_counter()
        plan = build_publish_plan(
            content=content,
            platform_ids=["douyin", "youtube", "blog"],
            platform_content_type="video_post",
            dry_run=True,
            session=session,
        )
        costs_plan.append((perf_counter() - t0) * 1000.0)

        t1 = perf_counter()
        run_publish_plan(
            plan=plan,
            session=session,
            dry_run=True,
            random_seed=7,
        )
        costs_run.append((perf_counter() - t1) * 1000.0)

    return {
        "iterations": iterations,
        "plan_latency_ms": _ms_stats(costs_plan),
        "run_latency_ms": _ms_stats(costs_run),
    }


def _run_publish_live_blog_bench(iterations: int, output_root: str) -> Dict[str, Any]:
    content = {
        "title": "旅行周报",
        "description": "本周素材精选与路线建议。",
        "keywords": ["旅行", "路线", "周报"],
    }
    session = bootstrap_publish_session(actor_id="bench_live", authenticated=True)
    costs: List[float] = []

    for _ in range(iterations):
        plan = build_publish_plan(
            content=content,
            platform_ids=["blog"],
            platform_content_type="article_post",
            dry_run=False,
            session=session,
        )
        t0 = perf_counter()
        result = run_publish_plan(
            plan=plan,
            session=session,
            dry_run=False,
            random_seed=7,
            output_root=output_root,
        )
        costs.append((perf_counter() - t0) * 1000.0)
        if result.get("status") not in {"posted", "failed", "blocked", "waiting_auth"}:
            raise RuntimeError(f"unexpected publish status: {result.get('status')}")

    return {
        "iterations": iterations,
        "run_latency_ms": _ms_stats(costs),
        "output_root": output_root,
    }


def _evaluate_acceptance(report: Dict[str, Any]) -> Dict[str, Any]:
    thresholds = {
        "export_plan_p95_ms": 250.0,
        "publish_dry_plan_p95_ms": 120.0,
        "publish_dry_run_p95_ms": 80.0,
        "publish_live_blog_p95_ms": 220.0,
    }

    export_p95 = float(report["benchmarks"]["social_export_plan"]["latency_ms"]["p95"])
    dry_plan_p95 = float(report["benchmarks"]["content_publish_dry"]["plan_latency_ms"]["p95"])
    dry_run_p95 = float(report["benchmarks"]["content_publish_dry"]["run_latency_ms"]["p95"])
    live_section = report["benchmarks"].get("content_publish_live_blog")
    live_p95 = float(live_section["run_latency_ms"]["p95"]) if isinstance(live_section, dict) else 0.0

    checks = {
        "export_plan_p95_ms": export_p95 <= thresholds["export_plan_p95_ms"],
        "publish_dry_plan_p95_ms": dry_plan_p95 <= thresholds["publish_dry_plan_p95_ms"],
        "publish_dry_run_p95_ms": dry_run_p95 <= thresholds["publish_dry_run_p95_ms"],
    }
    if isinstance(live_section, dict):
        checks["publish_live_blog_p95_ms"] = live_p95 <= thresholds["publish_live_blog_p95_ms"]

    return {
        "pass": all(checks.values()),
        "thresholds": thresholds,
        "checks": checks,
        "measured": {
            "export_plan_p95_ms": round(export_p95, 3),
            "publish_dry_plan_p95_ms": round(dry_plan_p95, 3),
            "publish_dry_run_p95_ms": round(dry_run_p95, 3),
            "publish_live_blog_p95_ms": round(live_p95, 3) if isinstance(live_section, dict) else None,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark render/publish paths")
    parser.add_argument("--iterations", type=int, default=20, help="benchmark iterations per scenario")
    parser.add_argument(
        "--platforms",
        default="douyin,xiaohongshu,youtube",
        help="comma separated social export platforms",
    )
    parser.add_argument(
        "--output",
        default="docs/benchmark_render_publish_report.json",
        help="output report path",
    )
    parser.add_argument(
        "--include-live-blog",
        action="store_true",
        help="include non-dry-run benchmark for built-in blog publish",
    )
    args = parser.parse_args()

    iterations = max(3, int(args.iterations or 20))
    platforms = [x.strip() for x in str(args.platforms or "").replace("，", ",").split(",") if x.strip()]
    if not platforms:
        platforms = ["douyin", "xiaohongshu", "youtube"]

    with tempfile.TemporaryDirectory(prefix="videoeditor_bench_") as td:
        temp_root = Path(td)
        input_video = temp_root / "sample_input.mp4"
        input_video.write_bytes(b"fake")
        export_out = temp_root / "social_exports"
        publish_out = temp_root / "publish"

        report: Dict[str, Any] = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "env": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "iterations": iterations,
            },
            "benchmarks": {
                "social_export_plan": _run_export_plan_bench(
                    iterations=iterations,
                    input_video=str(input_video),
                    output_dir=str(export_out),
                    platforms=platforms,
                ),
                "content_publish_dry": _run_publish_dry_bench(iterations=iterations),
            },
        }

        if args.include_live_blog:
            report["benchmarks"]["content_publish_live_blog"] = _run_publish_live_blog_bench(
                iterations=iterations,
                output_root=str(publish_out),
            )

    report["acceptance"] = _evaluate_acceptance(report)

    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[benchmark] report saved: {output_path}")
    print(f"[benchmark] acceptance pass: {report['acceptance']['pass']}")
    print(f"[benchmark] measured: {json.dumps(report['acceptance']['measured'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
