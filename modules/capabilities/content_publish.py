"""Cross-platform content publishing capability (dry-run + live run)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import hashlib
import json
import mimetypes
import re
import random
import socket
from urllib import error as urlerror
from urllib import request as urlrequest
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


# ── 内部错误分类 ──────────────────────────────────────────────────────

_ERROR_CLASSES = frozenset({
    "config_missing",
    "auth_failed",
    "params_invalid",
    "platform_rejected",
    "quota_exceeded",
    "network_error",
    "unknown",
})


class _PublishHTTPError(RuntimeError):
    """携带 http_status 的发布异常，供 _classify_error 提取状态码。"""

    def __init__(self, message: str, *, http_status: int = 0):
        super().__init__(message)
        self.http_status = http_status


def _classify_error(exc: Exception, *, http_status: int = 0) -> dict:
    """内部分类，返回 {error_class, retryable, action_hint}。"""
    code = getattr(exc, "http_status", 0) or http_status

    # HTTP 状态码分类
    if code in (401, 403):
        return {"error_class": "auth_failed", "retryable": False,
                "action_hint": "刷新 access_token 后重试"}
    if code == 429:
        return {"error_class": "quota_exceeded", "retryable": True,
                "action_hint": "等待配额恢复后重试"}
    if code in (400, 422):
        return {"error_class": "platform_rejected", "retryable": False,
                "action_hint": "检查内容参数后重试"}
    if code >= 500:
        return {"error_class": "network_error", "retryable": True,
                "action_hint": "可直接重试"}

    # 异常类型分类 —— 同时检查 exc 本身和 __cause__ 链
    all_exc = [exc]
    if getattr(exc, "__cause__", None) is not None:
        all_exc.append(exc.__cause__)

    msg = str(exc).lower()
    for e in all_exc:
        if isinstance(e, (TimeoutError, socket.timeout)):
            return {"error_class": "network_error", "retryable": True,
                    "action_hint": "检查网络后重试"}
    for e in all_exc:
        if isinstance(e, (ConnectionError, OSError)):
            emsg = str(e).lower()
            if any(kw in emsg for kw in ("refused", "reset", "broken pipe", "dns", "name resolution")):
                return {"error_class": "network_error", "retryable": True,
                        "action_hint": "检查网络后重试"}
    for e in all_exc:
        if isinstance(e, urlerror.URLError):
            reason = str(getattr(e, "reason", "")).lower()
            if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
                return {"error_class": "network_error", "retryable": True,
                        "action_hint": "检查网络后重试"}
            if any(kw in reason for kw in ("refused", "reset", "dns", "name resolution", "timed out")):
                return {"error_class": "network_error", "retryable": True,
                        "action_hint": "检查网络后重试"}

    # 消息关键词检测（超时）
    if any(kw in msg for kw in ("超时", "timed out", "timeout")):
        return {"error_class": "network_error", "retryable": True,
                "action_hint": "检查网络后重试"}

    # ValueError 语义分类
    for e in all_exc:
        if isinstance(e, ValueError):
            emsg = str(e).lower()
            if any(kw in emsg for kw in ("缺少", "不能为空", "missing", "未配置")):
                return {"error_class": "config_missing", "retryable": False,
                        "action_hint": "补充配置后重试"}
            return {"error_class": "params_invalid", "retryable": False,
                    "action_hint": "修正参数后重试"}

    # RuntimeError 含 "未配置" 也归为 config_missing
    if isinstance(exc, RuntimeError) and any(kw in msg for kw in ("未配置", "缺少")):
        return {"error_class": "config_missing", "retryable": False,
                "action_hint": "补充配置后重试"}

    return {"error_class": "unknown", "retryable": False,
            "action_hint": "检查详情后决定"}


def _validate_youtube_params(step: Dict[str, Any], connector: Dict[str, Any]) -> None:
    """YouTube 发布参数校验（pre-flight），校验失败抛 ValueError。"""
    token = str(connector.get("access_token", "") or connector.get("token", "") or "").strip()
    if not token:
        raise ValueError("youtube_api 缺少 access_token/token")

    content = step.get("content", {}) if isinstance(step.get("content"), dict) else {}
    title = str(content.get("title") or "").strip()
    if title and len(title) > 100:
        raise ValueError(f"YouTube title 不能超过 100 字符（当前 {len(title)}）")
    description = str(content.get("description") or "").strip()
    if description and len(description) > 5000:
        raise ValueError(f"YouTube description 不能超过 5000 字符（当前 {len(description)}）")

    privacy = str(connector.get("privacy_status", "") or "").strip().lower()
    if privacy and privacy not in ("private", "public", "unlisted"):
        raise ValueError(f"YouTube privacy_status 不合法: {privacy}，应为 private/public/unlisted")

    cat = str(connector.get("category_id", "") or "").strip()
    if cat and not cat.isdigit():
        raise ValueError(f"YouTube category_id 应为数字字符串: {cat}")


def _read_error_body(exc: urlerror.HTTPError) -> str:
    """安全读取 HTTPError body。"""
    try:
        return exc.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _build_publish_idempotency_digest(plan: Dict[str, Any], connectors: Dict[str, Any], dry_run: bool) -> str:
    """基于发布请求摘要的稳定 hash，用作幂等 key。"""
    steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
    parts: list = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        content = step.get("content", {}) if isinstance(step.get("content"), dict) else {}
        media_urls = content.get("media_urls") if isinstance(content.get("media_urls"), list) else []
        # 纳入 media_urls 中的本地文件路径以降低同标题误撞风险
        media_sig = ",".join(str(u) for u in media_urls)
        pid = str(step.get("platform_id", ""))
        conn = connectors.get(pid, {}) if isinstance(connectors, dict) else {}
        conn_kind = str(conn.get("kind", "") if isinstance(conn, dict) else "")
        parts.append("|".join([
            pid,
            str(content.get("title", "")),
            str(content.get("description", ""))[:200],
            media_sig,
            conn_kind,
        ]))
    raw = f"dry_run={dry_run}||" + "||".join(sorted(parts))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _safe_slug(text: str, fallback: str = "post") -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", str(text or "").strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or fallback


def _trim_text(text: Any, max_len: int = 360) -> str:
    s = str(text or "").strip()
    if len(s) <= max_len:
        return s
    return f"{s[: max_len - 3]}..."


def _resolve_platform_connector(platform_id: str, connectors: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    data = connectors if isinstance(connectors, dict) else {}
    pid = str(platform_id or "").strip().lower()
    if not pid:
        return {}
    direct = data.get(pid)
    if isinstance(direct, dict):
        return dict(direct)
    alias = data.get("default")
    if isinstance(alias, dict):
        return dict(alias)
    return {}


def _build_webhook_headers(connector: Dict[str, Any]) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    custom_headers = connector.get("headers")
    if isinstance(custom_headers, dict):
        for key, value in custom_headers.items():
            k = str(key or "").strip()
            if not k:
                continue
            headers[k] = str(value or "").strip()
    token = str(connector.get("token", "") or "").strip()
    if token and "authorization" not in {k.lower() for k in headers.keys()}:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _extract_response_field(payload: Any, keys: List[str]) -> str:
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        data = payload.get("data")
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
    return ""


def _publish_via_webhook(
    *,
    step: Dict[str, Any],
    connector: Dict[str, Any],
    session: Dict[str, Any],
    timeout_s: float = 25.0,
) -> Dict[str, Any]:
    endpoint = str(connector.get("endpoint", "") or "").strip()
    if not endpoint:
        raise ValueError("connector.endpoint 不能为空")
    method = str(connector.get("method", "POST") or "POST").strip().upper() or "POST"
    body = {
        "platform_id": step.get("platform_id"),
        "platform_name": step.get("platform_name"),
        "content_type": step.get("content_type"),
        "content": step.get("content", {}),
        "session": {
            "session_id": str(session.get("session_id", "") or ""),
            "authenticated": bool(session.get("authenticated", False)),
        },
        "requested_at": datetime.now().isoformat(timespec="seconds"),
    }
    payload_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=payload_bytes,
        method=method,
        headers=_build_webhook_headers(connector),
    )
    timeout_final = max(float(connector.get("timeout_s", timeout_s) or timeout_s), 1.0)
    try:
        with urlrequest.urlopen(req, timeout=timeout_final) as resp:
            status_code = int(getattr(resp, "status", 200) or 200)
            resp_body = resp.read().decode("utf-8", errors="ignore")
    except urlerror.HTTPError as exc:
        tail = ""
        try:
            tail = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            tail = ""
        raise RuntimeError(f"发布连接器返回 HTTP {exc.code}: {_trim_text(tail or exc.reason, 180)}") from exc
    except Exception as exc:
        raise RuntimeError(f"发布连接器调用失败: {exc}") from exc

    parsed: Any = {}
    if resp_body.strip():
        try:
            parsed = json.loads(resp_body)
        except Exception:
            parsed = {"raw": _trim_text(resp_body, 600)}
    post_id = _extract_response_field(parsed, ["post_id", "id", "publish_id"]) or f"{step.get('platform_id')}_{uuid.uuid4().hex[:10]}"
    post_url = _extract_response_field(parsed, ["url", "post_url", "link"])
    return {
        "post_id": post_id,
        "post_url": post_url,
        "connector_response": parsed,
        "connector_http_status": status_code,
        "connector_endpoint": endpoint,
    }


def _normalize_connector_kind(connector: Dict[str, Any]) -> str:
    return str(connector.get("kind", "webhook") or "webhook").strip().lower() or "webhook"


def _connector_is_ready(platform_id: str, connector: Dict[str, Any]) -> bool:
    pid = str(platform_id or "").strip().lower()
    if pid == "blog":
        return True
    if not isinstance(connector, dict) or not connector:
        return False
    kind = _normalize_connector_kind(connector)
    if kind == "youtube_api" and pid == "youtube":
        token = str(connector.get("access_token", "") or connector.get("token", "") or "").strip()
        return bool(token)
    return bool(str(connector.get("endpoint", "") or "").strip())


def _youtube_upload_source(step: Dict[str, Any], connector: Dict[str, Any]) -> Path:
    content = step.get("content", {}) if isinstance(step.get("content"), dict) else {}
    source = str(connector.get("media_file", "") or "").strip()
    if not source:
        source = str(content.get("video_file", "") or "").strip()
    if not source:
        media_urls = content.get("media_urls", []) if isinstance(content.get("media_urls"), list) else []
        if media_urls:
            source = str(media_urls[0] or "").strip()
    if not source:
        raise ValueError("youtube_api 需要 media_file 或 content.media_urls[0] 指向本地视频文件")
    if source.startswith("http://") or source.startswith("https://"):
        raise ValueError("youtube_api 当前仅支持本地视频文件上传，不支持 URL 直传")
    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise ValueError(f"youtube_api 视频文件不存在: {path}")
    return path


def _youtube_metadata(step: Dict[str, Any], connector: Dict[str, Any]) -> Dict[str, Any]:
    content = step.get("content", {}) if isinstance(step.get("content"), dict) else {}
    privacy_status = str(connector.get("privacy_status", "private") or "private").strip().lower()
    if privacy_status not in {"private", "public", "unlisted"}:
        privacy_status = "private"
    category_id = str(connector.get("category_id", "22") or "22").strip() or "22"
    publish_at = str(connector.get("publish_at", "") or "").strip()

    snippet = {
        "title": str(content.get("title") or "Untitled").strip() or "Untitled",
        "description": str(content.get("description") or "").strip(),
        "categoryId": category_id,
        "tags": content.get("keywords", []) if isinstance(content.get("keywords"), list) else [],
    }
    status: Dict[str, Any] = {"privacyStatus": privacy_status}
    if publish_at:
        status["publishAt"] = publish_at
    return {"snippet": snippet, "status": status}


def _youtube_auth_headers(connector: Dict[str, Any], content_type: str = "application/json; charset=UTF-8") -> Dict[str, str]:
    token = str(connector.get("access_token", "") or connector.get("token", "") or "").strip()
    if not token:
        raise ValueError("youtube_api 缺少 access_token/token")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
    }
    custom_headers = connector.get("headers")
    if isinstance(custom_headers, dict):
        for key, value in custom_headers.items():
            k = str(key or "").strip()
            if not k:
                continue
            headers[k] = str(value or "").strip()
    return headers


def _publish_youtube_via_api(
    *,
    step: Dict[str, Any],
    connector: Dict[str, Any],
    timeout_s: float = 120.0,
) -> Dict[str, Any]:
    # Pre-flight 校验（失败抛 ValueError → _classify_error 归为 config_missing/params_invalid）
    _validate_youtube_params(step, connector)
    source = _youtube_upload_source(step, connector)
    meta = _youtube_metadata(step, connector)
    size = int(source.stat().st_size)
    media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    notify_subscribers = str(bool(connector.get("notify_subscribers", False))).lower()

    init_url = (
        "https://www.googleapis.com/upload/youtube/v3/videos"
        f"?uploadType=resumable&part=snippet,status&notifySubscribers={notify_subscribers}"
    )
    init_headers = _youtube_auth_headers(connector)
    init_headers["X-Upload-Content-Type"] = media_type
    init_headers["X-Upload-Content-Length"] = str(size)
    init_body = json.dumps(meta, ensure_ascii=False).encode("utf-8")
    req_init = urlrequest.Request(init_url, data=init_body, method="POST", headers=init_headers)

    timeout_final = max(float(connector.get("timeout_s", timeout_s) or timeout_s), 3.0)
    try:
        with urlrequest.urlopen(req_init, timeout=timeout_final) as init_resp:
            upload_url = str(init_resp.headers.get("Location", "") or "").strip()
    except urlerror.HTTPError as exc:
        tail = _read_error_body(exc)
        raise _PublishHTTPError(
            f"YouTube 初始化上传失败 HTTP {exc.code}: {_trim_text(tail or exc.reason, 220)}",
            http_status=exc.code,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise _PublishHTTPError(f"YouTube 初始化上传超时: {exc}", http_status=0) from exc
    except Exception as exc:
        raise RuntimeError(f"YouTube 初始化上传失败: {exc}") from exc

    if not upload_url:
        raise RuntimeError("YouTube 未返回可用的上传地址（Location）")

    upload_headers = _youtube_auth_headers(connector, content_type=media_type)
    upload_headers["Content-Length"] = str(size)
    data = source.read_bytes()
    req_upload = urlrequest.Request(upload_url, data=data, method="PUT", headers=upload_headers)
    try:
        with urlrequest.urlopen(req_upload, timeout=max(timeout_final, 30.0)) as upload_resp:
            status_code = int(getattr(upload_resp, "status", 200) or 200)
            body = upload_resp.read().decode("utf-8", errors="ignore")
    except urlerror.HTTPError as exc:
        tail = _read_error_body(exc)
        raise _PublishHTTPError(
            f"YouTube 上传失败 HTTP {exc.code}: {_trim_text(tail or exc.reason, 220)}",
            http_status=exc.code,
        ) from exc
    except (TimeoutError, socket.timeout) as exc:
        raise _PublishHTTPError(f"YouTube 上传超时: {exc}", http_status=0) from exc
    except Exception as exc:
        raise RuntimeError(f"YouTube 上传失败: {exc}") from exc

    parsed: Any = {}
    if body.strip():
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": _trim_text(body, 800)}
    video_id = _extract_response_field(parsed, ["id", "video_id"])
    post_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
    return {
        "post_id": video_id or f"youtube_{uuid.uuid4().hex[:10]}",
        "post_url": post_url,
        "connector_response": parsed,
        "connector_http_status": status_code,
        "connector_endpoint": "youtube_api",
        "artifacts": {
            "uploaded_file": str(source.resolve()),
            "size_bytes": size,
            "media_type": media_type,
        },
    }


def _publish_blog_artifacts(step: Dict[str, Any], *, output_root: str = "") -> Dict[str, Any]:
    root = Path(str(output_root or "").strip()).expanduser()
    if str(root).strip() == "":
        root = Path.cwd() / "output" / "content_publish"
    blog_dir = root / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)

    content = step.get("content", {}) if isinstance(step.get("content"), dict) else {}
    title = str(content.get("title") or "Untitled").strip() or "Untitled"
    slug = _safe_slug(title, fallback=f"post-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = blog_dir / f"{stamp}_{slug}.md"
    html_path = blog_dir / f"{stamp}_{slug}.html"

    markdown = str(content.get("markdown_frontmatter") or content.get("article_markdown") or "").strip()
    html = str(content.get("html") or content.get("article_html") or "").strip()
    if not markdown:
        markdown = f"---\ntitle: {title}\n---\n\n{str(content.get('description') or '').strip()}".strip()
    if not html:
        safe_body = str(content.get("description") or "").replace("\n", "<br>")
        html = f"<article><h1>{title}</h1><p>{safe_body}</p></article>"

    md_path.write_text(markdown, encoding="utf-8")
    html_path.write_text(html, encoding="utf-8")
    return {
        "post_id": f"blog_{stamp}_{slug}",
        "post_url": str(md_path.resolve()),
        "artifacts": {
            "markdown_path": str(md_path.resolve()),
            "html_path": str(html_path.resolve()),
        },
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
    connectors: Optional[Dict[str, Any]] = None,
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
    connector_map = connectors if isinstance(connectors, dict) else {}

    steps: List[Dict[str, Any]] = []
    warnings: List[str] = []
    for pid in platforms:
        profile = PUBLISH_PLATFORMS[pid]
        supported = profile.supports_video if content_type == "video_post" else profile.supports_article
        connector = _resolve_platform_connector(pid, connector_map)
        connector_kind = _normalize_connector_kind(connector) if connector else ""
        connector_ready = _connector_is_ready(pid, connector)
        state = "planned" if supported else "blocked"
        reason = "" if supported else f"{profile.name} 暂不支持 {content_type}"
        if not supported:
            warnings.append(reason)
        if supported and (not dry_run) and pid != "blog" and not connector_ready:
            state = "blocked"
            reason = f"{profile.name} 未配置发布连接器（connector）"
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
                "connector_kind": connector_kind or ("builtin_blog" if pid == "blog" else ""),
                "connector_required": (not dry_run) and pid != "blog",
                "connector_ready": bool(connector_ready),
            }
        )

    requires_auth = not bool(dry_run)
    session_expired = _is_session_expired(session_info) if session_info else True
    auth_ready = bool(session_info.get("authenticated", False)) and not session_expired
    status = "planned"
    if requires_auth and not auth_ready:
        status = "waiting_auth"
    elif steps and all(str(s.get("state", "")).lower() == "blocked" for s in steps):
        status = "blocked"

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
        "connectors_configured": sorted(
            [pid for pid in platforms if _connector_is_ready(pid, _resolve_platform_connector(pid, connector_map))]
        ),
    }


def run_publish_plan(
    *,
    plan: Dict[str, Any],
    session: Optional[Dict[str, Any]] = None,
    dry_run: bool = False,
    rerun_failed_only: bool = False,
    random_seed: Optional[int] = 7,
    connectors: Optional[Dict[str, Any]] = None,
    output_root: str = "",
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
    connector_map = connectors if isinstance(connectors, dict) else {}
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

        if current_state == "blocked":
            blocked += 1
            out_steps.append({**item, "run_state": "blocked"})
            continue

        if run_dry:
            out_steps.append({**item, "state": "planned", "run_state": "dry_run"})
            continue

        min_delay, max_delay = exec_strategy.get("random_delay_ms", [800, 2600])
        min_delay = max(int(min_delay), 0)
        max_delay = max(int(max_delay), min_delay)
        sampled_delay = rng.randint(min_delay, max_delay)
        run_logs.append(f"{item.get('platform_id')} -> delay {sampled_delay}ms")

        platform_id = str(item.get("platform_id", "") or "").strip().lower()
        if not platform_id:
            failed += 1
            out_steps.append({**item, "state": "failed", "run_state": "failed", "error": "缺少 platform_id"})
            continue

        try:
            publish_result: Dict[str, Any] = {}
            if platform_id == "blog":
                publish_result = _publish_blog_artifacts(item, output_root=output_root)
            else:
                connector = _resolve_platform_connector(platform_id, connector_map)
                if not connector:
                    raise RuntimeError(f"{platform_id} 未配置发布连接器（connector）")
                kind = _normalize_connector_kind(connector)
                if kind == "webhook":
                    publish_result = _publish_via_webhook(step=item, connector=connector, session=sess)
                elif kind == "youtube_api" and platform_id == "youtube":
                    publish_result = _publish_youtube_via_api(step=item, connector=connector)
                else:
                    raise RuntimeError(f"暂不支持 connector.kind={kind}")

            posted += 1
            out_steps.append(
                {
                    **item,
                    "state": "posted",
                    "run_state": "posted",
                    "post_id": str(publish_result.get("post_id") or f"{platform_id}_{uuid.uuid4().hex[:10]}"),
                    "post_url": str(publish_result.get("post_url", "") or ""),
                    "posted_at": datetime.now().isoformat(timespec="seconds"),
                    "connector": {
                        "kind": (
                            "builtin_blog"
                            if platform_id == "blog"
                            else ("youtube_api" if str(publish_result.get("connector_endpoint", "") or "") == "youtube_api" else "webhook")
                        ),
                        "endpoint": str(publish_result.get("connector_endpoint", "") or ""),
                    },
                    "artifacts": publish_result.get("artifacts", {}),
                    "connector_response": publish_result.get("connector_response", {}),
                }
            )
        except Exception as exc:
            failed += 1
            classification = _classify_error(exc)
            out_steps.append(
                {
                    **item,
                    "state": "failed",
                    "run_state": "failed",
                    "error": str(exc),
                    "error_detail": classification,
                }
            )
            continue

    if waiting_auth:
        overall_status = "waiting_auth"
    elif failed > 0:
        overall_status = "failed"
    elif blocked > 0 and posted == 0:
        overall_status = "blocked"
    else:
        overall_status = "posted" if not run_dry else "planned"

    # recovery_hint：可追踪、可恢复建议
    error_classes_seen: list = []
    has_config_or_blocked = blocked > 0
    if failed > 0:
        error_classes_seen = list({
            step.get("error_detail", {}).get("error_class", "unknown")
            for step in out_steps
            if step.get("run_state") == "failed" and isinstance(step.get("error_detail"), dict)
        })
    if failed > 0 and blocked > 0:
        rerun_scope = "failed_and_blocked"
    elif failed > 0:
        rerun_scope = "failed_only"
    elif blocked > 0:
        rerun_scope = "fix_config_then_rerun"
    else:
        rerun_scope = "none"

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
        "connectors_configured": sorted(
            [pid for pid in src_plan.get("platform_ids", []) if _connector_is_ready(str(pid), _resolve_platform_connector(str(pid), connector_map))]
        ),
        "summary": {
            "total": len(out_steps),
            "posted": posted,
            "failed": failed,
            "blocked": blocked,
        },
        "steps": out_steps,
        "logs": run_logs,
        "recovery_hint": {
            "can_rerun": failed > 0 or blocked > 0,
            "rerun_endpoint": "/api/capabilities/content_publish/rerun",
            "rerun_scope": rerun_scope,
            "error_classes": sorted(error_classes_seen) if error_classes_seen else [],
        },
    }
