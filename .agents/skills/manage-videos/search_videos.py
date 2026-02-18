#!/usr/bin/env python3
"""
视频索引搜索工具
"""

import json
import argparse
from pathlib import Path

class VideoSearch:
    def __init__(self, index_file="video_index.json"):
        self.index_file = Path(index_file)
        self.index = self.load_index()
    
    def load_index(self):
        """加载索引文件"""
        if not self.index_file.exists():
            print(f"错误: 索引文件不存在 {self.index_file}")
            return None
        
        with open(self.index_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def search(self, query, search_field="all"):
        """搜索视频"""
        if not self.index:
            return []
        
        results = []
        query_lower = query.lower()
        
        for video_id, video_data in self.index.get("videos", {}).items():
            match_score = 0
            match_details = []
            
            # 在文件名中搜索
            filename = video_data["file_info"]["filename"].lower()
            if query_lower in filename:
                match_score += 10
                match_details.append(f"文件名匹配: {video_data['file_info']['filename']}")
            
            # 在标签中搜索
            tags = video_data["index_data"]["tags"]
            for tag in tags:
                if query_lower in tag.lower():
                    match_score += 5
                    match_details.append(f"标签匹配: {tag}")
            
            # 在搜索关键词中搜索
            keywords = video_data["index_data"]["search_keywords"]
            for keyword in keywords:
                if query_lower in str(keyword).lower():
                    match_score += 3
                    match_details.append(f"关键词匹配: {keyword}")
            
            # 在内容摘要中搜索
            content = video_data["content_summary"]
            for note in content.get("notes", []):
                if query_lower in note.lower():
                    match_score += 2
                    match_details.append(f"内容匹配: {note}")
            
            # 在技术信息中搜索
            tech = video_data["technical_summary"]
            resolution = tech.get("resolution", "").lower()
            if query_lower in resolution:
                match_score += 4
                match_details.append(f"分辨率匹配: {resolution}")
            
            if match_score > 0:
                results.append({
                    "video_id": video_id,
                    "filename": video_data["file_info"]["filename"],
                    "match_score": match_score,
                    "match_details": match_details,
                    "preview_info": video_data["index_data"]["preview_info"],
                    "content_summary": video_data["content_summary"],
                    "file_info": {
                        "size": video_data["file_info"]["file_size_human"],
                        "created": video_data["file_info"]["created_time"][:10]
                    }
                })
        
        # 按匹配分数排序
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results
    
    def search_by_tags(self, tags):
        """按标签搜索"""
        if not self.index:
            return []
        
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",")]
        
        results = []
        for video_id, video_data in self.index.get("videos", {}).items():
            video_tags = video_data["index_data"]["tags"]
            
            # 计算标签匹配度
            matched_tags = set(video_tags) & set(tags)
            if matched_tags:
                match_score = len(matched_tags) * 5
                
                results.append({
                    "video_id": video_id,
                    "filename": video_data["file_info"]["filename"],
                    "match_score": match_score,
                    "matched_tags": list(matched_tags),
                    "all_tags": video_tags,
                    "preview_info": video_data["index_data"]["preview_info"],
                    "content_summary": video_data["content_summary"]
                })
        
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results
    
    def search_by_resolution(self, min_width=None, min_height=None):
        """按分辨率搜索"""
        if not self.index:
            return []
        
        results = []
        for video_id, video_data in self.index.get("videos", {}).items():
            resolution = video_data["technical_summary"]["resolution"]
            
            # 解析分辨率
            try:
                if "x" in resolution:
                    width_str, height_str = resolution.split("x")
                    width = int(width_str)
                    height = int(height_str)
                    
                    match = True
                    if min_width and width < min_width:
                        match = False
                    if min_height and height < min_height:
                        match = False
                    
                    if match:
                        results.append({
                            "video_id": video_id,
                            "filename": video_data["file_info"]["filename"],
                            "resolution": resolution,
                            "width": width,
                            "height": height,
                            "preview_info": video_data["index_data"]["preview_info"],
                            "content_summary": video_data["content_summary"]
                        })
            except:
                continue
        
        # 按分辨率排序（从高到低）
        results.sort(key=lambda x: (x.get("width", 0), x.get("height", 0)), reverse=True)
        return results
    
    def search_by_duration(self, min_seconds=None, max_seconds=None):
        """按时长搜索"""
        if not self.index:
            return []
        
        results = []
        for video_id, video_data in self.index.get("videos", {}).items():
            duration_str = video_data["technical_summary"]["duration"]
            
            try:
                duration = float(duration_str)
                
                match = True
                if min_seconds and duration < min_seconds:
                    match = False
                if max_seconds and duration > max_seconds:
                    match = False
                
                if match:
                    results.append({
                        "video_id": video_id,
                        "filename": video_data["file_info"]["filename"],
                        "duration": duration,
                        "duration_formatted": f"{duration:.1f}s",
                        "preview_info": video_data["index_data"]["preview_info"],
                        "content_summary": video_data["content_summary"]
                    })
            except:
                continue
        
        # 按时长排序
        results.sort(key=lambda x: x.get("duration", 0))
        return results

def print_results(results, query=None):
    """打印搜索结果"""
    if not results:
        if query:
            print(f"未找到匹配 '{query}' 的视频")
        else:
            print("未找到匹配的视频")
        return
    
    print(f"找到 {len(results)} 个匹配的视频:")
    print("=" * 80)
    
    for i, result in enumerate(results[:10], 1):  # 只显示前10个
        print(f"{i}. {result['filename']}")
        print(f"   ID: {result['video_id']}")
        
        if 'match_score' in result:
            print(f"   匹配度: {result['match_score']}分")
        
        if 'match_details' in result and result['match_details']:
            print(f"   匹配项: {', '.join(result['match_details'][:3])}")
        
        if 'matched_tags' in result:
            print(f"   匹配标签: {', '.join(result['matched_tags'])}")
        
        preview = result.get('preview_info', {})
        print(f"   分辨率: {preview.get('resolution', '未知')}")
        print(f"   时长: {preview.get('duration', '未知')}s")
        
        if preview.get('has_audio'):
            print(f"   音频: 有")
        
        content = result.get('content_summary', {})
        if content.get('notes'):
            print(f"   备注: {', '.join(content['notes'][:2])}")
        
        print()

def main():
    parser = argparse.ArgumentParser(description="视频索引搜索工具")
    parser.add_argument("query", nargs="?", help="搜索关键词")
    parser.add_argument("--tags", help="按标签搜索，用逗号分隔")
    parser.add_argument("--resolution", help="按分辨率搜索，如 1920x1080")
    parser.add_argument("--min-width", type=int, help="最小宽度")
    parser.add_argument("--min-height", type=int, help="最小高度")
    parser.add_argument("--min-duration", type=float, help="最小时长（秒）")
    parser.add_argument("--max-duration", type=float, help="最大时长（秒）")
    parser.add_argument("--index", default="video_index.json", help="索引文件路径")
    
    args = parser.parse_args()
    
    search = VideoSearch(args.index)
    
    if args.tags:
        results = search.search_by_tags(args.tags)
        print_results(results, f"标签: {args.tags}")
    
    elif args.resolution:
        try:
            width, height = map(int, args.resolution.split("x"))
            results = search.search_by_resolution(width, height)
            print_results(results, f"分辨率 ≥ {args.resolution}")
        except:
            print("错误: 分辨率格式应为 宽度x高度，如 1920x1080")
    
    elif args.min_width or args.min_height:
        results = search.search_by_resolution(args.min_width, args.min_height)
        desc = []
        if args.min_width:
            desc.append(f"宽度≥{args.min_width}")
        if args.min_height:
            desc.append(f"高度≥{args.min_height}")
        print_results(results, f"分辨率: {'且'.join(desc)}")
    
    elif args.min_duration or args.max_duration:
        results = search.search_by_duration(args.min_duration, args.max_duration)
        desc = []
        if args.min_duration:
            desc.append(f"≥{args.min_duration}s")
        if args.max_duration:
            desc.append(f"≤{args.max_duration}s")
        print_results(results, f"时长: {'-'.join(desc)}")
    
    elif args.query:
        results = search.search(args.query)
        print_results(results, args.query)
    
    else:
        # 显示所有视频
        if search.index:
            all_videos = []
            for video_id, video_data in search.index.get("videos", {}).items():
                all_videos.append({
                    "video_id": video_id,
                    "filename": video_data["file_info"]["filename"],
                    "preview_info": video_data["index_data"]["preview_info"],
                    "content_summary": video_data["content_summary"]
                })
            print_results(all_videos, "所有视频")
        else:
            print("无法加载索引文件")

if __name__ == "__main__":
    main()