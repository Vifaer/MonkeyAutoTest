#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import logging
import subprocess
import threading
import math
import re
from datetime import datetime, timedelta
from utils.timeout_command import run as run_cmd
from utils.stress_monitor import StressMonitor


class ExtendedMonkeyTest:
    """
    扩展的Monkey测试类
    支持长时间（12-72小时）压力测试
    """

    def __init__(self, device, package, config):
        self.device = device
        self.package = package
        self.config = config
        # 每次真正启动测试前会在 run_long_stress_test 里重新生成一次“按时间戳划分”的运行目录
        # 这里先给出一个兜底路径，避免某些辅助方法在测试启动前访问属性时报错
        self._run_log_dir = os.path.join("logs", str(device.sn))
        self.log_path = os.path.join(self._run_log_dir, "extended_monkey.log")
        self.logcat_log_path = os.path.join(self._run_log_dir, "logcat_monkey.log")
        self._monkey_process = None
        self._logcat_process = None
        self._stop_logcat = threading.Event()
        self._stop_monitor = threading.Event()

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
        # 某些 ROM/Monkey 版本在生成 permission/系统键 等事件时会异常，默认降低这些事件比例以提升稳定性
        pct_permission = self.config.get('pct_permission', 0)
        pct_anyevent = self.config.get('pct_anyevent', 0)
        pct_appswitch = self.config.get('pct_appswitch', 0)
        pct_syskeys = self.config.get('pct_syskeys', 0)
        
        # 按时长推算事件数：事件数 ≈ duration_hours * 3600 * 1000 / throttle
        # 这样可以让 Monkey 理论上跑约等于设定时长
        # 优先使用计算的事件数（确保GUI配置的时长生效），除非明确指定了 use_config_event_count
        use_config_event_count = self.config.get('use_config_event_count', False)
        
        if use_config_event_count and 'event_count' in self.config and self.config.get('event_count') is not None:
            event_count = self.config.get('event_count', 100000)
            logging.info(f"使用配置的事件数: {event_count}（忽略时长计算）")
        else:
            # 根据时长和throttle计算事件数
            # duration_hours * 3600秒 * 1000毫秒 / throttle毫秒 = 事件数
            calculated_events = int((duration_hours * 3600.0 * 1000.0) / throttle)
            # 至少保证有100个事件，避免过短
            event_count = max(100, calculated_events)
            # 日志中同时友好展示"小时/分钟"（提前计算，因为后面需要用到）
            if duration_hours < 1:
                minutes = duration_hours * 60.0
                duration_str = f"{minutes:g} 分钟 (~{duration_hours:.2f} 小时)"
            else:
                if abs(duration_hours - round(duration_hours)) < 1e-6:
                    duration_str = f"{int(round(duration_hours))} 小时"
                else:
                    duration_str = f"{duration_hours:.1f} 小时"
            logging.info(f"根据时长 {duration_str} 和 throttle {throttle}ms 计算事件数: {event_count}")

        # 日志中同时友好展示"小时/分钟"（如果之前没计算过）
        if 'duration_str' not in locals():
            if duration_hours < 1:
                minutes = duration_hours * 60.0
                duration_str = f"{minutes:g} 分钟 (~{duration_hours:.2f} 小时)"
            else:
                if abs(duration_hours - round(duration_hours)) < 1e-6:
                    duration_str = f"{int(round(duration_hours))} 小时"
                else:
                    duration_str = f"{duration_hours:.1f} 小时"

        logging.info(f"开始长时间压力测试，持续 {duration_str}，事件数: {event_count}")

        # 为本次测试运行创建独立的时间戳日志目录：logs/设备SN/年月日时分秒
        run_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        self._run_log_dir = os.path.join("logs", str(self.device.sn), run_ts)
        try:
            os.makedirs(self._run_log_dir, exist_ok=True)
        except Exception as e:
            logging.warning(f"创建运行日志目录失败 {self._run_log_dir}: {e}")
        # 更新本次运行使用的关键日志路径
        self.log_path = os.path.join(self._run_log_dir, "extended_monkey.log")
        self.logcat_log_path = os.path.join(self._run_log_dir, "logcat_monkey.log")

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
            'log_summary': {},
            'run_log_dir': self._run_log_dir,  # 供报告中的 performance_sampling 可视化使用
        }
        # monkey 工具缺陷统计（例如 permission NPE）
        result['monkey_tool_bug_count'] = 0
        result['monkey_tool_bug_types'] = {}

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

        # 采样间隔：基础1s；>0.5h 时按比例增大（1h->2s，2h->4s，12h->24s）
        import math
        sampling_interval = 1
        if duration_hours > 0.5:
            sampling_interval = max(1, math.ceil(duration_hours / 0.5))
        performance_log_path = os.path.join(self._run_log_dir, "performance_sampling.jsonl")
        fallback_log_path = os.path.join(self._run_log_dir, "input_fallback.log")

        try:
            # 启动后台监控线程
            monitor_thread = self._start_monitoring_thread(result, sampling_interval, performance_log_path)
            
            # 启动 logcat 日志抓取线程
            logcat_thread = self._start_logcat_capture()

            # 检查是否直接使用Fallback（跳过传统Monkey）。注：传入的 config 即为 long_stress 段，无 long_stress 子键
            use_fallback_only = bool(self.config.get('use_fallback_only', False))
            if use_fallback_only:
                logging.info("配置为直接使用Fallback事件注入，跳过传统Monkey命令")
                # 直接使用fallback进行压力测试
                import random
                seed = random.randint(0, 65535)
                fallback_log_path = os.path.join(self._run_log_dir, "input_fallback_direct.log")
                total_duration_seconds = duration_hours * 3600.0
                fallback_result = self._run_input_fallback(
                    duration_seconds=total_duration_seconds,
                    throttle_ms=int(throttle),
                    seed=seed,
                    log_path=fallback_log_path
                )
                # 记录fallback结果到result中
                result['fallback_direct'] = True
                result['fallback_events'] = fallback_result.get('events_injected', 0)
                result['fallback_duration'] = fallback_result.get('duration_seconds', 0.0)
            else:
                # 执行分阶段Monkey测试
                self._run_phased_monkey_test(duration_hours, throttle, event_count, result)

            # 停止监控和logcat
            self._stop_logcat.set()
            self._stop_monitor.set()
            if logcat_thread:
                logcat_thread.join(timeout=5)
            monitor_thread.join(timeout=10)

        except Exception as e:
            logging.error(f"长时间压力测试失败: {str(e)}")
            result['error'] = str(e)

        finally:
            result['actual_end_time'] = datetime.now().isoformat()
            # 将异常日志单独落盘
            try:
                start_dt = datetime.fromisoformat(result.get('start_time', '').replace('Z', '+00:00'))
                if start_dt.tzinfo:
                    start_dt = start_dt.replace(tzinfo=None)
            except Exception:
                start_dt = datetime.now() - timedelta(hours=float(result.get('duration_hours', 12)))
            end_dt = datetime.now()
            exc_path = os.path.join(self._get_run_log_dir(), "exceptions.log")
            StressMonitor.extract_exceptions_to_file(
                self.logcat_log_path, exc_path, start_dt, end_dt, self.package.name
            )
            self._analyze_test_results(result)

        return result

    def _run_input_fallback(self, duration_seconds: float, throttle_ms: int, seed: int, log_path: str):
        """
        Monkey 不可用时的可选 fallback：用 adb shell input 注入随机事件，尽量覆盖点击/滑动/返回键等。
        Returns:
            dict: { 'events_injected': int, 'duration_seconds': float }
        """
        import random
        import re

        if duration_seconds <= 0:
            return {'events_injected': 0, 'duration_seconds': 0.0}

        # 1) 在开始 fallback 事件注入前，主动唤醒待测应用到前台，避免 Monkey 崩溃后界面停留在桌面或其他应用上。
        self._ensure_app_in_foreground_for_fallback()

        # 2) 计算“安全可操作区域”（排除状态栏/导航栏），无法识别时回退为保守边界
        safe_region = self._get_safe_touch_region()
        w = safe_region["width"]
        h = safe_region["height"]
        x_min, x_max = safe_region["x_min"], safe_region["x_max"]
        y_min, y_max = safe_region["y_min"], safe_region["y_max"]

        rng = random.Random(int(seed) ^ 0xA5A5)
        start = time.time()
        injected = 0

        # 轻量持久化，避免异常丢失
        try:
            d = os.path.dirname(log_path)
            if d and not os.path.exists(d):
                os.makedirs(d, exist_ok=True)
        except Exception:
            pass

        try:
            f = open(log_path, "a", encoding="utf-8")
        except Exception:
            f = None

        def _log(msg: str):
            try:
                logging.info(msg)
                if f:
                    f.write(f"{datetime.now().isoformat()} {msg}\n")
                    f.flush()
            except Exception:
                pass

        _log(
            f"[fallback] start duration={duration_seconds:.1f}s "
            f"throttle={throttle_ms}ms seed={seed} screen={w}x{h} "
            f"safe_region=({x_min},{y_min})-({x_max},{y_max})"
        )

        # fallback 期间每 2 秒检测一次前台，不在前台则拉起，并每 60 秒打一次进度日志
        foreground_check_interval = 2.0
        progress_log_interval = 60.0
        last_foreground_check = time.time()
        last_progress_log = time.time()

        while (time.time() - start) < duration_seconds:
            now = time.time()
            # 每 2 秒检测并保证待测应用在前台
            if now - last_foreground_check >= foreground_check_interval:
                last_foreground_check = now
                try:
                    if not self._is_app_in_foreground():
                        _log("[fallback] 检测到待测应用不在前台，主动拉起")
                        self._ensure_app_in_foreground_for_fallback()
                except Exception as e:
                    logging.debug(f"[fallback] 前台检测/拉起异常: {e}")
            # 每 60 秒打一次进度，避免长时间无日志
            if now - last_progress_log >= progress_log_interval:
                last_progress_log = now
                elapsed = now - start
                _log(f"[fallback] 进行中 elapsed={elapsed:.0f}s remaining≈{max(0, duration_seconds - elapsed):.0f}s events={injected}")

            # 事件选择：tap(70%) / swipe(20%) / key(10%)
            r = rng.random()
            try:
                if r < 0.70:
                    x = rng.randint(x_min, x_max)
                    y = rng.randint(y_min, y_max)
                    run_cmd(f"adb -s {self.device.sn} shell input tap {x} {y}", timeout=3)
                elif r < 0.90:
                    x1 = rng.randint(x_min, x_max)
                    y1 = rng.randint(y_min, y_max)
                    x2 = rng.randint(x_min, x_max)
                    y2 = rng.randint(y_min, y_max)
                    dur = rng.randint(150, 600)
                    run_cmd(f"adb -s {self.device.sn} shell input swipe {x1} {y1} {x2} {y2} {dur}", timeout=3)
                else:
                    # 常用键：BACK/DPAD/ENTER
                    key = rng.choice([4, 19, 20, 21, 22, 23])
                    run_cmd(f"adb -s {self.device.sn} shell input keyevent {key}", timeout=3)
                injected += 1
            except Exception:
                # 忽略单次失败
                pass

            # 控制节奏（ms）
            time.sleep(max(0.05, float(throttle_ms) / 1000.0))

        spent = time.time() - start
        _log(f"[fallback] done events={injected} spent={spent:.1f}s")
        if f:
            try:
                f.close()
            except Exception:
                pass
        return {'events_injected': injected, 'duration_seconds': spent}

    def _get_safe_touch_region(self):
        """
        检测屏幕分辨率及 UI Insets，推算“安全可操作区域”，避免点到状态栏和导航栏/Dock 栏。
        优先使用 wm size + wm density + dumpsys window mStableInsets，失败时使用保守边界。

        为了进一步降低误触系统 UI（底部导航栏、虚拟按键、手势条等）的概率，这里：
          - 通过 dpi 估算状态栏/导航栏的典型高度（dp -> px）
          - 结合 mStableInsets 的 top/bottom，取两者中“更保守”的一侧
          - 在最终安全区域外生成一张可视化遮罩图片（如果安装了 matplotlib），帮助人眼校验

        Returns:
            dict: { width, height, x_min, x_max, y_min, y_max }
        """
        # 默认值（若所有检测失败）
        width, height = 1280, 720
        density_dpi = 320  # 合理的默认值，后续通过 wm density 更新
        top_inset = bottom_inset = left_inset = right_inset = 0

        # 1) 分辨率：wm size
        try:
            out = run_cmd(f"adb -s {self.device.sn} shell wm size", timeout=3)
            if isinstance(out, str):
                m = re.search(r"Physical size:\s*(\d+)\s*[xX]\s*(\d+)", out)
                if m:
                    width, height = int(m.group(1)), int(m.group(2))
        except Exception:
            # 尝试从 device.screen 兜底
            try:
                scr = getattr(self.device, "screen", "") or ""
                m2 = re.search(r"(\d+)\s*[xX]\s*(\d+)", scr)
                if m2:
                    width, height = int(m2.group(1)), int(m2.group(2))
            except Exception:
                pass

        # 1.5) 如果用户在配置中显式设置了 Monkey 遮罩区域百分比，则**强制**按百分比计算安全区域，
        #      不再回退到自动计算的 Insets / dp 估算逻辑（确保 Monkey / fallback 都与 GUI 配置一致）。
        # 配置格式（在 long_stress 段内）：
        #   "monkey_mask": {"top": 5.0, "bottom": 8.0, "left": 2.0, "right": 2.0}
        mask_cfg = (self.config or {}).get("monkey_mask") if isinstance(self.config, dict) else None
        if isinstance(mask_cfg, dict):
            def _parse_pct(key: str):
                try:
                    v = float(mask_cfg.get(key))
                    if v < 0:
                        v = 0.0
                    if v > 100:
                        v = 100.0
                    return v
                except Exception:
                    return None

            top_pct = _parse_pct("top")
            bottom_pct = _parse_pct("bottom")
            left_pct = _parse_pct("left")
            right_pct = _parse_pct("right")

            if any(p is not None for p in (top_pct, bottom_pct, left_pct, right_pct)):
                # 未显式配置的边缘按 0.0 处理（不遮罩）
                top_pct = top_pct if top_pct is not None else 0.0
                bottom_pct = bottom_pct if bottom_pct is not None else 0.0
                left_pct = left_pct if left_pct is not None else 0.0
                right_pct = right_pct if right_pct is not None else 0.0

                # 按百分比计算原始坐标
                x_min = int(width * left_pct / 100.0)
                x_max = int(width * (1.0 - right_pct / 100.0))
                y_min = int(height * top_pct / 100.0)
                y_max = int(height * (1.0 - bottom_pct / 100.0))

                # 为了避免极端配置（top+bottom>=100 等）导致区域塌缩，这里做一次“自我修复”，
                # 但仍然完全基于 monkey_mask 约束，不再回退到自动 Insets 算法。
                x_min = max(0, min(width - 1, x_min))
                x_max = max(x_min + 1, min(width, x_max))
                y_min = max(0, min(height - 1, y_min))
                y_max = max(y_min + 1, min(height, y_max))

                safe_region = {
                    "width": width,
                    "height": height,
                    "x_min": x_min,
                    "x_max": x_max,
                    "y_min": y_min,
                    "y_max": y_max,
                }
                logging.info(
                    f"[safe_region] 使用 monkey_mask={mask_cfg} 计算安全区域: "
                    f"({x_min},{y_min})-({x_max},{y_max}) screen={width}x{height}"
                )
                # 基于用户配置的遮罩区域生成可视化预览（预览与 fallback 使用的区域完全一致）
                self._save_safe_region_overlay_if_possible(safe_region)
                return safe_region

        # 2) 未配置 monkey_mask 时，禁用自动 Insets / dp 推算逻辑，直接使用“全屏可操作区域”
        safe_region = {
            "width": width,
            "height": height,
            "x_min": 0,
            "x_max": max(1, width),
            "y_min": 0,
            "y_max": max(1, height),
        }
        logging.info(
            f"[safe_region] 未配置 monkey_mask，使用全屏区域: "
            f"({safe_region['x_min']},{safe_region['y_min']})-({safe_region['x_max']},{safe_region['y_max']}) "
            f"screen={width}x{height}"
        )

        self._save_safe_region_overlay_if_possible(safe_region)
        return safe_region

    def _ensure_app_in_foreground_for_fallback(self):
        """
        确保待测应用处于前台（fallback 注入前或压力测试期间守护线程调用）。

        按顺序尝试多种拉起方式，每种方式执行后等待约 0.8s 再轮询前台状态；
        任一步检测到前台即返回；全部尝试后仍非前台则记录 INFO 并返回（尽力而为）。
        """
        try:
            pkg = getattr(self.package, "name", None) or getattr(self.package, "package", None)
            if isinstance(self.package, str):
                pkg = pkg or self.package
            activity = getattr(self.package, "activity", None) if hasattr(self.package, "activity") else None

            if not pkg:
                logging.warning("[fallback] 无法确定包名，跳过前台唤醒步骤")
                return

            wait_seconds = 5.0
            try:
                cfg_val = self.config.get("fallback_launch_wait_seconds")
                if cfg_val is not None:
                    wait_seconds = max(1.0, float(cfg_val))
            except Exception:
                pass

            poll_interval = 0.5
            settle_delay = 0.8  # 拉起命令执行后稍等再检测，便于窗口管理器更新

            # 策略顺序：先 MAIN/LAUNCHER（不依赖 activity），再显式 -n pkg/activity，最后 monkey
            strategies = []
            strategies.append((
                "am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p " + pkg,
                f"adb -s {self.device.sn} shell am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {pkg}",
                10,
            ))
            if activity:
                strategies.append((
                    f"am start -W -n {pkg}/{activity}",
                    f"adb -s {self.device.sn} shell am start -W -n {pkg}/{activity}",
                    15,
                ))
            strategies.append((
                "monkey -p " + pkg + " -c LAUNCHER 1",
                f"adb -s {self.device.sn} shell monkey -p {pkg} -c android.intent.category.LAUNCHER 1",
                10,
            ))

            for desc, cmd, timeout in strategies:
                logging.info(f"[fallback] 尝试拉起应用到前台: {desc}")
                out = run_cmd(cmd, timeout=timeout)
                if out is None:
                    logging.debug("[fallback] 该次命令超时，尝试下一方式")
                elif isinstance(out, str) and ("Error" in out or "Exception" in out or "not found" in out.lower()):
                    logging.debug(f"[fallback] 该次命令可能失败: {out[:200]}")
                time.sleep(settle_delay)
                deadline = time.time() + wait_seconds
                while time.time() < deadline:
                    if self._is_app_in_foreground():
                        logging.info("[fallback] 检测到待测应用已在前台，继续执行")
                        return
                    time.sleep(poll_interval)
                # 本策略未在限定时间内检测到前台，尝试下一策略

            logging.info(
                "[fallback] 已尝试所有拉起方式，将继续执行后续操作（若前台检测与设备输出格式不一致，可忽略）"
            )
        except Exception as e:
            logging.warning(f"[fallback] 前台唤醒应用失败（继续执行 fallback）: {e}")

    def _ensure_foreground_during_monkey(self, process: subprocess.Popen, phase_duration_seconds: float):
        """
        在 Monkey 运行期间，每 2 秒检测一次待测应用是否仍在前台；
        若发现不在前台，则调用 _ensure_app_in_foreground_for_fallback 主动拉起应用，
        拉起后等待 1 秒再验证是否在前台，并打印相应日志便于追踪。
        """
        check_interval = 2.0
        start_ts = time.time()
        while process.poll() is None and (time.time() - start_ts) < phase_duration_seconds:
            try:
                if not self._is_app_in_foreground():
                    logging.info("[foreground-guard] 检测到待测应用不在前台，主动拉起应用到前台")
                    self._ensure_app_in_foreground_for_fallback()
                    time.sleep(1.0)  # 给设备时间完成窗口切换后再做一次验证
                    if self._is_app_in_foreground():
                        logging.info("[foreground-guard] 拉起后确认待测应用已在前台，下一轮 2s 后再次检测")
                    else:
                        logging.info("[foreground-guard] 拉起后仍检测到应用不在前台，下一轮 2s 后将再次尝试")
                time.sleep(check_interval)
            except Exception as e:
                logging.debug(f"[foreground-guard] 前台监控异常: {e}")
                time.sleep(check_interval)

    def _save_safe_region_overlay_if_possible(self, safe_region: dict):
        """
        尝试基于“设备真实截图 + 安全区域”生成一张 PNG 预览图。

        行为：
          1. 先通过 adb screencap 抓取当前屏幕截图并保存到本地 logs/<sn>/<timestamp>/device_screenshot.png
          2. 在截图基础上，用颜色遮罩标记“非可操作区域”，并叠加中文说明文字

        注意：
          - 仅在安装了 matplotlib 的情况下生效
          - 若截图失败/字体不可用，仅记录日志，不影响主流程
        """
        try:
            import matplotlib

            # 使用非交互式后端，避免在无 GUI 环境下出问题
            try:
                matplotlib.use("Agg")
            except Exception:
                pass

            import matplotlib.pyplot as plt
            from matplotlib.patches import Rectangle
            from matplotlib.font_manager import FontProperties

            width = safe_region.get("width", 0)
            height = safe_region.get("height", 0)
            x_min = safe_region.get("x_min", 0)
            x_max = safe_region.get("x_max", 0)
            y_min = safe_region.get("y_min", 0)
            y_max = safe_region.get("y_max", 0)

            if width <= 0 or height <= 0:
                return

            # 1) 先抓取设备当前屏幕截图到本次运行日志目录
            run_dir = self._get_run_log_dir()
            try:
                os.makedirs(run_dir, exist_ok=True)
            except Exception:
                pass

            device_tmp_path = "/sdcard/monkeyautotest_safe_region.png"
            local_screenshot_path = os.path.join(run_dir, "device_screenshot.png")

            try:
                # 抓取截图到设备本地
                cmd_cap = f"adb -s {self.device.sn} shell screencap -p {device_tmp_path}"
                run_cmd(cmd_cap, timeout=15)
                # 拉取到 PC 当前运行日志目录
                cmd_pull = f"adb -s {self.device.sn} pull {device_tmp_path} \"{local_screenshot_path}\""
                run_cmd(cmd_pull, timeout=20)
            except Exception as e:
                logging.debug(f"抓取/拉取设备截图失败，跳过遮罩可视化: {e}")
                return

            if not os.path.exists(local_screenshot_path):
                return

            # 读取截图
            img = plt.imread(local_screenshot_path)
            if img is None:
                return

            img_h, img_w = img.shape[0], img.shape[1]

            # 若截图分辨率与 wm size 有差异，以截图尺寸为准，整体按比例缩放安全区域
            if img_w != width or img_h != height:
                scale_x = img_w / float(width)
                scale_y = img_h / float(height)
                x_min = int(x_min * scale_x)
                x_max = int(x_max * scale_x)
                y_min = int(y_min * scale_y)
                y_max = int(y_max * scale_y)
                width = img_w
                height = img_h

            fig_w = max(4, width / 400)   # 适当缩放，避免图像过大
            fig_h = max(4, height / 400)
            fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=100)

            # 显示设备截图，原点在左上角
            ax.imshow(img, origin="upper")

            # 2) 在截图基础上绘制“非可操作区域”遮罩：用半透明红色包裹安全区域四周
            safe_w = max(0, x_max - x_min)
            safe_h = max(0, y_max - y_min)

            # 顶部遮罩
            if y_min > 0:
                ax.add_patch(
                    Rectangle(
                        (0, 0),
                        width,
                        y_min,
                        facecolor=(1.0, 0.0, 0.0, 0.35),
                        edgecolor="none",
                    )
                )
            # 底部遮罩
            if y_max < height:
                ax.add_patch(
                    Rectangle(
                        (0, y_max),
                        width,
                        height - y_max,
                        facecolor=(1.0, 0.0, 0.0, 0.35),
                        edgecolor="none",
                    )
                )
            # 左侧遮罩
            if x_min > 0:
                ax.add_patch(
                    Rectangle(
                        (0, y_min),
                        x_min,
                        safe_h,
                        facecolor=(1.0, 0.0, 0.0, 0.35),
                        edgecolor="none",
                    )
                )
            # 右侧遮罩
            if x_max < width:
                ax.add_patch(
                    Rectangle(
                        (x_max, y_min),
                        width - x_max,
                        safe_h,
                        facecolor=(1.0, 0.0, 0.0, 0.35),
                        edgecolor="none",
                    )
                )

            # 安全区域：用半透明绿色描边矩形标记
            ax.add_patch(
                Rectangle(
                    (x_min, y_min),
                    safe_w,
                    safe_h,
                    facecolor=(0.0, 0.8, 0.0, 0.10),
                    edgecolor=(0.0, 0.9, 0.0, 0.9),
                    linewidth=2,
                )
            )

            # 3) 中文文字说明：优先尝试使用系统中常见的中文字体，避免乱码/方框
            font_prop = None
            try:
                candidate_fonts = [
                    r"C:\Windows\Fonts\msyh.ttc",      # 微软雅黑
                    r"C:\Windows\Fonts\simhei.ttf",    # 黑体
                    r"/System/Library/Fonts/PingFang.ttc",  # macOS
                    r"/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux 常见中文字体
                ]
                for fp in candidate_fonts:
                    if os.path.exists(fp):
                        font_prop = FontProperties(fname=fp)
                        break
                if font_prop is not None:
                    plt.rcParams["axes.unicode_minus"] = False
            except Exception:
                font_prop = None

            text_kwargs = {
                "fontsize": 10,
                "color": "white",
                "ha": "center",
                "va": "bottom",
            }
            if font_prop is not None:
                text_kwargs["fontproperties"] = font_prop

            ax.text(
                width / 2,
                height * 0.02,
                "红色半透明区域为非可操作区域（避免点击系统UI/导航栏/Dock）",
                **text_kwargs,
            )

            ax.set_xlim(0, width)
            ax.set_ylim(height, 0)  # 反转 y 轴，使原点在左上角，符合屏幕坐标
            ax.set_xticks([])
            ax.set_yticks([])
            plt.tight_layout()

            # 保存到当前运行的日志目录中
            out_path = os.path.join(run_dir, "safe_region_overlay.png")
            try:
                fig.savefig(out_path, dpi=150)
                logging.info(f"已生成基于截图的 fallback 安全区域遮罩预览图: {out_path}")
            finally:
                plt.close(fig)
        except Exception as e:
            # 任何异常都只记录，不影响主流程
            logging.debug(f"生成安全区域遮罩预览图失败: {e}")

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
            phase_payload = {
                'phase': phase + 1,
                'start_time': phase_result['start_time'],
                'end_time': phase_result['end_time'],
                'events_executed': phase_result['events'],
                'crashes_in_phase': phase_result['crashes'],
                'anrs_in_phase': phase_result['anrs']
            }
            # 附加 monkey 工具缺陷信息（用于报告/统计）
            if phase_result.get("monkey_tool_bug"):
                result['monkey_tool_bug_count'] += 1
                bt = phase_result.get("monkey_tool_bug_type") or "unknown"
                result['monkey_tool_bug_types'][bt] = int(result['monkey_tool_bug_types'].get(bt, 0)) + 1
                phase_payload["monkey_tool_bug"] = True
                phase_payload["monkey_tool_bug_type"] = bt
                if phase_result.get("fallback"):
                    phase_payload["fallback"] = phase_result.get("fallback")

            result['performance_data'].append(phase_payload)

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
        # 分阶段 Monkey 日志写入到本次运行的时间戳目录下
        phase_log = os.path.join(self._get_run_log_dir(), f"monkey_phase_{phase + 1}.log")

        # 停止应用进程
        cmd = f"adb -s {self.device.sn} shell am force-stop {self.package.name}"
        run_cmd(cmd)
        time.sleep(3)

        # 执行Monkey命令
        import random
        seed = random.randint(0, 65535)

        # 构建Monkey命令（不使用shell重定向，改用subprocess直接捕获）
        # 注意：monkey 的 event-count 是最后一个“非选项参数”，一旦解析到 event-count，后续参数可能不再解析。
        # 因此必须把所有 --pct-* 等选项放在 event-count 之前。
        monkey_cmd = [
            "adb", "-s", self.device.sn, "shell", "monkey",
            "-p", self.package.name,
            "-s", str(seed),
            "--ignore-crashes",
            "--ignore-timeouts",
            "--ignore-security-exceptions",
            "--ignore-native-crashes",
            "--throttle", str(throttle),
            # 适度增加 verbosity，便于诊断
            "-v", "-v"
        ]

        # 追加事件比例控制：
        # 某些 ROM 的 monkey 在生成 permission 事件时会 NPE，因此这里默认显式配置各类事件百分比，
        # 并将 permission/syskeys/appswitch/anyevent 等设为 0，确保不会走到 permission 事件逻辑。
        def _get_int(name: str, default: int) -> int:
            try:
                return int(self.config.get(name, default))
            except Exception:
                return default

        pct_touch = _get_int("pct_touch", 35)
        pct_motion = _get_int("pct_motion", 25)
        pct_nav = _get_int("pct_nav", 20)
        pct_majornav = _get_int("pct_majornav", 15)
        pct_pinchzoom = _get_int("pct_pinchzoom", 5)
        pct_trackball = _get_int("pct_trackball", 0)
        pct_flip = _get_int("pct_flip", 0)
        pct_rotation = _get_int("pct_rotation", 0)

        pct_syskeys = _get_int("pct_syskeys", 0)
        pct_appswitch = _get_int("pct_appswitch", 0)
        pct_anyevent = _get_int("pct_anyevent", 0)
        pct_permission = _get_int("pct_permission", 0)

        def _clamp(v):
            return max(0, min(100, v))

        monkey_cmd += [
            "--pct-touch", str(_clamp(pct_touch)),
            "--pct-motion", str(_clamp(pct_motion)),
            "--pct-nav", str(_clamp(pct_nav)),
            "--pct-majornav", str(_clamp(pct_majornav)),
            "--pct-pinchzoom", str(_clamp(pct_pinchzoom)),
            "--pct-trackball", str(_clamp(pct_trackball)),
            "--pct-flip", str(_clamp(pct_flip)),
            "--pct-rotation", str(_clamp(pct_rotation)),

            "--pct-syskeys", str(_clamp(pct_syskeys)),
            "--pct-appswitch", str(_clamp(pct_appswitch)),
            "--pct-anyevent", str(_clamp(pct_anyevent)),
            "--pct-permission", str(_clamp(pct_permission)),
        ]

        # event-count 必须放在最后
        monkey_cmd.append(str(event_count))

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

            # 启动应用前台守护线程：每 few 秒检测一次，如果不在前台则自动拉起
            guard_thread = threading.Thread(
                target=self._ensure_foreground_during_monkey,
                args=(process, phase_duration_seconds),
                daemon=True,
            )
            guard_thread.start()

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
        
        # 检查Monkey进程的退出码
        exit_code = None
        exit_reason = ""
        if process and process.poll() is not None:
            exit_code = process.returncode
            if exit_code != 0:
                # 尝试从日志文件中读取最后几行，查找错误信息
                try:
                    if os.path.exists(phase_log):
                        with open(phase_log, 'rb') as f:
                            # 读取最后10KB的内容
                            f.seek(max(0, os.path.getsize(phase_log) - 10240))
                            last_lines = f.read().decode('utf-8', errors='ignore').split('\n')
                            # 查找错误相关的行
                            error_lines = [line for line in last_lines[-20:] if any(keyword in line.upper() for keyword in ['ERROR', 'CRASH', 'EXCEPTION', 'FAILED', 'ABORT'])]
                            if error_lines:
                                exit_reason = f"，最后错误: {error_lines[-1][:200]}"
                except Exception as e:
                    logging.debug(f"读取Monkey日志失败: {e}")
                
                # 根据退出码提供更详细的说明
                exit_code_meanings = {
                    1: "一般错误",
                    2: "参数错误",
                    47: "进程被信号终止（可能是应用崩溃或系统资源问题）",
                }
                meaning = exit_code_meanings.get(exit_code, "未知错误")
                logging.warning(f"Monkey进程异常退出，退出码: {exit_code} ({meaning}){exit_reason}")
                
                # 如果提前退出（远小于预期时长），记录警告
                expected_duration = (event_count * throttle) / 1000.0
                if actual_duration < expected_duration * 0.5:  # 实际时长小于预期的50%
                    logging.warning(f"Monkey提前退出：实际运行 {actual_duration:.1f}秒，预期 {expected_duration:.1f}秒，可能原因：应用崩溃、权限问题或系统资源限制")

        # 再次停止应用
        cmd = f"adb -s {self.device.sn} shell am force-stop {self.package.name}"
        run_cmd(cmd)

        # 分析阶段日志（包括logcat）
        phase_stats = self._analyze_phase_log(phase_log, seed=seed)
        logcat_stats = self._analyze_logcat_for_phase(phase + 1, start_time, end_time)
        
        # 合并统计结果
        total_crashes = phase_stats['crashes'] + logcat_stats['crashes']
        total_anrs = phase_stats['anrs'] + logcat_stats['anrs']
        events_completed = phase_stats.get('events_completed', 0)

        # Monkey 工具缺陷：permission NPE 等。可选 fallback：改用 adb input 注入随机事件，把阶段时长补齐。
        fallback_result = None
        if phase_stats.get("monkey_tool_bug"):
            bug_type = phase_stats.get("monkey_tool_bug_type") or "unknown"
            logging.warning(f"检测到 Monkey 工具异常类型: {bug_type}（将标记为 monkey_tool_bug）")
            if bool(self.config.get("enable_input_fallback", True)):
                remaining = max(0.0, float(phase_duration_seconds) - float(actual_duration))
                if remaining >= 1.0:
                    # fallback 日志同样放在本次运行的日志目录中
                    fallback_log = os.path.join(self._get_run_log_dir(), f"input_fallback_phase_{phase + 1}.log")
                    logging.warning(f"启用 input fallback，补齐剩余时长 {remaining:.1f}s（避免压力测试过早结束）")
                    fallback_result = self._run_input_fallback(
                        duration_seconds=remaining,
                        throttle_ms=int(throttle),
                        seed=int(seed),
                        log_path=fallback_log,
                    )
                    # 更新实际耗时（用于后续统计展示）
                    actual_duration = float(actual_duration) + float(fallback_result.get("duration_seconds", 0.0))
                    # fallback 注入事件不计入 Monkey injected，但记录在返回结构里
        
        # 如果事件完成数远小于预期，记录警告
        if events_completed > 0 and events_completed < event_count * 0.5:
            logging.warning(f"Monkey仅完成 {events_completed}/{event_count} 个事件（{events_completed/event_count*100:.1f}%），可能提前退出")
        
        # 检查是否因为超时被强制结束
        was_timeout = actual_duration >= phase_duration_seconds * 0.95  # 接近目标时长（95%以上）认为可能是超时
        timeout_info = "（超时强制结束）" if was_timeout else ""
        
        # 计算预期时长（事件数 * throttle / 1000）
        expected_duration = (event_count * throttle) / 1000.0
        duration_info = f"预期 {expected_duration:.1f}秒" if expected_duration > 0 else ""

        # 计算完成率
        completion_rate = 0.0
        if expected_duration > 0:
            completion_rate = (actual_duration / expected_duration) * 100.0
        
        completion_info = ""
        if completion_rate < 50.0 and exit_code != 0:
            completion_info = f"，完成率: {completion_rate:.1f}%"
        
        logging.info(f"阶段 {phase + 1} 完成: 实际耗时 {actual_duration:.1f}秒 {timeout_info}, "
                    f"目标时长 {phase_duration_seconds:.1f}秒, {duration_info}, "
                    f"崩溃 {total_crashes} 次, ANR {total_anrs} 次, "
                    f"退出码: {exit_code if exit_code is not None else 'N/A'}{completion_info}")

        return {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'events': event_count,
            'crashes': total_crashes,
            'anrs': total_anrs,
            'actual_duration_seconds': actual_duration,
            'exit_code': exit_code,
            'monkey_tool_bug': bool(phase_stats.get("monkey_tool_bug")),
            'monkey_tool_bug_type': phase_stats.get("monkey_tool_bug_type"),
            'fallback': fallback_result,
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

    def _analyze_phase_log(self, log_path, seed=None):
        """
        分析阶段日志（Monkey stdout），统计崩溃和ANR
        """
        crashes = 0
        anrs = 0
        events_completed = 0
        monkey_tool_bug = False
        monkey_tool_bug_type = None
        last_lines = []

        try:
            if os.path.exists(log_path):
                file_size = os.path.getsize(log_path)
                if file_size == 0:
                    logging.warning(f"Monkey日志文件为空: {log_path}")
                else:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            line = line.strip()
                            # Monkey 工具自身崩溃识别（ROM/monkey 缺陷）
                            if ("MonkeyPermissionUtil.generateRandomPermissionEvent" in line or
                                    "MonkeyPermissionUtil.java" in line):
                                monkey_tool_bug = True
                                monkey_tool_bug_type = "permission_npe"
                            if f"// CRASH: {self.package.name}" in line:
                                crashes += 1
                            elif f"// NOT RESPONDING: {self.package.name}" in line:
                                anrs += 1
                            elif "Events injected:" in line:
                                # 尝试提取已完成的事件数
                                try:
                                    parts = line.split("Events injected:")
                                    if len(parts) > 1:
                                        events_completed = int(parts[1].strip().split()[0])
                                except Exception:
                                    pass
                            last_lines.append(line)
                    
                    # 记录最后几行日志（用于诊断）
                    if last_lines:
                        tail = last_lines[-10:]
                        logging.warning(
                            "Monkey异常退出日志尾部%s:\n%s",
                            f"(seed={seed})" if seed is not None else "",
                            "\n".join(tail)
                        )
                    
                    if events_completed > 0:
                        logging.info(f"Monkey完成事件数: {events_completed}")
        except Exception as e:
            logging.warning(f"分析阶段日志失败: {str(e)}")

        return {
            'crashes': crashes, 
            'anrs': anrs,
            'events_completed': events_completed,
            'monkey_tool_bug': monkey_tool_bug,
            'monkey_tool_bug_type': monkey_tool_bug_type,
            'log_size': file_size if os.path.exists(log_path) else 0
        }
    
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
            
            # 启动 logcat 抓取（全量）：作为每次测试运行的完整记录
            logcat_cmd = [
                "adb", "-s", self.device.sn, "logcat",
                "-v", "threadtime",
            ]
            
            try:
                from utils.timeout_command import _resolve_adb_path
                adb_path = _resolve_adb_path()
                if adb_path:
                    logcat_cmd[0] = adb_path
                
                process = subprocess.Popen(
                    logcat_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self._logcat_process = process
                
                with open(self.logcat_log_path, 'w', encoding='utf-8', errors='replace') as f:
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

    def _start_monitoring_thread(self, result, interval_seconds, perf_log_path):
        """
        启动后台监控线程
        监控CPU、内存等性能指标，并将采样以 JSONL 持久化，避免异常退出导致数据丢失
        """
        def monitor():
            # 确保日志目录存在
            log_dir = os.path.dirname(perf_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            # 打开文件（追加），逐条 flush，降低丢失风险
            log_file = open(perf_log_path, 'a', encoding='utf-8')
            while True:
                try:
                    if self._stop_monitor.is_set():
                        break

                    # 前台/后台判定（以采样时应用所处状态为准）
                    is_fg = self._is_app_in_foreground()
                    mode = "foreground" if is_fg else "background"

                    # 监控CPU使用率
                    cpu_usage = self._get_cpu_usage()

                    # 监控内存使用率
                    mem_usage = self._get_memory_usage()

                    # 记录性能数据（应用级 PSS：KB/MB）
                    memory_mb = round(mem_usage / 1024.0, 2) if mem_usage > 0 else 0.0
                    perf_data = {
                        'timestamp': datetime.now().isoformat(),
                        'app_cpu_pct': cpu_usage,
                        'app_memory_pss_kb': mem_usage,
                        'app_memory_pss_mb': memory_mb,
                        'app_foreground_mode': mode,
                        'device_sn': self.device.sn,
                        'package': self.package.name,
                    }

                    result['performance_data'].append(perf_data)
                    # 实时写入文件，减少异常丢失风险
                    import json
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

        import threading
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()

        return monitor_thread

    def _get_cpu_usage(self):
        """获取CPU使用率（多种方法尝试，提高兼容性）"""
        pkg = getattr(self.package, "name", None) or getattr(self.package, "package", None)
        if not pkg:
            return 0.0
        
        # 方法1: top -n 1 -d 1（约 1 秒采样，避免 -d 0 瞬时采样导致常为 0%）
        try:
            cmd = f"adb -s {self.device.sn} shell top -n 1 -d 1"
            result = run_cmd(cmd, timeout=5)
            if result and isinstance(result, str):
                for line in result.splitlines():
                    if pkg in line:
                        parts = line.split()
                        for token in parts:
                            if token.endswith('%'):
                                cpu_str = token.rstrip('%')
                                try:
                                    cpu_val = float(cpu_str)
                                    if cpu_val >= 0 and cpu_val <= 100:
                                        return cpu_val
                                except ValueError:
                                    pass
        except Exception:
            pass
        
        # 方法2: dumpsys cpuinfo（部分设备更可靠）
        try:
            cmd = f"adb -s {self.device.sn} shell dumpsys cpuinfo | grep {pkg}"
            result = run_cmd(cmd, timeout=3)
            if result and isinstance(result, str):
                import re
                # 查找百分比，格式可能是 "XX%"
                match = re.search(r'(\d+\.?\d*)%', result)
                if match:
                    cpu_val = float(match.group(1))
                    if cpu_val >= 0 and cpu_val <= 100:
                        return cpu_val
        except Exception:
            pass
        
        # 方法3: ps + top（组合方式，部分ROM需要）
        try:
            # 先获取进程PID
            cmd = f"adb -s {self.device.sn} shell ps | grep {pkg}"
            result = run_cmd(cmd, timeout=3)
            if result and isinstance(result, str):
                for line in result.splitlines():
                    if pkg in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            pid = parts[1]
                            # 用top查看该PID的CPU
                            cmd2 = f"adb -s {self.device.sn} shell top -n 1 -d 1 -p {pid}"
                            result2 = run_cmd(cmd2, timeout=5)
                            if result2 and isinstance(result2, str):
                                for line2 in result2.splitlines():
                                    if pid in line2:
                                        parts2 = line2.split()
                                        for token in parts2:
                                            if token.endswith('%'):
                                                cpu_str = token.rstrip('%')
                                                try:
                                                    cpu_val = float(cpu_str)
                                                    if cpu_val >= 0 and cpu_val <= 100:
                                                        return cpu_val
                                                except ValueError:
                                                    pass
        except Exception:
            pass

        return 0.0

    def _get_memory_usage(self):
        """获取内存使用率（PSS，单位：KB），返回KB值（后续转换为MB显示）"""
        pkg = getattr(self.package, "name", None) or getattr(self.package, "package", None)
        if not pkg:
            return 0
        
        cmd = f"adb -s {self.device.sn} shell dumpsys meminfo {pkg}"
        result = run_cmd(cmd, timeout=5)

        if result and isinstance(result, str):
            try:
                for line in result.splitlines():
                    if "TOTAL PSS:" in line:
                        after = line.split("TOTAL PSS:")[1].strip()
                        num_str = after.split()[0]
                        # 移除可能的逗号分隔符
                        num_str = num_str.replace(',', '')
                        return int(num_str)
            except Exception:
                pass

        return 0

    def _get_run_log_dir(self):
        """
        获取当前测试运行对应的日志目录。

        优先使用 run_long_stress_test 中初始化的时间戳子目录；
        若尚未初始化，则退回到按 SN 的根目录 logs/<sn>，避免调用出错。
        """
        d = getattr(self, "_run_log_dir", None)
        if d:
            return d
        # 兜底：按设备 SN 返回一个稳定路径
        return os.path.join("logs", str(self.device.sn))

    def _is_app_in_foreground(self):
        """
        判断待测应用是否在前台：先查 window 焦点，再查 activity 栈顶，提高兼容性。
        """
        pkg = getattr(self.package, "name", None) or getattr(self.package, "package", None)
        if not pkg:
            return False
        try:
            # 方式1：dumpsys window windows 中的 mCurrentFocus / mFocusedApp
            cmd = f"adb -s {self.device.sn} shell dumpsys window windows"
            out = run_cmd(cmd, timeout=3)
            if isinstance(out, str):
                for line in out.splitlines():
                    line = line.strip()
                    if "mCurrentFocus" in line or "mFocusedApp" in line:
                        if pkg in line:
                            return True
            # 方式2：dumpsys activity activities 中的 resumed 栈顶（部分机型焦点行格式不同）
            cmd = f"adb -s {self.device.sn} shell dumpsys activity activities"
            out = run_cmd(cmd, timeout=3)
            if isinstance(out, str):
                for line in out.splitlines():
                    line = line.strip()
                    if "mResumedActivity" in line or "resumed" in line.lower():
                        if pkg in line:
                            return True
        except Exception:
            return False
        return False

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
        import json
        import math

        # 性能采样日志路径：与运行期采样线程使用的路径保持一致（时间戳子目录）
        perf_log_path = os.path.join(self._get_run_log_dir(), "performance_sampling.jsonl")

        def _safe_mean(xs):
            xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
            return (sum(xs) / len(xs)) if xs else 0.0

        def _safe_max(xs):
            xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
            return max(xs) if xs else 0.0

        def _memory_trend_slope(pss_list):
            # 简单线性趋势斜率（单位：每采样点增长多少 KB）
            ys = [y for y in pss_list if isinstance(y, (int, float)) and not isinstance(y, bool)]
            n = len(ys)
            if n < 10:
                return 0.0
            xs = list(range(n))
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xy = sum(x * y for x, y in zip(xs, ys))
            sum_x2 = sum(x * x for x in xs)
            denom = (n * sum_x2 - sum_x * sum_x)
            if denom == 0:
                return 0.0
            return (n * sum_xy - sum_x * sum_y) / denom

        # 优先从 JSONL 读取（更可靠，且异常退出也能保存已采样数据）
        cpu_fg, cpu_bg, mem_fg, mem_bg = [], [], [], []
        sample_count = 0
        first_ts, last_ts = None, None
        data_source = None

        try:
            if os.path.exists(perf_log_path) and os.path.getsize(perf_log_path) > 0:
                with open(perf_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            item = json.loads(line)
                        except Exception:
                            continue

                        if not isinstance(item, dict):
                            continue
                        if item.get("package") and item.get("package") != self.package.name:
                            continue

                        ts = item.get("timestamp")
                        if isinstance(ts, str):
                            if first_ts is None:
                                first_ts = ts
                            last_ts = ts

                        mode = item.get("app_foreground_mode", "")
                        cpu = float(item.get("app_cpu_pct", 0.0) or 0.0)
                        mem = int(item.get("app_memory_pss_kb", 0) or 0)
                        if mode == "foreground":
                            cpu_fg.append(cpu)
                            mem_fg.append(mem)
                        elif mode == "background":
                            cpu_bg.append(cpu)
                            mem_bg.append(mem)
                        else:
                            # 未知 mode：计入总体但不分组
                            cpu_fg.append(cpu)
                            mem_fg.append(mem)

                        sample_count += 1

                data_source = "jsonl"
        except Exception as e:
            logging.warning(f"读取性能采样文件失败 {perf_log_path}: {e}")

        # 回退：从内存 performance_data 统计（兼容旧逻辑）
        if data_source is None:
            perf_data = result.get("performance_data", [])
            for d in perf_data:
                if not isinstance(d, dict):
                    continue
                mode = d.get("app_foreground_mode", "foreground")
                cpu = float(d.get("app_cpu_pct", 0.0) or 0.0)
                mem = int(d.get("app_memory_pss_kb", 0) or 0)
                if mode == "background":
                    cpu_bg.append(cpu)
                    mem_bg.append(mem)
                else:
                    cpu_fg.append(cpu)
                    mem_fg.append(mem)
            sample_count = len(perf_data)
            data_source = "memory"

        cpu_all = cpu_fg + cpu_bg
        mem_all = mem_fg + mem_bg

        # 估算测试时长：JSONL 优先用采样点粗估；否则保持原先固定 30s 的估算
        # 注：真实采样间隔是动态的，这里用“采样点数”作为可追溯统计信息，时长用已有 result 的实际时间更可靠
        total_time_seconds = 0
        if isinstance(result.get("actual_end_time"), str) and isinstance(result.get("start_time"), str):
            # 这里不解析 ISO 时间，避免引入额外依赖；保留 0 由报告端展示 phase 实际耗时
            total_time_seconds = 0

        memory_slope = _memory_trend_slope(mem_all)
        memory_trend = "stable"
        # 简单阈值：每采样点增长 > 5KB 认为有上升趋势（阈值保守，避免误报）
        if memory_slope > 5:
            memory_trend = "increasing"

        result['log_summary'] = {
            'data_source': data_source,
            'performance_log_path': perf_log_path,
            'sample_count': sample_count,
            'first_sample_timestamp': first_ts,
            'last_sample_timestamp': last_ts,

            'total_test_time_seconds': total_time_seconds,

            'average_cpu_usage': _safe_mean(cpu_all),
            'peak_cpu_usage': _safe_max(cpu_all),
            'average_cpu_foreground': _safe_mean(cpu_fg),
            'peak_cpu_foreground': _safe_max(cpu_fg),
            'average_cpu_background': _safe_mean(cpu_bg),
            'peak_cpu_background': _safe_max(cpu_bg),

            'average_memory_pss': _safe_mean(mem_all),
            'peak_memory_pss': int(_safe_max(mem_all) or 0),
            'average_memory_foreground_pss': _safe_mean(mem_fg),
            'peak_memory_foreground_pss': int(_safe_max(mem_fg) or 0),
            'average_memory_background_pss': _safe_mean(mem_bg),
            'peak_memory_background_pss': int(_safe_max(mem_bg) or 0),

            'memory_trend': memory_trend,
            'memory_trend_slope_per_sample': float(memory_slope),

            'total_crashes': result.get('crashes', 0),
            'total_anrs': result.get('anrs', 0),
        }

        logging.info(f"测试结果分析完成: {result['log_summary']}")