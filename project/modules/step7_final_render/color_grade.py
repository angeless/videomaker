#!/usr/bin/env python3
"""
视频调色 / 曝光统一模块 — Color Grading & Exposure Normalization

功能：
1. 分析视频片段的亮度/对比度/白平衡
2. 计算参考基准（多段统一时取中位数）
3. 逐帧做亮度/对比度/色温修正，使多段视频视觉一致
4. 可选 LUT 风格化调色

两种模式：
- cv2 逐帧处理（精细，需 opencv + numpy）
- FFmpeg 滤镜链（快速，无额外依赖）

依赖：opencv-python, numpy (可选：无时降级为 FFmpeg)
"""

import logging
import math
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from modules.render_engine.concat_utils import safe_ffmpeg_arg

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


# ── 视频色彩分析 ──────────────────────────────────────────────

def analyze_clip_color(video_path: str, sample_frames: int = 10) -> Dict[str, Any]:
    """
    分析视频片段的色彩特性。

    Returns:
        {
          "brightness": float,     # 平均亮度 [0,1]
          "contrast": float,       # 标准差
          "color_temp": float,     # 色温偏移 (>0 暖, <0 冷)
          "gamma_est": float,      # 估算 gamma 值
          "r_mean": float,
          "g_mean": float,
          "b_mean": float,
        }
    """
    if not HAS_CV2:
        return _analyze_clip_ffmpeg(video_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return {"error": "无法打开视频", "brightness": 0.5}

    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            total = sample_frames

        indexes = sorted(set(
            int(x) for x in np.linspace(0, max(total - 1, 0), num=min(sample_frames, max(total, 1)))
        ))

        bri_list = []
        con_list = []
        r_list, g_list, b_list = [], [], []

        for idx in indexes:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue

            # 亮度 & 对比度（Y 通道）
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float64) / 255.0
            bri_list.append(float(np.mean(gray)))
            con_list.append(float(np.std(gray)))

            # 颜色通道均值
            b_mean, g_mean, r_mean, _ = cv2.mean(frame)
            r_list.append(r_mean / 255.0)
            g_list.append(g_mean / 255.0)
            b_list.append(b_mean / 255.0)
    finally:
        cap.release()

    if not bri_list:
        return {"error": "未能读取帧", "brightness": 0.5}

    brightness = float(np.mean(bri_list))
    contrast = float(np.mean(con_list))
    r_m = float(np.mean(r_list))
    g_m = float(np.mean(g_list))
    b_m = float(np.mean(b_list))

    # 色温 = R - B 偏移
    color_temp = r_m - b_m

    # Gamma 估算: 若平均亮度偏低/偏高，推算 gamma
    gamma_est = 1.0
    if 0.01 < brightness < 0.99:
        gamma_est = math.log(0.5) / math.log(max(brightness, 0.01))
        gamma_est = max(0.3, min(gamma_est, 3.0))

    return {
        "brightness": round(brightness, 4),
        "contrast": round(contrast, 4),
        "color_temp": round(color_temp, 4),
        "gamma_est": round(gamma_est, 3),
        "r_mean": round(r_m, 4),
        "g_mean": round(g_m, 4),
        "b_mean": round(b_m, 4),
    }


def _analyze_clip_ffmpeg(video_path: str) -> Dict[str, Any]:
    """降级版：用 FFmpeg signalstats 获取基础亮度"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", safe_ffmpeg_arg(str(video_path)),
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=10)
    except Exception:
        pass
    # FFmpeg 方式只返回默认值，精确分析需 cv2
    return {
        "brightness": 0.5,
        "contrast": 0.2,
        "color_temp": 0.0,
        "gamma_est": 1.0,
        "r_mean": 0.33,
        "g_mean": 0.33,
        "b_mean": 0.33,
        "method": "ffmpeg_fallback",
    }


# ── 参考基准计算 ──────────────────────────────────────────────

def compute_reference_profile(
    clip_analyses: List[Dict[str, Any]],
) -> Dict[str, float]:
    """
    从多段视频的分析结果计算参考基准（中位数）。
    用于统一调色的目标值。
    """
    if not clip_analyses:
        return {"brightness": 0.5, "contrast": 0.2, "color_temp": 0.0, "gamma_target": 1.0}

    bris = [c["brightness"] for c in clip_analyses if "brightness" in c]
    cons = [c["contrast"] for c in clip_analyses if "contrast" in c]
    temps = [c["color_temp"] for c in clip_analyses if "color_temp" in c]

    return {
        "brightness": round(float(np.median(bris)) if HAS_CV2 and bris else 0.5, 4),
        "contrast": round(float(np.median(cons)) if HAS_CV2 and cons else 0.2, 4),
        "color_temp": round(float(np.median(temps)) if HAS_CV2 and temps else 0.0, 4),
        "gamma_target": 1.0,
    }


# ── 逐帧调色（cv2 模式） ─────────────────────────────────────

def _adjust_frame(
    frame: "np.ndarray",
    brightness_shift: float,
    contrast_scale: float,
    temp_shift: float,
    gamma: float,
) -> "np.ndarray":
    """
    对单帧做亮度/对比度/色温/gamma 修正。

    Args:
        frame: BGR uint8 图像
        brightness_shift: 亮度偏移 [-0.5, 0.5]（加到归一化值上）
        contrast_scale: 对比度缩放 [0.5, 2.0]（1.0=不变）
        temp_shift: 色温偏移（>0 暖, <0 冷），调整 R/B 通道
        gamma: Gamma 校正值（<1 提亮暗部, >1 压暗）
    """
    result = frame.astype(np.float64) / 255.0

    # 1. 亮度偏移
    if abs(brightness_shift) > 0.005:
        result += brightness_shift

    # 2. 对比度（以 0.5 为中心缩放）
    if abs(contrast_scale - 1.0) > 0.01:
        result = (result - 0.5) * contrast_scale + 0.5

    # 3. 色温偏移（调 R 和 B 通道）
    if abs(temp_shift) > 0.005:
        result[:, :, 2] += temp_shift * 0.5   # R 通道
        result[:, :, 0] -= temp_shift * 0.5   # B 通道

    # 4. Gamma 校正
    if abs(gamma - 1.0) > 0.01:
        result = np.clip(result, 0, 1)
        result = np.power(result, 1.0 / max(gamma, 0.1))

    return np.clip(result * 255, 0, 255).astype(np.uint8)


def grade_video_cv2(
    input_path: str,
    output_path: str,
    clip_analysis: Dict[str, Any],
    reference: Dict[str, float],
) -> str:
    """
    用 cv2 逐帧调色，使片段色彩匹配参考基准。

    Args:
        input_path: 输入视频路径
        output_path: 输出视频路径
        clip_analysis: analyze_clip_color() 的输出
        reference: compute_reference_profile() 的输出

    Returns:
        输出路径
    """
    if not HAS_CV2:
        return grade_video_ffmpeg(input_path, output_path, clip_analysis, reference)

    bri_shift = reference["brightness"] - clip_analysis.get("brightness", 0.5)
    # 限制调整幅度，避免过曝/欠曝
    bri_shift = max(-0.15, min(0.15, bri_shift))

    ref_con = reference.get("contrast", 0.2)
    cur_con = clip_analysis.get("contrast", 0.2)
    contrast_scale = ref_con / max(cur_con, 0.01) if cur_con > 0.01 else 1.0
    contrast_scale = max(0.7, min(1.5, contrast_scale))

    temp_shift = reference.get("color_temp", 0) - clip_analysis.get("color_temp", 0)
    temp_shift = max(-0.08, min(0.08, temp_shift))

    gamma = clip_analysis.get("gamma_est", 1.0)
    if abs(gamma - 1.0) < 0.1:
        gamma = 1.0

    cap = cv2.VideoCapture(str(input_path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

        try:
            max_frames = max(total * 2, int(fps * 600)) if total > 0 else int(fps * 600)
            processed = 0
            while processed < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                graded = _adjust_frame(frame, bri_shift, contrast_scale, temp_shift, gamma)
                out.write(graded)
                processed += 1
                if processed % 60 == 0:
                    logger.info("调色进度: %d/%d", processed, total)
        finally:
            out.release()
    finally:
        cap.release()

    logger.info("调色完成: %s", output_path)
    return output_path


# ── FFmpeg 调色（降级模式） ───────────────────────────────────

def grade_video_ffmpeg(
    input_path: str,
    output_path: str,
    clip_analysis: Dict[str, Any],
    reference: Dict[str, float],
) -> str:
    """
    用 FFmpeg eq + colorbalance 滤镜调色。
    不依赖 cv2，速度更快但精度略低。
    """
    bri_shift = reference.get("brightness", 0.5) - clip_analysis.get("brightness", 0.5)
    bri_shift = max(-0.15, min(0.15, bri_shift))

    ref_con = reference.get("contrast", 0.2)
    cur_con = clip_analysis.get("contrast", 0.2)
    contrast_scale = ref_con / max(cur_con, 0.01) if cur_con > 0.01 else 1.0
    contrast_scale = max(0.7, min(1.5, contrast_scale))

    temp_shift = reference.get("color_temp", 0) - clip_analysis.get("color_temp", 0)
    temp_shift = max(-0.08, min(0.08, temp_shift))

    # FFmpeg eq 滤镜参数
    eq_brightness = bri_shift  # [-1, 1]
    eq_contrast = contrast_scale  # [0.0, 2.0]

    filters = [f"eq=brightness={eq_brightness:.3f}:contrast={eq_contrast:.3f}"]

    # colorbalance 用于色温调整
    if abs(temp_shift) > 0.01:
        # temp_shift > 0 → 加暖（+R -B）
        rs = max(-1, min(1, temp_shift * 5))
        bs = max(-1, min(1, -temp_shift * 5))
        filters.append(f"colorbalance=rs={rs:.3f}:bs={bs:.3f}")

    filter_chain = ",".join(filters)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    # Round-15.5: safe_ffmpeg_arg on both positional paths.
    cmd = [
        "ffmpeg", "-y", "-i", safe_ffmpeg_arg(str(input_path)),
        "-vf", filter_chain,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "copy",
        safe_ffmpeg_arg(str(output_path)),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=300)
        if r.returncode != 0:
            logger.error("FFmpeg 调色失败: %s", r.stderr[-500:] if r.stderr else "")
            return input_path
    except Exception as e:
        logger.error("FFmpeg 调色异常: %s", e)
        return input_path

    logger.info("FFmpeg 调色完成: %s", output_path)
    return output_path


# ── 批量统一调色 ──────────────────────────────────────────────

def unify_color_grading(
    clip_paths: List[str],
    output_dir: str,
    *,
    reference_profile: Optional[Dict[str, float]] = None,
    use_cv2: bool = True,
) -> Dict[str, Any]:
    """
    对多个视频片段进行统一调色。

    Args:
        clip_paths: 输入视频路径列表
        output_dir: 输出目录
        reference_profile: 参考基准（None=自动计算中位数）
        use_cv2: 是否使用 cv2（False=用 FFmpeg）

    Returns:
        {
          "reference": {brightness, contrast, color_temp},
          "clips": [
            {"input": "a.mp4", "output": "a_graded.mp4", "adjustments": {...}},
            ...
          ],
          "method": "cv2" | "ffmpeg"
        }
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # 1. 分析所有片段
    analyses = []
    for path in clip_paths:
        a = analyze_clip_color(str(path))
        a["_path"] = str(path)
        analyses.append(a)

    # 2. 计算参考基准
    if reference_profile is None:
        reference_profile = compute_reference_profile(analyses)

    # 3. 逐段调色
    method = "cv2" if (use_cv2 and HAS_CV2) else "ffmpeg"
    grade_fn = grade_video_cv2 if method == "cv2" else grade_video_ffmpeg

    results = []
    for analysis in analyses:
        input_path = analysis["_path"]
        name = Path(input_path).stem + "_graded" + Path(input_path).suffix
        output_path = os.path.join(output_dir, name)

        grade_fn(input_path, output_path, analysis, reference_profile)

        results.append({
            "input": input_path,
            "output": output_path,
            "analysis": {k: v for k, v in analysis.items() if k != "_path"},
            "adjustments": {
                "brightness_shift": round(reference_profile["brightness"] - analysis.get("brightness", 0.5), 4),
                "color_temp_shift": round(reference_profile.get("color_temp", 0) - analysis.get("color_temp", 0), 4),
            },
        })

    return {
        "reference": reference_profile,
        "clips": results,
        "method": method,
    }


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="视频调色/曝光统一")
    parser.add_argument("inputs", nargs="+", help="输入视频文件列表")
    parser.add_argument("-o", "--output-dir", default="./graded", help="输出目录")
    parser.add_argument("--ffmpeg-only", action="store_true", help="仅使用 FFmpeg 模式")
    args = parser.parse_args()

    result = unify_color_grading(
        args.inputs,
        args.output_dir,
        use_cv2=not args.ffmpeg_only,
    )

    print(f"\n参考基准: brightness={result['reference']['brightness']:.3f}, "
          f"color_temp={result['reference']['color_temp']:.4f}")
    print(f"模式: {result['method']}")
    for clip in result["clips"]:
        adj = clip["adjustments"]
        print(f"  {Path(clip['input']).name} → {Path(clip['output']).name}")
        print(f"    亮度偏移: {adj['brightness_shift']:+.4f}, 色温偏移: {adj['color_temp_shift']:+.4f}")
