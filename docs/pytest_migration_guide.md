# pytest 框架迁移指南

本文档说明如何从自定义测试框架迁移到标准的 pytest 框架。

## 迁移概述

项目已完全重构为使用标准的 pytest 测试框架，替代了原有的自定义测试框架。所有测试用例现在遵循 pytest 的约定和最佳实践。

## 主要变化

### 1. 测试文件结构

**之前**：测试逻辑分散在 `utils/stability_test.py` 中的类方法中

**现在**：测试用例位于 `tests/` 目录下，遵循 `test_*.py` 命名规范

```
tests/
├── __init__.py
├── test_system_robustness.py    # Monkey 模式压力测试
├── test_exception_recovery.py   # 异常恢复测试
└── test_performance.py          # 性能测试
```

### 2. 测试执行方式

**之前**：
```python
framework = StabilityTestFramework(device_sn, package, config)
framework.run_comprehensive_test()
```

**现在**：
```bash
pytest tests/ --device-sn device_sn --apk-path path/to/app.apk
```

### 3. 配置管理

**之前**：配置通过字典传递

**现在**：使用 pytest fixtures 集中管理（`conftest.py`）

### 4. 模块化测试

**之前**：通过 `ModularStabilityTest` 类和 `enabled_modules` 参数

**现在**：使用 pytest markers 和命令行参数

```bash
# 仅运行 Monkey 模式压力测试
pytest tests/ -m system_robustness

# 仅运行性能测试
pytest tests/ -m performance
```

## 使用方式

### 命令行执行

#### 基本用法

```bash
# 运行所有测试
pytest tests/

# 运行特定模块
pytest tests/ -m system_robustness
pytest tests/ -m exception_recovery
pytest tests/ -m performance

# 指定设备和APK
pytest tests/ --device-sn emulator-5554 --apk-path path/to/app.apk
```

#### 生成报告

```bash
# HTML 报告（推荐）
pytest tests/ --html=reports/pytest_report.html --self-contained-html

# 详细输出
pytest tests/ -v

# 简短输出
pytest tests/ -q
```

### 通过 main.py 执行

```bash
# 使用 pytest（默认）
python main.py --stability -s device_sn --apk-path path/to/app.apk

# 禁用 pytest，使用旧框架（不推荐）
python main.py --stability -s device_sn --apk-path path/to/app.apk --no-pytest
```

### GUI 界面

GUI 界面已更新，默认启用 pytest 框架。在测试配置窗口中：

1. 勾选"使用pytest框架（推荐，默认启用）"
2. 选择测试模式（完整测试或模块化测试）
3. 配置测试参数
4. 点击"开始稳定性测试"

## 测试标记（Markers）

pytest 使用标记来组织和过滤测试：

| 标记 | 说明 | 示例 |
|------|------|------|
| `@pytest.mark.stability` | 稳定性测试 | 所有稳定性相关测试 |
| `@pytest.mark.system_robustness` | Monkey 模式压力测试 | 长时间压力测试 |
| `@pytest.mark.exception_recovery` | 异常恢复测试 | 网络异常、数据异常测试 |
| `@pytest.mark.performance` | 性能测试 | 性能指标测试 |
| `@pytest.mark.performance_response` | 响应性能测试 | 冷启动、响应延迟测试 |
| `@pytest.mark.performance_resource` | 资源消耗测试 | CPU、内存测试 |
| `@pytest.mark.slow` | 慢速测试 | 长时间运行的测试 |
| `@pytest.mark.requires_device` | 需要设备 | 需要真实设备连接的测试 |
| `@pytest.mark.requires_mock_server` | 需要 Mock Server | 需要 Mock Server 的测试 |

### 使用标记过滤测试

```bash
# 运行所有稳定性测试
pytest tests/ -m stability

# 运行 Monkey 模式压力测试（排除慢速测试）
pytest tests/ -m "system_robustness and not slow"

# 运行性能测试
pytest tests/ -m performance
```

## Fixtures

所有共享资源通过 fixtures 提供，定义在 `conftest.py` 中：

### 配置 Fixtures

- `test_config`: 测试配置（从配置文件加载）
- `project_config`: 项目配置（从 `conf/project.json` 加载）

### 设备 Fixtures

- `device_sn`: 设备序列号（从命令行参数或环境变量获取）
- `device`: 设备对象
- `device_log`: 设备日志对象

### 包 Fixtures

- `package_path`: APK 包路径（从命令行参数或配置文件获取）
- `package`: 包对象

### 测试框架 Fixtures

- `stability_framework`: 稳定性测试框架（类级别）
- `modular_framework`: 模块化测试框架（类级别）

### Mock Server Fixtures

- `mock_server`: Mock Server 实例（会话级别，自动启动和停止）

## 命令行参数

pytest 支持以下自定义参数（通过 `conftest.py` 定义）：

| 参数 | 说明 | 示例 |
|------|------|------|
| `--device-sn` | 设备序列号 | `--device-sn emulator-5554` |
| `--apk-path` | APK 包本地路径 | `--apk-path path/to/app.apk` |
| `--apk-url` | APK 包网络地址 | `--apk-url http://example.com/app.apk` |
| `--module-robustness` | 启用 Monkey 模式压力测试模块 | `--module-robustness` |
| `--module-recovery` | 启用异常恢复测试模块 | `--module-recovery` |
| `--module-performance` | 启用完整性能测试模块 | `--module-performance` |
| `--module-response` | 启用响应性能测试模块 | `--module-response` |
| `--module-resource` | 启用资源消耗测试模块 | `--module-resource` |
| `--establish-baseline` | 建立性能基线 | `--establish-baseline` |
| `--compare-baseline` | 对比性能基线 | `--compare-baseline` |

## 报告生成

### HTML 报告

pytest-html 插件用于生成 HTML 报告：

```bash
pytest tests/ --html=reports/pytest_report.html --self-contained-html
```

报告包含：
- 测试摘要（通过/失败/跳过）
- 详细的测试结果
- 执行时间
- 错误信息和堆栈跟踪

### JSON 报告（可选）

如果需要 JSON 格式的报告：

```bash
pip install pytest-json-report
pytest tests/ --json-report --json-report-file=reports/pytest_report.json
```

## 向后兼容性

为了保持向后兼容性：

1. **main.py 支持 `--no-pytest` 参数**：可以禁用 pytest，使用旧的自定义框架
2. **配置文件兼容**：现有的配置文件（`conf/project.json`、`conf/test_ui_config.json`）仍然有效
3. **API 兼容**：`utils/stability_test.py` 中的类和方法仍然保留，供旧代码使用

## 迁移检查清单

- [x] 创建 `conftest.py` 集中管理 fixtures
- [x] 创建 `tests/` 目录和测试文件
- [x] 重构测试用例为 pytest 风格
- [x] 使用 pytest markers 实现模块化测试
- [x] 更新 `main.py` 默认使用 pytest
- [x] 更新 GUI 界面支持 pytest
- [x] 配置 pytest-html 报告生成
- [x] 创建 pytest.ini 配置文件
- [x] 更新 requirements.txt 包含 pytest 依赖
- [x] 编写迁移文档

## 常见问题

### Q: 如何跳过需要设备的测试？

A: 使用标记过滤：
```bash
pytest tests/ -m "not requires_device"
```

### Q: 如何只运行快速测试？

A: 排除慢速测试：
```bash
pytest tests/ -m "not slow"
```

### Q: 测试失败后如何调试？

A: 使用详细输出和交互式调试：
```bash
pytest tests/ -v --tb=long
pytest tests/ --pdb  # 进入调试器
```

### Q: 如何并行运行测试？

A: 安装 pytest-xdist：
```bash
pip install pytest-xdist
pytest tests/ -n auto  # 自动检测CPU核心数
```

## 下一步

1. 运行测试验证功能：`pytest tests/ -v`
2. 查看生成的报告：`reports/pytest_report.html`
3. 根据需要调整测试用例和配置
4. 集成到 CI/CD 流程中

## 参考资源

- [pytest 官方文档](https://docs.pytest.org/)
- [pytest-html 文档](https://pytest-html.readthedocs.io/)
- [pytest fixtures 文档](https://docs.pytest.org/en/stable/fixture.html)
- [pytest markers 文档](https://docs.pytest.org/en/stable/how-to/mark.html)
