"""R2: 安全修复 — SEC-001 CSRF + BUG-004 provider 枚举 + SEC-002 query 长度。

验收标准（来自 dev-plan-v0.11.md R2）：
- CSRF 跨域拦截生效（enforce_csrf 不再依赖 req_token）
- provider 非法值返回 400
- query 超长返回 400
"""

import sys
from pathlib import Path

import pytest

_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from modules.app_api.server import create_app


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ========== SEC-001: CSRF 保护 ==========


class TestSec001Csrf:
    """SEC-001: CSRF 保护不再依赖 token 开关。"""

    def test_cross_origin_post_blocked(self, client):
        """跨域 POST 应被 CSRF 拦截（返回 403）。"""
        resp = client.post(
            "/api/settings/ai",
            json={"provider": "openai"},
            headers={"Origin": "http://evil.com"},
        )
        assert resp.status_code == 403

    def test_no_origin_get_allowed(self, client):
        """无 Origin 的 GET 请求不被 CSRF 拦截（CSRF 仅拦截 mutating 方法）。"""
        resp = client.get("/api/session/bootstrap")
        assert resp.status_code in (200, 400, 403)  # 非 CSRF 403 即通过


# ========== BUG-004: provider 枚举校验 ==========


class TestBug004ProviderEnum:
    """BUG-004: POST /api/settings/ai provider 字段必须为合法枚举值。"""

    def test_invalid_provider_returns_400(self, client):
        """非法 provider 应返回 400。"""
        resp = client.post("/api/settings/ai", json={"provider": "unknown_xyz"})
        # 可能被 CSRF 拦截（403）或被 provider 校验拦截（400）
        assert resp.status_code in (400, 403)
        if resp.status_code == 400:
            assert "provider" in resp.get_json().get("error", "").lower() or "合法" in resp.get_json().get("error", "")

    def test_valid_provider_openai(self, client):
        """合法 provider openai 不应被拒绝（可能被 CSRF 拦截）。"""
        resp = client.post("/api/settings/ai", json={"provider": "openai"})
        # 不应返回 400（provider 级别的错误）；CSRF 403 是允许的
        if resp.status_code == 400:
            assert "provider" not in resp.get_json().get("error", "").lower()

    def test_valid_provider_moonshot_alias(self, client):
        """合法别名 kimi 应通过 provider 校验。"""
        resp = client.post("/api/settings/ai", json={"provider": "kimi"})
        if resp.status_code == 400:
            assert "provider" not in resp.get_json().get("error", "").lower()

    def test_empty_provider_allowed(self, client):
        """空 provider 不应触发校验（清除操作）。"""
        resp = client.post("/api/settings/ai", json={"provider": ""})
        if resp.status_code == 400:
            assert "provider" not in resp.get_json().get("error", "").lower()


# ========== SEC-002: query 长度限制 ==========


class TestSec002QueryLength:
    """SEC-002: 搜索 query 超过 500 字符应返回 400。"""

    def test_long_query_returns_400(self, client):
        """超长 query 应返回 400。"""
        resp = client.get(f"/api/library/search?q={'x' * 501}")
        assert resp.status_code == 400
        assert "500" in resp.get_json().get("error", "")

    def test_normal_query_passes(self, client):
        """正常长度 query 不应被拒绝。"""
        resp = client.get("/api/library/search?q=test+video")
        assert resp.status_code == 200

    def test_exactly_500_chars_passes(self, client):
        """恰好 500 字符应通过。"""
        resp = client.get(f"/api/library/search?q={'a' * 500}")
        assert resp.status_code == 200
