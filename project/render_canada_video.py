#!/usr/bin/env python3
"""
直接渲染 3+ 分钟加拿大生活视频
跳过 workflow 引擎，直接调用 RenderPipeline
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 添加项目根目录到 sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from modules.step7_final_render.pipeline import RenderPipeline

SRC_DIR = "/Users/angelwang/Documents/1128 百度盘备份 加拿大心酸史"
OUTPUT_DIR = ROOT / "output_canada_video"
OUTPUT_DIR.mkdir(exist_ok=True)
FINAL_OUTPUT = str(OUTPUT_DIR / "canada_story_final.mp4")

# ═══════════════════════════════════════════════════════════════
# 1. 片段选择 — 20 个片段，每段 10-15 秒
# ═══════════════════════════════════════════════════════════════

SEGMENTS = [
    # (filename, source_start, duration, narration_cn, narration_en)
    # 开篇 — 远景/自然
    ("IMG_7355.MOV", 5, 12,
     "你有没有想过，一个人背着行李，飞到地球的另一端，会是什么样的感觉？",
     "Have you ever wondered what it feels like to fly to the other side of the world, alone?"),

    ("IMG_7347.MOV", 10, 11,
     "二零二五年秋天，我来到了加拿大。",
     "In the fall of 2025, I arrived in Canada."),

    # 初到 — 城市/街道
    ("IMG_2229.MOV", 15, 12,
     "多伦多的街头，到处是陌生的面孔和听不懂的笑话。",
     "The streets of Toronto were full of unfamiliar faces and jokes I couldn't understand."),

    ("IMG_2560.MOV", 20, 11,
     "我租了一间小小的房间，窗外能看到一棵枫树。",
     "I rented a tiny room with a maple tree visible from the window."),

    ("IMG_3419.MOV", 30, 12,
     "每天早上醒来，都要花几秒钟才能想起自己在哪里。",
     "Every morning, it took a few seconds to remember where I was."),

    # 生活 — 日常
    ("IMG_2879.MOV", 10, 11,
     "超市里的东西贵得让人心疼，一颗白菜要三块加币。",
     "Everything in the supermarket was painfully expensive."),

    ("IMG_3386.MOV", 20, 12,
     "于是我学会了做饭。从煮泡面到煎牛排，厨艺突飞猛进。",
     "So I learned to cook. My skills grew from instant noodles to steak."),

    ("IMG_2840.MOV", 15, 11,
     "一个人吃饭的时候，总会想起家里妈妈做的菜。",
     "Eating alone always reminded me of Mom's cooking back home."),

    # 困难 — 挑战
    ("IMG_3505.MOV", 10, 12,
     "最难的不是语言，是那种深入骨髓的孤独感。",
     "The hardest part wasn't the language — it was the bone-deep loneliness."),

    ("IMG_2230.MOV", 20, 11,
     "暴风雪来的那天，我在公交站等了四十分钟。",
     "The day the blizzard came, I waited forty minutes at the bus stop."),

    ("IMG_2470.MOV", 15, 12,
     "手机里的天气预报写着零下二十度，体感温度零下三十五。",
     "The weather app said minus twenty. Wind chill: minus thirty-five."),

    ("IMG_7358.MOV", 25, 11,
     "那一刻我真的问自己：你为什么要来这里？",
     "In that moment I truly asked myself: why did you come here?"),

    # 转折 — 发现美好
    ("IMG_3382.MOV", 15, 12,
     "但是，转角总会遇到意想不到的温暖。",
     "But around the corner, there was always unexpected warmth."),

    ("IMG_3507.MOV", 10, 11,
     "邻居大叔每周末都会给我留一盒自己烤的饼干。",
     "My neighbor would leave me a box of homemade cookies every weekend."),

    ("IMG_7348.MOV", 15, 12,
     "图书馆的阿姨会主动和我练英语，纠正我的发音。",
     "The librarian would practice English with me and correct my pronunciation."),

    ("IMG_2277.MOV", 10, 11,
     "慢慢地，这里的陌生感开始褪去。",
     "Gradually, the feeling of being a stranger began to fade."),

    # 成长 — 收获
    ("IMG_3385.MOV", 15, 12,
     "我开始享受一个人逛公园的下午，和松鼠分享薯片。",
     "I began to enjoy solitary afternoons in the park, sharing chips with squirrels."),

    ("IMG_2247.MOV", 10, 11,
     "秋天的枫叶红得像火，美得不像真的。",
     "The autumn maple leaves were so red they looked unreal."),

    ("IMG_7357.MOV", 10, 12,
     "我终于明白，所谓心酸，不过是成长的另一个名字。",
     "I finally understood that bitterness is just another name for growth."),

    # 结尾
    ("IMG_7159.MOV", 15, 13,
     "如果你问我后不后悔，我会说，这段经历让我成为了更好的自己。加拿大，谢谢你。",
     "If you ask me whether I have regrets, I'd say this journey made me a better person. Canada, thank you."),
]


def build_script():
    """构建渲染管道需要的 script dict"""
    clips = []
    subtitles = []
    timeline_pos = 0.0

    for i, (fname, ss, dur, cn, en) in enumerate(SEGMENTS):
        path = os.path.join(SRC_DIR, fname)
        if not os.path.exists(path):
            print(f"WARNING: {path} not found, skipping")
            continue

        clips.append({
            "video_id": f"seg_{i}",
            "matched_path": path,
            "source_start": ss,
            "duration": dur,
            "has_face": False,
        })

        subtitles.append({
            "cn_text": cn,
            "en_text": en,
            "start_time": timeline_pos + 0.5,  # 0.5s 延迟显示
            "end_time": timeline_pos + dur - 0.5,
        })

        timeline_pos += dur

    return {
        "clips": clips,
        "subtitles": subtitles,
        "title": "加拿大心酸史",
        "total_duration": timeline_pos,
    }


def generate_ambient_bgm(duration_s: float, output_path: str):
    """用 FFmpeg 生成简约环境音乐（柔和的和弦垫音）"""
    # 生成多层正弦波叠加的环境音
    # C major 和弦基础音: C3(130.81), E3(164.81), G3(196.00), C4(261.63)
    # 加入慢速 LFO 调制，创造自然的起伏感
    filter_str = (
        # 基础和弦层
        f"sine=frequency=130.81:duration={duration_s}:sample_rate=44100[c3];"
        f"sine=frequency=164.81:duration={duration_s}:sample_rate=44100[e3];"
        f"sine=frequency=196.00:duration={duration_s}:sample_rate=44100[g3];"
        f"sine=frequency=261.63:duration={duration_s}:sample_rate=44100[c4];"
        # 第二组和弦 (F major: F3, A3, C4)
        f"sine=frequency=174.61:duration={duration_s}:sample_rate=44100[f3];"
        f"sine=frequency=220.00:duration={duration_s}:sample_rate=44100[a3];"
        # 混合所有音层
        "[c3][e3][g3][c4][f3][a3]amix=inputs=6:duration=longest:normalize=0,"
        # 低通滤波让声音更柔和
        "lowpass=f=800,"
        # 添加混响效果
        "aecho=0.8:0.7:500:0.3,"
        # 淡入淡出
        f"afade=t=in:st=0:d=3,afade=t=out:st={duration_s - 4}:d=4,"
        # 音量控制（背景音乐要小声）
        "volume=0.15"
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", filter_str,
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(duration_s),
        output_path,
    ]
    print(f"Generating ambient BGM ({duration_s:.0f}s)...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        print(f"BGM generation failed: {r.stderr[:500]}")
        return None
    print(f"BGM generated: {output_path}")
    return output_path


def main():
    print("=" * 60)
    print("加拿大心酸史 — 完整版渲染")
    print("=" * 60)

    # 构建脚本
    script = build_script()
    total_dur = script["total_duration"]
    print(f"\nScript: {len(script['clips'])} clips, {total_dur:.0f}s ({total_dur/60:.1f} min)")
    print(f"Subtitles: {len(script['subtitles'])} segments")

    if total_dur < 180:
        print(f"WARNING: Total duration {total_dur:.0f}s < 180s target")

    # 生成 BGM
    bgm_path = str(OUTPUT_DIR / "ambient_bgm.m4a")
    bgm = generate_ambient_bgm(total_dur + 5, bgm_path)

    # 空的 materials dict（我们用 matched_path 直接指定路径）
    materials = {}

    # 渲染配置 — 横屏 1920x1080
    config = {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "crf": 20,  # 较高质量
        "preset": "medium",
        "subtitle_size": 48,
        "subtitle_font": "PingFangSC-Regular",
        "enable_skin_smooth": False,  # 无人脸，跳过磨皮
        "enable_color_grading": True,
        "transition_style": "none",
        "timeout_stage_sec": 1800,
    }

    # 创建渲染管道
    def on_progress(info):
        if "message" in info:
            print(f"  [{info.get('progress', '?')}%] {info['message']}")

    pipeline = RenderPipeline(config, on_progress=on_progress)

    print(f"\nStarting render → {FINAL_OUTPUT}")
    print("This may take 10-20 minutes for a 3+ minute video...\n")

    try:
        result = pipeline.render(
            script=script,
            materials=materials,
            output_path=FINAL_OUTPUT,
            bgm_path=bgm if bgm else None,
        )
        print(f"\n{'=' * 60}")
        print(f"DONE! Output: {result}")

        # 验证输出
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration,size", "-of", "json", result],
            capture_output=True, text=True
        )
        info = json.loads(r.stdout).get("format", {})
        dur = float(info.get("duration", 0))
        size_mb = int(info.get("size", 0)) / (1024 * 1024)
        print(f"Duration: {dur:.1f}s ({dur/60:.1f} min)")
        print(f"File size: {size_mb:.1f} MB")
        print(f"{'=' * 60}")

    except Exception as e:
        print(f"\nRender failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
