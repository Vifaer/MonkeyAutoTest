#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import statistics
from datetime import datetime
from utils.timeout_command import run as run_cmd


class PerformanceMonitor:
    """
    性能监控类
    监控应用启动时间、响应延迟、CPU使用率、内存使用率等指标
    """

    def __init__(self, device, package, config):
        self.device = device
        self.package = package
        self.config = config

    def run_performance_tests(self):
        """
        运行所有性能测试（受配置时长控制）
        """
        # 获取配置的测试时长（小时），转换为秒
        duration_hours = self.config.get('long_stress', {}).get('duration_hours', 12)
        try:
            duration_hours = float(duration_hours)
        except Exception:
            duration_hours = 12.0
        
        # 性能测试分配总时长的40%（如果配置时长很短，至少保证5分钟）
        max_duration_seconds = max(300, int(duration_hours * 3600 * 0.4))
        
        logging.info(f"开始性能测试（最大时长: {max_duration_seconds}秒）")

        results = {
            'test_type': 'performance',
            'start_time': datetime.now().isoformat(),
            'max_duration_seconds': max_duration_seconds,
            'tests': {}
        }
        
        test_start_time = time.time()

        # 冷启动时间测试（分配30%时长）
        if time.time() - test_start_time < max_duration_seconds * 0.3:
            results['tests']['cold_start_time'] = self._test_cold_start_time(
                max_duration_seconds * 0.3 - (time.time() - test_start_time)
            )
        else:
            logging.warning("性能测试超过配置时长，跳过冷启动时间测试")
            results['tests']['cold_start_time'] = {'skipped': True, 'reason': 'timeout'}

        # 响应延迟测试（分配30%时长）
        if time.time() - test_start_time < max_duration_seconds * 0.6:
            results['tests']['response_delay'] = self._test_response_delay(
                max_duration_seconds * 0.6 - (time.time() - test_start_time)
            )
        else:
            logging.warning("性能测试超过配置时长，跳过响应延迟测试")
            results['tests']['response_delay'] = {'skipped': True, 'reason': 'timeout'}

        # 资源消耗测试（分配剩余时长）
        remaining_time = max_duration_seconds - (time.time() - test_start_time)
        if remaining_time > 60:  # 至少需要1分钟
            results['tests']['resource_usage'] = self._test_resource_usage(remaining_time)
        else:
            logging.warning("性能测试超过配置时长，跳过资源消耗测试")
            results['tests']['resource_usage'] = {'skipped': True, 'reason': 'timeout'}

        results['end_time'] = datetime.now().isoformat()
        results['actual_duration_seconds'] = time.time() - test_start_time

        return results

    def _test_cold_start_time(self, max_duration_seconds=None):
        """
        测试应用冷启动时间（受时长限制）
        达标参考：≤ 3秒
        
        Args:
            max_duration_seconds: 最大执行时长（秒），None表示不限制
        """
        logging.info(f"测试应用冷启动时间（最大时长: {max_duration_seconds or '无限制'}秒）")

        result = {
            'test_name': 'cold_start_time',
            'measurements': [],
            'average_time': 0,
            'min_time': 0,
            'max_time': 0,
            'standard_deviation': 0,
            'pass_rate': 0.0,
            'target_threshold': 3.0  # 3秒
        }

        # 根据可用时长调整测试次数（每次约需10秒：启动5秒+等待5秒）
        if max_duration_seconds:
            test_count = max(3, min(10, int(max_duration_seconds / 10)))
        else:
            test_count = 10
        
        test_start_time = time.time()
        for i in range(test_count):
            # 检查是否超时
            if max_duration_seconds and (time.time() - test_start_time) >= max_duration_seconds:
                logging.warning(f"冷启动测试超过时长限制，提前结束（已完成 {i}/{test_count} 次）")
                break
            logging.info(f"执行第 {i + 1}/{test_count} 次冷启动测试")

            # 确保应用完全停止
            self._force_stop_app()

            # 执行冷启动
            start_time = time.time()
            success = self._perform_cold_start()
            end_time = time.time()

            if success:
                cold_start_time = end_time - start_time
                result['measurements'].append(cold_start_time)
                logging.info(f"本次冷启动耗时: {cold_start_time:.2f}s")
            else:
                logging.warning(f"第 {i + 1} 次冷启动失败")
                result['measurements'].append(None)

            # 等待应用完全加载
            time.sleep(5)

        # 计算统计数据
        valid_measurements = [m for m in result['measurements'] if m is not None]

        if valid_measurements:
            result['average_time'] = statistics.mean(valid_measurements)
            result['min_time'] = min(valid_measurements)
            result['max_time'] = max(valid_measurements)
            result['standard_deviation'] = statistics.stdev(valid_measurements) if len(valid_measurements) > 1 else 0

            # 计算达标率（≤3秒）
            passed_count = sum(1 for m in valid_measurements if m <= result['target_threshold'])
            result['pass_rate'] = passed_count / len(valid_measurements)

            logging.info(f"冷启动时间测试完成 - 平均: {result['average_time']:.2f}s, 达标率: {result['pass_rate']:.1%}")

        return result

    def _test_response_delay(self, max_duration_seconds=None):
        """
        测试下发→展示延迟（受时长限制）
        达标参考：≤ 1.5秒
        
        Args:
            max_duration_seconds: 最大执行时长（秒），None表示不限制
        """
        logging.info(f"测试下发→展示延迟（最大时长: {max_duration_seconds or '无限制'}秒）")

        result = {
            'test_name': 'response_delay',
            'measurements': [],
            'average_delay': 0,
            'min_delay': 0,
            'max_delay': 0,
            'standard_deviation': 0,
            'pass_rate': 0.0,
            'target_threshold': 1.5  # 1.5秒
        }

        # 根据可用时长调整测试次数（每次约需3秒：测试1秒+间隔2秒）
        if max_duration_seconds:
            test_count = max(5, min(20, int(max_duration_seconds / 3)))
        else:
            test_count = 20
        
        test_start_time = time.time()
        for i in range(test_count):
            # 检查是否超时
            if max_duration_seconds and (time.time() - test_start_time) >= max_duration_seconds:
                logging.warning(f"响应延迟测试超过时长限制，提前结束（已完成 {i}/{test_count} 次）")
                break
            logging.info(f"执行第 {i + 1}/{test_count} 次响应延迟测试")

            # 触发数据请求（这里需要应用特定的触发方式）
            delay = self._measure_response_delay()

            if delay is not None:
                result['measurements'].append(delay)
                logging.info(f"本次响应延迟: {delay:.2f}s")
            else:
                logging.warning(f"第 {i + 1} 次响应延迟测试失败")
                result['measurements'].append(None)

            time.sleep(2)  # 测试间隔

        # 计算统计数据
        valid_measurements = [m for m in result['measurements'] if m is not None]

        if valid_measurements:
            result['average_delay'] = statistics.mean(valid_measurements)
            result['min_delay'] = min(valid_measurements)
            result['max_delay'] = max(valid_measurements)
            result['standard_deviation'] = statistics.stdev(valid_measurements) if len(valid_measurements) > 1 else 0

            # 计算达标率（≤1.5秒）
            passed_count = sum(1 for m in valid_measurements if m <= result['target_threshold'])
            result['pass_rate'] = passed_count / len(valid_measurements)

            logging.info(f"响应延迟测试完成 - 平均: {result['average_delay']:.2f}s, 达标率: {result['pass_rate']:.1%}")

        return result

    def _test_resource_usage(self, max_duration_seconds=None):
        """
        测试资源消耗（CPU和内存）（受时长限制）
        CPU达标参考：前台≤30% 后台≤1%
        内存：无持续增长
        
        Args:
            max_duration_seconds: 最大执行时长（秒），None表示使用配置值
        """
        # 如果未指定最大时长，使用配置值；如果指定了，使用较小值
        config_duration = self.config.get('monitor_duration', 1800)  # 默认30分钟
        if max_duration_seconds:
            monitor_duration = min(config_duration, int(max_duration_seconds))
        else:
            monitor_duration = config_duration
        
        logging.info(f"测试资源消耗（监控时长: {monitor_duration}秒）")

        result = {
            'test_name': 'resource_usage',
            'cpu_foreground': {
                'measurements': [],
                'average': 0,
                'peak': 0,
                'pass_rate': 0.0,
                'target_threshold': 30.0
            },
            'cpu_background': {
                'measurements': [],
                'average': 0,
                'peak': 0,
                'pass_rate': 0.0,
                'target_threshold': 1.0
            },
            'memory_pss': {
                'measurements': [],
                'average': 0,
                'peak': 0,
                'trend': 'stable',  # stable/increasing
                'memory_leak_detected': False
            },
            'monitor_duration': monitor_duration
        }

        # 启动应用并置于前台
        self._launch_app()
        time.sleep(5)

        # 监控前台资源消耗（分配50%时长）
        logging.info("监控前台资源消耗")
        foreground_duration = max(60, int(monitor_duration * 0.5))  # 至少1分钟
        foreground_data = self._monitor_resource_usage(
            duration=foreground_duration,
            background=False
        )

        result['cpu_foreground']['measurements'] = foreground_data['cpu']
        result['memory_pss']['measurements'] = foreground_data['memory']

        # 计算前台CPU统计
        if foreground_data['cpu']:
            result['cpu_foreground']['average'] = statistics.mean(foreground_data['cpu'])
            result['cpu_foreground']['peak'] = max(foreground_data['cpu'])
            passed_count = sum(1 for cpu in foreground_data['cpu'] if cpu <= result['cpu_foreground']['target_threshold'])
            result['cpu_foreground']['pass_rate'] = passed_count / len(foreground_data['cpu'])

        # 置于后台
        self._move_app_to_background()

        # 监控后台资源消耗（分配剩余时长）
        logging.info("监控后台资源消耗")
        background_duration = max(60, monitor_duration - foreground_duration)  # 至少1分钟
        background_data = self._monitor_resource_usage(
            duration=background_duration,
            background=True
        )

        result['cpu_background']['measurements'] = background_data['cpu']

        # 计算后台CPU统计
        if background_data['cpu']:
            result['cpu_background']['average'] = statistics.mean(background_data['cpu'])
            result['cpu_background']['peak'] = max(background_data['cpu'])
            passed_count = sum(1 for cpu in background_data['cpu'] if cpu <= result['cpu_background']['target_threshold'])
            result['cpu_background']['pass_rate'] = passed_count / len(background_data['cpu'])

        # 分析内存趋势
        if len(result['memory_pss']['measurements']) > 10:
            self._analyze_memory_trend(result['memory_pss'])

        logging.info(f"资源消耗测试完成 - 前台CPU平均: {result['cpu_foreground']['average']:.1f}%, "
                    f"后台CPU平均: {result['cpu_background']['average']:.1f}%")

        return result

    def _perform_cold_start(self):
        """
        执行应用冷启动
        """
        # 为了避免 APK manifest 中 package 与实际安装包名不一致导致 Activity 解析错误，
        # 这里优先通过设备自身解析 LAUNCHER Activity，再用 am start -W 启动。
        launcher_component = None
        try:
            import re
            resolve_cmds = [
                f"adb -s {self.device.sn} shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {self.package.name}",
                f"adb -s {self.device.sn} shell cmd package resolve-activity --brief {self.package.name}",
            ]
            for rc in resolve_cmds:
                rst = run_cmd(rc, timeout=15)
                if not isinstance(rst, str):
                    continue
                lines = [ln.strip() for ln in rst.splitlines() if ln.strip()]
                if not lines:
                    continue
                cand = lines[-1]
                # 常见格式：com.pkg/.MainActivity 或 name: com.pkg/.MainActivity
                m = re.search(r"([a-zA-Z0-9._]+/[a-zA-Z0-9_.$]+)", cand)
                if m:
                    launcher_component = m.group(1).strip()
                    break
        except Exception as e:
            logging.debug(f"解析 LAUNCHER Activity 失败，退回包内配置: {e}")

        if not launcher_component:
            # 兜底：使用 Package 提供的 activity（可能来自 aapt 或手工配置）
            launcher_component = f"{self.package.name}/{self.package.activity}"

        cmd = f"adb -s {self.device.sn} shell am start -W -n {launcher_component}"
        result = run_cmd(cmd, timeout=30)

        if not isinstance(result, str):
            logging.warning(f"冷启动命令执行失败（无输出），cmd={cmd!r}")
            return False

        text = result.strip()
        # 一般情况下 am start -W 输出会包含 TotalTime，但不同 ROM 也可能略有差异
        if "TotalTime:" in text:
            return True

        lowered = text.lower()
        # 若包含明显的错误关键字，则认为失败，并把原始输出打到日志里便于排查
        error_keywords = ("error type", "error:", "exception", "security", "not found", "unable to", "permission")
        if any(k in lowered for k in error_keywords):
            logging.warning(f"冷启动命令执行失败，adb 输出: {text}")
            return False

        # 没有错误关键字但也没有 TotalTime，视为成功（以实际耗时作为冷启动时间）
        logging.info(f"冷启动命令已执行（未检测到 TotalTime 字段），adb 输出: {text}")
        return True

    def _measure_response_delay(self):
        """
        测量响应延迟
        这里需要根据具体应用的特点来实现
        """
        # 记录请求开始时间
        request_start = time.time()

        # 触发数据请求（需要根据应用具体实现）
        self._trigger_data_request()

        # 等待响应完成（通过日志或其他方式检测）
        response_time = self._wait_for_response()

        if response_time:
            delay = response_time - request_start
            return delay
        else:
            return None

    def _monitor_resource_usage(self, duration, background=False):
        """
        监控资源使用情况
        """
        cpu_measurements = []
        memory_measurements = []

        sample_interval = self.config.get('sample_interval', 30)
        end_time = time.time() + duration

        while time.time() < end_time:
            # 采样CPU使用率
            cpu_usage = self._get_cpu_usage()
            if cpu_usage is not None:
                cpu_measurements.append(cpu_usage)

            # 采样内存使用率
            memory_usage = self._get_memory_pss()
            if memory_usage is not None:
                memory_measurements.append(memory_usage)

            time.sleep(sample_interval)

        return {
            'cpu': cpu_measurements,
            'memory': memory_measurements
        }

    def _get_cpu_usage(self):
        """
        获取应用CPU使用率
        """
        cmd = f"adb -s {self.device.sn} shell top -n 1 -d 0"
        result = run_cmd(cmd)

        if result and isinstance(result, str):
            try:
                lines = result.strip().splitlines()
                for line in lines:
                    if self.package.name in line:
                        parts = line.split()
                        # 不同 ROM 列顺序可能不同，尽量宽松：找带 % 的字段
                        for token in parts:
                            if token.endswith("%"):
                                cpu_str = token.rstrip("%")
                                return float(cpu_str)
            except (ValueError, IndexError) as e:
                logging.debug(f"解析CPU使用率失败: {str(e)}")

        return None

    def _get_memory_pss(self):
        """
        获取应用内存PSS值
        """
        cmd = f"adb -s {self.device.sn} shell dumpsys meminfo {self.package.name}"
        result = run_cmd(cmd)

        if result and isinstance(result, str):
            try:
                for line in result.splitlines():
                    if "TOTAL PSS:" in line:
                        # 形如 "TOTAL PSS:  12345 kB"
                        after = line.split("TOTAL PSS:")[1].strip()
                        num = after.split()[0]
                        return int(num)
            except (ValueError, IndexError) as e:
                logging.debug(f"解析内存PSS失败: {str(e)}")

        return None

    def _analyze_memory_trend(self, memory_result):
        """
        分析内存使用趋势，检测内存泄漏
        """
        measurements = memory_result['measurements']
        if len(measurements) < 10:
            return

        # 计算趋势（简单线性回归）
        n = len(measurements)
        x = list(range(n))
        y = measurements

        # 计算斜率
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)

        # 如果斜率明显为正，认为是内存泄漏
        if slope > 50:  # PSS每小时增长50KB以上
            memory_result['trend'] = 'increasing'
            memory_result['memory_leak_detected'] = True
            logging.warning("检测到内存泄漏趋势")
        else:
            memory_result['trend'] = 'stable'
            memory_result['memory_leak_detected'] = False

    # 辅助方法
    def _force_stop_app(self):
        """强制停止应用"""
        cmd = f"adb -s {self.device.sn} shell am force-stop {self.package.name}"
        run_cmd(cmd)

    def _launch_app(self):
        """启动应用"""
        cmd = f"adb -s {self.device.sn} shell am start -n {self.package.name}/{self.package.activity}"
        run_cmd(cmd)

    def _move_app_to_background(self):
        """将应用置于后台"""
        cmd = f"adb -s {self.device.sn} shell input keyevent KEYCODE_HOME"
        run_cmd(cmd)

    def _trigger_data_request(self):
        """触发数据请求（需要根据具体应用定制）"""
        # 这里需要根据应用的具体UI结构来实现
        # 例如：点击某个按钮或执行某个操作
        pass

    def _wait_for_response(self):
        """等待响应完成（需要根据应用日志或UI变化来判断）"""
        # 这里需要根据应用的具体实现来检测响应完成
        # 例如：等待特定日志出现或UI元素出现
        time.sleep(2)  # 简化实现
        return time.time()