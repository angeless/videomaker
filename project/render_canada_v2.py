#!/usr/bin/env python3
"""
加拿大心酸史 V2 — 基于真实转录内容的视频剪辑
保留原声 + 字幕 + 风景人物混搭 + BGM

策略：
1. 从转录中选取最佳叙事片段（保留原声）
2. 穿插空镜/B-roll
3. 字幕基于真实转录文本
4. BGM 低音量垫底
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
FONT_SIZE = 36

# ═══════════════════════════════════════════════════════════════
# 基于真实转录选取的片段 — 按叙事弧线排列
# (文件名, 开始秒, 时长, 字幕文本, 类型: narr=有人说话, broll=空镜)
# ═══════════════════════════════════════════════════════════════

SEGMENTS = [
    # ── 第一幕：到达加拿大 ──
    ("IMG_7159.MOV", 0, 14,
     "Hello everyone it's September 13th\nI'm renting a car from Queen Motion\nToronto airport station",
     "narr"),

    ("IMG_7155.MOV", 2, 6,
     "",  # B-roll 空镜：车/路
     "broll"),

    # ── 第二幕：买二手车 ──
    ("IMG_1326.MOV", 2, 12,
     "还得再来一趟就是说\n这个车是几几年的 2011年的\n多少公里 19万",
     "narr"),

    ("IMG_2229.MOV", 0, 14,
     "今天是我拿到这个车的第二天\n但我车还没有上牌\n因为我昨天去那个Service Ontario\n他给我说 我需要买保险",
     "narr"),

    # ── 第三幕：保险难题 ──
    ("IMG_2277.MOV", 0, 15,
     "今天我不是在搞保险的事儿嘛\n然后是没有搞成\nCAA给我推荐的那个broker\n大概五六百一个月",
     "narr"),

    ("IMG_2247.MOV", 0, 14,
     "事情果然没有想象中进展的这么顺利\n今天接到了那个保险公司的电话\n他把这个车认定为commercial use\n所以没办法买保险",
     "narr"),

    # ── 第四幕：自己修车 ──
    ("IMG_2560.MOV", 0, 14,
     "我现在感觉买二手车真的是一个\n没苦硬吃的行为\n因为这个车是老车嘛\n然后我这个人又有点强迫症",
     "narr"),

    ("IMG_2564.MOV", 0, 13,
     "这就是我所有的装备了\n今天要做的 撑起来换刹车片\n然后还有两个连杆",
     "narr"),

    ("IMG_2840.MOV", 0, 15,
     "自己修车的这几天\n最大的感受是\n经常忙活半天 啥也没干成",
     "narr"),

    ("IMG_2879.MOV", 0, 13,
     "我真的不知道该怎么办\n那个卡钳上的螺丝\n我还是拆不下来",
     "narr"),

    ("IMG_7155.MOV", 8, 5,
     "",  # B-roll
     "broll"),

    # ── 第五幕：太阳能板项目 ──
    ("IMG_3382.MOV", 0, 15,
     "好久没录视频啊\n说一下最近的进展吧\n我现在在研究怎么把\n太阳能板安装到车顶上",
     "narr"),

    ("IMG_3419.MOV", 0, 15,
     "来汇报一下今天的进展\n非常非常顺利\n我把我的太阳能板终于装上去了\n而且非常稳当",
     "narr"),

    ("IMG_7357.MOV", 0, 14,
     "今天是在找电线的一天\n我刚刚去了British Auto\n他们没有我要的那种电线",
     "narr"),

    ("IMG_7370.MOV", 0, 14,
     "站了这里一个小时了\n在跟ChatGPT老师学习\n整个电力系统的原理\n我觉得这个东西还挺有意思的",
     "narr"),

    # ── 第六幕：日常生活 ──
    ("IMG_3640.MOV", 5, 5,
     "",  # B-roll 空镜
     "broll"),

    ("IMG_3385.MOV", 0, 14,
     "刚刚去了一个很厉害的超市\n里面卖非常多中国的和印度的食物\n在Brampton\n南亚人占比比较多的一个地方",
     "narr"),

    ("IMG_7346.MOV", 0, 12,
     "你看看这份早餐觉得值不值\n三片面包 三根培根\n和两个双黄蛋",
     "narr"),

    ("IMG_7347.MOV", 10, 15,
     "今天想分享一下\n加拿大要不要给小费\n肯定是要给的啦\n其实我是挺赞成服务行业给小费的",
     "narr"),

    # ── 第七幕：社交与感悟 ──
    ("IMG_3505.MOV", 0, 15,
     "Hello呀\n今天经历了非常尴尬的一个晚上\n今晚上去找了一个多伦多的朋友\n然后认识另外一个小姐姐",
     "narr"),

    ("IMG_7345.MOV", 0, 12,
     "早上好呀\n今天天气超级好\n有阳光有雪有蓝天",
     "narr"),

    ("IMG_7246.MOV", 2, 5,
     "",  # B-roll 夜景空镜
     "broll"),

    ("IMG_7364.MOV", 0, 14,
     "昨晚差点没扛住\n然后准备去买那个Renogy官方的\n结果我就在想\n已经把所有东西都挑在购物车里了",
     "narr"),

    # ── 结尾 ──
    ("IMG_7355.MOV", 0, 12,
     "哈喽呀 报告一下今天\n今天算是比较充实的一天吧\n去了那个健身房锻炼了一会",
     "narr"),

    ("IMG_1833.MOV", 10, 6,
     "",  # B-roll 结尾空镜
     "broll"),
]


def load_font():
    try:
        return ImageFont.truetype(FONT_PATH, size=FONT_SIZE)
    except Exception:
        return ImageFont.load_default()


def draw_subtitle(frame, text, font):
    """在帧底部绘制中文字幕（白字黑边）"""
    if not text.strip():
        return frame
    h, w = frame.shape[:2]
    pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)

    lines = text.split('\n')
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    total_h = sum(line_heights) + (len(lines) - 1) * 6
    base_y = h - total_h - 50

    y = base_y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        # 黑色描边
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                if dx == 0 and dy == 0:
                    continue
                draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_heights[lines.index(line)] + 6

    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


def process_segment(seg_idx, fname, ss, dur, subtitle, seg_type, font, tmp_dir):
    """处理单个片段：裁剪 + 可选字幕 + 保留原声"""
    src = os.path.join(SRC_DIR, fname)
    if not os.path.exists(src):
        print(f"  SKIP: {fname} not found")
        return None

    W, H, FPS = 1920, 1080, 30

    # Step A: FFmpeg 裁剪 + 格式统一（保留音频！）
    raw = os.path.join(tmp_dir, f"raw_{seg_idx:03d}.mp4")
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}"
    cmd = [
        FFMPEG, "-y", "-ss", str(ss), "-i", src,
        "-t", str(dur), "-vf", vf,
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",  # 保留音频！
        raw,
    ]
    r = subprocess.run(cmd, capture_output=True, timeout=120)
    if r.returncode != 0:
        print(f"  ERROR cutting {fname}")
        return None

    if not subtitle.strip():
        # B-roll 无需字幕，直接返回
        return raw

    # Step B: 加字幕 (PIL 渲染)
    sub_vid = os.path.join(tmp_dir, f"sub_{seg_idx:03d}.mp4")

    cap = cv2.VideoCapture(raw)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 视频编码 pipe
    pipe_cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
        "-i", raw,           # 用原始文件的音频
        "-map", "0:v",        # 视频来自 pipe
        "-map", "1:a",        # 音频来自原始文件
        "-c:v", "libx264", "-crf", "20", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",       # 音频直接 copy
        "-shortest",
        sub_vid,
    ]
    proc = subprocess.Popen(pipe_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    sub_start = 0.5
    sub_end = dur - 0.3
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        t = frame_count / fps
        if sub_start <= t <= sub_end:
            frame = draw_subtitle(frame, subtitle, font)
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
    return raw  # 回退到无字幕版


def main():
    print("=" * 60)
    print("加拿大心酸史 V2 — 真实转录 + 原声 + 字幕")
    print("=" * 60)

    font = load_font()
    tmp = tempfile.mkdtemp(prefix="canada_v2_")
    print(f"Temp dir: {tmp}")

    # ── 逐段处理 ──
    seg_files = []
    total_dur = 0.0

    for i, (fname, ss, dur, sub, stype) in enumerate(SEGMENTS):
        label = "🗣️" if stype == "narr" else "🎬"
        print(f"\n[{i+1}/{len(SEGMENTS)}] {label} {fname} [{ss}s +{dur}s]...")
        result = process_segment(i, fname, ss, dur, sub, stype, font, tmp)
        if result:
            seg_files.append(result)
            total_dur += dur
            print(f"  ✓ Done ({total_dur:.0f}s cumulative)")
        else:
            print(f"  ✗ Failed")

    if len(seg_files) < 10:
        print(f"ERROR: Only {len(seg_files)} segments succeeded")
        sys.exit(1)

    print(f"\n{'='*40}")
    print(f"Segments: {len(seg_files)}, {total_dur:.0f}s ({total_dur/60:.1f} min)")

    # ── Concat ──
    print("\nConcatenating...")
    concat_list = os.path.join(tmp, "concat.txt")
    with open(concat_list, 'w') as f:
        for p in seg_files:
            f.write(f"file '{p}'\n")

    concat_out = os.path.join(tmp, "concat.mp4")
    r = subprocess.run([
        FFMPEG, "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-c", "copy", concat_out,
    ], capture_output=True, timeout=120)

    if r.returncode != 0:
        print("Concat failed!")
        sys.exit(1)

    # ── Mix BGM (低音量, 不盖过原声) ──
    print("Mixing BGM...")
    bgm_path = str(OUTPUT_DIR / "ambient_bgm.m4a")
    final_out = str(OUTPUT_DIR / "canada_story_v2.mp4")

    if os.path.exists(bgm_path):
        r = subprocess.run([
            FFMPEG, "-y",
            "-i", concat_out,
            "-i", bgm_path,
            "-filter_complex",
            f"[0:a]volume=1.0[voice];"
            f"[1:a]atrim=0:{total_dur},asetpts=PTS-STARTPTS,volume=0.08[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=3[out]",
            "-map", "0:v", "-map", "[out]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", final_out,
        ], capture_output=True, timeout=300)

        if r.returncode != 0:
            print("BGM mix failed, using video without BGM")
            shutil.copy2(concat_out, final_out)
    else:
        print("No BGM file found, output without BGM")
        shutil.copy2(concat_out, final_out)

    # ── 验证 ──
    print("\nVerifying...")
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
         "-of", "json", final_out],
        capture_output=True, text=True
    )
    info = json.loads(r.stdout).get("format", {})
    dur = float(info.get("duration", 0))
    size_mb = int(info.get("size", 0)) / (1024 * 1024)

    print(f"\n{'='*60}")
    print(f"COMPLETE!")
    print(f"Output:   {final_out}")
    print(f"Duration: {dur:.1f}s ({dur/60:.1f} min)")
    print(f"Size:     {size_mb:.1f} MB")
    print(f"Segments: {len(seg_files)}")
    print(f"Features: 原声保留, 中文字幕, 风景穿插, 低音BGM")
    print(f"{'='*60}")

    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
