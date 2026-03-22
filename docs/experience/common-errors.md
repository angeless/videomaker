# VideoEditor 常见错误清单

> 本文件记录开发过程中发现的跨任务通用错误模式。
> 每个 vX.Y.Z 任务完成后，如果发现了具有复用价值的错误模式，应追加到本文件。
> Phase 2 ③ 门禁要求对照本文件逐条扫描当前变更。

## 错误模式列表

### CE-001: macOS TCC PermissionError 假阳性
- **错误表现**: `Path.exists()` 返回 True 但 `open()` 抛出 PermissionError
- **根因**: macOS TCC 安全机制允许元数据读取但阻止内容访问（尤其是 `~/Downloads`）
- **正确做法**: 在 `exists()` 检查后加 `try: path.open("r").close()` 验证实际可读性
- **首次发现**: v0.9.1 - BF-001
- **适用范围**: 所有涉及 `~/Downloads`、`~/Documents` 等 TCC 保护目录的文件读取

### CE-002: cv2.VideoCapture 资源泄漏
- **错误表现**: 长时间运行后系统文件描述符耗尽
- **根因**: VideoCapture 在异常退出时未调用 `release()`
- **正确做法**: 所有 `cv2.VideoCapture` 必须包裹在 `try/finally` 中，finally 调用 `cap.release()`
- **首次发现**: v0.3.17
- **适用范围**: beauty.py, pipeline.py, auto_render.py, fingerprint.py, semantic.py, video_asset_toolkit.py

### CE-003: FFmpeg loudnorm 采样率漂移
- **错误表现**: 音频出现规律性电子噪音/伪影
- **根因**: `loudnorm` 滤镜静默改变采样率（44100→96000），导致 AAC 解码异常
- **正确做法**: loudnorm 之后必须加 `-ar 44100` 强制指定采样率
- **首次发现**: 加拿大视频渲染调试
- **适用范围**: 所有使用 loudnorm 滤镜的 FFmpeg 命令
