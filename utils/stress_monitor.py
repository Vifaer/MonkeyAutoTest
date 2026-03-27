#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
压力测试共用监控逻辑
供 BroadcastStressTest、TTSStressTest 等复用：前台检测、CPU/内存采样、logcat 采集与崩溃/ANR 分析
"""

import os
import re
import json
import time
import logging
import subprocess
import threading
import collections
import queue
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from utils.timeout_command import run as run_cmd

# 内存中保留的性能采样条数上限，超出时保留最近一段，避免长时间压力测试 OOM
MAX_PERF_SAMPLES_IN_MEMORY = 20000
TRIM_PERF_SAMPLES_TO = 10000


class StressMonitor:
    """
    压力测试监控器，提供前台检测、性能采样、logcat 采集与崩溃/ANR 分析。
    职责分组：前台与进程、性能采样、logcat/app.log、设备异常目录与 bugreport、logcat 解析与响应监控。
    """

    def __init__(
        self,
        device: Any,
        package: Any,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.device = device
        self.package = package
        self.config = config or {}
        self._stop_monitor = threading.Event()
        self._stop_logcat = threading.Event()
        self._logcat_process = None
        # 应用 PID 过滤日志（app.log）相关
        self._stop_app_log = threading.Event()
        self._app_log_process = None
        self._app_log_processes: dict[int, subprocess.Popen] = {}
        self._app_log_reader_threads: list[threading.Thread] = []
        # 设备异常目录监控结果（用于测试结束时触发 bugreport）
        self._device_exception_found = threading.Event()
        self._bugreport_lock = threading.Lock()
        self._bugreport_path: Optional[str] = None
        # 设备时间与本机时间差（秒），用于将 logcat 时间戳对齐到本机时间轴，减少统计误差
        self._device_time_offset = None
        # ERROR 日志监控
        self._error_monitor_stop = threading.Event()
        # CPU 核数缓存（用于将单进程CPU占比归一化到整机核数）
        self._cpu_core_count = None

        # 应用私有目录增量日志拉取（准实时）
        self._stop_app_private_logs_incremental = threading.Event()
        self._app_private_logs_incremental_thread: Optional[threading.Thread] = None

    # -------------------- 前台与进程 --------------------
    def _get_package_name(self) -> str:
        return getattr(self.package, "name", None) or getattr(self.package, "package", None) or ""

    def is_app_in_foreground(self) -> bool:
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

    def ensure_app_in_foreground(self) -> None:
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

    # -------------------- 性能采样（CPU/内存、start_monitoring_thread）--------------------
    def _parse_top_output_for_cpu(
        self, top_output: str, pkg: str
    ) -> tuple[float, float]:
        """
        从一次 top -n 1 -d 1 输出中同时解析设备总 CPU 与目标进程 CPU。
        返回 (app_cpu_pct, device_cpu_total_pct)；解析不到时对应值为 0.0。
        减少 adb 调用次数：单次 top 即可得到两项指标（设备格式稳定时）。
        """
        app_cpu = 0.0
        device_cpu = 0.0
        if not top_output or not isinstance(top_output, str):
            return (app_cpu, device_cpu)
        lines = top_output.splitlines()
        for line in lines:
            # 首行常为 "User 12%, Kernel 5%, IOW 0%, IRQ 0%"
            m = re.search(r"User\s*(\d+)%", line, re.I)
            if m:
                user = int(m.group(1))
                kernel = 0
                mk = re.search(r"Kernel\s*(\d+)%", line, re.I)
                if mk:
                    kernel = int(mk.group(1))
                total = user + kernel
                if 0 <= total <= 100:
                    device_cpu = float(total)
                break
        if device_cpu == 0.0:
            for line in lines:
                if re.match(r"^\s*CPU\s*:", line) or "Total:" in line:
                    m = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
                    if m:
                        device_cpu = float(m.group(1))
                        break
        for line in lines:
            if pkg in line:
                parts = line.split()
                for token in parts:
                    if token.endswith("%"):
                        try:
                            v = float(token.rstrip("%"))
                            if 0 <= v <= 100:
                                app_cpu = v
                                break
                        except ValueError:
                            pass
                break
        return (app_cpu, device_cpu)

    def get_cpu_usage(self) -> float:
        """
        获取待测应用 CPU 使用率（%）。
        使用 top -n 1 -d 1 进行约 1 秒采样；若 top 未列出该进程则尝试 dumpsys cpuinfo。
        """
        pkg = self._get_package_name()
        if not pkg:
            return 0.0
        try:
            cmd = f"adb -s {self.device.sn} shell top -n 1 -d 1"
            result = run_cmd(cmd, timeout=5)
            if result and isinstance(result, str):
                app_cpu, _ = self._parse_top_output_for_cpu(result, pkg)
                if app_cpu > 0:
                    return app_cpu
            cmd2 = f"adb -s {self.device.sn} shell dumpsys cpuinfo"
            result2 = run_cmd(cmd2, timeout=5)
            if result2 and isinstance(result2, str):
                for line in result2.splitlines():
                    if pkg in line:
                        m = re.search(r"(\d+(?:\.\d+)?)\s*%", line)
                        if m:
                            try:
                                v = float(m.group(1))
                                if 0 <= v <= 100:
                                    return v
                            except ValueError:
                                pass
        except Exception:
            pass
        return 0.0

    def get_device_cpu_total(self) -> float:
        """
        获取设备总体 CPU 使用率（0–100%）。从 top 首行或 dumpsys cpuinfo 解析。
        """
        try:
            cmd = f"adb -s {self.device.sn} shell top -n 1 -d 1"
            result = run_cmd(cmd, timeout=5)
            if result and isinstance(result, str):
                _, device_cpu = self._parse_top_output_for_cpu(result, "")
                if device_cpu > 0:
                    return device_cpu
            cmd2 = f"adb -s {self.device.sn} shell dumpsys cpuinfo"
            result2 = run_cmd(cmd2, timeout=5)
            if result2 and isinstance(result2, str):
                m = re.search(r"Total:\s*(\d+(?:\.\d+)?)\s*%", result2)
                if m:
                    return float(m.group(1))
        except Exception:
            pass
        return 0.0

    def get_cpu_core_count(self) -> int:
        """
        获取设备 CPU 核心数。优先解析 /proc/cpuinfo 中 processor 行数，失败时回退为 1。
        结果会缓存到实例属性，避免每次采样都触发 adb。
        """
        if isinstance(getattr(self, "_cpu_core_count", None), int) and self._cpu_core_count > 0:
            return self._cpu_core_count
        cores = 0
        try:
            out = run_cmd(f"adb -s {self.device.sn} shell cat /proc/cpuinfo", timeout=5)
            if isinstance(out, str):
                for line in out.splitlines():
                    if line.lower().startswith("processor"):
                        cores += 1
        except Exception:
            cores = 0
        if cores <= 0:
            try:
                out2 = run_cmd(f"adb -s {self.device.sn} shell nproc", timeout=3)
                if isinstance(out2, str):
                    last = out2.strip().splitlines()[-1].strip()
                    v = int(last)
                    if v > 0:
                        cores = v
            except Exception:
                cores = 0
        if cores <= 0:
            cores = 1
        self._cpu_core_count = cores
        return cores

    def get_device_memory_total_mb(self) -> float:
        """
        获取设备总体已用内存（MB）。用于与应用 PSS 区分，表示整机已用 RAM。
        优先使用 /proc/meminfo 的 MemTotal - MemFree（更稳定）；若失败则尝试 dumpsys meminfo。
        若 dumpsys 解析值过小（< 50 MB）则视为异常，回退到 /proc/meminfo。
        """
        # 1) /proc/meminfo 最可靠：MemTotal - MemFree = 已用内存 (kB)
        try:
            cmd2 = f"adb -s {self.device.sn} shell cat /proc/meminfo"
            result2 = run_cmd(cmd2, timeout=3)
            if result2 and isinstance(result2, str):
                total_m = re.search(r"MemTotal:\s*(\d+)\s*kB", result2)
                free_m = re.search(r"MemFree:\s*(\d+)\s*kB", result2)
                if total_m and free_m:
                    used_kb = int(total_m.group(1)) - int(free_m.group(1))
                    used_mb = round(used_kb / 1024.0, 2)
                    if used_mb >= 0:
                        return used_mb
        except Exception:
            pass
        # 2) dumpsys meminfo 作为补充
        try:
            cmd = f"adb -s {self.device.sn} shell dumpsys meminfo"
            result = run_cmd(cmd, timeout=8)
            if result and isinstance(result, str):
                m = re.search(r"Used\s+RAM:\s*(\d+)\s*kB", result, re.I)
                if m:
                    used_mb = round(int(m.group(1)) / 1024.0, 2)
                    if used_mb >= 50:  # 合理性：设备已用内存通常数百 MB 以上
                        return used_mb
                m = re.search(r"Total\s+PSS\s+by\s+process:\s*(\d+)", result, re.I)
                if m:
                    used_mb = round(int(m.group(1)) / 1024.0, 2)
                    if used_mb >= 50:
                        return used_mb
        except Exception:
            pass
        # 3) 若 /proc 未取到，再试 dumpsys 不校验（兼容异常设备）
        try:
            cmd = f"adb -s {self.device.sn} shell dumpsys meminfo"
            result = run_cmd(cmd, timeout=8)
            if result and isinstance(result, str):
                m = re.search(r"Used\s+RAM:\s*(\d+)\s*kB", result, re.I)
                if m:
                    return round(int(m.group(1)) / 1024.0, 2)
                m = re.search(r"Total\s+PSS\s+by\s+process:\s*(\d+)", result, re.I)
                if m:
                    return round(int(m.group(1)) / 1024.0, 2)
        except Exception:
            pass
        return 0.0

    def get_memory_usage(self) -> int:
        """获取内存使用量 PSS（KB）。失败或超时返回 0，不抛异常。"""
        try:
            pkg = self._get_package_name()
            if not pkg:
                return 0
            cmd = f"adb -s {self.device.sn} shell dumpsys meminfo {pkg}"
            result = run_cmd(cmd, timeout=5)
            if result and isinstance(result, str):
                for line in result.splitlines():
                    if "TOTAL PSS:" in line:
                        after = line.split("TOTAL PSS:")[1].strip()
                        num_str = after.split()[0].replace(',', '')
                        return int(num_str)
        except Exception as e:
            logging.debug("get_memory_usage failed: %s", e)
        return 0

    def _sample_performance_once(self) -> Dict[str, Any]:
        """
        执行一次性能采样，返回单条性能数据字典。
        单次 top 输出同时解析应用 CPU 与设备总 CPU，减少 adb 调用。
        任一步骤失败时返回带默认值的字典，不抛异常，避免监控线程阻塞测试。
        """
        pkg = self._get_package_name() or ""
        now_ts = datetime.now().isoformat()
        safe_default = {
            "timestamp": now_ts,
            "app_cpu_pct": 0.0,
            "app_memory_pss_kb": 0,
            "app_memory_pss_mb": 0.0,
            "app_foreground_mode": "background",
            "device_cpu_pct": 0.0,
            "device_memory_used_mb": 0.0,
            "device_sn": getattr(self.device, "sn", ""),
            "package": pkg,
        }
        try:
            is_fg = self.is_app_in_foreground()
            mode = "foreground" if is_fg else "background"
            app_cpu_raw = 0.0
            device_cpu_pct = 0.0
            try:
                cmd = f"adb -s {self.device.sn} shell top -n 1 -d 1"
                top_out = run_cmd(cmd, timeout=5)
                if top_out and isinstance(top_out, str):
                    app_cpu_raw, device_cpu_pct = self._parse_top_output_for_cpu(top_out, pkg)
            except Exception:
                pass
            if app_cpu_raw == 0.0 and pkg:
                app_cpu_raw = self.get_cpu_usage()
            if device_cpu_pct == 0.0:
                device_cpu_pct = self.get_device_cpu_total()
            cores = self.get_cpu_core_count()
            app_cpu_pct = round(app_cpu_raw / float(cores), 2) if cores > 0 else app_cpu_raw
            mem_usage = self.get_memory_usage()
            memory_mb = round(mem_usage / 1024.0, 2) if mem_usage > 0 else 0.0
            try:
                device_memory_used_mb = self.get_device_memory_total_mb()
            except Exception:
                device_memory_used_mb = 0.0
            return {
                "timestamp": now_ts,
                "app_cpu_pct": app_cpu_pct,
                "app_memory_pss_kb": mem_usage,
                "app_memory_pss_mb": memory_mb,
                "app_foreground_mode": mode,
                "device_cpu_pct": device_cpu_pct,
                "device_memory_used_mb": device_memory_used_mb,
                "device_sn": self.device.sn,
                "package": pkg,
            }
        except Exception as e:
            logging.warning("性能采样单次失败，使用默认值: %s", e)
            return safe_default

    def start_monitoring_thread(
        self,
        result: Dict[str, Any],
        interval_seconds: float,
        perf_log_path: str,
    ) -> threading.Thread:
        """启动后台监控线程：每 interval_seconds 采样 CPU/内存并写入 JSONL"""
        def monitor() -> None:
            log_dir = os.path.dirname(perf_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            log_file = open(perf_log_path, "a", encoding="utf-8", errors="replace")
            try:
                while True:
                    try:
                        if self._stop_monitor.is_set():
                            break
                        perf_data = self._sample_performance_once()
                        result["performance_data"].append(perf_data)
                        # 长时间运行限制内存中列表长度，报告可从 JSONL 读取完整数据
                        if len(result["performance_data"]) > MAX_PERF_SAMPLES_IN_MEMORY:
                            result["performance_data"] = result["performance_data"][-TRIM_PERF_SAMPLES_TO:]
                        log_file.write(json.dumps(perf_data, ensure_ascii=False) + "\n")
                        log_file.flush()
                        try:
                            os.fsync(log_file.fileno())
                        except Exception:
                            pass
                        time.sleep(interval_seconds)
                    except Exception as e:
                        logging.warning("性能监控出错: %s", str(e))
                        time.sleep(interval_seconds)
            finally:
                try:
                    log_file.flush()
                    log_file.close()
                except Exception:
                    pass
        t = threading.Thread(target=monitor, daemon=True)
        t.start()
        return t

    # -------------------- logcat 全量抓取与 app.log（PID 过滤）--------------------
    def start_logcat_capture(self, logcat_log_path, *, clear_before: bool = False):
        """
        启动 logcat 抓取线程（全量）。
        默认与 `adb logcat` 默认输出保持一致（不清空缓冲区、不过滤 tag）。
        """
        self.logcat_log_path = logcat_log_path

        def capture_logcat():
            log_dir = os.path.dirname(logcat_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            if clear_before:
                # 可选：清空 logcat 缓冲区（用于减少噪音），但会改变输出内容与 `adb logcat` 的一致性
                run_cmd(f"adb -s {self.device.sn} logcat -c", timeout=5)
            try:
                from utils.timeout_command import _resolve_adb_path
                adb_path = _resolve_adb_path()
                adb_bin = adb_path or "adb"
                # 不指定 -v：尽量与用户手动运行 `adb logcat` 默认输出一致
                logcat_cmd = [adb_bin, "-s", self.device.sn, "logcat"]
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
                        # readline 阻塞等待下一行；这里不额外 sleep，避免积压导致丢行
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
        self._stop_app_log.set()
        self._error_monitor_stop.set()
        self._stop_app_private_logs_incremental.set()
        if self._logcat_process and self._logcat_process.poll() is None:
            try:
                self._logcat_process.terminate()
                self._logcat_process.wait(timeout=2)
            except Exception:
                pass
        self._logcat_process = None
        if self._app_log_process and self._app_log_process.poll() is None:
            try:
                self._app_log_process.terminate()
                self._app_log_process.wait(timeout=2)
            except Exception:
                pass
        self._app_log_process = None
        # 多进程 app.log 子进程回收
        try:
            for proc in list(self._app_log_processes.values()):
                try:
                    if proc and proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=2)
                except Exception:
                    pass
        except Exception:
            pass
        self._app_log_processes = {}
        self._app_log_reader_threads = []

        # 停止增量拉取线程
        try:
            if self._app_private_logs_incremental_thread and self._app_private_logs_incremental_thread.is_alive():
                self._app_private_logs_incremental_thread.join(timeout=5)
        except Exception:
            pass
        self._app_private_logs_incremental_thread = None

    # -------------------- 设备异常目录（/data/anr, /data/tombstones）监控 --------------------

    def clear_device_exception_dirs(self) -> None:
        """
        测试前清空设备异常目录，排除历史干扰日志：
        - /data/anr
        - /data/tombstones

        委托给 infra.device_cleanup 统一实现。
        注意：部分设备需要 root 才能访问/清理；失败仅记录 warning，不中断测试。
        """
        from infra.device_cleanup import clear_device_exception_dirs

        sn = getattr(self.device, "sn", "") or ""
        clear_device_exception_dirs(sn)

    def start_exception_file_monitor(self, run_log_dir: str, interval_seconds: float = 10.0) -> threading.Thread:
        """
        测试期间监控设备异常目录 /data/anr 与 /data/tombstones：
        - 增量发现新文件
        - 判断内容是否属于待测应用（通过包名匹配）
        - 将原始文件内容转储到本地 logs/<sn>/<ts>/anr|tombstones
        - 将元数据写入 device_exceptions.log，并在 app.log 末尾追加概要行

        优先使用 adb pull 进行转储（更高效），pull 失败时保留 cat 兜底。
        """
        pkg = self._get_package_name().strip()
        if not pkg or not run_log_dir:
            t = threading.Thread(target=lambda: None, daemon=True)
            t.start()
            return t

        try:
            os.makedirs(run_log_dir, exist_ok=True)
        except Exception:
            pass

        processed_anr = set()
        processed_tomb = set()

        def _list_remote(remote_dir: str) -> list:
            try:
                out = run_cmd(f"adb -s {self.device.sn} shell ls {remote_dir}", timeout=6)
                if not isinstance(out, str):
                    return []
                names = []
                for line in out.splitlines():
                    s = line.strip()
                    if not s or s in (".", ".."):
                        continue
                    # ls 可能返回错误信息，简单过滤
                    if "No such file" in s or "Permission denied" in s:
                        continue
                    names.append(s)
                return names
            except Exception:
                return []

        def _pull_remote(remote_path: str, local_path: str) -> bool:
            """
            优先使用 adb pull 将设备文件转储到本地。
            注意：部分设备/目录需要 root 权限，pull 可能失败。
            """
            try:
                run_cmd(f'adb -s {self.device.sn} pull "{remote_path}" "{local_path}"', timeout=30)
                return os.path.isfile(local_path) and os.path.getsize(local_path) > 0
            except Exception:
                return False

        def _read_remote_cat(remote_path: str) -> str:
            """pull 失败时的兜底读取方式（adb shell cat）"""
            try:
                out = run_cmd(f"adb -s {self.device.sn} shell cat {remote_path}", timeout=20)
                return out if isinstance(out, str) else ""
            except Exception:
                return ""

        def _read_local(local_path: str) -> str:
            try:
                with open(local_path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception:
                return ""

        def _is_match(content: str) -> bool:
            if not content:
                return False
            if f"Cmd line: {pkg}" in content:
                return True
            if f">>> {pkg} <<<" in content:
                return True
            return False

        def _write_index(exc_type: str, src_path: str, local_path: str) -> None:
            now = datetime.now().isoformat()
            idx_path = os.path.join(run_log_dir, "device_exceptions.log")
            line = f"[{now}] type={exc_type} pkg={pkg} src={src_path} local={local_path}\n"
            try:
                with open(idx_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(line)
            except Exception:
                pass
            # 同步概要到 app.log，供报告实时展示
            try:
                app_path = os.path.join(run_log_dir, "app.log")
                with open(app_path, "a", encoding="utf-8", errors="replace") as f:
                    f.write(f"# [device-exception] {line}")
            except Exception:
                pass
            # 标记：本次运行中已发现设备侧异常文件
            try:
                self._device_exception_found.set()
            except Exception:
                pass

        def _worker() -> None:
            while not self._stop_monitor.is_set():
                try:
                    for remote_dir, local_subdir, processed, exc_type in (
                        ("/data/anr", "anr", processed_anr, "ANR"),
                        ("/data/tombstones", "tombstones", processed_tomb, "Crash"),
                    ):
                        names = _list_remote(remote_dir)
                        if not names:
                            continue
                        for name in names:
                            if name in processed:
                                continue
                            processed.add(name)
                            src_path = f"{remote_dir}/{name}"
                            local_dir = os.path.join(run_log_dir, local_subdir)
                            try:
                                os.makedirs(local_dir, exist_ok=True)
                            except Exception:
                                pass
                            local_path = os.path.join(local_dir, name)
                            pulled = _pull_remote(src_path, local_path)
                            if pulled:
                                content = _read_local(local_path)
                                if not _is_match(content):
                                    # 非目标应用相关：删除本地文件，避免污染
                                    try:
                                        os.remove(local_path)
                                    except Exception:
                                        pass
                                    continue
                                # 为本地文件补齐源路径头（pull 得到的原始文件不包含）
                                try:
                                    if not content.startswith("# src:"):
                                        with open(local_path, "w", encoding="utf-8", errors="replace") as f:
                                            f.write(f"# src: {src_path}\n")
                                            f.write(content)
                                except Exception:
                                    pass
                                _write_index(exc_type, src_path, local_path)
                                continue

                            # pull 失败：兜底 cat（仅当匹配才落盘）
                            content = _read_remote_cat(src_path)
                            if not _is_match(content):
                                continue
                            try:
                                with open(local_path, "w", encoding="utf-8", errors="replace") as f:
                                    f.write(f"# src: {src_path}\n")
                                    f.write(content)
                            except Exception as e:
                                logging.warning("[device-exc] 写入本地异常文件失败 %s: %s", local_path, e)
                                continue
                            _write_index(exc_type, src_path, local_path)
                except Exception as e:
                    logging.debug("[device-exc] 监控线程异常（忽略继续）: %s", e)
                # 轮询间隔
                try:
                    time.sleep(max(1.0, float(interval_seconds)))
                except Exception:
                    time.sleep(10.0)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

    @staticmethod
    def collect_bugreport_if_needed(
        device_sn: str,
        package_name: str,
        run_log_dir: str,
        timeout_seconds: int = 900,
        reason: str = "",
    ) -> Optional[str]:
        """
        若设备侧存在与目标应用相关的 ANR/tombstone（通过内容包名匹配），则导出 bugreport 到本地：
          logs/<sn>/<ts>/bugreport/bugreport_<sn>_<YYYYMMDD_HHMMSS>.zip

        - 该函数可在“测试完成”或“外部手动停止（子进程被杀）后”由 GUI 进程调用
        - 失败仅返回 None，不抛异常（避免影响主流程）
        """
        sn = (device_sn or "").strip()
        pkg = (package_name or "").strip()
        trigger_reason = (reason or "测试结束").strip() or "测试结束"

        logging.info("[bugreport] ---------- 开始检查是否需导出 bugreport ----------")
        logging.info("[bugreport] 触发原因: %s | 设备: %s | 包名: %s | 日志目录: %s", trigger_reason, sn, pkg, run_log_dir)

        if not sn or not pkg or not run_log_dir:
            logging.warning("[bugreport] 参数不完整（设备/包名/日志目录为空），跳过导出")
            return None
        if not os.path.isdir(run_log_dir):
            try:
                os.makedirs(run_log_dir, exist_ok=True)
            except Exception as e:
                logging.warning("[bugreport] 无法创建日志目录 %s: %s", run_log_dir, e)
                return None

        # 若已存在 bugreport 文件，直接返回一个（避免重复采集）
        try:
            bd = os.path.join(run_log_dir, "bugreport")
            if os.path.isdir(bd):
                existing = [fn for fn in os.listdir(bd) if fn.lower().endswith(".zip")]
                if existing:
                    path = os.path.join(bd, sorted(existing)[-1])
                    logging.info("[bugreport] 已存在本次运行的 bugreport 文件，跳过重复导出: %s", path)
                    logging.info("[bugreport] ---------- 检查结束（使用已有文件）----------")
                    return path
        except Exception as e:
            logging.debug("[bugreport] 检查已存在 bugreport 时异常: %s", e)

        def _list_remote(remote_dir: str) -> list:
            try:
                out = run_cmd(f"adb -s {sn} shell ls {remote_dir}", timeout=6)
                if not isinstance(out, str):
                    return []
                names = []
                for line in out.splitlines():
                    s = line.strip()
                    if not s or s in (".", ".."):
                        continue
                    if "No such file" in s or "Permission denied" in s:
                        continue
                    names.append(s)
                return names
            except Exception:
                return []

        def _remote_file_matches(remote_path: str) -> bool:
            """
            轻量判断是否与目标应用相关：
            - ANR: Cmd line: <pkg>
            - tombstone: >>> <pkg> <<<
            说明：仅依赖设备侧可读权限；若权限不足，返回 False（不触发 bugreport）。
            """
            try:
                # 设备侧 grep（可能不存在/权限不足），失败时返回 False
                p1 = f'Cmd line: {pkg}'
                out1 = run_cmd(f'adb -s {sn} shell grep -m 1 -F "{p1}" "{remote_path}"', timeout=8)
                if isinstance(out1, str) and p1 in out1:
                    return True
                p2 = f">>> {pkg} <<<"
                out2 = run_cmd(f'adb -s {sn} shell grep -m 1 -F "{p2}" "{remote_path}"', timeout=8)
                if isinstance(out2, str) and p2 in out2:
                    return True
            except Exception:
                return False
            return False

        # 1) 终局检查：设备侧是否存在与 pkg 匹配的异常文件
        matched = []
        try:
            for remote_dir in ("/data/anr", "/data/tombstones"):
                for name in _list_remote(remote_dir):
                    rp = f"{remote_dir}/{name}"
                    if _remote_file_matches(rp):
                        matched.append(rp)
        except Exception as e:
            logging.warning("[bugreport] 扫描设备异常目录时出错: %s", e)
            matched = []

        if not matched:
            logging.info("[bugreport] 未发现与目标包名 [%s] 相关的 ANR/tombstone 文件，无需导出 bugreport", pkg)
            logging.info("[bugreport] ---------- 检查结束（无需导出）----------")
            return None

        logging.info("[bugreport] 发现与目标包名 [%s] 相关的异常文件，共 %d 个:", pkg, len(matched))
        for rp in matched[:20]:
            logging.info("[bugreport]   - %s", rp)
        if len(matched) > 20:
            logging.info("[bugreport]   - ... 及其他 %d 个", len(matched) - 20)

        # 2) 导出 bugreport
        try:
            bug_dir = os.path.join(run_log_dir, "bugreport")
            os.makedirs(bug_dir, exist_ok=True)
        except Exception as e:
            logging.warning("[bugreport] 创建 bugreport 目录失败: %s", e)
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_zip = os.path.join(bug_dir, f"bugreport_{sn}_{ts}.zip")
        logging.info("[bugreport] 开始导出 bugreport（目标: %s），过程可能需数分钟，请稍候...", out_zip)

        export_ok = False
        export_error = ""
        try:
            out = run_cmd(f'adb -s {sn} bugreport "{out_zip}"', timeout=int(timeout_seconds))
            if out is None:
                export_error = "命令超时（未在限定时间内完成）"
            elif isinstance(out, str) and (
                "error" in out.lower() or "permission denied" in out.lower() or "not found" in out.lower()
            ):
                export_error = out.strip()[:300]
            elif os.path.isfile(out_zip) and os.path.getsize(out_zip) > 0:
                export_ok = True
            else:
                export_error = "未生成有效 zip 文件或文件为空"
        except Exception as e:
            export_error = str(e)

        if not export_ok:
            logging.warning("[bugreport] 导出失败: %s", export_error or "未知原因")
            logging.info("[bugreport] ---------- bugreport 导出流程结束（失败）----------")
            return None

        size_mb = os.path.getsize(out_zip) / (1024 * 1024)
        logging.info("[bugreport] 导出成功，文件: %s（大小: %.1f MB）", out_zip, size_mb)

        # 3) 写入索引与 app.log，供报告标记与定位
        try:
            idx_path = os.path.join(run_log_dir, "device_exceptions.log")
            with open(idx_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(
                    f"[{datetime.now().isoformat()}] type=BUGREPORT pkg={pkg} local={out_zip} reason={reason} matched={len(matched)}\n"
                )
        except Exception:
            pass
        try:
            app_path = os.path.join(run_log_dir, "app.log")
            with open(app_path, "a", encoding="utf-8", errors="replace") as f:
                f.write(
                    f"# [bugreport] local={out_zip} reason={reason} matched={len(matched)}\n"
                )
                for rp in matched[:20]:
                    f.write(f"# [bugreport] matched_src={rp}\n")
        except Exception:
            pass
        try:
            with open(os.path.join(bug_dir, "bugreport_path.txt"), "w", encoding="utf-8", errors="replace") as f:
                f.write(out_zip)
                f.write("\n")
        except Exception:
            pass

        logging.info("[bugreport] ---------- bugreport 检查与导出流程结束 ----------")
        return out_zip

    def maybe_collect_bugreport(self, run_log_dir: str, reason: str = "") -> Optional[str]:
        """
        实例方法封装：在测试结束时调用。
        - 若监控期间已发现异常文件（或终局扫描发现），则导出 bugreport
        """
        pkg = self._get_package_name().strip()
        sn = getattr(getattr(self, "device", None), "sn", "") or ""
        trigger_reason = (reason or "测试结束").strip() or "测试结束"

        logging.info("[bugreport] 测试结束/停止时尝试导出 bugreport（原因: %s）", trigger_reason)

        try:
            with self._bugreport_lock:
                if self._bugreport_path and os.path.isfile(self._bugreport_path):
                    logging.info("[bugreport] 使用已导出的 bugreport，跳过重复导出: %s", self._bugreport_path)
                    return self._bugreport_path
                out = self.collect_bugreport_if_needed(sn, pkg, run_log_dir, reason=trigger_reason)
                if out:
                    self._bugreport_path = out
                    logging.info("[bugreport] 本次导出结果: 成功，路径: %s", out)
                else:
                    logging.info("[bugreport] 本次导出结果: 未触发或未发现相关异常文件，未生成新 bugreport")
                return out
        except Exception as e:
            logging.warning("[bugreport] 导出过程发生异常: %s", e)
            return None

    def maybe_collect_app_private_logs(self, run_log_dir: str, reason: str = "") -> None:
        """
        测试结束后拉取应用私有目录日志（例如 NaviLogs）。

        - 规则来源：`conf/app_log_pull_rules.json`
        - 依据 package_name 选择远端目录
        - 失败仅记录 warning，不影响主流程
        """
        try:
            pkg = self._get_package_name().strip()
            sn = getattr(getattr(self, "device", None), "sn", "") or ""
            if not pkg or not sn or not run_log_dir:
                return

            enabled = True
            try:
                enabled = bool(self.config.get("app_log_pull_enabled", True))
            except Exception:
                enabled = True
            if not enabled:
                return

            from infra.app_log_pull import pull_app_private_logs

            pull_app_private_logs(
                device_sn=sn,
                package_name=pkg,
                run_log_dir=run_log_dir,
                config=self.config,
                reason=reason or "test_end",
            )
        except Exception as e:
            logging.warning("[app-log-pull] 收集应用私有日志失败: %s", e)

    def start_app_private_logs_incremental_monitor(self, run_log_dir: str, reason: str = "") -> None:
        """
        启动应用私有目录增量日志拉取（准实时）。

        读取 `conf/app_log_pull_rules.json` 的 `incremental` 配置与 package 对应规则。
        拉取失败不影响主流程；退出由 StressMonitor.stop() 控制。
        """
        try:
            pkg = self._get_package_name().strip()
            sn = getattr(getattr(self, "device", None), "sn", "") or ""
            if not pkg or not sn or not run_log_dir:
                return

            # 用户/GUI 侧可用开关（没有则默认开启：由规则文件决定）
            try:
                if "app_log_pull_enabled" in self.config:
                    if not bool(self.config.get("app_log_pull_enabled", True)):
                        return
            except Exception:
                pass

            # 清理旧线程
            self._stop_app_private_logs_incremental.clear()

            from infra.app_log_pull import run_app_private_logs_incremental_pulling

            def _runner() -> None:
                run_app_private_logs_incremental_pulling(
                    stop_event=self._stop_app_private_logs_incremental,
                    device_sn=sn,
                    package_name=pkg,
                    run_log_dir=run_log_dir,
                    config=self.config,
                    reason=reason or "test_running",
                )

            self._app_private_logs_incremental_thread = threading.Thread(target=_runner, daemon=True)
            self._app_private_logs_incremental_thread.start()
        except Exception as e:
            logging.warning("[app-log-pull] 启动增量拉取失败: %s", e)

    # -------------------- 应用 PID 基础工具 --------------------

    @staticmethod
    def _split_csv(raw: Any) -> list[str]:
        if raw is None:
            return []
        txt = str(raw).replace("\n", ",").replace(";", ",")
        out = []
        seen = set()
        for it in txt.split(","):
            s = it.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    @staticmethod
    def _parse_package_process_map(raw: Any) -> dict[str, list[str]]:
        """
        支持格式：
        - com.demo.app:main,remote;com.demo.other:worker
        - 每行一条：pkg:proc1,proc2
        """
        result: dict[str, list[str]] = {}
        if raw is None:
            return result
        text = str(raw).strip()
        if not text:
            return result
        for chunk in text.replace("\r", "").replace("\n", ";").split(";"):
            item = chunk.strip()
            if not item or ":" not in item:
                continue
            pkg, procs = item.split(":", 1)
            pkg = pkg.strip()
            if not pkg:
                continue
            plist = StressMonitor._split_csv(procs)
            if plist:
                result[pkg] = plist
        return result

    def _build_app_log_cfg(self) -> dict:
        cfg_raw = self.config.get("app_log")
        cfg = cfg_raw if isinstance(cfg_raw, dict) else {}
        norm = {
            "enabled": bool(cfg.get("enabled", True)),
            "extra_packages_csv": cfg.get("extra_packages_csv", ""),
            "package_process_map": cfg.get("package_process_map", ""),
            "include_process_names_csv": cfg.get("include_process_names_csv", ""),
            "levels": str(cfg.get("levels", "VDIWEF") or "VDIWEF").upper(),
            "tags_include_csv": cfg.get("tags_include_csv", ""),
            "tags_exclude_csv": cfg.get("tags_exclude_csv", ""),
            "keywords_include_csv": cfg.get("keywords_include_csv", ""),
            "keywords_exclude_csv": cfg.get("keywords_exclude_csv", ""),
            "output_subdir": str(cfg.get("output_subdir", "") or "").strip(),
        }
        try:
            norm["max_file_mb"] = max(1.0, float(cfg.get("max_file_mb", 50.0)))
        except Exception:
            norm["max_file_mb"] = 50.0
        try:
            norm["backup_count"] = max(1, int(float(cfg.get("backup_count", 3))))
        except Exception:
            norm["backup_count"] = 3
        try:
            norm["flush_interval_ms"] = max(50, int(float(cfg.get("flush_interval_ms", 500))))
        except Exception:
            norm["flush_interval_ms"] = 500
        try:
            norm["batch_lines"] = max(1, int(float(cfg.get("batch_lines", 50))))
        except Exception:
            norm["batch_lines"] = 50
        try:
            norm["pid_refresh_seconds"] = max(0.5, float(cfg.get("pid_refresh_seconds", 2.0)))
        except Exception:
            norm["pid_refresh_seconds"] = 2.0
        return norm

    def _list_device_processes(self) -> list[tuple[int, str]]:
        """
        返回设备进程列表：[(pid, process_name), ...]
        """
        rows: list[tuple[int, str]] = []
        try:
            out = run_cmd(f"adb -s {self.device.sn} shell ps -A", timeout=6)
            if not isinstance(out, str):
                return rows
            for line in out.splitlines():
                line = line.strip()
                if not line or " PID " in f" {line} ":
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                name = parts[-1].strip()
                if not name:
                    continue
                pid = None
                for p in parts:
                    if p.isdigit():
                        pid = int(p)
                        break
                if pid is None or pid <= 0:
                    continue
                rows.append((pid, name))
        except Exception:
            return rows
        return rows

    def _resolve_target_processes_for_app_log(self, cfg: dict) -> dict[int, str]:
        pkg = self._get_package_name().strip()
        packages = set([pkg] if pkg else [])
        packages.update(self._split_csv(cfg.get("extra_packages_csv")))
        process_map = self._parse_package_process_map(cfg.get("package_process_map"))
        include_names = set(self._split_csv(cfg.get("include_process_names_csv")))
        # 追加映射中针对已选择包名的进程名
        for p in list(packages):
            for proc in process_map.get(p, []):
                include_names.add(proc)
                if ":" not in proc:
                    include_names.add(f"{p}:{proc}")

        result: dict[int, str] = {}
        for pid, name in self._list_device_processes():
            matched = False
            for p in packages:
                if name == p or name.startswith(f"{p}:"):
                    matched = True
                    break
            if not matched and name in include_names:
                matched = True
            if matched:
                result[pid] = name
        return result

    @staticmethod
    def _parse_threadtime_line(line: str) -> tuple[Optional[int], str, str, str]:
        """
        解析 threadtime 行，返回 (pid, level, tag, content_lower)
        """
        # MM-DD HH:MM:SS.mmm  PID  TID L TAG: msg
        m = re.match(
            r"^\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+\s+(\d+)\s+\d+\s+([VDIWEF])\s+([^:]+):\s?(.*)$",
            line,
        )
        if not m:
            return None, "", "", line.lower()
        try:
            pid = int(m.group(1))
        except Exception:
            pid = None
        level = (m.group(2) or "").upper()
        tag = (m.group(3) or "").strip()
        content = f"{tag}: {m.group(4) or ''}".lower()
        return pid, level, tag, content

    def _match_app_log_filters(self, line: str, cfg: dict) -> bool:
        _, level, tag, content_lower = self._parse_threadtime_line(line)
        levels = set(ch for ch in str(cfg.get("levels", "VDIWEF")).upper() if ch.isalpha())
        if level and levels and level not in levels:
            return False
        tag_l = tag.lower()
        tags_include = [x.lower() for x in self._split_csv(cfg.get("tags_include_csv"))]
        tags_exclude = [x.lower() for x in self._split_csv(cfg.get("tags_exclude_csv"))]
        if tags_include and (not tag_l or tag_l not in tags_include):
            return False
        if tag_l and tags_exclude and tag_l in tags_exclude:
            return False
        kw_inc = [x.lower() for x in self._split_csv(cfg.get("keywords_include_csv"))]
        kw_exc = [x.lower() for x in self._split_csv(cfg.get("keywords_exclude_csv"))]
        if kw_inc and not any(k in content_lower for k in kw_inc):
            return False
        if kw_exc and any(k in content_lower for k in kw_exc):
            return False
        return True

    @staticmethod
    def _rotate_app_log_file(log_path: str, backup_count: int) -> None:
        if backup_count < 1:
            return
        try:
            for i in range(backup_count, 1, -1):
                src = f"{log_path}.{i - 1}"
                dst = f"{log_path}.{i}"
                if os.path.exists(src):
                    os.replace(src, dst)
            if os.path.exists(log_path):
                os.replace(log_path, f"{log_path}.1")
        except Exception:
            pass

    def _get_app_pid(self) -> Optional[int]:
        """
        通过包名获取当前应用 PID。

        优先使用 pidof，失败时回退到 ps 解析。
        """
        pkg = self._get_package_name().strip()
        if not pkg:
            return None
        try:
            # 尝试 pidof
            cmd = f"adb -s {self.device.sn} shell pidof {pkg}"
            out = run_cmd(cmd, timeout=3)
            if isinstance(out, str):
                parts = out.strip().split()
                if parts:
                    try:
                        return int(parts[0])
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            # 回退到 ps 解析
            cmd = f"adb -s {self.device.sn} shell ps -A | grep {pkg}"
            out = run_cmd(cmd, timeout=5)
            if isinstance(out, str):
                for line in out.splitlines():
                    line = line.strip()
                    if not line or pkg not in line:
                        continue
                    parts = line.split()
                    # 通用 ps：USER PID ... NAME
                    for token in parts:
                        if token.isdigit():
                            try:
                                return int(token)
                            except Exception:
                                continue
        except Exception:
            pass
        return None

    def start_app_log_capture(self, app_log_path: str) -> threading.Thread:
        """
        启动基于 PID 的应用日志抓取线程：adb logcat --pid <pid> -v threadtime -> app.log。

        - 每 2 秒检查一次 PID，应用重启时自动切换到新 PID。
        - 日志以 UTF-8 写入，确保中文显示正常。
        """
        cfg = self._build_app_log_cfg()
        pkg = self._get_package_name().strip()
        if not pkg and not self._split_csv(cfg.get("extra_packages_csv")):
            logging.warning("[app-log] 未指定包名且未配置额外包名，跳过应用日志采集")
            t = threading.Thread(target=lambda: None, daemon=True)
            t.start()
            return t

        if not cfg.get("enabled", True):
            logging.info("[app-log] 已禁用精准采集，跳过 app.log")
            t = threading.Thread(target=lambda: None, daemon=True)
            t.start()
            return t

        # 输出路径支持子目录覆盖
        out_path = app_log_path
        subdir = (cfg.get("output_subdir") or "").strip()
        if subdir:
            base_dir = os.path.dirname(app_log_path)
            out_path = os.path.join(base_dir, subdir, os.path.basename(app_log_path))

        self._stop_app_log.clear()

        def _worker() -> None:
            line_q: queue.Queue = queue.Queue(maxsize=5000)
            self._app_log_processes = {}
            self._app_log_reader_threads = []

            def _spawn_pid_reader(pid: int, proc_name: str) -> None:
                try:
                    from utils.timeout_command import _resolve_adb_path
                    adb_path = _resolve_adb_path() or "adb"
                except Exception:
                    adb_path = "adb"
                cmd = [adb_path, "-s", self.device.sn, "logcat", "--pid", str(pid), "-v", "threadtime"]
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self._app_log_processes[pid] = proc
                if self._app_log_process is None:
                    self._app_log_process = proc
                logging.info("[app-log] 启动应用日志采集: pid=%s process=%s", pid, proc_name)

                def _reader():
                    try:
                        if not proc.stdout:
                            return
                        while not (self._stop_monitor.is_set() or self._stop_app_log.is_set()):
                            if proc.poll() is not None:
                                break
                            line = proc.stdout.readline()
                            if not line:
                                time.sleep(0.02)
                                continue
                            try:
                                line_q.put_nowait((pid, line))
                            except queue.Full:
                                # 满队列时丢弃最旧数据，优先保证实时性
                                try:
                                    _ = line_q.get_nowait()
                                except Exception:
                                    pass
                                try:
                                    line_q.put_nowait((pid, line))
                                except Exception:
                                    pass
                    except Exception:
                        pass

                rt = threading.Thread(target=_reader, daemon=True)
                rt.start()
                self._app_log_reader_threads.append(rt)

            # 确保目录存在
            log_dir = os.path.dirname(out_path)
            if log_dir and not os.path.exists(log_dir):
                try:
                    os.makedirs(log_dir, exist_ok=True)
                except Exception:
                    pass

            max_bytes = int(float(cfg.get("max_file_mb", 50.0)) * 1024 * 1024)
            backup_count = int(cfg.get("backup_count", 3))
            flush_interval_s = max(0.05, float(cfg.get("flush_interval_ms", 500)) / 1000.0)
            batch_lines = int(cfg.get("batch_lines", 50))
            pid_refresh_s = float(cfg.get("pid_refresh_seconds", 2.0))
            last_flush = time.time()
            last_refresh = 0.0
            pending = 0

            f = open(out_path, "a", encoding="utf-8", errors="replace")
            try:
                f.write(f"# [app-log] start at {datetime.now().isoformat()}\n")
                f.flush()
                while not (self._stop_monitor.is_set() or self._stop_app_log.is_set()):
                    now = time.time()
                    # 动态刷新目标进程集合
                    if now - last_refresh >= pid_refresh_s:
                        last_refresh = now
                        targets = self._resolve_target_processes_for_app_log(cfg)
                        target_pids = set(targets.keys())
                        active_pids = set(self._app_log_processes.keys())
                        # 停掉不再需要的 pid
                        for pid in list(active_pids - target_pids):
                            proc = self._app_log_processes.pop(pid, None)
                            if proc and proc.poll() is None:
                                try:
                                    proc.terminate()
                                    proc.wait(timeout=1)
                                except Exception:
                                    pass
                        # 拉起新增 pid
                        for pid in list(target_pids - active_pids):
                            _spawn_pid_reader(pid, targets.get(pid, ""))

                    # 消费队列
                    consumed = 0
                    while consumed < batch_lines:
                        try:
                            _, line = line_q.get_nowait()
                        except queue.Empty:
                            break
                        consumed += 1
                        if not self._match_app_log_filters(line, cfg):
                            continue
                        # 轮转
                        try:
                            if os.path.exists(out_path) and os.path.getsize(out_path) >= max_bytes:
                                f.flush()
                                self._rotate_app_log_file(out_path, backup_count)
                                f.close()
                                f = open(out_path, "a", encoding="utf-8", errors="replace")
                                f.write(f"# [app-log] rotate at {datetime.now().isoformat()}\n")
                        except Exception:
                            pass
                        f.write(line)
                        pending += 1

                    if pending > 0 and (time.time() - last_flush >= flush_interval_s or pending >= batch_lines):
                        try:
                            f.flush()
                        except Exception:
                            pass
                        last_flush = time.time()
                        pending = 0

                    if consumed == 0:
                        time.sleep(0.05)

                # 优雅收尾
                try:
                    f.flush()
                except Exception:
                    pass
            finally:
                try:
                    f.close()
                except Exception:
                    pass

            for proc in list(self._app_log_processes.values()):
                try:
                    if proc.poll() is None:
                        proc.terminate()
                        proc.wait(timeout=1)
                except Exception:
                    pass
            self._app_log_processes = {}
            self._app_log_process = None

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t

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
                    try:
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
                        logging.warning("[error-monitor] 检测到 ERROR 日志，尝试自动拉起应用: %s", stripped[:200])
                        try:
                            self.ensure_app_in_foreground()
                        except Exception as e:
                            logging.warning("[error-monitor] 自动拉起应用失败: %s", e)
                    except Exception as e:
                        logging.debug("[error-monitor] readline 异常: %s", e)
                        break
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception:
                            pass
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

        def _dt_to_logcat_time_key(dt: datetime) -> str:
            # 目标格式：MM-DD HH:MM:SS.mmm（字符串可直接字典序比较）
            ms = int(getattr(dt, "microsecond", 0) / 1000)
            return dt.strftime("%m-%d %H:%M:%S") + f".{ms:03d}"

        def _line_to_logcat_time_key(line: str) -> Optional[str]:
            """
            从 logcat 行提取时间戳（MM-DD HH:MM:SS.mmm）。
            兼容 brief/threadtime 常见的前两段 token：
              1) MM-DD
              2) HH:MM:SS(.mmm)?
            """
            if not line:
                return None
            parts = line.strip().split()
            if len(parts) < 2:
                return None
            mmdd = parts[0]
            t2 = parts[1]
            import re as _re
            m = _re.match(r"^(\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,3}))?$", t2)
            if not m:
                return None
            hms = m.group(1)
            ms = m.group(2) or "0"
            ms = (ms + "000")[:3]  # 保底补齐到 3 位
            return f"{mmdd} {hms}.{ms}"

        start_key = _dt_to_logcat_time_key(start_time)
        end_key = _dt_to_logcat_time_key(end_time)
        try:
            with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    time_key = _line_to_logcat_time_key(line)
                    if not time_key:
                        continue
                    if time_key < start_key:
                        continue
                    if time_key > end_key:
                        break

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
            # logcat 时间戳通常包含毫秒：MM-DD HH:MM:SS.mmm
            # 为保证区间判断正确，使用同一格式的“时间键”做比较（字符串字典序即可）
            start_str_display = start_time.strftime("%m-%d %H:%M:%S")
            end_str_display = end_time.strftime("%m-%d %H:%M:%S")

            def _dt_to_logcat_time_key(dt: datetime) -> str:
                ms = int(getattr(dt, "microsecond", 0) / 1000)
                return dt.strftime("%m-%d %H:%M:%S") + f".{ms:03d}"

            def _line_to_logcat_time_key(line: str) -> Optional[str]:
                parts = line.strip().split()
                if len(parts) < 2:
                    return None
                mmdd = parts[0]
                t2 = parts[1]
                import re as _re
                m = _re.match(r"^(\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,3}))?$", t2)
                if not m:
                    return None
                hms = m.group(1)
                ms = m.group(2) or "0"
                ms = (ms + "000")[:3]
                return f"{mmdd} {hms}.{ms}"

            start_key = _dt_to_logcat_time_key(start_time)
            end_key = _dt_to_logcat_time_key(end_time)
            out_dir = os.path.dirname(output_path)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)

            written = 0
            with open(logcat_path, 'r', encoding='utf-8', errors='ignore') as fin:
                lines = list(fin)

            with open(output_path, 'w', encoding='utf-8', errors='replace') as fout:
                fout.write(f"# 异常日志提取: {start_str_display} ~ {end_str_display}, 包名: {pkg}\n")
                fout.write("# 包含: 崩溃(Crash)、ANR、以及 E 级别仅限 AndroidRuntime 或本应用 TAG 的日志（规则等同 adb logcat -s <pkg>:V AndroidRuntime:E）\n")
                fout.write("-" * 60 + "\n")

                i = 0
                while i < len(lines):
                    line = lines[i]
                    raw = line
                    stripped = line.strip()
                    if not stripped:
                        i += 1
                        continue
                    time_key = _line_to_logcat_time_key(stripped)
                    in_range = start_key <= time_key <= end_key if time_key else False
                    if time_key and time_key > end_key:
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
                        # 按原始规则 adb logcat -s com.svw.avatar:V AndroidRuntime:E 筛选：
                        # 仅将 AndroidRuntime:E 或应用 TAG(包名):E 视为异常，不因其它 TAG 的 E 且含包名就写入
                        # 不强绑定 -v 格式（brief/threadtime 等均可能）
                        # priority 为单字符 V/D/I/W/E/F/S，tag 紧跟 priority 后且以 ':' 结尾
                        parts = stripped.split()
                        priority_set = {"V", "D", "I", "W", "E", "F", "S"}
                        prio = ""
                        tag = ""
                        for i_tok in range(len(parts) - 1):
                            tok = parts[i_tok].rstrip()
                            if tok in priority_set:
                                prio = tok
                                nxt = parts[i_tok + 1]
                                tag = nxt.rstrip(":")
                                break
                        if prio == "E" and pkg in stripped:
                            # 只保留 AndroidRuntime 或应用自身 TAG 的 E 级别，排除如其它组件的 E
                            if tag == "AndroidRuntime" or tag == pkg:
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
                            next_key = _line_to_logcat_time_key(next_stripped)
                            if next_key and next_key > end_key:
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

            # if written > 0:
            #     logging.info(f"异常日志已写入 {output_path}，共 {written} 条")
            # else:
            #     # 无匹配记录时写入简单说明，便于排查为什么 exceptions.log 为空
            #     with open(output_path, 'a', encoding='utf-8', errors='replace') as fout2:
            #         fout2.write("# 本时间窗内未检测到与包名相关的 Crash/ANR/ERROR 日志；"
            #                     "可能原因：logcat 文件为空、时间戳格式不匹配或包名过滤过严。\n")
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
        仅处理时间戳 >= request_send_time - 校准时间差 -2s 的日志行（校准时间差 = PC 时间 - 设备时间，由 _ensure_device_time_offset 得到），
        使用 log 时间戳对齐到 PC 后与 request_send_time 相减得到 response_time。
        若结果为负（时钟偏差或匹配到上一次的「已显示」），则按 0 秒计并打 warning 日志。
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

        # 时间戳过滤：只接受 对齐后时间戳 >= request_send_time - 校准时间差 -2s 的日志（校准时间差 = pc_time - device_time）
        cutoff_dt = None
        device_offset = None
        if request_send_time:
            self._ensure_device_time_offset()
            device_offset = self._device_time_offset
            try:
                # 使用校准时间差+2s作为容差；若未校准则回退为 2s 容差
                offset_seconds = (device_offset or 0.0) + 2.0
                cutoff_dt = request_send_time - timedelta(seconds=offset_seconds)
            except Exception:
                pass

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
                    try:
                        line = proc.stdout.readline()
                        if not line:
                            break
                        # 以关键字为主匹配；tag_filter 仅作为“可选的缩小范围”条件，避免因 tag 不一致导致漏检
                        if (appear_text in line or disappear_text in line) and (not tag_filter or tag_filter in line):
                            with line_lock:
                                lines.append(line.strip())
                    except Exception as e:
                        logging.debug("[response-monitor] readline 异常: %s", e)
                        break
                if proc.poll() is None:
                    try:
                        proc.terminate()
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        try:
                            proc.kill()
                            proc.wait(timeout=1)
                        except Exception:
                            pass
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
                                # 可能出现负值：设备/PC 时钟偏差、或匹配到上一次的「已显示」日志；对外统一按 0 处理
                                if result['response_time'] < 0:
                                    logging.warning(
                                        f"[response-monitor] 响应时间为负 ({result['response_time']:.3f}s)，"
                                        "可能为时钟偏差或匹配到旧日志，已按 0 秒计"
                                    )
                                    result['response_time'] = 0.0
                            else:
                                appear_log_ts = time.time()
                                result['response_time'] = appear_log_ts - poll_start
                                if result['response_time'] < 0:
                                    result['response_time'] = 0.0
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
