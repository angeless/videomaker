#!/usr/bin/env python3
"""
VideoEditer - 全自动渲染引擎
FFmpeg 本地渲染：磨皮、调色、字幕压制、BGM 混合
替代剪映手动操作，实现真正的自动化
"""

import json
import subprocess
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import tempfile
import shutil


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


class FFmpegRenderer:
    """FFmpeg 渲染器"""
    
    def __init__(self, config: RenderConfig = None):
        self.config = config or RenderConfig()
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()
        
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
        
        result = subprocess.run(cmd, capture_output=True, text=True)
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
        if has_skin_smooth and self.config.enable_skin_smooth:
            # 使用 smartblur 实现轻微磨皮
            # 注意：高级磨皮需要 MediaPipe + mask，这里先做基础版
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
        
        # 4. 字幕叠加
        if has_subtitle and subtitle_srt and Path(subtitle_srt).exists():
            # 硬字幕：将字幕烧录到视频中
            subtitle_filter = (
                f"subtitles='{subtitle_srt}':"
                f"force_style='FontName={self.config.subtitle_font},"
                f"FontSize={self.config.subtitle_size},"
                f"PrimaryColour=&H{self.config.subtitle_color.lstrip('#')}&,"
                f"OutlineColour=&H{self.config.subtitle_outline.lstrip('#')}&,"
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
        cmd.extend([
            "-c:v", "libx264",
            "-crf", str(self.config.crf),
            "-preset", self.config.preset,
            "-b:v", self.config.video_bitrate,
            "-pix_fmt", "yuv420p"
        ])
        
        # 音频处理
        if bgm_audio or narration_audio:
            # 需要复杂音频混合
            cmd = self._build_audio_mix_cmd(
                cmd, input_video, bgm_audio, narration_audio,
                start_time, end_time
            )
        else:
            # 仅复制原音频
            cmd.extend(["-c:a", "aac", "-b:a", self.config.audio_bitrate])
        
        # 输出文件
        cmd.append(str(output_path))
        
        # 执行渲染
        print(f"🎬 渲染: {output_path.name}")
        print(f"   滤镜: {video_filter[:80]}...")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ 渲染失败: {result.stderr}")
            raise RuntimeError(f"FFmpeg 渲染失败: {result.stderr[:500]}")
        
        print(f"✅ 完成: {output_path}")
        return str(output_path)
    
    def _build_audio_mix_cmd(
        self,
        base_cmd: List[str],
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            for video in video_list:
                # 使用绝对路径并处理特殊字符
                abs_path = str(Path(video).resolve())
                f.write(f"file '{abs_path}'\n")
            concat_file = f.name
        
        try:
            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_video
            ]
            
            print(f"🎬 合并 {len(video_list)} 个视频片段...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                raise RuntimeError(f"合并失败: {result.stderr}")
            
            print(f"✅ 合并完成: {output_video}")
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
            print(f"\n📽️  处理片段 {i+1}/{len(script['clips'])}")
            
            # 查找素材
            video_path = self._find_video_path(clip, materials)
            if not video_path:
                print(f"⚠️  跳过片段 {i+1}: 未找到素材")
                continue
            
            # 准备字幕
            subtitle_srt = None
            if i < len(script.get("subtitles", [])):
                sub = script["subtitles"][i]
                subtitle_srt = self._create_subtitle_srt(sub, self.temp_dir)
            
            # 渲染片段
            segment_output = self.temp_dir / f"segment_{i:03d}.mp4"
            
            self.renderer.render_video(
                input_video=video_path,
                output_video=str(segment_output),
                subtitle_srt=subtitle_srt,
                bgm_audio=script.get("bgm", {}).get("path") if i == 0 else None,
                narration_audio=script.get("narration", {}).get("path"),
                start_time=clip.get("source_start", 0),
                end_time=clip.get("source_end"),
                has_face=clip.get("has_face", False)
            )
            
            segment_files.append(str(segment_output))
        
        # 合并所有片段
        if len(segment_files) == 1:
            shutil.copy(segment_files[0], output_path)
        elif len(segment_files) > 1:
            self.renderer.concat_videos(segment_files, output_path)
        else:
            raise RuntimeError("没有可渲染的片段")
        
        # 清理临时文件
        self._cleanup()
        
        print(f"\n🎉 渲染完成: {output_path}")
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
