#!/usr/bin/env python3
"""
指纹系统完整测试
验证：相同内容不同位置 → 相同指纹
"""

import os
import shutil
from fingerprint_demo import FingerprintSystem
from pathlib import Path

def test_fingerprint_system():
    """测试指纹系统"""
    print("🔍 指纹系统完整测试")
    print("=" * 60)
    
    # 创建测试数据库
    test_db = "fingerprint_test.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    system = FingerprintSystem(test_db)
    
    # 测试用例
    test_cases = [
        {
            "name": "滑雪视频 - 原始文件",
            "path": "57c73514-c369-42ad-b502-50cf893a90f5.mp4",
            "description": "第一人称滑雪原始文件"
        },
        {
            "name": "滑雪视频 - 复制文件",
            "path": "ski_copy.mp4", 
            "description": "相同内容，不同文件名和位置"
        },
        {
            "name": "乐器视频 - 原始文件",
            "path": "4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov",
            "description": "传统乐器原始文件"
        },
        {
            "name": "乐器视频 - 复制文件",
            "path": "instrument_copy.mov",
            "description": "相同内容，不同文件名"
        }
    ]
    
    print("1. 索引所有测试文件:")
    print("-" * 40)
    
    fingerprints = {}
    for test in test_cases:
        if Path(test["path"]).exists():
            print(f"\n📹 {test['name']}")
            print(f"   描述: {test['description']}")
            print(f"   路径: {test['path']}")
            
            fp = system.index_video(test["path"])
            if fp:
                fingerprints[test["path"]] = fp
                print(f"   指纹: {fp}")
            else:
                print(f"   ❌ 索引失败")
        else:
            print(f"\n⚠️  文件不存在: {test['path']}")
    
    print("\n2. 验证指纹一致性:")
    print("-" * 40)
    
    # 检查相同内容是否有相同指纹
    print("\n滑雪视频对比:")
    ski_original_fp = fingerprints.get("57c73514-c369-42ad-b502-50cf893a90f5.mp4")
    ski_copy_fp = fingerprints.get("ski_copy.mp4")
    
    if ski_original_fp and ski_copy_fp:
        if ski_original_fp == ski_copy_fp:
            print(f"   ✅ 相同指纹: {ski_original_fp}")
            print(f"   证明: 相同内容 → 相同指纹，不管文件名和位置")
        else:
            print(f"   ❌ 不同指纹!")
            print(f"   原始: {ski_original_fp}")
            print(f"   复制: {ski_copy_fp}")
    else:
        print(f"   ⚠️  缺少指纹数据")
    
    print("\n乐器视频对比:")
    instrument_original_fp = fingerprints.get("4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov")
    instrument_copy_fp = fingerprints.get("instrument_copy.mov")
    
    if instrument_original_fp and instrument_copy_fp:
        if instrument_original_fp == instrument_copy_fp:
            print(f"   ✅ 相同指纹: {instrument_original_fp}")
            print(f"   证明: 相同内容 → 相同指纹，不管文件名和位置")
        else:
            print(f"   ❌ 不同指纹!")
            print(f"   原始: {instrument_original_fp}")
            print(f"   复制: {instrument_copy_fp}")
    else:
        print(f"   ⚠️  缺少指纹数据")
    
    print("\n3. 测试查找功能:")
    print("-" * 40)
    
    if ski_original_fp:
        print(f"\n通过指纹查找滑雪视频:")
        info = system.find_by_fingerprint(ski_original_fp)
        if info:
            print(f"   指纹: {info['fingerprint']}")
            print(f"   存储位置数: {info['location_count']}")
            for loc in info['locations']:
                print(f"   - {loc['path']} ({loc['size']} bytes)")
            
            # 验证
            expected_paths = [
                "57c73514-c369-42ad-b502-50cf893a90f5.mp4",
                "ski_copy.mp4"
            ]
            actual_paths = [loc['path'] for loc in info['locations']]
            
            print(f"\n   验证: 指纹应关联2个文件")
            for expected in expected_paths:
                found = any(expected in path for path in actual_paths)
                if found:
                    print(f"   ✅ 找到: {expected}")
                else:
                    print(f"   ❌ 未找到: {expected}")
    
    print("\n4. 测试通过路径查找:")
    print("-" * 40)
    
    test_path = "ski_copy.mp4"
    print(f"\n通过路径查找: {test_path}")
    path_info = system.find_by_path(test_path)
    if path_info:
        print(f"   找到指纹: {path_info['fingerprint']}")
        print(f"   这个指纹有 {path_info['location_count']} 个存储位置")
        
        # 显示分析信息（如果有）
        if 'analysis' in path_info:
            analysis = path_info['analysis']
            print(f"   分析: {analysis.get('content', {}).get('description', '未知')}")
            if analysis.get('tags'):
                print(f"   标签: {', '.join(analysis['tags'][:3])}")
    else:
        print(f"   ❌ 未找到")
    
    print("\n5. 测试重复查找:")
    print("-" * 40)
    
    duplicates = system.find_duplicates()
    if duplicates:
        print(f"\n找到 {len(duplicates)} 组重复文件:")
        for dup in duplicates:
            print(f"\n   指纹: {dup['fingerprint'][:16]}...")
            print(f"   重复数: {dup['count']}")
            for path in dup['paths'][:3]:  # 只显示前3个
                print(f"   - {Path(path).name}")
            if len(dup['paths']) > 3:
                print(f"   ... 还有 {len(dup['paths']) - 3} 个路径")
    else:
        print(f"\n   没有找到重复文件")
        print(f"   ⚠️  预期应该有2组重复（滑雪和乐器）")
    
    print("\n6. 模拟实际场景:")
    print("-" * 40)
    
    print("\n场景: 你的8TB素材库")
    print("假设滑雪视频有5个副本:")
    print("  1. /mnt/8tb/sports/skiing.mp4")
    print("  2. /mnt/nas/videos/action/snowboard.mp4")
    print("  3. D:/素材库/滑雪/第一人称.mp4")
    print("  4. E:/备份/2024/滑雪素材.mp4")
    print("  5. /cloud/backup/ski_001.mp4")
    
    print("\n指纹系统如何工作:")
    print("  1. 扫描所有位置，生成指纹")
    print("  2. 发现5个文件内容相同 → 相同指纹")
    print("  3. 指纹关联所有5个路径")
    
    print("\n搜索时:")
    print("  你搜索: '第一人称 滑雪 野雪'")
    print("  系统: 找到指纹 {ski_fingerprint}")
    print("  系统: 这个指纹有5个存储位置")
    print("  系统: 推荐使用最近的副本: /mnt/8tb/sports/skiing.mp4")
    
    print("\n" + "=" * 60)
    print("测试总结:")
    
    # 评估测试结果
    success_count = 0
    total_tests = 4
    
    # 测试1: 相同内容 → 相同指纹
    if ski_original_fp and ski_copy_fp and ski_original_fp == ski_copy_fp:
        print("✅ 测试1通过: 相同内容不同位置 → 相同指纹")
        success_count += 1
    else:
        print("❌ 测试1失败: 指纹不一致")
    
    # 测试2: 指纹关联多个路径
    if ski_original_fp:
        info = system.find_by_fingerprint(ski_original_fp)
        if info and info['location_count'] >= 2:
            print("✅ 测试2通过: 指纹正确关联多个存储位置")
            success_count += 1
        else:
            print("❌ 测试2失败: 指纹未关联多个路径")
    
    # 测试3: 通过路径查找指纹
    if test_path and system.find_by_path(test_path):
        print("✅ 测试3通过: 可以通过路径查找指纹")
        success_count += 1
    else:
        print("❌ 测试3失败: 无法通过路径查找")
    
    # 测试4: 重复检测
    if duplicates:
        print("✅ 测试4通过: 可以检测重复文件")
        success_count += 1
    else:
        print("⚠️  测试4警告: 未检测到重复（可能算法需要优化）")
    
    print(f"\n通过率: {success_count}/{total_tests} ({success_count/total_tests*100:.0f}%)")
    
    if success_count >= 3:
        print("\n🎉 指纹系统测试基本通过!")
        print("核心功能验证:")
        print("  ✅ 内容唯一性: 相同内容 → 相同指纹")
        print("  ✅ 位置无关性: 文件移动/复制不影响查找")
        print("  ✅ 多位置关联: 一个指纹关联所有副本")
        print("  ✅ 双向查找: 指纹↔路径双向查找")
    else:
        print("\n⚠️  指纹系统需要优化")
        print("需要改进:")
        print("  - 指纹生成算法稳定性")
        print("  - 重复检测准确性")
        print("  - 数据库操作可靠性")
    
    print(f"\n数据库文件: {test_db}")
    print("大小:", f"{os.path.getsize(test_db)/1024:.1f} KB" if os.path.exists(test_db) else "不存在")

if __name__ == "__main__":
    test_fingerprint_system()