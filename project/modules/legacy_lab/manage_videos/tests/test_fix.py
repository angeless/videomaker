#!/usr/bin/env python3
"""
修复测试
"""

import sqlite3
from pathlib import Path

def test_database():
    """测试数据库"""
    db_path = "video_fingerprints.db"
    
    if not Path(db_path).exists():
        print(f"❌ 数据库不存在: {db_path}")
        return
    
    print(f"🔍 测试数据库: {db_path}")
    print(f"大小: {Path(db_path).stat().st_size / 1024:.1f}KB")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    print(f"\n表: {[t[0] for t in tables]}")
    
    # 检查数据
    print("\n📊 数据统计:")
    
    cursor.execute("SELECT COUNT(*) FROM fingerprints")
    fp_count = cursor.fetchone()[0]
    print(f"  指纹数: {fp_count}")
    
    cursor.execute("SELECT COUNT(*) FROM file_locations")
    loc_count = cursor.fetchone()[0]
    print(f"  文件位置数: {loc_count}")
    
    # 检查具体数据
    print("\n🔍 检查具体记录:")
    
    cursor.execute("SELECT fingerprint, content_hash FROM fingerprints LIMIT 3")
    fingerprints = cursor.fetchall()
    
    for fp, content_hash in fingerprints:
        print(f"\n指纹: {fp}")
        print(f"内容哈希: {content_hash[:8]}...")
        
        cursor.execute(
            "SELECT file_path FROM file_locations WHERE fingerprint = ?",
            (fp,)
        )
        locations = cursor.fetchall()
        
        print(f"关联文件: {len(locations)} 个")
        for loc in locations:
            print(f"  - {Path(loc[0]).name}")
    
    # 测试路径查找
    print("\n🔍 测试路径查找:")
    
    test_files = [
        "57c73514-c369-42ad-b502-50cf893a90f5.mp4",
        "ski_copy.mp4",
        "4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov"
    ]
    
    for file in test_files:
        file_path = str(Path(file).absolute())
        print(f"\n查找: {file}")
        print(f"路径: {file_path}")
        
        cursor.execute(
            "SELECT fingerprint FROM file_locations WHERE file_path = ?",
            (file_path,)
        )
        result = cursor.fetchone()
        
        if result:
            print(f"✅ 找到指纹: {result[0]}")
        else:
            # 尝试相对路径
            cursor.execute(
                "SELECT fingerprint FROM file_locations WHERE file_path LIKE ?",
                (f"%{file}",)
            )
            result = cursor.fetchone()
            
            if result:
                print(f"⚠️  通过模糊查找找到: {result[0]}")
            else:
                print(f"❌ 未找到")
    
    conn.close()
    
    print("\n" + "=" * 60)
    print("💡 问题分析:")
    print("路径查找失败可能是因为:")
    print("1. 数据库存储的是绝对路径")
    print("2. 查找时使用的是相对路径")
    print("3. 路径格式不一致")
    print("\n✅ 解决方案:")
    print("使用绝对路径进行查找")

def main():
    test_database()

if __name__ == "__main__":
    main()