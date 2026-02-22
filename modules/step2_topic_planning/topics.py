#!/usr/bin/env python3
"""Step2 topic planning logic module."""

import re
from typing import Dict, List, Any

from .ai_client import AIClient, SYSTEM_PROMPT_VLOG, PROMPT_TOPICS


def build_material_summary(materials: Dict[str, Any]) -> str:
    lines: List[str] = []
    for vid_hash, vdata in materials.items():
        an = vdata.get("analysis", {})
        meta = an.get("metadata", {})
        tech = an.get("local_analysis", {}).get("technical", {})
        scene = an.get("local_analysis", {}).get("scene", {})
        objs = an.get("local_analysis", {}).get("objects", {})
        fname = vdata.get("filename", vid_hash[:8])
        dur = meta.get("duration", "?")
        res = tech.get("resolution", "?")
        desc = (scene.get("description") or "")[:50]
        mood = scene.get("mood", "")
        obj_list = ", ".join((objs.get("detected_objects") or [])[:5])
        sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
        sem_hint = " ".join(
            str(sem.get(k, "")) for k in ("setting", "activity", "time_of_day", "weather", "narrative_role")
            if sem.get(k)
        )
        lines.append(
            f"- {fname} | {dur}s | {res} | 场景:{desc} | 情绪:{mood} | 物体:{obj_list} | 语义:{sem_hint}"
        )
    return "\n".join(lines) if lines else "（未找到素材信息）"



def material_scene_hint(vdata: Dict[str, Any]) -> str:
    sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
    if sem:
        setting = sem.get("setting")
        activity = sem.get("activity")
        mood = sem.get("mood")
        return " ".join(x for x in [setting, activity, mood] if x)
    local_scene = (
        vdata.get("analysis", {})
        .get("local_analysis", {})
        .get("scene", {})
    )
    return str(local_scene.get("description", "") or "")



def generate_topics_from_materials(materials: Dict[str, Any]) -> List[Dict[str, Any]]:
    clusters: Dict[Any, Dict[str, Any]] = {}
    all_files: List[str] = []
    hooks: List[str] = []
    for _, vdata in materials.items():
        fname = str(vdata.get("filename", "") or "").strip()
        if fname:
            all_files.append(fname)

        sem = vdata.get("semantic", {}) if isinstance(vdata.get("semantic", {}), dict) else {}
        setting = str(sem.get("setting", "") or "").strip() or "旅行场景"
        activity = str(sem.get("activity", "") or "").strip() or "探索"
        mood = str(sem.get("mood", "") or "").strip() or "真实"
        key = (setting, activity)
        info = clusters.setdefault(key, {"count": 0, "mood": {}, "files": []})
        info["count"] += 1
        info["mood"][mood] = info["mood"].get(mood, 0) + 1
        if fname:
            info["files"].append(fname)

        hint = material_scene_hint(vdata)
        if hint:
            hooks.append(hint)

    ranked = sorted(
        clusters.items(),
        key=lambda kv: kv[1]["count"],
        reverse=True,
    )
    topics: List[Dict[str, Any]] = []
    for idx, ((setting, activity), info) in enumerate(ranked[:5], 1):
        mood = max(info["mood"], key=info["mood"].get) if info["mood"] else "真实"
        picks = info.get("files", [])[:5]
        hook = hooks[idx - 1][:24] if idx - 1 < len(hooks) else f"{setting}里最抓人的一幕"
        topics.append({
            "index": idx,
            "title": f"{setting}·{activity}高光合集",
            "theme": f"围绕“{setting}+{activity}”展开，突出真实现场感和人物情绪起伏。",
            "emotion": mood,
            "duration": "60秒" if info["count"] >= 3 else "45秒",
            "hook": hook,
            "recommended_assets": picks,
        })

    while len(topics) < 5:
        idx = len(topics) + 1
        fallback_files = all_files[(idx - 1) * 2:(idx - 1) * 2 + 4] or all_files[:4]
        topics.append({
            "index": idx,
            "title": f"旅行素材混剪方案{idx}",
            "theme": "基于现有素材做节奏剪辑，突出前3秒钩子和结尾记忆点。",
            "emotion": "真实",
            "duration": "45秒",
            "hook": "先看这一秒，再决定要不要划走",
            "recommended_assets": fallback_files[:5],
        })

    return topics[:5]



def extract_topics_from_response(ai_response: str, materials: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = str(ai_response or "")
    topics = []
    pattern = re.compile(
        r"\*\*选题\s*(\d+)\s*[：:]\s*[《\"]?([^》\"\n]+)[》\"]?\*\*([\s\S]*?)(?=\n\*\*选题\s*\d+\s*[：:]|$)"
    )
    for m in pattern.finditer(text):
        idx = int(m.group(1))
        title = (m.group(2) or "").strip()
        body = (m.group(3) or "").strip()
        theme = ""
        duration = "60秒"
        emotion = ""
        hook = ""
        recommended_assets: List[str] = []
        for line in body.splitlines():
            clean = line.strip().lstrip("-").strip()
            if clean.startswith("主题"):
                theme = clean.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif "建议时长" in clean:
                duration = clean.split("：", 1)[-1].split(":", 1)[-1].strip() or duration
            elif "核心情绪" in clean:
                emotion = clean.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif "开场钩子" in clean:
                hook = clean.split("：", 1)[-1].split(":", 1)[-1].strip().strip("“”\"")
            elif "推荐素材" in clean:
                raw_assets = clean.split("：", 1)[-1].split(":", 1)[-1].strip()
                recommended_assets = [
                    x.strip()
                    for x in re.split(r"[，,、;/\|]+", raw_assets)
                    if x.strip()
                ][:6]
        topics.append({
            "index": idx,
            "title": title or f"选题{idx}",
            "theme": theme or "内容向",
            "emotion": emotion or "真实",
            "duration": duration,
            "hook": hook,
            "recommended_assets": recommended_assets,
        })
    if topics:
        return topics[:5]
    return generate_topics_from_materials(materials)



def plan_topics(materials: Dict[str, Any], workflow_config: Dict[str, Any]) -> Dict[str, Any]:
    summary = build_material_summary(materials)
    ai = AIClient.from_workflow_config(workflow_config)
    prompt = PROMPT_TOPICS.format(material_summary=summary)
    response = ai.chat([{"role": "user", "content": prompt}], system=SYSTEM_PROMPT_VLOG)
    topics = extract_topics_from_response(response, materials)
    return {
        "summary": summary,
        "ai_response": response,
        "topics": topics,
    }



def build_topics_review_markdown(ai_response: str, summary: str, topics: List[Dict[str, Any]]) -> str:
    topics_md = []
    for t in topics:
        rec_assets = t.get("recommended_assets") or []
        rec_line = ", ".join(rec_assets[:5]) if isinstance(rec_assets, list) and rec_assets else "自动按语义匹配"
        topics_md.append(
            f"**选题{t.get('index', '?')}：《{t.get('title', '')}》**\n"
            f"- 主题：{t.get('theme', '')}\n"
            f"- 建议时长：{t.get('duration', '')}\n"
            f"- 核心情绪：{t.get('emotion', '')}\n"
            f"- 推荐素材：{rec_line}\n"
            f"- 开场钩子：「{t.get('hook', '')}」\n"
        )
    topics_block = "\n".join(topics_md).strip() or ai_response

    return f"""# 第2步审核：选题建议

> **操作说明**：
> 1. 查看下方 AI 生成的选题建议
> 2. 在 `chosen_topic` 填写您选择的序号（1-5）
> 3. 在 `user_ideas` 填写您的补充想法和创作方向
> 4. 将 `approved: false` 改为 `approved: true`
> 5. 重新运行 `python workflow.py run --project <项目路径>` 继续

```yaml
approved: false
chosen_topic: 1
user_ideas: ""
target_duration: 60
```

## AI 生成的选题建议

{topics_block}

---

## 素材概览（供参考）

{summary}
"""
