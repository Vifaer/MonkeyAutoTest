#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from utils import Device, Package, DeviceLog
from utils.timeout_command import run as run_cmd
from enum import Enum


class TestModule(Enum):
    """测试模块枚举"""
    SYSTEM_ROBUSTNESS = "system_robustness"
    EXCEPTION_RECOVERY = "exception_recovery"
    PERFORMANCE_RESPONSE = "performance_response"
    PERFORMANCE_RESOURCE = "performance_resource"
    PERFORMANCE_ALL = "performance_all"


class ModularStabilityTest:
    """
    模块化稳定性测试框架
    支持独立运行各个测试模块
    """

    def __init__(self, device_sn, package, config=None, enabled_modules=None, baseline_options=None):
        """
        Args:
            device_sn: 设备序列号
            package: 测试包
            config: 测试配置
            enabled_modules: 启用的测试模块列表
            baseline_options: 基线选项
        """
        self.device_sn = device_sn
        self.package = package
        self.device = Device(device_sn)
        self.device_log = DeviceLog(device_sn)
        self.config = config or self._load_default_config()
        self.baseline_options = baseline_options or {}

        # 默认启用所有模块（保持向后兼容性）
        if enabled_modules is None:
            self.enabled_modules = [
                TestModule.SYSTEM_ROBUSTNESS,
                TestModule.EXCEPTION_RECOVERY,
                TestModule.PERFORMANCE_ALL
            ]
        else:
            self.enabled_modules = enabled_modules

        # 测试结果存储
        self.test_results = {
            'device_info': {
                'sn': self.device.sn,
                'model': self.device.model,
                'os': self.device.os,
                'screen': self.device.screen
            },
            'package_info': {
                'name': package.name,
                'filename': package.filename,
                'path': package.path
            },
            'enabled_modules': [module.value for module in self.enabled_modules],
            'tests': {}
        }

    def _load_default_config(self):
        """加载默认配置"""
        return {
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
            }
        }

    def run_selected_tests(self):
        """
        运行选定的测试模块
        """
        logging.info(f"开始执行模块化稳定性测试，启用模块: {[m.value for m in self.enabled_modules]}")

        # 检查模块依赖关系
        self._check_module_dependencies()

        # 初始化设备日志
        self.device_log.init()

        # 应用安装和准备（所有测试都需要）
        self._prepare_application()

        # 根据启用的模块运行相应测试
        if TestModule.SYSTEM_ROBUSTNESS in self.enabled_modules:
            self._run_system_robustness_test()

        if TestModule.EXCEPTION_RECOVERY in self.enabled_modules:
            self._run_exception_recovery_test()

        if TestModule.PERFORMANCE_ALL in self.enabled_modules:
            self._run_performance_test()
        else:
            # 分别运行性能子模块
            if TestModule.PERFORMANCE_RESPONSE in self.enabled_modules:
                self._run_response_performance_test()

            if TestModule.PERFORMANCE_RESOURCE in self.enabled_modules:
                self._run_resource_consumption_test()

        # 生成测试报告
        self._generate_modular_report()

        logging.info("模块化稳定性测试执行完成")
        return self.test_results

    def reset(self):
        """重置本次运行的测试结果（便于pytest按用例隔离状态）"""
        self.test_results['tests'] = {}

    def _check_module_dependencies(self):
        """
        检查模块间的依赖关系，确保测试能正常运行
        """
        # 定义模块依赖关系
        module_dependencies = {
            TestModule.SYSTEM_ROBUSTNESS: [],  # 无依赖
            TestModule.EXCEPTION_RECOVERY: [],  # 可能需要mock_server，但不是强制依赖
            TestModule.PERFORMANCE_RESPONSE: [],  # 无依赖
            TestModule.PERFORMANCE_RESOURCE: [],  # 无依赖
            TestModule.PERFORMANCE_ALL: []  # 无依赖
        }

        # 检查互斥模块（不能同时启用）
        mutually_exclusive = [
            (TestModule.PERFORMANCE_ALL, [TestModule.PERFORMANCE_RESPONSE, TestModule.PERFORMANCE_RESOURCE]),
        ]

        # 检查互斥关系
        for main_module, conflicting_modules in mutually_exclusive:
            if main_module in self.enabled_modules:
                for conflicting in conflicting_modules:
                    if conflicting in self.enabled_modules:
                        logging.warning(f"检测到互斥模块: {main_module.value} 与 {conflicting.value} 不能同时启用")
                        logging.warning(f"将自动禁用 {conflicting.value}")
                        self.enabled_modules.remove(conflicting)

        # 检查特殊组合逻辑
        # 如果启用了性能子模块但没有启用主性能模块，发出警告
        performance_sub_modules = {TestModule.PERFORMANCE_RESPONSE, TestModule.PERFORMANCE_RESOURCE}
        enabled_perf_subs = performance_sub_modules.intersection(set(self.enabled_modules))

        if enabled_perf_subs and TestModule.PERFORMANCE_ALL in self.enabled_modules:
            logging.warning("同时启用了完整性能测试和性能子模块，将优先执行完整性能测试")
            for sub_module in enabled_perf_subs:
                self.enabled_modules.remove(sub_module)

        # 记录最终启用的模块
        logging.info(f"依赖检查完成，最终启用的模块: {[m.value for m in self.enabled_modules]}")

    def validate_module_configuration(self, enabled_modules):
        """
        验证模块配置的有效性

        Args:
            enabled_modules: 启用的模块列表

        Returns:
            tuple: (is_valid, warnings, errors)
        """
        warnings = []
        errors = []

        # 检查是否有启用的模块
        if not enabled_modules:
            errors.append("至少需要启用一个测试模块")
            return False, warnings, errors

        # 检查互斥模块
        if (TestModule.PERFORMANCE_ALL in enabled_modules and
            (TestModule.PERFORMANCE_RESPONSE in enabled_modules or
             TestModule.PERFORMANCE_RESOURCE in enabled_modules)):
            warnings.append("同时启用完整性能测试和性能子模块将只执行完整性能测试")

        # 检查依赖关系（目前所有模块都是独立的）

        return len(errors) == 0, warnings, errors

    def _run_response_performance_test(self):
        """仅运行响应性能测试"""
        logging.info("开始响应性能测试")

        from utils.performance_monitor import PerformanceMonitor
        perf_monitor = PerformanceMonitor(self.device, self.package, self.config['performance'])

        # 只运行响应相关的测试
        result = {}
        result['cold_start_time'] = perf_monitor._test_cold_start_time()
        result['response_delay'] = perf_monitor._test_response_delay()

        self.test_results['tests']['response_performance'] = result
        logging.info("响应性能测试完成")

    def _run_resource_consumption_test(self):
        """仅运行资源消耗测试"""
        logging.info("开始资源消耗测试")

        from utils.performance_monitor import PerformanceMonitor
        perf_monitor = PerformanceMonitor(self.device, self.package, self.config['performance'])

        # 只运行资源消耗测试
        result = {}
        result['resource_usage'] = perf_monitor._test_resource_usage()

        self.test_results['tests']['resource_consumption'] = result
        logging.info("资源消耗测试完成")

    def _prepare_application(self):
        """准备测试应用"""
        logging.info("准备测试应用...")

        # 已安装应用模式：跳过卸载/安装，仅验证存在并尽力补齐 activity
        if getattr(self.package, "source", "apk") == "installed" or not getattr(self.package, "path", ""):
            self._verify_app_installation(installed_only=True)
            return

        # APK模式：卸载旧版本并安装新版本
        self.device.uninstall(self.package)
        self.device.install(self.package)
        self._verify_app_installation(installed_only=False)

    def _verify_app_installation(self, installed_only: bool = False):
        """验证应用存在（APK模式：安装成功；已安装模式：包存在）"""
        cmd = f"adb -s {self.device_sn} shell pm path {self.package.name}"
        result = run_cmd(cmd)
        if not result or "package:" not in result:
            if installed_only:
                raise Exception(f"设备上未安装指定包名：{self.package.name}（请在GUI选择正确包名或先安装应用）")
            raise Exception(f"应用 {self.package.name} 安装失败（pm path 未找到）")

        # 尽力补齐 activity（避免后续 am start -n 失败）
        if not getattr(self.package, "activity", ""):
            try:
                # 复用 Package 的设备信息补齐逻辑（如果存在）
                if hasattr(self.package, "_populate_from_device"):
                    self.package._populate_from_device(self.device_sn)  # type: ignore
            except Exception:
                pass

        logging.info(f"应用 {self.package.name} 验证成功（模式：{'已安装' if installed_only else 'APK安装'}）")

    def _run_system_robustness_test(self):
        """运行系统健壮性测试"""
        logging.info("开始系统健壮性测试...")

        from utils.extended_monkey import ExtendedMonkeyTest
        monkey_test = ExtendedMonkeyTest(self.device, self.package, self.config['long_stress'])

        result = monkey_test.run_long_stress_test()
        self.test_results['tests']['system_robustness'] = result

        logging.info("系统健壮性测试完成")

    def _run_exception_recovery_test(self):
        """运行异常恢复测试"""
        logging.info("开始异常恢复测试...")

        from utils.exception_recovery import ExceptionRecoveryTest
        recovery_test = ExceptionRecoveryTest(self.device, self.package, self.config)

        result = recovery_test.run_all_recovery_tests()
        self.test_results['tests']['exception_recovery'] = result

        logging.info("异常恢复测试完成")

    def _run_performance_test(self):
        """运行完整性能测试"""
        logging.info("开始完整性能测试...")

        from utils.performance_monitor import PerformanceMonitor
        # 合并performance配置和long_stress配置，确保性能测试能获取到时长限制
        perf_config = self.config.get('performance', {}).copy()
        perf_config['long_stress'] = self.config.get('long_stress', {})
        perf_monitor = PerformanceMonitor(self.device, self.package, perf_config)

        result = perf_monitor.run_performance_tests()
        self.test_results['tests']['performance'] = result

        logging.info("完整性能测试完成")

    def _generate_modular_report(self):
        """生成模块化测试报告"""
        from utils.report_generator import StabilityReportGenerator
        from utils.baseline_manager import BaselineManager
        import os

        report_gen = StabilityReportGenerator()
        baseline_mgr = BaselineManager()

        # 获取应用版本
        version = self._get_app_version()

        # 生成基础报告
        report_path = report_gen.generate_comprehensive_report(self.test_results)

        # 建立或对比基线
        if self.baseline_options.get('establish_baseline', False):
            baseline_path = baseline_mgr.establish_baseline(self.test_results, version)
            logging.info(f"性能基线已建立: {baseline_path}")
        elif self.baseline_options.get('compare_baseline', False):
            comparison_result = baseline_mgr.compare_with_baseline(self.test_results, version)
            if comparison_result['comparison_available']:
                self._log_comparison_results(comparison_result)
                # 导出对比报告
                comparison_report_path = os.path.join("reports",
                    f"baseline_comparison_{version}_{self.test_results.get('start_time', '').replace(':', '').replace('-', '')[:15]}.json")
                baseline_mgr.export_baseline_report(comparison_result, comparison_report_path)

        logging.info(f"模块化测试报告已生成: {report_path}")
        return report_path

    def _get_app_version(self):
        """获取应用版本"""
        try:
            with open("conf/project.json", 'r', encoding='utf-8') as f:
                config = json.load(f)

            for version_key in config:
                if isinstance(config[version_key], dict):
                    return version_key
        except Exception as e:
            logging.warning(f"无法获取应用版本: {str(e)}")

        return "unknown_version"

    def _log_comparison_results(self, comparison_result):
        """记录对比结果"""
        logging.info("=" * 60)
        logging.info("性能基线对比结果")
        logging.info("=" * 60)

        baseline_version = comparison_result.get('baseline_version', 'unknown')
        overall_status = comparison_result.get('overall_assessment', 'unknown')

        logging.info(f"基线版本: {baseline_version}")
        logging.info(f"总体评估: {overall_status}")

        perf_comparison = comparison_result.get('performance_comparison', {})
        if perf_comparison:
            logging.info("性能指标对比:")
            for metric_name, metric_data in perf_comparison.items():
                status = metric_data.get('status', 'unknown')
                current = metric_data.get('current_value', 0)
                baseline = metric_data.get('baseline_value', 0)
                change_percent = metric_data.get('change_percent', 0)

                if isinstance(change_percent, (int, float)) and not isinstance(change_percent, bool):
                    if abs(change_percent) < float('inf'):
                        change_str = f"{change_percent:+.1f}%"
                    else:
                        change_str = "显著变化"
                else:
                    change_str = "N/A"

                logging.info(f"  {metric_name}: {status} (当前: {current:.2f}, 基线: {baseline:.2f}, 变化: {change_str})")

        stability_comparison = comparison_result.get('stability_comparison', {})
        if stability_comparison:
            logging.info("稳定性指标对比:")
            for metric_name, metric_data in stability_comparison.items():
                status = metric_data.get('status', 'unknown')
                current = metric_data.get('current_value', 0)
                baseline = metric_data.get('baseline_value', 0)

                logging.info(f"  {metric_name}: {status} (当前: {current}, 基线: {baseline})")

        logging.info("=" * 60)


class StabilityTestFramework:
    """
    车载端侧应用稳定性测试框架
    支持多种测试类型：系统健壮性、异常恢复、性能测试
    """

    def __init__(self, device_sn, package, config=None, baseline_options=None):
        self.device_sn = device_sn
        self.package = package
        self.device = Device(device_sn)
        self.device_log = DeviceLog(device_sn)
        self.config = config or self._load_default_config()
        self.baseline_options = baseline_options or {}

        # 测试结果存储
        self.test_results = {
            'device_info': {
                'sn': self.device.sn,
                'model': self.device.model,
                'os': self.device.os,
                'screen': self.device.screen
            },
            'package_info': {
                'name': package.name,
                'filename': package.filename,
                'path': package.path
            },
            'tests': {}
        }

    def _load_default_config(self):
        """加载默认配置"""
        return {
            'long_stress': {
                'duration_hours': 12,
                'throttle': 700,
                'event_count': 100000
            },
            'performance': {
                'sample_interval': 30,  # 采样间隔（秒）
                'monitor_duration': 3600  # 监控时长（秒）
            },
            'network': {
                'proxy_host': '127.0.0.1',
                'proxy_port': 8080,
                'weak_net_delay': 500  # 弱网延迟（毫秒）
            }
        }

    def run_comprehensive_test(self):
        """
        运行完整的稳定性测试套件
        包括系统健壮性、异常恢复、性能测试
        """
        logging.info("开始执行车载端侧应用稳定性测试")

        # 初始化设备日志
        self.device_log.init()

        # 1. 应用安装和准备
        self._prepare_application()

        # 2. 系统健壮性测试
        self._run_system_robustness_test()

        # 3. 异常恢复测试
        self._run_exception_recovery_test()

        # 4. 性能测试
        self._run_performance_test()

        # 5. 生成测试报告
        self._generate_comprehensive_report()

        logging.info("稳定性测试执行完成")
        return self.test_results

    # -------------------- pytest友好：公开API（返回值明确） --------------------
    def reset(self):
        """重置本次运行的测试结果（便于pytest按用例隔离状态）"""
        self.test_results['tests'] = {}

    def run_system_robustness(self):
        """运行系统健壮性测试并返回该模块结果 dict"""
        self._run_system_robustness_test()
        return self.test_results.get('tests', {}).get('system_robustness', {})

    def run_exception_recovery(self):
        """运行异常恢复测试并返回该模块结果 dict"""
        self._run_exception_recovery_test()
        return self.test_results.get('tests', {}).get('exception_recovery', {})

    def run_performance(self):
        """运行性能测试并返回该模块结果 dict"""
        self._run_performance_test()
        return self.test_results.get('tests', {}).get('performance', {})

    def run_all(self):
        """运行完整稳定性测试套件并返回完整 test_results"""
        return self.run_comprehensive_test()

    def _prepare_application(self):
        """准备测试应用"""
        logging.info("准备测试应用...")

        # 已安装应用模式：跳过卸载/安装，仅验证存在
        if getattr(self.package, "source", "apk") == "installed" or not getattr(self.package, "path", ""):
            self._verify_app_installation(installed_only=True)
            return

        self.device.uninstall(self.package)
        self.device.install(self.package)
        self._verify_app_installation(installed_only=False)

    def _verify_app_installation(self, installed_only: bool = False):
        """验证应用存在（APK模式：安装成功；已安装模式：包存在）"""
        cmd = f"adb -s {self.device_sn} shell pm path {self.package.name}"
        result = run_cmd(cmd)
        if not result or "package:" not in result:
            if installed_only:
                raise Exception(f"设备上未安装指定包名：{self.package.name}（请在GUI选择正确包名或先安装应用）")
            raise Exception(f"应用 {self.package.name} 安装失败（pm path 未找到）")

        if not getattr(self.package, "activity", ""):
            try:
                if hasattr(self.package, "_populate_from_device"):
                    self.package._populate_from_device(self.device_sn)  # type: ignore
            except Exception:
                pass

        logging.info(f"应用 {self.package.name} 验证成功（模式：{'已安装' if installed_only else 'APK安装'}）")

    def _run_system_robustness_test(self):
        """运行系统健壮性测试"""
        logging.info("开始系统健壮性测试...")

        from utils.extended_monkey import ExtendedMonkeyTest
        monkey_test = ExtendedMonkeyTest(self.device, self.package, self.config['long_stress'])

        result = monkey_test.run_long_stress_test()
        self.test_results['tests']['system_robustness'] = result

        logging.info("系统健壮性测试完成")

    def _run_exception_recovery_test(self):
        """运行异常恢复测试"""
        logging.info("开始异常恢复测试...")

        from utils.exception_recovery import ExceptionRecoveryTest
        recovery_test = ExceptionRecoveryTest(self.device, self.package, self.config)

        result = recovery_test.run_all_recovery_tests()
        self.test_results['tests']['exception_recovery'] = result

        logging.info("异常恢复测试完成")

    def _run_performance_test(self):
        """运行性能测试"""
        logging.info("开始性能测试...")

        from utils.performance_monitor import PerformanceMonitor
        perf_monitor = PerformanceMonitor(self.device, self.package, self.config['performance'])

        result = perf_monitor.run_performance_tests()
        self.test_results['tests']['performance'] = result

        logging.info("性能测试完成")

    def _generate_comprehensive_report(self):
        """生成综合测试报告"""
        from utils.report_generator import StabilityReportGenerator
        from utils.baseline_manager import BaselineManager
        import os

        report_gen = StabilityReportGenerator()
        baseline_mgr = BaselineManager()

        # 获取应用版本（从配置文件或包信息）
        version = self._get_app_version()

        # 生成基础报告
        report_path = report_gen.generate_comprehensive_report(self.test_results)

        # 建立或对比基线
        if self._should_establish_baseline():
            baseline_path = baseline_mgr.establish_baseline(self.test_results, version)
            logging.info(f"性能基线已建立: {baseline_path}")
        else:
            comparison_result = baseline_mgr.compare_with_baseline(self.test_results, version)
            if comparison_result['comparison_available']:
                self._log_comparison_results(comparison_result)
                # 导出对比报告
                comparison_report_path = os.path.join("reports",
                    f"baseline_comparison_{version}_{self.test_results.get('start_time', '').replace(':', '').replace('-', '')[:15]}.json")
                baseline_mgr.export_baseline_report(comparison_result, comparison_report_path)

        logging.info(f"测试报告已生成: {report_path}")

        return report_path

    def _get_app_version(self):
        """获取应用版本"""
        # 从配置文件获取版本信息
        try:
            import json
            with open("conf/project.json", 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 查找当前使用的版本配置
            # 这里简化处理，返回第一个找到的版本
            for version_key in config:
                if isinstance(config[version_key], dict):
                    return version_key
        except Exception as e:
            logging.warning(f"无法获取应用版本: {str(e)}")

        return "unknown_version"

    def _should_establish_baseline(self):
        """判断是否应该建立基线"""
        # 检查命令行参数
        if self.baseline_options.get('establish_baseline', False):
            return True

        # 检查是否存在基线文件（如果没有明确指定建立基线）
        baseline_file = "baselines/performance_baseline.json"
        return not os.path.exists(baseline_file)

    def _log_comparison_results(self, comparison_result):
        """记录对比结果"""
        logging.info("=" * 60)
        logging.info("性能基线对比结果")
        logging.info("=" * 60)

        baseline_version = comparison_result.get('baseline_version', 'unknown')
        overall_status = comparison_result.get('overall_assessment', 'unknown')

        logging.info(f"基线版本: {baseline_version}")
        logging.info(f"总体评估: {overall_status}")

        # 性能对比结果
        perf_comparison = comparison_result.get('performance_comparison', {})
        if perf_comparison:
            logging.info("性能指标对比:")
            for metric_name, metric_data in perf_comparison.items():
                status = metric_data.get('status', 'unknown')
                current = metric_data.get('current_value', 0)
                baseline = metric_data.get('baseline_value', 0)
                change_percent = metric_data.get('change_percent', 0)

                if isinstance(change_percent, (int, float)) and not isinstance(change_percent, bool):
                    if abs(change_percent) < float('inf'):
                        change_str = f"{change_percent:+.1f}%"
                    else:
                        change_str = "显著变化"
                else:
                    change_str = "N/A"

                logging.info(f"  {metric_name}: {status} (当前: {current:.2f}, 基线: {baseline:.2f}, 变化: {change_str})")

        # 稳定性对比结果
        stability_comparison = comparison_result.get('stability_comparison', {})
        if stability_comparison:
            logging.info("稳定性指标对比:")
            for metric_name, metric_data in stability_comparison.items():
                status = metric_data.get('status', 'unknown')
                current = metric_data.get('current_value', 0)
                baseline = metric_data.get('baseline_value', 0)

                logging.info(f"  {metric_name}: {status} (当前: {current}, 基线: {baseline})")

        logging.info("=" * 60)


class StabilityTestRunner:
    """
    稳定性测试运行器
    支持多设备并行测试
    """

    def __init__(self, device_list, package, config=None, baseline_options=None):
        self.device_list = device_list
        self.package = package
        self.config = config
        self.baseline_options = baseline_options or {}
        self.test_threads = []

    def run_parallel_tests(self):
        """并行运行多设备测试"""
        logging.info(f"开始对 {len(self.device_list)} 个设备执行稳定性测试")

        for device_sn in self.device_list:
            thread = threading.Thread(
                target=self._run_single_device_test,
                args=(device_sn,),
                name=f"StabilityTest-{device_sn}"
            )
            self.test_threads.append(thread)
            thread.start()

        # 等待所有测试完成
        for thread in self.test_threads:
            thread.join()

        logging.info("所有设备的稳定性测试已完成")

    def _run_single_device_test(self, device_sn):
        """运行单个设备的测试"""
        try:
            framework = StabilityTestFramework(device_sn, self.package, self.config, self.baseline_options)
            framework.run_comprehensive_test()
        except Exception as e:
            logging.error(f"设备 {device_sn} 测试失败: {str(e)}")
            raise