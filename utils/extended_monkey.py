#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import logging
import subprocess
import threading
import math
from datetime import datetime, timedelta
from utils.timeout_command import run as run_cmd


class ExtendedMonkeyTest:
    """
    扩展的Monkey测试类
    支持长时间（12-72小时）压力测试
    """

    def __init__(self, device, package, config):
        self.device = device
        self.package = package
        self.config = config
        self.log_path = f"logs/{device.sn}/extended_monkey.log"
        self.logcat_log_path = f"logs/{device.sn}/logcat_monkey.log"
        self._monkey_process = None
        self._logcat_process = None
        self._stop_logcat = threading.Event()

    def run_long_stress_test(self):
        """
        运行长时间压力测试
        """
        # 容错处理：duration_hours 可能来自 GUI / CLI（字符串或浮点数）
        raw_duration = self.config.get('duration_hours', 12)
        try:
            duration_hours = float(raw_duration)
        except Exception:
            duration_hours = 12.0

        if duration_hours <= 0:
            logging.warning(f"收到非法测试时长 {raw_duration}，回退使用默认 12 小时")
            duration_hours = 12.0

        throttle = self.config.get('throttle', 700)
        
        # 按时长推算事件数：事件数 ≈ duration_hours * 3600 * 1000 / throttle
        # 这样可以让 Monkey 理论上跑约等于设定时长
        # 如果配置中明确指定了 event_count，则优先使用配置值（向后兼容）
        if 'event_count' in self.config and self.config.get('event_count') is not None:
            event_count = self.config.get('event_count', 100000)
            logging.info(f"使用配置的事件数: {event_count}")
        else:
            # 根据时长和throttle计算事件数
            # duration_hours * 3600秒 * 1000毫秒 / throttle毫秒 = 事件数
            calculated_events = int((duration_hours * 3600.0 * 1000.0) / throttle)
            # 至少保证有100个事件，避免过短
            event_count = max(100, calculated_events)
            logging.info(f"根据时长 {duration_str} 和 throttle {throttle}ms 计算事件数: {event_count}")

        # 日志中同时友好展示“小时/分钟”
        if duration_hours < 1:
            minutes = duration_hours * 60.0
            duration_str = f"{minutes:g} 分钟 (~{duration_hours:.2f} 小时)"
        else:
            if abs(duration_hours - round(duration_hours)) < 1e-6:
                duration_str = f"{int(round(duration_hours))} 小时"
            else:
                duration_str = f"{duration_hours:.1f} 小时"

        logging.info(f"开始长时间压力测试，持续 {duration_str}")

        # 计算预期结束时间（仅用于结果记录，不直接控制 Monkey 运行时长）
        end_time = datetime.now() + timedelta(hours=duration_hours)

        result = {
            'test_type': 'long_stress',
            'duration_hours': duration_hours,
            'start_time': datetime.now().isoformat(),
            'end_time': end_time.isoformat(),
            'crashes': 0,
            'anrs': 0,
            'performance_data': [],
            'log_summary': {}
        }

        # 初始化日志文件（确保目录存在）
        log_dir = os.path.dirname(self.log_path)
        try:
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
        except Exception as e:
            logging.warning(f"创建日志目录失败 {log_dir}: {e}")

        with open(self.log_path, 'w', encoding='utf-8') as f:
            f.write(f"Extended Monkey Test Start: {datetime.now()}\n")
            f.write(f"Duration: {duration_hours} hours\n")
            f.write(f"Package: {self.package.name}\n")
            f.write("-" * 50 + "\n")

        try:
            # 启动后台监控线程
            monitor_thread = self._start_monitoring_thread(result)
            
            # 启动 logcat 日志抓取线程
            logcat_thread = self._start_logcat_capture()

            # 执行分阶段Monkey测试
            self._run_phased_monkey_test(duration_hours, throttle, event_count, result)

            # 停止监控和logcat
            self._stop_logcat.set()
            if logcat_thread:
                logcat_thread.join(timeout=5)
            monitor_thread.join(timeout=10)

        except Exception as e:
            logging.error(f"长时间压力测试失败: {str(e)}")
            result['error'] = str(e)

        finally:
            result['actual_end_time'] = datetime.now().isoformat()
            self._analyze_test_results(result)

        return result

    def _run_phased_monkey_test(self, duration_hours, throttle, event_count, result):
        """
        分阶段执行Monkey测试
        每个阶段约 1 小时，避免单次测试过长
        """
        # 将"总时长（小时）"换算为阶段数：
        # - 默认每阶段约 1 小时
        # - 小于 1 小时时仍至少执行 1 个阶段（例如 GUI 配置为 1 分钟时，应显示为 1 个阶段而不是 12 个阶段）
        try:
            hours = float(duration_hours)
        except Exception:
            hours = 12.0

        if hours <= 0:
            hours = 12.0

        # 对于非整数时长，取四舍五入后的值，至少为 1
        total_phases = max(1, int(round(hours)))
        
        # 计算每阶段的时长（秒）和事件数
        phase_duration_seconds = (hours * 3600.0) / total_phases
        events_per_phase = max(1, event_count // total_phases)

        for phase in range(total_phases):
            logging.info(f"执行第 {phase + 1}/{total_phases} 阶段压力测试（目标时长: {phase_duration_seconds:.1f}秒）")

            # 清理应用状态
            self._cleanup_app_state()

            # 执行单阶段 Monkey 测试（带超时控制）
            phase_result = self._run_single_phase_monkey(
                phase, throttle, events_per_phase, phase_duration_seconds
            )

            # 记录阶段结果
            result['performance_data'].append({
                'phase': phase + 1,
                'start_time': phase_result['start_time'],
                'end_time': phase_result['end_time'],
                'events_executed': phase_result['events'],
                'crashes_in_phase': phase_result['crashes'],
                'anrs_in_phase': phase_result['anrs']
            })

            result['crashes'] += phase_result['crashes']
            result['anrs'] += phase_result['anrs']

            # 检查是否需要提前结束
            if self._should_stop_test(result):
                logging.warning("检测到严重问题，提前结束测试")
                break

            # 阶段间休息（最后一个阶段不需要休息）
            if phase < total_phases - 1:
                time.sleep(60)  # 1分钟休息

    def _run_single_phase_monkey(self, phase, throttle, event_count, phase_duration_seconds):
        """
        执行单个阶段的Monkey测试（带超时控制）
        
        Args:
            phase: 阶段编号
            throttle: 节流时间（毫秒）
            event_count: 事件数
            phase_duration_seconds: 阶段目标时长（秒），超过此时长会强制结束
        """
        phase_log = f"logs/{self.device.sn}/monkey_phase_{phase + 1}.log"

        # 停止应用进程
        cmd = f"adb -s {self.device.sn} shell am force-stop {self.package.name}"
        run_cmd(cmd)
        time.sleep(3)

        # 执行Monkey命令
        import random
        seed = random.randint(0, 65535)

        # 构建Monkey命令（不使用shell重定向，改用subprocess直接捕获）
        monkey_cmd = [
            "adb", "-s", self.device.sn, "shell", "monkey",
            "-p", self.package.name,
            "-s", str(seed),
            "--ignore-crashes",
            "--ignore-timeouts",
            "--ignore-security-exceptions",
            "--ignore-native-crashes",
            "--throttle", str(throttle),
            "-v", str(event_count)
        ]

        logging.info(f"执行Monkey命令: {' '.join(monkey_cmd)}")

        start_time = datetime.now()
        phase_start_time = time.time()
        
        # 使用subprocess.Popen启动Monkey进程
        try:
            # 解析adb路径
            from utils.timeout_command import _resolve_adb_path
            adb_path = _resolve_adb_path()
            if adb_path:
                monkey_cmd[0] = adb_path
            
            process = subprocess.Popen(
                monkey_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False
            )
            self._monkey_process = process
            
            # 同时将输出写入日志文件
            log_file = open(phase_log, 'wb')
            
            # 启动超时监控线程
            timeout_thread = threading.Thread(
                target=self._monitor_monkey_timeout,
                args=(process, phase_duration_seconds, phase_start_time),
                daemon=True
            )
            timeout_thread.start()
            
            # 使用线程读取输出，主线程监控超时
            output_thread = threading.Thread(
                target=self._read_monkey_output,
                args=(process, log_file),
                daemon=True
            )
            output_thread.start()
            
            # 主线程监控超时
            elapsed = 0
            while process.poll() is None:
                elapsed = time.time() - phase_start_time
                if elapsed >= phase_duration_seconds:
                    logging.warning(f"阶段 {phase + 1} 超过目标时长 {phase_duration_seconds:.1f}秒，强制结束")
                    self._kill_monkey_process(process)
                    break
                time.sleep(0.5)  # 每0.5秒检查一次
            
            # 等待输出线程结束
            output_thread.join(timeout=2)
            
            # 如果进程还在运行，再次尝试等待（最多再等2秒）
            if process.poll() is None:
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._kill_monkey_process(process)
            
            # 确保日志文件已关闭
            try:
                log_file.close()
            except Exception:
                pass
            
        except Exception as e:
            logging.error(f"执行Monkey命令失败: {e}")
            if process and process.poll() is None:
                self._kill_monkey_process(process)
        
        finally:
            self._monkey_process = None
        
        end_time = datetime.now()
        actual_duration = (end_time - start_time).total_seconds()

        # 再次停止应用
        cmd = f"adb -s {self.device.sn} shell am force-stop {self.package.name}"
        run_cmd(cmd)

        # 分析阶段日志（包括logcat）
        phase_stats = self._analyze_phase_log(phase_log)
        logcat_stats = self._analyze_logcat_for_phase(phase + 1, start_time, end_time)
        
        # 合并统计结果
        total_crashes = phase_stats['crashes'] + logcat_stats['crashes']
        total_anrs = phase_stats['anrs'] + logcat_stats['anrs']

        logging.info(f"阶段 {phase + 1} 完成: 实际耗时 {actual_duration:.1f}秒, "
                    f"崩溃 {total_crashes} 次, ANR {total_anrs} 次")

        return {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'events': event_count,
            'crashes': total_crashes,
            'anrs': total_anrs,
            'actual_duration_seconds': actual_duration
        }
    
    def _monitor_monkey_timeout(self, process, timeout_seconds, start_time):
        """监控Monkey进程超时"""
        while process.poll() is None:
            elapsed = time.time() - start_time
            if elapsed >= timeout_seconds:
                logging.warning(f"检测到超时（{elapsed:.1f}秒 >= {timeout_seconds:.1f}秒），准备强制结束")
                self._kill_monkey_process(process)
                break
            time.sleep(1)
    
    def _read_monkey_output(self, process, log_file):
        """在后台线程中读取Monkey输出"""
        try:
            # 持续读取直到进程结束且没有更多输出
            while True:
                chunk = process.stdout.read(4096)
                if chunk:
                    log_file.write(chunk)
                    log_file.flush()
                elif process.poll() is not None:
                    # 进程已结束且没有更多输出
                    break
                else:
                    # 进程还在运行但暂时没有输出
                    time.sleep(0.1)
        except Exception as e:
            logging.warning(f"读取Monkey输出时出错: {e}")
        finally:
            try:
                log_file.flush()
            except Exception:
                pass
    
    def _kill_monkey_process(self, process):
        """强制结束Monkey进程"""
        if process is None:
            return
        
        try:
            # 先尝试terminate
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # 如果5秒内没结束，强制kill
                process.kill()
                process.wait()
            
            # 同时通过adb kill掉设备上的monkey进程
            import sys
            if sys.platform == 'win32':
                # Windows: 使用taskkill或adb shell kill
                cmd = f"adb -s {self.device.sn} shell killall monkey"
            else:
                cmd = f"adb -s {self.device.sn} shell pkill -f monkey"
            run_cmd(cmd, timeout=3)
            logging.info("已强制结束Monkey进程")
        except Exception as e:
            logging.warning(f"结束Monkey进程时出错: {e}")

    def _analyze_phase_log(self, log_path):
        """
        分析阶段日志（Monkey stdout），统计崩溃和ANR
        """
        crashes = 0
        anrs = 0

        try:
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        line = line.strip()
                        if f"// CRASH: {self.package.name}" in line:
                            crashes += 1
                        elif f"// NOT RESPONDING: {self.package.name}" in line:
                            anrs += 1
        except Exception as e:
            logging.warning(f"分析阶段日志失败: {str(e)}")

        return {'crashes': crashes, 'anrs': anrs}
    
    def _start_logcat_capture(self):
        """
        启动logcat日志抓取线程
        """
        def capture_logcat():
            """在后台持续抓取logcat日志"""
            log_dir = os.path.dirname(self.logcat_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            # 清空之前的logcat日志
            cmd = f"adb -s {self.device.sn} logcat -c"
            run_cmd(cmd, timeout=5)
            
            # 启动logcat抓取（过滤应用相关日志）
            logcat_cmd = [
                "adb", "-s", self.device.sn, "logcat",
                "-v", "time",
                f"{self.package.name}:*", "AndroidRuntime:E", "*:S"
            ]
            
            try:
                from utils.timeout_command import _resolve_adb_path
                adb_path = _resolve_adb_path()
                if adb_path:
                    logcat_cmd[0] = adb_path
                
                process = subprocess.Popen(
                    logcat_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False
                )
                self._logcat_process = process
                
                with open(self.logcat_log_path, 'wb') as f:
                    while not self._stop_logcat.is_set():
                        if process.poll() is not None:
                            break
                        try:
                            chunk = process.stdout.read(4096)
                            if chunk:
                                f.write(chunk)
                                f.flush()
                        except Exception:
                            break
                        time.sleep(0.1)
                
                # 停止logcat
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
            except Exception as e:
                logging.warning(f"logcat抓取失败: {e}")
            finally:
                self._logcat_process = None
        
        logcat_thread = threading.Thread(target=capture_logcat, daemon=True)
        logcat_thread.start()
        return logcat_thread
    
    def _analyze_logcat_for_phase(self, phase, start_time, end_time):
        """
        从logcat日志中分析指定时间段的崩溃和ANR
        
        Args:
            phase: 阶段编号
            start_time: 阶段开始时间
            end_time: 阶段结束时间
        """
        crashes = 0
        anrs = 0
        
        try:
            if not os.path.exists(self.logcat_log_path):
                return {'crashes': 0, 'anrs': 0}
            
            # 将datetime转换为logcat时间格式（MM-DD HH:MM:SS.mmm）
            start_str = start_time.strftime("%m-%d %H:%M:%S")
            end_str = end_time.strftime("%m-%d %H:%M:%S")
            
            with open(self.logcat_log_path, 'r', encoding='utf-8', errors='ignore') as f:
                in_phase = False
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检查时间戳是否在阶段范围内
                    # logcat格式: MM-DD HH:MM:SS.mmm level/tag: message
                    try:
                        # 提取时间戳（前19个字符：MM-DD HH:MM:SS.mmm）
                        if len(line) >= 19:
                            time_str = line[:19]
                            # 简单比较（不考虑年份，因为测试通常在同一天）
                            if start_str <= time_str <= end_str:
                                in_phase = True
                            elif time_str > end_str:
                                break
                    except Exception:
                        pass
                    
                    if not in_phase:
                        continue
                    
                    # 检查崩溃信息
                    # AndroidRuntime崩溃通常包含: FATAL EXCEPTION, Process, PID
                    if "FATAL EXCEPTION" in line and self.package.name in line:
                        crashes += 1
                    elif "AndroidRuntime" in line and "FATAL" in line:
                        # 检查下一行是否包含包名
                        crashes += 1
                    elif f"Process: {self.package.name}" in line and "FATAL" in line:
                        crashes += 1
                    
                    # 检查ANR信息
                    # ANR通常包含: ANR in, Process, NOT RESPONDING
                    if "ANR in" in line and self.package.name in line:
                        anrs += 1
                    elif "NOT RESPONDING" in line and self.package.name in line:
                        anrs += 1
                    elif "ActivityManager" in line and "ANR" in line and self.package.name in line:
                        anrs += 1
                        
        except Exception as e:
            logging.warning(f"分析logcat日志失败: {str(e)}")
        
        if crashes > 0 or anrs > 0:
            logging.info(f"从logcat检测到阶段 {phase} 的崩溃: {crashes} 次, ANR: {anrs} 次")
        
        return {'crashes': crashes, 'anrs': anrs}

    def _start_monitoring_thread(self, result):
        """
        启动后台监控线程
        监控CPU、内存等性能指标
        """
        def monitor():
            while True:
                try:
                    # 监控CPU使用率
                    cpu_usage = self._get_cpu_usage()

                    # 监控内存使用率
                    mem_usage = self._get_memory_usage()

                    # 记录性能数据
                    perf_data = {
                        'timestamp': datetime.now().isoformat(),
                        'cpu_usage': cpu_usage,
                        'memory_pss': mem_usage
                    }

                    result['performance_data'].append(perf_data)

                    time.sleep(30)  # 每30秒采样一次

                except Exception as e:
                    logging.warning(f"性能监控出错: {str(e)}")
                    time.sleep(30)

        import threading
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        return monitor_thread

    def _get_cpu_usage(self):
        """获取CPU使用率"""
        cmd = f"adb -s {self.device.sn} shell top -n 1 -d 0"
        result = run_cmd(cmd)

        if result and isinstance(result, str):
            try:
                for line in result.splitlines():
                    if self.package.name in line:
                        parts = line.split()
                        for token in parts:
                            if token.endswith('%'):
                                return float(token.rstrip('%'))
            except Exception:
                pass

        return 0.0

    def _get_memory_usage(self):
        """获取内存使用率（PSS）"""
        cmd = f"adb -s {self.device.sn} shell dumpsys meminfo {self.package.name}"
        result = run_cmd(cmd)

        if result and isinstance(result, str):
            try:
                for line in result.splitlines():
                    if "TOTAL PSS:" in line:
                        after = line.split("TOTAL PSS:")[1].strip()
                        num = after.split()[0]
                        return int(num)
            except Exception:
                pass

        return 0

    def _cleanup_app_state(self):
        """清理应用状态"""
        # 清除应用数据
        cmd = f"adb -s {self.device.sn} shell pm clear {self.package.name}"
        run_cmd(cmd)

        # 重启应用验证
        time.sleep(2)

    def _should_stop_test(self, result):
        """
        检查是否应该停止测试
        如果发现太多崩溃或ANR，提前结束
        """
        # 如果单小时内崩溃超过5次或ANR超过3次，停止测试
        recent_performance = result.get('performance_data', [])
        if len(recent_performance) >= 120:  # 1小时的数据
            recent_hour_data = recent_performance[-120:]
            recent_crashes = sum(item.get('crashes_in_phase', 0) for item in recent_hour_data if 'crashes_in_phase' in item)
            recent_anrs = sum(item.get('anrs_in_phase', 0) for item in recent_hour_data if 'anrs_in_phase' in item)

            if recent_crashes >= 5 or recent_anrs >= 3:
                return True

        return False

    def _analyze_test_results(self, result):
        """分析测试结果"""
        total_time = len(result.get('performance_data', [])) * 30  # 30秒采样间隔

        if total_time > 0:
            # 计算平均性能指标
            cpu_data = [d.get('cpu_usage', 0) for d in result['performance_data'] if isinstance(d, dict) and 'cpu_usage' in d]
            mem_data = [d.get('memory_pss', 0) for d in result['performance_data'] if isinstance(d, dict) and 'memory_pss' in d]

            result['log_summary'] = {
                'total_test_time_seconds': total_time,
                'average_cpu_usage': sum(cpu_data) / len(cpu_data) if cpu_data else 0,
                'peak_cpu_usage': max(cpu_data) if cpu_data else 0,
                'average_memory_pss': sum(mem_data) / len(mem_data) if mem_data else 0,
                'peak_memory_pss': max(mem_data) if mem_data else 0,
                'total_crashes': result['crashes'],
                'total_anrs': result['anrs']
            }

        logging.info(f"测试结果分析完成: {result['log_summary']}")