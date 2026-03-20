#!/usr/bin/env python3
"""
批量分析加拿大素材 — 视觉分析 + 语音转录
输出: analyzed_videos.json (含每个视频的视觉特征、场景分类、转录文本)
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from modules.step1_material_analysis.video_asset_toolkit import VideoAssetToolkit
from modules.step1_material_analysis.transcribe import transcribe_video

SRC_DIR = Path("/Users/angelwang/Documents/1128 百度盘备份 加拿大心酸史")
OUTPUT_PATH = ROOT / "output_canada_video" / "analyzed_videos.json"


def get_video_duration(path: str) -> float:
    """用 ffprobe 获取视频时长"""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(path)],
            capture_output=True, text=True, timeout=10
        )
        return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        return 0


def main():
    # 收集所有 MOV/MP4 文件
    videos = sorted(SRC_DIR.glob("*.MOV")) + sorted(SRC_DIR.glob("*.mp4"))
    print(f"找到 {len(videos)} 个视频文件")

    # 过滤: 只处理 > 3 秒的视频 (跳过 Live Photo 等短片)
    valid_videos = []
    print("检查视频时长...")
    for v in videos:
        dur = get_video_duration(str(v))
        if dur > 3.0:
            valid_videos.append((v, dur))

    print(f"有效视频 (>3s): {len(valid_videos)} 个")
    total_dur = sum(d for _, d in valid_videos)
    print(f"总时长: {total_dur:.0f}s ({total_dur/60:.1f} min)")

    # 初始化分析工具
    toolkit = VideoAssetToolkit()

    # 如果已有部分结果, 加载继续
    existing = {}
    if OUTPUT_PATH.exists():
        try:
            existing = json.load(open(OUTPUT_PATH, "r", encoding="utf-8"))
            print(f"已有 {len(existing)} 个视频分析结果，将跳过已完成的")
        except Exception:
            pass

    results = dict(existing)

    for i, (vpath, dur) in enumerate(valid_videos):
        fname = vpath.name

        # 跳过已分析的
        if fname in results and results[fname].get("transcription", {}).get("has_speech") is not None:
            logger.info("[%d/%d] 跳过 (已完成): %s", i+1, len(valid_videos), fname)
            continue

        logger.info("[%d/%d] 分析: %s (%.1fs)", i+1, len(valid_videos), fname, dur)

        # 1. 视觉分析
        try:
            visual = toolkit.local_analysis(vpath)
        except Exception as e:
            logger.warning("  视觉分析失败: %s", e)
            visual = {}

        # 2. 元数据
        try:
            metadata = toolkit.extract_metadata(vpath)
        except Exception as e:
            logger.warning("  元数据提取失败: %s", e)
            metadata = {}

        # 3. 语音转录 (medium 模型, 最多转录前 120 秒)
        try:
            transcript = transcribe_video(
                str(vpath),
                model_size="medium",
                max_duration=min(dur, 120),
            )
        except Exception as e:
            logger.warning("  转录失败: %s", e)
            transcript = {"has_speech": False, "transcript": "", "segments": []}

        # 提取关键特征用于分类
        scene = visual.get("scene", {})
        objects = visual.get("objects", {})
        tech = visual.get("technical", {})
        vis_feat = scene.get("visual_features", {})

        # 分类: scenery vs person vs mixed
        face_ratio = vis_feat.get("face_ratio", 0)
        if face_ratio < 0.05:
            content_type = "scenery"
        elif face_ratio > 0.5:
            content_type = "person"
        else:
            content_type = "mixed"

        results[fname] = {
            "path": str(vpath),
            "duration": round(dur, 1),
            "content_type": content_type,
            "face_ratio": round(face_ratio, 3),
            "scene_description": scene.get("description", ""),
            "mood": scene.get("mood", ""),
            "detected_objects": objects.get("detected_objects", []),
            "quality_level": tech.get("quality_level", ""),
            "resolution": tech.get("resolution", ""),
            "visual_features": vis_feat,
            "transcription": {
                "has_speech": transcript.get("has_speech", False),
                "transcript": transcript.get("transcript", ""),
                "segments": transcript.get("segments", []),
                "language": transcript.get("language", ""),
                "speech_ratio": transcript.get("speech_ratio", 0),
            },
            "metadata": {
                "creation_time": metadata.get("tags", {}).get("creation_time", ""),
                "location": metadata.get("location", None),
                "has_audio": bool(metadata.get("audio_streams")),
            },
        }

        # 简要输出
        speech_info = ""
        if transcript.get("has_speech"):
            text = transcript.get("transcript", "")[:50]
            speech_info = f" | 语音: {text}..."
        logger.info("  ✓ %s | %s | face=%.2f%s",
                     fname, content_type, face_ratio, speech_info)

        # 每 5 个视频保存一次进度
        if (i + 1) % 5 == 0:
            with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info("  [进度已保存: %d/%d]", i+1, len(valid_videos))

    # 最终保存
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 统计
    scenery = sum(1 for r in results.values() if r.get("content_type") == "scenery")
    person = sum(1 for r in results.values() if r.get("content_type") == "person")
    mixed = sum(1 for r in results.values() if r.get("content_type") == "mixed")
    has_speech = sum(1 for r in results.values() if r.get("transcription", {}).get("has_speech"))

    print(f"\n{'='*60}")
    print(f"分析完成! 结果保存到: {OUTPUT_PATH}")
    print(f"总视频: {len(results)}")
    print(f"  风景空镜: {scenery}")
    print(f"  人物特写: {person}")
    print(f"  混合: {mixed}")
    print(f"  有语音: {has_speech}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
