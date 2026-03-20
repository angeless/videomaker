#!/usr/bin/env python3
"""
视频元数据提取与搜索演示
"""

import json
from pathlib import Path
from extract_metadata import extract_video_metadata, save_metadata_to_index
from search_videos import VideoSearch

def main():
    print("🎬 视频元数据提取与搜索演示")
    print("=" * 60)
    
    # 1. 提取元数据
    print("1. 提取视频元数据...")
    video_dir = Path(".")
    video_files = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.mov"))
    
    all_metadata = []
    for video_file in video_files:
        print(f"  处理: {video_file.name}")
        metadata = extract_video_metadata(video_file)
        all_metadata.append(metadata)
    
    # 2. 保存索引
    print("\n2. 创建搜索索引...")
    index_file = "video_index_demo.json"
    index = save_metadata_to_index(all_metadata, index_file)
    print(f"  索引已保存: {index_file}")
    print(f"  总视频数: {index['total_videos']}")
    
    # 3. 测试搜索
    print("\n3. 测试搜索功能...")
    search = VideoSearch(index_file)
    
    # 测试各种搜索
    test_searches = [
        ("搜索分辨率包含'720'", "720"),
        ("搜索高质量视频", "high"),
        ("搜索有音频的视频", "audio"),
        ("按标签搜索", "codec_h264"),
    ]
    
    for desc, query in test_searches:
        print(f"\n{desc}:")
        results = search.search(query)
        if results:
            print(f"  找到 {len(results)} 个结果")
            for result in results[:2]:  # 只显示前2个
                print(f"  - {result['filename']} (匹配度: {result.get('match_score', 'N/A')})")
        else:
            print("  无结果")
    
    # 4. 高级搜索演示
    print("\n4. 高级搜索演示:")
    
    # 按分辨率筛选
    print("\n  按分辨率筛选 (宽度≥700):")
    results = search.search_by_resolution(min_width=700)
    for result in results:
        print(f"  - {result['filename']} ({result['resolution']})")
    
    # 按时长筛选
    print("\n  按时长筛选 (5-10秒):")
    results = search.search_by_duration(min_seconds=5, max_seconds=10)
    for result in results:
        print(f"  - {result['filename']} ({result['duration_formatted']})")
    
    # 5. 显示元数据示例
    print("\n5. 元数据结构示例:")
    if all_metadata:
        sample = all_metadata[0]
        print(f"  文件信息:")
        print(f"    - 文件名: {sample['file_info']['filename']}")
        print(f"    - 大小: {sample['file_info']['file_size_human']}")
        print(f"    - 哈希ID: {sample['file_info']['file_hash']}")
        
        print(f"  技术信息:")
        tech = sample.get('technical_metadata', {})
        video_stream = tech.get('streams', {}).get('video', [{}])[0]
        print(f"    - 分辨率: {video_stream.get('width', '?')}x{video_stream.get('height', '?')}")
        print(f"    - 时长: {tech.get('format', {}).get('duration', '未知')}s")
        print(f"    - 有音频: {len(tech.get('streams', {}).get('audio', [])) > 0}")
        
        print(f"  内容分析:")
        content = sample['content_summary']
        print(f"    - 质量推断: {content.get('inferred_quality', '未知')}")
        print(f"    - 备注: {', '.join(content.get('notes', []))}")
        
        print(f"  搜索标签:")
        tags = sample['index_data']['tags']
        print(f"    - {', '.join(tags)}")
    
    print("\n" + "=" * 60)
    print("演示完成!")
    print(f"\n可用命令:")
    print(f"  查看所有视频: python3 search_videos.py")
    print(f"  关键词搜索: python3 search_videos.py '720'")
    print(f"  按分辨率搜索: python3 search_videos.py --min-width 1000")
    print(f"  按时长搜索: python3 search_videos.py --min-duration 5 --max-duration 10")
    print(f"\n索引文件: {index_file}")

if __name__ == "__main__":
    main()