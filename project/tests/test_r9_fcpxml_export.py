"""Tests for R9 FCPXML export."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.exporters.fcpxml.builder import FCPXMLBuilder


@pytest.fixture
def sample_tracks():
    return {
        "video": [
            {"uid": "v1", "start_ms": 0, "end_ms": 3000, "label": "opening", "path": "/fake/v1.mp4"},
            {"uid": "v2", "start_ms": 2700, "end_ms": 7700, "label": "middle", "path": "/fake/v2.mp4"},
        ],
        "subtitle": [
            {"text": "Hello", "start_ms": 0, "end_ms": 2000},
            {"text": "World", "start_ms": 3000, "end_ms": 5000},
        ],
        "audio": [],
    }


class TestFCPXMLBuilder:
    def test_creates_file(self, tmp_path, sample_tracks):
        out = tmp_path / "test.fcpxml"
        builder = FCPXMLBuilder("test", sample_tracks)
        result = builder.build(str(out))
        assert Path(result["fcpxml_path"]).exists()

    def test_valid_xml(self, tmp_path, sample_tracks):
        out = tmp_path / "test.fcpxml"
        builder = FCPXMLBuilder("test", sample_tracks)
        builder.build(str(out))
        tree = ET.parse(str(out))
        assert tree.getroot().tag == "fcpxml"

    def test_root_version_1_9(self, tmp_path, sample_tracks):
        out = tmp_path / "test.fcpxml"
        builder = FCPXMLBuilder("test", sample_tracks)
        builder.build(str(out))
        tree = ET.parse(str(out))
        assert tree.getroot().attrib["version"] == "1.9"

    def test_has_asset_clips(self, tmp_path, sample_tracks):
        out = tmp_path / "test.fcpxml"
        builder = FCPXMLBuilder("test", sample_tracks)
        builder.build(str(out))
        tree = ET.parse(str(out))
        clips = tree.getroot().findall(".//asset-clip")
        assert len(clips) == 2

    def test_has_title_elements(self, tmp_path, sample_tracks):
        out = tmp_path / "test.fcpxml"
        builder = FCPXMLBuilder("test", sample_tracks)
        builder.build(str(out))
        tree = ET.parse(str(out))
        titles = tree.getroot().findall(".//title")
        assert len(titles) >= 1

    def test_result_has_clip_count(self, tmp_path, sample_tracks):
        out = tmp_path / "test.fcpxml"
        builder = FCPXMLBuilder("test", sample_tracks)
        result = builder.build(str(out))
        assert result["clip_count"] == 2
        assert result["duration_ms"] == 7700

    def test_empty_tracks(self, tmp_path):
        out = tmp_path / "empty.fcpxml"
        builder = FCPXMLBuilder("empty", {"video": [], "subtitle": [], "audio": []})
        result = builder.build(str(out))
        tree = ET.parse(str(out))
        assert tree.getroot().tag == "fcpxml"
        assert result["clip_count"] == 0
