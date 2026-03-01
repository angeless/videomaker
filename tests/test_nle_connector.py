import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.adapters.nle_connector import (  # noqa: E402
    get_nle_connector,
    list_nle_connector_statuses,
    normalize_nle_editor,
)


def test_normalize_nle_editor_aliases():
    assert normalize_nle_editor("resolve") == "davinci"
    assert normalize_nle_editor("fcp") == "finalcut"
    assert normalize_nle_editor("unknown_editor") == "finalcut"


def test_list_nle_connector_statuses_contains_requested_editor():
    statuses = list_nle_connector_statuses(["davinci", "premiere"])
    ids = {item["editor"] for item in statuses}
    assert "davinci" in ids
    assert "premiere" in ids


def test_resolve_connector_detects_env_path(tmp_path, monkeypatch):
    fake_app = tmp_path / "DaVinci Resolve.app"
    fake_app.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("VIDEOEDITOR_DAVINCI_APP_PATH", str(fake_app))

    connector = get_nle_connector("davinci")
    status = connector.detect().to_dict()
    assert status["editor"] == "davinci"
    assert status["app_detected"] is True
    assert status["app_path"] == str(fake_app.resolve())


def test_davinci_connector_creates_handoff(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    script = {
        "clips": [
            {
                "video_id": "v1",
                "source_start": 0,
                "source_end": 2.0,
                "scene_description": "demo",
            }
        ]
    }
    materials = {
        "v1": {
            "path": str(video),
            "filename": "clip.mp4",
        }
    }

    connector = get_nle_connector("davinci")
    out_dir = tmp_path / "handoff"
    ret = connector.create_handoff(
        script=script,
        materials=materials,
        output_dir=str(out_dir),
        title="Demo Timeline",
        fps=30,
    )
    assert ret["editor"] == "davinci"
    assert any(str(x).endswith(".fcpxml") for x in ret["files"])
    assert any(str(x).endswith(".edl") for x in ret["files"])
