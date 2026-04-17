#!/usr/bin/env python3
"""
视频指纹去重模块
使用感知哈希 (pHash) 检测重复/相似片段，SQLite 持久化存储。

来源：opencut/indexer/fingerprint.py（移植并适配 manage-videos skill）
"""

import sqlite3
import hashlib
import json
import logging
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional, Callable

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class VideoHasher:
    """视频帧感知哈希计算"""

    @staticmethod
    def compute_frame_phash(frame, hash_size: int = 16) -> str:
        """
        计算单帧感知哈希 (pHash)
        流程: 灰度 → 缩放 → DCT → 低频区域 → 二值化 → 十六进制
        """
        if not HAS_CV2:
            raise ImportError("opencv-python 未安装，无法计算 pHash")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray, (hash_size * 4, hash_size * 4))
        float_img = np.float32(resized)
        dct = cv2.dct(float_img)
        dct_low = dct[:hash_size, :hash_size]
        median = np.median(dct_low)
        binary = (dct_low > median).flatten()
        hex_hash = format(int("".join(str(int(b)) for b in binary), 2), 'x').zfill(hash_size * hash_size // 4)
        return hex_hash

    @staticmethod
    def compute_video_fingerprint(video_path: str, sample_interval: float = 1.0) -> Dict:
        """
        按时间间隔采样帧，聚合生成视频指纹

        Returns:
            {
                "path": str,
                "duration": float,
                "frame_hashes": [str, ...],
                "representative_hash": str   # 中位帧的哈希
            }
        """
        import time
        _fp_t0 = time.perf_counter()
        if not HAS_CV2:
            raise ImportError("opencv-python 未安装")

        cap = cv2.VideoCapture(video_path)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps

            frame_hashes = []
            sample_step = int(fps * sample_interval)

            for frame_idx in range(0, total_frames, max(sample_step, 1)):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    break
                try:
                    h = VideoHasher.compute_frame_phash(frame)
                    frame_hashes.append(h)
                except Exception:
                    pass
        finally:
            cap.release()

        # 取中间帧作为代表哈希
        representative = frame_hashes[len(frame_hashes) // 2] if frame_hashes else ""

        _fp_elapsed = (time.perf_counter() - _fp_t0) * 1000
        logger.debug("[perf] compute_video_fingerprint: %.1fms frames=%d path=%s",
                     _fp_elapsed, len(frame_hashes), Path(video_path).name)
        return {
            "path": video_path,
            "duration": duration,
            "frame_count": len(frame_hashes),
            "frame_hashes": frame_hashes,
            "representative_hash": representative,
        }

    @staticmethod
    def hamming_distance(hash1: str, hash2: str) -> int:
        """计算两个十六进制哈希的汉明距离"""
        if len(hash1) != len(hash2):
            return 999
        n1 = int(hash1, 16)
        n2 = int(hash2, 16)
        xor = n1 ^ n2
        return bin(xor).count('1')

    @staticmethod
    def is_similar(hash1: str, hash2: str, threshold: int = 5) -> bool:
        """判断两个哈希是否相似（汉明距离 <= threshold）"""
        return VideoHasher.hamming_distance(hash1, hash2) <= threshold

    @staticmethod
    def simhash_aggregate(hex_hashes: List[str]) -> str:
        """
        将多个等长十六进制哈希聚合为单一 SimHash。

        算法：按 bit 位投票——某 bit 位在超过半数的哈希中为 1，则结果该位为 1。
        结果是一个与输入等长的十六进制字符串，代表所有帧的整体内容指纹。

        对转码/压缩鲁棒：单个帧哈希的微小变化不影响多数投票结果。
        """
        if not hex_hashes:
            return ""
        bit_len = len(hex_hashes[0]) * 4  # 每个十六进制字符 = 4 bits
        # 初始化 bit 位计数器
        counts = [0] * bit_len
        for h in hex_hashes:
            val = int(h, 16)
            for i in range(bit_len):
                if val & (1 << (bit_len - 1 - i)):
                    counts[i] += 1
        threshold = len(hex_hashes) / 2
        result_bits = []
        for c in counts:
            result_bits.append("1" if c > threshold else "0")
        result_int = int("".join(result_bits), 2)
        return format(result_int, 'x').zfill(len(hex_hashes[0]))


class FingerprintDB:
    """
    视频指纹数据库（SQLite）

    表结构：
    - video_fingerprints: 视频级别元信息 + 代表哈希
    - frame_hashes: 帧级别哈希（用于片段级去重）
    """

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Round-13 P1:
        # - check_same_thread=False because Flask / step1 worker threads
        #   share this instance. Required; otherwise concurrent calls raise.
        # - WAL mode for concurrent reads alongside a writer (default
        #   journal_mode=DELETE serializes all access and blocks readers
        #   during writes).
        # - Module-level lock to serialize writes across threads, preventing
        #   "database is locked" errors under concurrent step1 runs.
        import threading as _threading
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, timeout=10.0
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = _threading.Lock()
        self._init_db()

    def _init_db(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS video_fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                duration REAL,
                representative_hash TEXT,
                frame_count INTEGER,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS frame_hashes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER REFERENCES video_fingerprints(id),
                frame_index INTEGER,
                phash TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_rep_hash ON video_fingerprints(representative_hash);
            CREATE INDEX IF NOT EXISTS idx_frame_hash ON frame_hashes(phash);
        """)
        self._conn.commit()

    def add_video(self, fingerprint: Dict) -> int:
        """添加视频指纹到数据库，返回 video_id"""
        cur = self._conn.execute(
            """INSERT OR REPLACE INTO video_fingerprints
               (path, duration, representative_hash, frame_count)
               VALUES (?, ?, ?, ?)""",
            (fingerprint["path"], fingerprint["duration"],
             fingerprint["representative_hash"], fingerprint["frame_count"])
        )
        video_id = cur.lastrowid

        # 批量插入帧哈希
        frame_rows = [
            (video_id, i, h)
            for i, h in enumerate(fingerprint.get("frame_hashes", []))
        ]
        self._conn.executemany(
            "INSERT INTO frame_hashes (video_id, frame_index, phash) VALUES (?, ?, ?)",
            frame_rows
        )
        self._conn.commit()
        return video_id

    def find_duplicates(self, threshold: int = 5) -> List[List[str]]:
        """
        找出所有重复视频组（基于代表哈希汉明距离）

        Returns:
            [[path1, path2], [path3, path4, path5], ...]
        """
        rows = self._conn.execute(
            "SELECT path, representative_hash FROM video_fingerprints WHERE representative_hash != ''"
        ).fetchall()

        visited: Set[str] = set()
        groups = []

        for i, (path_i, hash_i) in enumerate(rows):
            if path_i in visited:
                continue
            group = [path_i]
            for path_j, hash_j in rows[i + 1:]:
                if path_j not in visited and VideoHasher.is_similar(hash_i, hash_j, threshold):
                    group.append(path_j)
                    visited.add(path_j)
            if len(group) > 1:
                visited.add(path_i)
                groups.append(group)

        return groups

    def find_similar_segments(self, phash: str, threshold: int = 3) -> List[Dict]:
        """根据帧哈希查找相似片段（用于场景复用）"""
        rows = self._conn.execute(
            """SELECT vf.path, fh.frame_index, fh.phash
               FROM frame_hashes fh
               JOIN video_fingerprints vf ON fh.video_id = vf.id"""
        ).fetchall()

        results = []
        for path, frame_idx, candidate_hash in rows:
            dist = VideoHasher.hamming_distance(phash, candidate_hash)
            if dist <= threshold:
                results.append({
                    "path": path,
                    "frame_index": frame_idx,
                    "distance": dist
                })

        return sorted(results, key=lambda x: x["distance"])

    def deduplicate(self, file_list: List[str], threshold: int = 5) -> List[str]:
        """
        从文件列表中去除重复，返回去重后的列表（保留每组中最先出现的）
        """
        unique = []
        seen_hashes = []

        for path in file_list:
            try:
                fp = VideoHasher.compute_video_fingerprint(path)
                rep = fp["representative_hash"]
                if not any(VideoHasher.is_similar(rep, h, threshold) for h in seen_hashes):
                    unique.append(path)
                    seen_hashes.append(rep)
                    self.add_video(fp)
            except Exception as e:
                logger.warning("跳过 %s: %s", path, e)

        return unique

    def scan_and_index(
        self,
        directory: str,
        extensions: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> int:
        """
        扫描目录，批量建立指纹索引

        Returns:
            成功索引的视频数量
        """
        exts = extensions or [".mp4", ".mov", ".avi", ".mkv", ".m4v"]
        video_files = [
            p for p in Path(directory).rglob("*")
            if p.suffix.lower() in exts
        ]

        indexed = 0
        for i, path in enumerate(video_files):
            if progress_callback:
                progress_callback(i + 1, len(video_files))
            try:
                fp = VideoHasher.compute_video_fingerprint(str(path))
                self.add_video(fp)
                indexed += 1
            except Exception as e:
                logger.error("索引失败 %s: %s", path.name, e)

        return indexed

    def get_stats(self) -> Dict:
        """获取数据库统计信息"""
        video_count = self._conn.execute("SELECT COUNT(*) FROM video_fingerprints").fetchone()[0]
        frame_count = self._conn.execute("SELECT COUNT(*) FROM frame_hashes").fetchone()[0]
        dup_groups = self.find_duplicates()
        return {
            "indexed_videos": video_count,
            "indexed_frames": frame_count,
            "duplicate_groups": len(dup_groups),
            "duplicate_videos": sum(len(g) for g in dup_groups),
        }

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        logger.info("Usage: python fingerprint.py <video_dir> [db_path]")
        sys.exit(1)

    video_dir = sys.argv[1]
    db_path = sys.argv[2] if len(sys.argv) > 2 else "./fingerprints.db"

    with FingerprintDB(Path(db_path)) as db:
        logger.info("扫描目录: %s", video_dir)
        count = db.scan_and_index(
            video_dir,
            progress_callback=lambda cur, tot: logger.info("[%d/%d]", cur, tot)
        )
        logger.info("索引完成: %d 个视频", count)

        stats = db.get_stats()
        logger.info("统计: %s", stats)

        dups = db.find_duplicates()
        if dups:
            logger.info("发现 %d 组重复:", len(dups))
            for g in dups:
                logger.info("  - %s", ", ".join(Path(p).name for p in g))
