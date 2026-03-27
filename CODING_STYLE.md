## 代码风格与架构约定

本项目采用 **分层架构 + 显式领域模型**，并配合统一的编码规范与工具链，以提高长期可维护性。

### 1. 目录与分层

- `gui/`：GUI 层，只负责界面和事件绑定，不直接操作 adb/pytest/文件系统。
- `core/`：核心业务逻辑与领域模型，例如测试计划、测试结果、报告服务等。
- `infra/`：基础设施层，封装 ADB、配置、日志、Mock Server、网络代理等外部依赖。
- `reports/`：报告子域，负责测试结果到报告的适配。
- `utils/`：存量工具代码，逐步迁移到上述分层中。

依赖方向：`gui` / `main.py` → `core` → `infra` / `reports`（禁止反向依赖）。

### 2. 命名规范

- **模块/包**：`snake_case`，按功能命名，例如 `stability_service.py`、`mock_server.py`。
- **类**：`PascalCase`，例如 `StabilityTestService`、`GuiContext`。
- **函数/方法**：`snake_case`，动词开头，例如 `run_with_pytest`、`load_project_config`。
- **常量**：全大写 + 下划线，例如 `PAUSE_TIMEOUT_SECONDS`。
- **私有实现细节**：前缀 `_`，例如 `_run_single_device_test`。

### 3. 日志规范

- 使用 `infra.logging.setup_logging` 统一初始化日志。
- 业务代码中使用模块级 `logging`，不要再调用 `basicConfig`。
- 日志前缀建议包含子域信息，例如：
  - 稳定性框架：`[stability] ...`
  - 设备异常：`[device-exc] ...`
  - 网络代理：`[net-proxy] ...`
- 区分日志级别：
  - `logging.debug`：调试细节（默认可以关闭）。
  - `logging.info`：关键流程节点、成功步骤。
  - `logging.warning`：可恢复问题或降级处理。
  - `logging.error`：导致当前操作失败的问题。
  - `logging.critical`：影响整体测试框架运行的严重问题。

### 4. 异常处理约定

- **核心规则**：在“边界”层（GUI 事件处理、CLI 命令入口、线程入口）捕获异常并记录日志，其余内部函数尽量抛出异常由上层统一处理。
- 仅在以下场景静默吞掉异常：
  - 不影响主要流程的 UI 美化、Tooltip、非关键统计信息等。
  - 清理/关闭操作中的容错（例如关闭网络代理失败可以忽略）。
- 避免裸 `except:`，尽量使用 `except Exception as e:` 并记录异常信息。
- 不在库函数中调用 `sys.exit`，将退出码通过返回值或 `TestResultSummary` 传递给最外层入口。

### 5. 类型注解与文档

- 所有公共函数/类（对外暴露的 API）必须添加 **类型注解**。
- 内部辅助函数建议逐步补充类型注解，特别是涉及结构化数据（dict/list）的地方。
- 复杂函数建议编写简短 docstring，说明：
  - 参数与返回值含义
  - 可能抛出的关键异常
  - 非直观的设计取舍

示例：

```python
from typing import List

def build_pytest_args(plan: StabilityTestPlan) -> List[str]:
    """根据测试计划构建 pytest 参数列表。"""
    ...
```

### 6. GUI 代码约定

- 所有跨线程更新 UI 的操作必须通过 `root.after` 或线程安全的队列完成，禁止在非 UI 线程直接调用 Tk 控件方法。
- 复用通用 UI 元素（颜色/字体/Tooltip等）时统一从 `gui.toolkit` 导入。
- 新增 GUI 组件时优先拆分成子模块（例如 `gui/report_viewer.py`），避免继续膨胀 `gui_main.py`。

### 7. 测试与工具

- 单元测试与集成测试使用 `pytest`，测试文件放在 `tests/` 目录，命名为 `test_*.py`。
- 新增核心功能时，应至少补充一个冒烟测试或集成测试。
- 代码格式与 Lint：
  - 使用 `ruff` 进行 Lint 与基础格式化。
  - 行宽建议 100 字符以内，遇到长表达式优先折行。

详细的工具配置与使用方式见 `CONTRIBUTING.md`。

