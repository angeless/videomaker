# 视界工具箱 (Video Asset Toolkit) V1

## 📋 简介
专为 8TB 级旅游视频素材库设计的语义搜索与归纳系统。支持本地/云端混合分析，实现海量素材的智能索引与快速检索。

## 🚀 核心功能
- **多维度分析**：技术质量、内容标签、地点识别、业务价值。
- **混合架构**：本地轻量筛选 + 云端深度索引，极致成本优化。
- **语义搜索**：支持中文/英文关键词检索。
- **AI 友好**：提供结构化 JSON 输出，可供其他 Agent 直接调用。

## 🛠️ 安装指南
1. **环境要求**：Python 3.8+, FFmpeg
2. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```
3. **配置文件**：修改 `config.json` 填入 API 密钥。

## 🔍 使用说明
- **交互式搜索**：
  ```bash
  python3 chinese_search_ui.py --interactive
  ```
- **命令行搜索**：
  ```bash
  python3 chinese_search_ui.py --query "滑雪"
  ```
- **批量分析**：
  ```bash
  python3 analyze_videos.py --path "/path/to/videos"
  ```

## 🤖 对于 AI 的说明
本工具提供 `search_index` 字段，包含所有关键元数据。调用 `search_ui.search(query)` 即可获取匹配素材的精确路径及时间戳。
