#!/usr/bin/env python3
"""
提取视频完整元数据并建立索引
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
import hashlib
import os

def extract_video_metadata(video_path):
    """提取视频完整元数据"""
    video_path = Path(video_path)
    
    result = {
        "file_info": {},
        "technical_metadata": {},
        "content_analysis": {},
        "index_data": {}
    }
    
    # 1. 文件系统元数据
    try:
        stat_info = video_path.stat()
        result["file_info"] = {
            "filename": video_path.name,
            "file_size": stat_info.st_size,
            "file_size_human": f"{stat_info.st_size / 1024 / 1024:.2f} MB",
            "created_time": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
            "modified_time": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
            "accessed_time": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
            "file_hash": generate_file_hash(video_path)
        }
    except Exception as e:
        result["file_info"]["error"] = str(e)
    
    # 2. 技术元数据 (FFprobe)
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            str(video_path)
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        ffprobe_data = json.loads(output)
        
        # 格式信息
        format_info = ffprobe_data.get("format", {})
        result["technical_metadata"]["format"] = {
            "format_name": format_info.get("format_name"),
            "duration": format_info.get("duration"),
            "size": format_info.get("size"),
            "bit_rate": format_info.get("bit_rate"),
            "tags": format_info.get("tags", {})
        }
        
        # 流信息
        video_streams = []
        audio_streams = []
        subtitle_streams = []
        
        for stream in ffprobe_data.get("streams", []):
            stream_type = stream.get("codec_type")
            if stream_type == "video":
                video_streams.append({
                    "codec": stream.get("codec_name"),
                    "profile": stream.get("profile"),
                    "width": stream.get("width"),
                    "height": stream.get("height"),
                    "pixel_format": stream.get("pix_fmt"),
                    "frame_rate": stream.get("r_frame_rate"),
                    "avg_frame_rate": stream.get("avg_frame_rate"),
                    "bit_rate": stream.get("bit_rate"),
                    "duration": stream.get("duration"),
                    "rotation": stream.get("rotation", 0),
                    "has_b_frames": stream.get("has_b_frames", 0)
                })
            elif stream_type == "audio":
                audio_streams.append({
                    "codec": stream.get("codec_name"),
                    "channels": stream.get("channels"),
                    "channel_layout": stream.get("channel_layout"),
                    "sample_rate": stream.get("sample_rate"),
                    "bit_rate": stream.get("bit_rate"),
                    "language": stream.get("tags", {}).get("language", "unknown")
                })
            elif stream_type == "subtitle":
                subtitle_streams.append({
                    "codec": stream.get("codec_name"),
                    "language": stream.get("tags", {}).get("language", "unknown")
                })
        
        result["technical_metadata"]["streams"] = {
            "video": video_streams,
            "audio": audio_streams,
            "subtitle": subtitle_streams
        }
        
        # 章节信息
        chapters = ffprobe_data.get("chapters", [])
        if chapters:
            result["technical_metadata"]["chapters"] = chapters
        
    except Exception as e:
        result["technical_metadata"]["error"] = str(e)
    
    # 3. 内容分析（基于文件名和元数据的简单推断）
    result["content_analysis"] = analyze_content_from_metadata(
        video_path.name, 
        result["technical_metadata"]
    )
    
    # 4. 索引数据
    result["index_data"] = create_index_data(result)
    
    return result

def generate_file_hash(video_path):
    """生成文件哈希（用于去重和索引）"""
    try:
        # 使用文件大小和文件名生成简单哈希
        stat_info = video_path.stat()
        hash_input = f"{video_path.name}_{stat_info.st_size}_{stat_info.st_mtime}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    except:
        return hashlib.sha256(video_path.name.encode()).hexdigest()[:16]

def analyze_content_from_metadata(filename, tech_metadata):
    """基于元数据推断内容"""
    filename_lower = filename.lower()
    
    analysis = {
        "inferred_scene": "unknown",
        "inferred_quality": "unknown",
        "inferred_usage": [],
        "notes": []
    }
    
    # 基于文件名推断
    if "snow" in filename_lower or "powder" in filename_lower:
        analysis["inferred_scene"] = "snow_sports"
        analysis["inferred_usage"] = ["action_sports", "travel", "adventure"]
    elif "ushguli" in filename_lower:
        analysis["inferred_scene"] = "mountain_village"
        analysis["inferred_usage"] = ["travel", "culture", "landscape"]
    elif "instrument" in filename_lower or "wood" in filename_lower:
        analysis["inferred_scene"] = "cultural_artifacts"
        analysis["inferred_usage"] = ["culture", "education", "documentary"]
    
    # 基于技术参数推断质量
    video_stream = tech_metadata.get("streams", {}).get("video", [{}])[0]
    width = video_stream.get("width", 0)
    height = video_stream.get("height", 0)
    
    if width >= 1920 or height >= 1080:
        analysis["inferred_quality"] = "high"
        analysis["notes"].append("高清分辨率")
    elif width >= 1280 or height >= 720:
        analysis["inferred_quality"] = "medium"
        analysis["notes"].append("标清分辨率")
    else:
        analysis["inferred_quality"] = "low"
        analysis["notes"].append("低分辨率")
    
    # 检查是否有音频
    audio_streams = tech_metadata.get("streams", {}).get("audio", [])
    if audio_streams:
        analysis["notes"].append(f"包含音频: {len(audio_streams)}个音轨")
    
    return analysis

def create_index_data(metadata):
    """创建搜索索引数据"""
    file_info = metadata["file_info"]
    tech_meta = metadata["technical_metadata"]
    content = metadata["content_analysis"]
    
    video_stream = tech_meta.get("streams", {}).get("video", [{}])[0]
    
    # 创建可搜索的标签
    tags = []
    
    # 技术标签
    if video_stream.get("width") and video_stream.get("height"):
        tags.append(f"res_{video_stream['width']}x{video_stream['height']}")
    
    if video_stream.get("codec"):
        tags.append(f"codec_{video_stream['codec']}")
    
    # 内容标签
    tags.append(content["inferred_scene"])
    tags.append(f"quality_{content['inferred_quality']}")
    
    # 使用场景标签
    tags.extend(content["inferred_usage"])
    
    # 去重并排序
    tags = sorted(list(set(tags)))
    
    return {
        "video_id": file_info.get("file_hash"),
        "filename": file_info.get("filename"),
        "tags": tags,
        "search_keywords": create_search_keywords(file_info, content),
        "preview_info": {
            "duration": tech_meta.get("format", {}).get("duration"),
            "resolution": f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
            "has_audio": len(tech_meta.get("streams", {}).get("audio", [])) > 0
        }
    }

def create_search_keywords(file_info, content):
    """创建搜索关键词"""
    keywords = []
    
    # 文件名相关
    filename = file_info.get("filename", "")
    keywords.append(filename)
    keywords.append(Path(filename).stem)  # 去掉扩展名
    
    # 内容相关
    keywords.append(content["inferred_scene"])
    keywords.extend(content["inferred_usage"])
    
    # 质量相关
    keywords.append(content["inferred_quality"])
    
    # 去重并过滤空值
    keywords = [k for k in keywords if k and k != "unknown"]
    return list(set(keywords))

def save_metadata_to_index(metadata_list, output_file="video_index.json"):
    """保存元数据到索引文件"""
    index = {
        "metadata_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "total_videos": len(metadata_list),
        "videos": {}
    }
    
    for metadata in metadata_list:
        video_id = metadata["index_data"]["video_id"]
        index["videos"][video_id] = {
            "file_info": metadata["file_info"],
            "index_data": metadata["index_data"],
            "technical_summary": {
                "resolution": metadata["index_data"]["preview_info"]["resolution"],
                "duration": metadata["index_data"]["preview_info"]["duration"],
                "has_audio": metadata["index_data"]["preview_info"]["has_audio"]
            },
            "content_summary": metadata["content_analysis"]
        }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    return index

def main():
    """主函数"""
    video_dir = Path(".")
    video_files = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.mov"))
    
    print(f"找到 {len(video_files)} 个视频文件")
    print("=" * 60)
    
    all_metadata = []
    
    for video_file in video_files:
        print(f"处理: {video_file.name}")
        metadata = extract_video_metadata(video_file)
        all_metadata.append(metadata)
        
        # 显示摘要
        idx = metadata["index_data"]
        print(f"  ID: {idx['video_id']}")
        print(f"  分辨率: {idx['preview_info']['resolution']}")
        print(f"  标签: {', '.join(idx['tags'][:5])}")
        if len(idx['tags']) > 5:
            print(f"        ... 共 {len(idx['tags'])} 个标签")
        print()
    
    # 保存索引
    index_file = "video_index.json"
    index = save_metadata_to_index(all_metadata, index_file)
    
    print("=" * 60)
    print(f"索引已保存到: {index_file}")
    print(f"总视频数: {index['total_videos']}")
    
    # 统计信息
    all_tags = []
    for metadata in all_metadata:
        all_tags.extend(metadata["index_data"]["tags"])
    
    unique_tags = set(all_tags)
    print(f"唯一标签数: {len(unique_tags)}")
    print(f"热门标签: {sorted(unique_tags)[:10]}")

if __name__ == "__main__":
    main()