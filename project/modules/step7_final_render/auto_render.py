#!/usr/bin/env python3
"""
VideoEditer - 全自动渲染引擎
FFmpeg 本地渲染：磨皮、调色、字幕压制、BGM 混合
替代剪映手动操作，实现真正的自动化
"""

import json
import logging
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import tempfile
import shutil

logger = logging.getLogger(__name__)

try:
    from render.beauty import AdvancedBeautyFilter
    HAS_ADVANCED_BEAUTY = True
except ImportError:
    HAS_ADVANCED_BEAUTY = False


@dataclass
class RenderConfig:
    """渲染配置"""
    # 视频设置
    width: int = 1080
    height: int = 1920
    fps: int = 30
    video_bitrate: str = "8M"
    
    # 音频设置
    audio_bitrate: str = "192k"
    bgm_volume: float = 0.3
    narration_volume: float = 1.0
    
    # 字幕设置
    subtitle_font: str = "PingFangSC-Regular"
    subtitle_size: int = 56
    subtitle_color: str = "#FFFFFF"
    subtitle_outline: str = "#000000"
    
    # 滤镜设置
    enable_skin_smooth: bool = True
    enable_color_grading: bool = True
    skin_smooth_strength: float = 0.5
    lut_path: Optional[str] = None
    
    # 输出设置
    output_format: str = "mp4"
    crf: int = 18  # 质量 (0-51, 越小越好)
    preset: str = "slow"  # 编码速度

    # 硬件加速（由 hardware.encoding_strategy 自动填充）
    video_encoder: str = "libx264"        # e.g. "h264_videotoolbox"
    hwaccel: Optional[str] = None         # e.g. "videotoolbox"
    encoder_extra_args: Optional[List[str]] = None  # additional ffmpeg flags

    def apply_hardware_profile(self) -> "RenderConfig":
        """Auto-detect hardware and update encoder settings in-place."""
        try:
            from modules.hardware.detector import get_system_profile
            from modules.hardware.encoding_strategy import choose_encoder
            profile = get_system_profile()
            params = choose_encoder(profile)
            self.video_encoder = params.video_encoder
            self.hwaccel = params.hwaccel
            self.encoder_extra_args = list(params.extra_args)
        except Exception:
            pass  # keep CPU defaults
        return self

    @classmethod
    def from_aesthetic_preset(cls, aesthetic: str = "travel_story", **overrides) -> "RenderConfig":
        """Create RenderConfig with orientation matching the aesthetic preset.

        Uses PRESET_ORIENTATIONS from refinement.py to set width/height.
        """
        try:
            from modules.capabilities.refinement import PRESET_ORIENTATIONS
            orientation = PRESET_ORIENTATIONS.get(aesthetic, "vertical")
        except ImportError:
            orientation = "vertical"
        if orientation == "horizontal":
            defaults = {"width": 1920, "height": 1080}
        else:
            defaults = {"width": 1080, "height": 1920}
        defaults.update(overrides)
        return cls(**defaults)


class FFmpegRenderer:
    """FFmpeg 渲染器"""

    def __init__(self, config: RenderConfig = None):
        self.config = config or RenderConfig()
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()
        self._has_subtitles_filter = self._check_subtitles_filter()

    def _encoder_args(self) -> List[str]:
        """Build encoder arguments from config, respecting hardware acceleration."""
        c = self.config
        encoder = c.video_encoder or "libx264"
        args = ["-c:v", encoder]

        if encoder == "libx264":
            args.extend(["-crf", str(c.crf), "-preset", c.preset])
        elif encoder == "h264_videotoolbox":
            # VideoToolbox uses -q:v instead of -crf (range ~1-100, lower=better)
            vt_quality = max(1, min(100, int(c.crf * 2)))
            args.extend(["-q:v", str(vt_quality)])
        elif encoder == "h264_nvenc":
            args.extend(["-cq", str(c.crf)])

        args.extend(["-b:v", c.video_bitrate, "-pix_fmt", "yuv420p"])

        if c.encoder_extra_args:
            args.extend(c.encoder_extra_args)
        return args

    def _check_subtitles_filter(self) -> bool:
        """检测当前 FFmpeg 是否支持 subtitles filter（需要 libass）"""
        result = subprocess.run(
            [self.ffmpeg_path, "-filters"],
            capture_output=True, text=True, timeout=15
        )
        has_it = " subtitles " in result.stdout or "\tsubtitles " in result.stdout
        if not has_it:
            logger.info("FFmpeg 未编译 libass，字幕将跳过（安装：brew install libass && brew reinstall ffmpeg）")
        return has_it
        
    def _find_ffmpeg(self) -> str:
        """查找 FFmpeg 可执行文件"""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("FFmpeg 未安装或未在 PATH 中")
        return ffmpeg
    
    def _find_ffprobe(self) -> str:
        """查找 FFprobe 可执行文件"""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise RuntimeError("FFprobe 未安装或未在 PATH 中")
        return ffprobe
    
    def get_video_info(self, video_path: str) -> Dict:
        """获取视频信息"""
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,r_frame_rate",
            "-show_entries", "format=duration",
            "-of", "json",
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"无法获取视频信息: {result.stderr}")
        
        return json.loads(result.stdout)
    
    def build_filter_complex(
        self,
        has_subtitle: bool = False,
        has_skin_smooth: bool = False,
        has_color_grading: bool = False,
        subtitle_srt: Optional[str] = None
    ) -> str:
        """
        构建 FFmpeg filter_complex
        
        滤镜链顺序：
        1. 缩放/裁剪 (scale/crop)
        2. 磨皮 (smartblur/skin detection)
        3. 调色 (lut3d/colorbalance)
        4. 字幕 (subtitles)
        """
        filters = []
        
        # 1. 基础处理：缩放和帧率
        filters.append(f"scale={self.config.width}:{self.config.height}:force_original_aspect_ratio=decrease,pad={self.config.width}:{self.config.height}:(ow-iw)/2:(oh-ih)/2:black")
        filters.append(f"fps={self.config.fps}")
        
        # 2. 磨皮滤镜（仅当启用且检测到人脸）
        # 注意：高级磨皮（频率分解）由 render/beauty.py 在 VideoPipeline 层处理；
        # 此处的 smartblur 作为 fallback（当 beauty.py 不可用时）
        if has_skin_smooth and self.config.enable_skin_smooth:
            strength = self.config.skin_smooth_strength
            filters.append(f"smartblur=lr={strength*2}:ls=-1.0")
        
        # 3. 调色滤镜
        if has_color_grading and self.config.enable_color_grading:
            if self.config.lut_path and Path(self.config.lut_path).exists():
                # 应用 LUT
                filters.append(f"lut3d='{self.config.lut_path}'")
            else:
                # 默认增强对比度和饱和度（旅游 vlog 风格）
                filters.append("eq=contrast=1.1:saturation=1.2:brightness=0.02")
        
        # 4. 字幕叠加（需要 FFmpeg 编译含 libass，否则跳过）
        if has_subtitle and subtitle_srt and Path(subtitle_srt).exists() and self._has_subtitles_filter:
            # ASS 颜色格式为 &H00BBGGRR&（BGR，非 RGB）
            def rgb_to_ass(hex_color: str) -> str:
                h = hex_color.lstrip('#')
                r, g, b = h[0:2], h[2:4], h[4:6]
                return f"00{b}{g}{r}".upper()
            # FFmpeg 8+ 要求用 filename= 显式键名；路径中不含单引号
            escaped = subtitle_srt.replace("'", "\\'")
            subtitle_filter = (
                f"subtitles=filename='{escaped}':"
                f"force_style='FontName={self.config.subtitle_font},"
                f"FontSize={self.config.subtitle_size},"
                f"PrimaryColour=&H{rgb_to_ass(self.config.subtitle_color)}&,"
                f"OutlineColour=&H{rgb_to_ass(self.config.subtitle_outline)}&,"
                f"Outline=2,Shadow=1,Alignment=2,MarginV=50'"
            )
            filters.append(subtitle_filter)
        
        return ",".join(filters)
    
    def render_video(
        self,
        input_video: str,
        output_video: str,
        subtitle_srt: Optional[str] = None,
        bgm_audio: Optional[str] = None,
        narration_audio: Optional[str] = None,
        start_time: float = 0,
        end_time: Optional[float] = None,
        has_face: bool = False
    ) -> str:
        """
        渲染单个视频片段
        
        Args:
            input_video: 输入视频路径
            output_video: 输出视频路径
            subtitle_srt: 字幕文件路径 (.srt)
            bgm_audio: 背景音乐路径
            narration_audio: 旁白音频路径
            start_time: 开始时间（秒）
            end_time: 结束时间（秒）
            has_face: 是否包含人脸（决定是否磨皮）
        
        Returns:
            输出视频路径
        """
        output_path = Path(output_video)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 构建视频滤镜
        video_filter = self.build_filter_complex(
            has_subtitle=bool(subtitle_srt),
            has_skin_smooth=has_face,
            has_color_grading=self.config.enable_color_grading,
            subtitle_srt=subtitle_srt
        )
        
        # 构建 FFmpeg 命令
        cmd = [self.ffmpeg_path, "-y"]
        
        # 输入视频
        cmd.extend(["-i", input_video])
        
        # 时间裁剪
        if start_time > 0:
            cmd.extend(["-ss", str(start_time)])
        if end_time:
            duration = end_time - start_time
            cmd.extend(["-t", str(duration)])
        
        # 视频滤镜
        cmd.extend(["-vf", video_filter])
        
        # 视频编码设置
        cmd.extend(self._encoder_args())
        
        # 音频处理
        if bgm_audio or narration_audio:
            # 需要复杂音频混合
            cmd = self._build_audio_mix_cmd(
                input_video, bgm_audio, narration_audio,
                start_time, end_time
            )
        else:
            # 仅复制原音频
            cmd.extend(["-c:a", "aac", "-b:a", self.config.audio_bitrate])
        
        # 输出文件
        cmd.append(str(output_path))
        
        # 执行渲染
        logger.info("渲染: %s", output_path.name)
        logger.info("滤镜: %s...", video_filter[:80])
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

        if result.returncode != 0:
            logger.error("渲染失败: %s", result.stderr)
            raise RuntimeError(f"FFmpeg 渲染失败: {result.stderr[:500]}")
        
        logger.info("完成: %s", output_path)
        return str(output_path)
    
    def _build_audio_mix_cmd(
        self,
        video_path: str,
        bgm_audio: Optional[str],
        narration_audio: Optional[str],
        start_time: float,
        end_time: Optional[float]
    ) -> List[str]:
        """构建音频混合命令"""
        inputs = [video_path]
        if bgm_audio:
            inputs.append(bgm_audio)
        if narration_audio:
            inputs.append(narration_audio)
        
        # 重新构建命令，包含所有输入
        cmd = [self.ffmpeg_path, "-y"]
        
        for inp in inputs:
            cmd.extend(["-i", inp])
        
        # 时间裁剪（对所有输入）
        if start_time > 0:
            cmd.extend(["-ss", str(start_time)])
        if end_time:
            duration = end_time - start_time
            cmd.extend(["-t", str(duration)])
        
        # 构建音频滤镜
        audio_filters = []
        
        if len(inputs) == 1:
            # 只有原视频音频
            audio_filters.append("[0:a]aformat=fltp:44100:stereo[aout]")
        elif len(inputs) == 2:
            # 视频 + BGM 或 视频 + 旁白
            if bgm_audio and not narration_audio:
                # 混合原声和 BGM
                audio_filters.append(
                    f"[0:a]volume=1.0[a0];"
                    f"[1:a]volume={self.config.bgm_volume}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]"
                )
            elif narration_audio and not bgm_audio:
                # 混合原声和旁白
                audio_filters.append(
                    f"[0:a]volume=0.3[a0];"
                    f"[1:a]volume={self.config.narration_volume}[a1];"
                    f"[a0][a1]amix=inputs=2:duration=first[aout]"
                )
        elif len(inputs) == 3:
            # 视频 + BGM + 旁白
            audio_filters.append(
                f"[0:a]volume=0.2[a0];"
                f"[1:a]volume={self.config.bgm_volume}[a1];"
                f"[2:a]volume={self.config.narration_volume}[a2];"
                f"[a0][a1][a2]amix=inputs=3:duration=first:dropout_transition=2[aout]"
            )
        
        cmd.extend(["-filter_complex", "".join(audio_filters)])
        cmd.extend(["-map", "0:v", "-map", "[aout]"])
        cmd.extend(["-c:a", "aac", "-b:a", self.config.audio_bitrate])
        
        return cmd
    
    def concat_videos(self, video_list: List[str], output_video: str) -> str:
        """
        合并多个视频片段
        
        Args:
            video_list: 视频文件路径列表
            output_video: 输出文件路径
        
        Returns:
            输出视频路径
        """
        # 创建 concat 列表文件
        # Escape single quotes per FFmpeg concat demuxer syntax — '\'' terminates
        # the quoted literal, inserts an escaped quote, then reopens. Without
        # this, a filename containing ' could break out of the quoted filename
        # and inject demuxer directives. Callers today only pass server-generated
        # paths, but this is defense-in-depth for future callers.
        def _escape_concat(p: str) -> str:
            return p.replace("'", r"'\''")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for video in video_list:
                # 使用绝对路径并处理特殊字符
                abs_path = str(Path(video).resolve())
                f.write(f"file '{_escape_concat(abs_path)}'\n")
            concat_file = f.name
        
        try:
            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                # 重编码以统一帧率时间基，避免 VFR 拼接断帧
                "-vf", f"fps={self.config.fps}",
                *self._encoder_args(),
                "-c:a", "aac", "-b:a", self.config.audio_bitrate,
                output_video
            ]

            logger.info("合并 %d 个视频片段...", len(video_list))
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
            
            if result.returncode != 0:
                raise RuntimeError(f"合并失败: {result.stderr}")
            
            logger.info("合并完成: %s", output_video)
            return output_video
            
        finally:
            Path(concat_file).unlink(missing_ok=True)


class VideoPipeline:
    """视频渲染流水线"""
    
    def __init__(self, config: RenderConfig = None):
        self.renderer = FFmpegRenderer(config)
        self.temp_dir = Path(tempfile.mkdtemp())
    
    def render_from_script(
        self,
        script_path: str,
        materials_index: str,
        output_path: str
    ) -> str:
        """
        根据脚本渲染完整视频
        
        这是核心接口，替代 generate_jianying_json.py 的手动操作
        """
        # 加载脚本和素材
        with open(script_path, 'r', encoding='utf-8') as f:
            script = json.load(f)
        
        with open(materials_index, 'r', encoding='utf-8') as f:
            materials = json.load(f)
        
        # 渲染每个片段
        segment_files = []
        
        for i, clip in enumerate(script.get("clips", [])):
            logger.info("处理片段 %d/%d", i + 1, len(script["clips"]))
            
            # 查找素材
            video_path = self._find_video_path(clip, materials)
            if not video_path:
                logger.warning("跳过片段 %d: 未找到素材", i + 1)
                continue
            
            # 准备字幕
            subtitle_srt = None
            if i < len(script.get("subtitles", [])):
                sub = script["subtitles"][i]
                subtitle_srt = self._create_subtitle_srt(sub, self.temp_dir)
            
            # 渲染片段
            segment_output = self.temp_dir / f"segment_{i:03d}.mp4"
            
            has_face = clip.get("has_face", False)

            # 高级磨皮：优先用频率分解（render/beauty.py），fallback 到 FFmpeg smartblur
            beauty_output = None
            src_start = clip.get("source_start", 0)
            src_end = clip.get("source_end")

            if has_face and self.renderer.config.enable_skin_smooth and HAS_ADVANCED_BEAUTY:
                try:
                    beauty_filter = AdvancedBeautyFilter(
                        smooth_strength=self.renderer.config.skin_smooth_strength
                    )
                    # Step 1: 先用 FFmpeg 裁剪到正确时间段（保留音频），同时强制 30fps CFR
                    # -r 30 -vsync cfr 解决 iPhone HEVC VFR（600 tbr）导致的卡顿/断帧
                    clipped = str(self.temp_dir / f"clipped_{i:03d}.mp4")
                    clip_cmd = [self.renderer.ffmpeg_path, "-y",
                                "-ss", str(src_start), "-i", video_path]
                    if src_end:
                        clip_cmd.extend(["-t", str(src_end - src_start)])
                    clip_cmd.extend(["-r", "30", "-vsync", "cfr",
                                     *self.renderer._encoder_args(),
                                     "-c:a", "aac", clipped])
                    subprocess.run(clip_cmd, capture_output=True, check=True, timeout=300)

                    # Step 2: 磨皮（仅视频）
                    beauty_vid_only = str(self.temp_dir / f"beauty_vid_{i:03d}.mp4")
                    beauty_filter.process_video(clipped, beauty_vid_only)

                    # Step 3: 把原始音频贴回磨皮后的视频
                    beauty_output = str(self.temp_dir / f"beauty_{i:03d}.mp4")
                    merge_cmd = [self.renderer.ffmpeg_path, "-y",
                                 "-i", beauty_vid_only, "-i", clipped,
                                 "-map", "0:v", "-map", "1:a?",
                                 "-c:v", "copy", "-c:a", "copy",
                                 beauty_output]
                    subprocess.run(merge_cmd, capture_output=True, check=True, timeout=300)
                    logger.info("磨皮: 频率分解（高级）")
                except Exception as e:
                    logger.warning("磨皮: 降级到 smartblur (%s)", e)
                    beauty_output = None

            render_input = beauty_output or video_path
            # 已磨皮时 start/end 已包含在 beauty_output 中，不再重复裁剪
            actual_start = 0 if beauty_output else src_start
            actual_end = None if beauty_output else src_end

            self.renderer.render_video(
                input_video=render_input,
                output_video=str(segment_output),
                subtitle_srt=subtitle_srt,
                bgm_audio=None,  # BGM 在合并后统一混入完整视频
                narration_audio=script.get("narration", {}).get("path"),
                start_time=actual_start,
                end_time=actual_end,
                has_face=has_face and not beauty_output  # 已磨皮则不再 smartblur
            )
            
            segment_files.append(str(segment_output))
        
        # 合并所有片段
        concat_output = output_path  # 默认直接输出到目标
        subtitles = script.get("subtitles", [])
        need_sub_post = subtitles and not self.renderer._has_subtitles_filter

        if need_sub_post:
            # 字幕将在合并后由 Python 处理，先输出到临时文件
            concat_output = str(self.temp_dir / "concat_raw.mp4")

        if len(segment_files) == 1:
            shutil.copy(segment_files[0], concat_output)
        elif len(segment_files) > 1:
            self.renderer.concat_videos(segment_files, concat_output)
        else:
            raise RuntimeError("没有可渲染的片段")

        # PIL 字幕烧录（libass 不可用时的 fallback）
        if need_sub_post:
            logger.info("PIL 字幕烧录（libass 不可用，使用 Python 实现）")
            self._burn_subtitles_python(concat_output, subtitles, output_path)

        # BGM 混合（全视频，在字幕处理后统一叠加）
        bgm_path = (script.get("bgm") or {}).get("path")
        if bgm_path and Path(bgm_path).exists():
            logger.info("BGM 混合（完整视频）...")
            bgm_tmp = str(self.temp_dir / "final_bgm.mp4")
            self._mix_bgm(output_path, bgm_path, bgm_tmp)
            shutil.copy(bgm_tmp, output_path)
            logger.info("BGM 混合完成")
        elif bgm_path:
            logger.warning("BGM 文件不存在，跳过: %s", bgm_path)

        # 清理临时文件
        self._cleanup()

        logger.info("渲染完成: %s", output_path)
        return output_path

    def _burn_subtitles_python(
        self,
        video_path: str,
        subtitles: List[Dict],
        output_path: str
    ) -> str:
        """
        PIL 字幕烧录（FFmpeg 无 libass 时的 fallback）

        - 全局时间轴对齐（subtitle 的 start/end_time 相对完整视频）
        - 双语：中文在上，英文在下
        - 白字黑边，底部居中
        """
        try:
            import cv2 as _cv2
            import numpy as _np
            from PIL import Image as _Image, ImageDraw, ImageFont as _Font
        except ImportError as e:
            logger.warning("PIL/cv2 不可用，跳过字幕: %s", e)
            shutil.copy(video_path, output_path)
            return output_path

        # 查找中文字体
        font_candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Medium.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        cn_font_path = next((p for p in font_candidates if Path(p).exists()), None)
        font_size = self.renderer.config.subtitle_size
        try:
            cn_font = _Font.truetype(cn_font_path, font_size) if cn_font_path else _Font.load_default()
            en_font = _Font.truetype(cn_font_path, int(font_size * 0.75)) if cn_font_path else _Font.load_default()
        except Exception:
            cn_font = en_font = _Font.load_default()

        cap = _cv2.VideoCapture(video_path)
        try:
            fps = cap.get(_cv2.CAP_PROP_FPS) or 30
            w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
            total = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))

            # 先写无音频的视频
            video_only = str(self.temp_dir / "sub_vid_only.mp4")
            fourcc = _cv2.VideoWriter_fourcc(*'mp4v')
            writer = _cv2.VideoWriter(video_only, fourcc, fps, (w, h))

            try:
                # P0.4: 安全上限防止损坏视频导致无限循环
                max_frames = max(total * 2, int(fps * 600)) if total > 0 else int(fps * 600)
                frame_idx = 0
                while frame_idx < max_frames:
                    ret, frame = cap.read()
                    if not ret:
                        break

                    ts = frame_idx / fps

                    # 找当前时间点活跃的字幕
                    active = next(
                        (s for s in subtitles if s.get("start_time", 0) <= ts <= s.get("end_time", 0)),
                        None
                    )

                    if active:
                        pil_img = _Image.fromarray(_cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB))
                        draw = ImageDraw.Draw(pil_img)

                        lines = []
                        if active.get("cn_text"):
                            lines.append((active["cn_text"], cn_font))
                        if active.get("en_text"):
                            lines.append((active["en_text"], en_font))

                        margin_v = 60
                        line_gap = 8
                        # 计算总高度
                        heights = [draw.textbbox((0, 0), t, font=f)[3] for t, f in lines]
                        total_h = sum(heights) + line_gap * (len(lines) - 1)
                        y = h - margin_v - total_h

                        for text, font in lines:
                            bbox = draw.textbbox((0, 0), text, font=font)
                            tw = bbox[2] - bbox[0]
                            x = (w - tw) // 2
                            lh = bbox[3]
                            # 黑色描边
                            for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,2)]:
                                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
                            # 白色主体
                            draw.text((x, y), text, font=font, fill=(255, 255, 255))
                            y += lh + line_gap

                        frame = _cv2.cvtColor(_np.array(pil_img), _cv2.COLOR_RGB2BGR)

                    writer.write(frame)
                    frame_idx += 1
            finally:
                writer.release()
        finally:
            cap.release()

        # 合并原始音频轨道
        logger.info("字幕烧录完成，合并音频...")
        cmd = [
            self.renderer.ffmpeg_path, "-y",
            "-i", video_only,
            "-i", video_path,
            "-map", "0:v", "-map", "1:a?",  # a? 表示音频可选
            *self.renderer._encoder_args(),
            "-c:a", "aac",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning("音频合并失败，使用无声版: %s", result.stderr[:200])
            shutil.copy(video_only, output_path)

        return output_path
    
    def _mix_bgm(self, video_path: str, bgm_path: str, output_path: str) -> str:
        """将 BGM 混入完整视频（原声降至 80%，BGM 按配置音量叠加）"""
        vol = self.renderer.config.bgm_volume
        ab = self.renderer.config.audio_bitrate
        # 检查视频是否有音频流
        probe = subprocess.run(
            [self.renderer.ffprobe_path, "-v", "error",
             "-select_streams", "a:0", "-show_entries", "stream=codec_type",
             "-of", "csv=p=0", video_path],
            capture_output=True, text=True, timeout=30
        )
        has_audio = probe.stdout.strip() == "audio"

        if has_audio:
            af = (f"[0:a]volume=0.8[a0];"
                  f"[1:a]volume={vol}[a1];"
                  f"[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]")
            cmd = [
                self.renderer.ffmpeg_path, "-y",
                "-i", video_path, "-i", bgm_path,
                "-filter_complex", af,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", ab,
                output_path
            ]
        else:
            # 视频无音轨：直接把 BGM 作为唯一音频
            cmd = [
                self.renderer.ffmpeg_path, "-y",
                "-i", video_path, "-i", bgm_path,
                "-filter_complex", f"[1:a]volume={vol}[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", ab,
                "-shortest", output_path
            ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            logger.warning("BGM 混合失败，保留原音频: %s", result.stderr[:200])
            shutil.copy(video_path, output_path)
        return output_path

    def _find_video_path(self, clip: Dict, materials: Dict) -> Optional[str]:
        """从素材索引中查找视频路径"""
        video_id = clip.get("video_id") or clip.get("material_id") or clip.get("path")
        
        videos = materials.get("videos", {})
        if video_id in videos:
            return videos[video_id].get("file_info", {}).get("path")
        
        # 尝试直接路径
        if Path(video_id).exists():
            return video_id
        
        return None
    
    def _create_subtitle_srt(self, sub: Dict, temp_dir: Path) -> str:
        """创建 SRT 字幕文件"""
        srt_path = temp_dir / f"subtitle_{id(sub)}.srt"
        
        start = self._seconds_to_srt_time(sub["start_time"])
        end = self._seconds_to_srt_time(sub["end_time"])
        
        # 双语字幕
        cn_text = sub.get("cn_text", "")
        en_text = sub.get("en_text", "")
        
        content = f"{cn_text}\n{en_text}" if en_text else cn_text
        
        srt_content = f"""1
{start} --> {end}
{content}
"""
        srt_path.write_text(srt_content, encoding='utf-8')
        return str(srt_path)
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """转换为 SRT 时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _cleanup(self):
        """清理临时文件"""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)


def main():
    parser = argparse.ArgumentParser(description="VideoEditer - 全自动渲染引擎")
    parser.add_argument("--script", "-s", required=True, help="脚本文件路径 (JSON)")
    parser.add_argument("--materials", "-m", required=True, help="素材索引文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出视频路径")
    parser.add_argument("--width", type=int, default=1080, help="视频宽度")
    parser.add_argument("--height", type=int, default=1920, help="视频高度")
    parser.add_argument("--fps", type=int, default=30, help="帧率")
    parser.add_argument("--crf", type=int, default=18, help="视频质量 (0-51)")
    parser.add_argument("--no-skin-smooth", action="store_true", help="禁用磨皮")
    parser.add_argument("--no-color-grading", action="store_true", help="禁用调色")
    
    args = parser.parse_args()
    
    # 创建配置
    config = RenderConfig(
        width=args.width,
        height=args.height,
        fps=args.fps,
        crf=args.crf,
        enable_skin_smooth=not args.no_skin_smooth,
        enable_color_grading=not args.no_color_grading
    )
    
    # 执行渲染
    pipeline = VideoPipeline(config)
    pipeline.render_from_script(
        script_path=args.script,
        materials_index=args.materials,
        output_path=args.output
    )


if __name__ == "__main__":
    main()
