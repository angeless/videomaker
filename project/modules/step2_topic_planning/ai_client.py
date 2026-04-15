#!/usr/bin/env python3
"""
AI API 适配器
支持：Anthropic Claude / OpenAI 兼容（OpenAI、Moonshot/Kimi、Qwen、Gemini、MaxMini 等）/ 无 key 时输出模板
"""

import os
from typing import List, Dict, Optional


# ── 提示词（中文，旅游/生活 vlog 风格）─────────────────────────────────

SYSTEM_PROMPT_VLOG = (
    "你是一名专业的旅游/生活 vlog 创作顾问，擅长为抖音、小红书、Instagram 创作引人入胜的脚本。\n"
    "风格要求：真实、治愈、有温度，避免过度营销感。\n"
    "输出简洁直接，给出可执行的内容，不要过多解释。"
)

PROMPT_TOPICS = """## 素材清单

以下是我拍摄的原始视频素材：

{material_summary}

---

请根据以上素材，帮我策划 **5个** 适合发布在抖音/小红书的短视频选题。

每个选题请包含：
1. **标题**（吸引点击，20字以内）
2. **主题与角度**（2-3句话描述核心叙事视角）
3. **建议时长**（30秒/60秒/90秒）
4. **核心情绪**（治愈/励志/惊艳/有趣/共鸣）
5. **推荐素材**（从上方清单中列举最适合的3-5个文件名）
6. **开场钩子**（第一句旁白，能在3秒内抓住观众）

格式：
**选题1：《标题》**
- 主题：...
- 建议时长：60秒
- 核心情绪：治愈
- 推荐素材：文件1.mp4, 文件2.mp4
- 开场钩子：「...」"""

PROMPT_SCRIPT = """## 已选定选题

用户选择了第 {chosen_topic} 个选题，参考下方原始建议：

{topics_suggestions}

---

## 用户补充想法

{user_ideas}

---

## 可用素材清单

{material_summary}

---

## 任务：生成完整脚本

请生成一个 **{target_duration}秒** 的完整短视频脚本，输出**合法 JSON**，结构如下：

```json
{{
  "title": "视频标题",
  "total_duration": {target_duration},
  "clips": [
    {{
      "clip_index": 1,
      "video_id": "从素材清单中选择的文件名",
      "source_start": 0,
      "source_end": 8,
      "duration": 8,
      "scene_description": "镜头画面描述（给剪辑看）",
      "has_face": false,
      "camera_note": "运镜建议（缓推/航拍/固定）"
    }}
  ],
  "subtitles": [
    {{
      "clip_index": 1,
      "cn_text": "中文旁白（不超过20字）",
      "en_text": "English subtitle",
      "start_time": 0.0,
      "end_time": 8.0
    }}
  ],
  "bgm": {{"path": null, "style": "建议BGM风格"}},
  "narration": {{"path": null, "tone": "旁白语气"}}
}}
```

创作要求：
- 开头8秒必须有强钩子（震撼画面或金句）
- 每个镜头3-10秒，节奏紧凑
- 中文字幕每条不超过20字，口语化
- 结尾预留3秒
- 只使用素材清单中实际存在的文件名
- 同一视频文件最多使用一段（避免重复）"""


# ── AIClient 主类 ────────────────────────────────────────────────────

class AIClient:
    """
    轻量 AI API 适配器。

    优先级：
    1. 构造函数显式传入 provider
    2. 环境变量自动检测（ANTHROPIC_API_KEY → anthropic；OPENAI_API_KEY → openai）
    3. 无 key → 返回模板占位符，用户手动填写
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.max_tokens = max_tokens
        self.temperature = temperature
        # Validate base_url scheme early — a typo like "evil.com" (no scheme)
        # or "file:///..." would otherwise silently flow into the OpenAI SDK
        # and cause confusing failures. Only http/https are legitimate.
        if base_url:
            from urllib.parse import urlparse
            _bu_scheme = urlparse(str(base_url)).scheme
            if _bu_scheme not in ("http", "https"):
                raise ValueError(
                    f"base_url 必须是 http:// 或 https:// 开头 (got scheme={_bu_scheme!r})"
                )
        self.base_url = base_url

        self.provider = self._normalize_provider(provider or self._detect_provider())
        self.api_key = api_key or self._get_api_key()
        self.model = model or self._default_model()
        self._client = None  # lazy init

    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_provider(provider: Optional[str]) -> Optional[str]:
        p = str(provider or "").strip().lower()
        if not p:
            return None
        # 别名归一：Kimi 属于 Moonshot 体系；maxmini/minimax 归一。
        if p == "kimi":
            return "moonshot"
        if p in {"minimax", "maxmini"}:
            return "maxmini"
        return p

    @staticmethod
    def _is_openai_compatible(provider: Optional[str]) -> bool:
        return provider in {"openai", "moonshot", "qwen", "gemini", "maxmini"}

    def _detect_provider(self) -> Optional[str]:
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return None

    def _get_api_key(self) -> Optional[str]:
        if self.provider == "anthropic":
            return os.environ.get("ANTHROPIC_API_KEY")
        if self._is_openai_compatible(self.provider):
            return os.environ.get("OPENAI_API_KEY")
        return None

    def _default_model(self) -> str:
        if self.provider == "anthropic":
            return "claude-sonnet-4-6"
        if self.provider == "moonshot":
            return "moonshot-v1-8k"
        if self.provider == "qwen":
            return "qwen-plus"
        if self.provider == "gemini":
            return "gemini-2.0-flash"
        if self.provider == "maxmini":
            return "abab6.5s-chat"
        return "gpt-4o-mini"

    def _init_client(self):
        if self._client is not None:
            return
        if self.provider == "anthropic":
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("请安装 Anthropic SDK：pip install anthropic")
        else:
            try:
                import openai
                kwargs: Dict = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self._client = openai.OpenAI(**kwargs)
            except ImportError:
                raise RuntimeError("请安装 OpenAI SDK：pip install openai")

    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict],
        system: Optional[str] = None,
    ) -> str:
        """
        发送对话请求，返回模型回复文本。
        无 API key 时返回可手动填写的模板占位符。
        """
        if not self.provider or not self.api_key:
            return self._template_fallback(messages)

        self._init_client()

        if self.provider == "anthropic":
            return self._call_anthropic(messages, system)
        else:
            return self._call_openai(messages, system)

    def _call_anthropic(self, messages: List[Dict], system: Optional[str]) -> str:
        kwargs: Dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)
        return response.content[0].text

    def _call_openai(self, messages: List[Dict], system: Optional[str]) -> str:
        all_messages: List[Dict] = []
        if system:
            all_messages.append({"role": "system", "content": system})
        all_messages.extend(messages)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=all_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content

    def _template_fallback(self, messages: List[Dict]) -> str:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            "(无请求内容)",
        )
        return (
            "<!-- ⚠️  未检测到 AI API Key -->\n"
            "<!-- 请设置环境变量后重跑：export ANTHROPIC_API_KEY=... -->\n"
            "<!-- 或者手动在此处填写内容后，将下方 approved 改为 true -->\n\n"
            f"<!-- 原始请求摘要：\n{last_user[:300]}\n-->\n\n"
            "请在此处手动填写您的内容...\n"
        )

    # ------------------------------------------------------------------

    @classmethod
    def from_workflow_config(cls, config: Dict) -> "AIClient":
        """从 workflow.json 的 config 段构造。"""
        return cls(
            provider=config.get("ai_provider"),
            base_url=config.get("ai_base_url"),
            model=config.get("ai_model"),
        )

    def __repr__(self) -> str:
        # Never include key prefix — modern key formats like sk-ant-api03-...
        # and sk-proj-... have 8-char prefixes that identify the account tier
        # or project scope. repr() can leak to logs / exception traces.
        key_hint = "set" if self.api_key else "unset"
        return f"<AIClient provider={self.provider} model={self.model} key={key_hint}>"
