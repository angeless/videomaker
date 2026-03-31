# VideoEditor 编码标准与质量要求

**文档版本**：v1.0
**生效日期**：2026-03-19
**作者**：架构团队
**适用范围**：所有开发者（AI 和人类）
**最后更新**：2026-03-19

---

## 文档目的

本文档定义 VideoEditor 项目的编码标准、质量要求和开发规范，确保：

1. 所有代码遵循一致的结构和风格
2. 错误处理、资源管理、外部调用安全可控
3. 测试覆盖充分，质量可度量
4. 跨层调用清晰，模块边界保持
5. 日志、配置、数据库操作规范统一

**强制性要求**（必须遵守）用 **MUST** 标记；**强烈建议** 用 **SHOULD** 标记；**可选参考** 用 **MAY** 标记。

---

## 1. 系统分层与职责边界

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│        接入层 (API Layer)                                │
│  modules/app_api/, apps/desktop/ui, apps/cli           │
│  职责: HTTP/CLI 请求处理、参数校验、响应格式化         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│        业务层 (Core Layer)                              │
│  modules/step1-7/, modules/capabilities/                │
│  职责: 核心业务逻辑、状态管理、流程编排                │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│        工具层 (Utils Layer)                             │
│  modules/工具函数、外部工具封装                        │
│  职责: FFmpeg、yt-dlp、LLM 等调用、通用工具集         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────┴────────────────────────────────────┐
│        数据层 (Data Layer)                              │
│  modules/library/, SQLite, 本地文件系统                 │
│  职责: 数据持久化、查询、事务管理                      │
└─────────────────────────────────────────────────────────┘
```

### 1.2 契约层与适配器层

- **modules/contracts/** — 定义跨模块的接口契约，列举规范与禁区
- **modules/adapters/** — NLE(Jianying 等)、云端存储等的适配实现

### 1.3 工作流引擎关系

**modules/workflow_engine/** 与业务层的关系：

- 工作流引擎不应包含业务逻辑，仅负责任务调度、状态转移、重试
- 每一个步骤(step1-7)或能力(capabilities)都是一个独立的执行单元
- 工作流引擎通过**发布-订阅**或**回调**驱动步骤执行，不直接修改业务数据

### 1.4 层间调用规则

**MUST**：遵循单向依赖：

```
接入层 → 业务层 → 工具层 → 数据层
        (可跳级)   ↓

业务层 → 适配器层 → 外部系统
业务层 → 契约层(读)
```

**禁止**：

- ❌ 工具层调用业务层
- ❌ 数据层调用业务层
- ❌ 业务层之间的循环依赖（step1 ↔ step2）
- ❌ 适配器层暴露业务逻辑给外部
- ❌ 绕过适配器直接调用外部系统

**SHOULD**：导入链：显式声明依赖，勿隐式引入。

---

## 2. 命名规范

### 2.1 Python 文件名

格式：`snake_case.py`

```
✅ audio_quality.py
✅ material_analysis.py
✅ transcript_correction.py
✅ project_relink_api.py

❌ AudioQuality.py
❌ Material_Analysis.py
❌ Transcript-Correction.py
```

### 2.2 类名

格式：`PascalCase`，反映类的职责。

```python
✅ class AudioQualityAnalyzer:
✅ class MaterialLibraryStore:
✅ class TranscriptCorrector:
✅ class FFmpegWrapper:

❌ class audio_quality_analyzer:
❌ class Analyzer:  # 太通用
```

### 2.3 函数名与方法名

格式：`snake_case`，动词优先（获取、计算、保存、验证）。

```python
✅ def extract_audio(video_path: str) -> bytes:
✅ def analyze_quality_score(video_path: str) -> float:
✅ def save_project(data: dict) -> str:
✅ def validate_input_params(params: dict) -> bool:

❌ def audio(video_path: str):  # 不清楚作用
❌ def compute(video_path: str):  # 太模糊
```

### 2.4 常量名

格式：`UPPER_SNAKE_CASE`，模块级常量放在 `__init__.py` 或模块顶部。

```python
✅ DEFAULT_AUDIO_BITRATE = 128
✅ MAX_VIDEO_DURATION_SECONDS = 3600
✅ QUALITY_THRESHOLD_DB = 18
✅ SUPPORTED_VIDEO_FORMATS = ('mp4', 'mov', 'mkv')

❌ default_audio_bitrate = 128
❌ maxDuration = 3600
```

### 2.5 环境变量名

格式：`UPPER_SNAKE_CASE_WITH_PROJECT_PREFIX`

```python
✅ VIDEOEDITOR_FFmpeg_PATH
✅ VIDEOEDITOR_API_PORT
✅ VIDEOEDITOR_MODEL_CACHE_DIR
✅ VIDEOEDITOR_LLM_API_KEY

❌ ffmpeg_path
❌ FFMPEG_PATH  # 无项目前缀易冲突
```

### 2.6 数据库表名与字段名

格式：`snake_case`

```sql
✅ CREATE TABLE workflow_jobs (
     job_id TEXT PRIMARY KEY,
     project_path TEXT NOT NULL,
     status TEXT,  -- pending|running|done|failed
     created_at TIMESTAMP
   );

❌ CREATE TABLE WorkflowJobs (...)
❌ CREATE TABLE jobs (  # 太通用
```

### 2.7 模块目录命名

格式：`snake_case_with_step_number`

```
✅ modules/step1_material_analysis/
✅ modules/step2_topic_planning/
✅ modules/capabilities/audio_voice/
✅ modules/adapters/jianying/

❌ modules/Step1MaterialAnalysis/
❌ modules/MATERIAL_ANALYSIS/
```

### 2.8 测试函数命名

格式：`test_<function_name>_<scenario>` 或 `test_<function_name>_<expected_result>`

```python
✅ def test_extract_audio_success():
✅ def test_extract_audio_with_invalid_path():
✅ def test_save_project_creates_directory():
✅ def test_validate_params_rejects_negative_duration():

❌ def test_audio():
❌ def testExtractAudio():
❌ def test1():
```

### 2.9 文档文件命名

格式：`YYYY-MM-DD_项目名_文档类型_主题_Vx.y.md`

```
✅ 2026-03-19_VideoEditor_编码规范_命名与结构_v1.0.md
✅ 2026-03-19_VideoEditor_测试记录_音频分析链路_v1.2.md
✅ 2026-03-18_VideoEditor_代码审计_状态流转_v0.9.md

❌ coding_standards.md
❌ 新版本.md
❌ 最终版.md
```

---

## 3. 代码结构规范

### 3.1 Python 文件模板

每个 Python 文件 **MUST** 遵循这个结构：

```python
#!/usr/bin/env python3
"""
模块简述 — English Name (if applicable)

长描述：模块功能、输入、输出、依赖、注意事项。

示例：
  输入: {"video_path": "/path/to/video.mp4"}
  输出: {"quality_score": 0.82, "issues": [...]}

错误: 若文件不存在、FFmpeg 超时则抛出 AudioAnalysisError。
"""

# 标准库导入
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 第三方导入
import numpy as np  # 仅当确实需要

# 项目内导入
from modules.contracts import AudioAnalysisContract
from modules.adapters.ffmpeg_wrapper import FFmpegWrapper
from modules.library.storage import LibraryStore
from modules.exceptions import AudioAnalysisError, TimeoutError

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# 常量与全局配置
# ─────────────────────────────────────────────────────────────

DEFAULT_AUDIO_BITRATE: int = 128  # kbps
MAX_ANALYSIS_TIMEOUT: int = 60    # seconds
SUPPORTED_FORMATS: tuple = ('mp4', 'mov', 'mkv')

# ─────────────────────────────────────────────────────────────
# 公共接口（API）
# ─────────────────────────────────────────────────────────────

def analyze_audio_quality(video_path: str, timeout: int = 60) -> Dict[str, Any]:
    """
    分析视频音频质量。

    Args:
        video_path: 视频文件路径（绝对路径）
        timeout: 分析超时时间（秒）

    Returns:
        {
            "snr_db": float,
            "quality_score": float,  # 0-1
            "issues": List[str],
            "method": str
        }

    Raises:
        AudioAnalysisError: 分析失败
        TimeoutError: 分析超时
        FileNotFoundError: 文件不存在
        ValueError: 参数无效

    示例:
        >>> result = analyze_audio_quality("/path/to/video.mp4", timeout=30)
        >>> print(f"质量: {result['quality_score']}")
    """
    pass

# ─────────────────────────────────────────────────────────────
# 内部实现
# ─────────────────────────────────────────────────────────────

def _extract_pcm(video_path: str, output_raw: str) -> bool:
    """内部: 提取 PCM 音频（不应直接暴露给外部）"""
    pass

def _compute_snr(pcm_data: np.ndarray) -> float:
    """内部: 计算信噪比"""
    pass
```

**关键点**：

- **Shebang** 行：`#!/usr/bin/env python3`
- **模块 docstring**：描述功能、输入/输出、错误、示例
- **Import 顺序**：标准库 → 第三方 → 项目内（按字母顺序）
- **常量分组**：统一定义在顶部
- **公共接口**：先列出所有公共函数，附完整 docstring
- **内部实现**：以 `_` 或 `__` 前缀标记，不在公共文档中体现
- **分隔符**：用 `# ─── ... ────` 分隔逻辑段落，提高可读性

### 3.2 类型标注（强制）

**MUST**：所有公共函数（非 `_` 开头）必须有完整的类型标注。

```python
✅ def save_project(project_data: Dict[str, Any],
                    output_dir: Path) -> str:
    """存储项目，返回项目 ID。"""
    pass

✅ def list_materials(status: Optional[str] = None) -> List[Material]:
    """列出素材。status 为 None 时返回全部。"""
    pass

❌ def save_project(project_data, output_dir):
    """缺少类型标注"""
    pass

❌ def list_materials(status=None):
    """缺少类型标注"""
    pass
```

**SHOULD**：内部函数（`_` 开头）鼓励标注，但不强制。

```python
def _internal_helper(x: int, y: str) -> bool:
    """内部助手函数，建议标注但非必须"""
    pass

def _simple_check(x):
    """简单内部函数，可不标注"""
    pass
```

**特殊类型**：

```python
from typing import Any, Dict, List, Optional, Tuple, Callable, Union
from pathlib import Path

# 对于联合类型，使用 Union 或 | (Python 3.10+)
def process(data: Union[str, Path]) -> None:  # Python 3.9 及以下
    pass

def process(data: str | Path) -> None:  # Python 3.10+
    pass

# 对于回调函数
OnSuccess = Callable[[Dict[str, Any]], None]
def run_async(on_success: OnSuccess) -> None:
    pass
```

### 3.3 Docstring 要求

**模块 docstring**（文件顶部）：

```python
"""
模块名 — English Name

一句话描述功能。

详细说明（可选）：
  - 输入格式
  - 输出格式
  - 关键依赖
  - 使用场景

示例（可选）：
  >>> from modules.xxx import analyze
  >>> result = analyze(data)
  >>> print(result['score'])
"""
```

**函数 docstring**（Google style）：

```python
def analyze_quality(video_path: str,
                    timeout: int = 60,
                    use_cache: bool = True) -> Dict[str, float]:
    """
    分析视频质量。

    Args:
        video_path: 视频文件绝对路径
        timeout: 分析超时时间（秒，默认 60）
        use_cache: 是否使用缓存结果（默认 True）

    Returns:
        {
            "quality_score": float (0-1),
            "snr_db": float,
            "loudness_lufs": float,
            "issues": List[str]
        }

    Raises:
        FileNotFoundError: 文件不存在
        AudioAnalysisError: 分析失败（含错误消息）
        TimeoutError: 分析超时
        ValueError: 参数无效（timeout < 0 等）

    示例：
        >>> result = analyze_quality("/path/video.mp4", timeout=30)
        >>> if result['quality_score'] > 0.8:
        ...     print("高质量视频")

    注意：
        - 首次调用会加载 FFmpeg，可能较慢
        - 结果会存入缓存，同路径重复调用快速返回
        - 超时会清理临时文件，但不保证资源完全释放
    """
    pass
```

**类 docstring**：

```python
class AudioQualityAnalyzer:
    """
    音频质量分析器。

    负责对视频/音频进行多维度质量评估，包括信噪比、响度、
    动态范围等。支持缓存与增量分析。

    属性：
        cache_dir (Path): 缓存目录
        timeout (int): 默认超时时间（秒）

    示例：
        >>> analyzer = AudioQualityAnalyzer(cache_dir="/tmp/cache")
        >>> result = analyzer.analyze("/path/video.mp4")
        >>> print(result['quality_score'])

    设计备注：
        - 使用 FFmpeg 提取 PCM，numpy 计算特征
        - 缓存基于文件内容 hash，避免重复分析
        - 超时由 FFmpeg 命令行 timeout 保障
    """

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        """初始化分析器。"""
        pass

    def analyze(self, video_path: str) -> Dict[str, Any]:
        """分析视频。"""
        pass
```

**行内注释**（用于非显而易见的逻辑）：

```python
# 使用稍保守的阈值，避免误报降低体验
if snr_db < 20:
    issues.append("底噪偏高")

# 当 FFmpeg 超时时，子进程可能未完全清理
# 需要显式 kill 以释放资源
if proc.poll() is None:
    proc.kill()
```

### 3.4 临时方案标记

**MUST**：临时或不完美的实现必须标记。

```python
# TODO: 当添加 GPU 支持时，改用 CUDA 加速计算
def compute_features(pcm_data: np.ndarray) -> np.ndarray:
    # 当前使用 CPU 计算，性能较差
    return np.fft.fft(pcm_data)

# FIXME: 修复 bug#123 - 某些特殊字符导致文件名错误
# 临时方案：手动转义，后续改用 pathlib 规范化
escaped_name = safe_filename(name).replace("?", "_")

# HACK: 工作流引擎暂不支持动态参数，硬编码 timeout
# 长期计划：在契约层新增 timeout_config，由工作流引擎下发
timeout = 60
```

**格式**：

- `TODO`: 计划中的功能或改进
- `FIXME`: 已知 bug，待修复
- `HACK`: 临时方案或 workaround，说明背景与长期计划

---

## 4. 错误处理规范（核心）

### 4.1 自定义异常体系

**MUST**：在 `modules/exceptions.py` 中定义层级化异常。

```python
# modules/exceptions.py

"""VideoEditor 自定义异常体系"""

class VideoEditorError(Exception):
    """所有 VideoEditor 异常的基类"""
    pass

# ─── 业务层异常 ───

class MaterialAnalysisError(VideoEditorError):
    """素材分析失败"""
    pass

class AudioAnalysisError(MaterialAnalysisError):
    """音频分析失败"""
    pass

class TranscriptionError(MaterialAnalysisError):
    """语音转录失败"""
    pass

class WorkflowError(VideoEditorError):
    """工作流执行失败"""
    pass

class JobTimeoutError(WorkflowError):
    """任务执行超时"""
    pass

class JobCancelledError(WorkflowError):
    """任务被用户取消"""
    pass

# ─── 工具层异常 ───

class ExternalToolError(VideoEditorError):
    """外部工具（FFmpeg、yt-dlp 等）调用失败"""
    pass

class FFmpegError(ExternalToolError):
    """FFmpeg 执行失败"""
    pass

class YtDlpError(ExternalToolError):
    """yt-dlp 下载失败"""
    pass

# ─── 数据层异常 ───

class StorageError(VideoEditorError):
    """存储操作失败"""
    pass

class DatabaseError(StorageError):
    """数据库操作失败"""
    pass

class FileAccessError(StorageError):
    """文件访问失败"""
    pass

# ─── 配置与验证异常 ───

class ConfigError(VideoEditorError):
    """配置错误（缺失、格式不对）"""
    pass

class ValidationError(VideoEditorError):
    """参数或数据验证失败"""
    pass
```

### 4.2 错误处理铁律

#### 规则 1：绝不使用裸 except

**MUST**：永远显式捕获特定异常。

```python
✅ try:
    result = ffmpeg_wrapper.extract_audio(video_path)
except FFmpegError as e:
    logger.error(f"FFmpeg 提取音频失败: {e}", exc_info=True)
    raise AudioAnalysisError(f"无法提取音频: {e}") from e

❌ try:
    result = ffmpeg_wrapper.extract_audio(video_path)
except:
    # 裸 except 隐藏错误，导致难以调试
    pass
```

#### 规则 2：异常必须被记录或重新抛出，不可吞没

**MUST**：捕获异常后，要么记录要么重新抛出，不可沉默失败。

```python
✅ def analyze_video(path: str) -> Dict[str, Any]:
    try:
        result = _extract_audio(path)
    except FileNotFoundError as e:
        logger.warning(f"文件不存在: {path}")
        raise  # 重新抛出，让调用者处理
    except FFmpegError as e:
        logger.error(f"FFmpeg 失败: {e}", exc_info=True)
        raise AudioAnalysisError(f"分析失败") from e

❌ def analyze_video(path: str) -> Dict[str, Any]:
    try:
        result = _extract_audio(path)
    except Exception:
        return {}  # 沉默失败，调用者无法知晓错误
```

#### 规则 3：业务层异常必须写入日志

**MUST**：业务操作失败时，必须记录，便于运维与排查。

```python
✅ def save_project(project_data: Dict) -> str:
    try:
        project_id = uuid.uuid4().hex
        self.db.save(project_id, project_data)
        logger.info(f"项目已保存: project_id={project_id}")
        return project_id
    except DatabaseError as e:
        logger.error(
            f"保存项目失败: project_data={project_data}",
            exc_info=True
        )
        raise

❌ def save_project(project_data: Dict) -> str:
    try:
        return self.db.save(project_id, project_data)
    except DatabaseError:
        raise  # 未记录错误细节
```

#### 规则 4：API 层异常通过统一 handler 返回格式化 JSON

**MUST**：Flask 路由中的异常由全局 error handler 处理，返回标准格式。

```python
# modules/app_api/server.py

@app.errorhandler(ValidationError)
def handle_validation_error(e: ValidationError):
    """处理参数验证失败"""
    return jsonify({
        "success": False,
        "error": "validation_error",
        "message": str(e),
        "code": 400
    }), 400

@app.errorhandler(AudioAnalysisError)
def handle_analysis_error(e: AudioAnalysisError):
    """处理分析失败"""
    logger.error(f"分析失败: {e}", exc_info=True)
    return jsonify({
        "success": False,
        "error": "analysis_error",
        "message": "音频分析失败，请重试或检查输入文件",
        "code": 500
    }), 500

@app.errorhandler(Exception)
def handle_unexpected_error(e: Exception):
    """处理未捕获的异常"""
    logger.critical(f"未捕获的异常: {e}", exc_info=True)
    return jsonify({
        "success": False,
        "error": "internal_error",
        "message": "服务器内部错误，请联系管理员",
        "code": 500
    }), 500

# 路由示例
@app.route('/api/capabilities/audio_voice/synthesize', methods=['POST'])
def synthesize_voice():
    """合成语音"""
    try:
        params = request.json
        if not params.get('text'):
            raise ValidationError("text 参数必填")

        result = voice_synthesizer.synthesize(
            text=params['text'],
            voice_id=params.get('voice_id', 'default')
        )
        return jsonify({"success": True, "data": result})
    except ValidationError as e:
        # 由 @app.errorhandler 处理
        raise
    except AudioAnalysisError as e:
        raise
    # 其他异常也会被全局 handler 捕获
```

#### 规则 5：所有外部调用必须有超时和重试

**MUST**：调用 FFmpeg、LLM API、网络请求等，必须设置超时与重试策略。

```python
✅ def extract_audio_with_retry(
    video_path: str,
    timeout: int = 60,
    max_retries: int = 3
) -> bytes:
    """
    提取音频，支持重试。

    Args:
        video_path: 视频文件路径
        timeout: 单次超时（秒）
        max_retries: 最大重试次数

    Returns:
        PCM 字节数据

    Raises:
        FFmpegError: 重试次数耗尽仍失败
    """
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"提取音频，尝试 {attempt}/{max_retries}: {video_path}")
            pcm_data = _extract_pcm_internal(video_path, timeout=timeout)
            logger.info(f"提取成功: {len(pcm_data)} 字节")
            return pcm_data
        except subprocess.TimeoutExpired as e:
            if attempt < max_retries:
                logger.warning(f"超时，3秒后重试: {e}")
                time.sleep(3)
            else:
                logger.error(f"重试 {max_retries} 次后超时: {video_path}")
                raise FFmpegError(f"提取音频超时: {video_path}") from e
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg 异常 (attempt {attempt}): {e.stderr}")
            if attempt < max_retries:
                logger.info("2秒后重试")
                time.sleep(2)
            else:
                raise FFmpegError(f"FFmpeg 失败: {e.stderr}") from e

❌ def extract_audio(video_path: str) -> bytes:
    """提取音频，无超时、无重试"""
    return _extract_pcm_internal(video_path)
```

### 4.3 错误响应统一格式

**MUST**：所有 API 错误响应遵循统一格式。

```json
{
  "success": false,
  "error": "error_code",           // 机器可读错误代码
  "message": "Human-readable msg",  // 用户可读消息
  "code": 400,                       // HTTP 状态码（冗余但有用）
  "timestamp": "2026-03-19T10:30:00Z",
  "trace_id": "uuid-for-tracking"   // 可选：用于日志关联
}
```

**成功响应**：

```json
{
  "success": true,
  "data": { /* 实际数据 */ },
  "timestamp": "2026-03-19T10:30:00Z"
}
```

**实现示例**：

```python
def make_error_response(error_type: str, message: str,
                        http_code: int, trace_id: Optional[str] = None):
    """构造错误响应"""
    return jsonify({
        "success": False,
        "error": error_type,
        "message": message,
        "code": http_code,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "trace_id": trace_id or uuid.uuid4().hex
    }), http_code
```

### 4.4 对 FFmpeg、yt-dlp 等子进程调用的错误处理

**MUST**：所有子进程调用必须捕获 stdout、stderr，并妥善清理资源。

```python
def call_ffmpeg(args: List[str], timeout: int = 60) -> Tuple[str, str]:
    """
    调用 FFmpeg，返回 (stdout, stderr)。

    Args:
        args: FFmpeg 命令行参数列表（不包括 'ffmpeg'）
        timeout: 超时时间（秒）

    Returns:
        (stdout 文本, stderr 文本)

    Raises:
        FileNotFoundError: FFmpeg 不存在
        subprocess.TimeoutExpired: 执行超时
        FFmpegError: FFmpeg 返回非零状态码
    """
    proc = None
    try:
        # 完整命令
        cmd = ['ffmpeg', '-y'] + args  # -y 覆盖输出文件

        logger.debug(f"执行命令: {' '.join(cmd)}")

        # 捕获输出
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors='replace'  # 替换无法解码的字符
        )

        stdout, stderr = proc.communicate(timeout=timeout)

        if proc.returncode != 0:
            logger.error(f"FFmpeg 失败 (code={proc.returncode}): {stderr}")
            raise FFmpegError(f"FFmpeg 失败: {stderr}")

        return stdout, stderr

    except FileNotFoundError as e:
        logger.error(f"FFmpeg 未找到: {e}")
        raise FFmpegError(f"FFmpeg 未安装或不在 PATH 中") from e
    except subprocess.TimeoutExpired:
        logger.error(f"FFmpeg 超时 ({timeout}秒)")
        if proc:
            proc.kill()  # 强制终止
            proc.wait()  # 等待进程完全退出
        raise FFmpegError(f"FFmpeg 执行超时") from None
    finally:
        # 确保资源清理
        if proc and proc.poll() is None:
            logger.warning("未完全清理的子进程，强制 kill")
            proc.kill()
            proc.wait()
```

---

## 5. 外部调用治理

### 5.1 所有外部工具调用必须通过封装函数

**MUST**：不允许在业务代码中直接调用 FFmpeg、yt-dlp 等。

```
❌ 业务代码中：
   subprocess.run(['ffmpeg', ...])

✅ 通过工具层封装：
   from modules.adapters.ffmpeg_wrapper import FFmpegWrapper
   wrapper = FFmpegWrapper()
   result = wrapper.extract_audio(video_path)
```

### 5.2 封装函数必须包含：超时、重试、日志、错误解析、资源清理

**MUST**：所有工具层封装都遵循下列模板。

```python
# modules/adapters/ffmpeg_wrapper.py

class FFmpegWrapper:
    """FFmpeg 调用封装"""

    def __init__(self, timeout: int = 60, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.ffmpeg_path = self._locate_ffmpeg()

    def extract_audio(self, video_path: str) -> bytes:
        """
        提取视频音频轨道为 PCM。

        Args:
            video_path: 视频文件绝对路径

        Returns:
            PCM 原始字节数据

        Raises:
            FFmpegError: 提取失败
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(
                    f"[FFmpeg] 提取音频 (attempt {attempt}/{self.max_retries}): "
                    f"{video_path}"
                )

                result = self._extract_audio_internal(
                    video_path,
                    timeout=self.timeout
                )

                logger.info(
                    f"[FFmpeg] 提取成功: {len(result)} 字节"
                )
                return result

            except subprocess.TimeoutExpired as e:
                if attempt < self.max_retries:
                    logger.warning(
                        f"[FFmpeg] 超时，等待后重试: {self.timeout}s"
                    )
                    time.sleep(2)
                else:
                    logger.error(
                        f"[FFmpeg] 重试 {self.max_retries} 次后超时"
                    )
                    raise FFmpegError(
                        f"FFmpeg 超时: {video_path}"
                    ) from e

            except subprocess.CalledProcessError as e:
                logger.error(
                    f"[FFmpeg] 执行失败: {e.stderr[:500]}..."
                )
                if attempt < self.max_retries:
                    logger.info(f"[FFmpeg] 等待后重试")
                    time.sleep(2)
                else:
                    raise FFmpegError(
                        f"FFmpeg 失败: {e.stderr}"
                    ) from e

    def _extract_audio_internal(self, video_path: str,
                                timeout: int) -> bytes:
        """内部实现，不暴露给外部"""
        # 实现细节...
        pass

    def _locate_ffmpeg(self) -> str:
        """查找 FFmpeg 路径"""
        # 先查 VIDEOEDITOR_FFMPEG_PATH，再找 PATH
        pass
```

### 5.3 LLM API 调用封装要求

**MUST**：所有 LLM 调用通过专用的 API 客户端，包含速率限制与缓存。

```python
# modules/adapters/llm_client.py

class LLMClient:
    """统一的 LLM API 调用客户端"""

    def __init__(self, api_key: str, cache_dir: Optional[Path] = None):
        self.api_key = api_key
        self.cache = LLMResponseCache(cache_dir) if cache_dir else None
        self.rate_limiter = RateLimiter(max_requests_per_minute=60)

    def complete(
        self,
        prompt: str,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2000,
        timeout: int = 30
    ) -> str:
        """
        调用 LLM 完成任务。

        Args:
            prompt: 提示文本
            model: 模型名称
            temperature: 采样温度
            max_tokens: 最大输出 token
            timeout: 请求超时（秒）

        Returns:
            LLM 生成的文本

        Raises:
            LLMError: API 调用失败
            TimeoutError: 请求超时
        """
        # 1. 检查缓存
        cache_key = self._make_cache_key(prompt, model, temperature)
        if self.cache and cache_key in self.cache:
            logger.debug(f"[LLM] 缓存命中: {cache_key[:20]}...")
            return self.cache.get(cache_key)

        # 2. 速率限制
        self.rate_limiter.wait_if_needed()

        # 3. 调用 API，含重试
        for attempt in range(1, 4):
            try:
                logger.info(
                    f"[LLM] 调用 {model} (attempt {attempt}/3), "
                    f"prompt_len={len(prompt)}"
                )

                response = self._call_openai_api(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout
                )

                # 4. 缓存结果
                if self.cache:
                    self.cache.set(cache_key, response)

                logger.info(
                    f"[LLM] 调用成功: "
                    f"output_len={len(response)}"
                )
                return response

            except requests.Timeout:
                if attempt < 3:
                    logger.warning(f"[LLM] 超时，{2**attempt}秒后重试")
                    time.sleep(2 ** attempt)
                else:
                    logger.error(f"[LLM] 重试 3 次后仍超时")
                    raise LLMError(f"LLM 请求超时") from None

            except requests.HTTPError as e:
                status = e.response.status_code
                if status == 429:  # 限流
                    wait_time = int(e.response.headers.get('Retry-After', 60))
                    logger.warning(f"[LLM] 限流，等待 {wait_time}秒")
                    time.sleep(wait_time)
                elif status in (500, 502, 503):  # 服务器错误
                    if attempt < 3:
                        logger.warning(f"[LLM] 服务器错误，重试")
                        time.sleep(2 ** attempt)
                    else:
                        raise LLMError(f"LLM 服务不可用") from e
                else:
                    logger.error(f"[LLM] HTTP {status}: {e}")
                    raise LLMError(f"LLM API 错误: {status}") from e

    def _call_openai_api(self, prompt: str, model: str,
                         temperature: float, max_tokens: int,
                         timeout: int) -> str:
        """内部实现"""
        pass
```

### 5.4 调用日志格式

**MUST**：所有外部调用都应记录完整的调用链。

```
[模块名] 操作名 (参数摘要): 结果

✅ [FFmpeg] 提取音频 (video=/path/video.mp4, timeout=60): 成功, 2048字节
✅ [LLM] 调用 gpt-4o-mini (prompt_len=250): 成功, output_len=180
✅ [YtDlp] 下载视频 (url=https://..., format=720p): 成功, 125MB

❌ [FFmpeg] 提取音频 (video=/path/video.mp4, timeout=60): 失败, 超时
❌ [LLM] 调用 gpt-4o-mini: 失败, HTTP 429 (限流)
```

---

## 6. 数据库操作规范

### 6.1 SQLite 使用规则

**MUST**：所有数据库访问通过统一的 Store 类，不允许裸 SQL。

```python
# ✅ 通过 Store 类
from modules.library.storage import LibraryStore
store = LibraryStore(db_path="/path/app.db")
materials = store.query_materials(status="active")

# ❌ 直接 SQL
import sqlite3
conn = sqlite3.connect("/path/app.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM materials WHERE status='active'")
```

**MUST**：所有查询都使用参数化查询，防止 SQL 注入。

```python
✅ def query_by_name(self, name: str) -> List[Material]:
    """查询素材"""
    return self.db.query(
        "SELECT * FROM materials WHERE name = ?",
        (name,)
    )

❌ def query_by_name(self, name: str) -> List[Material]:
    """查询素材"""
    # SQL 注入风险！
    return self.db.query(f"SELECT * FROM materials WHERE name = '{name}'")
```

### 6.2 数据迁移管理

**MUST**：数据库 schema 变更使用版本化的迁移脚本。

```
migrations/
├── 001_initial_schema.sql      # 初始建表
├── 002_add_quality_score.sql   # 添加字段
├── 003_create_job_table.sql    # 新增表
└── migration_log.py             # 迁移记录与执行
```

```python
# modules/app_api/migrations.py

class Migration:
    """数据库迁移管理"""

    MIGRATIONS = [
        {
            'version': 1,
            'name': 'initial_schema',
            'file': 'migrations/001_initial_schema.sql'
        },
        {
            'version': 2,
            'name': 'add_quality_score',
            'file': 'migrations/002_add_quality_score.sql'
        }
    ]

    @classmethod
    def get_current_version(cls, db_path: str) -> int:
        """获取当前 schema 版本"""
        # 检查元数据表
        pass

    @classmethod
    def migrate(cls, db_path: str) -> None:
        """执行待定迁移"""
        current = cls.get_current_version(db_path)
        for migration in cls.MIGRATIONS:
            if migration['version'] > current:
                logger.info(f"执行迁移: {migration['name']}")
                # 执行 SQL 脚本
                # 更新版本记录
```

### 6.3 状态流转规则（任务/工作流的状态机定义）

**MUST**：所有涉及状态的表都必须定义状态机，并在代码中强制执行。

```python
# modules/contracts/workflow_contract.py

class JobStatus(Enum):
    """任务状态机"""
    PENDING = "pending"      # 初始状态
    RUNNING = "running"      # 执行中
    DONE = "done"            # 成功完成
    FAILED = "failed"        # 执行失败

# 状态转移规则
JOB_STATUS_TRANSITIONS = {
    JobStatus.PENDING: [JobStatus.RUNNING],
    JobStatus.RUNNING: [JobStatus.DONE, JobStatus.FAILED],
    JobStatus.DONE: [],       # 终态，不允许转移
    JobStatus.FAILED: []      # 终态，不允许转移
}

def validate_status_transition(current: JobStatus,
                               target: JobStatus) -> bool:
    """验证状态转移是否合法"""
    if target not in JOB_STATUS_TRANSITIONS.get(current, []):
        raise WorkflowError(
            f"非法状态转移: {current.value} -> {target.value}"
        )
    return True
```

使用时：

```python
def update_job_status(job_id: str, new_status: JobStatus) -> None:
    """更新任务状态"""
    current_status = self.db.get_job_status(job_id)

    # 验证转移
    validate_status_transition(current_status, new_status)

    # 执行更新
    self.db.update_job(
        job_id,
        status=new_status.value,
        updated_at=datetime.utcnow()
    )

    logger.info(
        f"任务状态转移: job_id={job_id}, "
        f"{current_status.value} -> {new_status.value}"
    )
```

### 6.4 数据备份策略

**SHOULD**：每次重要操作前自动备份数据库。

```python
def backup_database(db_path: Path, backup_dir: Optional[Path] = None) -> Path:
    """备份数据库"""
    backup_dir = backup_dir or db_path.parent / ".backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"app_{timestamp}.db.bak"

    import shutil
    shutil.copy2(db_path, backup_path)

    logger.info(f"数据库已备份: {backup_path}")
    return backup_path

# 在关键操作前调用
def safe_migrate(db_path: Path) -> None:
    """安全迁移，带备份"""
    backup_database(db_path)
    Migration.migrate(db_path)
```

---

## 7. 资源管理规范

### 7.1 临时文件管理

**MUST**：所有临时文件使用统一目录与清理策略。

```python
# modules/utils/temp_file_manager.py

class TempFileManager:
    """临时文件管理器"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(tempfile.gettempdir()) / "videoeditor"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.tracked_files = set()

    def create_temp_file(self, suffix: str = "") -> Path:
        """创建临时文件"""
        fd, path = tempfile.mkstemp(suffix=suffix, dir=str(self.base_dir))
        os.close(fd)
        temp_path = Path(path)
        self.tracked_files.add(temp_path)
        logger.debug(f"创建临时文件: {temp_path}")
        return temp_path

    def create_temp_dir(self) -> Path:
        """创建临时目录"""
        temp_dir = Path(tempfile.mkdtemp(dir=str(self.base_dir)))
        self.tracked_files.add(temp_dir)
        logger.debug(f"创建临时目录: {temp_dir}")
        return temp_dir

    def cleanup(self) -> None:
        """清理所有临时文件"""
        for path in self.tracked_files:
            try:
                if path.is_dir():
                    import shutil
                    shutil.rmtree(path)
                else:
                    path.unlink()
                logger.debug(f"已清理: {path}")
            except Exception as e:
                logger.warning(f"清理失败: {path}, {e}")
        self.tracked_files.clear()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cleanup()
```

**MUST**：使用 context manager 确保资源释放。

```python
✅ def process_video(video_path: str) -> Dict[str, Any]:
    """处理视频，自动清理临时文件"""
    with TempFileManager() as temp_mgr:
        temp_audio = temp_mgr.create_temp_file(suffix=".wav")

        try:
            # 提取音频
            ffmpeg.extract_audio(video_path, str(temp_audio))

            # 分析
            result = analyze_audio(temp_audio)

            return result
        finally:
            # 自动清理
            pass  # temp_mgr.__exit__ 会调用 cleanup()

❌ def process_video(video_path: str) -> Dict[str, Any]:
    """处理视频，可能泄漏文件"""
    temp_audio = Path(tempfile.mktemp(suffix=".wav"))
    ffmpeg.extract_audio(video_path, str(temp_audio))
    result = analyze_audio(temp_audio)
    # 忘记删除 temp_audio，磁盘泄漏！
    return result
```

### 7.2 视频/音频文件处理中的内存管理

**MUST**：大文件处理使用流式处理，不一次性加载到内存。

```python
✅ def compute_audio_features(audio_path: str,
                              chunk_size: int = 4096) -> np.ndarray:
    """逐块处理音频，避免内存溢出"""
    features = []

    with open(audio_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break

            # 处理块
            pcm_data = np.frombuffer(chunk, dtype=np.int16)
            feature = compute_fft(pcm_data)
            features.append(feature)

    return np.concatenate(features, axis=0)

❌ def compute_audio_features(audio_path: str) -> np.ndarray:
    """一次性加载，大文件会 OOM"""
    with open(audio_path, 'rb') as f:
        pcm_data = np.frombuffer(f.read(), dtype=np.int16)
    return compute_fft(pcm_data)
```

### 7.3 大文件操作前的磁盘空间检查

**MUST**：大文件操作前检查磁盘空间。

```python
def check_disk_space(target_path: Path, required_bytes: int) -> bool:
    """检查磁盘空间是否充足"""
    import shutil
    stat = shutil.disk_usage(target_path)
    free_bytes = stat.free

    # 保留 10% 的缓冲
    required_with_buffer = int(required_bytes * 1.1)

    if free_bytes < required_with_buffer:
        raise StorageError(
            f"磁盘空间不足: 需要 {required_with_buffer / 1e9:.1f}GB, "
            f"可用 {free_bytes / 1e9:.1f}GB"
        )
    return True

def save_video(video_data: bytes, output_path: Path) -> None:
    """保存视频，先检查空间"""
    # 检查空间（video_data 大小 + 2 倍缓冲）
    check_disk_space(output_path.parent, len(video_data) * 2)

    with open(output_path, 'wb') as f:
        f.write(video_data)

    logger.info(f"视频已保存: {output_path} ({len(video_data) / 1e6:.1f}MB)")
```

### 7.4 子进程管理（超时、清理）

**MUST**：所有子进程都必须设置超时与清理。

```python
def run_subprocess(cmd: List[str], timeout: int = 60) -> Tuple[str, str]:
    """
    运行子进程，含超时与清理。

    Args:
        cmd: 命令行参数列表
        timeout: 超时时间（秒）

    Returns:
        (stdout, stderr)

    Raises:
        subprocess.TimeoutExpired: 超时
        subprocess.CalledProcessError: 返回值非零
    """
    proc = None
    try:
        logger.debug(f"启动子进程: {' '.join(cmd)}")
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors='replace'
        )

        stdout, stderr = proc.communicate(timeout=timeout)

        if proc.returncode != 0:
            raise subprocess.CalledProcessError(
                proc.returncode, cmd, stdout, stderr
            )

        return stdout, stderr

    except subprocess.TimeoutExpired:
        logger.error(f"子进程超时，强制终止: {' '.join(cmd[:3])}")
        if proc:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 某些进程 SIGKILL 也杀不掉
                logger.warning("无法杀死子进程")
        raise
    finally:
        if proc and proc.poll() is None:
            # 确保子进程已终止
            proc.kill()
            proc.wait()
```

---

## 8. 日志规范

### 8.1 日志格式

**MUST**：所有日志使用统一的 Python logging 模块。

```python
import logging

logger = logging.getLogger(__name__)

# 日志记录示例
logger.debug("调试信息，开发时查看")
logger.info("正常流程: 已初始化数据库")
logger.warning("警告: 磁盘空间不足")
logger.error("错误: 提取音频失败", exc_info=True)  # 含堆栈
logger.critical("严重错误: 服务启动失败")
```

**日志输出格式（标准配置）**：

```
[2026-03-19 10:30:45,123] [modules.step1_material_analysis.audio_quality] [INFO] 音频分析完成: quality_score=0.82
[2026-03-19 10:30:46,456] [modules.adapters.ffmpeg_wrapper] [ERROR] FFmpeg 失败: Command not found
  Traceback (most recent call last):
    File "ffmpeg_wrapper.py", line 42, in extract_audio
      proc.communicate(timeout=timeout)
    FileNotFoundError: FFmpeg not found
```

**配置示例**（apps/desktop/main.py）：

```python
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '[%(levelname)s] %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'detailed',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': 'logs/app.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5
        }
    },
    'root': {
        'level': 'DEBUG',
        'handlers': ['console', 'file']
    }
}

logging.config.dictConfig(LOGGING_CONFIG)
```

### 8.2 日志级别使用规则

| 级别 | 场景 | 示例 |
|-----|------|------|
| DEBUG | 开发调试，详细信息 | 参数值、中间计算结果、缓存命中 |
| INFO | 正常业务流程 | 初始化完成、任务开始/结束、数据已保存 |
| WARNING | 可恢复的问题 | 缓存失效、重试、文件权限降级 |
| ERROR | 操作失败，但程序继续 | 单个请求失败、外部调用异常、数据库查询失败 |
| CRITICAL | 系统无法继续运行 | 数据库无法连接、应用启动失败 |

### 8.3 关键操作必须记录的信息

**MUST**：关键操作需记录完整上下文。

```python
# ✅ 完整的关键操作日志
logger.info(
    f"任务开始: job_id={job_id}, step={current_step}, "
    f"params={params}, project_path={project_path}"
)

# 处理...

logger.info(
    f"任务完成: job_id={job_id}, step={current_step}, "
    f"duration={elapsed_time:.1f}s, result_size={result_size}, "
    f"status={final_status}"
)

# ❌ 日志信息不足
logger.info("任务完成")
logger.info(f"完成: {job_id}")
```

**关键操作清单**：

- 项目初始化/打开
- 步骤开始/完成/失败
- 外部 API 调用（入参、出参摘要、耗时）
- 数据库操作（CRUD 的关键字段）
- 文件系统操作（路径、大小、异常）
- 状态转移（前后状态、转移原因）
- 错误发生（错误类型、堆栈、恢复策略）

### 8.4 敏感信息脱敏

**MUST**：日志不应包含密钥、密码、个人隐私数据。

```python
✅ logger.info(f"保存 API 密钥: key_id={key_id[:8]}...")  # 仅显示前 8 字符
✅ logger.info(f"用户信息: user_id={user_id}, email_prefix={email.split('@')[0]}")
✅ logger.info(f"项目路径: {str(project_path)}")  # 路径通常无关紧要

❌ logger.info(f"保存 API 密钥: {api_key}")
❌ logger.info(f"用户信息: email={email}, phone={phone}")
❌ logger.debug(f"密码: {password}")
```

**脱敏工具函数**：

```python
def mask_secret(secret: str, show_chars: int = 8) -> str:
    """脱敏密钥"""
    if len(secret) <= show_chars:
        return "*" * len(secret)
    return secret[:show_chars] + "*" * (len(secret) - show_chars)

# 使用
logger.info(f"API 密钥: {mask_secret(api_key)}")
```

---

## 9. 配置管理规范

### 9.1 所有配置通过 settings 或环境变量

**MUST**：配置不硬编码，所有可配置项通过 Settings 类或环境变量。

```python
# modules/app_api/settings.py

from pathlib import Path
from typing import Optional
import os
import json

class Settings:
    """应用配置管理"""

    # 默认值
    DEFAULT_FFmpeg_TIMEOUT = 60
    DEFAULT_API_PORT = 5000
    DEFAULT_API_HOST = "127.0.0.1"
    DEFAULT_MODEL_CACHE_DIR = Path.home() / ".cache" / "videoeditor"

    def __init__(self):
        # 1. 加载 .env（仅本地开发）
        self._load_env_file()

        # 2. 从环境变量读取（高优先级）
        self.ffmpeg_timeout = int(
            os.getenv('VIDEOEDITOR_FFmpeg_TIMEOUT',
                      self.DEFAULT_FFmpeg_TIMEOUT)
        )
        self.api_port = int(
            os.getenv('VIDEOEDITOR_API_PORT',
                      self.DEFAULT_API_PORT)
        )
        self.api_host = os.getenv('VIDEOEDITOR_API_HOST',
                                   self.DEFAULT_API_HOST)
        self.llm_api_key = os.getenv('VIDEOEDITOR_LLM_API_KEY')
        self.model_cache_dir = Path(
            os.getenv('VIDEOEDITOR_MODEL_CACHE_DIR',
                      self.DEFAULT_MODEL_CACHE_DIR)
        )

        # 3. 创建缓存目录
        self.model_cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_env_file(self):
        """加载 .env 文件（可选）"""
        from pathlib import Path
        env_file = Path(__file__).parent.parent.parent / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, _, value = line.partition('=')
                        os.environ.setdefault(key.strip(), value.strip())

    def get_app_settings_file(self) -> Path:
        """获取应用设置文件路径"""
        # .video_library/app_settings.json
        return Path.home() / ".video_library" / "app_settings.json"

    def load_app_settings(self) -> dict:
        """从文件读取应用级设置"""
        settings_file = self.get_app_settings_file()
        if not settings_file.exists():
            return {}

        try:
            with open(settings_file) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"读取应用设置失败: {e}")
            return {}

    def save_app_settings(self, settings: dict) -> None:
        """保存应用级设置"""
        settings_file = self.get_app_settings_file()
        settings_file.parent.mkdir(parents=True, exist_ok=True)

        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=2)

        logger.info(f"应用设置已保存: {settings_file}")

# 全局单例
_settings = None

def get_settings() -> Settings:
    """获取全局设置"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

使用：

```python
from modules.app_api.settings import get_settings

settings = get_settings()
ffmpeg_timeout = settings.ffmpeg_timeout
llm_api_key = settings.llm_api_key
```

### 9.2 配置分层

**MUST**：遵循配置优先级链。

```
DEFAULT (代码中硬编码的默认值)
  ↓
.env 文件（可选，仅本地开发）
  ↓
环境变量（VIDEOEDITOR_* 前缀）
  ↓
应用级设置文件（~/.video_library/app_settings.json，用户可写）
```

示例：

```python
# 假设要配置 FFmpeg 超时

# 1. 代码默认值
DEFAULT_TIMEOUT = 60

# 2. .env 文件（开发环境）
# VIDEOEDITOR_FFmpeg_TIMEOUT=30

# 3. 环境变量（CI/CD、容器）
# export VIDEOEDITOR_FFmpeg_TIMEOUT=120

# 4. 用户通过 GUI 保存到 app_settings.json
# ~/.video_library/app_settings.json:
# {
#   "ffmpeg_timeout": 90
# }

# 最终生效优先级：app_settings.json > 环境变量 > .env > 默认值
```

### 9.3 配置禁止事项

**MUST NOT**：

- ❌ 硬编码配置值（如 `timeout = 60`）
- ❌ 直接 `os.environ['KEY']`，应通过 Settings 类
- ❌ 配置散落在各模块，应集中在 settings.py
- ❌ 敏感信息（密钥）存入版本控制，应使用 .env 或环境变量

### 9.4 .video_library/app_settings.json 的角色

**SHOULD**：应用用户配置存储在 `~/.video_library/app_settings.json`。

```json
{
  "ui": {
    "auto_approve_materials": false,
    "language": "zh",
    "theme": "light"
  },
  "ai": {
    "llm_provider": "openai",
    "model": "gpt-4o-mini"
  },
  "publish": {
    "connectors": {
      "youtube": {
        "channel_id": "UCxxxx",
        "auto_tags": ["vlog", "travel"]
      }
    }
  },
  "ffmpeg_timeout": 60,
  "model_cache_dir": "/path/to/cache"
}
```

此文件由应用保存，用户可编辑，但应通过 GUI 修改。

---

## 10. 测试规范

### 10.1 测试层次

```
单元测试 (Unit Tests)
  ↓
集成测试 (Integration Tests)
  ↓
手动端到端验证 (E2E Validation)
```

### 10.2 测试文件命名与结构

**MUST**：测试文件与被测模块对应。

```
modules/step1_material_analysis/
├── audio_quality.py
├── __init__.py
└── tests/
    ├── __init__.py
    ├── test_audio_quality.py    # 对应 audio_quality.py
    └── fixtures/
        ├── sample_video.mp4      # 测试样本
        └── expected_results.json  # 期望输出

tests/
├── test_project_relink.py        # 项目级集成测试
├── test_relink_regression.py     # 回归测试
├── fixtures/
│   ├── jianying_samples/         # 真实样本
│   └── mock_data.json
└── conftest.py                   # pytest 共享配置
```

### 10.3 单元测试规则

**MUST**：每个公共函数至少覆盖：正常路径 + 一个异常路径 + 边界条件。

```python
import pytest
from modules.step1_material_analysis.audio_quality import analyze_audio_quality
from modules.exceptions import AudioAnalysisError

class TestAudioQualityAnalyzer:
    """音频质量分析测试"""

    def test_analyze_valid_video(self, tmp_path):
        """正常路径: 有效视频分析成功"""
        # 准备
        video_file = tmp_path / "test_video.mp4"
        # 创建虚拟视频文件（或用真实样本）
        video_file.write_bytes(b"mock video")

        # 执行
        result = analyze_audio_quality(str(video_file), timeout=10)

        # 断言
        assert result['quality_score'] >= 0
        assert result['quality_score'] <= 1
        assert 'issues' in result
        assert isinstance(result['issues'], list)

    def test_analyze_nonexistent_file(self):
        """异常路径: 文件不存在"""
        with pytest.raises(FileNotFoundError):
            analyze_audio_quality("/nonexistent/video.mp4")

    def test_analyze_timeout(self, monkeypatch):
        """异常路径: 分析超时"""
        # 模拟超时
        def mock_extract(*args, **kwargs):
            import subprocess
            raise subprocess.TimeoutExpired("ffmpeg", timeout=5)

        import modules.adapters.ffmpeg_wrapper as ffmpeg_module
        monkeypatch.setattr(ffmpeg_module, "_extract_pcm", mock_extract)

        with pytest.raises(AudioAnalysisError):
            analyze_audio_quality("dummy_path.mp4", timeout=5)

    def test_analyze_empty_video(self, tmp_path):
        """边界条件: 空视频（无音频）"""
        # 创建没有音频轨道的视频文件
        video_file = tmp_path / "silent_video.mp4"
        # ... 创建无音频视频

        result = analyze_audio_quality(str(video_file))
        assert result['quality_score'] == 0
        assert '无音频' in result['issues']
```

**MUST NOT**：

- ❌ 测试依赖外部网络（除非明确集成测试）
- ❌ 测试依赖真实文件系统（应使用 tmp_path fixture）
- ❌ 测试依赖特定的环境变量（应 mock 或通过 conftest）
- ❌ 测试包含 sleep、随机延迟

**SHOULD**：使用 pytest fixtures 共享常用资源。

```python
# tests/conftest.py

import pytest
from pathlib import Path

@pytest.fixture
def sample_video(tmp_path):
    """提供示例视频文件"""
    video_file = tmp_path / "sample.mp4"
    video_file.write_bytes(b"mock video data")
    return video_file

@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """模拟 FFmpeg"""
    def mock_extract_audio(video_path, output_path, **kwargs):
        Path(output_path).write_bytes(b"pcm data")
        return True

    import modules.adapters.ffmpeg_wrapper
    monkeypatch.setattr(
        modules.adapters.ffmpeg_wrapper,
        "extract_audio",
        mock_extract_audio
    )

# 使用
def test_with_sample(sample_video, mock_ffmpeg):
    result = analyze_audio_quality(str(sample_video))
    assert result is not None
```

### 10.4 集成测试规则

**SHOULD**：集成测试验证跨模块的完整流程。

```python
# tests/test_workflow_integration.py

class TestWorkflowIntegration:
    """工作流集成测试"""

    def test_complete_analysis_pipeline(self, tmp_path):
        """完整流程: 初始化 → 分析 → 保存"""
        from modules.app_api.server import create_app
        from modules.app_api.job_store import JobStore

        # 准备
        app = create_app(db_path=str(tmp_path / "test.db"))
        client = app.test_client()

        # 初始化项目
        response = client.post('/api/init', json={
            'project_name': 'test_project',
            'description': 'Test workflow'
        })
        assert response.status_code == 200
        project_id = response.json['project_id']

        # 运行分析步骤
        response = client.post('/api/run_step', json={
            'step': 1,
            'project_id': project_id
        })
        job_id = response.json['job_id']

        # 轮询完成
        for _ in range(10):
            response = client.get(f'/api/job/{job_id}')
            if response.json['status'] in ('done', 'failed'):
                break
            time.sleep(0.5)

        assert response.json['status'] == 'done'
        assert 'materials' in response.json['result']
```

### 10.5 测试禁止事项

**MUST NOT**：

- ❌ 修改全局状态（无法并行运行）
- ❌ 依赖测试执行顺序（每个测试应独立）
- ❌ 在测试中创建真实文件而不清理
- ❌ 在测试中连接真实数据库（除非明确的集成测试）

### 10.6 最低覆盖要求

| 模块类型 | 最低行覆盖 | 说明 |
|---------|----------|------|
| 工具层封装 | 80% | FFmpeg、LLM 等调用必须覆盖成功与失败路径 |
| 业务层 | 70% | 状态机、数据转换、业务规则 |
| 接入层 API | 60% | 主要端点覆盖，可接受不测试错误处理的冗余部分 |
| 数据层 | 80% | 查询、CRUD、事务 |

使用 pytest-cov 检查：

```bash
pytest --cov=modules --cov-report=html
# 查看 htmlcov/index.html
```

---

## 11. 前端规范

### 11.1 Alpine.js 组件规范

**SHOULD**：组件应自包含，属性清晰。

```html
<!-- ✅ 清晰的组件-->
<div x-data="audioAnalyzer()" @init="loadProject()">
    <div x-show="loading" class="spinner"></div>
    <div x-show="!loading" class="result">
        <p>质量得分: <span x-text="score.toFixed(2)"></span></p>
        <button @click="startAnalysis" :disabled="isRunning">
            开始分析
        </button>
    </div>
</div>

<script>
function audioAnalyzer() {
    return {
        score: 0,
        loading: false,
        isRunning: false,

        loadProject() {
            // 初始化逻辑
        },

        startAnalysis() {
            this.isRunning = true;
            fetch('/api/capabilities/audio_voice/analyze', {
                method: 'POST',
                body: JSON.stringify({ ... })
            })
            .then(res => res.json())
            .then(data => {
                this.score = data.quality_score;
                this.isRunning = false;
            });
        }
    };
}
</script>
```

### 11.2 HTML 结构规范

**SHOULD**：语义化 HTML，避免 div 污染。

```html
✅ <article>
  <header>
    <h1>分析结果</h1>
  </header>
  <section>
    <h2>质量评分</h2>
    <p>得分: <span class="score">0.82</span></p>
  </section>
  <footer>
    <button>返回</button>
  </footer>
</article>

❌ <div id="container">
  <div id="header">
    <div id="title">分析结果</div>
  </div>
  <div id="content">
    <div id="score">得分: <div class="value">0.82</div></div>
  </div>
</div>
```

### 11.3 CSS 规范

**SHOULD**：使用一致的命名规范（BEM 或类似）。

```css
/* ✅ BEM 规范 */
.audio-analyzer {
  padding: 1rem;
}

.audio-analyzer__score {
  font-size: 2rem;
  font-weight: bold;
}

.audio-analyzer__score--danger {
  color: red;
}

.audio-analyzer__button {
  padding: 0.5rem 1rem;
}

.audio-analyzer__button:disabled {
  opacity: 0.5;
}
```

### 11.4 前后端接口约定

**MUST**：前后端通过 API 契约文档明确接口定义。

```markdown
# 音频分析 API

## 请求
POST /api/capabilities/audio_voice/analyze
Content-Type: application/json

{
  "video_path": "/path/to/video.mp4",
  "analysis_type": "full" | "quick",
  "timeout": 60
}

## 响应
200 OK

{
  "success": true,
  "data": {
    "quality_score": 0.82,
    "snr_db": 28.5,
    "issues": ["底噪偏高"],
    "duration_seconds": 120.5
  },
  "timestamp": "2026-03-19T10:30:00Z"
}

## 错误响应
400 Bad Request

{
  "success": false,
  "error": "invalid_path",
  "message": "文件不存在: /path/to/video.mp4",
  "code": 400
}
```

---

## 12. AI 开发者自检清单

**MUST**：每创建或修改一个文件后，对照以下清单。

### 基础检查

- [ ] 文件有 shebang + 模块 docstring
- [ ] 所有公共函数有完整类型标注
- [ ] 所有公共函数有 Google style docstring
- [ ] Import 语句正确、无重复
- [ ] 常量定义在文件顶部，使用 UPPER_CASE
- [ ] 函数名/类名遵循命名规范
- [ ] 无硬编码配置值（timeout、路径、API key 等）
- [ ] 代码行长不超过 100 字符（允许 URL 等例外）

### 错误处理检查

- [ ] 所有异常捕获都是具体类型（无裸 except）
- [ ] 异常被记录或重新抛出（无沉默失败）
- [ ] 业务错误使用自定义异常类（来自 exceptions.py）
- [ ] API 路由异常由全局 handler 处理
- [ ] 所有外部调用（FFmpeg、LLM、网络）有超时设置
- [ ] 超时异常有重试逻辑或明确的降级方案

### 资源管理检查

- [ ] 临时文件使用 TempFileManager 或 context manager
- [ ] 文件操作使用 try...finally 或 with 语句
- [ ] 子进程有超时、kill 逻辑
- [ ] 大文件处理使用流式处理（无 OOM 风险）
- [ ] 数据库连接在 finally 中关闭
- [ ] 网络请求有连接超时（socket.timeout）

### 接口一致性检查

- [ ] 如果修改了公共 API，是否更新了契约文档
- [ ] 函数签名与文档描述一致
- [ ] 返回值类型与 docstring 一致
- [ ] 异常列表与实际抛出异常一致
- [ ] 如果改动了状态机，是否更新了定义文件

### 测试覆盖检查

- [ ] 有相应的单元测试文件（test_xxx.py）
- [ ] 至少覆盖：正常路径、一个异常路径、边界条件
- [ ] 使用 mock/fixture，不依赖真实资源
- [ ] 测试独立，无序列依赖
- [ ] 测试通过

### 日志检查

- [ ] 关键操作有日志记录（INFO 级别）
- [ ] 异常有日志记录，含堆栈（ERROR 级别）
- [ ] 日志不包含敏感信息（密钥、密码、隐私数据）
- [ ] 日志消息有上下文（参数、返回值摘要）
- [ ] 使用统一的日志前缀标记模块

### 代码审查检查

- [ ] 无死代码、无注释掉的代码
- [ ] TODO/FIXME/HACK 标记清晰，有说明
- [ ] 注释仅用于非显而易见的逻辑
- [ ] 变量名有意义，无单字母（除了循环变量）
- [ ] 函数长度合理（不超过 50 行）
- [ ] 没有明显的重复代码（可提取方法）

---

## 13. 安全基线

### 13.1 API 认证

**SHOULD**：非公开 API 应有认证机制。

```python
from functools import wraps
import secrets

def require_api_token(f):
    """API token 验证装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-API-Token')
        if not token or token != os.getenv('VIDEOEDITOR_API_TOKEN'):
            return jsonify({
                "success": False,
                "error": "unauthorized",
                "message": "无效的 API token"
            }), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/admin/reset', methods=['POST'])
@require_api_token
def reset_database():
    """重置数据库（需要认证）"""
    pass
```

### 13.2 密钥存储

**MUST**：密钥不进 git，存在 .env 或环境变量。

```
.gitignore:
  .env
  *.key
  secrets/

.env (本地开发，不提交):
  VIDEOEDITOR_LLM_API_KEY=sk-xxxx
  VIDEOEDITOR_DB_PASSWORD=xxxxx
```

### 13.3 输入校验

**MUST**：所有来自用户的输入都要校验。

```python
def validate_file_path(file_path: str, allowed_dir: Path) -> Path:
    """验证文件路径，防止路径遍历"""
    path = Path(file_path).resolve()

    # 检查是否在允许目录内
    try:
        path.relative_to(allowed_dir.resolve())
    except ValueError:
        raise ValidationError(f"路径超出允许范围: {file_path}")

    # 检查文件是否存在
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    return path

# 使用
@app.route('/api/files/<path:rel>')
def download_file(rel):
    """下载项目文件"""
    try:
        project_dir = Path("/path/to/projects") / request.args.get('project_id')
        file_path = validate_file_path(rel, project_dir)
        return send_file(file_path)
    except ValidationError as e:
        return jsonify({"error": str(e)}), 400
```

### 13.4 文件路径安全

**MUST**：避免路径注入攻击。

```python
✅ # 使用 Path.resolve() 规范化路径
video_path = Path(user_input).resolve()
if not video_path.exists():
    raise FileNotFoundError()

✅ # 校验路径在允许范围内
allowed_root = Path("/projects")
video_path.relative_to(allowed_root)  # 若超出范围抛异常

❌ # 危险: 直接拼接用户输入
video_path = f"/projects/{user_input}/video.mp4"
# 用户可能输入 "../../etc/passwd"
```

---

## 14. 与其他文档的关系

本文档的上游与下游关系：

```
上游:
  ├── modules/contracts/*           (接口规范 → 影响编码边界)
  └── docs/project_relink_dev_policy_v1.md
                                    (project_relink 特定规范 → 遵守冻结规则)

本文档 (coding-standards.md)
  │
  ├→ 每个 PR 都应对照本清单
  └→ 每个新模块都应遵循本模板
```

相关文档：

| 文档 | 关系 |
|-----|------|
| capabilities-api.md | 能力模块公共接口规范 |
| project_relink_freeze_rules_and_guardrails_v1.md | project_relink 冻结规则（补充）|
| README.md | 项目概览，非编码规范 |

---

## 15. 修订说明

### v1.0 (2026-03-19)

初版发布，涵盖：

- 系统分层与职责边界
- 命名规范（文件、类、函数、常量、数据库）
- 代码结构模板、类型标注、docstring
- 错误处理铁律与自定义异常体系
- 外部调用治理（FFmpeg、LLM、网络）
- 数据库、资源管理、日志、配置规范
- 测试规范与自检清单
- 前端规范、安全基线

### 后续维护计划

- [ ] 基于实际编码反馈补充边界案例
- [ ] 补充更多的错误处理示例（如网络超时）
- [ ] 添加性能规范章节（缓存、批量操作等）
- [ ] 完善前端测试规范

---

## 附录 A：常用导入模板

```python
# 标准库
import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# 项目内基础
from modules.exceptions import (
    VideoEditorError,
    AudioAnalysisError,
    FFmpegError,
    WorkflowError,
)

# 项目内工具
from modules.adapters.ffmpeg_wrapper import FFmpegWrapper
from modules.adapters.llm_client import LLMClient
from modules.app_api.settings import get_settings
from modules.utils.temp_file_manager import TempFileManager

# 项目内业务
from modules.step1_material_analysis.audio_quality import analyze_audio_quality
from modules.library.storage import LibraryStore

logger = logging.getLogger(__name__)
```

---

## 附录 B：pytest.ini 配置

```ini
[pytest]
# 项目根目录 pytest 配置
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*

# 覆盖率配置
addopts =
    --cov=modules
    --cov-report=html:htmlcov
    --cov-report=term-missing
    --cov-fail-under=70
    -v

# 测试超时（防止无限等待）
timeout = 30

# 禁用网络访问（除非在 markers 中标记）
markers =
    integration: 集成测试，可能使用网络或真实资源
    slow: 慢速测试
```


---

## 附录 C：质量铁律（v1.18 新增，交叉引用 dev-governance.md §14）

### 铁律 #21：禁止静默降级实现

开发计划明确要求的技术方案（embedding 模型、算法策略、API 字段等），编码时**必须按计划执行**。

**禁止行为举例**：
- 计划要求 embedding 向量搜索 → 编码时偷换为 keyword 关键字匹配
- 计划要求 3 种检索策略 → 编码时只实现 2 种
- 计划要求返回特定 API 字段 → 编码时省略部分字段

**处理方式**：无法按计划实现 → 停止并报告原因，由用户决定是否接受降级方案。AI 不得自行决定降级。

### 铁律 #22：Phase 4 审计逐条验收

Phase 4 审计中，**禁止模糊声称"基本完成"或"大部分满足"**。

每条验收标准必须明确标注：
- ✅ 已实现（附具体证据：测试输出 / API 响应 / 截图）
- ❌ 未实现（附原因 + 影响评估）

### 铁律 #23：完成前必须有证据（§13.5）

禁止无证据声称完成。Phase 6 汇报前必须：运行验证命令 → 阅读输出 → 逐条标注 ✅/❌ → 全部 ✅ 才可声明完成。

### 铁律 #24：门禁失败禁止简单重试（§13.2）

门禁失败时必须执行系统化调试（D1 根因 → D2 模式匹配 → D3 假设验证 → D4 修复）。最多 3 次修复尝试，超过则停止等待用户介入。

---

**文档完**
