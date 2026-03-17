#!/usr/bin/env python3
"""
音频质量评分模块 — Audio Quality Scoring

对视频/音频进行音频质量分析，输出：
- SNR (信噪比) 估算
- 底噪电平
- 削波/clipping 比例
- 响度 (LUFS, 通过 FFmpeg loudnorm 获取)
- 动态范围
- 综合评分与等级

依赖：FFmpeg, numpy (可选：无 numpy 时降级为纯 FFmpeg 分析)

输出格式：
{
  "snr_db": 28.5,
  "noise_floor_db": -45.2,
  "clipping_ratio": 0.001,
  "loudness_lufs": -16.3,
  "peak_db": -1.2,
  "dynamic_range_db": 18.5,
  "quality_score": 0.82,
  "quality_level": "good",
  "issues": ["底噪略高"],
  "method": "ffmpeg+numpy"
}
"""

import json
import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def _extract_pcm(video_path: str, output_raw: str, timeout: int = 60) -> bool:
    """用 FFmpeg 提取 16-bit 单声道 PCM"""
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        "-f", "s16le", output_raw,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.returncode == 0 and os.path.exists(output_raw)
    except Exception as e:
        logger.warning("音频提取失败: %s — %s", video_path, e)
        return False


def _measure_loudness_ffmpeg(video_path: str) -> Dict[str, Any]:
    """用 FFmpeg loudnorm 第一遍扫描获取 LUFS / LRA / peak"""
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # loudnorm 输出在 stderr 末尾
        stderr = r.stderr or ""
        # 找到 JSON 块
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            info = json.loads(stderr[json_start:json_end])
            return {
                "input_i": float(info.get("input_i", -70)),
                "input_tp": float(info.get("input_tp", -70)),
                "input_lra": float(info.get("input_lra", 0)),
                "input_thresh": float(info.get("input_thresh", -70)),
            }
    except Exception as e:
        logger.warning("FFmpeg loudnorm 分析失败: %s", e)
    return {}


def _analyze_pcm_numpy(raw_path: str) -> Dict[str, Any]:
    """用 numpy 分析 PCM 数据：SNR / clipping / 动态范围"""
    data = np.fromfile(raw_path, dtype=np.int16).astype(np.float64)
    if len(data) < 1600:  # 不足 0.1 秒
        return {"error": "音频数据太短"}

    # 归一化到 [-1, 1]
    samples = data / 32768.0

    # 整体 RMS
    rms = np.sqrt(np.mean(samples ** 2))
    rms_db = 20 * math.log10(max(rms, 1e-10))

    # Peak
    peak = np.max(np.abs(samples))
    peak_db = 20 * math.log10(max(peak, 1e-10))

    # Clipping 比例（采样值 >= 0.99 视为削波）
    clipping_count = np.sum(np.abs(samples) >= 0.99)
    clipping_ratio = float(clipping_count) / len(samples)

    # 底噪估算：按 50ms 帧切分，取最安静的 10% 帧的 RMS 作为底噪
    frame_size = 800  # 50ms @ 16kHz
    num_frames = len(samples) // frame_size
    if num_frames < 5:
        noise_floor_db = rms_db - 20  # 粗略估算
    else:
        frame_rms = []
        for i in range(num_frames):
            frame = samples[i * frame_size : (i + 1) * frame_size]
            fr = np.sqrt(np.mean(frame ** 2))
            frame_rms.append(fr)
        frame_rms.sort()
        quiet_10pct = frame_rms[: max(1, num_frames // 10)]
        noise_rms = np.mean(quiet_10pct)
        noise_floor_db = 20 * math.log10(max(noise_rms, 1e-10))

    # SNR = RMS_signal - RMS_noise (dB)
    snr_db = rms_db - noise_floor_db

    # 动态范围 = peak - 底噪
    dynamic_range_db = peak_db - noise_floor_db

    return {
        "rms_db": round(rms_db, 1),
        "peak_db": round(peak_db, 1),
        "snr_db": round(max(snr_db, 0), 1),
        "noise_floor_db": round(noise_floor_db, 1),
        "clipping_ratio": round(clipping_ratio, 5),
        "dynamic_range_db": round(max(dynamic_range_db, 0), 1),
    }


def _compute_quality_score(metrics: Dict[str, Any]) -> tuple:
    """根据各指标计算综合评分和问题列表"""
    score = 0.0
    issues = []

    snr = metrics.get("snr_db", 0)
    noise = metrics.get("noise_floor_db", -60)
    clip = metrics.get("clipping_ratio", 0)
    lufs = metrics.get("loudness_lufs", -70)
    peak = metrics.get("peak_db", -70)

    # SNR 评分 (权重 35%)
    if snr >= 30:
        snr_score = 1.0
    elif snr >= 20:
        snr_score = 0.7 + (snr - 20) * 0.03
    elif snr >= 10:
        snr_score = 0.3 + (snr - 10) * 0.04
    else:
        snr_score = max(0, snr * 0.03)
        issues.append(f"信噪比过低 ({snr:.0f}dB)，建议使用外接麦克风或降噪")
    score += snr_score * 0.35

    # 底噪评分 (权重 20%)
    if noise <= -50:
        noise_score = 1.0
    elif noise <= -40:
        noise_score = 0.6 + (-noise - 40) * 0.04
    elif noise <= -30:
        noise_score = 0.2 + (-noise - 30) * 0.04
    else:
        noise_score = 0.0
        issues.append(f"底噪过高 ({noise:.0f}dB)，建议安静环境录制")
    score += noise_score * 0.20

    # 响度评分 (权重 20%) - 理想范围 -20 ~ -12 LUFS
    if -20 <= lufs <= -12:
        lufs_score = 1.0
    elif -24 <= lufs < -20:
        lufs_score = 0.7
    elif -28 <= lufs < -24:
        lufs_score = 0.4
        issues.append(f"响度偏低 ({lufs:.1f} LUFS)，建议后期增益")
    elif lufs < -28:
        lufs_score = 0.1
        issues.append(f"响度过低 ({lufs:.1f} LUFS)")
    elif lufs > -12:
        lufs_score = 0.5
        issues.append(f"响度偏高 ({lufs:.1f} LUFS)，可能产生失真")
    else:
        lufs_score = 0.5
    score += lufs_score * 0.20

    # 削波评分 (权重 15%)
    if clip < 0.0001:
        clip_score = 1.0
    elif clip < 0.001:
        clip_score = 0.7
    elif clip < 0.01:
        clip_score = 0.3
        issues.append(f"存在削波 ({clip * 100:.2f}%)，音频可能失真")
    else:
        clip_score = 0.0
        issues.append(f"严重削波 ({clip * 100:.1f}%)，音频失真明显")
    score += clip_score * 0.15

    # Peak 余量评分 (权重 10%)
    headroom = -peak  # peak_db 是负值，headroom 为正
    if headroom >= 3:
        head_score = 1.0
    elif headroom >= 1:
        head_score = 0.6
    else:
        head_score = 0.2
        issues.append("峰值接近 0dB，余量不足")
    score += head_score * 0.10

    score = round(min(max(score, 0), 1.0), 3)

    if score >= 0.8:
        level = "excellent"
    elif score >= 0.6:
        level = "good"
    elif score >= 0.4:
        level = "fair"
    else:
        level = "poor"

    return score, level, issues


def analyze_audio_quality(
    video_path: str,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    分析视频/音频的音频质量。

    Args:
        video_path: 视频或音频文件路径
        timeout: FFmpeg 超时时间

    Returns:
        音频质量评分结果
    """
    video_path = str(video_path)
    if not os.path.exists(video_path):
        return {"error": f"文件不存在: {video_path}", "quality_score": 0, "quality_level": "unknown"}

    metrics = {}
    method_parts = []

    # 1. FFmpeg loudnorm 测量 LUFS
    loudness = _measure_loudness_ffmpeg(video_path)
    if loudness:
        metrics["loudness_lufs"] = loudness.get("input_i", -70)
        metrics["loudness_lra"] = loudness.get("input_lra", 0)
        method_parts.append("ffmpeg_loudnorm")

    # 2. numpy PCM 分析（SNR / clipping / 动态范围）
    if HAS_NUMPY:
        tmp_dir = tempfile.mkdtemp(prefix="audio_quality_")
        raw_path = os.path.join(tmp_dir, "audio.raw")
        try:
            if _extract_pcm(video_path, raw_path, timeout=timeout):
                pcm_metrics = _analyze_pcm_numpy(raw_path)
                if "error" not in pcm_metrics:
                    metrics.update(pcm_metrics)
                    method_parts.append("numpy")
        finally:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # 3. 如果没有 numpy，用 loudnorm 数据粗略估算
    if "snr_db" not in metrics:
        if loudness:
            # 粗略估算：LUFS - threshold ≈ SNR
            est_snr = abs(loudness.get("input_i", -70) - loudness.get("input_thresh", -70))
            metrics["snr_db"] = round(min(est_snr, 60), 1)
            metrics["noise_floor_db"] = round(loudness.get("input_thresh", -60), 1)
            metrics["peak_db"] = round(loudness.get("input_tp", -70), 1)
            metrics["clipping_ratio"] = 0.01 if loudness.get("input_tp", -10) > -0.5 else 0.0
            metrics["dynamic_range_db"] = round(loudness.get("input_lra", 10), 1)
            method_parts.append("estimated")

    # 如果连 loudness_lufs 都没有（FFmpeg 也失败了），给默认值
    if "loudness_lufs" not in metrics:
        metrics["loudness_lufs"] = metrics.get("rms_db", -24)

    # 4. 计算综合评分
    score, level, issues = _compute_quality_score(metrics)
    metrics["quality_score"] = score
    metrics["quality_level"] = level
    metrics["issues"] = issues
    metrics["method"] = "+".join(method_parts) if method_parts else "unavailable"

    return metrics


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="音频质量评分")
    parser.add_argument("input", nargs="+", help="视频/音频文件")
    parser.add_argument("-o", "--output", default=None, help="输出 JSON 路径")
    args = parser.parse_args()

    results = {}
    for path in args.input:
        name = Path(path).name
        print(f"分析: {name}")
        result = analyze_audio_quality(path)
        results[name] = result
        print(f"  SNR: {result.get('snr_db', '?')}dB  LUFS: {result.get('loudness_lufs', '?')}  "
              f"Score: {result.get('quality_score', '?')} ({result.get('quality_level', '?')})")
        for issue in result.get("issues", []):
            print(f"  ⚠ {issue}")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存: {args.output}")
