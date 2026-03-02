#!/usr/bin/env python3
"""
改进的指纹系统
使用更稳定的哈希算法，确保相同内容 → 相同指纹
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import subprocess

class ImprovedFingerprintSystem:
    def __init__(self, db_path="improved_fingerprints.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fingerprints (
            fingerprint TEXT PRIMARY KEY,
            content_hash TEXT,
            tech_hash TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_locations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT,
            file_path TEXT UNIQUE,
            file_size INTEGER,
            last_modified TIMESTAMP,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (fingerprint) REFERENCES fingerprints (fingerprint)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def generate_fingerprint(self, video_path):
        """生成改进的指纹"""
        video_path = Path(video_path)
        
        # 1. 基于文件内容的稳定哈希（忽略时间戳）
        content_hash = self._stable_content_hash(video_path)
        
        # 2. 基于技术特征的哈希
        tech_hash = self._stable_tech_hash(video_path)
        
        # 3. 组合指纹（只使用内容和技术的哈希）
        fingerprint = f"{content_hash[:12]}:{tech_hash[:12]}"
        return fingerprint, content_hash, tech_hash
    
    def _stable_content_hash(self, video_path):
        """稳定的内容哈希（忽略时间戳）"""
        try:
            stat = video_path.stat()
            
            # 读取文件固定部分（忽略时间相关部分）
            with open(video_path, 'rb') as f:
                # 读取文件开头（包含文件头信息）
                header = f.read(4096)  # 4KB头信息
                
                # 读取文件中间部分（跳过可能的时间戳区域）
                f.seek(stat.st_size // 3)
                middle1 = f.read(4096)
                
                f.seek(stat.st_size * 2 // 3)
                middle2 = f.read(4096)
                
                # 读取文件结尾（跳过可能的时间戳）
                f.seek(max(0, stat.st_size - 4096))
                footer = f.read(4096)
            
            # 组合：文件大小 + 固定位置的内容
            hash_input = (
                str(stat.st_size).encode() +  # 文件大小
                header +                      # 文件头
                middle1 +                     # 中间部分1
                middle2 +                     # 中间部分2
                footer                        # 文件尾
            )
            
            return hashlib.sha256(hash_input).hexdigest()
        except Exception as e:
            # 回退：使用文件名和大小（稳定）
            stat = video_path.stat()
            fallback = f"{video_path.name}_{stat.st_size}"
            return hashlib.sha256(fallback.encode()).hexdigest()
    
    def _stable_tech_hash(self, video_path):
        """稳定的技术特征哈希"""
        try:
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            data = json.loads(output)
            
            format_info = data.get("format", {})
            duration = format_info.get("duration", "0")
            size = format_info.get("size", "0")
            
            # 视频流特征
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if video_stream:
                width = video_stream.get("width", "0")
                height = video_stream.get("height", "0")
                codec = video_stream.get("codec_name", "unknown")
                
                # 稳定的技术特征（忽略可能变化的时间戳）
                features = f"{width}x{height}:{codec}:{duration}:{size}"
                return hashlib.sha256(features.encode()).hexdigest()
        except Exception:
            pass
        
        # 回退：使用文件大小（稳定）
        return hashlib.sha256(str(video_path.stat().st_size).encode()).hexdigest()
    
    def index_video(self, video_path):
        """索引视频"""
        video_path = Path(video_path)
        
        if not video_path.exists():
            return None
        
        # 生成指纹
        fingerprint, content_hash, tech_hash = self.generate_fingerprint(video_path)
        print(f"📹 {video_path.name}")
        print(f"  指纹: {fingerprint}")
        print(f"  内容哈希: {content_hash[:8]}...")
        print(f"  技术哈希: {tech_hash[:8]}...")
        
        # 检查是否已存在（基于内容哈希）
        existing = self.find_by_content_hash(content_hash)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if existing:
            print(f"  ⚠️  相同内容已存在，指纹: {existing['fingerprint']}")
            print(f"  添加新路径到现有指纹")
            
            # 添加新路径
            try:
                stat = video_path.stat()
                cursor.execute(
                    '''INSERT INTO file_locations 
                       (fingerprint, file_path, file_size, last_modified)
                       VALUES (?, ?, ?, ?)''',
                    (existing['fingerprint'], str(video_path), stat.st_size,
                     datetime.fromtimestamp(stat.st_mtime).isoformat())
                )
                conn.commit()
                print(f"  ✅ 添加新路径成功")
                return existing['fingerprint']
            except sqlite3.IntegrityError:
                print(f"  ⚠️  路径已存在")
                return existing['fingerprint']
        else:
            print(f"  ✅ 新内容，创建指纹记录")
            
            # 创建新记录
            cursor.execute(
                '''INSERT INTO fingerprints (fingerprint, content_hash, tech_hash)
                   VALUES (?, ?, ?)''',
                (fingerprint, content_hash, tech_hash)
            )
            
            stat = video_path.stat()
            cursor.execute(
                '''INSERT INTO file_locations 
                   (fingerprint, file_path, file_size, last_modified)
                   VALUES (?, ?, ?, ?)''',
                (fingerprint, str(video_path), stat.st_size,
                 datetime.fromtimestamp(stat.st_mtime).isoformat())
            )
            
            conn.commit()
            print(f"  ✅ 创建记录成功")
            return fingerprint
        
        conn.close()
    
    def find_by_content_hash(self, content_hash):
        """通过内容哈希查找"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT fingerprint FROM fingerprints WHERE content_hash = ?",
            (content_hash,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return self.get_fingerprint_info(result[0])
        return None
    
    def get_fingerprint_info(self, fingerprint):
        """获取指纹信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM fingerprints WHERE fingerprint = ?",
            (fingerprint,)
        )
        fp_row = cursor.fetchone()
        
        if not fp_row:
            conn.close()
            return None
        
        cursor.execute(
            "SELECT file_path, file_size, last_modified FROM file_locations WHERE fingerprint = ?",
            (fingerprint,)
        )
        locations = cursor.fetchall()
        
        conn.close()
        
        return {
            "fingerprint": fingerprint,
            "content_hash": fp_row[1],
            "tech_hash": fp_row[2],
            "locations": [
                {"path": loc[0], "size": loc[1], "modified": loc[2]}
                for loc in locations
            ],
            "location_count": len(locations)
        }
    
    def find_by_path(self, file_path):
        """通过路径查找"""
        file_path = Path(file_path)
        
        # 尝试绝对路径
        abs_path = str(file_path.absolute())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 先尝试绝对路径
        cursor.execute(
            "SELECT fingerprint FROM file_locations WHERE file_path = ?",
            (abs_path,)
        )
        result = cursor.fetchone()
        
        # 如果没找到，尝试相对路径（查找包含文件名的记录）
        if not result:
            cursor.execute(
                "SELECT fingerprint FROM file_locations WHERE file_path LIKE ?",
                (f"%{file_path.name}",)
            )
            result = cursor.fetchone()
        
        conn.close()
        
        if result:
            return self.get_fingerprint_info(result[0])
        return None
    
    def find_duplicates(self):
        """查找重复文件（基于内容哈希）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT f.content_hash, f.fingerprint, COUNT(*) as count,
                   GROUP_CONCAT(fl.file_path, ' | ') as paths
            FROM fingerprints f
            JOIN file_locations fl ON f.fingerprint = fl.fingerprint
            GROUP BY f.content_hash
            HAVING count > 1
        ''')
        
        duplicates = cursor.fetchall()
        conn.close()
        
        return [
            {
                "content_hash": row[0],
                "fingerprint": row[1],
                "count": row[2],
                "paths": row[3].split(" | ")
            }
            for row in duplicates
        ]

def test_improved_system():
    """测试改进的系统"""
    print("🔧 测试改进的指纹系统")
    print("=" * 60)
    
    # 清理旧数据库
    test_db = "improved_test.db"
    if Path(test_db).exists():
        Path(test_db).unlink()
    
    system = ImprovedFingerprintSystem(test_db)
    
    # 测试文件
    test_files = [
        "57c73514-c369-42ad-b502-50cf893a90f5.mp4",  # 滑雪原始
        "ski_copy.mp4",                              # 滑雪复制
        "4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov",  # 乐器原始
        "instrument_copy.mov"                        # 乐器复制
    ]
    
    print("1. 索引测试文件:")
    print("-" * 40)
    
    fingerprints = {}
    for file in test_files:
        if Path(file).exists():
            print(f"\n处理: {file}")
            fp = system.index_video(file)
            if fp:
                fingerprints[file] = fp
    
    print("\n2. 验证改进效果:")
    print("-" * 40)
    
    # 检查滑雪视频
    print("\n滑雪视频对比:")
    ski_original = fingerprints.get("57c73514-c369-42ad-b502-50cf893a90f5.mp4")
    ski_copy = fingerprints.get("ski_copy.mp4")
    
    if ski_original and ski_copy:
        if ski_original == ski_copy:
            print(f"   ✅ 相同指纹: {ski_original}")
            
            # 验证关联的路径
            info = system.get_fingerprint_info(ski_original)
            if info and info['location_count'] >= 2:
                print(f"   ✅ 指纹关联 {info['location_count']} 个路径")
                for loc in info['locations']:
                    print(f"      - {Path(loc['path']).name}")
            else:
                print(f"   ❌ 指纹未关联多个路径")
        else:
            print(f"   ❌ 不同指纹!")
            print(f"      原始: {ski_original}")
            print(f"      复制: {ski_copy}")
    
    # 检查乐器视频
    print("\n乐器视频对比:")
    inst_original = fingerprints.get("4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov")
    inst_copy = fingerprints.get("instrument_copy.mov")
    
    if inst_original and inst_copy:
        if inst_original == inst_copy:
            print(f"   ✅ 相同指纹: {inst_original}")
            
            info = system.get_fingerprint_info(inst_original)
            if info and info['location_count'] >= 2:
                print(f"   ✅ 指纹关联 {info['location_count']} 个路径")
            else:
                print(f"   ❌ 指纹未关联多个路径")
        else:
            print(f"   ❌ 不同指纹!")
            print(f"      原始: {inst_original}")
            print(f"      复制: {inst_copy}")
    
    print("\n3. 测试重复检测:")
    print("-" * 40)
    
    duplicates = system.find_duplicates()
    if duplicates:
        print(f"\n找到 {len(duplicates)} 组重复文件:")
        for dup in duplicates:
            print(f"\n   内容哈希: {dup['content_hash'][:8]}...")
            print(f"   指纹: {dup['fingerprint']}")
            print(f"   重复数: {dup['count']}")
            for path in dup['paths'][:3]:
                print(f"      - {Path(path).name}")
    else:
        print(f"\n   没有找到重复文件")
    
    print("\n4. 实际应用演示:")
    print("-" * 40)
    
    if ski_original:
        info = system.get_fingerprint_info(ski_original)
        if info and info['location_count'] >= 2:
            print(f"\n实际场景: 滑雪视频有 {info['location_count']} 个副本")
            print("搜索时:")
            print("  1. 你搜索'第一人称滑雪'")
            print(f"  2. 系统找到指纹: {info['fingerprint'][:16]}...")
            print(f"  3. 系统显示所有 {info['location_count']} 个存储位置")
            print("  4. 你可以选择最近的副本使用")
            print("\n✅ 实现了'不管文件在哪都能找到'")
    
    print("\n" + "=" * 60)
    print("改进总结:")
    
    # 评估
    success = 0
    if ski_original and ski_copy and ski_original == ski_copy:
        print("✅ 改进1: 相同内容 → 相同指纹（稳定哈希）")
        success += 1
    else:
        print("❌ 改进1失败")
    
    if ski_original:
        info = system.get_fingerprint_info(ski_original)
        if info and info['location_count'] >= 2:
            print("✅ 改进2: 指纹关联多个存储位置")
            success += 1
        else:
            print("❌ 改进2失败")
    
    if duplicates:
        print("✅ 改进3: 可以检测重复文件")
        success += 1
    else:
        print("⚠️  改进3: 重复检测需要更多测试")
    
    print(f"\n改进成功率: {success}/3")
    
    if success >= 2:
        print("\n🎉 改进的指纹系统基本可用!")
        print("可以开始扫描8TB素材库了")
    else:
        print("\n⚠️  需要进一步优化指纹算法")

if __name__ == "__main__":
    test_improved_system()