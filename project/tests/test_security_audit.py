"""Tests for T-0904: security event audit logging + brute force detection.

Covers:
  AC-01: Origin/CSRF/Token failures produce audit_log entries
  AC-02: Brute-force detection fires after 5 failures in 60s
  AC-03: system_routes input validation uses param_utils
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── helpers ──────────────────────────────────────────────────────────────


class _FakeGlobalMediaLibrary:
    db_path: Path = Path("/tmp/fake.db")

    def get_stats(self):
        return {"total": 0, "video": 0, "audio": 0, "image": 0}

    def search(self, **kw):
        return {"results": [], "total": 0}

    def get_assets(self, uids):
        return [{"uid": u, "status": "unknown"} for u in (uids or [])]


def _setup_server(tmp_path, *, require_token=True, token="test_token", csrf="test_csrf"):
    """Configure server state for security tests. Returns (client, db_path)."""
    from modules.app_api import server

    old = {
        "library": server._library,
        "require": server._REQUIRE_LOCAL_API_TOKEN,
        "token": server._LOCAL_API_TOKEN,
        "csrf": server._LOCAL_CSRF_TOKEN,
        "require_csrf": server._REQUIRE_CSRF_PROTECTION,
    }

    lib = _FakeGlobalMediaLibrary()
    lib.db_path = tmp_path / "test_security_audit.db"
    server._library = lib
    server._REQUIRE_LOCAL_API_TOKEN = require_token
    server._LOCAL_API_TOKEN = token
    server._LOCAL_CSRF_TOKEN = csrf
    server._REQUIRE_CSRF_PROTECTION = True

    # Initialize audit_log with a test DB
    audit_db = tmp_path / "audit.db"
    from modules.app_api.services.audit_log import init_audit_log
    init_audit_log(audit_db)

    client = server.app.test_client()
    return client, audit_db, old


def _restore_server(old):
    from modules.app_api import server
    server._library = old["library"]
    server._REQUIRE_LOCAL_API_TOKEN = old["require"]
    server._LOCAL_API_TOKEN = old["token"]
    server._LOCAL_CSRF_TOKEN = old["csrf"]
    server._REQUIRE_CSRF_PROTECTION = old["require_csrf"]


def _read_audit_entries(db_path, operation=None):
    """Read audit_log entries directly from SQLite."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    if operation:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE operation = ? ORDER BY id DESC", (operation,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── AC-01: Security events produce audit log entries ─────────────────────


class TestSecurityAuditOrigin:
    """AC-01a: Origin check failure writes security_origin_fail."""

    def test_bad_origin_produces_audit_entry(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path)
        try:
            resp = client.post(
                "/api/settings/ui",
                json={"font_scale": 1.0},
                headers={
                    "Origin": "http://evil.example.com",
                    "X-VideoEditor-Token": "test_token",
                    "X-VideoEditor-CSRF": "test_csrf",
                },
            )
            assert resp.status_code == 403
            entries = _read_audit_entries(audit_db, "security_origin_fail")
            assert len(entries) >= 1
            assert entries[0]["resource_type"] == "security"
            assert entries[0]["status"] == "blocked"
        finally:
            _restore_server(old)

    def test_good_origin_no_audit_entry(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path)
        try:
            resp = client.get(
                "/api/status",
                headers={"X-VideoEditor-Token": "test_token"},
            )
            assert resp.status_code == 200
            entries = _read_audit_entries(audit_db, "security_origin_fail")
            assert len(entries) == 0
        finally:
            _restore_server(old)


class TestSecurityAuditCSRF:
    """AC-01b: CSRF check failure writes security_csrf_fail."""

    def test_bad_csrf_produces_audit_entry(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path)
        try:
            resp = client.post(
                "/api/settings/ui",
                json={"font_scale": 1.0},
                headers={
                    "Origin": "http://localhost:5173",
                    "X-VideoEditor-Token": "test_token",
                    "X-VideoEditor-CSRF": "wrong_csrf",
                },
            )
            assert resp.status_code == 403
            entries = _read_audit_entries(audit_db, "security_csrf_fail")
            assert len(entries) >= 1
            assert entries[0]["status"] == "blocked"
        finally:
            _restore_server(old)

    def test_missing_csrf_produces_audit_entry(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path)
        try:
            resp = client.post(
                "/api/settings/ui",
                json={"font_scale": 1.0},
                headers={
                    "Origin": "http://localhost:5173",
                    "X-VideoEditor-Token": "test_token",
                    # no CSRF header
                },
            )
            assert resp.status_code == 403
            entries = _read_audit_entries(audit_db, "security_csrf_fail")
            assert len(entries) >= 1
        finally:
            _restore_server(old)


class TestSecurityAuditToken:
    """AC-01c: Token check failure writes security_token_fail."""

    def test_bad_token_produces_audit_entry(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path)
        try:
            resp = client.get(
                "/api/status",
                headers={"X-VideoEditor-Token": "wrong_token"},
            )
            assert resp.status_code == 401
            entries = _read_audit_entries(audit_db, "security_token_fail")
            assert len(entries) >= 1
            assert entries[0]["status"] == "blocked"
        finally:
            _restore_server(old)

    def test_no_token_produces_audit_entry(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path)
        try:
            resp = client.get("/api/status")
            assert resp.status_code == 401
            entries = _read_audit_entries(audit_db, "security_token_fail")
            assert len(entries) >= 1
        finally:
            _restore_server(old)


# ── AC-02: Brute-force detection ─────────────────────────────────────────


class TestBruteForceDetection:
    """AC-02: 5 token failures from same IP within 60s triggers security_brute_force."""

    def test_brute_force_fires_after_threshold(self, tmp_path):
        from modules.app_api.middleware import security as sec_mod
        # Reset counter
        sec_mod._auth_fail_counter.clear()

        client, audit_db, old = _setup_server(tmp_path)
        try:
            for _ in range(5):
                resp = client.get(
                    "/api/status",
                    headers={"X-VideoEditor-Token": "wrong"},
                )
                assert resp.status_code == 401

            entries = _read_audit_entries(audit_db, "security_brute_force")
            assert len(entries) >= 1
            assert entries[0]["status"] == "blocked"
        finally:
            _restore_server(old)
            sec_mod._auth_fail_counter.clear()

    def test_below_threshold_no_brute_force(self, tmp_path):
        from modules.app_api.middleware import security as sec_mod
        sec_mod._auth_fail_counter.clear()

        client, audit_db, old = _setup_server(tmp_path)
        try:
            for _ in range(4):
                client.get(
                    "/api/status",
                    headers={"X-VideoEditor-Token": "wrong"},
                )
            entries = _read_audit_entries(audit_db, "security_brute_force")
            assert len(entries) == 0
        finally:
            _restore_server(old)
            sec_mod._auth_fail_counter.clear()

    def test_expired_failures_not_counted(self, tmp_path):
        from modules.app_api.middleware import security as sec_mod
        sec_mod._auth_fail_counter.clear()

        client, audit_db, old = _setup_server(tmp_path)
        try:
            # Simulate 4 old failures by directly injecting expired timestamps
            old_time = time.time() - 120  # 2 minutes ago
            sec_mod._auth_fail_counter["127.0.0.1"] = [old_time] * 4

            # One new failure — should NOT trigger brute force (old ones pruned)
            client.get(
                "/api/status",
                headers={"X-VideoEditor-Token": "wrong"},
            )
            entries = _read_audit_entries(audit_db, "security_brute_force")
            assert len(entries) == 0
        finally:
            _restore_server(old)
            sec_mod._auth_fail_counter.clear()


# ── AC-03: system_routes input validation ────────────────────────────────


class TestSystemRoutesValidation:
    """AC-03: system_routes uses parse_str_param/parse_int_param."""

    def test_audit_endpoint_limit_clamped(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path, require_token=False)
        try:
            # Negative limit should be clamped, not crash
            resp = client.get("/api/system/audit?limit=-5")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["ok"] is True

            # Huge limit clamped to 1000
            resp2 = client.get("/api/system/audit?limit=99999")
            assert resp2.status_code == 200
            data2 = resp2.get_json()
            assert data2["filters"]["limit"] <= 1000
        finally:
            _restore_server(old)

    def test_logs_export_tail_clamped(self, tmp_path):
        client, audit_db, old = _setup_server(tmp_path, require_token=False)
        try:
            # Non-numeric tail should use default, not crash
            resp = client.post(
                "/api/system/logs/export",
                json={"tail": "not_a_number", "format": "json"},
            )
            # May return 404 if no log file, but should NOT return 500
            assert resp.status_code in (200, 404)
        finally:
            _restore_server(old)
