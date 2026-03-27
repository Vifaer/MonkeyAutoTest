# MonkeyAutoTest

车载端侧应用自动化测试工具，提供 GUI 与命令行两种入口，支持稳定性测试、性能监控、异常恢复、广播/TTS 压测与报告生成。

## 文档导航

- 架构说明：`ARCHITECTURE.md`
- GUI 使用手册：`README-GUI.md`
- 代码风格：`CODING_STYLE.md`
- 贡献指南：`CONTRIBUTING.md`

## 当前架构（与代码一致）

项目采用分层架构，依赖方向为 `gui/main.py -> core -> infra/reports`，并在迁移期允许 `core/infra/reports` 通过适配调用 `utils` 存量能力。

- `gui/`：界面展示、交互与事件绑定
- `core/`：测试计划、业务编排与服务入口
- `infra/`：ADB、配置、日志、网络等基础设施能力
- `reports/`：报告模型、生成与重构
- `utils/`：存量模块（逐步迁移中）

详细分层约束请以 `ARCHITECTURE.md` 为准。

## 环境前提

- Python 3.13+
- 可用的 `adb`（系统 PATH 或项目内 `tools/adb/adb.exe`）
- 建议使用虚拟环境

## 安装

在项目根目录执行以下任一方式：

```bash
pip install uv
uv sync
```

或：

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

## 启动方式

### 1) GUI 启动（推荐）

```bash
python gui_main.py
```

GUI 详细说明、参数解释、模块配置与遮罩配置步骤请见 `README-GUI.md`。

### 2) 命令行启动

#### 稳定性测试

```bash
python main.py --stability -s <device_sn> -p <apk_path>
```

常用扩展参数：

```bash
python main.py --stability --duration 2 -s <device_sn> -p <apk_path>
python main.py --stability --performance-only -s <device_sn> -p <apk_path>
python main.py --stability --robustness-only -s <device_sn> -p <apk_path>
```

#### 传统 Monkey（兼容入口）

```bash
python main.py -v <version> -s <device_sn> -p <apk_path> -r <recipient>
```

> 传统 Monkey 的详细机制与参数调优不在本 README 展开。

## 关键配置文件

- `conf/project.json`：项目版本、包信息、模块化配置
- `conf/test_ui_config.json.example`：GUI 配置示例（实际文件 `conf/test_ui_config.json`）
- `baselines/performance_baseline.json.example`：性能基线示例（实际文件 `baselines/performance_baseline.json`）

## 常见问题（简版）

- 设备未识别：确认 USB 调试与 `adb devices` 输出
- 启动失败：检查 `adb` 路径、APK 路径与设备 SN
- 配置异常：优先参考 `.example` 文件重建本地配置

## 工程化检查

```bash
ruff check .
ruff format .
mypy core infra gui
pytest -q
```
