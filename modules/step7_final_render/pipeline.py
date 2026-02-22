#!/usr/bin/env python3
"""
渲染管道模块
流程：素材拼接 → 磨皮 → 调色 → 字幕压制 → 音频混合

来源：opencut/render/pipeline.py + local auto_render.py 音频混合逻辑
"""

import json
import re
import select
import subprocess
import tempfile
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from .beauty import AdvancedBeautyFilter, apply_beauty_filter_simple


class RenderPipeline:
    """
    渲染管道

    执行顺序：
    1. concat_materials  — 逐片段 CFR 编码 + concat（修复 iPhone VFR 问题）
    2. apply_beauty      — 频率分解磨皮（检测到人脸时）
    3. apply_color       — FFmpeg 调色（eq + curves）
    4. apply_subtitles   — 硬字幕（libass 可用则 FFmpeg，否则 PIL/cv2 fallback）
    5. mix_audio         — FFmpeg 音频混合（原声 + BGM + 旁白）
    """

    def __init__(self, config: Dict, on_progress=None, should_cancel=None):
        self.config = config
        self.ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe = shutil.which("ffprobe") or "ffprobe"
        self._temp_dir = Path(tempfile.mkdtemp(prefix="opencut_render_"))
        self._ffmpeg_filters = None  # lazy cache
        self._on_progress = on_progress
        self._should_cancel = should_cancel

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def render(
        self,
        script: Dict,
        materials: Dict,
        output_path: str,
        bgm_path: Optional[str] = None,
        narration_path: Optional[str] = None,
    ) -> str:
        """
        全流程渲染

        Args:
            script:      脚本 JSON（含 clips / subtitles）
            materials:   素材索引 JSON
            output_path: 最终输出路径
            bgm_path:    背景音乐路径（可选）
            narration_path: 旁白音频路径（可选）

        Returns:
            最终视频路径
        """
        clips = script.get("clips", [])
        subtitles = script.get("subtitles", [])
        has_face = any(c.get("has_face", False) for c in clips)

        base = str(self._temp_dir / "stage")

        # 1. 拼接（CFR 强制重编码，修复 iPhone VFR 问题）
        concat_out = self._concat_materials(clips, materials, base)

        # 2. 磨皮（有人脸才处理）
        beauty_out = self._apply_beauty(concat_out, base, has_face)

        # 3. 调色
        color_out = self._apply_color_grading(beauty_out, base)

        # 4. 字幕
        sub_out = self._apply_subtitles(color_out, subtitles, base)

        # 5. 音频混合
        final = self._mix_audio(sub_out, output_path, bgm_path, narration_path)

        self._cleanup()
        print(f"\n🎉 渲染完成: {final}")
        return final

    # ------------------------------------------------------------------
    # Public stage API (stable surface for workflow/adapters)
    # ------------------------------------------------------------------

    def concat_materials(self, clips: List[Dict], materials: Dict, base: str) -> str:
        return self._concat_materials(clips, materials, base)

    def apply_beauty(self, input_path: str, base: str, has_face: bool) -> str:
        return self._apply_beauty(input_path, base, has_face)

    def apply_color_grading(self, input_path: str, base: str) -> str:
        return self._apply_color_grading(input_path, base)

    def apply_subtitles(self, input_path: str, subtitles: List[Dict], base: str) -> str:
        return self._apply_subtitles(input_path, subtitles, base)

    def mix_audio(
        self,
        input_path: str,
        output_path: str,
        bgm_path: Optional[str],
        narration_path: Optional[str],
    ) -> str:
        return self._mix_audio(input_path, output_path, bgm_path, narration_path)

    # ------------------------------------------------------------------
    # 各阶段
    # ------------------------------------------------------------------

    def _concat_materials(self, clips: List[Dict], materials: Dict, base: str) -> str:
        """
        拼接素材片段。
        修复 Bug A：iPhone HEVC VFR 时间戳问题。
        每个片段单独 re-encode 为 CFR H264，再通过 concat demuxer 合并。
        """
        w = self.config.get("width", 1080)
        h = self.config.get("height", 1920)
        fps = self.config.get("fps", 30)
        crf = self.config.get("crf", 18)
        preset = self.config.get("preset", "medium")

        seg_dir = self._temp_dir / "segs"
        seg_dir.mkdir(exist_ok=True)
        segs: List[str] = []
        seg_durations: List[float] = []

        for i, clip in enumerate(clips):
            video_path = self._resolve_material_path(clip, materials)
            if not video_path:
                print(f"  ⚠️  片段 {i+1} 找不到素材路径，跳过")
                continue

            ss = clip.get("source_start", 0) or 0
            se = clip.get("source_end") or clip.get("end_time")
            dur = (se - ss) if se is not None else clip.get("duration", 5)

            seg_out = str(seg_dir / f"seg_{i:03d}.mp4")
            # scale + pad to target resolution, force CFR fps, H264 re-encode
            vf = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                  f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
                  f"fps={fps}")
            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(ss), "-i", video_path,
                "-t", str(dur),
                "-vf", vf,
                "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
                "-pix_fmt", "yuv420p",
                "-an",  # 去掉原始音轨，BGM 在 Stage 5 叠加
                seg_out,
            ]
            r = subprocess.run(cmd, capture_output=True)
            if r.returncode == 0:
                segs.append(seg_out)
                try:
                    seg_durations.append(max(float(dur), 0.05))
                except Exception:
                    seg_durations.append(1.0)
            else:
                print(f"  ⚠️  片段 {i+1} 编码失败: {r.stderr[-200:].decode(errors='replace')}")

        if not segs:
            raise RuntimeError("没有有效片段，无法拼接")

        output = base + "_concat.mp4"
        transition_style = str(self.config.get("transition_style", "none") or "none").strip().lower()
        transition_duration = self.config.get("transition_duration", 0.0)
        try:
            transition_duration = float(transition_duration or 0.0)
        except Exception:
            transition_duration = 0.0

        use_transition = (
            len(segs) >= 2
            and transition_style not in {"none", "cut", ""}
            and transition_duration > 0
            and self._ffmpeg_has_filter("xfade")
        )
        if use_transition:
            self._concat_with_transition(
                segs=segs,
                durations=seg_durations,
                output=output,
                transition_style=transition_style,
                transition_duration=transition_duration,
                fps=fps,
                crf=crf,
                preset=preset,
            )
        else:
            concat_file = str(self._temp_dir / "concat.txt")
            with open(concat_file, "w", encoding="utf-8") as f:
                for s in segs:
                    f.write(f"file '{s}'\n")

            cmd2 = [
                self.ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output,
            ]
            self._run(
                cmd2,
                "素材拼接",
                input_path=segs[0] if segs else None,
                timeout_seconds=float(self.config.get("timeout_concat_sec", 1500)),
            )
        return output

    def _apply_beauty(self, input_path: str, base: str, has_face: bool) -> str:
        """逐帧磨皮（仅当检测到人脸时）"""
        if not has_face:
            return input_path

        output = base + "_beauty.mp4"

        try:
            beauty = AdvancedBeautyFilter(
                smooth_strength=self.config.get("skin_smooth_strength", 0.8),
                pore_reduction=self.config.get("pore_reduction", 0.6),
            )
            beauty.process_video(input_path, output)
            return output
        except Exception:
            # Bug E 修复：捕获所有异常（不只是 ImportError），fallback 到 smartblur
            print("  磨皮处理失败，使用简易磨皮（FFmpeg smartblur）")
            return self._apply_beauty_fallback(input_path, base)

    def _apply_beauty_fallback(self, input_path: str, base: str) -> str:
        """简易磨皮 fallback（FFmpeg smartblur）"""
        output = base + "_beauty_simple.mp4"
        strength = self.config.get("skin_smooth_strength", 0.5)
        cmd = [
            self.ffmpeg, "-y", "-i", input_path,
            "-vf", f"smartblur=lr={strength * 2}:ls=-1.0",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            # Bug D 修复：用条件音频 map，无音频轨时不崩溃
            "-map", "0:v", "-map", "0:a?",
            "-c:a", "copy", output,
        ]
        self._run(
            cmd,
            "简易磨皮",
            input_path=input_path,
            timeout_seconds=float(self.config.get("timeout_stage_sec", 900)),
        )
        return output

    def _apply_color_grading(self, input_path: str, base: str) -> str:
        """调色（旅游 vlog 风格：高对比度 + 高饱和 + 冷色调）"""
        if not bool(self.config.get("enable_color_grading", True)):
            return input_path

        output = base + "_color.mp4"
        preset = str(self.config.get("aesthetic_preset", "travel_story") or "travel_story").strip().lower()
        if bool(self.config.get("enable_skill_enhance", True)):
            preset_filters = {
                "travel_story": "eq=contrast=1.10:saturation=1.14:brightness=0.02,"
                                "curves=r='0/0 0.45/0.42 1/1':g='0/0 0.5/0.5 1/1':b='0/0 0.5/0.56 1/1',"
                                "unsharp=5:5:0.4:5:5:0.0",
                "cinematic": "eq=contrast=1.08:saturation=1.08:brightness=-0.01,"
                             "curves=r='0/0 0.4/0.38 1/1':g='0/0 0.45/0.44 1/1':b='0/0 0.5/0.58 1/1',"
                             "colorbalance=rs=0.02:gs=-0.01:bs=-0.02",
                "vibrant": "eq=contrast=1.12:saturation=1.25:brightness=0.03,"
                           "unsharp=5:5:0.35:5:5:0.0",
                "natural": "eq=contrast=1.03:saturation=1.05:brightness=0.01",
            }
        else:
            preset_filters = {
                "travel_story": "eq=contrast=1.08:saturation=1.10:brightness=0.01",
                "cinematic": "eq=contrast=1.06:saturation=1.04:brightness=-0.01",
                "vibrant": "eq=contrast=1.08:saturation=1.15:brightness=0.02",
                "natural": "eq=contrast=1.02:saturation=1.03:brightness=0.0",
            }
        vf_filter = preset_filters.get(preset, preset_filters["travel_story"])

        cmd = [
            self.ffmpeg, "-y", "-i", input_path,
            "-vf", vf_filter,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            # Bug D 修复：条件音频 map
            "-map", "0:v", "-map", "0:a?",
            "-c:a", "copy", output,
        ]
        self._run(
            cmd,
            "调色",
            input_path=input_path,
            timeout_seconds=float(self.config.get("timeout_stage_sec", 900)),
        )
        return output

    def _concat_with_transition(
        self,
        segs: List[str],
        durations: List[float],
        output: str,
        transition_style: str,
        transition_duration: float,
        fps: int,
        crf: int,
        preset: str,
    ):
        """使用 xfade 做视频转场（无音频，音频在 Stage 5 混音）。"""
        if len(segs) < 2:
            shutil.copy(segs[0], output)
            return

        supported = {"fade", "smoothleft", "smoothright", "circleopen", "pixelize"}
        style = transition_style if transition_style in supported else "fade"

        valid_durations = [max(float(d), 0.2) for d in durations[:len(segs)]]
        if len(valid_durations) < len(segs):
            valid_durations.extend([1.0] * (len(segs) - len(valid_durations)))

        min_clip = min(valid_durations)
        d = max(0.05, min(float(transition_duration), 1.5, min_clip * 0.45))

        if len(segs) > 24:
            print("  ⚠️  片段过多，转场自动降级为硬切拼接")
            concat_file = str(self._temp_dir / "concat_xfade_fallback.txt")
            with open(concat_file, "w", encoding="utf-8") as f:
                for s in segs:
                    f.write(f"file '{s}'\n")
            cmd_fallback = [
                self.ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output,
            ]
            self._run(
                cmd_fallback,
                "素材拼接",
                input_path=segs[0] if segs else None,
                timeout_seconds=float(self.config.get("timeout_concat_sec", 1500)),
            )
            return

        cmd = [self.ffmpeg, "-y"]
        for seg in segs:
            cmd.extend(["-i", seg])

        filters = []
        last_label = "[0:v]"
        cumulative = 0.0
        for i in range(1, len(segs)):
            cumulative += valid_durations[i - 1]
            offset = max(cumulative - d * i, 0.0)
            out_label = f"[v{i}]"
            filters.append(
                f"{last_label}[{i}:v]xfade=transition={style}:duration={d:.3f}:offset={offset:.3f}{out_label}"
            )
            last_label = out_label
        filters.append(f"{last_label}format=yuv420p[vout]")

        cmd.extend([
            "-filter_complex", ";".join(filters),
            "-map", "[vout]",
            "-r", str(fps),
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-an",
            output,
        ])
        self._run(
            cmd,
            f"素材拼接 + 转场({style})",
            input_path=segs[0] if segs else None,
            timeout_seconds=float(self.config.get("timeout_concat_sec", 1500)),
        )

    def _apply_subtitles(self, input_path: str, subtitles: List[Dict], base: str) -> str:
        """
        硬字幕压制（双语）。
        Bug C 修复：先检测 FFmpeg filter 可用性；
        libass/subtitles 不可用时自动切换到 PIL+cv2 fallback。
        """
        if not subtitles:
            return input_path

        srt_path = str(self._temp_dir / "subtitle.srt")
        self._generate_srt(subtitles, srt_path)
        output = base + "_sub.mp4"

        # 尝试 FFmpeg subtitles filter
        if self._ffmpeg_has_filter("subtitles"):
            font = self.config.get("subtitle_font", "PingFangSC-Regular")
            size = self.config.get("subtitle_size", 56)
            cmd = [
                self.ffmpeg, "-y", "-i", input_path,
                "-vf", (
                    f"subtitles='{srt_path}':"
                    f"force_style='FontName={font},FontSize={size},"
                    f"PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,"
                    f"Outline=2,Shadow=1,Alignment=2,MarginV=50'"
                ),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-map", "0:v", "-map", "0:a?", "-c:a", "copy",
                output,
            ]
            try:
                self._run(
                    cmd,
                    "字幕压制",
                    input_path=input_path,
                    timeout_seconds=float(self.config.get("timeout_stage_sec", 900)),
                )
                return output
            except RuntimeError:
                pass  # fallback below

        # PIL/cv2 fallback
        if HAS_CV2 and HAS_PIL:
            print("  libass 不可用，使用 PIL+cv2 字幕渲染")
            return self._apply_subtitles_cv2(input_path, subtitles, output)

        print("  ⚠️  字幕渲染跳过（libass / cv2 均不可用）")
        return input_path

    def _apply_subtitles_cv2(
        self, input_path: str, subtitles: List[Dict], output: str
    ) -> str:
        """PIL + cv2 字幕渲染 fallback（无需 libass）"""
        import cv2 as _cv2  # noqa
        import numpy as _np  # noqa
        from PIL import Image as _Image, ImageDraw as _Draw, ImageFont as _Font

        font_size_cn = self.config.get("subtitle_size", 56)
        font_size_en = max(24, font_size_cn // 2)
        font_path = "/System/Library/Fonts/PingFang.ttc"

        try:
            font_cn = _Font.truetype(font_path, size=font_size_cn)
            font_en = _Font.truetype(font_path, size=font_size_en)
        except Exception:
            font_cn = _Font.load_default()
            font_en = _Font.load_default()

        cap = _cv2.VideoCapture(input_path)
        fps = cap.get(_cv2.CAP_PROP_FPS) or 30.0
        w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT) or 0)

        tmp_vid = str(self._temp_dir / "sub_nofont.mp4")
        out_writer = _cv2.VideoWriter(
            tmp_vid, _cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h)
        )

        frame_idx = 0
        while True:
            if callable(self._should_cancel):
                try:
                    if bool(self._should_cancel()):
                        cap.release()
                        out_writer.release()
                        raise RuntimeError("__CANCELLED__")
                except RuntimeError:
                    raise
                except Exception:
                    pass
            ret, frame = cap.read()
            if not ret:
                break
            t = frame_idx / fps
            active = next(
                ((s.get("cn_text", ""), s.get("en_text", ""))
                 for s in subtitles
                 if s.get("start_time", 0) <= t <= s.get("end_time", 0)),
                None,
            )
            if active:
                cn_text, en_text = active
                pil = _Image.fromarray(_cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB))
                draw = _Draw.Draw(pil)
                # Chinese line
                bbox = draw.textbbox((0, 0), cn_text, font=font_cn)
                cx = (w - (bbox[2] - bbox[0])) // 2
                cy = h - 200
                draw.text((cx + 2, cy + 2), cn_text, font=font_cn, fill=(0, 0, 0, 180))
                draw.text((cx, cy), cn_text, font=font_cn, fill=(255, 255, 255))
                # English line
                if en_text:
                    ebbox = draw.textbbox((0, 0), en_text, font=font_en)
                    ex = (w - (ebbox[2] - ebbox[0])) // 2
                    ey = cy + font_size_cn + 8
                    draw.text((ex + 1, ey + 1), en_text, font=font_en, fill=(0, 0, 0, 150))
                    draw.text((ex, ey), en_text, font=font_en, fill=(255, 255, 255, 220))
                frame = _cv2.cvtColor(_np.array(pil), _cv2.COLOR_RGB2BGR)
            out_writer.write(frame)
            frame_idx += 1
            if callable(self._on_progress) and total_frames > 0 and frame_idx % max(total_frames // 20, 1) == 0:
                pct = int(max(1, min((frame_idx / total_frames) * 100, 99)))
                try:
                    self._on_progress("字幕压制", pct, f"{frame_idx}/{total_frames} frames")
                except Exception:
                    pass

        cap.release()
        out_writer.release()

        # Re-encode with H264 and copy audio from original
        cmd = [
            self.ffmpeg, "-y",
            "-i", tmp_vid,
            "-i", input_path,
            "-map", "0:v", "-map", "1:a?",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast",
            "-c:a", "copy",
            output,
        ]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(f"  ⚠️  字幕 re-encode 失败，使用无字幕版本")
            return input_path
        return output

    def _mix_audio(
        self,
        input_path: str,
        output_path: str,
        bgm_path: Optional[str],
        narration_path: Optional[str],
    ) -> str:
        """
        音频混合：原声 + BGM + 旁白
        Bug B 修复：先检测输入视频是否含音频流，避免 [0:a] 引用崩溃。
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        has_audio = self._has_audio_stream(input_path)
        bgm_vol = self.config.get("bgm_volume", 0.3)
        nar_vol = self.config.get("narration_volume", 1.0)
        bitrate = self.config.get("audio_bitrate", "192k")

        # ── 无 BGM 也无旁白 ──────────────────────────────────────────
        if not bgm_path and not narration_path:
            if has_audio:
                cmd = [self.ffmpeg, "-y", "-i", input_path,
                       "-c:v", "copy", "-c:a", "aac", "-b:a", bitrate, output_path]
            else:
                # 无音频直接复制视频
                cmd = [self.ffmpeg, "-y", "-i", input_path, "-c:v", "copy",
                       "-an", output_path]
            self._run(
                cmd,
                "输出封装",
                input_path=input_path,
                timeout_seconds=float(self.config.get("timeout_audio_sec", 480)),
            )
            return output_path

        # ── 构建 inputs 和 filter_complex ───────────────────────────
        # inputs[0] = 视频文件（可能无音频）
        # inputs[1] = BGM（若有）
        # inputs[2] = narration（若有）
        inputs = [input_path]
        if bgm_path:
            inputs.append(bgm_path)
        if narration_path:
            inputs.append(narration_path)

        audio_inputs = []  # filter_complex 中的音频 input 标签

        idx = 0
        if has_audio:
            audio_inputs.append((f"[{idx}:a]", 0.8))
        # BGM / narration 的 input 索引
        extra_start = 1
        if bgm_path:
            audio_inputs.append((f"[{extra_start}:a]", bgm_vol))
            extra_start += 1
        if narration_path:
            audio_inputs.append((f"[{extra_start}:a]", nar_vol))

        if not audio_inputs:
            # 视频无音频 + 无 BGM/narration（理论上不会走到这里，但保险）
            cmd = [self.ffmpeg, "-y", "-i", input_path,
                   "-c:v", "copy", "-an", output_path]
            self._run(
                cmd,
                "输出封装（无音频）",
                input_path=input_path,
                timeout_seconds=float(self.config.get("timeout_audio_sec", 480)),
            )
            return output_path

        # 构建 filter_complex
        chains = []
        mix_labels = []
        for i, (label, vol) in enumerate(audio_inputs):
            out_label = f"[a{i}]"
            chains.append(f"{label}volume={vol}{out_label}")
            mix_labels.append(out_label)

        mix_in = "".join(mix_labels)
        n = len(mix_labels)
        chains.append(f"{mix_in}amix=inputs={n}:duration=first:dropout_transition=2[aout]")
        af = ";".join(chains)

        cmd = [self.ffmpeg, "-y"]
        for inp in inputs:
            cmd.extend(["-i", inp])
        cmd.extend([
            "-filter_complex", af,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", bitrate,
            output_path,
        ])
        self._run(
            cmd,
            "音频混合",
            input_path=input_path,
            timeout_seconds=float(self.config.get("timeout_audio_sec", 480)),
        )
        return output_path

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def _has_audio_stream(self, path: str) -> bool:
        """检测视频文件是否包含音频流"""
        try:
            r = subprocess.run(
                [self.ffprobe, "-v", "quiet",
                 "-select_streams", "a",
                 "-show_entries", "stream=codec_type",
                 "-of", "default", path],
                capture_output=True, text=True, timeout=10,
            )
            return "codec_type=audio" in r.stdout
        except Exception:
            return False

    def _ffmpeg_has_filter(self, filter_name: str) -> bool:
        """检测 FFmpeg 是否编译了指定 filter（lazy cache）"""
        if self._ffmpeg_filters is None:
            try:
                r = subprocess.run(
                    [self.ffmpeg, "-filters"],
                    capture_output=True, text=True, timeout=10,
                )
                self._ffmpeg_filters = r.stdout + r.stderr
            except Exception:
                self._ffmpeg_filters = ""
        return filter_name in self._ffmpeg_filters

    def _generate_srt(self, subtitles: List[Dict], srt_path: str):
        """生成双语 SRT 字幕文件"""
        lines = []
        for i, sub in enumerate(subtitles, 1):
            start = self._seconds_to_srt(sub.get("start_time", 0))
            end = self._seconds_to_srt(sub.get("end_time", 0))
            cn = sub.get("cn_text", "")
            en = sub.get("en_text", "")
            text = f"{cn}\n{en}" if en else cn
            lines.append(f"{i}\n{start} --> {end}\n{text}\n")

        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))

    def _seconds_to_srt(self, seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    def _resolve_material_path(self, clip: Dict, materials: Dict) -> Optional[str]:
        """从素材索引中解析视频路径"""
        vid = clip.get("video_id") or clip.get("material_id") or clip.get("path")
        if not vid:
            return None
        if Path(vid).exists():
            return vid
        videos = materials.get("videos", {})
        if vid in videos:
            return videos[vid].get("file_info", {}).get("path")
        return None

    @staticmethod
    def _parse_ffmpeg_time(line: str) -> Optional[float]:
        if not line:
            return None
        match = re.search(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", line)
        if not match:
            return None
        try:
            hh = int(match.group(1))
            mm = int(match.group(2))
            ss = float(match.group(3))
            return hh * 3600 + mm * 60 + ss
        except Exception:
            return None

    def _probe_duration(self, path: Optional[str]) -> Optional[float]:
        if not path:
            return None
        try:
            r = subprocess.run(
                [
                    self.ffprobe,
                    "-v",
                    "quiet",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                capture_output=True,
                text=True,
                timeout=12,
            )
            if r.returncode != 0:
                return None
            duration = float((r.stdout or "").strip())
            if duration <= 0:
                return None
            return duration
        except Exception:
            return None

    def _run(
        self,
        cmd: List[str],
        stage_name: str,
        input_path: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        """运行 FFmpeg 命令（支持进度回调、取消、超时 watchdog）。"""
        print(f"  [{stage_name}] 处理中...")

        if timeout_seconds is None:
            timeout_seconds = float(self.config.get("timeout_stage_sec", 900))
        duration = self._probe_duration(input_path)
        if callable(self._on_progress):
            try:
                self._on_progress(stage_name, 1, "start")
            except Exception:
                pass

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="ignore",
            bufsize=1,
        )
        start_at = time.time()
        last_progress = -1
        last_line = ""

        while True:
            if callable(self._should_cancel):
                try:
                    if bool(self._should_cancel()):
                        process.kill()
                        process.wait(timeout=2)
                        raise RuntimeError("__CANCELLED__")
                except RuntimeError:
                    raise
                except Exception:
                    pass

            elapsed = time.time() - start_at
            if timeout_seconds and elapsed > float(timeout_seconds):
                process.kill()
                try:
                    process.wait(timeout=2)
                except Exception:
                    pass
                raise RuntimeError(f"{stage_name} 超时: {float(timeout_seconds):.1f}s")

            line = ""
            if process.stderr:
                try:
                    ready, _, _ = select.select([process.stderr], [], [], 0.2)
                    if ready:
                        line = process.stderr.readline()
                except Exception:
                    line = process.stderr.readline()
            if line:
                last_line = line.strip()
                if duration and callable(self._on_progress):
                    ts = self._parse_ffmpeg_time(line)
                    if ts is not None:
                        progress = int(max(1, min((ts / duration) * 100.0, 99.0)))
                        if progress != last_progress:
                            last_progress = progress
                            try:
                                self._on_progress(
                                    stage_name,
                                    progress,
                                    f"{ts:.1f}s/{duration:.1f}s",
                                )
                            except Exception:
                                pass
            elif process.poll() is not None:
                break
            else:
                time.sleep(0.05)

        ret = process.wait()
        if ret != 0:
            raise RuntimeError(f"{stage_name} 失败:\n{last_line[:500]}")
        if callable(self._on_progress):
            try:
                self._on_progress(stage_name, 100, "done")
            except Exception:
                pass

    def _cleanup(self):
        if self._temp_dir.exists():
            shutil.rmtree(self._temp_dir)
