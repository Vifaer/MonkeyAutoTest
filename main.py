#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import logging
import argparse
import threading
import os
import json

# 解决Windows下编码问题
if sys.platform == 'win32':
    try:
        import locale
        locale.setlocale(locale.LC_ALL, 'zh_CN.UTF-8')
    except:
        try:
            locale.setlocale(locale.LC_ALL, 'Chinese_China.UTF-8')
        except:
            pass

    # 确保stdout使用UTF-8编码
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except:
            pass

from utils import addition
from utils import ProjectLog
from utils.stability_test import StabilityTestRunner
from utils.config_io import read_json


def init_param():
    """
    系统参数：
    稳定性测试模式：
    --stability，启用稳定性测试模式
    -s/--sn，必填，待测设备序列号。如果有多个，以空格隔开
    --config，选填，稳定性测试配置文件路径
    --duration，选填，测试时长（小时），默认12小时
    --no-mock-server，选填，禁用Mock Server
    --no-network-proxy，选填，禁用网络代理
    """
    parser = argparse.ArgumentParser(description="车载端侧应用自动化测试工具")

    # 测试模式选择
    parser.add_argument("--stability", action="store_true", help="启用车载端侧稳定性测试模式")

    # 稳定性测试参数
    parser.add_argument("-s", "--sn", required=True, help="Serial number(s) of Android device")
    parser.add_argument("--config", required=False, help="Stability test configuration file path")
    parser.add_argument("--duration", type=int, default=12, help="Test duration in hours (default: 12)")
    parser.add_argument("--no-mock-server", action="store_true", help="Disable Mock Server")
    parser.add_argument("--no-network-proxy", action="store_true", help="Disable network proxy")
    parser.add_argument("--network-method", required=False, choices=['root', 'pc_proxy', 'wifi_control', 'app_simulation'],
                       default='root', help="Network simulation method (default: root)")
    parser.add_argument("--establish-baseline", action="store_true", help="Establish performance baseline")
    parser.add_argument("--compare-baseline", action="store_true", help="Compare current results with baseline")

    # 模块化测试选项
    parser.add_argument("--modular", action="store_true", help="Enable modular test mode")
    parser.add_argument("--robustness-only", action="store_true", help="Run only system robustness test")
    parser.add_argument("--recovery-only", action="store_true", help="Run only exception recovery test")
    parser.add_argument("--performance-only", action="store_true", help="Run only performance tests")
    parser.add_argument("--response-only", action="store_true", help="Run only response performance test")
    parser.add_argument("--resource-only", action="store_true", help="Run only resource consumption test")
    parser.add_argument("--broadcast-only", action="store_true", help="Run only broadcast stress test")
    parser.add_argument("--tts-only", action="store_true", help="Run only TTS stress test")

    args = parser.parse_args()

    # 验证参数
    if not args.stability:
        parser.error("请使用 --stability 启用稳定性测试模式")

    if not args.sn:
        parser.error("稳定性测试模式需要指定 -s/--sn 参数")

    # 处理参数
    if args.stability:
        # 稳定性测试模式
        # 检查是否启用模块化测试
        modular_enabled = (args.modular or args.robustness_only or args.recovery_only or
                          args.performance_only or args.response_only or args.resource_only or
                          args.broadcast_only or args.tts_only)

        # 确定启用的测试模块
        enabled_modules = []
        if args.robustness_only:
            enabled_modules.append('system_robustness')
        if args.recovery_only:
            enabled_modules.append('exception_recovery')
        if args.performance_only:
            enabled_modules.append('performance_all')
        if args.response_only:
            enabled_modules.append('performance_response')
        if args.resource_only:
            enabled_modules.append('performance_resource')
        if args.broadcast_only:
            enabled_modules.append('broadcast_stress')
        if args.tts_only:
            enabled_modules.append('tts_stress')

        return {
            'mode': 'stability',
            'sn_list': args.sn.split(),
            'config_path': args.config,
            'duration': args.duration,
            'use_mock_server': not args.no_mock_server,
            'use_network_proxy': not args.no_network_proxy,
            'network_method': args.network_method,
            'establish_baseline': args.establish_baseline,
            'compare_baseline': args.compare_baseline,
            'modular_enabled': modular_enabled,
            'enabled_modules': enabled_modules,
            'apk_url': getattr(args, 'url', None) or "",
            'apk_path': getattr(args, 'path', None) or ""
        }
    return None


def main():
    """主程序入口"""
    params = init_param()
    if params is None:
        return
    # 稳定性测试模式
    run_stability_test(params)


def build_pytest_args(params):
    """
    构建pytest命令行参数
    使用配置字典优化参数构建逻辑。
    每次运行生成独立的 HTML 报告文件，避免覆盖历史报告。
    """
    import os
    from datetime import datetime

    # 基础pytest参数
    # GUI 场景下（smoke_only）优先跑 tests/integration，避免同一用例在 tests/ 与 tests/integration 重复执行
    test_target = 'tests/'
    if params.get('smoke_only', False):
        test_target = 'tests/integration/'
    # 模块化稳定性（GUI 勾选模块）：使用单一 runner 用例，runner 内部按参数运行模块并生成实时/阶段性/最终报告
    if params.get('modular_enabled', False):
        test_target = 'tests/integration/test_modular_runner.py'

    # 模块化测试时由 report_generator 写入单一综合报告（{sn}_{project}_{ts}.html），不在此处添加 pytest-html
    reports_dir = 'reports'
    os.makedirs(reports_dir, exist_ok=True)
    pytest_args = [test_target, '-v', '--tb=short']
    if not params.get('modular_enabled', False):
        mode = params.get('mode', 'test')
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_report_name = f"pytest_{mode}_{ts}.html"
        html_report_path = os.path.join(reports_dir, html_report_name)
        pytest_args.extend([f'--html={html_report_path}', '--self-contained-html'])

    # 设备序列号参数
    if params['sn_list']:
        pytest_args.extend(['--device-sn', params['sn_list'][0]])

    # 测试应用来源：优先已安装应用包名，其次 APK 路径/URL
    if params.get('package_name'):
        pytest_args.extend(['--package-name', params['package_name']])
    elif params.get('apk_path'):
        pytest_args.extend(['--apk-path', params['apk_path']])
    elif params.get('apk_url'):
        pytest_args.extend(['--apk-url', params['apk_url']])

    # 模块到标记的映射配置
    MODULE_MARKER_MAP = {
        'system_robustness': 'system_robustness',
        'exception_recovery': 'exception_recovery',
        'performance_all': 'performance',
        'performance_response': 'performance',
        'performance_resource': 'performance',
        'broadcast_stress': 'broadcast_stress',
        'tts_stress': 'tts_stress',
    }

    MODULE_ARG_MAP = {
        'system_robustness': '--module-robustness',
        'exception_recovery': '--module-recovery',
        'performance_all': '--module-performance',
        'performance_response': '--module-response',
        'performance_resource': '--module-resource',
        'broadcast_stress': '--module-broadcast',
        'tts_stress': '--module-tts',
    }

    # 模块化测试：根据启用的模块添加参数（由 runner 用例内部执行模块，不再依赖 pytest marker 过滤）
    if params.get('modular_enabled', False):
        enabled_modules = params.get('enabled_modules', [])
        
        # 添加模块参数
        for module in enabled_modules:
            if module in MODULE_ARG_MAP:
                pytest_args.append(MODULE_ARG_MAP[module])
    else:
        # 完整测试套件：运行所有稳定性测试
        # GUI 场景下仅运行标记为 stability_smoke 的轻量用例
        if params.get('smoke_only', False):
            pytest_args.extend(['-m', 'stability_smoke'])
        else:
            pytest_args.extend(['-m', 'stability'])

    # 基线选项
    if params.get('establish_baseline', False):
        pytest_args.append('--establish-baseline')
    if params.get('compare_baseline', False):
        pytest_args.append('--compare-baseline')

    # 长时间压力测试时长（小时），通过 pytest 自定义参数传递给测试配置
    duration = params.get('duration')
    if duration is not None:
        try:
            pytest_args.extend(['--duration-hours', str(float(duration))])
        except Exception:
            # 如果转换失败则忽略，由测试侧使用默认值
            pass

    # 直接使用 Fallback 事件注入（跳过 monkey 命令）
    if params.get('use_fallback_only', False):
        pytest_args.append('--use-fallback-only')

    return pytest_args


def run_stability_test(params):
    """运行稳定性测试"""
    logging.info("开始车载端侧稳定性测试模式")
    logging.info(f"测试设备: {', '.join(params['sn_list'])}")
    logging.info(f"测试时长: {params['duration']} 小时")

    # 检查是否启用模块化测试
    if params.get('modular_enabled', False):
        logging.info("启用模块化测试模式")
        logging.info(f"启用的测试模块: {params.get('enabled_modules', [])}")

    # 使用pytest框架执行测试
    logging.info("使用pytest框架执行测试")
    try:
        import pytest  # type: ignore
        import sys

        # 构建pytest参数
        pytest_args = build_pytest_args(params)

        logging.info(f"pytest 参数: {' '.join(pytest_args)}")
        exit_code = pytest.main(pytest_args)
        sys.exit(exit_code)
    except ImportError:
        logging.error("pytest 未安装，请运行 'pip install pytest pytest-html pytest-cov pytest-timeout pytest-xdist' 安装所需依赖")
        sys.exit(-1)

    logging.info("稳定性测试执行完成")


def load_stability_config(params):
    """加载稳定性测试配置"""
    config = {
        'long_stress': {
            'duration_hours': params['duration'],
            'throttle': 700,
            'event_count': 100000,
            'use_fallback_only': params.get('use_fallback_only', False)  # 直接使用Fallback事件注入
        },
        'performance': {
            'sample_interval': 30,
            'monitor_duration': 3600
        },
        'network': {
            'proxy_host': '127.0.0.1',
            'proxy_port': 8080,
            'weak_net_delay': 500
        },
        'mock_server': {
            'enabled': params['use_mock_server'],
            'host': '127.0.0.1',
            'port': 8080
        },
        'network_proxy': {
            'enabled': params['use_network_proxy'],
            'type': 'mitmproxy',  # 或 'charles'
            'method': params.get('network_method', 'root')  # 网络模拟方法
        }
    }

    # 如果指定了配置文件，合并配置
    if params.get('config_path'):
        try:
            with open(params['config_path'], 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            # 递归合并配置
            config = merge_configs(config, file_config)
            logging.info(f"已加载配置文件: {params['config_path']}")
        except Exception as e:
            logging.warning(f"加载配置文件失败: {str(e)}")

    # 与GUI持久化配置联动：如果存在 conf/test_ui_config.json，则将其中的 mock_server / monkey_mask 段合并进来
    try:
        gui_cfg_path = os.path.join("conf", "test_ui_config.json")
        gui_cfg = read_json(gui_cfg_path, default={})
        if isinstance(gui_cfg, dict):
            ms = gui_cfg.get("mock_server")
            if isinstance(ms, dict):
                if "mock_server" not in config or not isinstance(config["mock_server"], dict):
                    config["mock_server"] = {}
                # GUI配置优先覆盖默认 host/port/mode/rules_path 等
                config["mock_server"].update(ms)
                logging.info(f"已从GUI配置合并Mock Server设置: {ms}")

            # GUI 中配置的 monkey 遮罩区域（百分比），合并到 long_stress.monkey_mask 中
            mm = gui_cfg.get("monkey_mask")
            if isinstance(mm, dict):
                try:
                    ls = config.get("long_stress")
                    if not isinstance(ls, dict):
                        ls = {}
                    # 只写入一个子 dict，具体解析/容错交给 ExtendedMonkeyTest 内部处理
                    ls["monkey_mask"] = mm
                    config["long_stress"] = ls
                    logging.info(f"已从GUI配置合并 Monkey 遮罩区域设置: {mm}")
                except Exception as _e:
                    logging.warning(f"合并 Monkey 遮罩区域配置失败: {_e}")
    except Exception as e:
        logging.warning(f"从GUI配置加载Mock Server设置失败: {e}")

    return config


def merge_configs(base_config, override_config):
    """递归合并配置字典"""
    result = base_config.copy()

    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value

    return result


def get_stability_test_package(params):
    """获取稳定性测试的APK包"""
    from utils import addition

    # 如果指定了APK路径或URL，直接使用
    if params['apk_path'] or params['apk_url']:
        # 使用默认项目配置来获取包
        prj_json = addition.get_project_json()
        default_version = list(prj_json.keys())[0] if prj_json else None

        if default_version:
            return addition.get_package(default_version, prj_json[default_version],
                                      params['apk_url'], params['apk_path'])
        else:
            # 如果没有项目配置，直接创建Package对象
            from utils import Package
            if params['apk_path']:
                return Package(params['apk_path'])
            else:
                logging.error("稳定性测试模式需要指定APK路径或URL")
                sys.exit(-1)
    else:
        logging.error("稳定性测试模式需要指定APK路径(-p)或URL(-u)")
        sys.exit(-1)


if __name__ == "__main__":
    # 初始化日志
    project_log = ProjectLog()
    project_log.set_up()

    try:
        # 主程序
        main()
    except KeyboardInterrupt:
        logging.info("测试被用户中断")
    except Exception as e:
        logging.error(f"测试执行失败: {str(e)}")
        sys.exit(-1)
    finally:
        # 将本次结果复制到历史日志目录
        project_log.tear_down()
