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
from utils.config_io import read_json, load_stability_config as load_unified_config
from core.services.stability_service import StabilityTestService


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
            enabled_modules.append('monkey_stress')
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
    # 稳定性测试模式：通过 StabilityTestService 构建计划并执行
    service = StabilityTestService()
    plan = service.plan_from_params(params)
    result = service.run_with_pytest(plan)
    # CLI 模式下保持原有行为：根据 pytest 退出码退出进程
    import sys

    sys.exit(result.exit_code)


    logging.info("稳定性测试执行完成")


def load_stability_config(params):
    """加载稳定性测试配置（CLI入口，适配参数）"""
    # 使用统一的配置加载函数
    config = load_unified_config(config_path=params.get('config_path'))
    
    # CLI 参数覆盖
    if 'duration' in params:
        config.setdefault('long_stress', {})['duration_hours'] = params['duration']
    
    if 'use_fallback_only' in params:
        config.setdefault('long_stress', {})['use_fallback_only'] = params['use_fallback_only']
    
    if 'use_mock_server' in params:
        config.setdefault('mock_server', {})['enabled'] = params['use_mock_server']
    
    if 'use_network_proxy' in params:
        config.setdefault('network_proxy', {})['enabled'] = params['use_network_proxy']
    
    if 'network_method' in params:
        config.setdefault('network_proxy', {})['method'] = params.get('network_method', 'root')
    
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
