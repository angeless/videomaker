#!/usr/bin/env python3
"""
加拿大心酸史 V3.3 — 聚焦"买二手车"一个故事

修复记录：
- V3:   首版，B-roll 音量爆音导致"电子噪音"
- V3.1: B-roll 静音 + loudnorm，但 loudnorm 将采样率升至 96kHz 导致解码伪影
- V3.2: 强制 44100Hz + 音频 crossfade + 改进 BGM ducking
- V3.3: 降 TP 至 -6dB 防爆 + concat demuxer 替代链式 xfade 减少重编码 + 最终 limiter
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SRC_DIR = "/Users/angelwang/Documents/1128 百度盘备份 加拿大心酸史"
OUTPUT_DIR = Path("/Users/angelwang/videoeditor/output_canada_video")
ANALYSIS_PATH = OUTPUT_DIR / "analyzed_videos.json"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

FONT_PATH = "/System/Library/Fonts/PingFang.ttc"
FONT_SIZE = 38
W, H, FPS = 1920, 1080, 30
SAMPLE_RATE = 44100  # 强制统一采样率，防止 loudnorm 改变采样率

SCRIPT = [
    # ── Hook: 开场金句 ──
    ("IMG_2560.MOV", 0.0, 16),
    # ── B-roll: 过渡 ──
    ("IMG_2678.MOV", 0, 4),
    # ── 买车: 2011年 19万公里 ──
    ("IMG_1326.MOV", 2, 11),
    # ── 保险: 拿到车第二天 ──
    ("IMG_2229.MOV", 0.5, 24),
    # ── B-roll: 过渡 ──
    ("IMG_2231.MOV", 0, 4),
    # ── 保险被拒: commercial use ──
    ("IMG_2247.MOV", 0, 16),
    # ── 保险太贵 ──
    ("IMG_2277.MOV", 2, 18),
    # ── B-roll: 过渡 ──
    ("IMG_2718.MOV", 0, 4),
    # ── 准备修车: 找材料最费劲 ──
    ("IMG_2419.MOV", 22, 15),
    # ── 装备就绪 ──
    ("IMG_2564.MOV", 0, 19),
    # ── 修车受挫: 啥也没干成 ──
    ("IMG_2840.MOV", 1, 11),
    # ── 绝望: 螺丝拆不下来 ──
    ("IMG_2879.MOV", 1, 11),
    # ── B-roll: 过渡 ──
    ("IMG_2863.MOV", 0, 5),
    # ── 解决: 师傅三下五除二 ──
    ("IMG_2993.MOV", 0, 20),
    # ── B-roll: 收尾 ──
    ("IMG_2994.MOV", 0, 5),
    # ── 感悟/结尾 ──
    ("IMG_2245.MOV", 19, 15),
]


def load_analysis():
    if not ANALYSIS_PATH.exists():
        print(f"WARNING: {ANALYSIS_PATH} not found")
        return {}
    with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_subtitle_segments(analysis, fname, clip_start, clip_dur):
    info = analysis.get(fname, {})
    all_segs = info.get("transcription", {}).get("segments", [])
    clip_end = clip_start + clip_dur
    result = []
    for seg in all_segs:
        s, e = seg.get("start", 0), seg.get("end", 0)
        if e <= clip_start or s >= clip_end:
            continue
        result.append({
            "rel_start": max(s, clip_start) - clip_start,
            "rel_end": min(e, clip_end) - clip_start,
            "text": seg.get("text", "").strip(),
        })
    return result


def load_font():
    try:
        return ImageFont.truetype(FONT_PATH, size=FONT_SIZE)
    except Exception:
        return ImageFont.load_default()


def draw_subtitle(frame, text, font):
    if not text.strip():
        return frame
    h, w = frame.shape[:2]
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    MAX_CHARS = 22
    raw_text = text.replace('\n', '')
    lines = []
    while raw_text:
        lines.append(raw_text[:MAX_CHARS])
        raw_text = raw_text[MAX_CHARS:]

    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    total_h = sum(line_heights) + (len(lines) - 1) * 8
    base_y = h - total_h - 60

    y = base_y
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_heights[i] + 8

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def process_segment(seg_idx, fname, ss, dur, sub_segs, font, tmp_dir):
    src = os.path.join(SRC_DIR, fname)
    if not os.path.exists(src):
        print(f"  SKIP: {fname} not found")
        return None

    raw = os.path.join(tmp_dir, f"raw_{seg_idx:03d}.mp4")
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}")

    is_broll = not sub_segs

    if is_broll:
        # B-roll: 静音（保留极小音量避免 concat 音频流断裂）
        af = "volume=0.01,aformat=sample_fmts=fltp"
    else:
        # 叙事: loudnorm 归一化，TP=-6dB 预留足够 headroom 防 AAC 编码后爆破
        af = "loudnorm=I=-16:TP=-6:LRA=11,aformat=sample_fmts=fltp"

    cmd = [
        FFMPEG, "-y", "-ss", str(ss), "-i", src,
        "-t", str(dur), "-vf", vf,
        "-af", af,
        "-ar", str(SAMPLE_RATE),  # 强制采样率，防止 loudnorm 改变
        "-ac", "2",               # 强制双声道（IMG_1326 是单声道）
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        raw,
    ]

    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0:
        print(f"  ERROR cutting {fname}: {r.stderr[-200:]}")
        return None

    if is_broll:
        return raw

    # 叠加字幕
    sub_vid = os.path.join(tmp_dir, f"sub_{seg_idx:03d}.mp4")
    cap = cv2.VideoCapture(raw)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    pipe_cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
        "-i", raw,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest",
        sub_vid,
    ]
    proc = subprocess.Popen(pipe_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        t = frame_count / fps

        current_text = ""
        for seg in sub_segs:
            if seg["rel_start"] <= t <= seg["rel_end"]:
                current_text = seg["text"]
                break

        if current_text:
            frame = draw_subtitle(frame, current_text, font)

        try:
            proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            break
        frame_count += 1

    cap.release()
    proc.stdin.close()
    proc.wait(timeout=60)

    if os.path.exists(sub_vid) and os.path.getsize(sub_vid) > 1000:
        return sub_vid
    return raw


def concat_segments(seg_files, tmp_dir):
    """用 concat demuxer 拼接片段（不重编码音频，避免代际质量损失）"""
    if len(seg_files) < 2:
        return seg_files[0] if seg_files else None

    # concat demuxer — 所有片段已统一编码参数，可直接 copy
    concat_list = os.path.join(tmp_dir, "concat_list.txt")
    with open(concat_list, 'w') as f:
        for seg in seg_files:
            f.write(f"file '{seg}'\n")

    out = os.path.join(tmp_dir, "concat_all.mp4")
    cmd = [
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", out,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0:
        print(f"  concat demuxer failed, trying re-encode fallback...")
        cmd = [
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-ar", str(SAMPLE_RATE), "-ac", "2",
            "-c:a", "aac", "-b:a", "192k",
            out,
        ]
        subprocess.run(cmd, capture_output=True, timeout=300)

    return out


def main():
    print("=" * 60)
    print("加拿大心酸史 V3.3 — 防爆破 + 无损拼接 + limiter")
    print("=" * 60)

    analysis = load_analysis()
    font = load_font()
    tmp = tempfile.mkdtemp(prefix="canada_v3_")
    print(f"Temp dir: {tmp}")

    total_script_dur = sum(dur for _, _, dur in SCRIPT)
    print(f"脚本总时长: {total_script_dur:.0f}s ({total_script_dur/60:.1f} min)")
    print(f"片段数: {len(SCRIPT)}")
    print()

    # ── 逐段处理 ──
    seg_files = []
    total_dur = 0.0

    for i, (fname, ss, dur) in enumerate(SCRIPT):
        sub_segs = get_subtitle_segments(analysis, fname, ss, dur)
        has_sub = len(sub_segs) > 0
        label = f"🗣️ ({len(sub_segs)} subs)" if has_sub else "🎬 B-roll"

        print(f"[{i+1}/{len(SCRIPT)}] {label} {fname} [{ss}s +{dur}s]...")
        result = process_segment(i, fname, ss, dur, sub_segs, font, tmp)

        if result:
            seg_files.append(result)
            total_dur += dur
            print(f"  ✓ Done ({total_dur:.0f}s cumulative)")
        else:
            print(f"  ✗ Failed")

    if len(seg_files) < 10:
        print(f"ERROR: Only {len(seg_files)} segments")
        sys.exit(1)

    print(f"\n{'='*40}")
    print(f"Segments: {len(seg_files)}, {total_dur:.0f}s")

    # ── Concat（无损拼接，避免链式重编码导致的音频劣化）──
    print("\nConcatenating (demuxer copy)...")
    concat_out = concat_segments(seg_files, tmp)

    if not concat_out or not os.path.exists(concat_out):
        print("Concat failed!")
        sys.exit(1)

    # 验证 concat 采样率
    sr = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate", "-of", "csv=p=0", concat_out],
        capture_output=True, text=True
    ).stdout.strip()
    print(f"  Concat sample rate: {sr} Hz")

    # ── Mix BGM ──
    print("Mixing BGM...")
    bgm_path = str(OUTPUT_DIR / "ambient_bgm.m4a")
    final_out = str(OUTPUT_DIR / "canada_story_v3_3.mp4")

    if os.path.exists(bgm_path):
        # BGM 混音 + alimiter 防止混合后峰值超 0dBFS
        r = subprocess.run([
            FFMPEG, "-y",
            "-i", concat_out,
            "-i", bgm_path,
            "-filter_complex",
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,volume=0.06[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
            f"alimiter=limit=0.9:attack=5:release=50[out]",
            "-map", "0:v", "-map", "[out]",
            "-ar", str(SAMPLE_RATE), "-ac", "2",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", final_out,
        ], capture_output=True, timeout=300)

        if r.returncode != 0:
            print(f"BGM mix failed: {r.stderr[-300:]}")
            print("Exporting without BGM...")
            shutil.copy2(concat_out, final_out)
    else:
        print("No BGM file, exporting without")
        shutil.copy2(concat_out, final_out)

    # ── 验证 ──
    print("\nVerifying...")
    probe = subprocess.run(
        ["ffprobe", "-v", "error",
         "-show_entries", "format=duration,size",
         "-show_entries", "stream=sample_rate,codec_name",
         "-of", "json", final_out],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    fmt = info.get("format", {})
    dur = float(fmt.get("duration", 0))
    size_mb = int(fmt.get("size", 0)) / (1024 * 1024)
    streams = info.get("streams", [])
    audio_sr = next((s["sample_rate"] for s in streams if s.get("sample_rate")), "?")

    print(f"\n{'='*60}")
    print(f"COMPLETE!")
    print(f"Output:      {final_out}")
    print(f"Duration:    {dur:.1f}s ({dur/60:.1f} min)")
    print(f"Size:        {size_mb:.1f} MB")
    print(f"Audio:       {audio_sr} Hz (应为 44100)")
    print(f"Segments:    {len(seg_files)}")
    print(f"Concat:      demuxer copy (无损)")
    print(f"{'='*60}")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
