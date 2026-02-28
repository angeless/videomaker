from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.capabilities.subtitle_calibration import calibrate_subtitles


def test_subtitle_calibration_text_only_keeps_timeline():
    subtitles = [
        {"index": 1, "start_time": 0.0, "end_time": 1.2, "cn_text": "你好", "en_text": "hello"},
        {"index": 2, "start_time": 1.3, "end_time": 2.0, "cn_text": "世界", "en_text": "world"},
    ]
    result = calibrate_subtitles(subtitles, mode="text_only", translation="off")
    assert result["mode"] == "text_only"
    assert result["quality_report"]["timeline_changed_count"] == 0
    assert result["calibrated_subtitles"][0]["start_time"] == 0.0
    assert result["calibrated_subtitles"][1]["start_time"] == 1.3


def test_subtitle_calibration_timeline_align_resolves_overlap():
    subtitles = [
        {"index": 1, "start_time": 0.0, "end_time": 1.5, "cn_text": "第一句", "en_text": "line one"},
        {"index": 2, "start_time": 1.2, "end_time": 2.2, "cn_text": "第二句", "en_text": "line two"},
    ]
    result = calibrate_subtitles(subtitles, mode="timeline_align", translation="off")
    calibrated = result["calibrated_subtitles"]
    assert result["quality_report"]["overlap_before"] == 1
    assert result["quality_report"]["overlap_after"] == 0
    assert calibrated[1]["start_time"] >= calibrated[0]["end_time"]


def test_subtitle_calibration_bilingual_translation_fills_missing_side():
    subtitles = [
        {"index": 1, "start_time": 0.0, "end_time": 1.0, "cn_text": "今天出发", "en_text": ""},
        {"index": 2, "start_time": 1.1, "end_time": 2.0, "cn_text": "", "en_text": "See you"},
    ]
    result = calibrate_subtitles(subtitles, mode="text_only", translation="bilingual")
    calibrated = result["calibrated_subtitles"]
    assert calibrated[0]["en_text"].strip() != ""
    assert calibrated[1]["cn_text"].strip() != ""
    assert result["quality_report"]["text_changed_count"] >= 2


def test_subtitle_calibration_api_inline_run(tmp_path):
    fake_library_mod = types.ModuleType("modules.library.global_media_library")

    class _FakeGlobalMediaLibrary:
        def __init__(self, *args, **kwargs):
            self.db_path = ROOT / ".tmp_fake_library_subtitle_api.db"

    fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
    sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

    from modules.app_api import server  # noqa: E402

    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        resp = client.post(
            "/api/capabilities/subtitle_calibration/run",
            json={
                "input_mode": "inline",
                "mode": "timeline_align",
                "translation": "bilingual",
                "subtitles": [
                    {"start_time": 0, "end_time": 1.1, "cn_text": "你好"},
                    {"start_time": 1.0, "end_time": 1.8, "en_text": "hello"},
                ],
            },
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        assert payload["result"]["mode"] == "timeline_align"
        assert payload["result"]["quality_report"]["overlap_after"] == 0
    finally:
        server._project_dir = old_project_dir
