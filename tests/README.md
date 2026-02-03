# 测试框架说明

本项目已完全迁移到标准的 pytest 测试框架。

## 测试结构

```
tests/
├── __init__.py
├── unit/                        # 单元测试（不依赖设备/ADB）
│   └── __init__.py
└── integration/                 # 集成测试（依赖设备/ADB/网络/Mock）
    ├── __init__.py
    ├── test_system_robustness.py    # 系统健壮性测试
    ├── test_exception_recovery.py   # 异常恢复测试
    └── test_performance.py          # 性能测试
```

## 运行测试

### 命令行方式

```bash
# 运行所有测试
pytest tests/

# 运行特定模块的测试
pytest tests/ -m system_robustness
pytest tests/ -m exception_recovery
pytest tests/ -m performance

# 运行特定测试文件
pytest tests/integration/test_system_robustness.py

# 运行特定测试方法
pytest tests/integration/test_performance.py::TestPerformanceMetrics::test_cold_start_time

# 生成 HTML 报告
pytest tests/ --html=reports/pytest_report.html --self-contained-html
```

### 通过 main.py 运行

```bash
# 使用 pytest 框架（默认）
python main.py --stability -s device_sn --apk-path path/to/app.apk
```

### 模块化测试

```bash
# 仅运行系统健壮性测试
pytest tests/ -m system_robustness

# 仅运行异常恢复测试
pytest tests/ -m exception_recovery

# 仅运行性能测试
pytest tests/ -m performance

# 仅运行响应性能测试
pytest tests/ -m performance_response

# 仅运行资源消耗测试
pytest tests/ -m performance_resource
```

## 命令行参数

pytest 支持以下自定义参数（通过 conftest.py 定义）：

- `--device-sn`: 设备序列号
- `--apk-path`: APK 包本地路径
- `--apk-url`: APK 包网络地址
- `--module-robustness`: 启用系统健壮性测试模块
- `--module-recovery`: 启用异常恢复测试模块
- `--module-performance`: 启用完整性能测试模块
- `--module-response`: 启用响应性能测试模块
- `--module-resource`: 启用资源消耗测试模块
- `--establish-baseline`: 建立性能基线
- `--compare-baseline`: 对比性能基线

## 测试标记（Markers）

- `@pytest.mark.stability`: 稳定性测试标记
- `@pytest.mark.system_robustness`: 系统健壮性测试标记
- `@pytest.mark.exception_recovery`: 异常恢复测试标记
- `@pytest.mark.performance`: 性能测试标记
- `@pytest.mark.performance_response`: 响应性能测试标记
- `@pytest.mark.performance_resource`: 资源消耗测试标记
- `@pytest.mark.slow`: 慢速测试标记（长时间运行）
- `@pytest.mark.requires_device`: 需要真实设备连接的测试
- `@pytest.mark.requires_mock_server`: 需要 Mock Server 的测试
- `@pytest.mark.requires_network_proxy`: 需要网络代理的测试

## Fixtures

所有共享的测试资源都通过 conftest.py 中的 fixtures 提供：

- `test_config`: 测试配置
- `project_config`: 项目配置
- `device_sn`: 设备序列号
- `device`: 设备对象
- `device_log`: 设备日志对象
- `package_path`: APK 包路径
- `package`: 包对象
- `stability_framework`: 稳定性测试框架（类级别）
- `modular_framework`: 模块化测试框架（类级别）
- `mock_server`: Mock Server（会话级别）

## 报告生成

### HTML 报告

```bash
pytest tests/ --html=reports/pytest_report.html --self-contained-html
```

报告将保存在 `reports/pytest_report.html`。

### JSON 报告（可选）

如果需要 JSON 格式的报告，可以安装 `pytest-json-report`：

```bash
pip install pytest-json-report
pytest tests/ --json-report --json-report-file=reports/pytest_report.json
```

## 配置

pytest 配置文件：`pytest.ini`

主要配置项：
- 测试文件匹配模式
- 测试目录
- 命令行选项
- 标记说明
- 日志配置

## 注意事项

1. **设备连接**：运行测试前确保设备已连接并通过 `adb devices` 验证
2. **APK 路径**：必须提供有效的 APK 包路径（通过 `--apk-path` 参数或配置文件）
3. **长时间测试**：系统健壮性测试可能需要数小时，使用 `-m slow` 标记可以跳过这些测试
4. **Mock Server**：某些测试需要 Mock Server，确保 Mock Server 已正确配置和启动

## 迁移说明

从自定义测试框架迁移到 pytest 后：

1. ✅ 所有测试用例遵循 `test_*` 命名规范
2. ✅ 使用 pytest fixtures 管理共享资源
3. ✅ 使用 pytest markers 实现模块化测试
4. ✅ 支持 pytest 的所有标准功能（参数化、跳过、标记等）
5. ✅ 生成标准的 pytest HTML 报告
6. ✅ 保持与现有配置文件的兼容性
7. ✅ GUI 界面已更新以支持 pytest

## 向后兼容性

为了保持向后兼容性，`main.py` 仍然支持 `--no-pytest` 参数来使用旧的自定义框架。但推荐使用 pytest 框架。
