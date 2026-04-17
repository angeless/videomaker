"""RegionExtractor — crop annotated regions from video frames.

Converts DrawingOverlay stroke JSON into cropped PIL Images
for VLM analysis.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

logger = logging.getLogger(__name__)

# Padding ratio for pen/arrow bounding boxes
BBOX_PADDING_RATIO = 0.10
# Default crop size (px) for arrow tip
ARROW_CROP_SIZE = 200


@dataclass
class ExtractionResult:
    """Result of region extraction from frame + strokes."""

    region_image: Any  # PIL.Image
    bbox: Tuple[int, int, int, int]  # (x, y, w, h)
    tool_type: str
    confidence: float = 1.0


class RegionExtractor:
    """Extract annotated regions from video frames."""

    def extract(
        self,
        frame: Any,
        strokes: List[Dict],
        canvas_size: Optional[Tuple[int, int]] = None,
    ) -> ExtractionResult:
        """Crop the annotated region from a video frame.

        Args:
            frame: PIL.Image of the video frame.
            strokes: List of stroke dicts from DrawingOverlay.serializeToStore().
            canvas_size: (width, height) of the canvas. If None, uses frame size.

        Returns:
            ExtractionResult with cropped image and metadata.
        """
        if not strokes:
            return ExtractionResult(
                region_image=frame,
                bbox=(0, 0, frame.size[0], frame.size[1]),
                tool_type="full_frame",
            )

        frame_w, frame_h = frame.size
        canvas_w, canvas_h = canvas_size or (frame_w, frame_h)
        # Round-15.5: a caller passing canvas_size=(0, 0) would crash on
        # frame_w/canvas_w below. Fall back to frame dimensions when the
        # canvas is missing/degenerate.
        if not canvas_w or canvas_w <= 0:
            canvas_w = frame_w
        if not canvas_h or canvas_h <= 0:
            canvas_h = frame_h

        # Auto-detect normalized coordinates (0-1 range from DrawingOverlay)
        all_points = [p for s in strokes for p in s.get("points", [])]
        is_normalized = all_points and all(
            0 <= p.get("x", 0) <= 1.01 and 0 <= p.get("y", 0) <= 1.01
            for p in all_points
        )

        if is_normalized:
            # Normalized coords: multiply directly by frame size
            scale_x = float(frame_w)
            scale_y = float(frame_h)
        else:
            # Pixel coords: scale from canvas to frame
            scale_x = frame_w / canvas_w
            scale_y = frame_h / canvas_h

        # Determine the primary tool and compute bounding box
        tool_type = strokes[0].get("tool", strokes[0].get("type", "pen"))

        if len(strokes) == 1:
            bbox = self._stroke_to_bbox(strokes[0], scale_x, scale_y)
            tool_type = strokes[0].get("tool", "pen")
        else:
            # Merge bounding boxes of all strokes
            boxes = [
                self._stroke_to_bbox(s, scale_x, scale_y) for s in strokes
            ]
            bbox = self._merge_bboxes(boxes)
            tool_type = strokes[0].get("tool", "pen")

        # Clamp to frame bounds
        x, y, w, h = bbox
        x = max(0, x)
        y = max(0, y)
        w = min(w, frame_w - x)
        h = min(h, frame_h - y)

        if w <= 0 or h <= 0:
            return ExtractionResult(
                region_image=frame,
                bbox=(0, 0, frame_w, frame_h),
                tool_type="full_frame",
            )

        cropped = frame.crop((x, y, x + w, y + h))
        return ExtractionResult(
            region_image=cropped,
            bbox=(x, y, w, h),
            tool_type=tool_type,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_stroke(stroke: Dict) -> Dict:
        """Normalize DrawingOverlay stroke format differences.

        DrawingOverlay uses 'type' key and 'start'/'end' for rect/circle/arrow.
        RegionExtractor expects 'tool' key and 'points' list.
        """
        result = dict(stroke)
        # Accept both 'tool' and 'type' keys
        if "tool" not in result and "type" in result:
            result["tool"] = result["type"]
        # Convert 'start'/'end' to 'points' list
        if "points" not in result and "start" in result:
            pts = [result["start"]]
            if "end" in result:
                pts.append(result["end"])
            result["points"] = pts
        return result

    def _stroke_to_bbox(
        self,
        stroke: Dict,
        scale_x: float,
        scale_y: float,
    ) -> Tuple[int, int, int, int]:
        """Convert a single stroke to (x, y, w, h) bounding box."""
        stroke = self._normalize_stroke(stroke)
        tool = stroke.get("tool", "pen")
        points = stroke.get("points", [])

        if not points:
            return (0, 0, 0, 0)

        if tool == "rect":
            return self._rect_bbox(points, scale_x, scale_y)
        elif tool == "circle":
            return self._circle_bbox(points, scale_x, scale_y)
        elif tool == "arrow":
            return self._arrow_bbox(points, scale_x, scale_y)
        elif tool == "spotlight":
            return self._rect_bbox(points, scale_x, scale_y)
        else:
            # pen, text, blur, eraser — use bounding box of all points
            return self._points_bbox(points, scale_x, scale_y)

    def _rect_bbox(
        self, points: List[Dict], sx: float, sy: float
    ) -> Tuple[int, int, int, int]:
        """Rect tool: two corner points."""
        if len(points) < 2:
            return self._points_bbox(points, sx, sy)
        x1 = int(points[0]["x"] * sx)
        y1 = int(points[0]["y"] * sy)
        x2 = int(points[1]["x"] * sx)
        y2 = int(points[1]["y"] * sy)
        x = min(x1, x2)
        y = min(y1, y2)
        return (x, y, abs(x2 - x1), abs(y2 - y1))

    def _circle_bbox(
        self, points: List[Dict], sx: float, sy: float
    ) -> Tuple[int, int, int, int]:
        """Circle/ellipse tool: bounding rectangle of the ellipse."""
        if len(points) < 2:
            return self._points_bbox(points, sx, sy)
        x1 = int(points[0]["x"] * sx)
        y1 = int(points[0]["y"] * sy)
        x2 = int(points[1]["x"] * sx)
        y2 = int(points[1]["y"] * sy)
        x = min(x1, x2)
        y = min(y1, y2)
        return (x, y, abs(x2 - x1), abs(y2 - y1))

    def _arrow_bbox(
        self, points: List[Dict], sx: float, sy: float
    ) -> Tuple[int, int, int, int]:
        """Arrow tool: crop around the arrow tip (end point)."""
        if len(points) < 2:
            return self._points_bbox(points, sx, sy)
        # Arrow tip is the last point
        tip_x = int(points[-1]["x"] * sx)
        tip_y = int(points[-1]["y"] * sy)
        half = ARROW_CROP_SIZE // 2
        return (tip_x - half, tip_y - half, ARROW_CROP_SIZE, ARROW_CROP_SIZE)

    def _points_bbox(
        self, points: List[Dict], sx: float, sy: float
    ) -> Tuple[int, int, int, int]:
        """Compute bounding box of a list of points with padding."""
        if not points:
            return (0, 0, 0, 0)

        xs = [int(p["x"] * sx) for p in points]
        ys = [int(p["y"] * sy) for p in points]

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        w = max_x - min_x
        h = max_y - min_y

        # Add padding
        pad_x = max(int(w * BBOX_PADDING_RATIO), 10)
        pad_y = max(int(h * BBOX_PADDING_RATIO), 10)

        return (min_x - pad_x, min_y - pad_y, w + 2 * pad_x, h + 2 * pad_y)

    @staticmethod
    def _merge_bboxes(
        boxes: List[Tuple[int, int, int, int]],
    ) -> Tuple[int, int, int, int]:
        """Merge multiple bounding boxes into one encompassing box."""
        if not boxes:
            return (0, 0, 0, 0)

        min_x = min(b[0] for b in boxes)
        min_y = min(b[1] for b in boxes)
        max_x = max(b[0] + b[2] for b in boxes)
        max_y = max(b[1] + b[3] for b in boxes)

        return (min_x, min_y, max_x - min_x, max_y - min_y)
