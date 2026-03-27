## 贡献指南

感谢你愿意为 **MonkeyAutoTest** 做出贡献！本项目已经逐步引入分层架构与工程化工具，下面是参与开发的基本约定。

### 1. 开发环境

1. 安装 Python（建议 3.13，与 `.python-version` 一致）。
2. 在项目根目录创建虚拟环境并安装依赖（任选其一）：

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

或使用 `uv`：

```bash
pip install uv
uv sync
```

### 2. 代码风格

- 请遵循 `CODING_STYLE.md` 中的目录分层、命名、日志与异常处理约定。
- 新增模块时优先放在合适的分层目录：
  - GUI 相关 → `gui/`
  - 核心业务逻辑/领域模型 → `core/`
  - ADB、配置、日志、网络代理、Mock Server → `infra/`
  - 报告相关逻辑 → `reports/`
- 避免在新代码中引入对 `utils/` 的直接耦合，如有需要请先在 `infra/` 或 `core/` 中增加一层封装。

### 3. 提交流程建议

每次提交前建议执行：

```bash
# 基础静态检查（后续会在 pre-commit 中自动执行）
ruff check .

# 可选：类型检查与测试
mypy core infra gui
pytest -q
```

在提交信息中简要说明 **动机（Why）** 与 **主要更改点（What）**，例如：

> refactor: extract GUI toolkit to gui/toolkit.py  
> feat: add StabilityTestService and domain TestPlan

### 4. 测试与回归

- 对稳定性/压力测试框架的改动，至少需要跑一轮 **快速冒烟用例**（标记为 `stability_smoke` 的 pytest 测试）。
- 修改 GUI 相关逻辑时，建议手动验证：
  - GUI 能正常启动与关闭；
  - 核心操作（设备检测、启动/停止测试、查看报告）无明显异常；
  - 日志窗口仍能实时刷新。

### 5. 架构演进建议

如果你的改动涉及到：

- 新的测试模块（例如新增一种压力测试场景）；
- 对现有分层结构的调整；
- 公共服务接口行为的变化；

请在 PR 或变更说明中简要描述：

- 变更背景与目标；
- 涉及到的目录与模块；
- 是否需要额外的迁移步骤或兼容性考虑。

### 6. 提问与讨论

在进行较大规模重构或引入新依赖前，建议先在说明文档或评论中写下你的设计思路，包含：

- 当前痛点与问题；
- 几种可选方案的优缺点；
- 选择某个方案的理由。

这样可以让后续维护者更容易理解你的决策，也便于后续继续演进。

