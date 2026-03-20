#!/usr/bin/env python3
"""
对已入库但没有 usability_score 的素材进行补评分。
用法: python tools/backfill_usability_scores.py --db-path <library.db>
      python tools/backfill_usability_scores.py --db-path <library.db> --dry-run
      python tools/backfill_usability_scores.py --db-path <library.db> --batch-size 200
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from modules.step1_material_analysis.usability_scorer import score_asset


def backfill(db_path: str, batch_size: int = 100, dry_run: bool = False):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT uid, duration, width, height, fps, codec, quality_score, phash,
               analysis_json
        FROM assets
        WHERE usability_score IS NULL
          AND analysis_json IS NOT NULL
        LIMIT ?
    """, (batch_size,)).fetchall()

    print(f"Found {len(rows)} assets to score")

    # 库级统计（一次性）
    total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    scene_rows = conn.execute("""
        SELECT json_extract(analysis_json, '$.semantic.scene_description'), COUNT(*)
        FROM assets WHERE analysis_json IS NOT NULL GROUP BY 1
    """).fetchall()
    library_stats = {
        "total_assets": total,
        "scene_type_counts": {r[0]: r[1] for r in scene_rows if r[0]},
        "similar_assets_count": 0,
    }

    updated = 0
    for row in rows:
        try:
            analysis = json.loads(row["analysis_json"]) if row["analysis_json"] else {}
            visual_stats = analysis.get("visual_stats", {})
            audio_info = analysis.get("audio_quality", None)

            tags = conn.execute(
                "SELECT tag_name, score, source FROM asset_tag_result WHERE asset_uid = ?",
                (row["uid"],)
            ).fetchall()
            tag_results = [{"tag_name": t[0], "score": t[1], "source": t[2]} for t in tags]

            result = score_asset(
                asset_row=dict(row),
                visual_stats=visual_stats,
                audio_info=audio_info,
                analysis_json=analysis,
                tag_results=tag_results,
                library_stats=library_stats,
            )

            if not dry_run:
                conn.execute("""
                    UPDATE assets SET
                        usability_score = ?,
                        usability_tier = ?,
                        material_type = ?,
                        trash_level = ?,
                        analysis_json = json_set(analysis_json, '$.quality_assessment', json(?))
                    WHERE uid = ?
                """, (
                    result["usability_score"],
                    result["usability_tier"],
                    result["material_type"],
                    result["trash_evaluation"]["trash_level"],
                    json.dumps(result, ensure_ascii=False),
                    row["uid"],
                ))
                updated += 1

            tier = result["usability_tier"]
            trash = result["trash_evaluation"]["trash_level"]
            print(f"  {row['uid'][:12]}... → {tier} ({result['usability_score']:.2f}) trash={trash}")

        except Exception as e:
            print(f"  {row['uid'][:12]}... ERROR: {e}")

    if not dry_run:
        conn.commit()
    conn.close()
    print(f"\nDone. Updated {updated}/{len(rows)} assets.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    backfill(args.db_path, args.batch_size, args.dry_run)
