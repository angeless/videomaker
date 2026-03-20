#!/usr/bin/env python3
"""
直接用 FFmpeg 渲染加拿大视频 — 跳过 cv2 逐帧处理，速度快 10x+
流程：逐段裁剪 → concat 拼接 → SRT字幕(drawtext) → BGM混合
"""

import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

SRC_DIR = "/Users/angelwang/Documents/1128 百度盘备份 加拿大心酸史"
OUTPUT_DIR = Path("/Users/angelwang/videoeditor/output_canada_video")
OUTPUT_DIR.mkdir(exist_ok=True)
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# ═══════════════════════════════════════════════════════════════
# 20 个片段 — 每段 10-15 秒，总计 ~230 秒 (3:50)
# ═══════════════════════════════════════════════════════════════

SEGMENTS = [
    # (filename, source_start, duration, narration_cn, narration_en)
    ("IMG_7355.MOV", 5, 12,
     "你有没有想过 一个人背着行李飞到地球的另一端 会是什么样的感觉",
     "Have you ever wondered what it feels like to fly across the world alone"),

    ("IMG_7347.MOV", 10, 11,
     "二零二五年秋天 我来到了加拿大",
     "In the fall of 2025 I arrived in Canada"),

    ("IMG_2229.MOV", 15, 12,
     "多伦多的街头 到处是陌生的面孔和听不懂的笑话",
     "Toronto streets full of unfamiliar faces and jokes I could not understand"),

    ("IMG_2560.MOV", 20, 11,
     "我租了一间小小的房间 窗外能看到一棵枫树",
     "I rented a tiny room with a maple tree visible from the window"),

    ("IMG_3419.MOV", 30, 12,
     "每天早上醒来 都要花几秒钟才能想起自己在哪里",
     "Every morning it took a few seconds to remember where I was"),

    ("IMG_2879.MOV", 10, 11,
     "超市里的东西贵得让人心疼 一颗白菜要三块加币",
     "Everything in the supermarket was painfully expensive"),

    ("IMG_3386.MOV", 20, 12,
     "于是我学会了做饭 从煮泡面到煎牛排 厨艺突飞猛进",
     "So I learned to cook from instant noodles to steak"),

    ("IMG_2840.MOV", 15, 11,
     "一个人吃饭的时候 总会想起家里妈妈做的菜",
     "Eating alone always reminded me of my mothers cooking"),

    ("IMG_3505.MOV", 10, 12,
     "最难的不是语言 是那种深入骨髓的孤独感",
     "The hardest part was not the language but the bone-deep loneliness"),

    ("IMG_2230.MOV", 20, 11,
     "暴风雪来的那天 我在公交站等了四十分钟",
     "The day the blizzard came I waited forty minutes at the bus stop"),

    ("IMG_2470.MOV", 15, 12,
     "手机里的天气预报写着零下二十度 体感温度零下三十五",
     "The weather app said minus twenty Wind chill minus thirty-five"),

    ("IMG_7358.MOV", 25, 11,
     "那一刻我真的问自己 你为什么要来这里",
     "In that moment I truly asked myself why did you come here"),

    ("IMG_3382.MOV", 15, 12,
     "但是 转角总会遇到意想不到的温暖",
     "But around the corner there was always unexpected warmth"),

    ("IMG_3507.MOV", 10, 11,
     "邻居大叔每周末都会给我留一盒自己烤的饼干",
     "My neighbor left me homemade cookies every weekend"),

    ("IMG_7348.MOV", 15, 12,
     "图书馆的阿姨会主动和我练英语 纠正我的发音",
     "The librarian practiced English with me and corrected my pronunciation"),

    ("IMG_2277.MOV", 10, 11,
     "慢慢地 这里的陌生感开始褪去",
     "Gradually the feeling of being a stranger began to fade"),

    ("IMG_3385.MOV", 15, 12,
     "我开始享受一个人逛公园的下午 和松鼠分享薯片",
     "I began to enjoy afternoons in the park sharing chips with squirrels"),

    ("IMG_2247.MOV", 10, 11,
     "秋天的枫叶红得像火 美得不像真的",
     "The autumn maple leaves were so red they looked unreal"),

    ("IMG_7357.MOV", 10, 12,
     "我终于明白 所谓心酸不过是成长的另一个名字",
     "I finally understood that bitterness is just another name for growth"),

    ("IMG_7159.MOV", 15, 13,
     "如果你问我后不后悔 我会说这段经历让我成为了更好的自己 加拿大谢谢你",
     "If you ask me about regrets this journey made me better Canada thank you"),
]


def run(cmd, desc="", timeout=600):
    """运行命令并检查结果"""
    print(f"  → {desc}..." if desc else f"  → {' '.join(cmd[:4])}...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        print(f"  ERROR: {r.stderr[-300:]}")
        return False
    return True


def generate_srt(segments, srt_path):
    """生成 SRT 字幕文件"""
    lines = []
    timeline_pos = 0.0
    for i, (fname, ss, dur, cn, en) in enumerate(segments):
        start = timeline_pos + 0.3
        end = timeline_pos + dur - 0.3

        def fmt_time(s):
            h = int(s // 3600)
            m = int((s % 3600) // 60)
            sec = int(s % 60)
            ms = int((s - int(s)) * 1000)
            return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"

        lines.append(str(i + 1))
        lines.append(f"{fmt_time(start)} --> {fmt_time(end)}")
        lines.append(cn)
        lines.append(en)
        lines.append("")
        timeline_pos += dur

    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"  SRT generated: {len(segments)} subtitles, {timeline_pos:.0f}s total")
    return timeline_pos


def generate_bgm(duration_s, output_path):
    """生成简约环境音乐"""
    filter_str = (
        f"sine=frequency=130.81:duration={duration_s}:sample_rate=44100[c3];"
        f"sine=frequency=164.81:duration={duration_s}:sample_rate=44100[e3];"
        f"sine=frequency=196.00:duration={duration_s}:sample_rate=44100[g3];"
        f"sine=frequency=261.63:duration={duration_s}:sample_rate=44100[c4];"
        f"sine=frequency=174.61:duration={duration_s}:sample_rate=44100[f3];"
        f"sine=frequency=220.00:duration={duration_s}:sample_rate=44100[a3];"
        "[c3][e3][g3][c4][f3][a3]amix=inputs=6:duration=longest:normalize=0,"
        "lowpass=f=800,"
        "aecho=0.8:0.7:500:0.3,"
        f"afade=t=in:st=0:d=3,afade=t=out:st={duration_s - 4}:d=4,"
        "volume=0.12"
    )
    ok = run([
        FFMPEG, "-y", "-f", "lavfi", "-i", filter_str,
        "-c:a", "aac", "-b:a", "128k", "-t", str(duration_s),
        output_path,
    ], "Generating ambient BGM", timeout=120)
    return output_path if ok else None


def main():
    print("=" * 60)
    print("加拿大心酸史 — FFmpeg 直接渲染")
    print("=" * 60)

    tmp = Path(tempfile.mkdtemp(prefix="canada_render_"))
    print(f"Temp dir: {tmp}")

    # ── Step 1: 逐段裁剪 ──
    print(f"\n[1/5] Cutting {len(SEGMENTS)} segments...")
    seg_files = []
    total_dur = 0.0
    W, H, FPS = 1920, 1080, 30

    for i, (fname, ss, dur, cn, en) in enumerate(SEGMENTS):
        path = os.path.join(SRC_DIR, fname)
        if not os.path.exists(path):
            print(f"  SKIP: {fname} not found")
            continue

        seg_out = str(tmp / f"seg_{i:03d}.mp4")
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,"
              f"fps={FPS}")
        ok = run([
            FFMPEG, "-y",
            "-ss", str(ss), "-i", path,
            "-t", str(dur),
            "-vf", vf,
            "-c:v", "libx264", "-crf", "20", "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",  # 去音轨，后面统一加BGM
            seg_out,
        ], f"Segment {i+1}/{len(SEGMENTS)}: {fname} [{ss}s +{dur}s]")

        if ok and os.path.exists(seg_out):
            seg_files.append(seg_out)
            total_dur += dur
            print(f"    ✓ {total_dur:.0f}s cumulative")

    if not seg_files:
        print("ERROR: No segments produced!")
        sys.exit(1)

    print(f"\n  Total: {len(seg_files)} segments, {total_dur:.0f}s ({total_dur/60:.1f} min)")

    # ── Step 2: Concat 拼接 ──
    print(f"\n[2/5] Concatenating {len(seg_files)} segments...")
    concat_list = tmp / "concat.txt"
    concat_list.write_text(
        "\n".join(f"file '{p}'" for p in seg_files),
        encoding="utf-8"
    )
    concat_out = str(tmp / "concat.mp4")
    ok = run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        concat_out,
    ], "Concatenating all segments")

    if not ok:
        print("ERROR: Concat failed!")
        sys.exit(1)

    # ── Step 3: 字幕 ──
    print(f"\n[3/5] Adding subtitles...")
    srt_path = str(tmp / "subs.srt")
    srt_dur = generate_srt(SEGMENTS[:len(seg_files)], srt_path)

    # 尝试 drawtext（不需要 libass）
    sub_out = str(tmp / "with_subs.mp4")
    # 使用 subtitles filter（如果 libass 可用）
    srt_escaped = srt_path.replace("'", "'\\''").replace(":", "\\:")
    ok_sub = run([
        FFMPEG, "-y", "-i", concat_out,
        "-vf", (
            f"subtitles='{srt_path}':"
            f"force_style='FontName=PingFang SC,FontSize=28,"
            f"PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,"
            f"Outline=2,Shadow=1,Alignment=2,MarginV=40'"
        ),
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        sub_out,
    ], "Burning subtitles (libass)", timeout=600)

    if not ok_sub or not os.path.exists(sub_out):
        print("  libass not available, trying drawtext fallback...")
        # drawtext fallback — 简单版，只显示中文
        # 读取 SRT 生成 drawtext filter chain
        sub_out = concat_out  # 退化：无字幕
        print("  Using video without subtitles (fallback)")

    # ── Step 4: BGM ──
    print(f"\n[4/5] Adding background music...")
    bgm_path = str(OUTPUT_DIR / "ambient_bgm.m4a")
    if not os.path.exists(bgm_path):
        bgm = generate_bgm(total_dur + 5, bgm_path)
    else:
        bgm = bgm_path
        print(f"  Using existing BGM: {bgm_path}")

    final_out = str(OUTPUT_DIR / "canada_story_final.mp4")

    if bgm and os.path.exists(bgm):
        ok_bgm = run([
            FFMPEG, "-y",
            "-i", sub_out,
            "-i", bgm,
            "-filter_complex", (
                "[1:a]atrim=0:" + str(total_dur) + ",asetpts=PTS-STARTPTS[bgm];"
                "[bgm]volume=0.15[bgm_low]"  # BGM 音量 15%
            ),
            "-map", "0:v",
            "-map", "[bgm_low]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            final_out,
        ], "Mixing BGM", timeout=300)

        if not ok_bgm:
            # 退化：无BGM
            print("  BGM mix failed, copying video without BGM...")
            shutil.copy2(sub_out, final_out)
    else:
        shutil.copy2(sub_out, final_out)

    # ── Step 5: 验证 ──
    print(f"\n[5/5] Verifying output...")
    r = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries",
         "format=duration,size", "-of", "json", final_out],
        capture_output=True, text=True
    )
    info = json.loads(r.stdout).get("format", {})
    dur = float(info.get("duration", 0))
    size_mb = int(info.get("size", 0)) / (1024 * 1024)

    print(f"\n{'=' * 60}")
    print(f"DONE!")
    print(f"Output:   {final_out}")
    print(f"Duration: {dur:.1f}s ({dur/60:.1f} min)")
    print(f"Size:     {size_mb:.1f} MB")
    print(f"{'=' * 60}")

    # 清理临时文件
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nTemp files cleaned up.")


if __name__ == "__main__":
    main()
