#!/usr/bin/env python3
"""
视界工具箱 - 运行脚本
"""

import sys
import argparse
from pathlib import Path
from video_asset_toolkit import VideoAssetToolkit

def main():
    parser = argparse.ArgumentParser(description="视频资产分析工具箱")
    parser.add_argument("input", nargs="+", help="视频文件或目录路径")
    parser.add_argument("--config", default="config.json", help="配置文件路径")
    parser.add_argument("--output", choices=["json", "markdown", "csv", "all"], default="all", help="输出格式")
    parser.add_argument("--batch", action="store_true", help="批量处理模式")
    
    args = parser.parse_args()
    
    # 初始化工具箱
    toolkit = VideoAssetToolkit(args.config)
    
    # 收集视频文件
    video_files = []
    for input_path in args.input:
        path = Path(input_path)
        if path.is_file():
            if path.suffix.lower() in ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv']:
                video_files.append(path)
        elif path.is_dir():
            for ext in ['*.mp4', '*.mov', '*.avi', '*.mkv', '*.flv', '*.wmv']:
                video_files.extend(path.glob(ext))
    
    if not video_files:
        print("错误: 未找到视频文件")
        sys.exit(1)
    
    print(f"找到 {len(video_files)} 个视频文件")
    
    # 分析视频
    results = toolkit.analyze_videos(video_files, args.output)
    
    print(f"\n分析完成！共分析 {len(results)} 个视频")
    
    # 显示简要统计
    quality_stats = {"优秀": 0, "良好": 0, "一般": 0, "较差": 0}
    for video_id, data in results.items():
        technical = data['analysis'].get('local_analysis', {}).get('technical', {})
        if technical:
            quality_level = technical.get('quality_level', '未知')
            if quality_level in quality_stats:
                quality_stats[quality_level] += 1
    
    print("\n=== 质量统计 ===")
    for level, count in quality_stats.items():
        if count > 0:
            print(f"{level}: {count} 个视频")
    
    # 显示建议摘要
    print("\n=== 主要建议 ===")
    all_recommendations = []
    for video_id, data in results.items():
        recommendations = data['analysis'].get('recommendations', [])
        for rec in recommendations:
            if rec.get('priority') == 'high':
                all_recommendations.append(f"{data['filename']}: {rec.get('message')}")
    
    if all_recommendations:
        for rec in all_recommendations[:5]:  # 显示前5个高优先级建议
            print(f"- {rec}")
    else:
        print("无高优先级建议")
    
    print(f"\n详细报告已保存到 {toolkit.results_dir} 目录")

if __name__ == "__main__":
    main()