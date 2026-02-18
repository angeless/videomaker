#!/usr/bin/env python3
"""
视频指纹索引系统
核心：生成唯一指纹，实现"不管文件在哪都能找到"
"""

import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime
import subprocess
import os

class VideoFingerprintSystem:
    def __init__(self, db_path="video_fingerprints.db"):
        """初始化指纹数据库"""
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """初始化数据库表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 主指纹表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fingerprints (
            fingerprint TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 文件路径表（一个指纹可能对应多个路径）
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
        
        # 内容索引表（基于分析结果）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS content_index (
            fingerprint TEXT PRIMARY KEY,
            technical_data TEXT,
            content_data TEXT,
            emotional_data TEXT,
            business_data TEXT,
            search_tags TEXT,
            FOREIGN KEY (fingerprint) REFERENCES fingerprints (fingerprint)
        )
        ''')
        
        # 搜索索引表（倒排索引）
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS search_index (
            tag TEXT,
            fingerprint TEXT,
            weight REAL,
            PRIMARY KEY (tag, fingerprint)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def generate_fingerprint(self, video_path):
        """生成视频的唯一指纹"""
        video_path = Path(video_path)
        
        # 方法1：基于文件内容的哈希（如果文件相同）
        content_hash = self._hash_file_content(video_path)
        
        # 方法2：基于技术特征的哈希
        tech_hash = self._hash_technical_features(video_path)
        
        # 方法3：基于视觉特征的哈希（简化版）
        visual_hash = self._hash_visual_features(video_path)
        
        # 组合指纹
        fingerprint = f"{content_hash[:8]}:{tech_hash[:8]}:{visual_hash[:8]}"
        return fingerprint
    
    def _hash_file_content(self, video_path):
        """基于文件内容生成哈希"""
        try:
            # 使用文件大小和部分内容生成哈希
            stat_info = video_path.stat()
            
            # 读取文件开头、中间、结尾的部分数据
            with open(video_path, 'rb') as f:
                # 开头1MB
                start_data = f.read(1024 * 1024)
                
                # 跳到中间
                f.seek(stat_info.st_size // 2)
                middle_data = f.read(1024 * 1024)
                
                # 跳到结尾前1MB
                f.seek(max(0, stat_info.st_size - 1024 * 1024))
                end_data = f.read(1024 * 1024)
            
            # 组合生成哈希
            hash_input = start_data + middle_data + end_data + str(stat_info.st_size).encode()
            return hashlib.sha256(hash_input).hexdigest()
        except Exception as e:
            # 回退方案：使用文件名和大小
            fallback = f"{video_path.name}_{stat_info.st_size}_{stat_info.st_mtime}"
            return hashlib.sha256(fallback.encode()).hexdigest()
    
    def _hash_technical_features(self, video_path):
        """基于技术特征生成哈希"""
        try:
            # 提取技术元数据
            cmd = [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(video_path)
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
            data = json.loads(output)
            
            # 提取关键特征
            format_info = data.get("format", {})
            duration = format_info.get("duration", "0")
            size = format_info.get("size", "0")
            bitrate = format_info.get("bit_rate", "0")
            
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
                framerate = video_stream.get("r_frame_rate", "0/1")
                
                # 生成特征字符串
                features = f"{width}x{height}:{codec}:{framerate}:{duration}:{size}:{bitrate}"
                return hashlib.sha256(features.encode()).hexdigest()
        except:
            pass
        
        # 回退方案
        return hashlib.sha256(str(video_path.stat().st_size).encode()).hexdigest()
    
    def _hash_visual_features(self, video_path):
        """基于视觉特征生成哈希（简化版）"""
        # 实际应用中应该使用PHASH或关键帧特征
        # 这里使用文件修改时间作为简化版本
        mtime = video_path.stat().st_mtime
        return hashlib.sha256(str(mtime).encode()).hexdigest()
    
    def index_video(self, video_path, analyze_content=True):
        """索引视频文件"""
        video_path = Path(video_path)
        
        if not video_path.exists():
            print(f"错误: 文件不存在 {video_path}")
            return None
        
        # 1. 生成指纹
        fingerprint = self.generate_fingerprint(video_path)
        print(f"视频: {video_path.name}")
        print(f"指纹: {fingerprint}")
        
        # 2. 检查是否已存在
        existing = self.get_fingerprint_info(fingerprint)
        
        if existing:
            print(f"⚠️  指纹已存在，添加新路径")
            # 添加新路径
            self.add_file_location(fingerprint, video_path)
            return fingerprint
        else:
            print(f"✅ 新指纹，创建记录")
            # 创建新记录
            self.create_fingerprint_record(fingerprint, video_path, analyze_content)
            return fingerprint
    
    def create_fingerprint_record(self, fingerprint, video_path, analyze_content=True):
        """创建指纹记录"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. 添加指纹记录
        cursor.execute(
            "INSERT OR IGNORE INTO fingerprints (fingerprint) VALUES (?)",
            (fingerprint,)
        )
        
        # 2. 添加文件路径
        stat_info = video_path.stat()
        cursor.execute(
            '''INSERT OR REPLACE INTO file_locations 
               (fingerprint, file_path, file_size, last_modified) 
               VALUES (?, ?, ?, ?)''',
            (fingerprint, str(video_path), stat_info.st_size, 
             datetime.fromtimestamp(stat_info.st_mtime).isoformat())
        )
        
        # 3. 分析内容并创建索引（如果需要）
        if analyze_content:
            content_data = self.analyze_video_content(video_path)
            self.update_content_index(fingerprint, content_data)
        
        conn.commit()
        conn.close()
        
        print(f"✅ 指纹记录创建完成")
        return True
    
    def add_file_location(self, fingerprint, video_path):
        """为已有指纹添加新路径"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        stat_info = video_path.stat()
        try:
            cursor.execute(
                '''INSERT INTO file_locations 
                   (fingerprint, file_path, file_size, last_modified) 
                   VALUES (?, ?, ?, ?)''',
                (fingerprint, str(video_path), stat_info.st_size,
                 datetime.fromtimestamp(stat_info.st_mtime).isoformat())
            )
            conn.commit()
            print(f"✅ 添加新路径: {video_path}")
            return True
        except sqlite3.IntegrityError:
            print(f"⚠️  路径已存在: {video_path}")
            return False
        finally:
            conn.close()
    
    def analyze_video_content(self, video_path):
        """分析视频内容（简化版）"""
        # 这里应该调用完整的分析系统
        # 现在返回模拟数据
        from enhanced_analysis import EnhancedVideoAnalyzer
        
        analyzer = EnhancedVideoAnalyzer()
        result = analyzer.analyze_video(video_path)
        
        return {
            "technical": result.get("technical_analysis", {}),
            "content": result.get("content_analysis", {}),
            "emotional": result.get("emotional_analysis", {}),
            "business": result.get("business_analysis", {}),
            "search_tags": result.get("search_index", {}).get("tags", [])
        }
    
    def update_content_index(self, fingerprint, content_data):
        """更新内容索引"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 更新内容索引表
        cursor.execute(
            '''INSERT OR REPLACE INTO content_index 
               (fingerprint, technical_data, content_data, emotional_data, business_data, search_tags)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (fingerprint,
             json.dumps(content_data.get("technical", {})),
             json.dumps(content_data.get("content", {})),
             json.dumps(content_data.get("emotional", {})),
             json.dumps(content_data.get("business", {})),
             json.dumps(content_data.get("search_tags", [])))
        )
        
        # 更新搜索索引（倒排索引）
        tags = content_data.get("search_tags", [])
        for tag in tags:
            # 简单权重计算
            weight = 1.0
            cursor.execute(
                '''INSERT OR REPLACE INTO search_index (tag, fingerprint, weight)
                   VALUES (?, ?, ?)''',
                (tag, fingerprint, weight)
            )
        
        conn.commit()
        conn.close()
        
        print(f"✅ 内容索引更新完成，添加 {len(tags)} 个标签")
    
    def get_fingerprint_info(self, fingerprint):
        """获取指纹信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取指纹基本信息
        cursor.execute(
            "SELECT * FROM fingerprints WHERE fingerprint = ?",
            (fingerprint,)
        )
        fingerprint_row = cursor.fetchone()
        
        if not fingerprint_row:
            conn.close()
            return None
        
        # 获取所有文件路径
        cursor.execute(
            "SELECT file_path, file_size, last_modified FROM file_locations WHERE fingerprint = ?",
            (fingerprint,)
        )
        locations = cursor.fetchall()
        
        # 获取内容索引
        cursor.execute(
            "SELECT * FROM content_index WHERE fingerprint = ?",
            (fingerprint,)
        )
        content_row = cursor.fetchone()
        
        conn.close()
        
        return {
            "fingerprint": fingerprint,
            "locations": [
                {"path": loc[0], "size": loc[1], "modified": loc[2]}
                for loc in locations
            ],
            "location_count": len(locations),
            "content_index": self._parse_content_row(content_row) if content_row else None
        }
    
    def _parse_content_row(self, content_row):
        """解析内容索引行"""
        if not content_row:
            return None
        
        return {
            "technical": json.loads(content_row[1]) if content_row[1] else {},
            "content": json.loads(content_row[2]) if content_row[2] else {},
            "emotional": json.loads(content_row[3]) if content_row[3] else {},
            "business": json.loads(content_row[4]) if content_row[4] else {},
            "search_tags": json.loads(content_row[5]) if content_row[5] else []
        }
    
    def find_video_by_fingerprint(self, fingerprint):
        """通过指纹查找视频"""
        return self.get_fingerprint_info(fingerprint)
    
    def find_video_by_path(self, file_path):
        """通过路径查找视频（获取其指纹）"""
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
    
    def search_by_tag(self, tag):
        """通过标签搜索视频"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            '''SELECT si.fingerprint, si.weight, ci.search_tags
               FROM search_index si
               LEFT JOIN content_index ci ON si.fingerprint = ci.fingerprint
               WHERE si.tag LIKE ? OR ci.search_tags LIKE ?
               ORDER BY si.weight DESC''',
            (f"%{tag}%", f"%{tag}%")
        )
        
        results = cursor.fetchall()
        conn.close()
        
        videos = []
        for fingerprint, weight, tags_json in results:
            info = self.get_fingerprint_info(fingerprint)
            if info:
                info["search_weight"] = weight
                videos.append(info)
        
        return videos
    
    def find_duplicates(self):
        """查找重复文件（相同指纹，不同路径）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT fingerprint, COUNT(*) as location_count, 
                   GROUP_CONCAT(file_path, ' | ') as paths
            FROM file_locations
            GROUP BY fingerprint
            HAVING location_count > 1
            ORDER BY location_count DESC
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
    
    def scan_directory(self, directory_path, recursive=True):
        """扫描目录并索引所有视频"""
        directory = Path(directory_path)
        
        if not directory.exists():
            print(f"错误: 目录不存在 {directory}")
            return []
        
        # 支持的视频格式
        video_extensions = [".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".m4v"]
        
        fingerprints = []
        
        if recursive:
            # 递归扫描
            for ext in video_extensions:
                for video_file in directory.rglob(f"*{ext}"):
                    print(f"扫描: {video_file}")
                    fp = self.index_video(video_file, analyze_content=True)
                    if fp:
                        fingerprints.append(fp)
        else:
            # 只扫描当前目录
            for ext in video_extensions:
                for video_file in directory.glob(f"*{ext}"):
                    print(f"扫描: {video_file}")
                    fp = self.index_video(video_file, analyze_content=True)
                    if fp:
                        fingerprints.append(fp)
        
        print(f"✅ 扫描完成，索引了 {len(fingerprints)} 个视频")
        return fingerprints

def main():
    """主函数演示"""
    import sys
    
    system = VideoFingerprintSystem()
    
    print("🎬 视频指纹索引系统")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        # 命令行模式
        if sys.argv[1] == "scan":
            directory =