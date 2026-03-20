# project_relink Adapter Contract v1.0

## 1. 文档定位

本文档定义 `ProjectRelinkAdapter` 的接口契约。任何新 NLE 格式（如 FCPXML、DaVinci Resolve、Premiere Pro）必须先实现此契约，再接入 `project_relink` 系统。

适用文件：`modules/library/project_relink_adapter.py`

---

## 2. Adapter ABC 定义

```python
class ProjectRelinkAdapter(ABC):
    @property
    @abstractmethod
    def project_type(self) -> str: ...

    @abstractmethod
    def validate(self, project_path: str) -> Dict: ...

    @abstractmethod
    def parse_references(self, project_path: str) -> List[Dict]: ...

    @abstractmethod
    def apply_relink(self, project_path: str, output_path: str, path_map: Dict[str, str]) -> Dict: ...

    @abstractmethod
    def get_version_info(self, project_path: str) -> Dict: ...
```

---

## 3. 方法契约

### 3.1 `project_type` (property)

返回唯一标识符，用于 adapter registry 和数据库存储。

- 类型：`str`
- 示例：`"jianying"`, `"fcpxml"`, `"resolve"`
- 约束：全小写，无空格，不可变

### 3.2 `validate(project_path) -> Dict`

验证工程文件是否可读、结构是否合法。

输入：
- `project_path: str` — 工程文件绝对路径

输出：
```python
{
    "valid": bool,          # 是否可以被 parse
    "errors": [str],        # 致命错误列表
    "warnings": [str],      # 非致命提示
    "version_info": {}      # 提取的版本/元信息
}
```

约束：
- 只读操作，不修改文件
- 文件不存在或不可读时返回 `valid=False` + errors
- `version_info` 格式不强制，但建议包含 `app_version` 和 `draft_version`

### 3.3 `parse_references(project_path) -> List[Dict]`

解析工程中的所有素材引用。

输入：
- `project_path: str` — 工程文件绝对路径

输出：每条引用为一个 dict：
```python
{
    "asset_name": str,      # 文件名（如 "clip.mp4"）
    "old_path": str,        # 工程中存储的路径（绝对或相对）
    "source_ref": str,      # 工程内唯一 ID（如 material_id）
    "media_type": str,      # "video" | "audio"
    "size_bytes": int|None  # 文件大小提示（可选）
}
```

约束：
- 只读操作，不修改文件
- `old_path` 为空或缺失的条目必须跳过
- `source_ref` 是继承匹配的第一优先级键，必须尽可能填充
- `media_type` 只允许 `"video"` 或 `"audio"`
- 去重由调用方（`build_project_relink_map`）处理，adapter 返回原始列表即可

### 3.4 `apply_relink(project_path, output_path, path_map) -> Dict`

将路径替换应用到工程副本。

输入：
- `project_path: str` — 原始工程文件
- `output_path: str` — 输出副本路径
- `path_map: Dict[str, str]` — `{old_path: new_path}` 替换映射

输出：
```python
{
    "applied": int,     # 成功替换的条目数
    "skipped": int      # 未匹配的映射数
}
```

约束：
- **绝不修改原始工程文件**（冻结规则 §2.6）
- 只替换 `path_map` 中精确匹配的路径
- 输出文件的父目录不存在时自动创建
- 保持原始工程文件的编码格式（UTF-8）

### 3.5 `get_version_info(project_path) -> Dict`

提取工程版本/元信息。

输出（建议字段）：
```python
{
    "app_version": str|None,
    "draft_version": str|None
}
```

约束：
- 只读操作
- 解析失败时返回空 dict `{}`

---

## 4. Adapter 注册

新 adapter 必须注册到 `ADAPTERS` 字典：

```python
ADAPTERS: Dict[str, type] = {
    "jianying": JianyingRelinkAdapter,
    "fcpxml": FCPXMLRelinkAdapter,  # 未来
}
```

注册后，`get_adapter(project_type)` 即可获取实例。

---

## 5. 新 NLE 接入检查清单

接入新格式前必须完成以下清单：

### 5.1 前置条件
- [ ] 阅读《project_relink 维护与交接手册》
- [ ] 阅读《project_relink 版本冻结规则》
- [ ] 确认不触及任何冻结红线

### 5.2 实现要求
- [ ] 实现 `ProjectRelinkAdapter` 全部 4 个抽象方法 + 1 个 property
- [ ] `project_type` 返回唯一标识符
- [ ] `validate` 正确检测文件格式错误
- [ ] `parse_references` 返回标准格式的引用列表
- [ ] `apply_relink` 绝不修改原始文件
- [ ] `get_version_info` 解析失败返回空 dict

### 5.3 测试要求
- [ ] 至少 3 个真实工程样本作为测试 fixture
- [ ] 覆盖 parse → relink → apply 完整链路
- [ ] 覆盖 CJK 文件名、特殊字符路径
- [ ] 覆盖空工程（无素材）边界情况
- [ ] 性能测试：100+ 素材引用的工程在 5 秒内完成

### 5.4 集成要求
- [ ] 注册到 `ADAPTERS` 字典
- [ ] API 路由中 `project_type` 参数支持新类型
- [ ] 前端下拉选择器增加新类型
- [ ] 回归测试全量通过

---

## 6. 已实现 Adapter 列表

| project_type | 类名 | 文件格式 | 状态 |
|---|---|---|---|
| `jianying` | `JianyingRelinkAdapter` | JSON (`draft_content.json` / `template.json`) | ✅ 已完成 |

---

## 7. 关键原则

1. **adapter 只负责格式转换**，不负责 relink 逻辑
2. **relink 引擎与 adapter 完全解耦**，引擎只看标准引用列表
3. **apply 永远生成副本**，绝不覆盖原始工程
4. **source_ref 必须尽可能填充**，这是继承匹配的第一优先级
5. **新 adapter 不得绕开已有 contract**，即使某些字段对该格式无意义
