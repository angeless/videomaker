#!/usr/bin/env python3
"""Audit coverage tracker for VideoEditor.

Maintains ``docs/audit/coverage.json`` — a machine-readable registry of
every source file's audit state. Works as a lightweight ledger: each
audit round marks files as scanned or fixed, with the round number and
commit hash recorded. This lets us answer "have we actually audited
file X yet?" without relying on anyone's memory.

Status values:
  unaudited        — never scanned in any round
  scanned          — agent read it, found no actionable issues
  audited_fixed    — agent found bugs, fixed + committed
  skip             — generated / third-party / __init__.py stub / exempt

Usage:
  python3 scripts/audit_coverage.py status
      Show aggregate coverage stats.

  python3 scripts/audit_coverage.py list [--status STATUS] [--priority P0|P1|P2]
      List files matching filter, one per line.

  python3 scripts/audit_coverage.py mark <file> <status> [--round N] [--commit HASH] [--note TEXT]
      Update a file's entry.

  python3 scripts/audit_coverage.py bootstrap
      Populate the registry from git history since v0.18.0 baseline.

The registry file is checked into git. Every audit PR should include
its update.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Repo root is the project/ directory two levels above this script
ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "docs" / "audit" / "coverage.json"
BASELINE_COMMIT = "da9e73c"  # v0.18.0 release — anything after this is audit work
VALID_STATUSES = {"unaudited", "scanned", "audited_fixed", "skip"}

# Priority tiers — aligns with the round-11 recommendation
PRIORITY_PATTERNS: Dict[str, List[str]] = {
    "P0": [
        "modules/app_api/services/",
        "modules/subscription/",
        "modules/mcp_server/tools/",
        "modules/app_api/middleware/",
    ],
    "P1": [
        "modules/library/",
        "modules/step1_material_analysis/",
    ],
    "P2": [
        "modules/render_engine/",
        "modules/adapters/",
        "modules/step3_script_generation/",
        "modules/step4_material_matching/",
        "modules/step6_rough_cut/",
        "modules/step2_topic_planning/",
        "modules/step5_preview_generation/",
        "modules/step7_final_render/",
        "modules/hardware/",
        "modules/workflow_engine/",
        "modules/job_system/",
        "modules/capabilities/",
        "modules/review_engine/",
    ],
}


def enumerate_source_files() -> List[Path]:
    """All .py, .vue, .js files under modules/ and apps/desktop/ui-vue/src/."""
    roots = [
        ROOT / "modules",
        ROOT / "apps" / "desktop" / "ui-vue" / "src",
    ]
    files: List[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for ext in ("*.py", "*.vue", "*.js"):
            files.extend(p for p in root.rglob(ext) if "__pycache__" not in p.parts)
    return sorted(files)


def priority_for(rel_path: str) -> str:
    """Classify a file path into P0/P1/P2/other."""
    for tier in ("P0", "P1", "P2"):
        for prefix in PRIORITY_PATTERNS[tier]:
            if rel_path.startswith(prefix):
                return tier
    return "other"


def load_registry() -> dict:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return {
        "version": "1.0",
        "baseline_commit": BASELINE_COMMIT,
        "files": {},
    }


def save_registry(reg: dict) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    reg["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    REGISTRY_PATH.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n")


def git_files_modified_since(baseline: str) -> List[str]:
    """All tracked source files modified since baseline commit."""
    try:
        result = subprocess.run(
            ["git", "log", f"{baseline}..HEAD", "--pretty=format:", "--name-only"],
            cwd=ROOT.parent,  # run at repo root, not project/
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError:
        return []
    paths = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        # Only keep modules/apps source files within project/
        if not line.startswith("project/"):
            continue
        rel = line[len("project/"):]
        if (rel.startswith("modules/") or rel.startswith("apps/")) and any(
            rel.endswith(ext) for ext in (".py", ".vue", ".js")
        ):
            paths.add(rel)
    return sorted(paths)


def git_last_commit_for(rel_path: str, baseline: str) -> Optional[str]:
    """Return the most recent commit hash that modified rel_path since baseline."""
    try:
        full_path = f"project/{rel_path}"
        result = subprocess.run(
            ["git", "log", f"{baseline}..HEAD", "-n", "1", "--pretty=format:%h", "--", full_path],
            cwd=ROOT.parent, capture_output=True, text=True, check=True,
        )
        out = result.stdout.strip()
        return out if out else None
    except subprocess.CalledProcessError:
        return None


def cmd_bootstrap(args) -> None:
    """Populate registry from current filesystem + git history."""
    reg = load_registry()
    reg.setdefault("files", {})
    all_files = enumerate_source_files()
    modified = set(git_files_modified_since(BASELINE_COMMIT))

    added = 0
    bumped = 0
    for f in all_files:
        rel = str(f.relative_to(ROOT))
        entry = reg["files"].get(rel)
        # Classify __init__.py as skip by default unless already marked
        default_status = "skip" if f.name == "__init__.py" else "unaudited"
        if entry is None:
            status = "audited_fixed" if rel in modified else default_status
            commit = git_last_commit_for(rel, BASELINE_COMMIT) if status == "audited_fixed" else None
            reg["files"][rel] = {
                "priority": priority_for(rel),
                "status": status,
                "rounds": [],
                "commits": [commit] if commit else [],
                "note": "auto-bootstrapped from git history" if status == "audited_fixed"
                        else ("__init__.py stub" if default_status == "skip" else ""),
            }
            added += 1
        elif rel in modified and entry.get("status") == "unaudited":
            # Someone fixed it but registry was stale
            entry["status"] = "audited_fixed"
            commit = git_last_commit_for(rel, BASELINE_COMMIT)
            if commit and commit not in entry.get("commits", []):
                entry.setdefault("commits", []).append(commit)
            bumped += 1

    save_registry(reg)
    print(f"Bootstrap complete. Added {added} new entries, bumped {bumped} stale entries.")


def cmd_status(args) -> None:
    reg = load_registry()
    files = reg.get("files", {})
    by_status: Dict[str, int] = {}
    by_priority_status: Dict[str, Dict[str, int]] = {"P0": {}, "P1": {}, "P2": {}, "other": {}}
    for rel, entry in files.items():
        s = entry.get("status", "unaudited")
        p = entry.get("priority", "other")
        by_status[s] = by_status.get(s, 0) + 1
        by_priority_status[p][s] = by_priority_status[p].get(s, 0) + 1

    total = len(files)
    audited = sum(v for k, v in by_status.items() if k in ("scanned", "audited_fixed"))
    print(f"Audit Coverage — {total} total source files")
    print(f"  Baseline: {reg.get('baseline_commit', '?')}")
    print(f"  Last updated: {reg.get('last_updated', 'never')}")
    print()
    print("By status:")
    for s in ("audited_fixed", "scanned", "unaudited", "skip"):
        n = by_status.get(s, 0)
        pct = (n * 100 / total) if total else 0
        print(f"  {s:16s} {n:4d}  ({pct:5.1f}%)")
    print()
    print(f"Audited (fixed or scanned): {audited}/{total} = {audited*100/total:.1f}%")
    print()
    print("By priority × status:")
    print(f"  {'':<10} {'fixed':>7} {'scanned':>7} {'unaud':>7} {'skip':>7} {'total':>7}")
    for p in ("P0", "P1", "P2", "other"):
        row = by_priority_status[p]
        total_p = sum(row.values())
        print(f"  {p:<10} {row.get('audited_fixed',0):>7} {row.get('scanned',0):>7} "
              f"{row.get('unaudited',0):>7} {row.get('skip',0):>7} {total_p:>7}")


def cmd_list(args) -> None:
    reg = load_registry()
    for rel, entry in sorted(reg.get("files", {}).items()):
        if args.status and entry.get("status") != args.status:
            continue
        if args.priority and entry.get("priority") != args.priority:
            continue
        print(rel)


def cmd_mark(args) -> None:
    reg = load_registry()
    rel = args.file
    files = reg.setdefault("files", {})
    entry = files.setdefault(rel, {
        "priority": priority_for(rel),
        "status": "unaudited",
        "rounds": [],
        "commits": [],
        "note": "",
    })
    if args.status not in VALID_STATUSES:
        sys.exit(f"invalid status {args.status!r}; choose from {VALID_STATUSES}")
    entry["status"] = args.status
    if args.round is not None:
        rounds = entry.setdefault("rounds", [])
        if args.round not in rounds:
            rounds.append(args.round)
            rounds.sort()
    if args.commit:
        commits = entry.setdefault("commits", [])
        if args.commit not in commits:
            commits.append(args.commit)
    if args.note:
        entry["note"] = args.note
    save_registry(reg)
    print(f"Marked {rel} → {args.status}")


def main() -> None:
    p = argparse.ArgumentParser(description="Audit coverage tracker")
    sp = p.add_subparsers(dest="cmd", required=True)

    sp.add_parser("bootstrap", help="Populate registry from filesystem + git history")
    sp.add_parser("status", help="Show coverage stats")

    pl = sp.add_parser("list", help="List files matching filter")
    pl.add_argument("--status", help="Filter by status")
    pl.add_argument("--priority", choices=("P0", "P1", "P2", "other"))

    pm = sp.add_parser("mark", help="Update a file's audit status")
    pm.add_argument("file")
    pm.add_argument("status", choices=sorted(VALID_STATUSES))
    pm.add_argument("--round", type=int)
    pm.add_argument("--commit")
    pm.add_argument("--note")

    args = p.parse_args()
    {"bootstrap": cmd_bootstrap, "status": cmd_status,
     "list": cmd_list, "mark": cmd_mark}[args.cmd](args)


if __name__ == "__main__":
    main()
