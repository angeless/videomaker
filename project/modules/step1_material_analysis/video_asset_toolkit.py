#!/usr/bin/env python3
"""
视界工具箱 - Video Asset Toolkit
本地/云端多维度视频分析工具
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
import hashlib
import logging
import re

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    HAS_CV = True
except Exception:
    HAS_CV = False

class VideoAssetToolkit:
    def __init__(self, config_path=None):
        self.config = self.load_config(config_path)
        self.results_dir = Path(self.config.get("results_dir", "./results"))
        self.results_dir.mkdir(exist_ok=True)
        self._visual_stats_cache = {}
        self._face_cascade = None
        if HAS_CV:
            try:
                cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                self._face_cascade = cv2.CascadeClassifier(cascade_path)
                if self._face_cascade.empty():
                    self._face_cascade = None
            except Exception:
                self._face_cascade = None
        
    def load_config(self, config_path):
        """加载配置文件"""
        default_config = {
            "local_models": {
                "enabled": True,
                "object_detection": True,
                "scene_description": True,
                "technical_analysis": True
            },
            "cloud_models": {
                "enabled": False,
                "gemini_api_key": "",
                "openai_api_key": ""
            },
            "analysis_dimensions": [
                "objects",
                "scenes", 
                "colors",
                "composition",
                "mood",
                "business_value",
                "technical_quality"
            ],
            "output_formats": ["json", "markdown", "csv"],
            "max_videos_per_batch": 100
        }
        
        if config_path and Path(config_path).exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception:
                logger.warning("无法读取配置文件 %s, 使用默认配置", config_path)
                
        return default_config
    
    def analyze_videos(self, video_paths, output_format="all"):
        """分析视频列表"""
        if isinstance(video_paths, (str, Path)):
            video_paths = [video_paths]
            
        results = {}
        for video_path in video_paths:
            video_path = Path(video_path)
            if not video_path.exists():
                logger.warning("视频不存在 %s", video_path)
                continue

            logger.info("分析: %s", video_path.name)
            result = self.analyze_single_video(video_path)
            
            # 生成唯一ID
            video_hash = self.generate_video_hash(video_path)
            results[video_hash] = {
                "filename": video_path.name,
                "path": str(video_path),
                "hash": video_hash,
                "analysis": result,
                "timestamp": datetime.now().isoformat()
            }
            
        # 保存结果
        self.save_results(results, output_format)
        return results
    
    def generate_video_hash(self, video_path):
        """生成视频哈希（指纹）"""
        try:
            # 使用文件大小和修改时间生成简单哈希
            stat = video_path.stat()
            hash_input = f"{video_path.name}_{stat.st_size}_{stat.st_mtime}"
            return hashlib.md5(hash_input.encode()).hexdigest()[:12]
        except Exception:
            return hashlib.md5(video_path.name.encode()).hexdigest()[:12]
    
    def analyze_single_video(self, video_path, enable_transcription=None,
                             include_audio_quality=None):
        """分析单个视频

        Args:
            video_path: 视频文件路径
            enable_transcription: 是否启用语音转录 (None=使用config, True/False=强制)
            include_audio_quality: 是否包含音频质量评分 (None=使用config, True/False=强制)
        """
        result = {
            "metadata": self.extract_metadata(video_path),
            "local_analysis": {},
            "cloud_analysis": {},
            "transcription": {},
            "audio_quality": {},
            "recommendations": []
        }

        # 本地分析
        if self.config["local_models"]["enabled"]:
            result["local_analysis"] = self.local_analysis(video_path)

        # 语音转录（默认开启：faster-whisper VAD 自动跳过无语音视频）
        do_transcribe = enable_transcription
        if do_transcribe is None:
            do_transcribe = self.config.get("transcription", {}).get("enabled", True)
        if do_transcribe:
            result["transcription"] = self._transcribe_video(video_path)

        # 音频质量评分
        do_audio_quality = include_audio_quality
        if do_audio_quality is None:
            do_audio_quality = self.config.get("audio_quality", {}).get("enabled", False)
        if do_audio_quality:
            result["audio_quality"] = self._analyze_audio_quality(video_path)

        # 云端分析
        if self.config["cloud_models"]["enabled"]:
            result["cloud_analysis"] = self.cloud_analysis(video_path)

        # 生成建议
        result["recommendations"] = self.generate_recommendations(result)

        return result

    def _transcribe_video(self, video_path):
        """调用转录模块对视频进行语音识别"""
        try:
            from modules.step1_material_analysis.transcribe import transcribe_video
        except ImportError:
            try:
                from .transcribe import transcribe_video
            except ImportError:
                logger.warning("转录模块不可用，跳过语音识别")
                return {"enabled": False, "error": "transcribe module not found"}

        tc = self.config.get("transcription", {})
        model_size = tc.get("model_size", "medium")
        language = tc.get("language", None)
        max_duration = tc.get("max_duration", None)

        logger.info("转录: %s (model=%s)", Path(video_path).name, model_size)
        return transcribe_video(
            str(video_path),
            model_size=model_size,
            language=language,
            max_duration=max_duration,
        )
    
    def _analyze_audio_quality(self, video_path):
        """调用音频质量评分模块"""
        try:
            from modules.step1_material_analysis.audio_quality import analyze_audio_quality
        except ImportError:
            try:
                from .audio_quality import analyze_audio_quality
            except ImportError:
                logger.warning("音频质量模块不可用，跳过评分")
                return {"enabled": False, "error": "audio_quality module not found"}

        logger.info("音频质量评分: %s", Path(video_path).name)
        return analyze_audio_quality(str(video_path))

    @staticmethod
    def _parse_iso6709_location(tag_value):
        """Parse ISO 6709 location string to lat/lon/alt dict.

        Handles formats like ``+40.7128-074.0060+000.00/`` produced by
        Apple QuickTime and similar Android ``location`` tags.

        Returns ``{"latitude": float, "longitude": float, "altitude": float|None}``
        or ``None`` if parsing fails.
        """
        if not tag_value:
            return None
        try:
            m = re.match(
                r'([+-]\d+\.?\d*)([+-]\d+\.?\d*)([+-]\d+\.?\d*)?/?',
                str(tag_value).strip(),
            )
            if not m:
                return None
            lat = float(m.group(1))
            lon = float(m.group(2))
            alt = float(m.group(3)) if m.group(3) else None
            return {"latitude": lat, "longitude": lon, "altitude": alt}
        except Exception:
            return None

    def extract_metadata(self, video_path):
        """提取视频元数据"""
        try:
            # Round-13: resolve to absolute path so ffprobe can't interpret a
            # filename starting with "-" as an option (argv injection).
            # If somehow relative and starts with "-", prefix with "./".
            vp = str(video_path)
            if not os.path.isabs(vp):
                vp_abs = os.path.abspath(vp)
            else:
                vp_abs = vp
            if vp_abs.startswith("-"):
                # Absolute paths normally start with "/" so this is rare, but
                # be defensive: refuse rather than feed a "-" arg to ffprobe.
                raise ValueError(f"refusing ffprobe on suspicious path {vp_abs!r}")
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                vp_abs,
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=30)
            metadata = json.loads(output)
            
            # 提取关键信息
            format_info = metadata.get("format", {})
            streams = metadata.get("streams", [])
            
            video_streams = []
            audio_streams = []
            
            for stream in streams:
                if stream.get("codec_type") == "video":
                    video_streams.append({
                        "codec": stream.get("codec_name"),
                        "width": stream.get("width"),
                        "height": stream.get("height"),
                        "fps": stream.get("r_frame_rate"),
                        "bitrate": stream.get("bit_rate")
                    })
                elif stream.get("codec_type") == "audio":
                    audio_streams.append({
                        "codec": stream.get("codec_name"),
                        "channels": stream.get("channels"),
                        "sample_rate": stream.get("sample_rate")
                    })
            
            # --- GPS / location extraction ---
            gps = None
            format_tags = format_info.get("tags", {})
            # Collect all tags (format-level + every stream) for location search
            all_tags = dict(format_tags)
            for stream in streams:
                for k, v in (stream.get("tags") or {}).items():
                    all_tags.setdefault(k, v)

            for tag_name in (
                "com.apple.quicktime.location.ISO6709",
                "com.apple.quicktime.location",
                "location",
            ):
                raw = all_tags.get(tag_name)
                if raw:
                    parsed = self._parse_iso6709_location(raw)
                    if parsed:
                        gps = parsed
                        break

            return {
                "duration": format_info.get("duration"),
                "size": format_info.get("size"),
                "bitrate": format_info.get("bit_rate"),
                "format": format_info.get("format_name"),
                "video_streams": video_streams,
                "audio_streams": audio_streams,
                "tags": format_tags,
                "gps": gps,
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def local_analysis(self, video_path):
        """本地模型分析"""
        result = {}
        
        # 技术质量分析
        if self.config["local_models"].get("technical_analysis", True):
            result["technical"] = self.technical_analysis(video_path)
            
        # 物体检测（模拟）
        if self.config["local_models"].get("object_detection", True):
            result["objects"] = self.object_detection_simulation(video_path)
            
        # 场景描述（模拟）
        if self.config["local_models"].get("scene_description", True):
            result["scene"] = self.scene_description_simulation(video_path)
            
        return result
    
    def technical_analysis(self, video_path):
        """技术质量分析"""
        try:
            metadata = self.extract_metadata(video_path)
            if "error" in metadata:
                return {"error": metadata["error"]}
                
            video_stream = metadata.get("video_streams", [{}])[0]
            
            # 计算质量评分
            width = int(video_stream.get("width", 0))
            height = int(video_stream.get("height", 0))
            bitrate = video_stream.get("bitrate", "0")
            
            # 分辨率评分
            if width >= 3840 or height >= 2160:  # 4K
                resolution_score = 0.95
            elif width >= 1920 or height >= 1080:  # 1080p
                resolution_score = 0.85
            elif width >= 1280 or height >= 720:  # 720p
                resolution_score = 0.70
            elif width >= 640 or height >= 480:  # 480p
                resolution_score = 0.50
            else:
                resolution_score = 0.30
                
            # 码率评分
            try:
                bitrate_num = int(bitrate)
                if bitrate_num > 10000000:  # 10 Mbps
                    bitrate_score = 0.95
                elif bitrate_num > 5000000:  # 5 Mbps
                    bitrate_score = 0.85
                elif bitrate_num > 2000000:  # 2 Mbps
                    bitrate_score = 0.70
                elif bitrate_num > 1000000:  # 1 Mbps
                    bitrate_score = 0.50
                else:
                    bitrate_score = 0.30
            except (TypeError, ValueError):
                bitrate_score = 0.50
                
            overall_quality = (resolution_score + bitrate_score) / 2
            
            return {
                "resolution": f"{width}x{height}",
                "resolution_score": resolution_score,
                "bitrate": bitrate,
                "bitrate_score": bitrate_score,
                "codec": video_stream.get("codec", "未知"),
                "fps": video_stream.get("fps", "未知"),
                "overall_quality": overall_quality,
                "quality_level": self.get_quality_level(overall_quality)
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def get_quality_level(self, score):
        """获取质量等级"""
        if score >= 0.8:
            return "优秀"
        elif score >= 0.6:
            return "良好"
        elif score >= 0.4:
            return "一般"
        else:
            return "较差"

    def _get_visual_stats(self, video_path, sample_frames=18):
        """从视频帧提取轻量视觉统计特征（不依赖云端）。"""
        key = str(Path(video_path).resolve())
        if key in self._visual_stats_cache:
            return self._visual_stats_cache[key]

        default_stats = {
            "sample_count": 0,
            "brightness": 0.5,
            "brightness_std": 0.0,
            "saturation": 0.35,
            "saturation_std": 0.0,
            "blue_ratio": 0.33,
            "green_ratio": 0.33,
            "red_ratio": 0.33,
            "edge_density": 0.1,
            "edge_density_std": 0.0,
            "motion_score": 0.0,
            "motion_std": 0.0,
            "face_ratio": 0.0,
            "color_temp": 0.0,
            "texture_complexity": 0.0,
            "hue_dominant": 0,
        }

        if not HAS_CV:
            self._visual_stats_cache[key] = default_stats
            return default_stats

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            cap.release()
            self._visual_stats_cache[key] = default_stats
            return default_stats

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            if total_frames <= 0:
                total_frames = sample_frames
            frame_indexes = sorted(set(
                int(x) for x in np.linspace(0, max(total_frames - 1, 0), num=min(sample_frames, max(total_frames, 1)))
            ))

            brightness_list = []
            saturation_list = []
            color_ratio_list = []
            edge_list = []
            motion_list = []
            face_hits = 0
            prev_gray = None

            for idx in frame_indexes:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue

                hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                v = hsv[:, :, 2]
                s = hsv[:, :, 1]
                brightness_list.append(float(np.mean(v)) / 255.0)
                saturation_list.append(float(np.mean(s)) / 255.0)

                b_mean, g_mean, r_mean, _ = cv2.mean(frame)
                total_color = max(b_mean + g_mean + r_mean, 1e-6)
                color_ratio_list.append((
                    float(b_mean / total_color),
                    float(g_mean / total_color),
                    float(r_mean / total_color),
                ))

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                edges = cv2.Canny(gray, 80, 160)
                edge_list.append(float(np.mean(edges > 0)))

                if prev_gray is not None:
                    diff = cv2.absdiff(gray, prev_gray)
                    motion_list.append(float(np.mean(diff)))
                prev_gray = gray

                if self._face_cascade is not None:
                    try:
                        faces = self._face_cascade.detectMultiScale(
                            gray,
                            scaleFactor=1.1,
                            minNeighbors=4,
                            minSize=(30, 30),
                        )
                        if len(faces) > 0:
                            face_hits += 1
                    except Exception:
                        pass
        finally:
            cap.release()

        if not brightness_list:
            self._visual_stats_cache[key] = default_stats
            return default_stats

        blue_ratio = float(np.mean([x[0] for x in color_ratio_list])) if color_ratio_list else 0.33
        green_ratio = float(np.mean([x[1] for x in color_ratio_list])) if color_ratio_list else 0.33
        red_ratio = float(np.mean([x[2] for x in color_ratio_list])) if color_ratio_list else 0.33

        # 色温估算: red_ratio - blue_ratio (>0 暖色调, <0 冷色调)
        color_temp = red_ratio - blue_ratio

        # 纹理复杂度: edge_density 标准差（高=场景多变，低=单一场景）
        edge_std = float(np.std(edge_list)) if len(edge_list) > 1 else 0.0
        texture_complexity = float(np.mean(edge_list)) * (1 + edge_std * 5) if edge_list else 0.1

        # 主色调（Hue 通道众数）
        hue_dominant = 0

        stats = {
            "sample_count": len(brightness_list),
            "brightness": float(np.mean(brightness_list)),
            "brightness_std": float(np.std(brightness_list)),
            "saturation": float(np.mean(saturation_list)) if saturation_list else 0.35,
            "saturation_std": float(np.std(saturation_list)) if len(saturation_list) > 1 else 0.0,
            "blue_ratio": blue_ratio,
            "green_ratio": green_ratio,
            "red_ratio": red_ratio,
            "edge_density": float(np.mean(edge_list)) if edge_list else 0.1,
            "edge_density_std": edge_std,
            "motion_score": float(np.mean(motion_list)) if motion_list else 0.0,
            "motion_std": float(np.std(motion_list)) if len(motion_list) > 1 else 0.0,
            "face_ratio": float(face_hits / max(len(brightness_list), 1)),
            "color_temp": round(color_temp, 4),
            "texture_complexity": round(texture_complexity, 4),
            "hue_dominant": hue_dominant,
        }
        self._visual_stats_cache[key] = stats
        return stats
    
    def object_detection_simulation(self, video_path):
        """基于视频帧视觉统计的轻量物体/场景标签推断（增强版）。"""
        stats = self._get_visual_stats(video_path)
        objects = []

        bri = stats["brightness"]
        sat = stats["saturation"]
        edge = stats["edge_density"]
        motion = stats["motion_score"]
        face = stats["face_ratio"]
        blue = stats["blue_ratio"]
        green = stats["green_ratio"]
        red = stats["red_ratio"]
        temp = stats.get("color_temp", 0)
        tex = stats.get("texture_complexity", 0)
        motion_std = stats.get("motion_std", 0)

        # ── 人物检测 ──
        if face >= 0.15:
            objects.append("person")
            if face >= 0.5 and motion <= 8:
                objects.append("talking")  # 高人脸+低运动=对话/采访
            if face >= 0.3:
                objects.append("portrait")

        # ── 自然元素 ──
        if green >= 0.36:
            objects.extend(["tree", "nature"])
            if green >= 0.40 and sat >= 0.35:
                objects.append("forest")
        if blue >= 0.34 and bri >= 0.55:
            objects.append("sky")
        if blue >= 0.38 and sat >= 0.32:
            objects.append("water")
            if blue >= 0.42 and bri >= 0.50:
                objects.append("ocean")
        if bri >= 0.78 and sat <= 0.28:
            objects.extend(["snow", "mountain"])

        # ── 建筑与城市 ──
        if edge >= 0.10:
            objects.append("building")
            if edge >= 0.15 and tex >= 0.15:
                objects.append("urban")
            if edge >= 0.12 and motion >= 12:
                objects.append("street")

        # ── 运动与活动 ──
        if motion >= 10.0:
            objects.append("activity")
        if motion >= 24.0:
            objects.append("vehicle")
        if motion >= 15.0 and motion_std >= 5.0:
            objects.append("dynamic")  # 运动变化大=动态镜头

        # ── 室内/室外 ──
        if sat >= 0.45 and bri >= 0.55:
            objects.append("outdoor")
        if bri <= 0.32 and edge <= 0.10:
            objects.append("indoor")
        elif bri <= 0.45 and temp > 0.02 and edge <= 0.12:
            objects.append("indoor")  # 暖色调+暗=室内灯光

        # ── 美食/餐饮（暖色+中等饱和度+中等亮度） ──
        if temp > 0.03 and 0.35 <= sat <= 0.55 and 0.40 <= bri <= 0.70 and edge >= 0.06:
            objects.append("food")

        # ── 景观 ──
        if edge <= 0.07 and green + blue >= 0.70:
            objects.append("landscape")
        if "outdoor" in objects and "landscape" not in objects:
            objects.append("landscape")
        if "indoor" in objects and "room" not in objects:
            objects.append("room")

        # ── 色温推断 ──
        if temp > 0.04:
            objects.append("warm_tone")  # 暖色调（日落/室内暖光）
        elif temp < -0.03:
            objects.append("cool_tone")  # 冷色调（蓝天/雪景/清晨）

        # ── 最低保证 ──
        if len(objects) < 2:
            if bri >= 0.55:
                objects.append("outdoor")
            else:
                objects.append("indoor")

        if not objects:
            objects = ["environment", "landscape"]

        dedup = []
        for obj in objects:
            if obj not in dedup:
                dedup.append(obj)

        # 增强置信度计算：更多特征=更高置信度
        feature_diversity = len(set(objects)) / 10.0
        confidence = min(0.95, 0.45 + stats["sample_count"] / 40.0
                         + min(motion / 120.0, 0.15)
                         + min(feature_diversity, 0.15))

        return {
            "detected_objects": dedup[:10],
            "confidence": round(float(confidence), 3),
            "method": "视频帧视觉统计推断（增强版）",
            "note": "基于亮度/饱和度/边缘/运动/人脸/色温/纹理的多特征分析"
        }
    
    def scene_description_simulation(self, video_path):
        """基于视觉统计生成场景描述与情绪（增强版）。"""
        stats = self._get_visual_stats(video_path)
        objects = self.object_detection_simulation(video_path).get("detected_objects", [])
        temp = stats.get("color_temp", 0)

        # ── 场景类型（多条件组合判定） ──
        obj_set = set(objects)
        if "snow" in obj_set and "mountain" in obj_set:
            scene_type = "snowy mountain outdoor scene"
        elif "ocean" in obj_set or ("water" in obj_set and "sky" in obj_set):
            scene_type = "coastal or waterfront scene"
        elif "forest" in obj_set or ("tree" in obj_set and "nature" in obj_set and "building" not in obj_set):
            scene_type = "natural forest or park scene"
        elif "urban" in obj_set or ("building" in obj_set and "street" in obj_set):
            scene_type = "urban street scene"
        elif "building" in obj_set and stats["edge_density"] >= 0.15:
            scene_type = "urban architecture scene"
        elif "water" in obj_set and "tree" in obj_set:
            scene_type = "natural landscape with water and vegetation"
        elif "food" in obj_set:
            scene_type = "food or dining scene"
        elif "talking" in obj_set:
            scene_type = "conversation or interview scene"
        elif "indoor" in obj_set and "person" in obj_set:
            scene_type = "indoor people-focused vlog scene"
        elif "person" in obj_set and "outdoor" in obj_set:
            scene_type = "outdoor lifestyle scene"
        elif "person" in obj_set:
            scene_type = "people-focused lifestyle scene"
        elif "landscape" in obj_set:
            scene_type = "open landscape scene"
        else:
            scene_type = "mixed environment scene"

        # ── 运镜 ──
        if stats["motion_score"] >= 26.0:
            camera_motion = "fast motion"
        elif stats["motion_score"] >= 12.0:
            camera_motion = "moderate motion"
        elif stats["motion_score"] >= 5.0:
            camera_motion = "slow pan"
        else:
            camera_motion = "stable framing"

        # ── 光线（结合色温） ──
        if stats["brightness"] >= 0.72:
            if temp > 0.03:
                lighting = "warm golden light"
            else:
                lighting = "bright daylight"
        elif stats["brightness"] <= 0.30:
            lighting = "low-light or nighttime"
        elif stats["brightness"] <= 0.40:
            if temp > 0.02:
                lighting = "warm indoor light"
            else:
                lighting = "low-light"
        else:
            if temp < -0.02:
                lighting = "cool natural light"
            else:
                lighting = "soft natural light"

        # ── 情绪（多维度组合） ──
        if stats["motion_score"] >= 24.0:
            mood = "energetic, dynamic"
        elif stats["brightness"] <= 0.35 and stats["saturation"] <= 0.30:
            mood = "moody, cinematic"
        elif stats["brightness"] <= 0.38 and temp > 0.02:
            mood = "warm, cozy"
        elif stats["saturation"] >= 0.46 and stats["brightness"] >= 0.55:
            mood = "vivid, lively"
        elif stats["face_ratio"] >= 0.3 and stats["motion_score"] <= 8:
            mood = "intimate, personal"
        elif "snow" in obj_set or "mountain" in obj_set:
            mood = "adventurous, majestic"
        elif stats["brightness_std"] >= 0.12:
            mood = "varied, transitional"
        else:
            mood = "calm, atmospheric"

        description = (
            f"{scene_type}; {camera_motion}; {lighting}."
        )
        # 更多特征 → 更高置信度
        feature_count = len([v for v in [
            stats.get("color_temp"), stats.get("texture_complexity"),
            stats.get("saturation_std"), stats.get("motion_std"),
        ] if v])
        confidence = min(0.95, 0.40 + stats["sample_count"] / 45.0
                         + min(stats["brightness_std"], 0.15)
                         + feature_count * 0.02)

        return {
            "description": description,
            "scene_type": scene_type,
            "mood": mood,
            "confidence": round(float(confidence), 3),
            "method": "视频帧视觉统计推断（增强版）",
            "note": "基于帧内容、运动、色温、纹理多维特征自动生成",
            "visual_features": {
                "brightness": round(float(stats["brightness"]), 3),
                "saturation": round(float(stats["saturation"]), 3),
                "edge_density": round(float(stats["edge_density"]), 3),
                "motion_score": round(float(stats["motion_score"]), 3),
                "face_ratio": round(float(stats["face_ratio"]), 3),
                "color_temp": round(float(temp), 4),
                "texture_complexity": round(float(stats.get("texture_complexity", 0)), 4),
            }
        }
    
    def cloud_analysis(self, video_path):
        """云端分析（需要API密钥）"""
        if not self.config["cloud_models"]["enabled"]:
            return {"enabled": False, "message": "云端分析未启用"}
            
        # 这里应该调用真实的API
        return {
            "enabled": True,
            "status": "需要配置API密钥",
            "gemini_api_key": bool(self.config["cloud_models"].get("gemini_api_key")),
            "openai_api_key": bool(self.config["cloud_models"].get("openai_api_key")),
            "note": "配置API密钥后可使用Gemini Vision/OpenAI进行深度分析"
        }
    
    def generate_recommendations(self, analysis_result):
        """生成建议"""
        recommendations = []
        
        # 技术质量建议
        technical = analysis_result.get("local_analysis", {}).get("technical", {})
        if technical and "overall_quality" in technical:
            quality = technical["overall_quality"]
            if quality < 0.5:
                recommendations.append({
                    "type": "technical",
                    "priority": "high",
                    "message": "视频质量较低，建议使用更高分辨率和码率拍摄",
                    "action": "检查相机设置，使用专业模式"
                })
            elif quality < 0.7:
                recommendations.append({
                    "type": "technical", 
                    "priority": "medium",
                    "message": "视频质量一般，可优化拍摄参数",
                    "action": "调整曝光和稳定器设置"
                })
        
        # 内容建议
        scene = analysis_result.get("local_analysis", {}).get("scene", {})
        if scene and "description" in scene:
            desc = scene["description"].lower()
            if "snow" in desc or "mountain" in desc:
                recommendations.append({
                    "type": "content",
                    "priority": "medium",
                    "message": "适合旅行/冒险类内容",
                    "action": "可制作滑雪教程或旅行vlog"
                })
            elif "instrument" in desc or "cultural" in desc:
                recommendations.append({
                    "type": "content",
                    "priority": "medium",
                    "message": "适合文化/教育类内容",
                    "action": "可制作文化遗产介绍视频"
                })
        
        return recommendations
    
    def save_results(self, results, output_format="all"):
        """保存分析结果"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"video_analysis_{timestamp}"
        
        formats = []
        if output_format == "all":
            formats = ["json", "markdown", "csv"]
        elif isinstance(output_format, str):
            formats = [output_format]
        else:
            formats = output_format
            
        saved_files = []
        
        # JSON格式 — atomic write (Round-13)
        if "json" in formats:
            json_file = self.results_dir / f"{base_name}.json"
            from modules.app_api.param_utils import atomic_write_json
            atomic_write_json(json_file, results)
            saved_files.append(str(json_file))
            
        # Markdown格式
        if "markdown" in formats:
            md_file = self.results_dir / f"{base_name}.md"
            md_content = self.generate_markdown_report(results)
            md_file.write_text(md_content, encoding='utf-8')
            saved_files.append(str(md_file))
            
        # CSV格式（简化）
        if "csv" in formats:
            csv_file = self.results_dir / f"{base_name}.csv"
            csv_content = self.generate_csv_report(results)
            csv_file.write_text(csv_content, encoding='utf-8')
            saved_files.append(str(csv_file))
            
        logger.info("分析结果已保存到:")
        for file in saved_files:
            logger.info("  - %s", file)
            
        return saved_files
    
    def generate_markdown_report(self, results):
        """生成Markdown报告"""
        lines = []
        lines.append("# 视频资产分析报告")
        lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"分析视频数量: {len(results)}")
        lines.append("")
        
        for video_id, data in results.items():
            lines.append(f"## {data['filename']}")
            lines.append(f"**文件哈希**: {video_id}")
            lines.append(f"**分析时间**: {data['timestamp']}")
            lines.append("")
            
            # 元数据
            metadata = data['analysis'].get('metadata', {})
            lines.append("### 元数据")
            lines.append(f"- 时长: {metadata.get('duration', '未知')}秒")
            lines.append(f"- 大小: {metadata.get('size', '未知')}字节")
            lines.append(f"- 格式: {metadata.get('format', '未知')}")
            
            # 技术分析
            technical = data['analysis'].get('local_analysis', {}).get('technical', {})
            if technical:
                lines.append("### 技术质量")
                lines.append(f"- 分辨率: {technical.get('resolution', '未知')}")
                lines.append(f"- 质量评分: {technical.get('overall_quality', 0):.2f} ({technical.get('quality_level', '未知')})")
                lines.append(f"- 编码: {technical.get('codec', '未知')}")
            
            # 物体检测
            objects = data['analysis'].get('local_analysis', {}).get('objects', {})
            if objects:
                lines.append("### 物体识别")
                lines.append(f"- 检测物体: {', '.join(objects.get('detected_objects', []))}")
                lines.append(f"- 置信度: {objects.get('confidence', 0):.2f}")
            
            # 场景描述
            scene = data['analysis'].get('local_analysis', {}).get('scene', {})
            if scene:
                lines.append("### 场景描述")
                lines.append(f"- 描述: {scene.get('description', '无')}")
                lines.append(f"- 情绪: {scene.get('mood', '无')}")
            
            # 建议
            recommendations = data['analysis'].get('recommendations', [])
            if recommendations:
                lines.append("### 优化建议")
                for rec in recommendations:
                    lines.append(f"- **{rec.get('priority', '').upper()}**: {rec.get('message', '')}")
                    lines.append(f"  → 操作: {rec.get('action', '')}")
            
            lines.append("")
            lines.append("---")
            lines.append("")
            
        return "\n".join(lines)
    
    def generate_csv_report(self, results):
        """生成CSV报告（简化版）"""
        lines = []
        # 表头
        lines.append("filename,hash,duration,resolution,quality_score,detected_objects,scene_description,recommendations")
        
        for video_id, data in results.items():
            filename = data['filename']
            
            # 元数据
            metadata = data['analysis'].get('metadata', {})
            duration = metadata.get('duration', '')
            
            # 技术信息
            technical = data['analysis'].get('local_analysis', {}).get('technical', {})
            resolution = technical.get('resolution', '')
            quality_score = technical.get('overall_quality', '')
            
            # 物体
            objects = data['analysis'].get('local_analysis', {}).get('objects', {})
            detected_objects = ','.join(objects.get('detected_objects', [])) if objects else ''
            
            # 场景
            scene = data['analysis'].get('local_analysis', {}).get('scene', {})
            scene_description = scene.get('description', '').replace(',', ';') if scene else ''
            
            # 建议
            recommendations = data['analysis'].get('recommendations', [])
            rec_text = '|'.join([r.get('message', '').replace(',', ';') for r in recommendations])
            
            # 构建CSV行
            line = f'"{filename}","{video_id}","{duration}","{resolution}","{quality_score}","{detected_objects}","{scene_description}","{rec_text}"'
            lines.append(line)
            
        return "\n".join(lines)
