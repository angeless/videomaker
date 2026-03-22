#!/usr/bin/env python3
"""
用 PIL 渲染字幕 + FFmpeg 编码 — 逐段处理避免超时
先给每段单独加字幕，再 concat + 混 BGM
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
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"

FONT_PATH = "/System/Library/Fonts/PingFang.ttc"
FONT_SIZE_CN = 40
FONT_SIZE_EN = 22

SEGMENTS = [
    ("IMG_7355.MOV", 5, 12,
     "你有没有想过 一个人背着行李飞到地球的另一端\n会是什么样的感觉",
     "Have you ever wondered what it feels like\nto fly across the world alone"),
    ("IMG_7347.MOV", 10, 11,
     "二零二五年秋天 我来到了加拿大", "In the fall of 2025 I arrived in Canada"),
    ("IMG_2229.MOV", 15, 12,
     "多伦多的街头\n到处是陌生的面孔和听不懂的笑话",
     "Toronto streets full of unfamiliar faces\nand jokes I could not understand"),
    ("IMG_2560.MOV", 20, 11,
     "我租了一间小小的房间\n窗外能看到一棵枫树",
     "I rented a tiny room\nwith a maple tree from the window"),
    ("IMG_3419.MOV", 30, 12,
     "每天早上醒来\n都要花几秒钟才能想起自己在哪里",
     "Every morning it took a few seconds\nto remember where I was"),
    ("IMG_2879.MOV", 10, 11,
     "超市里的东西贵得让人心疼\n一颗白菜要三块加币",
     "Everything in the supermarket\nwas painfully expensive"),
    ("IMG_3386.MOV", 20, 12,
     "于是我学会了做饭\n从煮泡面到煎牛排 厨艺突飞猛进",
     "So I learned to cook\nfrom instant noodles to steak"),
    ("IMG_2840.MOV", 15, 11,
     "一个人吃饭的时候\n总会想起家里妈妈做的菜",
     "Eating alone always reminded me\nof my mother's cooking"),
    ("IMG_3505.MOV", 10, 12,
     "最难的不是语言\n是那种深入骨髓的孤独感",
     "The hardest part was not the language\nbut the bone-deep loneliness"),
    ("IMG_2230.MOV", 20, 11,
     "暴风雪来的那天\n我在公交站等了四十分钟",
     "The day the blizzard came\nI waited forty minutes at the bus stop"),
    ("IMG_2470.MOV", 15, 12,
     "手机里的天气预报写着零下二十度\n体感温度零下三十五",
     "The weather app said minus twenty\nWind chill minus thirty-five"),
    ("IMG_7358.MOV", 25, 11,
     "那一刻我真的问自己\n你为什么要来这里",
     "In that moment I truly asked myself\nwhy did you come here"),
    ("IMG_3382.MOV", 15, 12,
     "但是\n转角总会遇到意想不到的温暖",
     "But around the corner\nthere was always unexpected warmth"),
    ("IMG_3507.MOV", 10, 11,
     "邻居大叔每周末都会给我\n留一盒自己烤的饼干",
     "My neighbor left me\nhomemade cookies every weekend"),
    ("IMG_7348.MOV", 15, 12,
     "图书馆的阿姨会主动和我练英语\n纠正我的发音",
     "The librarian practiced English with me\nand corrected my pronunciation"),
    ("IMG_2277.MOV", 10, 11,
     "慢慢地\n这里的陌生感开始褪去",
     "Gradually\nthe feeling of being a stranger began to fade"),
    ("IMG_3385.MOV", 15, 12,
     "我开始享受一个人逛公园的下午\n和松鼠分享薯片",
     "I began to enjoy afternoons in the park\nsharing chips with squirrels"),
    ("IMG_2247.MOV", 10, 11,
     "秋天的枫叶红得像火\n美得不像真的",
     "The autumn maple leaves were so red\nthey looked unreal"),
    ("IMG_7357.MOV", 10, 12,
     "我终于明白\n所谓心酸不过是成长的另一个名字",
     "I finally understood that bitterness\nis just another name for growth"),
    ("IMG_7159.MOV", 15, 13,
     "如果你问我后不后悔\n我会说这段经历让我成为了更好的自己\n加拿大 谢谢你",
     "If you ask me about regrets\nthis journey made me better\nCanada thank you"),
]


def load_fonts():
    try:
        font_cn = ImageFont.truetype(FONT_PATH, size=FONT_SIZE_CN)
        font_en = ImageFont.truetype(FONT_PATH, size=FONT_SIZE_EN)
        return font_cn, font_en
    except Exception as e:
        print(f"Warning: Could not load PingFang font: {e}")
        return ImageFont.load_default(), ImageFont.load_default()


def draw_subtitle(frame, cn_text, en_text, font_cn, font_en):
    """在帧上绘制双语字幕（居中，白字黑边）"""
    h, w = frame.shape[:2]
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    # 中文字幕位置
    cn_lines = cn_text.split('\n')
    total_cn_height = sum(draw.textbbox((0, 0), line, font=font_cn)[3] for line in cn_lines)
    total_cn_height += (len(cn_lines) - 1) * 4  # line gap

    # 英文字幕位置
    en_lines = en_text.split('\n') if en_text else []
    total_en_height = sum(draw.textbbox((0, 0), line, font=font_en)[3] for line in en_lines)
    total_en_height += (len(en_lines) - 1) * 2

    gap = 8
    total_height = total_cn_height + gap + total_en_height
    base_y = h - total_height - 60  # 60px from bottom

    # 绘制中文
    y = base_y
    for line in cn_lines:
        bbox = draw.textbbox((0, 0), line, font=font_cn)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        # 黑色描边
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font_cn, fill=(0, 0, 0))
        draw.text((x, y), line, font=font_cn, fill=(255, 255, 255))
        y += bbox[3] + 4

    # 绘制英文
    y += gap
    for line in en_lines:
        bbox = draw.textbbox((0, 0), line, font=font_en)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font_en, fill=(0, 0, 0))
        draw.text((x, y), line, font=font_en, fill=(255, 255, 255, 220))
        y += bbox[3] + 2

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def process_segment(seg_idx, fname, ss, dur, cn, en, font_cn, font_en, tmp_dir):
    """处理单个片段：裁剪 + 字幕渲染"""
    src_path = os.path.join(SRC_DIR, fname)
    if not os.path.exists(src_path):
        print(f"  SKIP: {fname} not found")
        return None

    W, H, FPS = 1920, 1080, 30

    # Step A: 用 FFmpeg 裁剪 + 统一格式
    raw_seg = os.path.join(tmp_dir, f"raw_{seg_idx:03d}.mp4")
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}"
    cmd = [
        FFMPEG, "-y", "-ss", str(ss), "-i", src_path,
        "-t", str(dur), "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p", "-an", raw_seg,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0:
        print(f"  ERROR cutting {fname}")
        return None

    # Step B: 用 cv2 + PIL 加字幕，输出 raw frames 到 FFmpeg pipe
    sub_seg = os.path.join(tmp_dir, f"sub_{seg_idx:03d}.mp4")

    cap = cv2.VideoCapture(raw_seg)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    # FFmpeg pipe 接收 raw frames
    pipe_cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        sub_seg,
    ]
    proc = subprocess.Popen(pipe_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # 字幕显示时间：0.3s 后开始，结束前 0.3s 停止
    sub_start = 0.3
    sub_end = dur - 0.3
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        t = frame_count / fps
        if sub_start <= t <= sub_end:
            frame = draw_subtitle(frame, cn, en, font_cn, font_en)
        try:
            proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            break
        frame_count += 1

    cap.release()
    proc.stdin.close()
    proc.wait(timeout=60)

    if os.path.exists(sub_seg) and os.path.getsize(sub_seg) > 1000:
        return sub_seg
    return None


def main():
    print("=" * 60)
    print("加拿大心酸史 — 字幕渲染 + BGM 混合")
    print("=" * 60)

    font_cn, font_en = load_fonts()
    tmp = tempfile.mkdtemp(prefix="canada_sub_")
    print(f"Temp dir: {tmp}")

    # 逐段处理
    sub_files = []
    total_dur = 0.0
    for i, (fname, ss, dur, cn, en) in enumerate(SEGMENTS):
        print(f"\n[{i+1}/{len(SEGMENTS)}] {fname} ({dur}s)...")
        result = process_segment(i, fname, ss, dur, cn, en, font_cn, font_en, tmp)
        if result:
            sub_files.append(result)
            total_dur += dur
            print(f"  ✓ Done ({total_dur:.0f}s cumulative)")
        else:
            print(f"  ✗ Failed")

    if len(sub_files) < 10:
        print(f"ERROR: Only {len(sub_files)} segments succeeded, need at least 10")
        sys.exit(1)

    print(f"\n{'=' * 40}")
    print(f"Segments done: {len(sub_files)}, {total_dur:.0f}s ({total_dur/60:.1f} min)")

    # Concat
    print("\nConcatenating...")
    concat_list = os.path.join(tmp, "concat.txt")
    with open(concat_list, 'w') as f:
        for p in sub_files:
            f.write(f"file '{p}'\n")

    concat_out = os.path.join(tmp, "concat.mp4")
    r = subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", concat_out,
    ], capture_output=True, timeout=120)

    if r.returncode != 0:
        print(f"Concat failed!")
        sys.exit(1)

    # Mix BGM
    print("Mixing BGM...")
    bgm_path = str(OUTPUT_DIR / "ambient_bgm.m4a")
    final_out = str(OUTPUT_DIR / "canada_story_complete.mp4")

    if os.path.exists(bgm_path):
        r = subprocess.run([
            FFMPEG, "-y",
            "-i", concat_out,
            "-i", bgm_path,
            "-filter_complex",
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,volume=0.15[bgm]",
            "-map", "0:v", "-map", "[bgm]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", final_out,
        ], capture_output=True, timeout=300)
    else:
        shutil.copy2(concat_out, final_out)

    # 验证
    print("\nVerifying...")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size", "-of", "json", final_out],
        capture_output=True, text=True
    )
    info = json.loads(r.stdout).get("format", {})
    dur = float(info.get("duration", 0))
    size_mb = int(info.get("size", 0)) / (1024 * 1024)

    print(f"\n{'=' * 60}")
    print(f"COMPLETE!")
    print(f"Output:   {final_out}")
    print(f"Duration: {dur:.1f}s ({dur/60:.1f} min)")
    print(f"Size:     {size_mb:.1f} MB")
    print(f"Segments: {len(sub_files)}")
    print(f"Features: subtitles (CN+EN), ambient BGM")
    print(f"{'=' * 60}")

    # 清理
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
