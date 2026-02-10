#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
压力测试共用监控逻辑
供 BroadcastStressTest、TTSStressTest 等复用：前台检测、CPU/内存采样、logcat 采集与崩溃/ANR 分析
"""

import os
import json
import time
import logging
import subprocess
import threading
import collections
from datetime import datetime, timedelta

from utils.timeout_command import run as run_cmd


class StressMonitor:
    """压力测试监控器，提供前台检测、性能采样、logcat 采集与崩溃/ANR 分析"""

    def __init__(self, device, package, config=None):
        self.device = device
        self.package = package
        self.config = config or {}
        self._stop_monitor = threading.Event()
        self._stop_logcat = threading.Event()
        self._logcat_process = None
        # 设备时间与本机时间差（秒），用于将 logcat 时间戳对齐到本机时间轴，减少统计误差
        self._device_time_offset = None
        # ERROR 日志监控
        self._error_monitor_stop = threading.Event()

    def _get_package_name(self):
        return getattr(self.package, "name", None) or getattr(self.package, "package", None) or ""

    def is_app_in_foreground(self):
        """判断待测应用是否在前台"""
        pkg = self._get_package_name()
        if not pkg:
            return False
        try:
            cmd = f"adb -s {self.device.sn} shell dumpsys window windows"
            out = run_cmd(cmd, timeout=3)
            if isinstance(out, str):
                for line in out.splitlines():
                    line = line.strip()
                    if "mCurrentFocus" in line or "mFocusedApp" in line:
                        if pkg in line:
                            return True
            cmd = f"adb -s {self.device.sn} shell dumpsys activity activities"
            out = run_cmd(cmd, timeout=3)
            if isinstance(out, str):
                for line in out.splitlines():
                    line = line.strip()
                    if "mResumedActivity" in line or "resumed" in line.lower():
                        if pkg in line:
                            return True
        except Exception:
            pass
        return False

    def ensure_app_in_foreground(self):
        """确保待测应用处于前台，不在则拉起"""
        pkg = self._get_package_name()
        if not pkg:
            logging.warning("[stress-monitor] 无法确定包名，跳过前台唤醒")
            return
        activity = getattr(self.package, "activity", None) if hasattr(self.package, "activity") else None
        wait_seconds = 5.0
        try:
            cfg_val = self.config.get("fallback_launch_wait_seconds")
            if cfg_val is not None:
                wait_seconds = max(1.0, float(cfg_val))
        except Exception:
            pass
        poll_interval = 0.5
        settle_delay = 0.8
        strategies = [
            (f"adb -s {self.device.sn} shell am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {pkg}", 10),
        ]
        if activity:
            strategies.append((f"adb -s {self.device.sn} shell am start -W -n {pkg}/{activity}", 15))
        strategies.append((f"adb -s {self.device.sn} shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1", 10))
        for cmd, timeout in strategies:
            logging.info(f"[stress-monitor] 尝试拉起应用到前台")
            run_cmd(cmd, timeout=timeout)
            time.sleep(settle_delay)
            deadline = time.time() + wait_seconds
            while time.time() < deadline:
                if self.is_app_in_foreground():
                    logging.info("[stress-monitor] 检测到待测应用已在前台")
                    return
                time.sleep(poll_interval)
        logging.info("[stress-monitor] 已尝试所有拉起方式，将继续执行")

    def get_cpu_usage(self):
        """获取 CPU 使用率"""
        pkg = self._get_package_name()
        if not pkg:
            return 0.0
        try:
            cmd = f"adb -s {self.device.sn} shell top -n 1 -d 0"
            result = run_cmd(cmd, timeout=3)
            if result and isinstance(result, str):
                for line in result.splitlines():
                    if pkg in line:
                        parts = line.split()
                        for token in parts:
                            if token.endswith('%'):
                                try:
                                    cpu_val = float(token.rstrip('%'))
                                    if 0 <= cpu_val <= 100:
                                        return cpu_val
                                except ValueError:
                                    pass
        except Exception:
            pass
        return 0.0

    def get_memory_usage(self):
        """获取内存使用量 PSS（KB）"""
        pkg = self._get_package_name()
        if not pkg:
            return 0
        cmd = f"adb -s {self.device.sn} shell dumpsys meminfo {pkg}"
        result = run_cmd(cmd, timeout=5)
        if result and isinstance(result, str):
            try:
                for line in result.splitlines():
                    if "TOTAL PSS:" in line:
                        after = line.split("TOTAL PSS:")[1].strip()
                        num_str = after.split()[0].replace(',', '')
                        return int(num_str)
            except Exception:
                pass
        return 0

    def start_monitoring_thread(self, result, interval_seconds, perf_log_path):
        """启动后台监控线程：每 interval_seconds 采样 CPU/内存并写入 JSONL"""
        def monitor():
            log_dir = os.path.dirname(perf_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            log_file = open(perf_log_path, 'a', encoding='utf-8')
            while True:
                try:
                    if self._stop_monitor.is_set():
                        break
                    is_fg = self.is_app_in_foreground()
                    mode = "foreground" if is_fg else "background"
                    cpu_usage = self.get_cpu_usage()
                    mem_usage = self.get_memory_usage()
                    memory_mb = round(mem_usage / 1024.0, 2) if mem_usage > 0 else 0.0
                    perf_data = {
                        'timestamp': datetime.now().isoformat(),
                        'cpu_usage': cpu_usage,
                        'memory_pss': mem_usage,
                        'memory_pss_mb': memory_mb,
                        'mode': mode,
                        'device_sn': self.device.sn,
                        'package': self._get_package_name(),
                    }
                    result['performance_data'].append(perf_data)
                    log_file.write(json.dumps(perf_data, ensure_ascii=False) + "\n")
                    log_file.flush()
                    try:
                        os.fsync(log_file.fileno())
                    except Exception:
                        pass
                    time.sleep(interval_seconds)
                except Exception as e:
                    logging.warning(f"性能监控出错: {str(e)}")
                    time.sleep(interval_seconds)
            try:
                log_file.flush()
                log_file.close()
            except Exception:
                pass
        t = threading.Thread(target=monitor, daemon=True)
        t.start()
        return t

    def start_logcat_capture(self, logcat_log_path):
        """
        启动 logcat 抓取线程（全量）。
        注意：旧实现使用 tag 过滤（如 f"{pkg}:*" + "*:S"），在多数应用下会导致日志为空。
        这里改为抓取全量 logcat，作为每次测试的完整记录。
        """
        self.logcat_log_path = logcat_log_path

        def capture_logcat():
            log_dir = os.path.dirname(logcat_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            run_cmd(f"adb -s {self.device.sn} logcat -c", timeout=5)
            try:
                from utils.timeout_command import _resolve_adb_path
                adb_path = _resolve_adb_path()
                adb_bin = adb_path or "adb"
                # 用 threadtime 带 pid/tid，便于后续排查；不加 selectors => 全量
                logcat_cmd = [adb_bin, "-s", self.device.sn, "logcat", "-v", "threadtime"]
                process = subprocess.Popen(
                    logcat_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self._logcat_process = process
                with open(logcat_log_path, 'w', encoding='utf-8', errors='replace') as f:
                    while not self._stop_logcat.is_set():
                        if process.poll() is not None:
                            break
                        try:
                            line = process.stdout.readline()
                            if line:
                                f.write(line)
                                f.flush()
                        except Exception:
                            break
                        time.sleep(0.1)
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

        t = threading.Thread(target=capture_logcat, daemon=True)
        t.start()
        return t

    def run_foreground_guard(self, duration_seconds):
        """每 2 秒检测前台，不在则拉起，运行指定时长"""
        check_interval = 2.0
        start_ts = time.time()
        while not self._stop_monitor.is_set() and (time.time() - start_ts) < duration_seconds:
            try:
                if not self.is_app_in_foreground():
                    logging.info("[foreground-guard] 检测到待测应用不在前台，主动拉起")
                    self.ensure_app_in_foreground()
                    time.sleep(1.0)
                time.sleep(check_interval)
            except Exception as e:
                logging.debug(f"[foreground-guard] 异常: {e}")
                time.sleep(check_interval)

    def stop(self):
        """停止监控与 logcat"""
        self._stop_monitor.set()
        self._stop_logcat.set()
        self._error_monitor_stop.set()
        if self._logcat_process and self._logcat_process.poll() is None:
            try:
                self._logcat_process.terminate()
                self._logcat_process.wait(timeout=2)
            except Exception:
                pass
        self._logcat_process = None

    def start_error_log_monitor(self, package_name: str = None, log_tags=None, min_restart_interval: float = 10.0):
        """
        启动通用 ERROR 日志监控线程：
        - 参考命令：adb logcat -s com.svw.avatar:V AndroidRuntime:E
        - 当检测到与待测应用相关的 ERROR 级别日志时，自动尝试拉起应用到前台。

        Args:
            package_name: 目标应用包名，默认为当前 package.name
            log_tags: 额外需要关注的 tag 列表（如 ["AndroidRuntime:E"]），可为空
            min_restart_interval: 连续 ERROR 之间触发自动拉起的最小间隔（秒），避免频繁重启
        """
        pkg = (package_name or self._get_package_name() or "").strip()
        if not pkg:
            logging.warning("[error-monitor] 未指定包名，跳过 ERROR 监控")
            return None

        self._error_monitor_stop.clear()

        def _worker():
            last_restart_ts = 0.0
            try:
                from utils.timeout_command import _resolve_adb_path
                adb_path = _resolve_adb_path() or "adb"
                tags = []
                # 参考 adb logcat -s com.svw.avatar:V AndroidRuntime:E
                tags.append(f"{pkg}:V")
                if log_tags:
                    tags.extend(log_tags)
                else:
                    tags.append("AndroidRuntime:E")
                cmd = [adb_path, "-s", self.device.sn, "logcat", "-v", "time", "-s"] + tags
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                while not self._error_monitor_stop.is_set() and proc.poll() is None:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    stripped = line.strip()
                    if not stripped:
                        continue
                    parts = stripped.split()
                    # threadtime 格式：MM-DD HH:MM:SS.mmm PID TID priority TAG: msg
                    level = parts[4] if len(parts) > 4 else ""
                    if level != "E":
                        continue
                    if pkg not in stripped and "AndroidRuntime" not in stripped:
                        continue
                    now_ts = time.time()
                    if now_ts - last_restart_ts < max(1.0, float(min_restart_interval or 0)):
                        continue
                    last_restart_ts = now_ts
                    logging.warning(f"[error-monitor] 检测到 ERROR 日志，尝试自动拉起应用: {stripped[:200]}")
                    try:
                        self.ensure_app_in_foreground()
                    except Exception as e:
                        logging.warning(f"[error-monitor] 自动拉起应用失败: {e}")
                try:
                    proc.terminate()
                except Exception:
                    pass
            except Exception as e:
                logging.debug(f"[error-monitor] 启动 ERROR 监控失败: {e}")

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    def analyze_logcat_for_crashes_anrs(self, start_time, end_time):
        """分析 logcat 中指定时间段的崩溃与 ANR"""
        logcat_path = getattr(self, 'logcat_log_path', None)
        if not logcat_path or not os.path.exists(logcat_path):
            return {'crashes': 0, 'anrs': 0}
        pkg = self._get_package_name()
        crashes = 0
        anrs = 0
        try:
            start_str = start_time.strftime("%m-%d %H:%M:%S")
            end_str = end_time.strftime("%m-%d %H:%M:%S")
            with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
                in_phase = False
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        if len(line) >= 19:
                            time_str = line[:19]
                            if start_str <= time_str <= end_str:
                                in_phase = True
                            elif time_str > end_str:
                                break
                    except Exception:
                        pass
                    if not in_phase:
                        continue
                    if "FATAL EXCEPTION" in line and pkg in line:
                        crashes += 1
                    elif "AndroidRuntime" in line and "FATAL" in line:
                        crashes += 1
                    elif f"Process: {pkg}" in line and "FATAL" in line:
                        crashes += 1
                    if "ANR in" in line and pkg in line:
                        anrs += 1
                    elif "NOT RESPONDING" in line and pkg in line:
                        anrs += 1
                    elif "ActivityManager" in line and "ANR" in line and pkg in line:
                        anrs += 1
        except Exception as e:
            logging.warning(f"分析logcat失败: {str(e)}")
        if crashes > 0 or anrs > 0:
            logging.info(f"从logcat检测到崩溃: {crashes} 次, ANR: {anrs} 次")
        return {'crashes': crashes, 'anrs': anrs}

    @staticmethod
    def extract_exceptions_to_file(logcat_path, output_path, start_time, end_time, package_name,
                                   include_error_level=True, context_lines_after=15):
        """
        从 logcat 中提取 crash、ANR、ERROR 等异常行，写入独立异常日志文件。

        Args:
            logcat_path: logcat 文件路径
            output_path: 异常日志输出路径（如 exceptions.log）
            start_time: 开始时间 (datetime)
            end_time: 结束时间 (datetime)
            package_name: 应用包名，用于过滤
            include_error_level: 是否包含 logcat ERROR 级别且与包相关的行
            context_lines_after: crash/ANR 后附带上下文行数（栈帧等）

        Returns:
            int: 写入的异常记录条数
        """
        if not logcat_path or not os.path.exists(logcat_path) or not package_name:
            return 0
        pkg = package_name
        try:
            start_str = start_time.strftime("%m-%d %H:%M:%S")
            end_str = end_time.strftime("%m-%d %H:%M:%S")
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            written = 0
            with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as fin:
                lines = list(fin)

            with open(output_path, 'w', encoding='utf-8', errors='replace') as fout:
                fout.write(f"# 异常日志提取: {start_str} ~ {end_str}, 包名: {pkg}\n")
                fout.write("# 包含: 崩溃(Crash)、ANR、ERROR 级别日志\n")
                fout.write("-" * 60 + "\n")

                i = 0
                while i < len(lines):
                    line = lines[i]
                    raw = line
                    stripped = line.strip()
                    if not stripped:
                        i += 1
                        continue
                    time_str = stripped[:19] if len(stripped) >= 19 else ""
                    in_range = start_str <= time_str <= end_str if time_str else False
                    if time_str and time_str > end_str:
                        break

                    is_crash = in_range and (
                        ("FATAL EXCEPTION" in stripped and pkg in stripped) or
                        ("AndroidRuntime" in stripped and "FATAL" in stripped) or
                        (f"Process: {pkg}" in stripped and "FATAL" in stripped)
                    )
                    is_anr = in_range and (
                        ("ANR in" in stripped and pkg in stripped) or
                        ("NOT RESPONDING" in stripped and pkg in stripped) or
                        ("ActivityManager" in stripped and "ANR" in stripped and pkg in stripped)
                    )
                    is_error = False
                    if include_error_level and in_range:
                        parts = stripped.split()
                        if len(parts) >= 5 and parts[4] == "E" and pkg in stripped:
                            is_error = True

                    if is_crash or is_anr:
                        fout.write(raw)
                        written += 1
                        for j in range(1, min(context_lines_after + 1, len(lines) - i)):
                            next_line = lines[i + j]
                            next_stripped = next_line.strip()
                            if not next_stripped:
                                fout.write(next_line)
                                continue
                            next_ts = next_stripped[:19] if len(next_stripped) >= 19 else ""
                            if next_ts and next_ts > end_str:
                                break
                            if next_stripped.startswith("at ") or next_stripped[0:1].isspace() or \
                               "Caused by:" in next_stripped or "at " in next_stripped:
                                fout.write(next_line)
                            else:
                                break
                        fout.write("\n")
                    elif is_error:
                        fout.write(raw)
                        written += 1

                    i += 1

            if written > 0:
                logging.info(f"异常日志已写入 {output_path}，共 {written} 条")
            return written
        except Exception as e:
            logging.warning(f"提取异常日志失败: {e}")
            return 0

    def _response_monitor_params(self):
        """
        从 config 读取响应监控时间参数，返回
        (max_wait_for_appear, check_interval, max_wait_for_disappear)。

        说明：
        - 旧版本存在 wait_after_send（发送后固定等待），已废弃并从配置中移除；
          现在发送后立即开始基于 logcat 的实时监控。
        """
        rm = self.config.get('response_monitor', {})
        def _float(key, default, min_val=0.1, max_val=3600):
            try:
                v = rm.get(key)
                if v is None:
                    return default
                f = float(v)
                return max(min_val, min(max_val, f))
            except (TypeError, ValueError):
                return default
        return (
            _float('max_wait_for_appear', 6),
            _float('check_interval', 0.1),
            _float('max_wait_for_disappear', 300),
        )

    def _ensure_device_time_offset(self):
        """
        计算并缓存设备时间与本机时间差（秒）。

        delta = pc_time - device_time
        之后可通过 device_dt + delta 将设备时间对齐到本机时间轴。
        """
        if self._device_time_offset is not None:
            return
        try:
            cmd = f"adb -s {self.device.sn} shell date +%s"
            out = run_cmd(cmd, timeout=5)
            if not out:
                return
            try:
                dev_ts = float(str(out).strip().splitlines()[-1].strip())
            except Exception:
                return
            pc_ts = time.time()
            self._device_time_offset = pc_ts - dev_ts
            logging.info(f"[stress-monitor] 设备时间已校准，PC-设备时间差约为 {self._device_time_offset:.3f} 秒")
        except Exception as e:
            logging.debug(f"[stress-monitor] 计算设备时间差失败: {e}")

    def _parse_logcat_timestamp(self, line: str):
        """
        解析 logcat 时间戳，兼容：
        - -v time / threadtime:  MM-DD HH:MM:SS.mmm
        - 部分设备/工具链：      YYYY-MM-DD HH:MM:SS.mmm
        返回 datetime（无时区；若无年份则使用当前年）。
        """
        if not line or len(line) < 19:
            return None
        import re
        # 1) YYYY-MM-DD HH:MM:SS(.mmm)?
        m = re.match(r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2}) (?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})(?:\.(?P<ms>\d{1,6}))?", line)
        if m:
            try:
                frac = (m.group("ms") or "0").ljust(6, "0")
                dt = datetime(
                    int(m.group("y")), int(m.group("m")), int(m.group("d")),
                    int(m.group("h")), int(m.group("mi")), int(m.group("s")),
                    int(frac)
                )
                return dt
            except Exception:
                return None
        # 2) MM-DD HH:MM:SS(.mmm)?
        m2 = re.match(r"^(?P<m>\d{2})-(?P<d>\d{2}) (?P<h>\d{2}):(?P<mi>\d{2}):(?P<s>\d{2})(?:\.(?P<ms>\d{1,6}))?", line)
        if m2:
            try:
                frac = (m2.group("ms") or "0").ljust(6, "0")
                dt = datetime(
                    datetime.now().year, int(m2.group("m")), int(m2.group("d")),
                    int(m2.group("h")), int(m2.group("mi")), int(m2.group("s")),
                    int(frac)
                )
                return dt
            except Exception:
                return None
        return None

    def _logcat_filter_params(self):
        """从 config 读取 logcat 过滤规则，返回 (tag_filter, appear_text, disappear_text)"""
        rm = self.config.get('response_monitor', {})
        tag = (rm.get('logcat_tag') or 'FusedVrCardService').strip()
        appear = (rm.get('logcat_appear_text') or '融合卡片已显示').strip()
        disappear = (rm.get('logcat_disappear_text') or '融合卡片已隐藏').strip()
        return tag, appear, disappear

    def _monitor_response_via_logcat(self, wait_after_send, max_wait_for_appear, check_interval, max_wait_for_disappear, request_send_time=None):
        """
        通过 adb logcat 监控融合卡片出现/消失。
        匹配规则：tag 包含 logcat_tag，消息包含 logcat_appear_text（出现）或 logcat_disappear_text（消失）。
        仅处理时间戳 >= request_send_time 的日志行，使用 log 实际时间戳计算 response_time、display_duration。
        """
        result = {
            'status': 'error',
            'appear_time': None,
            'disappear_time': None,
            'response_time': None,
            'display_duration': None,
            'model_name': None,
            'error': None
        }
        tag_filter, appear_text, disappear_text = self._logcat_filter_params()
        lines = collections.deque()
        line_lock = threading.Lock()
        stop_logcat = threading.Event()

        # 时间戳过滤：只接受不早于 request_send_time - 2s 的日志（设备与 PC 可能有时差）
        cutoff_dt = None
        if request_send_time:
            try:
                cutoff_dt = request_send_time - timedelta(seconds=2)
            except Exception:
                pass

        # 若提供了 request_send_time，则尝试对齐设备时间到 PC 时间轴
        device_offset = None
        if request_send_time:
            self._ensure_device_time_offset()
            device_offset = self._device_time_offset

        def _is_line_valid(line):
            if cutoff_dt is None:
                return True
            parsed = self._parse_logcat_timestamp(line)
            # 解析失败时不丢弃（避免因格式差异导致漏检）
            if parsed is None:
                return True
            aligned = parsed
            if device_offset is not None:
                try:
                    aligned = parsed + timedelta(seconds=device_offset)
                except Exception:
                    aligned = parsed
            return aligned >= cutoff_dt

        def logcat_reader():
            try:
                from utils.timeout_command import _resolve_adb_path
                adb_path = _resolve_adb_path() or "adb"
                logcat_cmd = [adb_path, "-s", self.device.sn, "logcat", "-v", "time"]
                proc = subprocess.Popen(
                    logcat_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding='utf-8', errors='replace'
                )
                while not stop_logcat.is_set() and proc.poll() is None:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    # 以关键字为主匹配；tag_filter 仅作为“可选的缩小范围”条件，避免因 tag 不一致导致漏检
                    if (appear_text in line or disappear_text in line) and (not tag_filter or tag_filter in line):
                        with line_lock:
                            lines.append(line.strip())
                try:
                    proc.terminate()
                except Exception:
                    pass
            except Exception as e:
                logging.debug(f"[response-monitor] logcat 读取异常: {e}")

        reader = threading.Thread(target=logcat_reader, daemon=True)
        reader.start()

        try:
            # 发送后不再做固定等待，直接开始监控；保持 poll_start 作为回退参考时间
            poll_start = time.time()
            appear_deadline = poll_start + max_wait_for_appear
            appear_log_ts = None
            appear_line_ts_dt = None

            while time.time() < appear_deadline:
                with line_lock:
                    while lines:
                        line = lines.popleft()
                        if not _is_line_valid(line):
                            continue
                        if appear_text in line:
                            parsed_dt = self._parse_logcat_timestamp(line)
                            if parsed_dt:
                                appear_line_ts_dt = parsed_dt
                                aligned_dt = parsed_dt
                                if device_offset is not None:
                                    try:
                                        aligned_dt = parsed_dt + timedelta(seconds=device_offset)
                                    except Exception:
                                        aligned_dt = parsed_dt
                                appear_log_ts = aligned_dt.timestamp()
                                ref_time = request_send_time if request_send_time else datetime.fromtimestamp(poll_start)
                                result['response_time'] = (aligned_dt - ref_time).total_seconds()
                            else:
                                appear_log_ts = time.time()
                                result['response_time'] = appear_log_ts - poll_start
                            result['appear_time'] = appear_log_ts
                            result['status'] = 'success'
                            logging.info(f"[response-monitor] logcat 检测到「{appear_text}」，响应时间: {result['response_time']:.3f}秒")
                            break
                if appear_log_ts is not None:
                    break
                time.sleep(check_interval)

            if appear_log_ts is None:
                result['status'] = 'timeout_appear'
                result['error'] = f'在{max_wait_for_appear}秒内未检测到 logcat「{appear_text}」'
                logging.warning(f"[response-monitor] {result['error']}")
                return result

            disappear_deadline = time.time() + max_wait_for_disappear
            disappear_log_ts = None

            while time.time() < disappear_deadline:
                with line_lock:
                    while lines:
                        line = lines.popleft()
                        if not _is_line_valid(line):
                            continue
                        if disappear_text in line:
                            parsed_dt = self._parse_logcat_timestamp(line)
                            if parsed_dt and appear_line_ts_dt:
                                disappear_log_ts = parsed_dt.timestamp()
                                result['display_duration'] = (parsed_dt - appear_line_ts_dt).total_seconds()
                            else:
                                disappear_log_ts = time.time()
                                result['display_duration'] = disappear_log_ts - appear_log_ts
                            result['disappear_time'] = disappear_log_ts
                            logging.info(f"[response-monitor] logcat 检测到「{disappear_text}」，显示时长: {result['display_duration']:.3f}秒")
                            return result
                time.sleep(check_interval)

            result['status'] = 'timeout_disappear'
            result['error'] = f'在{max_wait_for_disappear}秒内未检测到 logcat「{disappear_text}」'
            if appear_log_ts:
                result['display_duration'] = time.time() - appear_log_ts
            logging.warning(f"[response-monitor] {result['error']}")

        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            logging.error(f"[response-monitor] 监控异常: {e}")
        finally:
            stop_logcat.set()

        return result

    def monitor_response(self, wait_after_send=None, max_wait_for_appear=None, check_interval=None, max_wait_for_disappear=None, request_send_time=None):
        """
        监控响应（仅 logcat 模式）：等待 logcat 中出现「融合卡片已显示」，再等待「融合卡片已隐藏」。
        未传入的时间参数从 config.response_monitor 读取。
        
        Args:
            wait_after_send: 兼容旧版本参数，已废弃（发送后立即开始监控）
            max_wait_for_appear: 最多等待多少秒检测到出现（默认从配置或6秒）
            check_interval: 检测间隔（默认从配置或0.1秒，高频轮询）
            max_wait_for_disappear: 最多等待多少秒检测到消失（默认从配置或300秒）
            request_send_time: hint/text 发送时刻（datetime），用于过滤旧日志、精确计算响应时间
        
        Returns:
            dict: {
                'status': 'success'|'timeout_appear'|'timeout_disappear'|'error',
                'appear_time': float|None,
                'disappear_time': float|None,
                'response_time': float|None,
                'display_duration': float|None,
                'model_name': str|None,
                'error': str|None
            }
        """
        cfg_mwa, cfg_ci, cfg_mwd = self._response_monitor_params()
        # 固定等待已废弃，强制为 0（立即监控）
        wait_after_send = 0.0
        max_wait_for_appear = max_wait_for_appear if max_wait_for_appear is not None else cfg_mwa
        check_interval = check_interval if check_interval is not None else cfg_ci
        max_wait_for_disappear = max_wait_for_disappear if max_wait_for_disappear is not None else cfg_mwd
        return self._monitor_response_via_logcat(wait_after_send, max_wait_for_appear, check_interval, max_wait_for_disappear, request_send_time)
