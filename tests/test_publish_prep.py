from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.capabilities.publish_prep import (
    list_publish_profiles,
    load_profile_overrides,
    prepare_publish_package,
)


def test_prepare_publish_package_supports_multi_platform_prompt_overrides():
    script_text = "第一幕在海边出发，第二幕在老城日落收尾。"
    voiceover_text = "今天带你看一条可复制的旅行拍摄路线。"
    profile_overrides = {
        "youtube": {
            "name": "YouTube",
            "title_prompt": "YT-TITLE::{script}",
            "body_prompt": "YT-BODY::{voiceover}",
            "keywords_prompt": "YT-KW::{script}",
            "max_keywords": 5,
        },
        "tiktok": {
            "name": "TikTok",
            "title_prompt": "TT-TITLE::{voiceover}",
            "body_prompt": "TT-BODY::{script}",
            "keywords_prompt": "TT-KW::{voiceover}",
            "max_keywords": 4,
        },
    }
    calls = []

    def fake_generator(platform_id, field, prompt):
        calls.append((platform_id, field, prompt))
        if field == "keywords":
            return "旅行,拍摄,路线,海边,日落"
        return f"{platform_id}-{field}-generated"

    payload = prepare_publish_package(
        script_text=script_text,
        voiceover_text=voiceover_text,
        platform_ids=["youtube", "tiktok"],
        profile_overrides=profile_overrides,
        text_generator=fake_generator,
    )
    results = {item["platform_id"]: item for item in payload["platform_results"]}

    assert set(results.keys()) == {"youtube", "tiktok"}
    assert len(calls) == 6
    assert results["youtube"]["prompts"]["title"].startswith("YT-TITLE::")
    assert results["tiktok"]["prompts"]["title"].startswith("TT-TITLE::")
    assert results["youtube"]["content"]["title"] == "youtube-title-generated"
    assert results["tiktok"]["content"]["body"] == "tiktok-body-generated"
    assert results["youtube"]["content"]["keywords"] == ["旅行", "拍摄", "路线", "海边", "日落"]
    assert results["tiktok"]["content"]["keywords"] == ["旅行", "拍摄", "路线", "海边"]


def test_prepare_publish_package_fallback_generation():
    payload = prepare_publish_package(
        script_text="我们从机场出发，穿过山路，最后到达海边营地。",
        voiceover_text="这条线路适合第一次来的人，注意晚上的风会很大。",
        platform_ids=["小红书"],
    )
    result = payload["platform_results"][0]

    assert result["platform_id"] == "xiaohongshu"
    assert result["content"]["source"] == "fallback"
    assert result["content"]["title"]
    assert result["content"]["body"]
    assert 1 <= len(result["content"]["keywords"]) <= result["max_keywords"]


def test_list_publish_profiles_merges_custom_profile():
    profiles = list_publish_profiles(
        {
            "linkedin": {
                "platform_id": "linkedin",
                "name": "LinkedIn",
                "title_prompt": "LN-TITLE::{script}",
                "body_prompt": "LN-BODY::{voiceover}",
                "keywords_prompt": "LN-KW::{script}",
                "max_keywords": 6,
            }
        }
    )
    lookup = {item["platform_id"]: item for item in profiles}
    assert lookup["linkedin"]["name"] == "LinkedIn"
    assert lookup["linkedin"]["max_keywords"] == 6


def test_load_profile_overrides_supports_list_payload(tmp_path):
    profile_file = tmp_path / "profiles.json"
    profile_file.write_text(
        json.dumps(
            [
                {
                    "platform_id": "youtube",
                    "title_prompt": "A",
                    "body_prompt": "B",
                    "keywords_prompt": "C",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    loaded = load_profile_overrides(str(profile_file))
    assert "youtube" in loaded
    assert loaded["youtube"]["title_prompt"] == "A"


def test_prepare_publish_package_supports_extended_platform_matrix_and_aliases():
    payload = prepare_publish_package(
        script_text="这是一次旅行发布文案测试。",
        voiceover_text="包含海内外平台和博客输出。",
        platform_ids=["西瓜视频", "微信号", "thread", "facebook", "博客"],
    )
    ids = [item["platform_id"] for item in payload["platform_results"]]
    assert ids == ["ixigua", "wechat_channels", "threads", "facebook", "blog"]


def test_prepare_publish_package_supports_article_post_content_type():
    payload = prepare_publish_package(
        script_text="文章内容：从选题到发布完整流程。",
        voiceover_text="本篇是文章发布说明。",
        platform_ids=["wechat_mp"],
        platform_content_type="article_post",
    )
    result = payload["platform_results"][0]
    assert payload["platform_content_type"] == "article_post"
    assert result["platform_content_type"] == "article_post"
    assert result["platform_id"] == "wechat_mp"
    assert "文章" in result["prompts"]["title"] or "article" in result["prompts"]["title"].lower()
