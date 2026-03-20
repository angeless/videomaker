#!/usr/bin/env python3
"""Seed a minimal demo media library for local walkthrough.

Usage:
    python tools/seed_demo_library.py [--db-path PATH]

Creates 5 demo assets (3 video + 2 image) with realistic metadata,
tags, and one pair of near-duplicates for duplicate detection demo.

No real media files required — uses synthetic metadata only.
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules.library.global_media_library import GlobalMediaLibrary


def seed(db_path: str = None):
    if not db_path:
        lib_dir = ROOT / ".video_library"
        lib_dir.mkdir(exist_ok=True)
        db_path = str(lib_dir / "library.db")

    gml = GlobalMediaLibrary(db_path=db_path)
    now = gml._now()

    ASSETS = [
        {
            "uid": "demo_v1",
            "filename": "sunset_beach.mp4",
            "sha256": "demo_sha_sunset_beach_001",
            "primary_path": "/demo/videos/sunset_beach.mp4",
            "source_type": "local",
            "duration": 32.5,
            "resolution": "3840x2160",
            "quality_score": 92,
            "scene_description": "Golden hour beach scene, waves crashing, surfer silhouette against orange sky",
            "size_bytes": 85_000_000,
            "content_fingerprint": "ab" * 32,
        },
        {
            "uid": "demo_v2",
            "filename": "sunset_beach_v2.mp4",
            "sha256": "demo_sha_sunset_beach_002",
            "primary_path": "/demo/videos/sunset_beach_v2.mp4",
            "source_type": "local",
            "duration": 30.1,
            "resolution": "1920x1080",
            "quality_score": 78,
            "scene_description": "Beach sunset scene, similar angle, lower resolution export",
            "size_bytes": 42_000_000,
            "content_fingerprint": "ab" * 32,  # same fingerprint = near-duplicate
        },
        {
            "uid": "demo_v3",
            "filename": "city_timelapse.mp4",
            "sha256": "demo_sha_city_timelapse_003",
            "primary_path": "/demo/videos/city_timelapse.mp4",
            "source_type": "local",
            "duration": 18.0,
            "resolution": "3840x2160",
            "quality_score": 88,
            "scene_description": "City skyline timelapse, day to night transition, lights turning on",
            "size_bytes": 120_000_000,
            "content_fingerprint": "cd" * 32,
        },
        {
            "uid": "demo_i1",
            "filename": "mountain_lake.jpg",
            "sha256": "demo_sha_mountain_lake_004",
            "primary_path": "/demo/images/mountain_lake.jpg",
            "source_type": "local",
            "duration": 0,
            "resolution": "6000x4000",
            "quality_score": 95,
            "scene_description": "Crystal clear mountain lake reflecting snow-capped peaks, autumn foliage",
            "size_bytes": 12_000_000,
            "content_fingerprint": "ef" * 32,
        },
        {
            "uid": "demo_i2",
            "filename": "street_food.jpg",
            "sha256": "demo_sha_street_food_005",
            "primary_path": "/demo/images/street_food.jpg",
            "source_type": "local",
            "duration": 0,
            "resolution": "4032x3024",
            "quality_score": 82,
            "scene_description": "Night market street food stall, steam rising, colorful neon lights",
            "size_bytes": 8_500_000,
            "content_fingerprint": "11" * 32,
        },
    ]

    with gml._connect() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        if existing > 0:
            print(f"Library already has {existing} assets. Skipping seed.")
            return

        for a in ASSETS:
            conn.execute(
                """INSERT INTO assets
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
            # Set content_fingerprint
            try:
                conn.execute(
                    "UPDATE assets SET content_fingerprint = ? WHERE uid = ?",
                    (a["content_fingerprint"], a["uid"]),
                )
            except Exception:
                pass

            conn.execute(
                """INSERT INTO asset_locations
                   (uid, path, source_type, is_available, last_seen_at)
                   VALUES (?,?,?,?,?)""",
                (a["uid"], a["primary_path"], a["source_type"], 1, now),
            )

    print(f"Seeded {len(ASSETS)} demo assets into {db_path}")
    print("  3 videos (sunset_beach, sunset_beach_v2, city_timelapse)")
    print("  2 images (mountain_lake, street_food)")
    print("  1 duplicate pair (sunset_beach + sunset_beach_v2)")

    # Create a minimal Jianying draft for relink demo
    demo_dir = ROOT / "demo"
    demo_dir.mkdir(exist_ok=True)
    draft = {
        "materials": {
            "videos": [
                {"id": "mat_v1", "path": "/old/moved/sunset_beach.mp4"},
                {"id": "mat_v2", "path": "/old/moved/city_timelapse.mp4"},
                {"id": "mat_v3", "path": "/missing/deleted_clip.mp4"},
            ],
            "audios": [],
        },
        "tracks": [],
    }
    draft_path = demo_dir / "draft_content.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDemo Jianying draft: {draft_path}")
    print("  2 relink-able refs (sunset_beach, city_timelapse)")
    print("  1 missing ref (deleted_clip)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo media library")
    parser.add_argument("--db-path", help="SQLite database path (default: .video_library/library.db)")
    args = parser.parse_args()
    seed(args.db_path)
