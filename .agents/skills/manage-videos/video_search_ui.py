#!/usr/bin/env python3
"""
视频搜索界面演示（类似Edit Mind但更好用）
支持：关键词搜索 + 多维度筛选 + 智能排序
"""

import json
from pathlib import Path
import argparse
from datetime import datetime

class VideoSearchUI:
    def __init__(self, index_file="enhanced_analysis_results.json"):
        self.index_file = Path(index_file)
        self.data = self.load_data()
        self.videos = self.prepare_videos()
        
        # 可用的筛选维度
        self.filter_dimensions = {
            "technical": ["resolution", "quality", "duration", "codec"],
            "content": ["perspective", "action", "scene", "objects"],
            "emotional": ["mood", "energy", "aesthetic"],
            "business": ["quality_tier", "usage", "value"]
        }
    
    def load_data(self):
        """加载数据"""
        if not self.index_file.exists():
            print(f"错误: 数据文件不存在 {self.index_file}")
            return None
        
        with open(self.index_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def prepare_videos(self):
        """准备视频数据"""
        if not self.data:
            return []
        
        videos = []
        for video_id, video_data in self.data.get("results", {}).items():
            # 提取搜索相关数据
            basic = video_data.get("basic_info", {})
            technical = video_data.get("technical_analysis", {})
            content = video_data.get("content_analysis", {})
            emotional = video_data.get("emotional_analysis", {})
            business = video_data.get("business_analysis", {})
            search_idx = video_data.get("search_index", {})
            
            video = {
                "id": video_id,
                "filename": basic.get("filename", ""),
                "filepath": basic.get("filepath", ""),
                "size": basic.get("size_human", ""),
                "created": basic.get("created", ""),
                
                # 技术信息
                "resolution": technical.get("resolution", ""),
                "width": technical.get("width", 0),
                "height": technical.get("height", 0),
                "duration": float(technical.get("duration", 0) or 0),
                "quality": technical.get("quality_level", ""),
                "quality_score": technical.get("quality_score", 0),
                "codec": technical.get("codec", ""),
                
                # 内容信息
                "perspective": content.get("perspective", ""),
                "action": content.get("action", ""),
                "scene": content.get("scene", ""),
                "shot_type": content.get("shot_type", ""),
                "objects": content.get("objects", []),
                "description": content.get("description", ""),
                
                # 情感信息
                "mood": emotional.get("mood", ""),
                "energy": emotional.get("energy", ""),
                "aesthetic": emotional.get("aesthetic", ""),
                "emotional_tags": emotional.get("emotional_tags", []),
                
                # 业务信息
                "quality_tier": business.get("quality_tier", ""),
                "usage": business.get("suggested_usage", []),
                "audience": business.get("target_audience", []),
                "value": business.get("business_value", 0),
                "recommendations": business.get("recommendations", []),
                
                # 搜索索引
                "tags": search_idx.get("tags", []),
                "search_fields": search_idx.get("search_fields", {}),
                "preview": search_idx.get("preview", {})
            }
            videos.append(video)
        
        return videos
    
    def search(self, query=None, filters=None, sort_by="relevance"):
        """搜索视频"""
        results = self.videos.copy()
        
        # 关键词搜索
        if query:
            query_lower = query.lower()
            scored_results = []
            
            for video in results:
                score = 0
                
                # 文件名匹配（最高权重）
                if query_lower in video["filename"].lower():
                    score += 10
                
                # 描述匹配
                if query_lower in video["description"].lower():
                    score += 8
                
                # 标签匹配
                for tag in video["tags"]:
                    if query_lower in tag.lower():
                        score += 5
                
                # 物体匹配
                for obj in video["objects"]:
                    if query_lower in obj.lower():
                        score += 3
                
                # 使用场景匹配
                for usage in video["usage"]:
                    if query_lower in usage.lower():
                        score += 3
                
                if score > 0:
                    video["relevance_score"] = score
                    scored_results.append(video)
            
            results = scored_results
        
        # 应用筛选器
        if filters:
            filtered_results = []
            for video in results:
                match = True
                
                for filter_key, filter_value in filters.items():
                    if filter_key == "min_width" and video["width"] < filter_value:
                        match = False
                        break
                    elif filter_key == "min_height" and video["height"] < filter_value:
                        match = False
                        break
                    elif filter_key == "min_duration" and video["duration"] < filter_value:
                        match = False
                        break
                    elif filter_key == "max_duration" and video["duration"] > filter_value:
                        match = False
                        break
                    elif filter_key == "quality" and video["quality"] != filter_value:
                        match = False
                        break
                    elif filter_key == "perspective" and video["perspective"] != filter_value:
                        match = False
                        break
                    elif filter_key == "action" and video["action"] != filter_value:
                        match = False
                        break
                    elif filter_key == "scene" and video["scene"] != filter_value:
                        match = False
                        break
                    elif filter_key == "mood" and video["mood"] != filter_value:
                        match = False
                        break
                    elif filter_key == "has_audio" and not video.get("has_audio", True):
                        match = False
                        break
                
                if match:
                    filtered_results.append(video)
            
            results = filtered_results
        
        # 排序
        if sort_by == "relevance" and query:
            results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        elif sort_by == "quality":
            results.sort(key=lambda x: x["quality_score"], reverse=True)
        elif sort_by == "duration":
            results.sort(key=lambda x: x["duration"])
        elif sort_by == "resolution":
            results.sort(key=lambda x: (x["width"], x["height"]), reverse=True)
        elif sort_by == "value":
            results.sort(key=lambda x: x["value"], reverse=True)
        
        return results
    
    def print_results(self, results, query=None, show_details=False):
        """打印搜索结果"""
        if not results:
            if query:
                print(f"🔍 未找到匹配 '{query}' 的视频")
            else:
                print("📭 没有视频数据")
            return
        
        print(f"✅ 找到 {len(results)} 个视频")
        if query:
            print(f"   搜索词: '{query}'")
        print("=" * 100)
        
        for i, video in enumerate(results[:20], 1):  # 只显示前20个
            print(f"{i:2d}. 🎬 {video['filename']}")
            
            # 基础信息
            print(f"     📍 文件: {video['filepath']}")
            print(f"     📏 分辨率: {video['resolution']} | ⏱️ 时长: {video['duration']:.1f}s | 📊 质量: {video['quality']}")
            
            # 内容信息（如果有）
            if video['description'] and video['description'] != "一般视频内容":
                print(f"     🎯 内容: {video['description']}")
            
            # 标签
            if video['tags']:
                tags_display = [tag for tag in video['tags'] if tag not in ['general', 'medium_shot', 'energy_low']]
                if tags_display:
                    print(f"     🏷️  标签: {', '.join(tags_display[:8])}")
            
            # 使用场景
            if video['usage']:
                print(f"     💼 用途: {', '.join(video['usage'][:3])}")
            
            # 匹配分数（如果有）
            if 'relevance_score' in video:
                print(f"     ⭐ 匹配度: {video['relevance_score']}分")
            
            # 详细模式
            if show_details:
                if video['objects']:
                    print(f"     🔍 物体: {', '.join(video['objects'])}")
                if video['emotional_tags']:
                    print(f"     😊 情感: {', '.join(video['emotional_tags'])}")
                if video['recommendations']:
                    print(f"     💡 建议: {', '.join(video['recommendations'])}")
            
            print()
    
    def print_filter_panel(self):
        """打印筛选面板（类似Edit Mind）"""
        print("🎛️  筛选面板")
        print("-" * 50)
        
        # 收集所有可用的筛选值
        all_perspectives = set()
        all_actions = set()
        all_scenes = set()
        all_qualities = set()
        all_moods = set()
        
        for video in self.videos:
            if video["perspective"]:
                all_perspectives.add(video["perspective"])
            if video["action"]:
                all_actions.add(video["action"])
            if video["scene"]:
                all_scenes.add(video["scene"])
            if video["quality"]:
                all_qualities.add(video["quality"])
            if video["mood"]:
                all_moods.add(video["mood"])
        
        print("📷 拍摄视角:")
        for perspective in sorted(all_perspectives):
            if perspective != "unknown":
                print(f"   □ {perspective}")
        
        print("\n🎬 动作类型:")
        for action in sorted(all_actions):
            if action != "general":
                print(f"   □ {action}")
        
        print("\n🏞️  场景类型:")
        for scene in sorted(all_scenes):
            if scene != "general":
                print(f"   □ {scene}")
        
        print("\n📊 质量等级:")
        for quality in sorted(all_qualities):
            print(f"   □ {quality}")
        
        print("\n😊 情感氛围:")
        for mood in sorted(all_moods):
            if mood != "neutral":
                print(f"   □ {mood}")
        
        print("\n⏱️  时长范围:")
        print("   □ < 10秒")
        print("   □ 10-30秒")
        print("   □ 30-60秒")
        print("   □ > 60秒")
        
        print("\n📏 分辨率:")
        print("   □ 4K (3840x2160+)")
        print("   □ 1080p (1920x1080)")
        print("   □ 720p (1280x720)")
        print("   □ 标清 (<720p)")
        
        print("-" * 50)
    
    def interactive_search(self):
        """交互式搜索"""
        print("🎬 视频搜索系统")
        print("=" * 60)
        
        while True:
            print("\n请选择操作:")
            print("1. 🔍 关键词搜索")
            print("2. 🎛️  查看筛选面板")
            print("3. 📋 查看所有视频")
            print("4. 📊 查看统计信息")
            print("5. 🚪 退出")
            
            choice = input("\n请输入选项 (1-5): ").strip()
            
            if choice == "1":
                query = input("请输入搜索关键词: ").strip()
                if not query:
                    print("❌ 请输入搜索词")
                    continue
                
                # 询问筛选条件
                filters = {}
                print("\n可选筛选条件 (直接回车跳过):")
                
                min_width = input("最小宽度 (像素): ").strip()
                if min_width:
                    filters["min_width"] = int(min_width)
                
                min_height = input("最小高度 (像素): ").strip()
                if min_height:
                    filters["min_height"] = int(min_height)
                
                min_duration = input("最小时长 (秒): ").strip()
                if min_duration:
                    filters["min_duration"] = float(min_duration)
                
                max_duration = input("最大时长 (秒): ").strip()
                if max_duration:
                    filters["max_duration"] = float(max_duration)
                
                quality = input("质量等级 (high/medium/low): ").strip()
                if quality in ["high", "medium", "low"]:
                    filters["quality"] = quality
                
                # 执行搜索
                results = self.search(query=query, filters=filters if filters else None)
                self.print_results(results, query)
                
            elif choice == "2":
                self.print_filter_panel()
                
            elif choice == "3":
                results = self.search()
                self.print_results(results, show_details=True)
                
            elif choice == "4":
                self.print_statistics()
                
            elif choice == "5":
                print("👋 再见！")
                break
            else:
                print("❌ 无效选项")
    
    def print_statistics(self):
        """打印统计信息"""
        if not self.videos:
            print("📭 没有视频数据")
            return
        
        print("📊 视频库统计")
        print("-" * 50)
        
        total = len(self.videos)
        print(f"总视频数: {total}")
        
        # 分辨率统计
        resolutions = {}
        for video in self.videos:
            res = video["resolution"]
            resolutions[res] = resolutions.get(res, 0) + 1
        
        print(f"\n📏 分辨率分布:")
        for res, count in sorted(resolutions.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total) * 100
            print(f"  {res}: {count}个 ({percentage:.1f}%)")
        
        # 质量统计
        qualities = {}
        for video in self.videos:
            quality = video["quality"]
            qualities[quality] = qualities.get(quality, 0) + 1
        
        print(f"\n📊 质量分布:")
        for quality, count in sorted(qualities.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total) * 100
            print(f"  {quality}: {count}个 ({percentage:.1f}%)")
        
        # 时长统计
        durations = [v["duration"] for v in self.videos]
        if durations:
            avg_duration = sum(durations) / len(durations)
            max_duration = max(durations)
            min_duration = min(durations)
            print(f"\n⏱️  时长统计:")
            print(f"  平均: {avg_duration:.1f}秒")
            print(f"  最长: {max_duration:.1f}秒")
            print(f"  最短: {min_duration:.1f}秒")
        
        # 标签统计
        all_tags = []
        for video in self.videos:
            all_tags.extend(video["tags"])
        
        from collections import Counter
        tag_counts = Counter(all_tags)
        
        print(f"\n🏷️  热门标签 (前10):")
        for tag, count in tag_counts.most_common(10):
            print(f"  {tag}: {count}次")

def main():
    parser = argparse.ArgumentParser(description="视频搜索界面")
    parser.add_argument("--query", "-q", help="搜索关键词")
    parser.add_argument("--min-width", type=int, help="最小宽度")
    parser.add_argument("--min-height", type=int, help="最小高度")
    parser.add_argument("--min-duration", type=float, help="最小时长(秒)")
    parser.add_argument("--max-duration", type=float, help="最大时长(秒)")
    parser.add_argument("--quality", help="质量等级")
    parser.add_argument("--perspective", help="拍摄视角")
    parser.add_argument("--action", help="动作类型")
    parser.add_argument("--scene", help="场景类型")
    parser.add_argument("--mood", help="情感氛围")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--index", default="enhanced_analysis_results.json", help="数据文件")
    
    args = parser.parse_args()
    
    search_ui = VideoSearchUI(args.index)
    
    if args.interactive:
        search_ui.interactive_search()
    else:
        # 构建筛选器
        filters = {}
        if args.min_width:
            filters["min_width"] = args.min_width
        if args.min_height:
            filters["min_height"] = args.min_height
        if args.min_duration:
            filters["min_duration"] = args.min_duration
        if args.max_duration:
            filters["max_duration"] = args.max_duration
        if args.quality:
            filters["quality"] = args.quality
        if args.perspective:
            filters["perspective"] = args.perspective
        if args.action:
            filters["action"] = args.action
        if args.scene:
            filters["scene"] = args.scene
        if args.mood:
            filters["mood"] = args.mood
        
        # 执行搜索
        results = search_ui.search(query=args.query, filters=filters if filters else None)
        search_ui.print_results(results, args.query, show_details=True)

if __name__ == "__main__":
    main()