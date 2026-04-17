#!/usr/bin/env python3
"""
视频索引搜索工具
"""

import json
import argparse
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class VideoSearch:
    def __init__(self, index_file="video_index.json"):
        self.index_file = Path(index_file)
        self.index = self.load_index()
    
    def load_index(self):
        """加载索引文件"""
        if not self.index_file.exists():
            logger.error("索引文件不存在 %s", self.index_file)
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
            # Round-14: defensive accessors. Previously unconditional
            # subscripts raised KeyError on any malformed entry (e.g. old
            # schema or hand-edited index), aborting the ENTIRE search.
            # Now skip malformed entries and continue.
            if not isinstance(video_data, dict):
                continue
            file_info = video_data.get("file_info") or {}
            index_data = video_data.get("index_data") or {}
            content = video_data.get("content_summary") or {}
            tech = video_data.get("technical_summary") or {}

            raw_filename = file_info.get("filename") or ""
            if not raw_filename:
                continue

            match_score = 0
            match_details = []

            filename = raw_filename.lower()
            if query_lower in filename:
                match_score += 10
                match_details.append(f"文件名匹配: {raw_filename}")

            tags = index_data.get("tags") or []
            for tag in tags:
                if query_lower in str(tag).lower():
                    match_score += 5
                    match_details.append(f"标签匹配: {tag}")

            keywords = index_data.get("search_keywords") or []
            for keyword in keywords:
                if query_lower in str(keyword).lower():
                    match_score += 3
                    match_details.append(f"关键词匹配: {keyword}")

            for note in (content.get("notes") or []):
                if query_lower in str(note).lower():
                    match_score += 2
                    match_details.append(f"内容匹配: {note}")

            resolution = str(tech.get("resolution") or "").lower()
            if query_lower in resolution:
                match_score += 4
                match_details.append(f"分辨率匹配: {resolution}")

            if match_score > 0:
                results.append({
                    "video_id": video_id,
                    "filename": raw_filename,
                    "match_score": match_score,
                    "match_details": match_details,
                    "preview_info": index_data.get("preview_info") or {},
                    "content_summary": content,
                    "file_info": {
                        "size": file_info.get("file_size_human") or "",
                        "created": (file_info.get("created_time") or "")[:10],
                    },
                    "usability_score": video_data.get("usability_score"),
                    "usability_tier": video_data.get("usability_tier"),
                    "material_type": video_data.get("material_type"),
                    "trash_level": video_data.get("trash_level"),
                })
        
        # 按匹配分数排序，usability_score 作为同分 tiebreak
        results.sort(
            key=lambda x: (
                x["match_score"],
                x.get("usability_score", 0) or 0,
            ),
            reverse=True,
        )
        return results
    
    def search_by_tags(self, tags):
        """按标签搜索"""
        if not self.index:
            return []
        
        if isinstance(tags, str):
            tags = [tag.strip() for tag in tags.split(",")]
        
        results = []
        for video_id, video_data in self.index.get("videos", {}).items():
            # Round-14: defensive accessors — skip malformed entries.
            if not isinstance(video_data, dict):
                continue
            file_info = video_data.get("file_info") or {}
            index_data = video_data.get("index_data") or {}
            video_tags = index_data.get("tags") or []
            raw_filename = file_info.get("filename") or ""
            if not raw_filename:
                continue

            matched_tags = set(video_tags) & set(tags)
            if matched_tags:
                match_score = len(matched_tags) * 5

                results.append({
                    "video_id": video_id,
                    "filename": raw_filename,
                    "match_score": match_score,
                    "matched_tags": list(matched_tags),
                    "all_tags": video_tags,
                    "preview_info": index_data.get("preview_info") or {},
                    "content_summary": video_data.get("content_summary") or {},
                })
        
        results.sort(key=lambda x: x["match_score"], reverse=True)
        return results
    
    def search_by_resolution(self, min_width=None, min_height=None):
        """按分辨率搜索"""
        if not self.index:
            return []
        
        results = []
        for video_id, video_data in self.index.get("videos", {}).items():
            # Round-14: defensive accessors.
            if not isinstance(video_data, dict):
                continue
            tech = video_data.get("technical_summary") or {}
            resolution = str(tech.get("resolution") or "")

            try:
                if "x" in resolution:
                    width_str, height_str = resolution.split("x", 1)
                    width = int(width_str)
                    height = int(height_str)

                    match = True
                    if min_width and width < min_width:
                        match = False
                    if min_height and height < min_height:
                        match = False

                    if match:
                        file_info = video_data.get("file_info") or {}
                        index_data = video_data.get("index_data") or {}
                        results.append({
                            "video_id": video_id,
                            "filename": file_info.get("filename") or "",
                            "resolution": resolution,
                            "width": width,
                            "height": height,
                            "preview_info": index_data.get("preview_info") or {},
                            "content_summary": video_data.get("content_summary") or {},
                        })
            except (ValueError, TypeError):
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
            except Exception:
                continue
        
        # 按时长排序
        results.sort(key=lambda x: x.get("duration", 0))
        return results

def print_results(results, query=None):
    """打印搜索结果"""
    if not results:
        if query:
            logger.info("未找到匹配 '%s' 的视频", query)
        else:
            logger.info("未找到匹配的视频")
        return

    logger.info("找到 %s 个匹配的视频:", len(results))
    logger.info("=" * 80)

    for i, result in enumerate(results[:10], 1):  # 只显示前10个
        logger.info("%s. %s", i, result['filename'])
        logger.info("   ID: %s", result['video_id'])

        if 'match_score' in result:
            logger.info("   匹配度: %s分", result['match_score'])

        if 'match_details' in result and result['match_details']:
            logger.info("   匹配项: %s", ', '.join(result['match_details'][:3]))

        if 'matched_tags' in result:
            logger.info("   匹配标签: %s", ', '.join(result['matched_tags']))

        preview = result.get('preview_info', {})
        logger.info("   分辨率: %s", preview.get('resolution', '未知'))
        logger.info("   时长: %ss", preview.get('duration', '未知'))

        if preview.get('has_audio'):
            logger.info("   音频: 有")

        content = result.get('content_summary', {})
        if content.get('notes'):
            logger.info("   备注: %s", ', '.join(content['notes'][:2]))

        logger.info("")

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
        except Exception:
            logger.error("分辨率格式应为 宽度x高度，如 1920x1080")
    
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
            logger.error("无法加载索引文件")

if __name__ == "__main__":
    main()