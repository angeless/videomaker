#!/usr/bin/env python3
"""
剪映草稿 JSON 生成器
根据脚本和素材索引生成可直接导入剪映的草稿文件

支持两种素材索引格式:
1. VideoEditer 标准格式 (materials_index.json)
2. managevideos skill 输出格式
"""

import json
import uuid
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class VideoClip:
    """视频片段定义"""
    material_id: str
    path: str
    start_time: float  # 在时间轴上的开始时间（秒）
    end_time: float    # 在时间轴上的结束时间（秒）
    source_start: float = 0  # 素材本身的开始时间（秒）
    source_end: Optional[float] = None  # 素材本身的结束时间（秒）
    width: int = 1920
    height: int = 1080
    fps: int = 30
    
    def __post_init__(self):
        if self.source_end is None:
            self.source_end = self.end_time - self.start_time


@dataclass
class Subtitle:
    """字幕定义"""
    content: str
    start_time: float
    end_time: float
    font: str = "PingFangSC-Regular"
    size: int = 56
    color: str = "#FFFFFF"
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


@dataclass
class BGM:
    """背景音乐定义"""
    material_id: str
    path: str
    start_time: float
    end_time: float
    volume: float = 0.5
    fade_in: float = 1.0
    fade_out: float = 1.0


class JianyingDraftBuilder:
    """剪映草稿构建器"""
    
    def __init__(self, width: int = 1080, height: int = 1920, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.materials = {
            "videos": [],
            "audios": [],
            "texts": [],
            "effects": [],
            "filters": []
        }
        self.tracks = []
        self._material_id_map = {}
    
    def _generate_id(self) -> str:
        """生成 UUID v4"""
        return str(uuid.uuid4())
    
    def _us(self, seconds: float) -> int:
        """将秒转换为微秒"""
        return int(seconds * 1000000)
    
    def add_video_clip(self, clip: VideoClip) -> str:
        """添加视频片段，返回素材ID"""
        material_id = self._generate_id()
        
        # 添加视频素材
        video_material = {
            "id": material_id,
            "type": "video",
            "path": str(Path(clip.path).resolve()),
            "duration": self._us(clip.source_end - clip.source_start),
            "width": clip.width,
            "height": clip.height,
            "fps": clip.fps
        }
        self.materials["videos"].append(video_material)
        
        # 创建视频轨道片段
        segment = {
            "material_id": material_id,
            "start_time": self._us(clip.start_time),
            "end_time": self._us(clip.end_time),
            "source_start": self._us(clip.source_start),
            "source_end": self._us(clip.source_end),
            "transform": {
                "scale": {"x": 1.0, "y": 1.0},
                "position": {"x": 0, "y": 0},
                "rotation": 0
            },
            "speed": 1.0
        }
        
        # 添加到视频轨道
        video_track = self._get_or_create_track("video")
        video_track["segments"].append(segment)
        
        return material_id
    
    def add_subtitle(self, subtitle: Subtitle) -> str:
        """添加字幕，返回素材ID"""
        material_id = self._generate_id()
        
        # 添加文本素材
        text_material = {
            "id": material_id,
            "type": "text",
            "content": subtitle.content,
            "style": {
                "font": subtitle.font,
                "size": subtitle.size,
                "color": subtitle.color,
                "alignment": "center",
                "outline": {
                    "enabled": True,
                    "color": "#000000",
                    "width": 2
                }
            }
        }
        self.materials["texts"].append(text_material)
        
        # 创建字幕轨道片段
        segment = {
            "material_id": material_id,
            "start_time": self._us(subtitle.start_time),
            "end_time": self._us(subtitle.end_time),
            "transform": {
                "position": {"x": 0, "y": 400}  # 底部居中偏上
            }
        }
        
        # 添加到字幕轨道
        text_track = self._get_or_create_track("text")
        text_track["segments"].append(segment)
        
        return material_id
    
    def add_bgm(self, bgm: BGM) -> str:
        """添加背景音乐，返回素材ID"""
        material_id = self._generate_id()
        
        # 添加音频素材
        audio_material = {
            "id": material_id,
            "type": "audio",
            "path": str(Path(bgm.path).resolve()),
            "duration": self._us(bgm.end_time - bgm.start_time)
        }
        self.materials["audios"].append(audio_material)
        
        # 创建音频轨道片段
        segment = {
            "material_id": material_id,
            "start_time": self._us(bgm.start_time),
            "end_time": self._us(bgm.end_time),
            "volume": bgm.volume,
            "fade_in": self._us(bgm.fade_in),
            "fade_out": self._us(bgm.fade_out)
        }
        
        # 添加到音频轨道
        audio_track = self._get_or_create_track("audio")
        audio_track["segments"].append(segment)
        
        return material_id
    
    def _get_or_create_track(self, track_type: str) -> Dict:
        """获取或创建指定类型的轨道"""
        for track in self.tracks:
            if track["type"] == track_type:
                return track
        
        new_track = {
            "id": self._generate_id(),
            "type": track_type,
            "segments": []
        }
        self.tracks.append(new_track)
        return new_track
    
    def add_bilingual_subtitle(
        self, 
        cn_text: str, 
        en_text: str, 
        start_time: float, 
        end_time: float,
        cn_size: int = 56,
        en_size: int = 40
    ) -> str:
        """添加双语字幕（中文在上，英文在下）"""
        material_id = self._generate_id()
        
        # 合并双语内容
        content = f"{cn_text}\n{en_text}"
        
        # 添加文本素材
        text_material = {
            "id": material_id,
            "type": "text",
            "content": content,
            "style": {
                "font": "PingFangSC-Regular",
                "size": cn_size,
                "color": "#FFFFFF",
                "alignment": "center",
                "outline": {
                    "enabled": True,
                    "color": "#000000",
                    "width": 2
                },
                "line_spacing": 1.2
            }
        }
        self.materials["texts"].append(text_material)
        
        # 创建字幕轨道片段
        segment = {
            "material_id": material_id,
            "start_time": self._us(start_time),
            "end_time": self._us(end_time),
            "transform": {
                "position": {"x": 0, "y": 350}
            }
        }
        
        # 添加到字幕轨道
        text_track = self._get_or_create_track("text")
        text_track["segments"].append(segment)
        
        return material_id
    
    def build(self) -> Dict[str, Any]:
        """构建最终的草稿 JSON"""
        return {
            "platform": {
                "os": "macOS",
                "app_version": "3.0.0"
            },
            "materials": self.materials,
            "tracks": self.tracks,
            "canvas_config": {
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "color_space": "sRGB"
            },
            "duration": self._calculate_total_duration()
        }
    
    def _calculate_total_duration(self) -> int:
        """计算总时长（微秒）"""
        max_duration = 0
        for track in self.tracks:
            for segment in track["segments"]:
                max_duration = max(max_duration, segment["end_time"])
        return max_duration
    
    def save(self, output_path: str):
        """保存草稿到文件"""
        draft = self.build()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
        
        return output_path


def load_script(script_path: str) -> Dict:
    """加载脚本文件"""
    with open(script_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_materials_index(index_path: str) -> Dict:
    """
    加载素材索引
    
    支持格式:
    1. VideoEditer 标准格式: {"videos": {"id": {...}}}
    2. managevideos 格式: {"video_hash": {...}}
    3. 简单格式: {"video_hash": {...}} 或 [{...}]
    """
    with open(index_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 标准化为 VideoEditer 格式
    if "videos" in data:
        # 已经是标准格式
        return data
    elif isinstance(data, list):
        # 列表格式，转换为字典
        return {"videos": {f"vid_{i}": v for i, v in enumerate(data)}}
    elif isinstance(data, dict):
        # 检查是否是 managevideos 输出格式
        first_key = next(iter(data.keys())) if data else None
        if first_key and isinstance(data[first_key], dict):
            first_item = data[first_key]
            if "filename" in first_item or "path" in first_item:
                # 可能是 managevideos 格式，包装为 videos
                return {"videos": data}
    
    return data


def find_video_in_index(materials_index: Dict, video_id_or_path: str) -> Optional[Dict]:
    """
    在素材索引中查找视频
    
    Args:
        materials_index: 素材索引
        video_id_or_path: 视频ID或路径
    
    Returns:
        视频数据或 None
    """
    videos = materials_index.get("videos", {})
    
    # 先尝试直接匹配ID
    if video_id_or_path in videos:
        return videos[video_id_or_path]
    
    # 尝试匹配文件名
    for vid, vdata in videos.items():
        file_info = vdata.get("file_info", {})
        if file_info.get("filename") == video_id_or_path:
            return vdata
        if file_info.get("path") == video_id_or_path:
            return vdata
        # 兼容 managevideos 格式
        if vdata.get("filename") == video_id_or_path:
            return vdata
        if vdata.get("path") == video_id_or_path:
            return vdata
    
    return None


def extract_clip_from_material(video_data: Dict, segment_index: int = 0) -> VideoClip:
    """
    从素材数据中提取剪辑信息
    
    Args:
        video_data: 素材索引中的视频数据
        segment_index: 使用第几个可用片段
    
    Returns:
        VideoClip 对象
    """
    # 提取文件信息
    file_info = video_data.get("file_info", {})
    path = file_info.get("path", "")
    
    # 兼容 managevideos 格式
    if not path:
        path = video_data.get("path", "")
    
    # 提取技术信息
    technical = video_data.get("technical_summary", {})
    if not technical:
        # 兼容 managevideos 格式
        metadata = video_data.get("metadata", {})
        local_analysis = video_data.get("analysis", {}).get("local_analysis", {})
        tech_analysis = local_analysis.get("technical", {})
        
        width, height = parse_resolution(tech_analysis.get("resolution", "1920x1080"))
        duration = float(metadata.get("duration", 0))
        
        technical = {
            "width": width,
            "height": height,
            "duration": duration,
            "fps": 30
        }
    
    # 获取可用片段
    editing_info = video_data.get("editing_info", {})
    usable_segments = editing_info.get("usable_segments", [])
    
    if usable_segments and segment_index < len(usable_segments):
        segment = usable_segments[segment_index]
        source_start = segment.get("start", 0)
        source_end = segment.get("end", technical.get("duration", 0))
    else:
        source_start = 0
        source_end = technical.get("duration", 0)
    
    return VideoClip(
        material_id="",
        path=path,
        start_time=0,  # 将在添加到轨道时设置
        end_time=source_end - source_start,
        source_start=source_start,
        source_end=source_end,
        width=technical.get("width", 1920),
        height=technical.get("height", 1080),
        fps=technical.get("fps", 30)
    )


def parse_resolution(resolution: str) -> tuple:
    """解析分辨率"""
    try:
        if "x" in resolution:
            w, h = resolution.split("x")
            return int(w), int(h)
    except:
        pass
    return 1920, 1080


def main():
    parser = argparse.ArgumentParser(description='生成剪映草稿 JSON 文件')
    parser.add_argument('--script', required=True, help='脚本文件路径 (JSON)')
    parser.add_argument('--materials', required=True, help='素材索引文件路径 (JSON)')
    parser.add_argument('--output', required=True, help='输出草稿文件路径')
    parser.add_argument('--width', type=int, default=1080, help='画布宽度')
    parser.add_argument('--height', type=int, default=1920, help='画布高度')
    parser.add_argument('--fps', type=int, default=30, help='帧率')
    
    args = parser.parse_args()
    
    # 加载脚本和素材
    script = load_script(args.script)
    materials = load_materials_index(args.materials)
    
    # 创建构建器
    builder = JianyingDraftBuilder(
        width=args.width,
        height=args.height,
        fps=args.fps
    )
    
    # 根据脚本添加内容
    # TODO: 根据实际脚本格式解析并添加视频、字幕、BGM
    
    # 示例：添加视频片段
    if "clips" in script:
        for clip_data in script["clips"]:
            # 如果提供了素材索引，尝试从索引中获取视频信息
            if materials:
                video_id = clip_data.get("video_id") or clip_data.get("material_id") or clip_data.get("path")
                video_data = find_video_in_index(materials, video_id)
                
                if video_data:
                    # 从素材索引创建剪辑
                    clip = extract_clip_from_material(video_data)
                    clip.start_time = clip_data["start_time"]
                    clip.end_time = clip_data["end_time"]
                    
                    # 覆盖素材入出点（如果脚本中指定）
                    if "source_start" in clip_data:
                        clip.source_start = clip_data["source_start"]
                    if "source_end" in clip_data:
                        clip.source_end = clip_data["source_end"]
                else:
                    # 回退到直接路径模式
                    clip = VideoClip(
                        material_id="",
                        path=clip_data["path"],
                        start_time=clip_data["start_time"],
                        end_time=clip_data["end_time"],
                        source_start=clip_data.get("source_start", 0),
                        source_end=clip_data.get("source_end")
                    )
            else:
                # 无素材索引，使用脚本中的路径
                clip = VideoClip(
                    material_id="",
                    path=clip_data["path"],
                    start_time=clip_data["start_time"],
                    end_time=clip_data["end_time"],
                    source_start=clip_data.get("source_start", 0),
                    source_end=clip_data.get("source_end")
                )
            
            builder.add_video_clip(clip)
    
    # 示例：添加字幕
    if "subtitles" in script:
        for sub_data in script["subtitles"]:
            if "en_text" in sub_data:
                # 双语字幕
                builder.add_bilingual_subtitle(
                    cn_text=sub_data["cn_text"],
                    en_text=sub_data["en_text"],
                    start_time=sub_data["start_time"],
                    end_time=sub_data["end_time"]
                )
            else:
                # 单语字幕
                subtitle = Subtitle(
                    content=sub_data["content"],
                    start_time=sub_data["start_time"],
                    end_time=sub_data["end_time"]
                )
                builder.add_subtitle(subtitle)
    
    # 示例：添加BGM
    if "bgm" in script:
        bgm_data = script["bgm"]
        bgm = BGM(
            material_id=bgm_data.get("material_id", ""),
            path=bgm_data["path"],
            start_time=bgm_data["start_time"],
            end_time=bgm_data["end_time"],
            volume=bgm_data.get("volume", 0.5)
        )
        builder.add_bgm(bgm)
    
    # 保存草稿
    output_path = builder.save(args.output)
    print(f"✅ 剪映草稿已生成: {output_path}")


def search_materials_by_script(materials_index: Dict, script: Dict) -> List[Dict]:
    """
    根据脚本内容搜索匹配的素材
    
    Args:
        materials_index: 素材索引
        script: 脚本数据
    
    Returns:
        匹配的素材列表
    """
    matched_materials = []
    
    # 从脚本提取关键词
    keywords = set()
    
    # 从标题和描述提取
    keywords.update(script.get("title", "").split())
    keywords.update(script.get("description", "").split())
    
    # 从字幕提取
    for sub in script.get("subtitles", []):
        keywords.update(sub.get("cn_text", "").split())
        keywords.update(sub.get("en_text", "").split())
    
    # 从片段描述提取
    for clip in script.get("clips", []):
        keywords.update(clip.get("description", "").split())
        keywords.update(clip.get("tags", []))
    
    # 过滤空关键词
    keywords = {k.lower() for k in keywords if len(k) > 1}
    
    # 搜索素材
    videos = materials_index.get("videos", {})
    
    for vid, vdata in videos.items():
        score = 0
        match_reasons = []
        
        content = vdata.get("content_summary", {})
        index_data = vdata.get("index_data", {})
        editing = vdata.get("editing_info", {})
        
        # 兼容 managevideos 格式
        if not content:
            analysis = vdata.get("analysis", {}).get("local_analysis", {})
            scene = analysis.get("scene", {})
            content = {
                "description": scene.get("description", ""),
                "mood": scene.get("mood", ""),
                "objects": analysis.get("objects", {}).get("detected_objects", [])
            }
            index_data = {
                "tags": infer_tags_from_data(vdata)
            }
        
        # 在描述中匹配
        desc = content.get("description", "").lower()
        for kw in keywords:
            if kw in desc:
                score += 10
                match_reasons.append(f"描述匹配: {kw}")
        
        # 在标签中匹配
        tags = [t.lower() for t in index_data.get("tags", [])]
        for kw in keywords:
            if kw in tags:
                score += 8
                match_reasons.append(f"标签匹配: {kw}")
        
        # 在物体中匹配
        objects = [o.lower() for o in content.get("objects", [])]
        for kw in keywords:
            if kw in objects:
                score += 5
                match_reasons.append(f"物体匹配: {kw}")
        
        # 在情绪中匹配
        mood = content.get("mood", "").lower()
        for kw in keywords:
            if kw in mood:
                score += 3
                match_reasons.append(f"情绪匹配: {kw}")
        
        # 检查建议使用场景
        suggested = editing.get("suggested_usage", [])
        if any(kw in " ".join(suggested).lower() for kw in keywords):
            score += 6
            match_reasons.append("场景用途匹配")
        
        if score > 0:
            matched_materials.append({
                "video_id": vid,
                "score": score,
                "reasons": match_reasons,
                "data": vdata
            })
    
    # 按分数排序
    matched_materials.sort(key=lambda x: x["score"], reverse=True)
    
    return matched_materials


def infer_tags_from_data(video_data: Dict) -> List[str]:
    """从视频数据推断标签"""
    tags = []
    filename = video_data.get("filename", "").lower()
    
    if any(kw in filename for kw in ["drone", "dji"]):
        tags.append("航拍")
    if any(kw in filename for kw in ["snow", "ski"]):
        tags.append("滑雪")
    if any(kw in filename for kw in ["mountain"]):
        tags.append("山脉")
    
    return tags


if __name__ == "__main__":
    main()
