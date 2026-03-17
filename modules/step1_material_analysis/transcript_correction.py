#!/usr/bin/env python3
"""
ASR 转录校正模块 — Transcript Correction

对 Whisper 等 ASR 引擎输出的转录文本进行智能校正：
- LLM 校正（有 API key 时）：同音字/近音字、专名、标点断句
- 规则校正（无 API key 时降级）：常见同音字替换表 + 正则修复

输入格式（与 transcribe.py 输出一致）：
{
  "transcript": "完整转录文本",
  "segments": [
    {"start": 0.0, "end": 3.5, "text": "你好", "confidence": 0.92},
    ...
  ],
  "language": "zh",
  ...
}

输出格式：
{
  "corrected_transcript": "校正后完整文本",
  "corrected_segments": [
    {"start": 0.0, "end": 3.5, "text": "原文", "corrected_text": "校正后", "changed": true},
    ...
  ],
  "corrections_count": 3,
  "method": "llm/gpt-4o-mini" | "rules",
  "custom_terms": ["温哥华", ...],
}
"""

import logging
import re
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── 常见 ASR 同音字/近音字替换规则 ──────────────────────────────

# 格式: (错误模式 regex, 正确替换)
# 聚焦旅行/生活 vlog 场景的高频错别字
_ZH_COMMON_FIXES: List[tuple] = [
    # 地名
    (r"温个华", "温哥华"),
    (r"加拿大[的得]", "加拿大的"),
    (r"多伦多[的得]", "多伦多的"),
    (r"卡尔加[力里]", "卡尔加里"),
    (r"蒙特利[耳尔]", "蒙特利尔"),
    (r"渥太[花华]", "渥太华"),
    # 生活/vlog 高频
    (r"我[门们]", "我们"),
    (r"因[唯为]", "因为"),
    (r"已[今经]", "已经"),
    (r"这[各个]", "这个"),
    (r"那[各个]", "那个"),
    (r"非[长常]", "非常"),
    (r"知[到道]", "知道"),
    (r"时[候后]", "时候"),
    (r"然[后候]", "然后"),
    (r"可[已以]", "可以"),
    (r"所[已以]", "所以"),
    (r"生[活括]", "生活"),
    (r"感[决觉]", "感觉"),
    (r"[做作]一[各个]", "做一个"),
    # 汽车/购物场景
    (r"二手[成车]", "二手车"),
    (r"[价加驾]照", "驾照"),
    (r"保[显险]", "保险"),
    # 标点修复
    (r'([。！？])([^"\u201c\u201d\'])', r'\1 \2'),  # 句末标点后加空格
]

# 英文常见 ASR 错误
_EN_COMMON_FIXES: List[tuple] = [
    (r"\bwanna\b", "want to"),
    (r"\bgonna\b", "going to"),
    (r"\bgotta\b", "got to"),
    (r"\bkinda\b", "kind of"),
]


def _apply_rule_fixes(text: str, language: str = "zh") -> str:
    """应用规则替换修复常见 ASR 错误"""
    fixes = _ZH_COMMON_FIXES if language.startswith("zh") else _EN_COMMON_FIXES
    result = text
    for pattern, replacement in fixes:
        result = re.sub(pattern, replacement, result)
    return result


def _correct_with_llm(
    segments: List[Dict],
    language: str,
    ai_chat: Callable,
    custom_terms: Optional[List[str]] = None,
    batch_size: int = 10,
) -> List[Dict]:
    """使用 LLM 批量校正转录片段"""
    corrected = []
    terms_hint = ""
    if custom_terms:
        terms_hint = f"\n专有名词（必须保留原样）: {', '.join(custom_terms)}"

    lang_name = "中文" if language.startswith("zh") else "English"

    for i in range(0, len(segments), batch_size):
        batch = segments[i : i + batch_size]
        lines = []
        for idx, seg in enumerate(batch):
            lines.append(f"{idx + 1}. {seg.get('text', '')}")

        prompt = (
            f"以下是 ASR 语音识别输出的{lang_name}文本，可能有同音字错误、专名错误或断句不当。\n"
            f"请逐行校正，只修改确定有误的部分，保持原意和语序不变。\n"
            f"输出格式：每行一条，编号对应，只输出校正后文本（无需解释）。{terms_hint}\n\n"
            + "\n".join(lines)
        )

        try:
            response = ai_chat(
                messages=[{"role": "user", "content": prompt}],
                system="你是 ASR 转录校正助手。只修正明显的语音识别错误（同音字/专名/标点），不改变原意。",
            )
            # 解析 LLM 返回的逐行结果
            resp_lines = [
                ln.strip() for ln in str(response or "").strip().split("\n") if ln.strip()
            ]
            # 去掉行首编号
            cleaned = []
            for ln in resp_lines:
                m = re.match(r"^\d+[\.\)、]\s*", ln)
                cleaned.append(ln[m.end():] if m else ln)

            for j, seg in enumerate(batch):
                new_text = cleaned[j] if j < len(cleaned) else seg.get("text", "")
                changed = new_text != seg.get("text", "")
                corrected.append({
                    **seg,
                    "corrected_text": new_text,
                    "changed": changed,
                })
        except Exception as exc:
            logger.warning("LLM 校正批次 %d 失败，降级为规则校正: %s", i, exc)
            for seg in batch:
                fixed = _apply_rule_fixes(seg.get("text", ""), language)
                corrected.append({
                    **seg,
                    "corrected_text": fixed,
                    "changed": fixed != seg.get("text", ""),
                })

    return corrected


def correct_transcripts(
    transcription: Dict[str, Any],
    *,
    ai_client=None,
    custom_terms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    校正转录结果。

    Args:
        transcription: transcribe_video() 的输出
        ai_client: AIClient 实例（可选，None 时用规则校正）
        custom_terms: 自定义专名列表（如品牌名、地名），校正时保留原样

    Returns:
        校正结果字典
    """
    segments = transcription.get("segments", [])
    language = transcription.get("language", "zh") or "zh"
    method = "rules"

    if not segments:
        return {
            "corrected_transcript": transcription.get("transcript", ""),
            "corrected_segments": [],
            "corrections_count": 0,
            "method": "no_segments",
            "custom_terms": custom_terms or [],
        }

    corrected_segments = []

    # 尝试 LLM 校正
    if ai_client is not None:
        try:
            corrected_segments = _correct_with_llm(
                segments, language, ai_client.chat, custom_terms
            )
            method = f"llm/{ai_client.model}"
        except Exception as exc:
            logger.warning("LLM 校正整体失败，降级为规则校正: %s", exc)
            corrected_segments = []

    # 规则校正（降级 / 无 LLM 时）
    if not corrected_segments:
        method = "rules"
        for seg in segments:
            fixed = _apply_rule_fixes(seg.get("text", ""), language)
            corrected_segments.append({
                **seg,
                "corrected_text": fixed,
                "changed": fixed != seg.get("text", ""),
            })

    corrections_count = sum(1 for s in corrected_segments if s.get("changed"))
    corrected_full = " ".join(
        s.get("corrected_text", s.get("text", "")) for s in corrected_segments
    )

    return {
        "corrected_transcript": corrected_full,
        "corrected_segments": corrected_segments,
        "corrections_count": corrections_count,
        "method": method,
        "custom_terms": custom_terms or [],
    }


# ── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="ASR 转录校正")
    parser.add_argument("input", help="transcribe_video 输出的 JSON 文件")
    parser.add_argument("--terms", nargs="*", default=[], help="自定义专名列表")
    parser.add_argument("-o", "--output", default=None, help="输出 JSON 路径")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    result = correct_transcripts(data, custom_terms=args.terms or None)

    out_path = args.output or args.input.replace(".json", "_corrected.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"校正完成: {result['corrections_count']} 处修改 (method={result['method']})")
    print(f"输出: {out_path}")
