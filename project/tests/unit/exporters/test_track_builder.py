"""Unit tests for track_builder upgrade (C5)."""

from modules.exporters.track_builder import build_tracks_from_script


def _script():
    return {
        "clips": [
            {"video_id": "a", "duration": 5.0, "video_path": "/v/a.mp4"},
            {"video_id": "b", "duration": 3.0, "video_path": "/v/b.mp4"},
        ],
        "subtitles": [{"start_time": 0, "end_time": 3, "cn_text": "Hello"}],
    }


def test_backward_compat():
    """Without extra config, output format is unchanged."""
    result = build_tracks_from_script(_script(), {"bgm_path": "/bgm.mp3"})
    assert "video" in result
    assert "subtitle" in result
    assert "audio" in result
    assert len(result["video"]) == 2
    # No extra keys
    assert "audio_2" not in result
    assert "video_2" not in result


def test_extra_audio():
    """extra_audio_tracks config creates additional audio keys."""
    config = {
        "extra_audio_tracks": [
            {"label": "SFX", "path": "/sfx.wav", "volume": 0.5},
        ],
    }
    result = build_tracks_from_script(_script(), config)
    assert "audio_2" in result
    assert result["audio_2"][0]["label"] == "SFX"
    assert result["audio_2"][0]["volume"] == 0.5


def test_extra_video():
    """extra_video_tracks config creates PiP overlay keys."""
    config = {
        "extra_video_tracks": [
            {"label": "Facecam", "path": "/cam.mp4", "start_ms": 1000, "end_ms": 5000},
        ],
    }
    result = build_tracks_from_script(_script(), config)
    assert "video_2" in result
    assert result["video_2"][0]["label"] == "Facecam"
    assert result["video_2"][0]["start_ms"] == 1000


def test_import_to_store():
    """Output dict can be converted to TimelineStore-compatible format."""
    result = build_tracks_from_script(_script(), {})
    # Each key maps to a list of dicts — compatible with add_track + add_clip
    for key, items in result.items():
        assert isinstance(items, list)
        for item in items:
            assert isinstance(item, dict)
