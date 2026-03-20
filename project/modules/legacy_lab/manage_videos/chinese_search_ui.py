#!/usr/bin/env python3
"""
中文视频搜索界面 - 支持中文关键词搜索
"""

import json
import sys
from pathlib import Path
import argparse
from datetime import datetime

class ChineseVideoSearchUI:
    def __init__(self, index_file="manual_enhanced_index.json"):
        self.index_file = Path(index_file)
        self.data = self.load_data()
        self.videos = self.prepare_videos()
        
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
        for video_id, video_data in self.data.get("videos", {}).items():
            analysis = video_data.get("analysis", {})
            technical = video_data.get("technical", {})
            business = video_data.get("business", {})
            
            video = {
                "id": video_id,
                "filename": video_data.get("filename", ""),
                "description": analysis.get("description", ""),
                "content_type": analysis.get("content_type", ""),
                "location": analysis.get("location", ""),
                "perspective": analysis.get("perspective", ""),
                "confidence": analysis.get("confidence", 0),
                
                # 技术信息
                "resolution": technical.get("resolution", ""),
                "duration": technical.get("duration", ""),
                "quality": technical.get("quality", ""),
                "special": technical.get("special", ""),
                
                # 业务信息
                "primary_use": business.get("primary_use", ""),
                "target_audience": business.get("target_audience", ""),
                "content_angle": business.get("content_angle", ""),
                "safety_note": business.get("safety_note", ""),
                
                # 搜索标签
                "search_tags": video_data.get("search_tags", [])
            }
            videos.append(video)
        
        return videos
    
    def search(self, query=None, content_type=None, location=None):
        """搜索视频"""
        results = self.videos.copy()
        
        # 关键词搜索
        if query:
            query_lower = query.lower()
            scored_results = []
            
            for video in results:
                score = 0
                
                # 描述匹配（最高权重）
                if query_lower in video["description"].lower():
                    score += 10
                
                # 标签匹配
                for tag in video["search_tags"]:
                    if query_lower in tag.lower():
                        score += 5
                
                # 内容类型匹配
                if query_lower in video["content_type"].lower():
                    score += 3
                
                # 地点匹配
                if query_lower in video["location"].lower():
                    score += 3
                
                # 用途匹配
                if query_lower in video["primary_use"].lower():
                    score += 3
                
                if score > 0:
                    video["relevance_score"] = score
                    scored_results.append(video)
            
            results = scored_results
        
        # 内容类型筛选
        if content_type:
            results = [v for v in results if content_type.lower() in v["content_type"].lower()]
        
        # 地点筛选
        if location:
            results = [v for v in results if location.lower() in v["location"].lower()]
        
        # 按匹配度排序
        if query:
            results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return results
    
    def print_results(self, results, query=None):
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
        
        for i, video in enumerate(results, 1):
            print(f"{i}. 🎬 {video['filename']}")
            print(f"   📝 描述: {video['description']}")
            print(f"   📍 地点: {video['location']}")
            print(f"   📷 视角: {video['perspective']}")
            print(f"   📏 分辨率: {video['resolution']} | ⏱️ 时长: {video['duration']} | 📊 质量: {video['quality']}")
            
            # 标签
            if video['search_tags']:
                print(f"   🏷️  标签: {', '.join(video['search_tags'][:8])}")
            
            # 用途
            if video['primary_use']:
                print(f"   💼 用途: {video['primary_use']}")
            
            # 匹配分数（如果有）
            if 'relevance_score' in video:
                print(f"   ⭐ 匹配度: {video['relevance_score']}分")
            
            print()
    
    def print_all_tags(self):
        """打印所有可用标签"""
        all_tags = set()
        for video in self.videos:
            all_tags.update(video["search_tags"])
        
        print("🏷️  可用搜索标签:")
        print("-" * 50)
        
        tags_list = sorted(list(all_tags))
        for i, tag in enumerate(tags_list, 1):
            print(f"{tag:15}", end=" ")
            if i % 5 == 0:
                print()
        
        if len(tags_list) % 5 != 0:
            print()
        
        print(f"\n总计: {len(tags_list)} 个标签")
    
    def interactive_search(self):
        """交互式搜索（仅限终端环境，非交互环境直接返回）"""
        if not sys.stdin.isatty():
            print("⚠️  非交互式环境，跳过 interactive_search")
            return
        print("🎬 中文视频搜索系统")
        print("=" * 60)

        while True:
            print("\n请选择操作:")
            print("1. 🔍 关键词搜索")
            print("2. 🏷️  查看所有标签")
            print("3. 📋 查看所有视频")
            print("4. 🚪 退出")
            
            try:
                choice = input("\n请输入选项 (1-4): ").strip()
            except EOFError:
                print("\n👋 再见！")
                break
            
            if choice == "1":
                query = input("请输入搜索关键词: ").strip()
                if not query:
                    print("❌ 请输入搜索词")
                    continue
                
                # 可选筛选
                content_type = input("内容类型筛选 (直接回车跳过): ").strip()
                location = input("地点筛选 (直接回车跳过): ").strip()
                
                # 执行搜索
                results = self.search(
                    query=query, 
                    content_type=content_type if content_type else None,
                    location=location if location else None
                )
                self.print_results(results, query)
                
            elif choice == "2":
                self.print_all_tags()
                
            elif choice == "3":
                results = self.search()
                self.print_results(results)
                
            elif choice == "4":
                print("👋 再见！")
                break
            else:
                print("❌ 无效选项")

def main():
    parser = argparse.ArgumentParser(description="中文视频搜索界面")
    parser.add_argument("--query", "-q", help="搜索关键词")
    parser.add_argument("--content-type", help="内容类型筛选")
    parser.add_argument("--location", help="地点筛选")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--index", default="manual_enhanced_index.json", help="数据文件")
    
    args = parser.parse_args()
    
    search_ui = ChineseVideoSearchUI(args.index)
    
    if args.interactive:
        search_ui.interactive_search()
    else:
        # 执行搜索
        results = search_ui.search(
            query=args.query,
            content_type=args.content_type,
            location=args.location
        )
        search_ui.print_results(results, args.query)

if __name__ == "__main__":
    main()