# VideoEditor 竞品调研报告

> **文档版本**: V2.0
> **日期**: 2026-03-21
> **作者**: Angel（产品）+ Claude（调研执行）
> **调研范围**: 20款AI视频剪辑竞品，全维度深度分析
> **核心关注**: 多模态语义分析（语音+视频画面+图片）、可视化拖拽片段剪辑、Prompt智能剪辑
> **V2.0更新**: 新增视觉语义分析（视频画面/图片内容理解与检索）维度，全面修订对比矩阵、市场空白分析和战略建议

---

## 一、调研目标与方法

本报告围绕 VideoEditor 的四大核心差异化能力——**多模态语义分析（语音+视频画面+图片）**、可视化拖拽片段剪辑、每个片段的 Prompt 智能剪辑、**按主题/内容检索素材**——在市面上筛选了 20 款具有相关能力的竞品，从功能、体验、商业模式、技术路线四个维度进行全面对比分析，并附带用户调研（画像、痛点地图、真实反馈）。

**核心差异化定义**（V2.0明确）:
- **语音语义分析**: 不只是转录字幕，而是理解说了什么、什么主题、什么情感
- **视觉语义分析**: 理解画面中有什么场景、什么物体、什么动作、什么情绪（全新维度）
- **主题检索**: 用户说"我想剪一条关于海边日落的视频"，系统能从素材库中自动找到所有相关片段（语音+画面双通道匹配）
- **Prompt智能剪辑**: 对找到的每个片段，用自然语言指令控制剪辑效果

**调研方法**: 公开信息收集（官网、G2、Capterra、ProductHunt、Trustpilot、Reddit、知乎等），信息截止至 2026 年 3 月。

**竞品筛选标准**:
1. 具备语音识别/转录/分析能力
2. 具备**视频画面/图片内容理解与检索能力**（V2.0新增）
3. 具备拖拽式时间线或片段编辑能力
4. 具备AI智能剪辑或Prompt驱动编辑能力
5. 以桌面端为主，兼顾重要的Web端产品和API平台

---

## 二、20款竞品总览

### 分类框架

| 类别 | 描述 | 竞品 |
|------|------|------|
| **A. 专业桌面剪辑+AI增强** | 传统NLE加入AI能力 | DaVinci Resolve、Adobe Premiere Pro、Final Cut Pro、PowerDirector |
| **B. 桌面端AI优先剪辑** | 以AI为核心设计的桌面工具 | Filmora、Movavi、CapCut Desktop |
| **C. 文本驱动编辑（Text-Based）** | 以语音转录为编辑入口 | Descript、Riverside、Gling |
| **D. AI短视频裁切/重组** | 长视频→短视频的AI工具 | OpusClip、Vizard、Submagic |
| **E. Prompt驱动视频生成/编辑** | 用文本指令控制剪辑 | Runway、InVideo AI、Pictory、Captions |
| **F. AI插件/辅助工具** | 嵌入已有NLE的AI能力 | FireCut、TimeBolt |
| **G. 在线综合编辑平台** | Web端全功能编辑 | VEED.io、Kapwing |

---

## 三、逐竞品深度分析

### A1. DaVinci Resolve 20 — Blackmagic Design

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS/Linux） |
| **定位** | 专业级影视后期全流程工具 |
| **定价** | 免费版（功能极完整）+ Studio $295 一次性买断 |
| **语音分析** | ✅ AI语音转录 → 驱动 IntelliScript、动画字幕、Audio Assistant；RTX 4070上每分钟素材约30秒处理 |
| **拖拽剪辑** | ✅ 专业多轨时间线，完整的拖拽交互 |
| **Prompt剪辑** | ❌ 无Prompt驱动编辑能力 |
| **视觉语义分析** | ⚠️ 场景切换检测（Scene Cut Detection）、Magic Mask（对象追踪分割）；但无画面内容语义理解/自然语言检索 |
| **核心AI功能** | IntelliScript（语音匹配脚本自动排列时间线）、AI Multicam SmartSwitch（检测说话人自动切机位）、Magic Mask、Voice Isolation、AI Audio Assistant |
| **用户评价** | 专业用户极高认可度；免费版被称为"行业良心"；学习曲线陡峭是主要门槛 |
| **与我们的差异** | 功能极其强大但面向专业用户；无Prompt剪辑；IntelliScript是最接近"语义驱动剪辑"的功能；视觉分析仅限物体分割追踪，无画面内容语义理解 |

### A2. Adobe Premiere Pro — Adobe

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS） |
| **定位** | 行业标准专业剪辑软件 |
| **定价** | $22.99/月（年付约$263） |
| **语音分析** | ✅ 内置 Speech-to-Text，支持文本驱动编辑（Text-Based Editing） |
| **拖拽剪辑** | ✅ 业界标杆级多轨时间线 |
| **Prompt剪辑** | ⚠️ 有限——通过 Adobe Sensei AI 辅助自动色彩校正、对象移除等，但非Prompt驱动剪辑 |
| **视觉语义分析** | ✅ **Media Intelligence**（2025新增）——AI分析素材画面内容，支持自然语言搜索素材（如"outdoor shot with blue sky"），可按画面内容、光照、机位检索；同时结合语音和嵌入元数据 |
| **核心AI功能** | Text-Based Editing、**Media Intelligence视觉搜索**、自动字幕生成、自动色彩校正、AI对象添加/移除、场景检测 |
| **用户评价** | 行业标准但订阅制争议大；学习曲线高；性能要求高；Media Intelligence搜索是重要新增 |
| **与我们的差异** | **Media Intelligence是最接近我们"视觉语义检索"的功能**——但仅限素材面板内搜索，非完整的语义分析+Prompt剪辑闭环；价格高、学习曲线陡 |

### A3. Final Cut Pro 11 — Apple

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（macOS专属）+ iPad |
| **定位** | Apple生态下的专业级剪辑工具 |
| **定价** | $299.99 一次性买断 或 Apple Creator Studio $12.99/月订阅（含FCP+Logic Pro+Pixelmator Pro） |
| **语音分析** | ✅ Transcript Search（语音搜索对白）、Transcribe to Captions（自动字幕生成） |
| **拖拽剪辑** | ✅ 磁力时间线（Magnetic Timeline）—— 独特的拖拽交互范式 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ⚠️ Object Tracker（追踪画面中物体）、Scene Removal Mask；无画面内容自然语言检索 |
| **核心AI功能** | Voice Isolation、Object Tracker、Enhance Light and Color（ML驱动）、Smooth Slo-Mo |
| **用户评价** | Mac用户首选；性能优异；磁力时间线评价两极分化；生态锁定 |
| **与我们的差异** | Apple生态锁定；无Prompt能力；语音分析仅限搜索和字幕；视觉AI限于追踪/分割，无语义理解 |

### A4. PowerDirector 2026 — CyberLink

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows） |
| **定位** | 消费级AI视频编辑工具 |
| **定价** | 365订阅 $69.99/年 或 $19.99/月；Ultimate $139.99 买断 |
| **语音分析** | ✅ Speech to Text 自动字幕、AI Text to Speech（260+声音） |
| **拖拽剪辑** | ✅ 传统多轨时间线拖拽 |
| **Prompt剪辑** | ⚠️ 有限——AI Video Generation可从描述生成视频片段，但非片段级Prompt编辑 |
| **视觉语义分析** | ⚠️ AI Scene Detection（场景切换检测）；无画面内容理解/语义检索 |
| **核心AI功能** | AI Voice Translation（保留原声）、AI Auto Editing、AI Scene Detection、Speech Enhancement |
| **用户评价** | 性价比高；适合入门和中级用户；AI功能持续增强；模板丰富 |
| **与我们的差异** | 功能丰富但AI深度不够；场景检测仅限切换点识别，非内容理解；无Prompt剪辑 |

### B1. Filmora 15 — Wondershare

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS）+ 移动端 |
| **定位** | 入门级AI视频编辑，面向创作者 |
| **定价** | $69.99/年 或 $99.99 永久授权 |
| **语音分析** | ✅ AI Speech-to-Text 自动字幕（多语言）、AI Text-Based Editing（通过转录编辑视频） |
| **拖拽剪辑** | ✅ 直观的拖拽时间线 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ⚠️ AI场景检测（Scene Detection自动分段）；无画面内容语义理解 |
| **核心AI功能** | AI文本驱动编辑、AI静音检测裁切、AI场景检测、AI背景移除、AI降噪 |
| **用户评价** | 上手极快；AI功能实用；但高级色彩分级和多轨能力弱于专业工具；年付含额度限制（如30分钟/月STT） |
| **与我们的差异** | Text-Based Editing直接竞争；但AI深度有限，STT额度受限；无Prompt能力；视觉分析仅场景切分 |

### B2. Movavi Video Editor 2026

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS） |
| **定位** | 轻量级AI视频编辑 |
| **定价** | $59.95/年 或 $79.95 终身授权 |
| **语音分析** | ✅ Speech-to-Text自动字幕（多语言）、AI Pause Removal |
| **拖拽剪辑** | ✅ 简洁拖拽时间线 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无画面内容理解能力 |
| **核心AI功能** | AI降噪、AI背景移除、AI Motion Tracking、自动停顿移除 |
| **用户评价** | 极易上手（Trustpilot 4.3/5）；大项目性能堪忧；高级功能较弱 |
| **与我们的差异** | 定位接近（轻量桌面端）但AI能力浅薄；无语义分析、无视觉理解、无Prompt剪辑 |

### B3. CapCut Desktop — ByteDance

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端 + Web端 + 移动端 |
| **定位** | TikTok生态下的全能免费/低价视频编辑 |
| **定价** | 免费版（功能丰富）+ Pro $9.99/月（iOS $19.99/月）或 $74.99/年 |
| **语音分析** | ✅ Auto Captions（带Speaker Identification）、AI Vocal Isolation |
| **拖拽剪辑** | ✅ 拖拽时间线 |
| **Prompt剪辑** | ⚠️ AI Clipper（长视频自动裁切为短视频）、Generative AI Video（文本生成B-roll） |
| **视觉语义分析** | ✅ **Auto-Edit引擎**（2025-2026新增）——多模态AI理解画面内容：人脸检测、场景识别、动作识别；用户输入描述后AI分析素材、选择最佳片段并自动剪辑 |
| **核心AI功能** | AI Script Generation、Auto-Captions、Auto-Reframe、AI Masking、AI Clipper、**Auto-Edit多模态分析** |
| **用户评价** | 免费功能极强（App Store 4.6/5）；Pro锁定争议大；超15分钟视频不稳定；客服差 |
| **与我们的差异** | Auto-Edit的画面理解是有力竞争；但短视频优先、长视频不稳定；视觉理解用于自动剪辑而非用户主动检索；数据隐私顾虑 |

### C1. Descript — ⭐ 最直接的竞品

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS）+ Web端 |
| **定位** | 文本驱动视频/播客编辑的开创者 |
| **定价** | 免费（1小时转录/月、720p水印）→ Hobbyist $16/月(年付) → Creator $35/月 → Business $65/月 |
| **语音分析** | ✅✅ 核心竞争力——自动转录 → 编辑转录文本即编辑视频；一键去除填充词；Overdub（AI语音克隆纠错） |
| **拖拽剪辑** | ✅ 支持传统时间线+文本驱动编辑双模式 |
| **Prompt剪辑** | ⚠️ Underlord AI co-editor 可通过指令辅助剪辑，但非片段级Prompt控制 |
| **视觉语义分析** | ❌ 无画面内容语义理解；完全依赖语音转录作为编辑入口，忽视视觉维度 |
| **核心AI功能** | 文本驱动编辑、Overdub语音克隆、Studio Sound、AI一键去填充词/静音、AI视频生成、30+ AI工具 |
| **用户评价** | 文本编辑范式革命性（编辑时间减少60-70%）；但性能瓶颈严重（长视频卡顿/崩溃）；价格偏高；专业剪辑能力不足（无绿幕、无深度调色） |
| **与我们的差异** | **最直接的竞品**但有明显盲区——完全不理解画面内容，只依赖语音。我们的多模态语义分析（语音+画面）是核心差异点 |

### C2. Riverside

| 维度 | 详情 |
|------|------|
| **平台** | Web端为主（含桌面录制客户端） |
| **定位** | 播客/远程录制+AI编辑一体化平台 |
| **定价** | 免费（2小时/月）→ Standard $19/月 → Pro $29/月 → Live $34/月 |
| **语音分析** | ✅ 自动转录 → 文本驱动编辑；Magic Audio AI音频增强 |
| **拖拽剪辑** | ⚠️ 基础时间线编辑，非完整NLE |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无（面向播客/对话录制，视觉理解不在产品方向内） |
| **核心AI功能** | Text-Based Editing、AI Audio Enhancement、AI翻译配音（30+语言） |
| **用户评价** | 远程录制音质优秀；文本编辑方便；但技术故障频发（同步丢失、文件丢失）；客服差 |
| **与我们的差异** | 纯语音/播客场景；无视觉维度；无Prompt剪辑 |

### C3. Gling

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS） |
| **定位** | 专为YouTube Talking-Head视频设计的AI编辑器 |
| **定价** | 免费（1小时/月）→ $15/月 或 $100/年（10小时/月） |
| **语音分析** | ✅ 自动转录 → 文本驱动编辑；AI自动检测/移除静音、填充词、错误take |
| **拖拽剪辑** | ✅ 文本+时间线双模式编辑 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无（专注Talking-Head语音清理，不涉及画面内容理解） |
| **核心AI功能** | AI自动裁切（静音/填充词/坏take）、AI Captions、Auto Framing、标题生成 |
| **用户评价** | Talking-Head场景极高效（5-10x加速）；仅支持英语是最大限制；不适合复杂制作 |
| **与我们的差异** | 垂直场景做得深但面窄；无视觉理解、无Prompt能力；仅英语 |

### D1. OpusClip

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | AI长视频→短视频裁切工具 |
| **定价** | 免费（60信用/月）→ Starter $15/月 → Pro $29/月（按信用计费，1信用=1分钟源视频） |
| **语音分析** | ✅ AI分析语音高光片段、Virality Score评分 |
| **拖拽剪辑** | ⚠️ 基础编辑界面 |
| **Prompt剪辑** | ✅ Prompt-Based Video Editing——可通过文本描述查找特定时刻、动作、情感、角色 |
| **视觉语义分析** | ✅✅ **ClipAnything**（重磅功能）——多模态AI分析每一帧的视觉、音频和情感线索，识别物体、场景、动作、声音、情绪、文字；支持自然语言Prompt检索特定场景、角色、事件、情感时刻 |
| **核心AI功能** | AI高光检测、Virality Score、**ClipAnything多模态视觉搜索**、动画字幕（97%+准确率）、ReframeAnything、B-roll生成 |
| **用户评价** | 操作简便省时；ClipAnything的视觉搜索能力领先；Virality Score命中率不稳定；AI有时截断关键内容；Trustpilot仅2.4/5 |
| **与我们的差异** | **ClipAnything是视觉语义检索领域最接近我们定位的功能**；但仅做裁切重组，非完整编辑器；Web端非桌面；无片段级Prompt剪辑控制 |

### D2. Vizard

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | 长视频→社交短视频AI裁切平台 |
| **定价** | 免费（120分钟/月上传、10导出）→ Creator $20/月 → Business $19.5/月(年付) |
| **语音分析** | ✅ AI转录 → AI Clipping智能高光检测 → Speaker Detection |
| **拖拽剪辑** | ⚠️ 基础时间线编辑 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ⚠️ Speaker Detection（人脸识别说话人）、Auto-Reframe（追踪主体）；无画面内容语义理解 |
| **核心AI功能** | AI Clipping（一键高光）、Dynamic Captioning（32语言）、Speaker Detection & Auto-Reframe、AI Social Captions |
| **用户评价** | 快速高效（G2/Capterra高分）；深度编辑受限；AI高光选择有时不准 |
| **与我们的差异** | 视觉AI仅限人脸/主体追踪；无画面内容理解；无Prompt能力；Web端 |

### D3. Submagic

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | AI短视频字幕+静音裁切工具 |
| **定价** | Starter $14/月（20视频/月）→ Growth $34/月（无限视频、4K） |
| **语音分析** | ✅ 语音转录 → 文本驱动编辑（通过编辑转录裁切视频） |
| **拖拽剪辑** | ⚠️ 文本驱动编辑替代传统时间线 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无 |
| **核心AI功能** | 自动字幕、静音移除、B-roll插入、关键时刻检测 |
| **用户评价** | 字幕质量好；功能聚焦简洁 |
| **与我们的差异** | 功能单一；无视觉理解、无Prompt；面向短视频字幕场景 |

### E1. Runway — AI视频生成领域标杆

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | AI-first视频生成与编辑平台 |
| **定价** | 免费（125信用一次性）→ Pro $28/月 → Unlimited $76/月（年付） |
| **语音分析** | ❌ 不以语音分析为核心 |
| **拖拽剪辑** | ⚠️ 基础编辑 |
| **Prompt剪辑** | ✅✅ **核心能力**——Aleph功能支持生成后通过Prompt修改视频（加/减对象、改光照、改风格、改背景），Gen-4/4.5 文本生成视频 |
| **视觉语义分析** | ✅ Runway理解生成视频中的视觉内容——Aleph可识别画面中的物体、场景、光照并允许Prompt修改；但面向AI生成内容而非已有素材分析 |
| **核心AI功能** | Gen-4.5文本/图片→视频生成、Aleph后期Prompt编辑、4K输出、风格迁移 |
| **用户评价** | AI视频生成最前沿；但主要面向生成而非已有素材编辑；信用消耗快；价格高 |
| **与我们的差异** | 视觉理解面向生成内容而非用户已有素材；Aleph的交互理念值得参考但场景不同 |

### E2. InVideo AI

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | Prompt驱动的AI视频创建平台 |
| **定价** | 免费（2分钟/周）→ Plus ~$25/月 → Max ~$60/月 |
| **语音分析** | ⚠️ AI配音生成（非既有素材分析） |
| **拖拽剪辑** | ⚠️ 基础场景编辑 |
| **Prompt剪辑** | ✅ Magic Box——通过文本指令修改视频（删除场景、静音、换配音、调效果等） |
| **视觉语义分析** | ⚠️ 从1600万+素材库中按文本语义匹配画面素材；但面向素材库匹配而非用户已有素材分析 |
| **核心AI功能** | 文本→完整视频生成（脚本+素材+配音+剪辑）、Magic Box Prompt编辑、1600万+素材库 |
| **用户评价** | 从0→视频极快；但模板化明显；素材匹配有时不准 |
| **与我们的差异** | 素材库语义匹配有参考价值；但面向模板生成，非用户已有素材的视觉理解 |

### E3. Pictory

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | 文本/文章→视频的AI转换工具 |
| **定价** | Starter $19/月 → Professional $29/月 → Teams $99/月（年付） |
| **语音分析** | ⚠️ Audio-to-Video（语音录制→视频）、自动转录字幕 |
| **拖拽剪辑** | ⚠️ 模板式编辑为主 |
| **Prompt剪辑** | ⚠️ 文本驱动视频创建，但非片段级Prompt控制 |
| **视觉语义分析** | ❌ 无（面向文本→视频的生成，不分析用户已有素材的画面内容） |
| **核心AI功能** | 文章/脚本/URL→视频、长视频高光裁切、AI素材匹配、自动字幕 |
| **用户评价** | 极易上手（"最好用"评价多）；但不可替代专业编辑器；AI声音偏机械 |
| **与我们的差异** | 面向营销内容生成；无已有素材的视觉理解；无深度语音分析 |

### E4. Captions

| 维度 | 详情 |
|------|------|
| **平台** | 移动端优先（iOS/Android）+ 桌面端（Mirage Studio） |
| **定位** | AI短视频创作（创作者/小团队） |
| **定价** | 免费版 + Pro订阅 |
| **语音分析** | ✅ 自动字幕（多语言）、AI Voice Dubbing |
| **拖拽剪辑** | ⚠️ 移动端编辑界面 |
| **Prompt剪辑** | ✅ AI Edit——输入文字指令如"add B-roll of a city at night"或"make this part more dramatic"，AI执行修改 |
| **视觉语义分析** | ⚠️ AI Edit能识别画面中的元素并响应Prompt（如"add B-roll of a city at night"暗示对画面内容有一定理解），但不提供独立的视觉语义搜索 |
| **核心AI功能** | Text-to-Video、AI Edit（Prompt指令编辑）、AI Eye Contact、多语言字幕+配音 |
| **用户评价** | 移动端体验好；AI Edit有创新性；处理速度偶慢 |
| **与我们的差异** | AI Edit隐含一定视觉理解但不显性暴露为检索能力；移动端优先，桌面端弱 |

### F1. FireCut

| 维度 | 详情 |
|------|------|
| **平台** | Adobe Premiere Pro / DaVinci Resolve 插件 |
| **定位** | NLE内的AI自动化辅助插件 |
| **定价** | Shorts $14.50/月 → Plugin $34/月（含7天试用） |
| **语音分析** | ✅ AI转录 → 自动静音/填充词移除 → 章节检测 |
| **拖拽剪辑** | N/A（依托宿主NLE） |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无（纯音频驱动的清洁工具） |
| **核心AI功能** | 静音切除、填充词检测、自动缩放、字幕生成、章节创建、播客多轨编辑 |
| **用户评价** | 省时利器（编辑时间减少60%）；依赖Premiere/Resolve；功能聚焦 |
| **与我们的差异** | 插件模式；纯语音清洁，无视觉理解、无Prompt |

### F2. TimeBolt

| 维度 | 详情 |
|------|------|
| **平台** | 桌面端（Windows/macOS） |
| **定位** | 自动静音/填充词移除工具 |
| **定价** | 免费版 → Pro $17/月 或 $97/年 或 $347终身 |
| **语音分析** | ✅ AI转录 → 检测"um""uh""you know""like"等25+填充词（毫秒精度） |
| **拖拽剪辑** | ⚠️ 基础时间线预览/调整 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无 |
| **核心AI功能** | 自动Jump Cut、填充词检测（UMCHECK）、静音移除、导出到主流NLE |
| **用户评价** | 功能聚焦；填充词检测精准；搭配主流NLE使用 |
| **与我们的差异** | 纯音频清洁工具；无视觉理解、无Prompt |

### G1. VEED.io

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | 在线全功能AI视频编辑平台 |
| **定价** | Lite $12/月 → Pro $29/月 |
| **语音分析** | ✅ AI转录（98%准确率、100+语言）、Voice Cloning（Pro）、TTS |
| **拖拽剪辑** | ✅ 拖拽式Web编辑器 |
| **Prompt剪辑** | ⚠️ AI生成视频功能，但非片段级Prompt控制 |
| **视觉语义分析** | ❌ 无画面内容语义理解（Background Removal使用视觉AI但非语义检索） |
| **核心AI功能** | Auto-Subtitles、Magic Cut、AI Background Removal、Eye Contact Correction、Voice Cloning |
| **用户评价** | 字幕准确度高（Trustpilot 4/5、G2 4.6/5）；长视频卡顿/bug频发；Pro锁定功能争议 |
| **与我们的差异** | Web端；无画面语义理解或检索；Voice Cloning有参考价值 |

### G2. Kapwing

| 维度 | 详情 |
|------|------|
| **平台** | Web端 |
| **定位** | 在线协作视频编辑平台 |
| **定价** | 免费（水印）→ Pro $16/月(年付) → Business $50/月 |
| **语音分析** | ✅ Auto-Subtitle（70+语言）、Smart Cut（自动静音/填充词移除） |
| **拖拽剪辑** | ✅ 拖拽式Web编辑器 |
| **Prompt剪辑** | ❌ 无 |
| **视觉语义分析** | ❌ 无 |
| **核心AI功能** | Smart Cut（减少60%编辑时间）、Auto-Subtitle、AI Background Remover、多人协作 |
| **用户评价** | 免费功能多；适合团队协作；导出速度偶慢 |
| **与我们的差异** | 团队协作是差异化特色；无视觉理解；AI深度不够；Web端 |

---

## 四、核心功能横向对比矩阵

| 竞品 | 语音转录 | 语音语义 | 🆕视觉语义 | 素材主题检索 | 文本驱动编辑 | 拖拽时间线 | Prompt剪辑 | 本地运行 | 价格区间 |
|------|:--------:|:--------:|:----------:|:-----------:|:------------:|:----------:|:----------:|:--------:|:--------:|
| DaVinci Resolve | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ✅✅ | ❌ | ✅ | 免费/$295 |
| **Premiere Pro** | ✅ | ❌ | **✅** | **✅** | ✅ | ✅✅ | ❌ | ✅ | $23/月 |
| Final Cut Pro | ✅ | ❌ | ⚠️ | ❌ | ⚠️ | ✅✅ | ❌ | ✅ | $300 |
| PowerDirector | ✅ | ❌ | ⚠️ | ❌ | ❌ | ✅ | ⚠️ | ✅ | $70/年 |
| Filmora | ✅ | ❌ | ⚠️ | ❌ | ✅ | ✅ | ❌ | ✅ | $70/年 |
| Movavi | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ | $60/年 |
| **CapCut** | ✅ | ❌ | **✅** | ⚠️ | ❌ | ✅ | ⚠️ | ✅ | 免费/$10/月 |
| Descript | ✅✅ | ⚠️ | ❌ | ❌ | ✅✅ | ✅ | ⚠️ | ✅ | $16-65/月 |
| Riverside | ✅ | ❌ | ❌ | ❌ | ✅ | ⚠️ | ❌ | ❌ | $19-34/月 |
| Gling | ✅ | ⚠️ | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | $15/月 |
| **OpusClip** | ✅ | ✅ | **✅✅** | **✅✅** | ❌ | ⚠️ | ✅ | ❌ | $15-29/月 |
| Vizard | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ⚠️ | ❌ | ❌ | $20/月 |
| Submagic | ✅ | ❌ | ❌ | ❌ | ✅ | ⚠️ | ❌ | ❌ | $14-34/月 |
| Runway | ❌ | ❌ | ✅ | ❌ | ❌ | ⚠️ | ✅✅ | ❌ | $28-76/月 |
| InVideo AI | ⚠️ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ | ✅ | ❌ | $25-60/月 |
| Pictory | ⚠️ | ❌ | ❌ | ❌ | ⚠️ | ⚠️ | ⚠️ | ❌ | $19-99/月 |
| Captions | ✅ | ❌ | ⚠️ | ❌ | ❌ | ⚠️ | ✅ | ⚠️ | 免费/Pro |
| FireCut | ✅ | ❌ | ❌ | ❌ | ❌ | N/A | ❌ | ✅(插件) | $15-34/月 |
| TimeBolt | ✅ | ❌ | ❌ | ❌ | ❌ | ⚠️ | ❌ | ✅ | $17/月 |
| VEED.io | ✅ | ❌ | ❌ | ❌ | ⚠️ | ✅ | ⚠️ | ❌ | $12-29/月 |
| Kapwing | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ❌ | 免费/$16/月 |
| **VideoEditor（我们）** | **✅✅** | **✅✅** | **✅✅** | **✅✅** | **✅✅** | **✅✅** | **✅✅** | **✅** | **待定** |

**图例**: ✅✅=核心能力 ✅=支持 ⚠️=有限/部分 ❌=不支持

**🆕 V2.0新增列说明**:
- **视觉语义**: 是否能理解视频画面/图片中的内容（场景、物体、动作、情绪等）
- **素材主题检索**: 用户是否能用自然语言按主题/内容搜索已有素材（如"找所有海边日落的片段"）

---

## 五、关键发现：市场空白与机会

### 1. 🆕 "多模态语义分析+素材检索"是最大的未开发空白

在20款竞品中，**能同时理解语音内容和画面内容并提供自然语言检索的产品几乎为零**：

| 能力组合 | 竞品数量 | 代表 |
|---------|---------|------|
| 语音转录 → 字幕/文本编辑 | 15/20 | Descript、Filmora等（做到了但止步于此） |
| 视觉场景检测（切换点） | 8/20 | DaVinci、Filmora等（仅识别"这里换了一个镜头"） |
| 画面内容语义理解 | 3/20 | **Premiere Pro（Media Intelligence）、OpusClip（ClipAnything）、CapCut（Auto-Edit）** |
| 自然语言检索已有素材 | 2/20 | **仅 Premiere Pro（Media Intelligence）、OpusClip（ClipAnything）** |
| 多模态（语音+画面）联合检索 | 1/20 | **仅 OpusClip ClipAnything（但它不是完整编辑器）** |
| 多模态检索 + 完整时间线编辑 + Prompt剪辑 | **0/20** | **无——这是 VideoEditor 的核心机会** |

### 2. 视觉语义理解的三个层级与竞品分布

```
层级 1: 场景切换检测（Scene Cut Detection）
  → 8款产品已实现（DaVinci、Filmora、Premiere、PowerDirector等）
  → 仅识别"这里画面变了"，不理解"画面中是什么"
  → 技术成熟，门槛低

层级 2: 物体/人脸检测与追踪
  → 5款产品已实现（DaVinci Magic Mask、FCP Object Tracker、Vizard Speaker Detection等）
  → 知道"画面中有一个人在动"，但不理解含义
  → 技术较成熟

层级 3: 画面内容语义理解 + 自然语言检索 ← 我们的目标层级
  → 仅2-3款产品触及（Premiere Media Intelligence、OpusClip ClipAnything）
  → 能回答"哪些片段里有海边日落"这类问题
  → 技术前沿（CLIP/SigLIP模型85-90%准确率），但在编辑器中的集成极少
  → OpusClip做得最深但它不是完整编辑器
  → Premiere做了但仅限素材面板搜索，与编辑工作流割裂
```

### 3. Descript的致命盲区：完全不看画面

Descript作为"文本驱动编辑"的开创者，**完全依赖语音转录作为编辑入口，对视频画面零理解**。这意味着：
- 无法按画面内容搜索素材
- 无法识别"哪些片段是风景"vs"哪些片段是人脸特写"
- 对于没有对白的纯画面内容（B-roll、风景、产品展示）完全无能为力
- **这是 VideoEditor 相对 Descript 最大的差异化优势**

### 4. Prompt剪辑的市场教育已开始

Runway Aleph、InVideo Magic Box、Captions AI Edit 已经开始培育用户对"用文字指令控制视频"的认知。但这些产品主要面向生成内容，**在已有素材的片段级Prompt编辑上几乎无人深耕**。

### 5. 桌面端+本地运行是差异化壁垒

20款竞品中，具备视觉语义能力的新兴AI工具**全部是Web端/云端**（OpusClip、Premiere也需要云处理）。**在桌面端本地实现多模态语义分析，是一个被完全忽视的机会**——尤其对数据隐私敏感的用户群体。

### 6. 🆕 底层技术已成熟但产品化严重不足

视频语义理解的底层技术已相当成熟：
- **CLIP/SigLIP** 模型在通用数据集上达到85-90%语义搜索准确率
- **Twelve Labs Marengo 3.0** 提供多模态视频embedding API（$0.033/分钟）
- **Moments Lab / Valossa / Gyrus AI** 等提供企业级视频内容分析
- **NVIDIA AI Blueprint** 基于VLM+LLM+RAG的视频搜索方案

但这些技术主要服务于企业安防/媒体资产管理，**几乎没有被集成到面向创作者的桌面视频编辑工具中**。这是一个"技术已就绪但产品未出现"的典型窗口期。

---

## 六、用户调研

### 6.1 用户画像分层

基于竞品用户群体分析，VideoEditor 的潜在用户可分为以下四层：

#### Persona A：效率驱动型 YouTuber / 播客创作者
- **年龄**: 22-35岁
- **场景**: 每周产出1-3条Talking-Head视频/播客
- **核心需求**: 快速裁切无用片段（静音、口误、填充词），缩短从录制到发布的时间
- **当前工具**: Descript / Gling / CapCut + 手动剪辑
- **付费意愿**: $15-35/月
- **典型痛点**: "录制30分钟的视频，手动剪掉停顿和口误要花2小时"

#### Persona B：多平台内容运营者
- **年龄**: 25-40岁
- **场景**: 管理多个平台的内容分发，需要将长视频裁切为不同格式的短视频
- **核心需求**: 一条视频高效拆解为多条社交媒体内容
- **当前工具**: OpusClip / Vizard / CapCut
- **付费意愿**: $20-50/月
- **典型痛点**: "一条30分钟的直播回放，手动找高光片段并裁切成10条短视频要花一整天"

#### Persona C：独立创作者 / 小团队
- **年龄**: 20-45岁
- **场景**: 制作有创意表达需求的短视频内容（教程、Vlog、评测等）
- **核心需求**: 不仅要快，还要能精细控制每个片段的效果和风格
- **当前工具**: Premiere Pro / Filmora / DaVinci Resolve
- **付费意愿**: $30-100/月 或一次性付费
- **典型痛点**: "我知道我想要什么效果，但在时间线上一帧帧调太慢了；如果能用文字告诉工具我要什么就好了"

#### Persona D：数据/隐私敏感型用户
- **年龄**: 30-50岁
- **场景**: 企业内部视频制作、教育内容、医疗/法律等敏感领域视频
- **核心需求**: 视频内容不能上传到云端，需要本地化处理
- **当前工具**: DaVinci Resolve / Premiere Pro
- **付费意愿**: $100-300 一次性或年付
- **典型痛点**: "所有AI视频工具都要上传到云端，我们的内容不允许这样做"

### 6.2 用户痛点地图

```
┌─────────────────────────────────────────────────────────────────┐
│                       用户痛点地图                                │
├─────────────────────┬───────────────────────────────────────────┤
│ 痛点等级             │ 具体痛点                                    │
├─────────────────────┼───────────────────────────────────────────┤
│                     │ ① 手动剪切静音/口误/填充词耗时巨大           │
│ 🔴 极高频/强烈     │ ② 找不到"好的片段"——缺乏语义级检索能力       │
│                     │ ②b🆕 纯画面素材（B-roll/风景/产品）完全无法   │
│                     │     被语音工具检索到——只能人工翻看            │
│                     │ ③ AI工具性能差——长视频卡顿/崩溃/导出慢       │
│                     │ ④ 所有新AI工具都是云端，数据上传不可控         │
├─────────────────────┼───────────────────────────────────────────┤
│                     │ ⑤ 文本编辑只能做裁切，不能做"智能变换"       │
│ 🟠 高频/明确       │ ⑤b🆕 想按"主题"组织素材但工具只能按时间排列   │
│                     │ ⑥ AI裁切命中率不够——截断笑点/遗漏高光        │
│                     │ ⑦ 工具太多——需要在3-4个工具间跳转完成一个流程 │
│                     │ ⑧ 价格贵——订阅制叠加起来成本高               │
├─────────────────────┼───────────────────────────────────────────┤
│                     │ ⑨ 多语言支持不足——很多工具仅英语              │
│ 🟡 中频/可忍受     │ ⑩ 学习曲线高——专业工具上手难                  │
│                     │ ⑪ 免费版到付费版功能断层太大                  │
│                     │ ⑫ 客服响应差——付费后问题难解决                │
├─────────────────────┼───────────────────────────────────────────┤
│                     │ ⑬ 协作能力弱——难以多人同时编辑               │
│ 🟢 低频/潜在       │ ⑭ 没有学习路径——不知道怎么用好AI功能          │
│                     │ ⑮ 导出格式/分辨率限制                        │
└─────────────────────┴───────────────────────────────────────────┘
```

### 6.3 真实用户反馈汇总（来源标注）

**关于语音/文本驱动编辑（主要来自Descript用户）**:

> "Text-based editing reduced my editing time by 60-70% for spoken-word content." — G2 Review

> "The text-to-edit model feels foreign to creators used to timeline-based editors." — Fritz.ai Review

> "For professionals who rely on advanced editing tools like green screen adjustments or detailed color grading, Descript falls short." — G2 Review

**关于AI裁切质量（主要来自OpusClip用户）**:

> "The AI gives some decent ideas, but it often misses the point and can struggle with context, sometimes cutting off a joke before the punchline." — Eesel.ai Review

> "While the AI gives them some decent ideas, many experienced OpusClip users bypass the scheduler entirely." — ProductHunt / Reddit

**关于性能问题（跨平台共性）**:

> "Performance bottlenecks and slow processing speeds hinder what should be a smooth experience." — Descript Review

> "CapCut becomes unstable and unreliable beyond ~15 minutes." — BIGVU Review

> "Frequent glitches, export confusion, and poor support." — VEED.io Trustpilot

**关于隐私与本地化需求**:

> "83% of creators are using AI in some form, but 33% view the replacement of human creativity with AI as their top concern." — Digiday Survey

**关于Prompt/智能编辑的期望**:

> "If you have to hunt through menus to swap a voice or edit text, non-technical users will hit a wall." — Atlassian Blog

> "There's a need for semantic editing features, such as the ability to request things like making drums softer." — ProVideo Coalition

**关于视觉内容搜索与素材检索（V2.0新增）**:

> "57% of respondents are interested in AI-assisted video editing and metadata tagging." — MediaValet Video Asset Management Report 2025

> "Premiere Pro's Media Intelligence visual search works by analyzing footage using on-device models and searches for shots based on imagery, spoken words, or content." — Larry Jordan

> "ClipAnything is the first-ever multimodal AI video clipping software that lets you clip any moment from any video using visual, audio, and sentiment cues." — OpusClip Official

> "Modern video discovery systems understand individual visual elements, spoken words, on-screen text, sounds, and the relationships between them, transforming video from an opaque format into searchable data." — Moments Lab Blog 2026

> "70% of video editors now acknowledge that AI features like automatic scene detection substantially improve their workflow." — PXZ.ai 2025

---

## 七、商业模式对比分析

| 模式 | 代表产品 | 优势 | 风险 |
|------|---------|------|------|
| **一次性买断** | DaVinci ($295)、FCP ($300)、Movavi ($80) | 用户忠诚度高、无订阅疲劳 | 收入不可持续、功能迭代缺乏经济动力 |
| **月/年订阅** | Premiere ($23/月)、Descript ($24-65/月)、Filmora ($70/年) | 持续现金流、持续迭代 | 订阅疲劳、用户流失率高 |
| **信用/分钟计费** | OpusClip、Runway、InVideo | 按用量付费合理 | 重度用户成本高、费用不透明 |
| **免费增值 (Freemium)** | CapCut、DaVinci(免费版)、Kapwing | 用户增长快 | 变现压力大、免费→付费转化率低 |

**对 VideoEditor 的建议**: 考虑"买断 + AI功能按量付费"混合模式。桌面基础编辑工具一次性买断（$79-149），AI语义分析和Prompt剪辑按月/按量付费（$15-30/月），兼顾用户获取和持续收入。

---

## 八、技术路线对比

| 技术方向 | 当前主流方案 | 领先竞品 | VideoEditor的机会 |
|---------|-------------|---------|------------------|
| **语音转录** | Whisper / 各家自研 ASR | Descript、VEED（98%准确率） | 基线能力，必须做好；中文多方言支持是差异化 |
| **语音语义理解** | GPT/LLM驱动的内容分析 | OpusClip（初步尝试） | 用LLM理解语音内容的含义、情感、主题结构 |
| 🆕 **视觉语义理解** | CLIP/SigLIP视觉语言模型（85-90%准确率） | Premiere Pro（Media Intelligence）、OpusClip（ClipAnything） | **最大机会**——将视觉理解深度集成到编辑工作流中；竞品要么不做、要么做了但与编辑割裂 |
| 🆕 **多模态融合检索** | 多模态embedding（Twelve Labs Marengo、CLIP联合向量空间） | 几乎空白（仅OpusClip ClipAnything有初步实现） | **蓝海**——语音+画面联合检索，用户说"找有人讲海边旅行且画面有海的片段"能同时匹配语音和画面 |
| **Prompt编辑** | Text-to-Video生成模型 | Runway (Aleph)、Captions (AI Edit) | 需要区分"生成级Prompt"和"编辑级Prompt"——我们应聚焦后者 |
| **视频处理** | FFmpeg + GPU加速 | DaVinci (CUDA/OpenCL)、Premiere (Mercury) | 本地GPU加速是性能保障；视觉分析模型的本地推理需要GPU优化 |
| **UI范式** | 时间线 vs 文本编辑 | Descript（文本）、Resolve（时间线） | **三模式融合**——可视化拖拽时间线 + 语义标注面板（语音+画面双通道）+ Prompt输入 |

### 🆕 视觉语义分析的技术路线选择

| 方案 | 优势 | 劣势 | 适用场景 |
|------|------|------|---------|
| **CLIP/SigLIP本地推理** | 可离线运行、隐私安全、推理速度快（GPU加速后<100ms/帧） | 语义深度有限，复杂场景理解弱 | V1首选——轻量级视觉搜索 |
| **Vision-Language Model (VLM)本地** | 深度语义理解，能描述画面内容 | 模型体积大（7B+），推理较慢 | V2增强——画面内容详细描述和QA |
| **Twelve Labs API云端** | 最强多模态理解，开箱即用 | 依赖云端、$0.033/分钟成本、隐私风险 | 可选增值功能 |
| **混合架构（推荐）** | 本地CLIP做基础检索 + 可选VLM做深度分析 | 架构复杂度高 | **最优平衡——本地为主、云端可选** |

---

## 九、对 VideoEditor 的战略建议

### 9.1 核心差异化定位（V2.0修订）

**"桌面端 · 多模态语义驱动 · Prompt可控 的AI视频剪辑工具"**

四个核心壁垒（从三个升级为四个）：
1. 🆕 **多模态语义分析**（语音+画面双通道理解——不只是听懂说了什么，还要看懂画面中有什么）
2. 🆕 **主题驱动素材检索**（用户说"我要剪一条关于海边日落的视频"，系统从语音和画面两个维度找到所有相关片段）
3. **可视化片段编辑**（拖拽时间线+语义标注面板的融合体验）
4. **片段级Prompt智能剪辑**（对找到的每个片段独立下达AI编辑指令）

附加壁垒：桌面本地运行、数据不上云。

### 9.2 核心用户故事（V2.0新增——阐明差异化价值）

> **"我拍了200条素材，想剪一条关于'城市夜景+美食'的短视频"**
>
> - **当前竞品能做的**：转录语音→搜索提到"夜景"或"美食"的片段→手动时间线排列
> - **当前竞品做不到的**：找到画面中有城市夜景但没有语音提及的B-roll；找到展示美食特写的纯画面片段
> - **VideoEditor 能做的**：语音通道找到"讲到夜景/美食"的片段 + 视觉通道找到"画面是夜景/美食"的片段 → 合并检索结果 → 用户拖拽排列 → 对每个片段Prompt控制剪辑效果

这是市面上**零产品**能完整实现的工作流。

### 9.3 最应参考的6款竞品（V2.0修订）

1. **OpusClip ClipAnything** — 🆕 多模态视觉+音频+情感搜索的产品形态（最直接参考）
2. **Premiere Pro Media Intelligence** — 🆕 视觉语义搜索集成到NLE的交互设计
3. **Descript** — 文本驱动编辑的范式设计（学其优、避其画面盲区和性能坑）
4. **Runway Aleph** — Prompt后期编辑的交互理念
5. **CapCut Auto-Edit** — 🆕 多模态AI理解画面并自动剪辑的产品逻辑
6. **Twelve Labs API** — 🆕 多模态视频embedding的技术实现参考

### 9.4 需警惕的风险

1. **视觉理解准确率**：🆕 CLIP/SigLIP在通用场景下85-90%准确率，意味着10-15%的误召回——需要设计好用户纠错和反馈机制
2. **本地推理性能**：🆕 视觉模型的本地推理需要GPU；需要确保在中等配置设备上也能流畅使用
3. **AI能力的"可靠性悬崖"**: 用户对AI编辑的容忍度低——截断一个笑点就会失去信任
4. **性能问题**: Descript/VEED/CapCut全部在长视频场景翻车，我们必须在本地性能上投入
5. **定价策略**: 避免纯信用制（OpusClip用户抱怨最多）；买断+增值订阅更符合桌面端用户心智
6. **多语言**: 中文（含方言）+ 英文是最低要求；Gling仅英语被大量吐槽

---

## 十、待确认问题

1. VideoEditor 的目标优先级用户是哪个 Persona（A/B/C/D）？
2. 🆕 视觉语义分析的优先级：V1就做还是V2再加？如果V1做，用CLIP本地推理还是混合架构？
3. 🆕 多模态融合检索的交互形态：一个统一搜索框（语音+画面自动匹配）还是分开两个通道让用户选择？
4. 初版是否需要支持Prompt剪辑，还是先做好多模态语义分析+拖拽？
5. 是否需要对 OpusClip ClipAnything 或 Premiere Pro Media Intelligence 做深度产品体验走查？
6. 商业模式倾向是买断、订阅还是混合？
7. 中文多方言的语音识别是否作为V1核心能力？
8. 🆕 本地视觉推理的最低硬件要求如何定义？（是否要求独立GPU？）

---

## 附录：信息来源

### 竞品评测与用户反馈
- G2 Reviews: Descript、OpusClip、Vizard、Filmora、VEED.io、Kapwing、Pictory
- Capterra: Gling、CapCut、Movavi、PowerDirector
- ProductHunt: CapCut用户评论
- Trustpilot: OpusClip (2.4/5)、VEED.io (4/5)、Movavi (4.3/5)
- Fritz.ai: Descript深度评测、OpusClip深度评测
- Eesel.ai: OpusClip定价分析、Descript评论汇总、CapCut评论汇总
- 知乎: 2026年AI视频工具合集、剪辑软件推荐
- 各产品官方定价页面（截至2026年3月）

### V2.0 新增来源（视觉语义分析相关）
- [Moments Lab Blog: What Is AI Video Discovery — 2026](https://www.momentslab.com/blog/what-is-ai-video-discovery-an-updated-guide-for-2026)
- [Voxel51: Visual AI in Video — 2026 Landscape](https://voxel51.com/blog/visual-ai-in-video-2026-landscape)
- [Mixpeek: Video Analysis AI — Complete 2026 Guide](https://mixpeek.com/blog/video-analysis-ai)
- [Twelve Labs: Video Intelligence Platform](https://www.twelvelabs.io/)
- [Twelve Labs + Frame.io Integration](https://www.twelvelabs.io/blog/twelve-labs-and-frame-io)
- [OpusClip ClipAnything](https://www.opus.pro/clipanything)
- [Adobe Premiere Pro Media Intelligence](https://larryjordan.com/articles/ai-powered-media-intelligence-search-in-premiere-pro-2025/)
- [MediaValet: Video Asset Management Report 2025](https://www.mediavalet.com/resources/video-asset-management-report)
- [Valossa: Video Analysis AI](https://valossa.com/)
- [Gyrus AI: Media Asset Management](https://gyrus.ai/Solutions/media-asset-management-search.html)
- [Spot AI: Semantic Search](https://www.spot.ai/semanticsearch)
- [PXZ.ai: AI Video Editing Tools 2025 Comparison](https://pxz.ai/blog/best-ai-video-editing-tools-2025)
- [Flowith Blog: CapCut Desktop Pro 2026](https://flowith.io/blog/capcut-desktop-pro-2026-professional-short-form-video-accessible-billion-creators/)
- Digiday: 创作者AI使用率调研（2025）

> ⚠️ 所有定价信息基于公开渠道收集，可能因地区和促销活动有所不同。标记为"未确认"的信息已在文中注明。

---

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| V1.0 | 2026-03-21 | 初版：20款竞品全维度分析（语音分析+拖拽剪辑+Prompt剪辑） |
| V2.0 | 2026-03-21 | 新增视觉语义分析维度；更新全部20款竞品的视觉分析评估；重构对比矩阵（新增视觉语义+素材检索列）；重写市场空白分析；新增技术路线选择表；修订战略建议和核心用户故事 |

---

*文档结束*
