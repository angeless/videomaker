#!/usr/bin/env python3
"""
高级磨皮滤镜模块
算法：MediaPipe 人脸检测 + 频率分解（低频=光影/肤色，高频=毛孔/痘印）+ 局部平滑

来源：opencut/render/beauty.py（移植并适配 video-editor skill）
依赖（可选）：pip install mediapipe opencv-python numpy
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False

try:
    import mediapipe as mp
    HAS_MEDIAPIPE = True
except ImportError:
    HAS_MEDIAPIPE = False


class AdvancedBeautyFilter:
    """
    基于频率分解的高级磨皮滤镜

    核心算法：
    1. MediaPipe 人脸检测 → 获取人脸区域
    2. 频率分解：原图 = 低频（肤色光影）+ 高频（毛孔纹理痘印）
    3. 对低频层做智能平滑（保留轮廓，只处理皮肤纹理）
    4. 针对检测到的痘印区域做 inpainting 修复
    5. 重合：平滑低频 + 原高频 × (1 - pore_reduction)
    """

    def __init__(
        self,
        smooth_strength: float = 0.8,
        pore_reduction: float = 0.6,
        acne_threshold: float = 0.3
    ):
        if not HAS_CV2:
            raise ImportError("opencv-python 未安装：pip install opencv-python")

        self.smooth_strength = smooth_strength
        self.pore_reduction = pore_reduction
        self.acne_threshold = acne_threshold

        self._face_detector = None
        if HAS_MEDIAPIPE:
            self._face_detector = mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.5
            )

    def detect_face_regions(self, image: "np.ndarray") -> List[Tuple[int, int, int, int]]:
        """
        检测人脸区域
        Returns: [(x, y, w, h), ...]
        """
        if not HAS_MEDIAPIPE or self._face_detector is None:
            # 降级：返回图像中央 60% 区域
            h, w = image.shape[:2]
            margin_x, margin_y = int(w * 0.2), int(h * 0.1)
            return [(margin_x, margin_y, w - 2 * margin_x, h - 2 * margin_y)]

        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = self._face_detector.process(rgb)

        regions = []
        if results.detections:
            h, w = image.shape[:2]
            for det in results.detections:
                bbox = det.location_data.relative_bounding_box
                x = max(0, int(bbox.xmin * w))
                y = max(0, int(bbox.ymin * h))
                fw = min(int(bbox.width * w), w - x)
                fh = min(int(bbox.height * h), h - y)
                regions.append((x, y, fw, fh))

        return regions

    def frequency_separation(
        self, image: "np.ndarray", radius: int = 8
    ) -> Tuple["np.ndarray", "np.ndarray"]:
        """
        频率分解：低频 = 高斯模糊，高频 = 原图 - 低频
        radius 控制分离半径（越大，磨皮越重）
        """
        low_freq = cv2.GaussianBlur(image, (0, 0), radius)
        high_freq = cv2.addWeighted(image, 1.0, low_freq, -1.0, 128)
        return low_freq, high_freq

    def smooth_low_frequency(
        self, low_freq: "np.ndarray", strength: float
    ) -> "np.ndarray":
        """平滑低频层（保边滤镜，避免把轮廓也磨掉）"""
        sigma_color = 50 + int(strength * 50)
        sigma_space = 5 + int(strength * 10)
        return cv2.bilateralFilter(low_freq, d=9, sigmaColor=sigma_color, sigmaSpace=sigma_space)

    def reduce_pores(
        self, high_freq: "np.ndarray", strength: float
    ) -> "np.ndarray":
        """降低高频层能量（减少毛孔可见度）"""
        blended = cv2.addWeighted(
            high_freq, 1.0 - strength,
            np.full_like(high_freq, 128), strength,
            0
        )
        return blended

    def detect_acne_areas(
        self, image: "np.ndarray", face_region: Tuple[int, int, int, int]
    ) -> "np.ndarray":
        """
        检测痘印区域（基于红色通道异常）
        Returns: 二值掩码（255=痘印区域）
        """
        x, y, w, h = face_region
        roi = image[y:y + h, x:x + w]

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # 红色 HSV 范围（两段）
        mask1 = cv2.inRange(hsv, np.array([0, 50, 50]), np.array([10, 255, 255]))
        mask2 = cv2.inRange(hsv, np.array([160, 50, 50]), np.array([180, 255, 255]))
        red_mask = cv2.bitwise_or(mask1, mask2)

        # 形态学处理：去噪 + 扩张
        kernel = np.ones((3, 3), np.uint8)
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
        red_mask = cv2.dilate(red_mask, kernel, iterations=1)

        # 放回全图大小
        full_mask = np.zeros(image.shape[:2], dtype=np.uint8)
        full_mask[y:y + h, x:x + w] = red_mask
        return full_mask

    def heal_acne_areas(self, image: "np.ndarray", acne_mask: "np.ndarray") -> "np.ndarray":
        """用 inpainting 修复痘印区域"""
        if not np.any(acne_mask):
            return image
        return cv2.inpaint(image, acne_mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

    def apply_beauty_filter(self, image: "np.ndarray") -> "np.ndarray":
        """
        对整张图像应用磨皮滤镜

        流程：检测人脸 → 频率分解 → 平滑低频 → 降低高频 → 修复痘印 → 合成
        """
        result = image.copy()
        face_regions = self.detect_face_regions(image)

        for region in face_regions:
            x, y, w, h = region
            if w <= 0 or h <= 0:
                continue

            roi = image[y:y + h, x:x + w]

            # 频率分解
            low_freq, high_freq = self.frequency_separation(roi)

            # 平滑低频
            smooth_low = self.smooth_low_frequency(low_freq, self.smooth_strength)

            # 降低高频（减少毛孔）
            reduced_high = self.reduce_pores(high_freq, self.pore_reduction)

            # 合成
            processed = cv2.addWeighted(smooth_low, 1.0, reduced_high, 1.0, -128)
            processed = np.clip(processed, 0, 255).astype(np.uint8)

            result[y:y + h, x:x + w] = processed

        # 修复痘印（在合成后处理，针对最大人脸区域）
        if face_regions and self.acne_threshold > 0:
            region = max(face_regions, key=lambda r: r[2] * r[3])
            acne_mask = self.detect_acne_areas(result, region)
            result = self.heal_acne_areas(result, acne_mask)

        return result

    def process_video_frame(self, frame: "np.ndarray") -> "np.ndarray":
        """处理单帧（供视频逐帧处理调用）"""
        return self.apply_beauty_filter(frame)

    def process_video(self, input_path: str, output_path: str) -> str:
        """
        逐帧处理视频，输出磨皮后的视频文件

        Args:
            input_path: 输入视频路径
            output_path: 输出视频路径

        Returns:
            输出视频路径
        """
        cap = cv2.VideoCapture(input_path)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            try:
                # P0.4: 安全上限防止损坏视频导致无限循环
                max_frames = max(total * 2, int(fps * 600)) if total > 0 else int(fps * 600)
                processed = 0
                while processed < max_frames:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    out.write(self.process_video_frame(frame))
                    processed += 1
                    if processed % 30 == 0:
                        logger.info("磨皮进度: %d/%d", processed, total)
            finally:
                out.release()
        finally:
            cap.release()
        logger.info("磨皮完成: %s", output_path)
        return output_path


def apply_beauty_filter_simple(image: "np.ndarray", strength: float = 0.7) -> "np.ndarray":
    """
    简易磨皮（不需要 mediapipe，直接对全图做频率分解）
    适合快速处理或 mediapipe 未安装时的降级方案
    """
    if not HAS_CV2:
        return image

    radius = max(3, int(strength * 12))
    low_freq = cv2.GaussianBlur(image, (0, 0), radius)
    high_freq = cv2.addWeighted(image, 1.0, low_freq, -1.0, 128)
    reduced_high = cv2.addWeighted(high_freq, 1.0 - strength * 0.5,
                                   np.full_like(high_freq, 128), strength * 0.5, 0)
    result = cv2.addWeighted(low_freq, 1.0, reduced_high, 1.0, -128)
    return np.clip(result, 0, 255).astype(np.uint8)
