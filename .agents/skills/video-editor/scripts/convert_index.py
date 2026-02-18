#!/usr/bin/env python3
"""
素材索引转换器
将 managevideos skill 的输出转换为 VideoEditer 兼容格式
"""

import json
import argparse
from pathlib import Path
from datetime import datetime


def convert_managevideos_to_videoeditor(input_file: str, output_file: str):
    """
    将 managevideos 索引转换为 VideoEditer 格式
    
    Args:
        input_file: managevideos 生成的 JSON 文件路径
        output_file: 输出文件路径
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        source_data = json.load(f)
    
    # 初始化目标格式
    target_data = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "total_videos": len(source_data),
        "base_path": "",
        "videos": {}
    }
    
    # 转换每个视频
    for video_id, video_data in source_data.items():
        # 处理 managevideos 的不同输出格式
        if "file_info" in video_data:
            # 已经是标准格式
            target_data["videos"][video_id] = video_data
        else:
            # 从 analyze_videos.py 输出转换
            converted = convert_single_video(video_id, video_data)
            target_data["videos"][video_id] = converted
    
    # 保存
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(target_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 转换完成: {output_path}")
    print(f"   共 {len(target_data['videos'])} 个视频")
    
    return output_path


def convert_single_video(video_id: str, source: dict) -> dict:
    """转换单个视频数据"""
    
    # 提取文件信息
    file_info = {
        "filename": source.get("filename", ""),
        "path": source.get("path", ""),
        "relative_path": source.get("relative_path", ""),
        "file_size": source.get("file_size", 0),
        "file_size_human": source.get("file_size_human", ""),
        "created_time": source.get("created_time", ""),
        "modified_time": source.get("modified_time", "")
    }
    
    # 提取技术分析
    local_analysis = source.get("analysis", {}).get("local_analysis", {})
    technical = local_analysis.get("technical", {})
    
    technical_summary = {
        "duration": float(source.get("metadata", {}).get("duration", 0)),
        "duration_formatted": format_duration(float(source.get("metadata", {}).get("duration", 0))),
        "resolution": technical.get("resolution", "1920x1080"),
        "width": parse_resolution(technical.get("resolution", "1920x1080"))[0],
        "height": parse_resolution(technical.get("resolution", "1920x1080"))[1],
        "fps": 30,
        "bitrate": technical.get("bitrate", ""),
        "codec": technical.get("codec", "h264"),
        "has_audio": True,
        "quality_score": technical.get("overall_quality", 7.0),
        "quality_level": technical.get("quality_level", "良好")
    }
    
    # 提取内容分析
    scene = local_analysis.get("scene", {})
    objects = local_analysis.get("objects", {})
    
    content_summary = {
        "description": scene.get("description", ""),
        "mood": scene.get("mood", ""),
        "location": "",
        "objects": objects.get("detected_objects", []),
        "notes": []
    }
    
    # 生成索引数据
    index_data = {
        "tags": infer_tags(source),
        "search_keywords": infer_keywords(source),
        "preview_info": {
            "thumbnail_path": "",
            "preview_frame": 0,
            "duration": technical_summary["duration"],
            "resolution": technical_summary["resolution"],
            "has_audio": True
        }
    }
    
    # 生成剪辑信息
    editing_info = {
        "usable_segments": [
            {
                "start": 0,
                "end": technical_summary["duration"],
                "duration": technical_summary["duration"],
                "description": "完整片段",
                "quality_score": technical_summary["quality_score"],
                "suggested_for": ["通用"]
            }
        ],
        "suggested_usage": ["通用"],
        "color_profile": {
            "dominant_colors": [],
            "color_temperature": "未知",
            "brightness": "未知"
        }
    }
    
    return {
        "file_info": file_info,
        "technical_summary": technical_summary,
        "content_summary": content_summary,
        "index_data": index_data,
        "editing_info": editing_info
    }


def format_duration(seconds: float) -> str:
    """格式化时长"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"


def parse_resolution(resolution: str) -> tuple:
    """解析分辨率"""
    try:
        if "x" in resolution:
            w, h = resolution.split("x")
            return int(w), int(h)
    except:
        pass
    return 1920, 1080


def infer_tags(source: dict) -> list:
    """从源数据推断标签"""
    tags = []
    
    # 从文件名推断
    filename = source.get("filename", "").lower()
    if any(kw in filename for kw in ["drone", "dji", " aerial"]):
        tags.append("航拍")
    if any(kw in filename for kw in ["snow", "ski", "powder"]):
        tags.append("滑雪")
    if any(kw in filename for kw in ["mountain", "mount"]):
        tags.append("山脉")
    
    # 从场景描述推断
    scene = source.get("analysis", {}).get("local_analysis", {}).get("scene", {})
    desc = scene.get("description", "").lower()
    
    if "beach" in desc or "sand" in desc:
        tags.append("海滩")
    if "mountain" in desc:
        tags.append("山脉")
    if "snow" in desc:
        tags.append("雪景")
    
    return tags


def infer_keywords(source: dict) -> list:
    """从源数据推断搜索关键词"""
    keywords = []
    
    # 从文件名提取
    filename = source.get("filename", "")
    keywords.extend(filename.replace("_", " ").replace("-", " ").split())
    
    # 从物体检测提取
    objects = source.get("analysis", {}).get("local_analysis", {}).get("objects", {})
    keywords.extend(objects.get("detected_objects", []))
    
    return list(set(keywords))


def merge_indexes(index_files: list, output_file: str):
    """
    合并多个索引文件
    
    Args:
        index_files: 索引文件路径列表
        output_file: 输出文件路径
    """
    merged = {
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "total_videos": 0,
        "base_path": "",
        "videos": {}
    }
    
    for index_file in index_files:
        with open(index_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if "videos" in data:
            for vid, vdata in data["videos"].items():
                merged["videos"][vid] = vdata
        else:
            # 直接是视频数据
            for vid, vdata in data.items():
                if isinstance(vdata, dict) and "filename" in vdata:
                    merged["videos"][vid] = vdata
    
    merged["total_videos"] = len(merged["videos"])
    
    # 保存
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 合并完成: {output_file}")
    print(f"   共 {merged['total_videos']} 个视频")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(description="素材索引转换器")
    parser.add_argument("--input", "-i", required=True, help="输入文件或目录")
    parser.add_argument("--output", "-o", required=True, help="输出文件")
    parser.add_argument("--merge", "-m", action="store_true", help="合并多个索引文件")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    if args.merge:
        # 合并模式
        if input_path.is_dir():
            index_files = list(input_path.glob("*.json"))
        else:
            index_files = [input_path]
        
        merge_indexes([str(f) for f in index_files], args.output)
    else:
        # 单文件转换
        convert_managevideos_to_videoeditor(args.input, args.output)


if __name__ == "__main__":
    main()
