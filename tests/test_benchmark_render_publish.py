import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_script_generates_report(tmp_path):
    out = tmp_path / "bench_report.json"
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "benchmark_render_publish.py"),
        "--iterations",
        "3",
        "--output",
        str(out),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert out.exists()

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert "benchmarks" in payload
    assert "acceptance" in payload
    assert "social_export_plan" in payload["benchmarks"]
    assert "content_publish_dry" in payload["benchmarks"]
    assert isinstance(payload["acceptance"].get("pass"), bool)
