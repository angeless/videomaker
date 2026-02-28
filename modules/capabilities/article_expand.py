"""WeChat article expansion capability."""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional
import re


ArticleGenerator = Callable[[str, str], str]
_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{1,}")


def _split_points(raw: Iterable[str] | str) -> List[str]:
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        if out:
            return out
    text = str(raw or "").strip()
    if not text:
        return []
    parts = re.split(r"[\n\r;,，；。]+", text)
    return [p.strip() for p in parts if p and p.strip()]


def _split_sentences(text: str) -> List[str]:
    src = str(text or "").strip()
    if not src:
        return []
    parts = re.split(r"[。！？!?\n\r]+", src)
    return [p.strip() for p in parts if p and p.strip()]


def _extract_keywords(text: str, max_keywords: int = 12) -> List[str]:
    out: List[str] = []
    seen = set()
    for match in _TOKEN_PATTERN.finditer(str(text or "")):
        token = match.group(0).strip()
        if not token:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
        if len(out) >= max(max_keywords, 1):
            break
    return out


def _fallback_titles(seed_points: List[str], tone: str, count: int) -> List[str]:
    lead = seed_points[0] if seed_points else "这次内容"
    templates = [
        f"{lead}：一篇讲透的实操总结",
        f"从 0 到 1 做好 {lead}，这份清单够用了",
        f"{lead} 复盘：方法、踩坑与可复用模板",
        f"{lead}：给新手也能直接上手的版本",
        f"{lead} 的高效执行指南（{tone}）",
    ]
    dedup: List[str] = []
    seen = set()
    for title in templates:
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(title)
        if len(dedup) >= count:
            break
    return dedup


def _fallback_sections(source_text: str, seed_points: List[str], length_target: int) -> List[Dict[str, str]]:
    points = list(seed_points)
    if not points:
        points = _split_sentences(source_text)[:4]
    if not points:
        points = [
            "问题背景与目标定义",
            "执行路径与关键动作",
            "风险点与规避策略",
            "复盘与下一步计划",
        ]

    target_sections = 4 if length_target >= 1200 else 3
    points = points[: max(target_sections, 2)]

    sections: List[Dict[str, str]] = []
    for idx, point in enumerate(points, start=1):
        heading = point if len(point) <= 18 else point[:18]
        content = (
            f"第 {idx} 部分围绕“{point}”展开，先交代上下文，再给出可执行动作，"
            "最后补充验证标准与常见误区，确保读者可直接落地。"
        )
        sections.append({"heading": heading, "content": content})

    while len(sections) < target_sections:
        idx = len(sections) + 1
        sections.append(
            {
                "heading": f"补充章节 {idx}",
                "content": "补充案例、数据或对比，增强文章说服力与可复用性。",
            }
        )
    return sections


def _render_markdown(
    title: str,
    lead: str,
    sections: List[Dict[str, str]],
    cta: str,
    keywords: List[str],
) -> str:
    lines = [f"# {title}", "", lead, ""]
    for sec in sections:
        lines.append(f"## {sec.get('heading', '')}")
        lines.append(str(sec.get("content", "")).strip())
        lines.append("")
    lines.append("## 结尾")
    lines.append(cta)
    lines.append("")
    if keywords:
        lines.append("关键词：" + "、".join(keywords))
    return "\n".join(lines).strip()


def generate_article_expansion(
    source_text: str,
    key_points: Iterable[str] | str = (),
    *,
    tone: str = "professional",
    length_target: int = 1200,
    title_count: int = 5,
    text_generator: Optional[ArticleGenerator] = None,
) -> Dict[str, object]:
    """Generate WeChat article expansion package."""
    src = str(source_text or "").strip()
    points = _split_points(key_points)
    tone_text = str(tone or "professional").strip() or "professional"
    target = max(int(length_target or 1200), 300)
    title_n = max(min(int(title_count or 5), 10), 1)

    if text_generator is None:
        titles = _fallback_titles(points or _split_sentences(src), tone_text, title_n)
        lead_seed = points[0] if points else (_split_sentences(src)[0] if _split_sentences(src) else "这篇文章")
        lead = (
            f"这篇内容围绕“{lead_seed}”展开，目标是在有限篇幅内提供清晰结构、"
            "可执行步骤和复盘要点，帮助读者快速落地。"
        )
        sections = _fallback_sections(src, points, target)
        cta = "如果这篇内容对你有帮助，欢迎转发给同事，并留言你最想继续展开的问题。"
    else:
        seed = "\n".join(points[:8]) if points else src[:400]
        titles_raw = text_generator(
            "titles",
            (
                f"请基于以下素材生成 {title_n} 条微信公众号标题，每条单独一行，避免重复。\n"
                f"语气：{tone_text}\n素材：\n{seed}"
            ),
        )
        titles = [line.strip("-• ") for line in str(titles_raw or "").splitlines() if line.strip()]
        if not titles:
            titles = _fallback_titles(points or _split_sentences(src), tone_text, title_n)
        titles = titles[:title_n]

        lead = str(
            text_generator(
                "lead",
                f"基于以下素材写微信公众号导语（80-140字）。语气：{tone_text}\n素材：\n{seed}",
            )
            or ""
        ).strip()
        if not lead:
            lead = "本文将基于真实执行路径拆解核心方法，并给出可复制步骤。"

        body_text = str(
            text_generator(
                "body",
                (
                    "请输出 3-5 段结构化正文，每段格式为“标题：内容”。"
                    f"目标字数约 {target}。语气：{tone_text}\n素材：\n{seed}"
                ),
            )
            or ""
        ).strip()
        sections: List[Dict[str, str]] = []
        for line in body_text.splitlines():
            text = line.strip().strip("-•")
            if not text:
                continue
            if "：" in text:
                heading, content = text.split("：", 1)
            elif ":" in text:
                heading, content = text.split(":", 1)
            else:
                heading, content = f"段落 {len(sections) + 1}", text
            heading = heading.strip()[:24] or f"段落 {len(sections) + 1}"
            content = content.strip() or ""
            if content:
                sections.append({"heading": heading, "content": content})
        if not sections:
            sections = _fallback_sections(src, points, target)

        cta = str(
            text_generator(
                "cta",
                "写一段微信公众号文章结尾 CTA（20-50字），鼓励收藏/留言/转发。",
            )
            or ""
        ).strip()
        if not cta:
            cta = "欢迎收藏本文，并在评论区留下你的场景，我会继续补充对应案例。"

    keyword_source = "\n".join([src, "\n".join(points), "\n".join(titles), lead, cta])
    keywords = _extract_keywords(keyword_source, max_keywords=12)
    markdown = _render_markdown(
        title=titles[0] if titles else "公众号文章草稿",
        lead=lead,
        sections=sections,
        cta=cta,
        keywords=keywords,
    )

    return {
        "platform_id": "wechat_mp",
        "tone": tone_text,
        "length_target": target,
        "title_candidates": titles,
        "lead": lead,
        "sections": sections,
        "cta": cta,
        "keywords": keywords,
        "markdown": markdown,
    }
