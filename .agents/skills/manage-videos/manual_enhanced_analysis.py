#!/usr/bin/env python3
"""
手动增强分析：基于你的反馈直接修正
"""

import json
from datetime import datetime

def analyze_with_feedback():
    """基于你的反馈进行分析"""
    
    # 知识库
    knowledge = {
        "mestia": {
            "name": "梅斯蒂亚",
            "country": "格鲁吉亚",
            "description": "格鲁吉亚著名滑雪胜地，以野雪和自然风光闻名",
            "keywords": ["滑雪", "野雪", "徒步", "高山", "冒险"]
        },
        "ushguli": {
            "name": "乌树故里",
            "country": "格鲁吉亚",
            "description": "欧洲最高的永久居住村落，UNESCO世界遗产",
            "keywords": ["世界遗产", "中世纪", "徒步", "摄影", "文化"]
        },
        "georgian_instruments": {
            "description": "格鲁吉亚传统乐器，常见于旅游纪念品商店",
            "context": "旅游购物场景，面向游客的商品展示",
            "keywords": ["传统", "文化", "旅游", "纪念品", "手工艺品"]
        }
    }
    
    # 基于你的反馈进行分析
    analyses = {
        "4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov": {
            "filename": "4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov",
            "user_feedback": "背景是在伴手礼品店，旅游纪念品",
            
            # 修正后的分析
            "content_type": "cultural_display",
            "detailed_description": "格鲁吉亚传统乐器在旅游纪念品商店的展示",
            "location_context": "旅游购物场景，伴手礼品店",
            "shooting_perspective": "固定机位，商品展示角度",
            "cultural_context": "面向游客的旅游纪念品，非正式文化展示",
            
            # 技术分析
            "technical": {
                "resolution": "1744x1308",
                "duration": "1.8秒",
                "quality": "高清但短暂"
            },
            
            # 业务分析
            "business_value": {
                "primary_use": "旅游内容、文化介绍、纪念品展示",
                "target_audience": "旅行爱好者、文化探索者、购物指南观众",
                "content_angle": "旅游购物体验、地方特色商品、文化接触点"
            },
            
            # 搜索标签
            "search_tags": [
                "格鲁吉亚", "传统乐器", "旅游纪念品", "伴手礼", "文化展示",
                "旅游购物", "手工艺品", "固定机位", "商品展示"
            ],
            
            "confidence": 0.95  # 基于用户反馈，置信度高
        },
        
        "477ed0c7-6344-4fdb-9eed-bf7977141348.mov": {
            "filename": "477ed0c7-6344-4fdb-9eed-bf7977141348.mov",
            "user_feedback": "混剪视频，不是高空俯视，而是人站在山顶拍的",
            
            # 修正后的分析
            "content_type": "travel_experience",
            "detailed_description": "乌树故里（Ushguli）山顶视角的旅行混剪视频",
            "location_context": "格鲁吉亚斯瓦涅季地区，世界遗产村落",
            "shooting_perspective": "山顶视角（非航拍），手持/三脚架拍摄",
            "video_type": "混剪，多个镜头组合",
            
            # 技术分析
            "technical": {
                "resolution": "480x854",
                "duration": "6.1秒",
                "quality": "中等分辨率，适合移动端观看"
            },
            
            # 业务分析
            "business_value": {
                "primary_use": "旅行vlog、风景展示、目的地推广",
                "target_audience": "旅行者、摄影爱好者、文化探索者",
                "content_angle": "山顶视角体验、世界遗产展示、旅行瞬间记录"
            },
            
            # 搜索标签
            "search_tags": [
                "乌树故里", "Ushguli", "格鲁吉亚", "世界遗产", "山顶视角",
                "旅行混剪", "风景展示", "徒步旅行", "文化探索", "中世纪村落"
            ],
            
            "confidence": 0.90
        },
        
        "57c73514-c369-42ad-b502-50cf893a90f5.mp4": {
            "filename": "57c73514-c369-42ad-b502-50cf893a90f5.mp4",
            "user_feedback": "梅斯蒂亚山顶的野雪，不是滑雪场",
            
            # 修正后的分析
            "content_type": "adventure_sports",
            "detailed_description": "梅斯蒂亚（Mestia）山顶野雪的第一人称滑雪",
            "location_context": "格鲁吉亚梅斯蒂亚，专业野雪区域",
            "shooting_perspective": "第一人称视角（POV），运动相机拍摄",
            "sport_context": "野雪滑雪（backcountry），非压雪雪道",
            
            # 技术分析
            "technical": {
                "resolution": "720x1280",
                "duration": "8.5秒",
                "quality": "良好画质，适合动作展示",
                "special": "包含英文字幕"
            },
            
            # 业务分析
            "business_value": {
                "primary_use": "运动教程、冒险旅行、专业滑雪内容",
                "target_audience": "滑雪爱好者、冒险旅行者、运动品牌受众",
                "content_angle": "专业野雪体验、第一人称冒险、自然雪质展示",
                "safety_note": "野雪需要专业培训和装备"
            },
            
            # 搜索标签
            "search_tags": [
                "梅斯蒂亚", "Mestia", "格鲁吉亚", "野雪", "第一人称滑雪",
                "backcountry", "冒险运动", "运动相机", "粉雪", "高山滑雪",
                "专业滑雪", "自然雪", "冒险旅行"
            ],
            
            "confidence": 0.95
        }
    }
    
    return analyses

def print_analysis_results(analyses):
    """打印分析结果"""
    print("🎬 基于反馈的增强分析结果")
    print("=" * 80)
    
    for filename, analysis in analyses.items():
        print(f"\n📹 视频: {filename}")
        print(f"  用户反馈: {analysis['user_feedback']}")
        print(f"  详细描述: {analysis['detailed_description']}")
        print(f"  置信度: {analysis['confidence']}")
        
        # 技术信息
        tech = analysis.get('technical', {})
        print(f"  技术: {tech.get('resolution', '未知')}, {tech.get('duration', '未知')}")
        
        # 业务价值
        business = analysis.get('business_value', {})
        print(f"  主要用途: {business.get('primary_use', '未知')}")
        print(f"  目标受众: {business.get('target_audience', '未知')}")
        
        # 搜索标签（前5个）
        tags = analysis.get('search_tags', [])
        if tags:
            print(f"  搜索标签: {', '.join(tags[:5])}")
            if len(tags) > 5:
                print(f"          还有 {len(tags)-5} 个标签")
        
        print(f"  {'─'*40}")

def generate_search_index(analyses):
    """生成搜索索引"""
    index = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "analyzer": "manual_enhanced",
            "total_videos": len(analyses)
        },
        "videos": {},
        "tag_index": {}
    }
    
    # 构建视频索引
    for filename, analysis in analyses.items():
        video_id = f"video_{hash(filename) % 10000:04d}"
        
        index["videos"][video_id] = {
            "filename": filename,
            "analysis": {
                "description": analysis["detailed_description"],
                "content_type": analysis["content_type"],
                "location": analysis.get("location_context", ""),
                "perspective": analysis.get("shooting_perspective", ""),
                "confidence": analysis["confidence"]
            },
            "technical": analysis.get("technical", {}),
            "business": analysis.get("business_value", {}),
            "search_tags": analysis.get("search_tags", [])
        }
        
        # 构建标签倒排索引
        for tag in analysis.get("search_tags", []):
            if tag not in index["tag_index"]:
                index["tag_index"][tag] = []
            index["tag_index"][tag].append({
                "video_id": video_id,
                "filename": filename,
                "relevance": 1.0
            })
    
    return index

def search_by_tag(index, tag):
    """通过标签搜索"""
    results = []
    
    # 直接标签匹配
    if tag in index["tag_index"]:
        for item in index["tag_index"][tag]:
            video_info = index["videos"][item["video_id"]]
            results.append({
                "filename": video_info["filename"],
                "description": video_info["analysis"]["description"],
                "relevance": item["relevance"],
                "tags": video_info["search_tags"]
            })
    
    # 模糊匹配（标签包含搜索词）
    for tag_key, items in index["tag_index"].items():
        if tag in tag_key and tag_key not in [r["filename"] for r in results]:
            for item in items:
                video_info = index["videos"][item["video_id"]]
                results.append({
                    "filename": video_info["filename"],
                    "description": video_info["analysis"]["description"],
                    "relevance": item["relevance"] * 0.8,  # 降低权重
                    "tags": video_info["search_tags"]
                })
    
    # 按相关性排序
    results.sort(key=lambda x: x["relevance"], reverse=True)
    return results

def main():
    """主函数"""
    print("🔍 手动增强分析系统")
    print("基于你的反馈进行精确分析")
    print("=" * 80)
    
    # 1. 进行分析
    analyses = analyze_with_feedback()
    
    # 2. 打印结果
    print_analysis_results(analyses)
    
    # 3. 生成搜索索引
    index = generate_search_index(analyses)
    
    # 4. 保存结果
    output_file = "manual_enhanced_index.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 分析完成！结果已保存到: {output_file}")
    
    # 5. 演示搜索功能
    print("\n🔍 搜索演示:")
    print("-" * 40)
    
    test_searches = ["格鲁吉亚", "滑雪", "第一人称", "旅游", "传统"]
    
    for search_term in test_searches:
        results = search_by_tag(index, search_term)
        print(f"\n搜索 '{search_term}':")
        if results:
            for result in results[:2]:  # 只显示前2个
                print(f"  - {result['filename']}")
                print(f"    描述: {result['description'][:50]}...")
                print(f"    相关标签: {', '.join(result['tags'][:3])}")
        else:
            print("  无结果")
    
    print("\n" + "=" * 80)
    print("🎯 关键改进:")
    print("1. 视频1: 旅游纪念品商店 → 更准确的业务场景")
    print("2. 视频2: 山顶视角混剪 → 正确的拍摄方式")
    print("3. 视频3: 梅斯蒂亚野雪 → 专业的地理和运动上下文")
    print("\n✅ 现在分析结果更准确，搜索标签更有用！")

if __name__ == "__main__":
    main()