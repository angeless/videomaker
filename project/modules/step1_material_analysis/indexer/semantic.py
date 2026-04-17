#!/usr/bin/env python3
"""
语义索引模块（CLIP）
使用 OpenAI CLIP 进行图文语义搜索，支持中英文查询匹配视频内容。

来源：opencut/indexer/semantic.py（移植并适配 manage-videos skill）
依赖（可选）：pip install torch transformers
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Callable

logger = logging.getLogger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import torch
    from transformers import CLIPProcessor, CLIPModel
    from PIL import Image
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False


# Round-13 P1: CLIP model_name flows from workflow config into
# `CLIPModel.from_pretrained(model_name)`, which auto-downloads the named
# HuggingFace repo. Untrusted repo names can trigger arbitrary-code
# execution during model loading. Allowlist is the reliable defense.
_ALLOWED_CLIP_MODELS = {
    "openai/clip-vit-base-patch32",
    "openai/clip-vit-base-patch16",
    "openai/clip-vit-large-patch14",
    "openai/clip-vit-large-patch14-336",
    # Multilingual variants some users run
    "laion/CLIP-ViT-B-32-laion2B-s34B-b79K",
    "laion/CLIP-ViT-L-14-laion2B-s32B-b82K",
}


class CLIPEncoder:
    """CLIP 图文编码器"""

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        if not HAS_CLIP:
            raise ImportError("CLIP 依赖未安装：pip install torch transformers Pillow")

        # Reject any model name not on the allowlist to block code execution
        # via malicious HuggingFace repo download.
        if model_name not in _ALLOWED_CLIP_MODELS:
            logger.warning(
                "CLIP model_name %r not on allowlist; falling back to openai/clip-vit-base-patch32",
                model_name,
            )
            model_name = "openai/clip-vit-base-patch32"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_name = model_name
        self._model = None
        self._processor = None

    def _load_model(self):
        """延迟加载（首次使用时）"""
        if self._model is None:
            import time as _t
            _t0 = _t.perf_counter()
            logger.info("加载 CLIP 模型: %s (device=%s)", self.model_name, self.device)
            self._model = CLIPModel.from_pretrained(self.model_name).to(self.device)
            self._processor = CLIPProcessor.from_pretrained(self.model_name)
            _elapsed = (_t.perf_counter() - _t0) * 1000
            logger.info("[perf] clip_model_load: %.1fms model=%s device=%s",
                        _elapsed, self.model_name, self.device)

    def encode_image(self, image) -> "np.ndarray":
        """
        编码图像为 512 维向量（归一化）
        image: numpy BGR 数组（来自 cv2）或 PIL.Image
        """
        import time as _t
        _t0 = _t.perf_counter()
        self._load_model()

        if HAS_CV2 and isinstance(image, type(None) if not HAS_NUMPY else np.ndarray):
            # BGR → RGB → PIL
            pil_img = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        else:
            pil_img = image

        inputs = self._processor(images=pil_img, return_tensors="pt").to(self.device)
        with torch.no_grad():
            features = self._model.get_image_features(**inputs)
        vec = features.cpu().numpy()[0]
        logger.debug("[perf] clip_encode_image: %.1fms", (_t.perf_counter() - _t0) * 1000)
        return vec / (np.linalg.norm(vec) + 1e-8)

    def encode_text(self, text: str) -> "np.ndarray":
        """编码文本为 512 维向量（归一化）"""
        import time as _t
        _t0 = _t.perf_counter()
        self._load_model()

        inputs = self._processor(text=[text], return_tensors="pt", padding=True).to(self.device)
        with torch.no_grad():
            features = self._model.get_text_features(**inputs)
        vec = features.cpu().numpy()[0]
        logger.debug("[perf] clip_encode_text: %.1fms", (_t.perf_counter() - _t0) * 1000)
        return vec / (np.linalg.norm(vec) + 1e-8)

    def compute_similarity(self, image_vec: "np.ndarray", text_vec: "np.ndarray") -> float:
        """计算余弦相似度"""
        return float(np.dot(image_vec, text_vec))


class SemanticIndex:
    """
    视频语义索引

    索引文件格式（JSON）：
    {
        "videos": {
            "/path/to/video.mp4": {
                "keyframes": [[...512-dim vector...], ...],
                "clip_vectors": [{"start": 0, "end": 10, "vector": [...]}],
                "indexed_at": "..."
            }
        }
    }
    """

    def __init__(self, index_path: str, model_name: Optional[str] = None):
        self.index_path = Path(index_path)
        self.model_name = model_name or "openai/clip-vit-base-patch32"
        self._index: Dict = {"videos": {}}
        self._encoder: Optional[CLIPEncoder] = None
        self._load_index()

    def _load_index(self):
        if self.index_path.exists():
            with open(self.index_path, 'r', encoding='utf-8') as f:
                self._index = json.load(f)

    def _save_index(self):
        # Round-13: atomic write so crash mid-save can't corrupt the
        # semantic index (which would lose all prior embeddings).
        from modules.app_api.param_utils import atomic_write_json
        atomic_write_json(self.index_path, self._index)

    def _get_encoder(self) -> CLIPEncoder:
        if self._encoder is None:
            self._encoder = CLIPEncoder(self.model_name)
        return self._encoder

    def extract_keyframes(self, video_path: str, num_frames: int = 5) -> List:
        """均匀采样关键帧，返回 PIL.Image 列表"""
        if not HAS_CV2:
            raise ImportError("opencv-python 未安装")

        cap = cv2.VideoCapture(video_path)
        try:
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            indices = [int(i * total / num_frames) for i in range(num_frames)]

            frames = []
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if ret:
                    from PIL import Image
                    frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
        finally:
            cap.release()
        return frames

    def index_video(self, video_path: str, clip_duration: float = 10.0) -> List[str]:
        """
        对单个视频建立语义索引

        Returns:
            生成的向量 ID 列表
        """
        if not HAS_CLIP:
            logger.warning("跳过语义索引：CLIP 未安装")
            return []

        encoder = self._get_encoder()
        frames = self.extract_keyframes(video_path, num_frames=5)

        # 编码关键帧
        keyframe_vecs = [encoder.encode_image(f).tolist() for f in frames]

        self._index["videos"][video_path] = {
            "keyframes": keyframe_vecs,
            "indexed_at": __import__("datetime").datetime.now().isoformat()
        }
        self._save_index()

        return [f"{video_path}:frame:{i}" for i in range(len(keyframe_vecs))]

    def search(self, query: str, top_k: int = 5, min_duration: float = 0.0) -> List[Dict]:
        """
        语义搜索：用文本查询匹配视频

        Args:
            query: 中文或英文查询
            top_k: 返回结果数
            min_duration: 最短时长过滤（秒）

        Returns:
            [{"path": str, "score": float, "match_frame": int}, ...]
        """
        if not HAS_CLIP:
            logger.warning("CLIP 未安装，降级为关键词搜索")
            return self._keyword_fallback(query, top_k)

        encoder = self._get_encoder()
        text_vec = encoder.encode_text(query)

        results = []
        for path, data in self._index["videos"].items():
            keyframes = data.get("keyframes", [])
            if not keyframes:
                continue

            # 取每帧相似度的最大值
            import numpy as np
            scores = [
                encoder.compute_similarity(np.array(kv), text_vec)
                for kv in keyframes
            ]
            best_score = max(scores)
            best_frame = scores.index(best_score)

            results.append({
                "path": path,
                "score": best_score,
                "match_frame": best_frame
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _keyword_fallback(self, query: str, top_k: int) -> List[Dict]:
        """CLIP 不可用时的关键词降级搜索"""
        results = []
        keywords = query.split()
        for path in self._index["videos"]:
            score = sum(1 for kw in keywords if kw.lower() in Path(path).name.lower())
            if score > 0:
                results.append({"path": path, "score": float(score), "match_frame": 0})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def batch_index(
        self,
        video_files: List[str],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> int:
        """批量建立语义索引"""
        indexed = 0
        for i, path in enumerate(video_files):
            if progress_callback:
                progress_callback(i + 1, len(video_files))
            try:
                self.index_video(path)
                indexed += 1
            except Exception as e:
                logger.error("索引失败 %s: %s", Path(path).name, e)
        return indexed

    def get_stats(self) -> Dict:
        return {
            "indexed_videos": len(self._index["videos"]),
            "clip_available": HAS_CLIP,
            "model": self.model_name if HAS_CLIP else "N/A (关键词降级)",
        }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        logger.info("Usage: python semantic.py <video_dir> <index.json> [query]")
        sys.exit(1)

    video_dir, index_path = sys.argv[1], sys.argv[2]
    query = sys.argv[3] if len(sys.argv) > 3 else None

    idx = SemanticIndex(index_path)

    if query is None:
        # 建立索引
        files = [str(p) for p in Path(video_dir).rglob("*")
                 if p.suffix.lower() in (".mp4", ".mov", ".avi", ".mkv")]
        logger.info("发现 %d 个视频，开始索引...", len(files))
        count = idx.batch_index(files, progress_callback=lambda c, t: logger.info("[%d/%d]", c, t))
        logger.info("完成: %d 个视频", count)
        logger.info("统计: %s", idx.get_stats())
    else:
        # 搜索
        results = idx.search(query, top_k=5)
        logger.info("查询: %s", query)
        for r in results:
            logger.info("  %.3f  %s", r['score'], Path(r['path']).name)
