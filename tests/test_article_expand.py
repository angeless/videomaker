from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.capabilities.article_expand import generate_article_expansion


def test_article_expand_fallback_structure_complete():
    result = generate_article_expansion(
        source_text="我们从选题、脚本、拍摄到剪辑做了一次完整复盘，重点是效率和可复制。",
        key_points=["选题策略", "拍摄流程", "剪辑提效", "发布复盘"],
        tone="professional",
        length_target=1400,
    )
    assert result["platform_id"] == "wechat_mp"
    assert len(result["title_candidates"]) >= 1
    assert len(result["sections"]) >= 3
    assert result["lead"].strip()
    assert result["cta"].strip()
    assert len(result["keywords"]) >= 1
    assert result["markdown"].startswith("# ")


def test_article_expand_custom_generator_is_used():
    calls = []

    def fake_gen(field: str, prompt: str) -> str:
        calls.append((field, prompt))
        if field == "titles":
            return "标题A\n标题B"
        if field == "lead":
            return "这是导语"
        if field == "body":
            return "第一段：内容1\n第二段：内容2"
        if field == "cta":
            return "欢迎留言"
        return ""

    result = generate_article_expansion(
        source_text="原始内容",
        key_points="点1,点2",
        text_generator=fake_gen,
        title_count=2,
    )
    assert len(calls) >= 4
    assert result["title_candidates"][0] == "标题A"
    assert result["lead"] == "这是导语"
    assert result["sections"][0]["heading"] == "第一段"
    assert result["cta"] == "欢迎留言"


def test_article_expand_api_inline_generation(tmp_path):
    fake_library_mod = types.ModuleType("modules.library.global_media_library")

    class _FakeGlobalMediaLibrary:
        def __init__(self, *args, **kwargs):
            self.db_path = ROOT / ".tmp_fake_library_article_api.db"

    fake_library_mod.GlobalMediaLibrary = _FakeGlobalMediaLibrary
    sys.modules.setdefault("modules.library.global_media_library", fake_library_mod)

    from modules.app_api import server  # noqa: E402

    old_project_dir = server._project_dir
    server._project_dir = tmp_path
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    client = server.app.test_client()
    try:
        resp = client.post(
            "/api/capabilities/article_expand/generate",
            json={
                "input_mode": "inline",
                "source_text": "这是公众号扩写 API 测试内容。",
                "key_points": ["痛点", "方法", "案例"],
                "tone": "professional",
                "length_target": 900,
            },
        )
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["ok"] is True
        result = payload["result"]
        assert result["platform_id"] == "wechat_mp"
        assert len(result["title_candidates"]) >= 1
    finally:
        server._project_dir = old_project_dir
