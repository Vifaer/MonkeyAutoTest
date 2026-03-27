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
from infra.config import load_test_ui_config, load_project_config

# 响应监控默认配置（广播/TTS 压力测试共用，发送后立即开始监控）
DEFAULT_RESPONSE_MONITOR = {
    'max_wait_for_appear': 6,
    'check_interval': 0.1,
    'max_wait_for_disappear': 300,
}

DEFAULT_APP_LOG = {
    'enabled': True,
    'extra_packages_csv': '',
    'package_process_map': '',
    'include_process_names_csv': '',
    'levels': 'VDIWEF',
    'tags_include_csv': '',
    'tags_exclude_csv': '',
    'keywords_include_csv': '',
    'keywords_exclude_csv': '',
    'output_subdir': '',
    'max_file_mb': 50.0,
    'backup_count': 3,
    'flush_interval_ms': 500,
    'batch_lines': 50,
    'pid_refresh_seconds': 2.0,
}


# ==================== pytest 配置钩子 ====================

def pytest_configure(config):
    """pytest 配置钩子：注册自定义标记"""
    config.addinivalue_line("markers", "stability: 稳定性测试标记")
    config.addinivalue_line("markers", "monkey_stress: Monkey 模式压力测试标记")
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
            item.add_marker(pytest.mark.monkey_stress)
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
    gui_config = load_test_ui_config()
    if not isinstance(gui_config, dict):
        gui_config = {}

    # 默认配置
    default_config = {
        'long_stress': {
            'duration_hours': 12,
            'throttle': 700,
            # 移除默认 event_count，改为根据时长动态计算
            # 'event_count': 100000  # 已移除，改为根据时长计算
        },
        'performance': {
            'sample_interval': 30,
            'monitor_duration': 3600,
            'cold_start_threshold': 3.0,
            'response_delay_threshold': 1.5,
            'cpu_foreground_threshold': 30.0,
            'cpu_background_threshold': 1.0,
            'clickable_elements': ['AI Power', '智能体广场', '对话收藏']  # 默认可点击元素列表
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
        },
        'app_log': dict(DEFAULT_APP_LOG),
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

    # 3) 合并 GUI 配置中的 mock_server 设置（并归一化端口类型）
    if isinstance(gui_config, dict) and 'mock_server' in gui_config:
        mock_server_cfg = gui_config['mock_server']
        if isinstance(mock_server_cfg, dict):
            default_config['mock_server'].update(mock_server_cfg)
            # 端口在 GUI 配置中通常以字符串形式保存，这里统一转换为 int，防止 HTTPServer 绑定失败
            try:
                port_val = default_config['mock_server'].get('port', 8080)
                if port_val not in (None, ""):
                    default_config['mock_server']['port'] = int(port_val)
            except Exception as e:
                logging.warning(f"从 GUI 配置解析 mock_server.port 失败（{port_val!r}），回退使用 8080: {e}")
                default_config['mock_server']['port'] = 8080

    # 4) 合并 GUI 配置中的性能监控设置
    if isinstance(gui_config, dict) and 'performance_monitor' in gui_config:
        perf_monitor_cfg = gui_config['performance_monitor']
        if isinstance(perf_monitor_cfg, dict):
            # 解析可点击元素列表（逗号分隔的字符串）
            clickable_elements_str = perf_monitor_cfg.get('clickable_elements', '')
            if clickable_elements_str:
                try:
                    # 分割字符串，去除空白，过滤空字符串
                    elements = [e.strip() for e in str(clickable_elements_str).split(',') if e.strip()]
                    if elements:
                        default_config['performance']['clickable_elements'] = elements
                        logging.info(f"从GUI配置加载可点击元素: {elements}")
                except Exception as e:
                    logging.warning(f"解析可点击元素列表失败: {e}")

    # 5) 合并 GUI 配置中的 monkey_mask 设置（稳定性测试可操作区域遮罩）
    #    conf/test_ui_config.json 中为：
    #    "monkey_mask": {"top": "30.0", "bottom": "30.0", "left": "30.0", "right": "30.0"}
    if isinstance(gui_config, dict) and 'monkey_mask' in gui_config:
        mm_cfg = gui_config['monkey_mask']
        if isinstance(mm_cfg, dict):
            try:
                # 直接将 dict 写入 long_stress.monkey_mask，具体解析/容错交给 ExtendedMonkeyTest._get_safe_touch_region
                if 'long_stress' not in default_config or not isinstance(default_config['long_stress'], dict):
                    default_config['long_stress'] = {}
                default_config['long_stress']['monkey_mask'] = mm_cfg
                logging.info(f"从GUI配置加载 Monkey 遮罩区域设置: {mm_cfg}")
            except Exception as e:
                logging.warning(f"合并 Monkey 遮罩区域配置失败: {e}")

    # 6) 直接使用 Fallback 事件注入：优先 pytest 参数，其次 GUI 持久化配置
    use_fallback_opt = False
    try:
        use_fallback_opt = pytestconfig.getoption("--use-fallback-only", default=False)
    except Exception:
        pass
    if use_fallback_opt:
        if 'long_stress' not in default_config or not isinstance(default_config['long_stress'], dict):
            default_config['long_stress'] = {}
        default_config['long_stress']['use_fallback_only'] = True
        logging.info("已从 pytest 参数启用：直接使用 Fallback 事件注入")
    elif isinstance(gui_config, dict) and gui_config.get('use_fallback_only', False):
        if 'long_stress' not in default_config or not isinstance(default_config['long_stress'], dict):
            default_config['long_stress'] = {}
        default_config['long_stress']['use_fallback_only'] = True
        logging.info("已从 GUI 配置启用：直接使用 Fallback 事件注入")

    # 7) 合并广播/TTS 压力测试配置（含 response_monitor）
    dur_hours = default_config.get('long_stress', {}).get('duration_hours', 12)
    rm_merged = dict(DEFAULT_RESPONSE_MONITOR)
    if isinstance(gui_config, dict) and isinstance(gui_config.get('response_monitor'), dict):
        for k, v in gui_config['response_monitor'].items():
            # 已移除 detection_pattern（UI 正则模式已废弃，仅 logcat 模式）
            if k == 'detection_pattern':
                continue
            if v is not None:
                rm_merged[k] = v
    # 顶层 response_monitor，供 stability_test 注入到 broadcast_stress/tts_stress 的 cfg（含 anr_recover_threshold=0 时禁用自动恢复）
    default_config['response_monitor'] = rm_merged
    app_log_merged = dict(DEFAULT_APP_LOG)
    if isinstance(gui_config, dict) and isinstance(gui_config.get('app_log'), dict):
        for k, v in gui_config['app_log'].items():
            if v is not None:
                app_log_merged[k] = v
    # 归一化 app_log 数值字段，避免字符串导致运行时异常
    try:
        app_log_merged['max_file_mb'] = max(1.0, float(app_log_merged.get('max_file_mb', 50.0)))
    except Exception:
        app_log_merged['max_file_mb'] = 50.0
    try:
        app_log_merged['backup_count'] = max(1, int(float(app_log_merged.get('backup_count', 3))))
    except Exception:
        app_log_merged['backup_count'] = 3
    try:
        app_log_merged['flush_interval_ms'] = max(50, int(float(app_log_merged.get('flush_interval_ms', 500))))
    except Exception:
        app_log_merged['flush_interval_ms'] = 500
    try:
        app_log_merged['batch_lines'] = max(1, int(float(app_log_merged.get('batch_lines', 50))))
    except Exception:
        app_log_merged['batch_lines'] = 50
    try:
        app_log_merged['pid_refresh_seconds'] = max(0.5, float(app_log_merged.get('pid_refresh_seconds', 2.0)))
    except Exception:
        app_log_merged['pid_refresh_seconds'] = 2.0
    default_config['app_log'] = app_log_merged

    if isinstance(gui_config, dict) and 'broadcast_stress' in gui_config:
        bc = gui_config['broadcast_stress']
        if isinstance(bc, dict):
            default_config['broadcast_stress'] = {
                'duration_hours': dur_hours,
                'interval_seconds': 30,
                'broadcast_action': 'com.cei.llm.INPUT_HINT_TO_LLM',
                'hints': bc.get('hints', ['介绍一下白居易', '讲个笑话']),
                'hints_file': (bc.get('hints_file') or '').strip(),
                'response_monitor': rm_merged,
                'app_log': dict(app_log_merged),
            }
    if isinstance(gui_config, dict) and 'tts_stress' in gui_config:
        tts = gui_config['tts_stress']
        if isinstance(tts, dict):
            # 从 GUI 配置读取 TTS 间隔（非法值回退 30）
            interval_seconds = 30
            try:
                raw_interval = tts.get('interval_seconds', 30)
                if raw_interval not in (None, ''):
                    interval_seconds = int(float(raw_interval))
            except Exception:
                interval_seconds = 30
            if interval_seconds < 0:
                interval_seconds = 0
            default_config['tts_stress'] = {
                'duration_hours': dur_hours,
                'interval_seconds': interval_seconds,
                'texts': tts.get('texts', ['打开设置', '介绍一下北京']),
                'texts_file': (tts.get('texts_file') or '').strip(),
                # 唤醒词/结束词配置透传到运行时（此前遗漏导致唤醒词不生效）
                'end_phrase': (tts.get('end_phrase') or '').strip(),
                'wake_phrase': (tts.get('wake_phrase') or '').strip(),
                'wake_delay_seconds': tts.get('wake_delay_seconds', 2),
                # TTS 引擎音量（0-100 百分比，运行时再归一化）
                'volume_percent': tts.get('volume_percent', 100),
                'response_monitor': rm_merged,
                'app_log': dict(app_log_merged),
            }
    # monkey 长压也注入统一 app_log 配置
    if isinstance(default_config.get('long_stress'), dict):
        default_config['long_stress']['app_log'] = dict(app_log_merged)

    return default_config


@pytest.fixture(scope="session")
def project_config():
    """加载项目配置"""
    cfg = load_project_config()
    return cfg if isinstance(cfg, dict) else {}


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
        enabled_modules.append(TestModule.MONKEY_STRESS)
    if pytestconfig.getoption("--module-recovery", default=False):
        enabled_modules.append(TestModule.EXCEPTION_RECOVERY)
    if pytestconfig.getoption("--module-performance", default=False):
        enabled_modules.append(TestModule.PERFORMANCE_ALL)
    if pytestconfig.getoption("--module-response", default=False):
        enabled_modules.append(TestModule.PERFORMANCE_RESPONSE)
    if pytestconfig.getoption("--module-resource", default=False):
        enabled_modules.append(TestModule.PERFORMANCE_RESOURCE)
    if pytestconfig.getoption("--module-broadcast", default=False):
        enabled_modules.append(TestModule.BROADCAST_STRESS)
    if pytestconfig.getoption("--module-tts", default=False):
        enabled_modules.append(TestModule.TTS_STRESS)
    
    # 如果没有指定模块，默认启用所有
    if not enabled_modules:
        enabled_modules = [
            TestModule.MONKEY_STRESS,
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
    host = test_config['mock_server'].get('host', '127.0.0.1')
    port_cfg = test_config['mock_server'].get('port', 8080)
    try:
        port = int(port_cfg)
    except Exception as e:
        logging.warning(f"mock_server.port 配置无效（{port_cfg!r}），回退使用 8080: {e}")
        port = 8080
    server = mock_server_mod.MockServer(
        host=host,
        port=port,
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
        help="启用 Monkey 模式压力测试模块"
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
        "--module-broadcast",
        action="store_true",
        default=False,
        help="启用广播模式压力测试模块"
    )
    parser.addoption(
        "--module-tts",
        action="store_true",
        default=False,
        help="启用 TTS 模式压力测试模块"
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
    parser.addoption(
        "--use-fallback-only",
        action="store_true",
        default=False,
        help="直接使用 Fallback 事件注入，跳过 adb shell monkey 命令（由 GUI 勾选传入）"
    )