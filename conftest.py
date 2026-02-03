#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pytest 配置文件和共享 fixtures
集中管理所有测试的公共资源和配置
"""

import pytest
import os
import sys
import json
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from utils import Device, Package, DeviceLog
from utils.config_io import read_json


# ==================== pytest 配置钩子 ====================

def pytest_configure(config):
    """pytest 配置钩子：注册自定义标记"""
    config.addinivalue_line("markers", "stability: 稳定性测试标记")
    config.addinivalue_line("markers", "system_robustness: 系统健壮性测试标记")
    config.addinivalue_line("markers", "exception_recovery: 异常恢复测试标记")
    config.addinivalue_line("markers", "performance: 性能测试标记")
    config.addinivalue_line("markers", "performance_response: 响应性能测试标记")
    config.addinivalue_line("markers", "performance_resource: 资源消耗测试标记")
    config.addinivalue_line("markers", "slow: 慢速测试标记（长时间运行）")
    config.addinivalue_line("markers", "requires_device: 需要真实设备连接的测试")
    config.addinivalue_line("markers", "requires_mock_server: 需要 Mock Server 的测试")
    config.addinivalue_line("markers", "requires_network_proxy: 需要网络代理的测试")
    config.addinivalue_line("markers", "stability_smoke: GUI 入口下运行的轻量稳定性用例（不包含参数化长压用例）")


def pytest_collection_modifyitems(config, items):
    """修改测试收集：自动为测试添加标记"""
    for item in items:
        # 根据测试名称自动添加标记
        test_name = item.name.lower()
        if "robustness" in test_name or "stress" in test_name or "monkey" in test_name:
            item.add_marker(pytest.mark.system_robustness)
            item.add_marker(pytest.mark.stability)
        elif "exception" in test_name or "recovery" in test_name:
            item.add_marker(pytest.mark.exception_recovery)
            item.add_marker(pytest.mark.stability)
        elif "performance" in test_name or "cold_start" in test_name or "response" in test_name:
            item.add_marker(pytest.mark.performance)
            item.add_marker(pytest.mark.stability)
        
        # 长时间运行的测试
        if "long" in test_name or "duration" in test_name or "stress" in test_name:
            item.add_marker(pytest.mark.slow)
        
        # 需要设备的测试
        if "device" in test_name or "adb" in test_name:
            item.add_marker(pytest.mark.requires_device)


# ==================== 配置 Fixtures ====================

@pytest.fixture(scope="session")
def test_config(pytestconfig):
    """加载测试配置

    优先级：
    1. pytest 自定义参数 --duration-hours（由 main.py / GUI 传入，单位：小时，可为小数）
    2. GUI 持久化配置 conf/test_ui_config.json 中的 duration + duration_unit
    3. 本地默认值（12 小时）
    """
    config_path = os.path.join("conf", "test_ui_config.json")
    gui_config = read_json(config_path, default={})

    # 默认配置
    default_config = {
        'long_stress': {
            'duration_hours': 12,
            'throttle': 700,
            'event_count': 100000
        },
        'performance': {
            'sample_interval': 30,
            'monitor_duration': 3600,
            'cold_start_threshold': 3.0,
            'response_delay_threshold': 1.5,
            'cpu_foreground_threshold': 30.0,
            'cpu_background_threshold': 1.0
        },
        'exception_recovery': {
            'network_disconnect_duration': 30,
            'weak_network_duration': 60,
            'mock_server_enabled': True,
            'network_proxy_enabled': True
        },
        'mock_server': {
            'enabled': True,
            'host': '127.0.0.1',
            'port': 8080,
            'mode': 'http',
            'rules_path': 'conf/mock_rules.json'
        },
        'network_proxy': {
            'enabled': True,
            'type': 'mitmproxy',
            'method': 'root'
        }
    }

    # 1) pytest 参数 --duration-hours（统一使用“小时”）
    duration_opt = None
    try:
        duration_opt = pytestconfig.getoption("--duration-hours", default=None)
    except Exception:
        duration_opt = None

    if duration_opt is not None:
        try:
            dur_val = float(duration_opt)
            if dur_val > 0:
                default_config['long_stress']['duration_hours'] = dur_val
        except Exception:
            logging.warning(f"解析 --duration-hours 参数失败: {duration_opt}")

    # 2) GUI 持久化配置中的 duration + duration_unit（仅在未指定 --duration-hours 时生效）
    if duration_opt is None and isinstance(gui_config, dict):
        raw_duration = gui_config.get("duration")
        unit_txt = gui_config.get("duration_unit", "小时")
        if raw_duration not in (None, ""):
            try:
                dur_value = float(raw_duration)
                if str(unit_txt).startswith("分"):
                    dur_hours = dur_value / 60.0
                else:
                    dur_hours = dur_value
                if dur_hours > 0:
                    default_config['long_stress']['duration_hours'] = dur_hours
            except Exception:
                logging.warning(f"从 GUI 配置解析测试时长失败: duration={raw_duration}, unit={unit_txt}")

    # 3) 合并 GUI 配置中的 mock_server 设置
    if isinstance(gui_config, dict) and 'mock_server' in gui_config:
        mock_server_cfg = gui_config['mock_server']
        if isinstance(mock_server_cfg, dict):
            default_config['mock_server'].update(mock_server_cfg)

    return default_config


@pytest.fixture(scope="session")
def project_config():
    """加载项目配置"""
    config_path = os.path.join("conf", "project.json")
    return read_json(config_path, default={})


# ==================== 设备 Fixtures ====================

@pytest.fixture(scope="session")
def device_sn(pytestconfig):
    """获取设备序列号（从命令行参数或环境变量）"""
    # 优先从命令行参数获取
    device_sn = pytestconfig.getoption("--device-sn", default=None)
    if device_sn:
        return device_sn
    
    # 从环境变量获取
    device_sn = os.environ.get("TEST_DEVICE_SN", None)
    if device_sn:
        return device_sn
    
    # 默认值（用于开发测试）
    return "emulator-5554"


@pytest.fixture(scope="session")
def device(device_sn):
    """设备对象 fixture"""
    return Device(device_sn)


@pytest.fixture(scope="session")
def device_log(device_sn):
    """设备日志对象 fixture"""
    log = DeviceLog(device_sn)
    log.init()
    yield log
    # 清理（如果需要）


# ==================== 包 Fixtures ====================

@pytest.fixture(scope="session")
def package_path(pytestconfig, project_config):
    """获取 APK 包路径"""
    # 如果选择测试已安装应用（package-name），则不强制要求 apk_path
    package_name = pytestconfig.getoption("--package-name", default=None)
    if package_name:
        return None

    # 优先从命令行参数获取
    apk_path = pytestconfig.getoption("--apk-path", default=None)
    if apk_path and os.path.exists(apk_path):
        return apk_path
    
    apk_url = pytestconfig.getoption("--apk-url", default=None)
    if apk_url:
        # 如果有 URL，需要下载（这里简化处理）
        logging.warning("APK URL 需要手动下载，请使用 --apk-path 指定本地路径")
    
    # 从项目配置获取默认包
    if project_config:
        # 获取第一个版本的配置
        for version_key, version_config in project_config.items():
            if isinstance(version_config, dict) and 'apk_path' in version_config:
                apk_path = version_config['apk_path']
                if os.path.exists(apk_path):
                    return apk_path
    
    # 如果都没有，返回 None（测试需要跳过）
    return None


@pytest.fixture(scope="session")
def package(package_path, device_sn, pytestconfig):
    """包对象 fixture（支持 APK 安装 / 已安装应用两种模式）"""
    package_name = pytestconfig.getoption("--package-name", default=None)
    if package_name:
        # 已安装应用模式：从设备读取包信息（存在性/版本/启动Activity）
        return Package.from_installed(device_sn, package_name)

    if package_path is None:
        pytest.skip("需要指定 APK 包路径（使用 --apk-path 参数），或使用 --package-name 选择已安装应用")
    return Package(package_path)


# ==================== 测试框架 Fixtures ====================

@pytest.fixture(scope="function")
def stability_framework(device_sn, package, test_config):
    """稳定性测试框架 fixture（类级别）"""
    from utils.stability_test import StabilityTestFramework
    
    baseline_options = {
        'establish_baseline': False,
        'compare_baseline': False
    }
    
    framework = StabilityTestFramework(device_sn, package, test_config, baseline_options)
    # 每个用例使用干净状态
    try:
        framework.reset()
    except Exception:
        pass
    yield framework


@pytest.fixture(scope="function")
def modular_framework(device_sn, package, test_config, pytestconfig):
    """模块化测试框架 fixture（类级别）"""
    from utils.stability_test import ModularStabilityTest, TestModule
    
    # 从命令行参数获取启用的模块
    enabled_modules = []
    if pytestconfig.getoption("--module-robustness", default=False):
        enabled_modules.append(TestModule.SYSTEM_ROBUSTNESS)
    if pytestconfig.getoption("--module-recovery", default=False):
        enabled_modules.append(TestModule.EXCEPTION_RECOVERY)
    if pytestconfig.getoption("--module-performance", default=False):
        enabled_modules.append(TestModule.PERFORMANCE_ALL)
    if pytestconfig.getoption("--module-response", default=False):
        enabled_modules.append(TestModule.PERFORMANCE_RESPONSE)
    if pytestconfig.getoption("--module-resource", default=False):
        enabled_modules.append(TestModule.PERFORMANCE_RESOURCE)
    
    # 如果没有指定模块，默认启用所有
    if not enabled_modules:
        enabled_modules = [
            TestModule.SYSTEM_ROBUSTNESS,
            TestModule.EXCEPTION_RECOVERY,
            TestModule.PERFORMANCE_ALL
        ]
    
    baseline_options = {
        'establish_baseline': pytestconfig.getoption("--establish-baseline", default=False),
        'compare_baseline': pytestconfig.getoption("--compare-baseline", default=False)
    }
    
    framework = ModularStabilityTest(device_sn, package, test_config, enabled_modules, baseline_options)
    try:
        framework.reset()
    except Exception:
        pass
    yield framework


# ==================== Mock Server Fixtures ====================

@pytest.fixture(scope="session")
def mock_server(test_config):
    """Mock Server fixture（会话级别）"""
    if not test_config.get('mock_server', {}).get('enabled', False):
        pytest.skip("Mock Server 未启用")
    
    from utils import mock_server as mock_server_mod
    server = mock_server_mod.MockServer(
        host=test_config['mock_server'].get('host', '127.0.0.1'),
        port=test_config['mock_server'].get('port', 8080),
        rules_path=test_config['mock_server'].get('rules_path', 'conf/mock_rules.json')
    )
    
    # 启动服务器
    server.start()
    yield server
    
    # 清理：停止服务器
    server.stop()


# ==================== 命令行参数 ====================

def pytest_addoption(parser):
    """添加自定义命令行参数"""
    parser.addoption(
        "--device-sn",
        action="store",
        default=None,
        help="设备序列号"
    )
    parser.addoption(
        "--apk-path",
        action="store",
        default=None,
        help="APK 包本地路径"
    )
    parser.addoption(
        "--apk-url",
        action="store",
        default=None,
        help="APK 包网络地址"
    )
    parser.addoption(
        "--package-name",
        action="store",
        default=None,
        help="测试设备上已安装应用的包名（指定后将跳过APK安装）"
    )
    parser.addoption(
        "--module-robustness",
        action="store_true",
        default=False,
        help="启用系统健壮性测试模块"
    )
    parser.addoption(
        "--module-recovery",
        action="store_true",
        default=False,
        help="启用异常恢复测试模块"
    )
    parser.addoption(
        "--module-performance",
        action="store_true",
        default=False,
        help="启用完整性能测试模块"
    )
    parser.addoption(
        "--module-response",
        action="store_true",
        default=False,
        help="启用响应性能测试模块"
    )
    parser.addoption(
        "--module-resource",
        action="store_true",
        default=False,
        help="启用资源消耗测试模块"
    )
    parser.addoption(
        "--establish-baseline",
        action="store_true",
        default=False,
        help="建立性能基线"
    )
    parser.addoption(
        "--compare-baseline",
        action="store_true",
        default=False,
        help="对比性能基线"
    )
    parser.addoption(
        "--duration-hours",
        action="store",
        default=None,
        help="长时间压力测试时长（单位：小时，可为小数；由 GUI 或 main.py 传入）"
    )