"""Standalone publish copy preparation for multi-platform release."""

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional
import argparse
import json
import re


@dataclass(frozen=True)
class PublishPromptProfile:
    """Prompt templates and limits for one target platform."""

    platform_id: str
    name: str
    title_prompt: str
    body_prompt: str
    keywords_prompt: str
    max_keywords: int = 10


DEFAULT_PROMPT_PROFILES: Dict[str, PublishPromptProfile] = {
    "youtube": PublishPromptProfile(
        platform_id="youtube",
        name="YouTube",
        title_prompt=(
            "你是 YouTube 增长运营。按 {platform_content_type_hint} 生成 1 条标题。\n"
            "要求：60 字内，突出核心价值和关键词。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是 YouTube 内容编辑。按 {platform_content_type_hint} 写简介。\n"
            "要求：2-3 句摘要 + 行动引导，120-280 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是 YouTube SEO 编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "覆盖主题、地点、动作、风格。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=12,
    ),
    "tiktok": PublishPromptProfile(
        platform_id="tiktok",
        name="TikTok",
        title_prompt=(
            "你是 TikTok 运营。按 {platform_content_type_hint} 写 1 条标题。\n"
            "要求：20 字内，强钩子、口语化。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是 TikTok 文案编辑。按 {platform_content_type_hint} 写正文。\n"
            "要求：2-4 行短句，节奏快，结尾带互动。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是 TikTok 标签编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "优先话题词、场景词。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=8,
    ),
    "xiaohongshu": PublishPromptProfile(
        platform_id="xiaohongshu",
        name="小红书",
        title_prompt=(
            "你是小红书运营。按 {platform_content_type_hint} 写标题。\n"
            "要求：结果导向、25 字内。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是小红书编辑。按 {platform_content_type_hint} 写正文。\n"
            "要求：开场亮点/过程/结论结构，120-260 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是小红书关键词编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "兼顾搜索词和场景词。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=10,
    ),
    "ixigua": PublishPromptProfile(
        platform_id="ixigua",
        name="西瓜视频",
        title_prompt=(
            "你是西瓜视频运营。按 {platform_content_type_hint} 写标题。\n"
            "要求：突出信息增量，30 字内。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是西瓜视频编辑。按 {platform_content_type_hint} 写简介。\n"
            "要求：先摘要，再给亮点目录，120-220 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是西瓜视频关键词编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=10,
    ),
    "douyin": PublishPromptProfile(
        platform_id="douyin",
        name="抖音",
        title_prompt=(
            "你是抖音运营。按 {platform_content_type_hint} 写标题。\n"
            "要求：15-25 字，前 8 字有吸引力。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是抖音文案编辑。按 {platform_content_type_hint} 写正文。\n"
            "要求：短句 + 互动引导 + 结尾行动。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是抖音标签编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=8,
    ),
    "wechat_channels": PublishPromptProfile(
        platform_id="wechat_channels",
        name="微信号（视频号）",
        title_prompt=(
            "你是微信视频号运营。按 {platform_content_type_hint} 写标题。\n"
            "要求：20 字左右，清楚表达价值。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是微信视频号编辑。按 {platform_content_type_hint} 写发布文案。\n"
            "要求：简洁、可转发，80-180 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是微信视频号关键词编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=8,
    ),
    "wechat_mp": PublishPromptProfile(
        platform_id="wechat_mp",
        name="微信公众号",
        title_prompt=(
            "你是微信公众号编辑。按 {platform_content_type_hint} 写标题。\n"
            "要求：信息完整，可读性强，28 字内。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是微信公众号编辑。按 {platform_content_type_hint} 写导语+正文摘要。\n"
            "要求：结构化表达，180-420 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是微信公众号关键词编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=12,
    ),
    "instagram": PublishPromptProfile(
        platform_id="instagram",
        name="Instagram",
        title_prompt=(
            "You are an Instagram editor. Write 1 headline for {platform_content_type_hint}.\n"
            "Keep it catchy and concise.\nScript:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        body_prompt=(
            "You are an Instagram caption editor. Write a caption for {platform_content_type_hint}.\n"
            "Use short lines with CTA, 80-180 words.\nScript:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        keywords_prompt=(
            "Output Instagram keywords/hashtags for {platform_content_type_hint}, comma separated.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        max_keywords=12,
    ),
    "twitter": PublishPromptProfile(
        platform_id="twitter",
        name="Twitter/X",
        title_prompt=(
            "You are a Twitter/X editor. Write a concise hook for {platform_content_type_hint}.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        body_prompt=(
            "Write a Twitter/X post for {platform_content_type_hint}.\n"
            "Keep it punchy with 1 CTA.\nScript:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        keywords_prompt=(
            "Output Twitter/X keywords/hashtags for {platform_content_type_hint}, comma separated.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        max_keywords=10,
    ),
    "threads": PublishPromptProfile(
        platform_id="threads",
        name="Threads",
        title_prompt=(
            "You are a Threads editor. Write 1 short opener for {platform_content_type_hint}.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        body_prompt=(
            "Write a Threads post for {platform_content_type_hint} with a conversational tone.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        keywords_prompt=(
            "Output Threads keywords for {platform_content_type_hint}, comma separated.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        max_keywords=10,
    ),
    "facebook": PublishPromptProfile(
        platform_id="facebook",
        name="Facebook",
        title_prompt=(
            "You are a Facebook editor. Write 1 headline for {platform_content_type_hint}.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        body_prompt=(
            "Write a Facebook post for {platform_content_type_hint} with a clear CTA.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        keywords_prompt=(
            "Output Facebook keywords for {platform_content_type_hint}, comma separated.\n"
            "Script:\n{script}\n\nVoiceover:\n{voiceover}\n"
        ),
        max_keywords=10,
    ),
    "blog": PublishPromptProfile(
        platform_id="blog",
        name="Blog",
        title_prompt=(
            "你是博客编辑。按 {platform_content_type_hint} 写 1 条标题。\n"
            "要求：信息明确、可检索。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是博客编辑。按 {platform_content_type_hint} 写正文摘要。\n"
            "要求：可扩展为 Markdown 和 HTML，180-420 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是博客 SEO 编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=14,
    ),
    "bilibili": PublishPromptProfile(
        platform_id="bilibili",
        name="B站",
        title_prompt=(
            "你是 B站运营。按 {platform_content_type_hint} 写标题。\n"
            "要求：核心看点前置，32 字内。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        body_prompt=(
            "你是 B站简介编辑。按 {platform_content_type_hint} 写简介。\n"
            "要求：分点列出亮点，120-260 字。\n脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        keywords_prompt=(
            "你是 B站关键词编辑。按 {platform_content_type_hint} 输出关键词，逗号分隔。\n"
            "脚本：\n{script}\n\n口播：\n{voiceover}\n"
        ),
        max_keywords=12,
    ),
}


PLATFORM_ALIASES: Dict[str, str] = {
    "yt": "youtube",
    "youtube视频": "youtube",
    "youtube_video": "youtube",
    "xhs": "xiaohongshu",
    "小红书": "xiaohongshu",
    "西瓜": "ixigua",
    "西瓜视频": "ixigua",
    "xigua": "ixigua",
    "抖音": "douyin",
    "微信号": "wechat_channels",
    "视频号": "wechat_channels",
    "wechat_video": "wechat_channels",
    "wechat_short": "wechat_channels",
    "wechat_channels": "wechat_channels",
    "公众号": "wechat_mp",
    "微信公众号": "wechat_mp",
    "thread": "threads",
    "x": "twitter",
    "twitter_x": "twitter",
    "b站": "bilibili",
    "b站视频": "bilibili",
    "哔哩哔哩": "bilibili",
    "博客": "blog",
}

GENERIC_PROFILE = PublishPromptProfile(
    platform_id="generic",
    name="Generic",
    title_prompt=(
        "根据脚本和口播按 {platform_content_type_hint} 写 1 条发布标题。\n"
        "要求：突出看点，简洁自然。\n"
        "视频脚本：\n{script}\n\n口播文案：\n{voiceover}\n"
    ),
    body_prompt=(
        "根据脚本和口播按 {platform_content_type_hint} 写 1 段发布正文。\n"
        "要求：先摘要再补充价值点，结构清楚。\n"
        "视频脚本：\n{script}\n\n口播文案：\n{voiceover}\n"
    ),
    keywords_prompt=(
        "根据脚本和口播按 {platform_content_type_hint} 输出关键词。\n"
        "要求：仅输出关键词，用逗号分隔。\n"
        "视频脚本：\n{script}\n\n口播文案：\n{voiceover}\n"
    ),
    max_keywords=10,
)

TextGenerator = Callable[[str, str, str], str]
_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9][A-Za-z0-9_+-]{1,}")


def normalize_platform_id(platform_id: str) -> str:
    """Normalize platform id and resolve known aliases."""
    key = str(platform_id or "").strip().lower()
    if not key:
        return "generic"
    return PLATFORM_ALIASES.get(key, key)


def _coerce_profile(platform_id: str, raw) -> PublishPromptProfile:
    if isinstance(raw, PublishPromptProfile):
        if raw.platform_id == platform_id:
            return raw
        return PublishPromptProfile(
            platform_id=platform_id,
            name=raw.name,
            title_prompt=raw.title_prompt,
            body_prompt=raw.body_prompt,
            keywords_prompt=raw.keywords_prompt,
            max_keywords=raw.max_keywords,
        )
    if not isinstance(raw, dict):
        raise ValueError("profile must be dict or PublishPromptProfile")

    pid = normalize_platform_id(platform_id or raw.get("platform_id"))
    if not pid:
        raise ValueError("platform_id is required")
    max_keywords = raw.get("max_keywords", 10)
    try:
        max_keywords = max(int(max_keywords), 1)
    except Exception:
        max_keywords = 10
    return PublishPromptProfile(
        platform_id=pid,
        name=str(raw.get("name") or pid).strip() or pid,
        title_prompt=str(raw.get("title_prompt") or "").strip(),
        body_prompt=str(raw.get("body_prompt") or "").strip(),
        keywords_prompt=str(raw.get("keywords_prompt") or "").strip(),
        max_keywords=max_keywords,
    )


def resolve_publish_profiles(
    profile_overrides: Optional[Dict[str, Dict]] = None,
) -> Dict[str, PublishPromptProfile]:
    """Merge built-in profiles with user overrides."""
    profiles: Dict[str, PublishPromptProfile] = dict(DEFAULT_PROMPT_PROFILES)
    profiles["generic"] = GENERIC_PROFILE
    if not isinstance(profile_overrides, dict):
        return profiles

    for key, value in profile_overrides.items():
        pid = normalize_platform_id(key)
        if not pid and isinstance(value, dict):
            pid = normalize_platform_id(value.get("platform_id"))
        if not pid:
            continue
        try:
            profile = _coerce_profile(pid, value)
        except Exception:
            continue
        if not profile.title_prompt:
            profile = PublishPromptProfile(
                platform_id=profile.platform_id,
                name=profile.name,
                title_prompt=profiles.get(pid, GENERIC_PROFILE).title_prompt,
                body_prompt=profile.body_prompt or profiles.get(pid, GENERIC_PROFILE).body_prompt,
                keywords_prompt=profile.keywords_prompt or profiles.get(pid, GENERIC_PROFILE).keywords_prompt,
                max_keywords=profile.max_keywords,
            )
        elif not profile.body_prompt or not profile.keywords_prompt:
            base = profiles.get(pid, GENERIC_PROFILE)
            profile = PublishPromptProfile(
                platform_id=profile.platform_id,
                name=profile.name,
                title_prompt=profile.title_prompt,
                body_prompt=profile.body_prompt or base.body_prompt,
                keywords_prompt=profile.keywords_prompt or base.keywords_prompt,
                max_keywords=profile.max_keywords,
            )
        profiles[pid] = profile
    return profiles


def list_publish_profiles(
    profile_overrides: Optional[Dict[str, Dict]] = None,
) -> List[Dict]:
    """List merged platform profiles."""
    return [asdict(p) for p in resolve_publish_profiles(profile_overrides).values()]


def build_publish_prompts(
    script_text: str,
    voiceover_text: str,
    platform_id: str,
    platform_content_type: str = "video_post",
    profile_overrides: Optional[Dict[str, Dict]] = None,
) -> Dict[str, str]:
    """Build per-field prompts for one platform."""
    profiles = resolve_publish_profiles(profile_overrides)
    pid = normalize_platform_id(platform_id)
    profile = profiles.get(pid, profiles["generic"])
    content_type = str(platform_content_type or "video_post").strip().lower()
    if content_type not in {"video_post", "article_post"}:
        content_type = "video_post"
    payload = {
        "platform_id": pid,
        "platform_name": profile.name,
        "script": str(script_text or "").strip(),
        "voiceover": str(voiceover_text or "").strip(),
        "platform_content_type_hint": "视频发布文案" if content_type == "video_post" else "文章发布文案",
    }
    return {
        "title": profile.title_prompt.format(**payload),
        "body": profile.body_prompt.format(**payload),
        "keywords": profile.keywords_prompt.format(**payload),
    }


def _split_sentences(text: str) -> List[str]:
    text = str(text or "").strip()
    if not text:
        return []
    parts = re.split(r"[。！？!?\n\r]+", text)
    return [p.strip() for p in parts if p and p.strip()]


def _extract_keywords(text: str, max_keywords: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        token = match.group(0).strip()
        key = token.lower()
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(token)
        if len(out) >= max_keywords:
            break
    return out


def _fallback_publish_copy(
    script_text: str,
    voiceover_text: str,
    profile: PublishPromptProfile,
    platform_content_type: str = "video_post",
) -> Dict[str, object]:
    lead_pool = _split_sentences(voiceover_text) + _split_sentences(script_text)
    lead = lead_pool[0] if lead_pool else "旅行视频更新"
    title = lead[:32]

    summary_parts = _split_sentences(voiceover_text)[:2]
    if not summary_parts:
        summary_parts = _split_sentences(script_text)[:2]
    if not summary_parts:
        summary_parts = ["本期视频记录了从出发到落地的关键过程。"]
    body = "。".join(summary_parts).strip("。")
    if str(platform_content_type or "video_post").strip().lower() == "article_post":
        body = f"{body}。\n\n正文建议：可按“背景-方法-案例-总结”四段展开。"
    else:
        body = f"{body}。\n\n如果这条内容对你有帮助，欢迎收藏并留言你的问题。"

    keyword_source = f"{script_text}\n{voiceover_text}"
    keywords = _extract_keywords(keyword_source, max_keywords=profile.max_keywords)
    if not keywords:
        keywords = ["旅行", "vlog", "视频创作"][: profile.max_keywords]
    return {
        "title": title,
        "body": body,
        "keywords": keywords,
        "source": "fallback",
    }


def prepare_publish_package(
    script_text: str,
    voiceover_text: str,
    platform_ids: Iterable[str],
    platform_content_type: str = "video_post",
    profile_overrides: Optional[Dict[str, Dict]] = None,
    text_generator: Optional[TextGenerator] = None,
) -> Dict[str, object]:
    """
    Generate per-platform title/body/keywords package.

    `text_generator(platform_id, field, prompt)` is optional. When absent, deterministic
    fallback generation is used so the module stays standalone.
    """
    profiles = resolve_publish_profiles(profile_overrides)
    content_type = str(platform_content_type or "video_post").strip().lower()
    if content_type not in {"video_post", "article_post"}:
        content_type = "video_post"
    normalized: List[str] = []
    seen = set()
    for raw in platform_ids or []:
        pid = normalize_platform_id(raw)
        if pid in seen:
            continue
        seen.add(pid)
        normalized.append(pid)
    if not normalized:
        normalized = ["generic"]

    results: List[Dict[str, object]] = []
    for pid in normalized:
        profile = profiles.get(pid, profiles["generic"])
        prompts = build_publish_prompts(
            script_text=script_text,
            voiceover_text=voiceover_text,
            platform_id=pid,
            platform_content_type=content_type,
            profile_overrides=profile_overrides,
        )
        if text_generator is None:
            generated = _fallback_publish_copy(
                script_text,
                voiceover_text,
                profile,
                platform_content_type=content_type,
            )
        else:
            generated_keywords = text_generator(pid, "keywords", prompts["keywords"])
            keyword_items = [item.strip() for item in re.split(r"[,\n，]+", generated_keywords) if item.strip()]
            generated = {
                "title": text_generator(pid, "title", prompts["title"]).strip(),
                "body": text_generator(pid, "body", prompts["body"]).strip(),
                "keywords": keyword_items[: profile.max_keywords],
                "source": "generator",
            }

        results.append(
            {
                "platform_id": pid,
                "platform_name": profile.name,
                "platform_content_type": content_type,
                "max_keywords": profile.max_keywords,
                "prompts": prompts,
                "content": generated,
            }
        )
    return {
        "script_chars": len(str(script_text or "")),
        "voiceover_chars": len(str(voiceover_text or "")),
        "platform_content_type": content_type,
        "platform_results": results,
    }


def load_profile_overrides(profile_path: str) -> Dict[str, Dict]:
    """Load profile overrides from a JSON file."""
    path = Path(profile_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        out: Dict[str, Dict] = {}
        for item in payload:
            if not isinstance(item, dict):
                continue
            pid = normalize_platform_id(item.get("platform_id"))
            if not pid:
                continue
            out[pid] = item
        return out
    if isinstance(payload, dict):
        return payload
    raise ValueError("profile JSON must be object or list")


def _read_text_arg(raw_value: str) -> str:
    text = str(raw_value or "").strip()
    maybe_path = Path(text)
    if maybe_path.exists() and maybe_path.is_file():
        return maybe_path.read_text(encoding="utf-8")
    return text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-platform publish copy preparation.")
    parser.add_argument("--script", required=True, help="Script text or path to script file.")
    parser.add_argument("--voiceover", default="", help="Voiceover text or path to voiceover file.")
    parser.add_argument(
        "--platform",
        action="append",
        default=[],
        help="Target platform id, repeatable. Example: --platform youtube --platform tiktok",
    )
    parser.add_argument("--profiles", help="Path to profile overrides JSON file.")
    parser.add_argument("--output", help="Optional output JSON path.")
    args = parser.parse_args(argv)

    overrides = load_profile_overrides(args.profiles) if args.profiles else None
    payload = prepare_publish_package(
        script_text=_read_text_arg(args.script),
        voiceover_text=_read_text_arg(args.voiceover),
        platform_ids=args.platform,
        profile_overrides=overrides,
        text_generator=None,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
