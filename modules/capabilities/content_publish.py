"""Cross-platform content publishing capability (dry-run + live run)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional
import random
import uuid


@dataclass(frozen=True)
class PublishPlatformProfile:
    platform_id: str
    name: str
    region: str
    supports_video: bool
    supports_article: bool
    supports_keywords: bool = True
    notes: str = ""


PUBLISH_PLATFORMS: Dict[str, PublishPlatformProfile] = {
    # Domestic
    "xiaohongshu": PublishPlatformProfile("xiaohongshu", "小红书", "domestic", True, True, True, "图文/短视频均可发布"),
    "ixigua": PublishPlatformProfile("ixigua", "西瓜视频", "domestic", True, False, True, "以视频发布为主"),
    "douyin": PublishPlatformProfile("douyin", "抖音", "domestic", True, False, True, "短视频为主"),
    "wechat_channels": PublishPlatformProfile("wechat_channels", "微信号（视频号）", "domestic", True, False, True, "统一按视频号处理"),
    "wechat_mp": PublishPlatformProfile("wechat_mp", "微信公众号", "domestic", True, True, True, "支持文章与视频"),
    # Global
    "youtube": PublishPlatformProfile("youtube", "YouTube", "global", True, False, True, "长视频/Shorts"),
    "instagram": PublishPlatformProfile("instagram", "Instagram", "global", True, True, True, "Reels/帖子"),
    "twitter": PublishPlatformProfile("twitter", "Twitter/X", "global", True, True, True, "支持文本+媒体"),
    "threads": PublishPlatformProfile("threads", "Threads", "global", True, True, True, "短文本社媒"),
    "facebook": PublishPlatformProfile("facebook", "Facebook", "global", True, True, True, "帖子/视频"),
    # Custom
    "blog": PublishPlatformProfile("blog", "Blog", "custom", True, True, True, "输出 Markdown+Frontmatter 与 HTML"),
}

PLATFORM_ALIASES: Dict[str, str] = {
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
    "微信公众号": "wechat_mp",
    "公众号": "wechat_mp",
    "wechat_mp": "wechat_mp",
    "yt": "youtube",
    "thread": "threads",
    "x": "twitter",
    "twitter_x": "twitter",
    "facebook_page": "facebook",
    "博客": "blog",
}

DEFAULT_HUMANIZATION = {
    "simulate_human_behavior": True,
    "random_delay_ms": [800, 2600],
    "input_jitter": True,
    "action_throttle_per_minute": 18,
    "risk_protection": True,
}

DEFAULT_AUTOMATION = {
    "browser_connector": "managed_browser",
    "session_hosting": True,
    "cookie_auto_refresh": False,
    "auth_refresh_mode": "qrcode",
}


def normalize_platform_id(platform_id: str) -> str:
    key = str(platform_id or "").strip().lower()
    if not key:
        return ""
    return PLATFORM_ALIASES.get(key, key)


def normalize_platforms(platform_ids: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in platform_ids or []:
        pid = normalize_platform_id(str(raw or ""))
        if not pid or pid in seen:
            continue
        if pid not in PUBLISH_PLATFORMS:
            continue
        seen.add(pid)
        out.append(pid)
    return out


def list_publish_platforms() -> Dict[str, Any]:
    all_items = [asdict(x) for x in PUBLISH_PLATFORMS.values()]
    return {
        "platforms": all_items,
        "groups": {
            "domestic": [x["platform_id"] for x in all_items if x["region"] == "domestic"],
            "global": [x["platform_id"] for x in all_items if x["region"] == "global"],
            "custom": [x["platform_id"] for x in all_items if x["region"] == "custom"],
        },
        "aliases": dict(PLATFORM_ALIASES),
    }


def bootstrap_publish_session(
    *,
    actor_id: str = "",
    session_id: str = "",
    authenticated: bool = False,
    expires_in_minutes: int = 120,
) -> Dict[str, Any]:
    now = datetime.now()
    session_key = str(session_id or uuid.uuid4().hex[:16]).strip()
    minutes = max(int(expires_in_minutes or 120), 1)
    expires_at = now + timedelta(minutes=minutes)
    return {
        "session_id": session_key,
        "actor_id": str(actor_id or "").strip(),
        "authenticated": bool(authenticated),
        "state": "ready" if authenticated else "waiting_auth",
        "auth_required": not bool(authenticated),
        "auth_hint": "扫码续登" if not authenticated else "",
        "created_at": now.isoformat(timespec="seconds"),
        "expires_at": expires_at.isoformat(timespec="seconds"),
        "connector": dict(DEFAULT_AUTOMATION),
    }


def _is_session_expired(session: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    if not isinstance(session, dict):
        return True
    expires_at = str(session.get("expires_at", "") or "").strip()
    if not expires_at:
        return True
    try:
        dt = datetime.fromisoformat(expires_at)
    except Exception:
        return True
    clock = now or datetime.now()
    return clock >= dt


def _normalize_content_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    title = str(src.get("title") or "").strip()
    description = str(src.get("description") or src.get("body") or "").strip()
    keywords_raw = src.get("keywords", [])
    if isinstance(keywords_raw, str):
        keywords = [x.strip() for x in keywords_raw.replace("，", ",").split(",") if x.strip()]
    elif isinstance(keywords_raw, list):
        keywords = [str(x).strip() for x in keywords_raw if str(x).strip()]
    else:
        keywords = []

    media_urls_raw = src.get("media_urls", [])
    media_urls = []
    if isinstance(media_urls_raw, list):
        media_urls = [str(x).strip() for x in media_urls_raw if str(x).strip()]

    article_markdown = str(src.get("article_markdown") or "").strip()
    article_html = str(src.get("article_html") or "").strip()

    return {
        "title": title,
        "description": description,
        "keywords": keywords,
        "media_urls": media_urls,
        "article_markdown": article_markdown,
        "article_html": article_html,
    }


def _ensure_blog_dual_format(content: Dict[str, Any]) -> Dict[str, str]:
    title = str(content.get("title") or "Untitled").strip() or "Untitled"
    body = str(content.get("description") or "").strip()
    markdown = str(content.get("article_markdown") or "").strip()
    html = str(content.get("article_html") or "").strip()

    if not markdown:
        markdown = f"---\ntitle: {title}\n---\n\n{body}".strip()
    elif not markdown.startswith("---"):
        markdown = f"---\ntitle: {title}\n---\n\n{markdown}".strip()

    if not html:
        safe_body = body.replace("\n", "<br>")
        html = f"<article><h1>{title}</h1><p>{safe_body}</p></article>"

    return {
        "markdown_frontmatter": markdown,
        "html": html,
    }


def build_publish_plan(
    *,
    content: Dict[str, Any],
    platform_ids: Iterable[str],
    platform_content_type: str = "video_post",
    dry_run: bool = True,
    session: Optional[Dict[str, Any]] = None,
    humanization: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    platforms = normalize_platforms(platform_ids)
    if not platforms:
        platforms = ["blog"]

    content_type = str(platform_content_type or "video_post").strip().lower()
    if content_type not in {"video_post", "article_post"}:
        content_type = "video_post"

    normalized_content = _normalize_content_payload(content)
    session_info = session if isinstance(session, dict) else {}
    strategy = dict(DEFAULT_HUMANIZATION)
    if isinstance(humanization, dict):
        strategy.update(humanization)

    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for pid in platforms:
        profile = PUBLISH_PLATFORMS[pid]
        supported = profile.supports_video if content_type == "video_post" else profile.supports_article
        state = "planned" if supported else "blocked"
        reason = "" if supported else f"{profile.name} 暂不支持 {content_type}"
        if not supported:
            warnings.append(reason)

        content_out = {
            "title": normalized_content["title"],
            "description": normalized_content["description"],
            "keywords": normalized_content["keywords"],
            "media_urls": normalized_content["media_urls"],
        }
        if pid == "blog":
            content_out.update(_ensure_blog_dual_format(normalized_content))

        steps.append(
            {
                "platform_id": pid,
                "platform_name": profile.name,
                "region": profile.region,
                "state": state,
                "reason": reason,
                "content_type": content_type,
                "content": content_out,
                "auth_required": not dry_run,
            }
        )

    requires_auth = not bool(dry_run)
    session_expired = _is_session_expired(session_info) if session_info else True
    auth_ready = bool(session_info.get("authenticated", False)) and not session_expired
    status = "planned"
    if requires_auth and not auth_ready:
        status = "waiting_auth"

    return {
        "status": status,
        "dry_run": bool(dry_run),
        "content_type": content_type,
        "platform_ids": platforms,
        "session": {
            "session_id": str(session_info.get("session_id", "") or ""),
            "authenticated": bool(session_info.get("authenticated", False)),
            "expired": bool(session_expired),
            "expires_at": str(session_info.get("expires_at", "") or ""),
        },
        "strategy": strategy,
        "steps": steps,
        "warnings": warnings,
    }


def run_publish_plan(
    *,
    plan: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    rerun_failed_only: bool = False,
    random_seed: Optional[int] = 7,
) -> Dict[str, Any]:
    src_plan = plan if isinstance(plan, dict) else {}
    steps = src_plan.get("steps", []) if isinstance(src_plan.get("steps"), list) else []
    strategy = src_plan.get("strategy", {}) if isinstance(src_plan.get("strategy"), dict) else {}
    exec_strategy = dict(DEFAULT_HUMANIZATION)
    exec_strategy.update(strategy)

    run_dry = bool(dry_run or src_plan.get("dry_run", False))
    sess = session if isinstance(session, dict) else {}
    session_expired = _is_session_expired(sess)
    auth_ready = bool(sess.get("authenticated", False)) and not session_expired

    rng = random.Random(int(random_seed if random_seed is not None else 7))
    run_logs: List[str] = []
    out_steps: List[Dict[str, Any]] = []
    posted = 0
    failed = 0
    blocked = 0

    waiting_auth = (not run_dry) and (not auth_ready)
    overall_status = "running" if not waiting_auth else "waiting_auth"

    for item in steps:
        if not isinstance(item, dict):
            continue
        current_state = str(item.get("state", "planned") or "planned")
        if rerun_failed_only and current_state not in {"failed", "blocked"}:
            out_steps.append({**item, "state": current_state, "run_state": "skipped"})
            continue

        if current_state == "blocked":
            blocked += 1
            out_steps.append({**item, "run_state": "blocked"})
            continue

        if waiting_auth:
            blocked += 1
            out_steps.append(
                {
                    **item,
                    "state": "waiting_auth",
                    "run_state": "waiting_auth",
                    "reason": "会话过期或未认证，需要扫码续登",
                    "auth_action": "qrcode_required",
                }
            )
            continue

        if run_dry:
            out_steps.append({**item, "state": "planned", "run_state": "dry_run"})
            continue

        min_delay, max_delay = exec_strategy.get("random_delay_ms", [800, 2600])
        min_delay = max(int(min_delay), 0)
        max_delay = max(int(max_delay), min_delay)
        sampled_delay = rng.randint(min_delay, max_delay)
        run_logs.append(f"{item.get('platform_id')} -> delay {sampled_delay}ms")

        # deterministic publish simulation
        if str(item.get("platform_id", "")) == "threads" and str(item.get("content", {}).get("title", "")) == "":
            failed += 1
            out_steps.append(
                {
                    **item,
                    "state": "failed",
                    "run_state": "failed",
                    "error": "threads 发布要求 title 非空",
                }
            )
            continue

        posted += 1
        out_steps.append(
            {
                **item,
                "state": "posted",
                "run_state": "posted",
                "post_id": f"{item.get('platform_id')}_{uuid.uuid4().hex[:10]}",
                "posted_at": datetime.now().isoformat(timespec="seconds"),
            }
        )

    if waiting_auth:
        overall_status = "waiting_auth"
    elif failed > 0:
        overall_status = "failed"
    elif blocked > 0 and posted == 0:
        overall_status = "blocked"
    else:
        overall_status = "posted" if not run_dry else "planned"

    return {
        "status": overall_status,
        "dry_run": run_dry,
        "session": {
            "session_id": str(sess.get("session_id", "") or ""),
            "authenticated": bool(sess.get("authenticated", False)),
            "expired": bool(session_expired),
            "expires_at": str(sess.get("expires_at", "") or ""),
        },
        "strategy": exec_strategy,
        "summary": {
            "total": len(out_steps),
            "posted": posted,
            "failed": failed,
            "blocked": blocked,
        },
        "steps": out_steps,
        "logs": run_logs,
    }
