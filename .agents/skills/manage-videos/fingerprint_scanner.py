#!/usr/bin/env python3
"""
指纹扫描器 - 开始扫描视频目录
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime
from improved_fingerprint import ImprovedFingerprintSystem

class FingerprintScanner:
    def __init__(self, db_path="video_fingerprints.db"):
        self.system = ImprovedFingerprintSystem(db_path)
        self.scan_stats = {
            "total_files": 0,
            "processed": 0,
            "skipped": 0,
            "errors": 0,
            "new_fingerprints": 0,
            "existing_fingerprints": 0,
            "start_time": None,
            "end_time": None
        }
    
    def scan_directory(self, directory_path, recursive=True, extensions=None):
        """扫描目录中的视频文件"""
        if extensions is None:
            extensions = ['.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.m4v', '.mpg', '.mpeg']
        
        directory = Path(directory_path)
        if not directory.exists():
            print(f"❌ 目录不存在: {directory}")
            return
        
        print(f"🔍 开始扫描目录: {directory}")
        print(f"   扩展名: {', '.join(extensions)}")
        print(f"   递归: {'是' if recursive else '否'}")
        print("=" * 60)
        
        self.scan_stats["start_time"] = datetime.now()
        
        # 收集视频文件
        video_files = []
        if recursive:
            for ext in extensions:
                video_files.extend(directory.rglob(f"*{ext}"))
        else:
            for ext in extensions:
                video_files.extend(directory.glob(f"*{ext}"))
        
        self.scan_stats["total_files"] = len(video_files)
        print(f"📁 找到 {len(video_files)} 个视频文件")
        
        if not video_files:
            print("⚠️  没有找到视频文件")
            return
        
        # 开始处理
        for i, video_file in enumerate(video_files, 1):
            try:
                self._process_video(video_file, i, len(video_files))
            except KeyboardInterrupt:
                print("\n\n⏹️ 扫描被用户中断")
                break
            except Exception as e:
                print(f"\n❌ 处理失败 {video_file.name}: {e}")
                self.scan_stats["errors"] += 1
        
        self.scan_stats["end_time"] = datetime.now()
        self._print_summary()
    
    def _process_video(self, video_file, current, total):
        """处理单个视频文件"""
        file_size = video_file.stat().st_size
        file_size_mb = file_size / 1024 / 1024
        
        print(f"\n[{current}/{total}] 📹 {video_file.name}")
        print(f"   大小: {file_size_mb:.1f}MB, 路径: {video_file.parent}")
        
        # 检查文件大小（跳过太小的文件）
        if file_size < 1024:  # 小于1KB
            print(f"   ⏭️  跳过: 文件太小")
            self.scan_stats["skipped"] += 1
            return
        
        # 生成指纹
        fingerprint = self.system.index_video(str(video_file))
        
        if fingerprint:
            # 检查这个指纹是否是新创建的
            info = self.system.get_fingerprint_info(fingerprint)
            if info and info['location_count'] == 1:
                self.scan_stats["new_fingerprints"] += 1
                print(f"   ✅ 新指纹: {fingerprint[:16]}...")
            else:
                self.scan_stats["existing_fingerprints"] += 1
                print(f"   🔄 已有指纹: {fingerprint[:16]}...")
                if info:
                    print(f"      关联 {info['location_count']} 个文件")
        
        self.scan_stats["processed"] += 1
        
        # 显示进度
        progress = current / total * 100
        print(f"   进度: {progress:.1f}%")
    
    def _print_summary(self):
        """打印扫描总结"""
        print("\n" + "=" * 60)
        print("📊 扫描完成!")
        print("=" * 60)
        
        duration = (self.scan_stats["end_time"] - self.scan_stats["start_time"]).total_seconds()
        
        print(f"📁 总文件数: {self.scan_stats['total_files']}")
        print(f"✅ 已处理: {self.scan_stats['processed']}")
        print(f"⏭️  已跳过: {self.scan_stats['skipped']}")
        print(f"❌ 错误: {self.scan_stats['errors']}")
        print(f"🆕 新指纹: {self.scan_stats['new_fingerprints']}")
        print(f"🔄 已有指纹: {self.scan_stats['existing_fingerprints']}")
        print(f"⏱️  总耗时: {duration:.1f}秒")
        
        if self.scan_stats["processed"] > 0:
            avg_time = duration / self.scan_stats["processed"]
            print(f"📈 平均每个文件: {avg_time:.2f}秒")
            
            # 估算8TB扫描时间
            estimated_8tb_time = avg_time * 1000000 / 3600  # 假设100万文件，转换为小时
            print(f"📅 估算8TB扫描: {estimated_8tb_time:.1f}小时 ({estimated_8tb_time/24:.1f}天)")
        
        # 显示数据库信息
        db_path = self.system.db_path
        if Path(db_path).exists():
            db_size = Path(db_path).stat().st_size / 1024
            print(f"💾 数据库大小: {db_size:.1f}KB")
        
        print("\n🎯 下一步:")
        print("1. 验证指纹准确性")
        print("2. 测试搜索功能")
        print("3. 开始扫描更大目录")
    
    def get_duplicates_report(self):
        """获取重复文件报告"""
        duplicates = self.system.find_duplicates()
        
        if not duplicates:
            print("\n✅ 没有找到重复文件")
            return
        
        print(f"\n🔍 找到 {len(duplicates)} 组重复文件:")
        print("-" * 40)
        
        total_space_saved = 0
        
        for i, dup in enumerate(duplicates, 1):
            print(f"\n{i}. 指纹: {dup['fingerprint'][:16]}...")
            print(f"   重复数: {dup['count']}")
            print(f"   文件:")
            
            total_size = 0
            for path in dup['paths']:
                size = Path(path).stat().st_size
                total_size += size
                size_mb = size / 1024 / 1024
                print(f"      - {Path(path).name} ({size_mb:.1f}MB)")
            
            # 计算可节省空间（保留一个副本）
            space_saved = total_size - (total_size / dup['count'])
            total_space_saved += space_saved
            
            saved_mb = space_saved / 1024 / 1024
            print(f"   可节省空间: {saved_mb:.1f}MB")
        
        total_saved_gb = total_space_saved / 1024 / 1024 / 1024
        print(f"\n💾 总计可节省空间: {total_saved_gb:.2f}GB")

def main():
    """主函数"""
    print("🎬 视频指纹扫描器")
    print("=" * 60)
    
    # 当前目录
    current_dir = Path(__file__).parent
    print(f"当前目录: {current_dir}")
    
    # 创建扫描器
    scanner = FingerprintScanner("video_fingerprints.db")
    
    # 扫描选项
    print("\n📋 扫描选项:")
    print("1. 扫描当前目录 (测试)")
    print("2. 扫描指定目录")
    print("3. 查看重复文件")
    print("4. 退出")
    
    try:
        choice = input("\n请选择 (1-4): ").strip()
        
        if choice == "1":
            # 扫描当前目录
            scanner.scan_directory(current_dir, recursive=False)
            
            # 显示重复报告
            scanner.get_duplicates_report()
            
        elif choice == "2":
            # 扫描指定目录
            target_dir = input("请输入目录路径: ").strip()
            if target_dir:
                scanner.scan_directory(target_dir, recursive=True)
                scanner.get_duplicates_report()
            else:
                print("❌ 目录路径不能为空")
        
        elif choice == "3":
            # 查看重复文件
            scanner.get_duplicates_report()
        
        elif choice == "4":
            print("👋 退出")
            return
        
        else:
            print("❌ 无效选择")
    
    except KeyboardInterrupt:
        print("\n\n👋 用户中断")
    
    print("\n" + "=" * 60)
    print("💡 使用提示:")
    print("  扫描8TB素材库: python3 fingerprint_scanner.py scan /mnt/8tb")
    print("  查看重复文件: python3 fingerprint_scanner.py duplicates")
    print("  搜索视频: python3 search_videos.py '关键词'")

if __name__ == "__main__":
    main()