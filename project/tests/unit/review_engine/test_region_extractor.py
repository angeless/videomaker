"""Tests for RegionExtractor — brush region cropping (v0.17.0 R4)."""

import pytest

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

pytestmark = pytest.mark.skipif(not _HAS_PIL, reason="PIL not available")

from modules.review_engine.region_extractor import RegionExtractor, ExtractionResult


@pytest.fixture
def frame():
    """Create a 1920x1080 test frame with color gradient."""
    img = Image.new("RGB", (1920, 1080), "black")
    # Draw a colored region for easier visual debugging
    for x in range(500, 700):
        for y in range(300, 500):
            img.putpixel((x, y), (255, 0, 0))  # red square
    return img


@pytest.fixture
def extractor():
    return RegionExtractor()


class TestRectTool:
    def test_rect_crop(self, extractor, frame):
        strokes = [
            {
                "tool": "rect",
                "points": [{"x": 500, "y": 300}, {"x": 700, "y": 500}],
                "color": "#ff0000",
                "lineWidth": 3,
            }
        ]
        result = extractor.extract(frame, strokes, canvas_size=(1920, 1080))
        assert isinstance(result, ExtractionResult)
        assert result.region_image.size[0] == 200  # 700-500
        assert result.region_image.size[1] == 200  # 500-300
        assert result.tool_type == "rect"
        assert result.bbox == (500, 300, 200, 200)


class TestCircleTool:
    def test_circle_crop_bounding_rect(self, extractor, frame):
        strokes = [
            {
                "tool": "circle",
                "points": [{"x": 600, "y": 400}, {"x": 700, "y": 500}],
                "color": "#00ff00",
                "lineWidth": 2,
            }
        ]
        result = extractor.extract(frame, strokes, canvas_size=(1920, 1080))
        assert isinstance(result, ExtractionResult)
        assert result.tool_type == "circle"
        # Bounding rect of ellipse
        assert result.region_image.size[0] > 0
        assert result.region_image.size[1] > 0


class TestPenTool:
    def test_pen_bounding_box(self, extractor, frame):
        strokes = [
            {
                "tool": "pen",
                "points": [
                    {"x": 100, "y": 200},
                    {"x": 150, "y": 250},
                    {"x": 200, "y": 220},
                    {"x": 180, "y": 300},
                ],
                "color": "#0000ff",
                "lineWidth": 3,
            }
        ]
        result = extractor.extract(frame, strokes, canvas_size=(1920, 1080))
        assert isinstance(result, ExtractionResult)
        assert result.tool_type == "pen"
        # Bounding box should encompass all points + padding
        assert result.region_image.size[0] > 100  # at least width of points
        assert result.region_image.size[1] > 100


class TestArrowTool:
    def test_arrow_center_crop(self, extractor, frame):
        strokes = [
            {
                "tool": "arrow",
                "points": [{"x": 400, "y": 300}, {"x": 600, "y": 400}],
                "color": "#ffff00",
                "lineWidth": 3,
            }
        ]
        result = extractor.extract(frame, strokes, canvas_size=(1920, 1080))
        assert isinstance(result, ExtractionResult)
        assert result.tool_type == "arrow"
        # Arrow tip is the end point — crop around it
        assert result.region_image.size[0] > 0


class TestMultiStroke:
    def test_multi_stroke_merged_bbox(self, extractor, frame):
        strokes = [
            {
                "tool": "pen",
                "points": [{"x": 100, "y": 100}, {"x": 200, "y": 200}],
                "color": "#ff0000",
                "lineWidth": 3,
            },
            {
                "tool": "pen",
                "points": [{"x": 800, "y": 600}, {"x": 900, "y": 700}],
                "color": "#00ff00",
                "lineWidth": 3,
            },
        ]
        result = extractor.extract(frame, strokes, canvas_size=(1920, 1080))
        assert isinstance(result, ExtractionResult)
        # Should encompass both strokes
        assert result.region_image.size[0] >= 700  # 900-100 (roughly)


class TestNoStroke:
    def test_no_stroke_returns_full_frame(self, extractor, frame):
        result = extractor.extract(frame, [], canvas_size=(1920, 1080))
        assert isinstance(result, ExtractionResult)
        assert result.region_image.size == frame.size
        assert result.tool_type == "full_frame"
