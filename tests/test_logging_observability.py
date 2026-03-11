"""Tests for P0 logging & performance observability services and routes."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── logging_service ────────────────────────────────────────────────────

class TestLoggingService:
    def test_init_creates_log_file(self, tmp_path):
        from modules.app_api.services import logging_service

        # Reset so we can re-init for this test
        logging_service._initialized = False
        logging_service._log_dir = None

        log_dir = logging_service.init_logging(log_dir=tmp_path / "test_logs")
        test_logger = logging.getLogger("test.observability")
        test_logger.info("hello from observability test")

        log_file = log_dir / "videoeditor.log"
        assert log_file.exists()
        content = log_file.read_text(encoding="utf-8")
        assert "hello from observability test" in content

        # Cleanup: remove handler to avoid leaking into other tests
        root = logging.getLogger()
        for h in list(root.handlers):
            if hasattr(h, "baseFilename") and "test_logs" in str(getattr(h, "baseFilename", "")):
                root.removeHandler(h)
                h.close()
        logging_service._initialized = False
        logging_service._log_dir = None

    def test_current_log_file_none_before_init(self):
        from modules.app_api.services import logging_service

        old_init = logging_service._initialized
        old_dir = logging_service._log_dir
        logging_service._initialized = False
        logging_service._log_dir = None
        try:
            assert logging_service.current_log_file() is None
        finally:
            logging_service._initialized = old_init
            logging_service._log_dir = old_dir


# ── startup_timing ─────────────────────────────────────────────────────

class TestStartupTiming:
    def test_mark_and_snapshot(self):
        from modules.app_api.services.startup_timing import mark, snapshot, reset

        reset()
        mark("event_a")
        mark("event_b")
        snap = snapshot()
        assert snap["total_ms"] >= 0
        assert len(snap["marks"]) == 2
        events = [m["event"] for m in snap["marks"]]
        assert "event_a" in events
        assert "event_b" in events
        reset()

    def test_empty_snapshot(self):
        from modules.app_api.services.startup_timing import snapshot, reset

        reset()
        snap = snapshot()
        assert snap == {"marks": [], "total_ms": 0}


# ── perf_log ───────────────────────────────────────────────────────────

class TestPerfLog:
    def test_record_and_recent(self, tmp_path):
        from modules.app_api.services import perf_log

        db = tmp_path / "test_perf.db"
        perf_log.init_perf_log(db)

        perf_log.record("test_op", 42.5, {"detail": "unit"})
        perf_log.record("test_op", 55.0)
        perf_log.record("other_op", 10.0)

        rows = perf_log.recent(limit=10)
        assert len(rows) >= 3
        ops = [r["operation"] for r in rows]
        assert "test_op" in ops
        assert "other_op" in ops

        perf_log.close()

    def test_query_stats(self, tmp_path):
        from modules.app_api.services import perf_log

        db = tmp_path / "test_perf_stats.db"
        perf_log.init_perf_log(db)

        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            perf_log.record("stat_op", v)

        stats = perf_log.query_stats(operation="stat_op")
        assert "stat_op" in stats
        s = stats["stat_op"]
        assert s["count"] == 5
        assert s["min"] == 10.0
        assert s["max"] == 50.0
        assert 25 <= s["avg"] <= 35

        perf_log.close()

    def test_record_never_raises(self, tmp_path):
        from modules.app_api.services import perf_log

        # Without init, record should silently do nothing
        perf_log._conn = None
        perf_log.record("noop", 1.0)  # should not raise


# ── API routes ─────────────────────────────────────────────────────────

class TestObservabilityRoutes:
    def _make_client(self):
        from modules.app_api import server
        server.app.config["TESTING"] = True
        return server.app.test_client()

    def test_startup_timing_route(self):
        client = self._make_client()
        resp = client.get("/api/system/startup-timing")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "startup" in data

    def test_perf_route(self):
        client = self._make_client()
        resp = client.get("/api/system/perf")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "stats" in data
        assert "recent" in data

    def test_logs_export_route(self):
        client = self._make_client()
        resp = client.post(
            "/api/system/logs/export",
            json={"format": "json", "tail": 10},
            content_type="application/json",
        )
        # 200 if logging was init'd, 404 otherwise — both are acceptable
        assert resp.status_code in (200, 404)
