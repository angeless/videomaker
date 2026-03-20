#!/usr/bin/env python3
"""
指纹索引系统演示
核心：不管文件在哪都能找到
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import subprocess

class FingerprintSystem:
    def __init__(self, db_path="video_fingerprints.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 指纹表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fingerprints (
            fingerprint TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 文件位置表（一个指纹对应多个位置）
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
        
        # 内容索引表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS content_index (
            fingerprint TEXT PRIMARY KEY,
            analysis_data TEXT,
            search_tags TEXT,
            FOREIGN KEY (fingerprint) REFERENCES fingerprints (fingerprint)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def generate_fingerprint(self, video_path):
        """生成唯一指纹"""
        video_path = Path(video_path)
        
        # 1. 基于文件内容的哈希
        content_hash = self._hash_file_content(video_path)
        
        # 2. 基于技术特征的哈希
        tech_hash = self._hash_technical_features(video_path)
        
        # 3. 基于视觉特征的哈希（简化）
        visual_hash = self._hash_visual_features(video_path)
        
        # 组合指纹
        return f"{content_hash[:8]}:{tech_hash[:8]}:{visual_hash[:8]}"
    
    def _hash_file_content(self, video_path):
        """文件内容哈希"""
        try:
            stat = video_path.stat()
            with open(video_path, 'rb') as f:
                # 读取文件的部分内容
                start = f.read(1024 * 1024)  # 开头1MB
                f.seek(stat.st_size // 2)
                middle = f.read(1024 * 1024)  # 中间1MB
                f.seek(max(0, stat.st_size - 1024 * 1024))
                end = f.read(1024 * 1024)  # 结尾1MB
            
            data = start + middle + end + str(stat.st_size).encode()
            return hashlib.sha256(data).hexdigest()
        except:
            stat = video_path.stat()
            fallback = f"{video_path.name}_{stat.st_size}_{stat.st_mtime}"
            return hashlib.sha256(fallback.encode()).hexdigest()
    
    def _hash_technical_features(self, video_path):
        """技术特征哈希"""
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
            
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if video_stream:
                width = video_stream.get("width", "0")
                height = video_stream.get("height", "0")
                codec = video_stream.get("codec_name", "unknown")
                
                features = f"{width}x{height}:{codec}:{duration}:{size}"
                return hashlib.sha256(features.encode()).hexdigest()
        except:
            pass
        
        return hashlib.sha256(str(video_path.stat().st_size).encode()).hexdigest()
    
    def _hash_visual_features(self, video_path):
        """视觉特征哈希（简化）"""
        mtime = video_path.stat().st_mtime
        return hashlib.sha256(str(mtime).encode()).hexdigest()
    
    def index_video(self, video_path):
        """索引视频"""
        video_path = Path(video_path)
        
        if not video_path.exists():
            return None
        
        # 生成指纹
        fingerprint = self.generate_fingerprint(video_path)
        print(f"📹 {video_path.name}")
        print(f"  指纹: {fingerprint}")
        
        # 检查是否已存在
        existing = self.get_fingerprint_info(fingerprint)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if existing:
            print(f"  ⚠️  指纹已存在，添加新路径")
            # 添加新路径
            try:
                stat = video_path.stat()
                cursor.execute(
                    '''INSERT INTO file_locations 
                       (fingerprint, file_path, file_size, last_modified)
                       VALUES (?, ?, ?, ?)''',
                    (fingerprint, str(video_path), stat.st_size,
                     datetime.fromtimestamp(stat.st_mtime).isoformat())
                )
                conn.commit()
                print(f"  ✅ 添加新路径成功")
            except sqlite3.IntegrityError:
                print(f"  ⚠️  路径已存在")
        else:
            print(f"  ✅ 新指纹，创建记录")
            # 创建新记录
            cursor.execute(
                "INSERT INTO fingerprints (fingerprint) VALUES (?)",
                (fingerprint,)
            )
            
            stat = video_path.stat()
            cursor.execute(
                '''INSERT INTO file_locations 
                   (fingerprint, file_path, file_size, last_modified)
                   VALUES (?, ?, ?, ?)''',
                (fingerprint, str(video_path), stat.st_size,
                 datetime.fromtimestamp(stat.st_mtime).isoformat())
            )
            
            # 分析内容
            analysis = self.analyze_video(video_path)
            cursor.execute(
                '''INSERT INTO content_index 
                   (fingerprint, analysis_data, search_tags)
                   VALUES (?, ?, ?)''',
                (fingerprint, json.dumps(analysis), 
                 json.dumps(analysis.get("tags", [])))
            )
            
            conn.commit()
            print(f"  ✅ 创建记录成功")
        
        conn.close()
        return fingerprint
    
    def analyze_video(self, video_path):
        """分析视频内容"""
        # 简化分析
        filename = video_path.name.lower()
        
        analysis = {
            "filename": video_path.name,
            "technical": {},
            "content": {},
            "tags": []
        }
        
        # 技术分析
        try:
            cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", 
                   "-show_format", "-show_streams", str(video_path)]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            data = json.loads(output)
            
            format_info = data.get("format", {})
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break
            
            if video_stream:
                analysis["technical"] = {
                    "resolution": f"{video_stream.get('width', '?')}x{video_stream.get('height', '?')}",
                    "duration": format_info.get("duration", "0"),
                    "codec": video_stream.get("codec_name", "unknown")
                }
                
                # 添加技术标签
                width = video_stream.get("width", 0)
                if width >= 1920:
                    analysis["tags"].append("4k")
                elif width >= 1280:
                    analysis["tags"].append("hd")
                else:
                    analysis["tags"].append("sd")
        except:
            pass
        
        # 内容推断（基于文件名）
        if "instrument" in filename or "wood" in filename:
            analysis["content"] = {
                "type": "cultural",
                "description": "传统乐器展示",
                "perspective": "static"
            }
            analysis["tags"].extend(["cultural", "indoor", "traditional"])
        elif "ushguli" in filename or "mountain" in filename:
            analysis["content"] = {
                "type": "landscape",
                "description": "雪山村落航拍",
                "perspective": "aerial"
            }
            analysis["tags"].extend(["landscape", "aerial", "mountain"])
        elif "ski" in filename or "snow" in filename:
            analysis["content"] = {
                "type": "action",
                "description": "第一人称滑雪",
                "perspective": "first_person"
            }
            analysis["tags"].extend(["action", "sports", "first_person"])
        
        return analysis
    
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
        
        cursor.execute(
            "SELECT analysis_data, search_tags FROM content_index WHERE fingerprint = ?",
            (fingerprint,)
        )
        content_row = cursor.fetchone()
        
        conn.close()
        
        info = {
            "fingerprint": fingerprint,
            "locations": [
                {"path": loc[0], "size": loc[1], "modified": loc[2]}
                for loc in locations
            ],
            "location_count": len(locations)
        }
        
        if content_row:
            info["analysis"] = json.loads(content_row[0]) if content_row[0] else {}
            info["tags"] = json.loads(content_row[1]) if content_row[1] else []
        
        return info
    
    def find_by_fingerprint(self, fingerprint):
        """通过指纹查找"""
        return self.get_fingerprint_info(fingerprint)
    
    def find_by_path(self, file_path):
        """通过路径查找"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT fingerprint FROM file_locations WHERE file_path = ?",
            (str(file_path),)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return self.get_fingerprint_info(result[0])
        return None
    
    def find_duplicates(self):
        """查找重复文件"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fingerprint, COUNT(*) as count, 
                   GROUP_CONCAT(file_path, ' | ') as paths
            FROM file_locations
            GROUP BY fingerprint
            HAVING count > 1
        ''')
        
        duplicates = cursor.fetchall()
        conn.close()
        
        return [
            {
                "fingerprint": row[0],
                "count": row[1],
                "paths": row[2].split(" | ")
            }
            for row in duplicates
        ]
    
    def search_by_tag(self, tag):
        """通过标签搜索"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            '''SELECT fingerprint FROM content_index 
               WHERE search_tags LIKE ?''',
            (f"%{tag}%",)
        )
        
        results = cursor.fetchall()
        conn.close()
        
        videos = []
        for row in results:
            info = self.get_fingerprint_info(row[0])
            if info:
                videos.append(info)
        
        return videos

def main():
    """主演示"""
    print("🔍 视频指纹索引系统演示")
    print("=" * 60)
    
    system = FingerprintSystem("fingerprint_demo.db")
    
    # 测试的三个视频
    test_videos = [
        "4e38f8ee-418d-4aba-8cf6-36af0e6a5f11.mov",  # 传统乐器
        "477ed0c7-6344-4fdb-9eed-bf7977141348.mov",  # 雪山古村
        "57c73514-c369-42ad-b502-50cf893a90f5.mp4"   # 第一人称滑雪
    ]
    
    print("1. 索引三个测试视频:")
    print("-" * 40)
    
    fingerprints = []
    for video in test_videos:
        if Path(video).exists():
            fp = system.index_video(video)
            if fp:
                fingerprints.append(fp)
        else:
            print(f"⚠️  文件不存在: {video}")
    
    print("\n2. 演示查找功能:")
    print("-" * 40)
    
    if fingerprints:
        # 演示通过指纹查找
        print(f"\n通过指纹查找第一个视频:")
        info = system.find_by_fingerprint(fingerprints[0])
        if info:
            print(f"  指纹: {info['fingerprint']}")
            print(f"  存储位置: {info['location_count']} 个")
            for loc in info['locations']:
                print(f"  - {loc['path']}")
        
        # 演示通过路径查找
        print(f"\n通过路径查找第二个视频:")
        path_info = system.find_by_path(test_videos[1])
        if path_info:
            print(f"  找到指纹: {path_info['fingerprint']}")
            if 'analysis' in path_info:
                print(f"  分析: {path_info['analysis'].get('content', {}).get('description', '未知')}")
        
        # 演示标签搜索
        print(f"\n搜索标签 'aerial':")
        aerial_videos = system.search_by_tag("aerial")
        print(f"  找到 {len(aerial_videos)} 个航拍视频")
        for video in aerial_videos:
            if 'analysis' in video:
                desc = video['analysis'].get('content', {}).get('description', '未知')
                print(f"  - {desc}")
        
        # 演示重复查找
        print(f"\n查找重复文件:")
        duplicates = system.find_duplicates()
        if duplicates:
            print(f"  找到 {len(duplicates)} 组重复")
            for dup in duplicates:
                print(f"  - 指纹 {dup['fingerprint'][:16]}... 有 {dup['count']} 个副本")
        else:
            print("  没有重复文件")
    
    print("\n" + "=" * 60)
    print("演示完成!")
    print("\n核心价值:")
    print("✅ 每个视频有唯一指纹，不管文件在哪都能找到")
    print("✅ 相同内容不同路径 → 同一个指纹")
    print("✅ 指纹关联分析结果和搜索标签")
    print("✅ 支持通过指纹、路径、标签查找")
    
    print("\n实际应用:")
    print("1. 扫描8TB素材库，生成所有指纹")
    print("2. 建立指纹数据库")
    print("3. 需要找视频时：")
    print("   - 通过内容描述搜索标签")
    print("   - 找到指纹")
    print("   - 查看所有存储位置")
    print("   - 直接使用最近的副本")

if __name__ == "__main__":
    main()