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
    BROADCAST_STRESS = "broadcast_stress"
    TTS_STRESS = "tts_stress"


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
                'screen': self.device.screen,
                # 设备显示版本号（ro.build.display.id），用于报告展示与筛选
                'build_display_id': getattr(self.device, "build_display_id", ""),
            },
            'package_info': {
                'name': package.name,
                'filename': package.filename,
                'path': package.path,
                # 应用版本信息（尽力从 APK 或设备已安装应用中解析）
                'version_name': getattr(package, "version_name", ""),
                'app_label': getattr(package, "app_label", ""),
            },
            'enabled_modules': [module.value for module in self.enabled_modules],
            'tests': {},
            'start_time': datetime.now().isoformat()
        }
        
        # 报告生成器（用于阶段性报告保存）
        self.report_generator = None
        self.intermediate_report_interval = 1800  # 每30分钟保存一次阶段性报告（秒）
        self.last_intermediate_save_time = time.time()

        # 实时报告：每分钟更新同一份报告
        self._live_state = {}
        self._live_report_path = None
        self._live_report_stop = threading.Event()
        self._live_report_thread = None

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

        # 初始化报告生成器
        from utils.report_generator import StabilityReportGenerator, LIVE_REPORT_UPDATE_INTERVAL
        self.report_generator = StabilityReportGenerator()

        # 构建实时报告状态并生成初始报告，启动每分钟更新线程
        long_stress = self.config.get('long_stress', {})
        project_key = os.environ.get("MONKEYAUTOTEST_PROJECT_KEY", "stability")
        self._live_state = {
            'device_info': self.test_results['device_info'].copy(),
            'package_info': self.test_results['package_info'].copy(),
            'project_key': project_key,
            'test_params': {
                'duration_hours': long_stress.get('duration_hours'),
                'throttle': long_stress.get('throttle'),
                'event_count': long_stress.get('event_count'),
            },
            'start_time': self.test_results['start_time'],
            'current_phase': 'idle',
            'modules_done': [],
            'run_log_dir': '',
            'test_results_snapshot': {},
            'crashes_so_far': 0,
            'anrs_so_far': 0,
        }
        self._live_report_path = self.report_generator.create_initial_report(self._live_state)
        self._live_report_stop.clear()
        self._live_report_thread = threading.Thread(target=self._live_report_update_loop, daemon=True)
        self._live_report_thread.start()
        logging.info(f"实时报告已启动，每 {LIVE_REPORT_UPDATE_INTERVAL} 秒更新: {self._live_report_path}")

        # 根据启用的模块运行相应测试
        if TestModule.SYSTEM_ROBUSTNESS in self.enabled_modules:
            self._live_state['current_phase'] = 'system_robustness'
            self._run_system_robustness_test()
            self._live_state['modules_done'].append('system_robustness')
            rb = self.test_results.get('tests', {}).get('system_robustness', {})
            self._live_state['run_log_dir'] = rb.get('run_log_dir', '') or self._live_state.get('run_log_dir', '')

        if TestModule.EXCEPTION_RECOVERY in self.enabled_modules:
            self._live_state['current_phase'] = 'exception_recovery'
            self._run_exception_recovery_test()
            self._live_state['modules_done'].append('exception_recovery')

        if TestModule.PERFORMANCE_ALL in self.enabled_modules:
            self._live_state['current_phase'] = 'performance'
            self._run_performance_test()
            self._live_state['modules_done'].append('performance')
        else:
            if TestModule.PERFORMANCE_RESPONSE in self.enabled_modules:
                self._live_state['current_phase'] = 'performance'
                self._run_response_performance_test()
                self._live_state['modules_done'].append('performance_response')

            if TestModule.PERFORMANCE_RESOURCE in self.enabled_modules:
                self._live_state['current_phase'] = 'performance'
                self._run_resource_consumption_test()
                self._live_state['modules_done'].append('performance_resource')

        if TestModule.BROADCAST_STRESS in self.enabled_modules:
            self._live_state['current_phase'] = 'broadcast_stress'
            self._run_broadcast_stress_test()
            self._live_state['modules_done'].append('broadcast_stress')
            bc = self.test_results.get('tests', {}).get('broadcast_stress', {})
            self._live_state['run_log_dir'] = bc.get('run_log_dir', '') or self._live_state.get('run_log_dir', '')

        if TestModule.TTS_STRESS in self.enabled_modules:
            self._live_state['current_phase'] = 'tts_stress'
            self._run_tts_stress_test()
            self._live_state['modules_done'].append('tts_stress')
            ts = self.test_results.get('tests', {}).get('tts_stress', {})
            self._live_state['run_log_dir'] = ts.get('run_log_dir', '') or self._live_state.get('run_log_dir', '')

        # 添加结束时间后，停止实时报告更新并最后一次写入同一报告文件（完整结果 + 已停止）
        self.test_results['end_time'] = datetime.now().isoformat()
        self._stop_live_report_updates()

        # 基线建立/对比（不再生成新报告文件，报告已由 update_live_report 写入同一文件）
        self._run_baseline_if_needed()

        logging.info(f"模块化稳定性测试执行完成，报告: {self._live_report_path or 'N/A'}")
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
            TestModule.SYSTEM_ROBUSTNESS: [],
            TestModule.EXCEPTION_RECOVERY: [],
            TestModule.PERFORMANCE_RESPONSE: [],
            TestModule.PERFORMANCE_RESOURCE: [],
            TestModule.PERFORMANCE_ALL: [],
            TestModule.BROADCAST_STRESS: [],
            TestModule.TTS_STRESS: [],
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

        run_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        run_log_dir = os.path.join("logs", str(self.device.sn), run_ts)
        os.makedirs(run_log_dir, exist_ok=True)
        logcat_log_path = os.path.join(run_log_dir, "logcat_performance_response.log")

        from utils.stress_monitor import StressMonitor
        monitor = StressMonitor(self.device, self.package, self.config.get('performance', {}))
        monitor._stop_logcat.clear()
        logcat_thread = monitor.start_logcat_capture(logcat_log_path)
        try:
            from utils.performance_monitor import PerformanceMonitor
            perf_monitor = PerformanceMonitor(self.device, self.package, self.config['performance'])

            # 只运行响应相关的测试
            result = {'run_log_dir': run_log_dir}
            result['cold_start_time'] = perf_monitor._test_cold_start_time()
            result['response_delay'] = perf_monitor._test_response_delay()
        finally:
            monitor.stop()
            if logcat_thread:
                logcat_thread.join(timeout=5)

        self.test_results['tests']['response_performance'] = result
        logging.info("响应性能测试完成")

    def _run_resource_consumption_test(self):
        """仅运行资源消耗测试"""
        logging.info("开始资源消耗测试")

        run_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        run_log_dir = os.path.join("logs", str(self.device.sn), run_ts)
        os.makedirs(run_log_dir, exist_ok=True)
        logcat_log_path = os.path.join(run_log_dir, "logcat_performance_resource.log")

        from utils.stress_monitor import StressMonitor
        monitor = StressMonitor(self.device, self.package, self.config.get('performance', {}))
        monitor._stop_logcat.clear()
        logcat_thread = monitor.start_logcat_capture(logcat_log_path)
        try:
            from utils.performance_monitor import PerformanceMonitor
            perf_monitor = PerformanceMonitor(self.device, self.package, self.config['performance'])

            # 只运行资源消耗测试
            result = {'run_log_dir': run_log_dir}
            result['resource_usage'] = perf_monitor._test_resource_usage()
        finally:
            monitor.stop()
            if logcat_thread:
                logcat_thread.join(timeout=5)

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

    def _run_broadcast_stress_test(self):
        """运行广播模式压力测试"""
        logging.info("开始广播模式压力测试...")
        from utils.broadcast_stress import BroadcastStressTest
        cfg = self.config.get('broadcast_stress', self.config.get('long_stress', {}))
        broadcast_test = BroadcastStressTest(self.device, self.package, cfg)

        def _progress_cb(partial_result: dict):
            """广播压力测试运行中增量写回，供实时报告线程读取。"""
            try:
                self.test_results.setdefault('tests', {})['broadcast_stress'] = partial_result
                run_log_dir = partial_result.get('run_log_dir')
                if run_log_dir:
                    self._live_state['run_log_dir'] = run_log_dir
            except Exception:
                pass

        result = broadcast_test.run_broadcast_stress_test(progress_cb=_progress_cb)
        self.test_results['tests']['broadcast_stress'] = result
        logging.info("广播模式压力测试完成")

    def _run_tts_stress_test(self):
        """运行 TTS 模式压力测试"""
        logging.info("开始 TTS 模式压力测试...")
        from utils.tts_stress import TTSStressTest
        cfg = self.config.get('tts_stress', self.config.get('long_stress', {}))
        tts_test = TTSStressTest(self.device, self.package, cfg)

        def _progress_cb(partial_result: dict):
            """TTS 压力测试运行中增量写回，供实时报告线程读取。"""
            try:
                self.test_results.setdefault('tests', {})['tts_stress'] = partial_result
                run_log_dir = partial_result.get('run_log_dir')
                if run_log_dir:
                    self._live_state['run_log_dir'] = run_log_dir
            except Exception:
                pass

        result = tts_test.run_tts_stress_test(progress_cb=_progress_cb)
        self.test_results['tests']['tts_stress'] = result
        logging.info("TTS 模式压力测试完成")

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

    def _save_intermediate_report_if_needed(self, phase_info: str):
        """
        如果需要，保存阶段性报告
        
        Args:
            phase_info: 阶段信息
        """
        if not self.report_generator:
            return
        
        current_time = time.time()
        # 检查是否到了保存阶段性报告的时间（每30分钟或每个模块完成后）
        if (current_time - self.last_intermediate_save_time) >= self.intermediate_report_interval:
            try:
                # 确定测试类型
                test_type = "comprehensive"
                if "system_robustness" in phase_info:
                    test_type = "system_robustness"
                elif "exception_recovery" in phase_info:
                    test_type = "exception_recovery"
                elif "performance" in phase_info:
                    test_type = "performance"
                elif "broadcast_stress" in phase_info:
                    test_type = "broadcast_stress"
                elif "tts_stress" in phase_info:
                    test_type = "tts_stress"
                
                # 保存阶段性报告
                self.report_generator.save_intermediate_report(
                    self.test_results,
                    device_sn=self.device.sn,
                    package_name=self.package.name,
                    test_type=test_type,
                    phase_info=phase_info
                )
                self.last_intermediate_save_time = current_time
                logging.info(f"阶段性报告已保存: {phase_info}")
            except Exception as e:
                logging.warning(f"保存阶段性报告失败: {e}")

    def _live_report_update_loop(self):
        """后台线程：每隔 LIVE_REPORT_UPDATE_INTERVAL 秒更新一次实时报告。"""
        from utils.report_generator import LIVE_REPORT_UPDATE_INTERVAL
        # 可通过配置覆盖刷新间隔（秒）
        try:
            interval = float(self.config.get("live_report_update_interval", LIVE_REPORT_UPDATE_INTERVAL))
            interval = max(1.0, min(3600.0, interval))
        except Exception:
            interval = float(LIVE_REPORT_UPDATE_INTERVAL)
        while True:
            if self._live_report_stop.wait(interval):
                break
            try:
                self._live_state['test_results_snapshot'] = dict(self.test_results)
                tests = self.test_results.get('tests', {})
                for key in ('system_robustness', 'broadcast_stress', 'tts_stress'):
                    r = tests.get(key, {})
                    if r and r.get('run_log_dir'):
                        self._live_state['run_log_dir'] = r.get('run_log_dir', '')
                        break
                if self.report_generator and self._live_report_path:
                    self.report_generator.update_live_report(self._live_state, self._live_report_path)
            except Exception as e:
                logging.debug(f"更新实时报告失败: {e}")

    def _stop_live_report_updates(self):
        """停止实时报告更新线程，并最后一次更新 live 报告为「已停止」状态。"""
        self._live_report_stop.set()
        if self._live_report_thread and self._live_report_thread.is_alive():
            self._live_report_thread.join(timeout=5)
        self._live_report_thread = None
        if self._live_report_path and self.report_generator:
            try:
                self._live_state['test_results_snapshot'] = dict(self.test_results)
                self._live_state['report_stopped'] = True
                self.report_generator.update_live_report(self._live_state, self._live_report_path)
            except Exception as e:
                logging.debug(f"更新实时报告为已停止状态失败: {e}")
            logging.info(f"实时报告已停止，综合报告已写入: {self._live_report_path}")

    def _run_baseline_if_needed(self):
        """建立或对比性能基线（报告已由 update_live_report 写入同一综合报告文件，此处仅处理基线）。"""
        from utils.baseline_manager import BaselineManager
        import os

        baseline_mgr = BaselineManager()
        version = self._get_app_version()

        if self.baseline_options.get('establish_baseline', False):
            baseline_path = baseline_mgr.establish_baseline(self.test_results, version)
            logging.info(f"性能基线已建立: {baseline_path}")
        elif self.baseline_options.get('compare_baseline', False):
            comparison_result = baseline_mgr.compare_with_baseline(self.test_results, version)
            if comparison_result['comparison_available']:
                self._log_comparison_results(comparison_result)
                comparison_report_path = os.path.join("reports",
                    f"baseline_comparison_{version}_{self.test_results.get('start_time', '').replace(':', '').replace('-', '')[:15]}.json")
                baseline_mgr.export_baseline_report(comparison_result, comparison_report_path)

    def _generate_modular_report(self):
        """已废弃：模块化测试仅使用单一综合报告（由 create_initial_report + update_live_report 写入）。保留本方法以兼容可能的外部调用。"""
        self.test_results['end_time'] = datetime.now().isoformat()
        if self._live_report_path and self.report_generator:
            try:
                self._live_state['test_results_snapshot'] = dict(self.test_results)
                self._live_state['report_stopped'] = True
                self.report_generator.update_live_report(self._live_state, self._live_report_path)
            except Exception as e:
                logging.debug(f"更新综合报告失败: {e}")
        self._run_baseline_if_needed()
        return self._live_report_path or ""

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
        from utils.report_generator import StabilityReportGenerator, TEST_TYPE_COMPREHENSIVE
        from utils.baseline_manager import BaselineManager
        import os

        report_gen = StabilityReportGenerator()
        baseline_mgr = BaselineManager()

        # 获取应用版本（从配置文件或包信息）
        version = self._get_app_version()

        # 生成基础报告（统一入口，保证格式一致）
        report_path = report_gen.generate_report(
            self.test_results,
            test_type=TEST_TYPE_COMPREHENSIVE,
        )

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