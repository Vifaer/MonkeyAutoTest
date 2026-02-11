#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
广播模式压力测试
通过 adb shell am broadcast 发送广播调用目标应用能力，按行遍历 hint 内容，每隔 30 秒执行一条
"""

import os
import time
import logging
import threading
from typing import Callable, Optional
from datetime import datetime, timedelta

from utils.timeout_command import run as run_cmd
from utils.stress_monitor import StressMonitor


class BroadcastStressTest:
    """广播模式压力测试：发送 broadcast 触发应用，监控前台与资源"""

    def __init__(self, device, package, config):
        self.device = device
        self.package = package
        self.config = config
        self._stop_event = threading.Event()
        self._run_log_dir = os.path.join("logs", str(device.sn))
        self.log_path = ""
        self.logcat_log_path = ""
        # 连续无响应计数与自动恢复阈值
        rm_cfg = (config or {}).get("response_monitor") or {}
        try:
            self.max_failure_count = int(float(rm_cfg.get("max_failure_count", 0) or 0))
        except Exception:
            self.max_failure_count = 0
        self._consecutive_no_response = 0

    def _restart_service_and_wait(self):
        """终止当前应用进程并重新拉起到前台，等待 10 秒让应用完全启动和稳定后继续。"""
        try:
            pkg = getattr(self.package, "name", None) or getattr(self.package, "package", None)
            if not pkg:
                logging.warning("[response-monitor] 无法确定包名，跳过自动重启")
                return
            cmd_stop = f"adb -s {self.device.sn} shell am force-stop {pkg}"
            logging.info(f"[response-monitor] 自动恢复：执行 {cmd_stop}")
            run_cmd(cmd_stop, timeout=10)
        except Exception as e:
            logging.warning(f"[response-monitor] 自动停止应用失败: {e}")
        # 使用 StressMonitor 的前台拉起逻辑恢复应用
        try:
            from utils.stress_monitor import StressMonitor
            monitor = StressMonitor(self.device, self.package, self.config)
            monitor.ensure_app_in_foreground()
        except Exception as e:
            logging.warning(f"[response-monitor] 自动拉起应用失败: {e}")
        logging.info("[response-monitor] 自动恢复完成，等待 10 秒后继续测试")
        time.sleep(10)

    def _load_hints(self):
        """加载 hint 列表：优先 hints_file（文本文件），否则 hints（每行一条），否则默认"""
        hints_file = self.config.get("hints_file", "").strip()
        if hints_file and os.path.isfile(hints_file):
            try:
                with open(hints_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    return lines
            except Exception as e:
                logging.warning(f"读取 hints 文件失败: {e}")
        hints = self.config.get("hints")
        if hints and isinstance(hints, list) and len(hints) > 0:
            return [str(h).strip() for h in hints if str(h).strip()]
        return ["介绍一下白居易", "讲个笑话", "今天天气怎么样", "介绍一下北京"]

    def run_broadcast_stress_test(self, progress_cb: Optional[Callable[[dict], None]] = None):
        """执行广播模式压力测试（可选 progress_cb 用于实时上报进度）"""
        hints = self._load_hints()
        interval_seconds = int(self.config.get("interval_seconds", 30))
        duration_hours = float(self.config.get("duration_hours", 12))
        broadcast_action = self.config.get("broadcast_action", "com.cei.llm.INPUT_HINT_TO_LLM")

        run_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        self._run_log_dir = os.path.join("logs", str(self.device.sn), run_ts)
        os.makedirs(self._run_log_dir, exist_ok=True)
        self.log_path = os.path.join(self._run_log_dir, "broadcast_stress.log")
        self.logcat_log_path = os.path.join(self._run_log_dir, "logcat_broadcast.log")
        perf_log_path = os.path.join(self._run_log_dir, "performance_sampling.jsonl")

        result = {
            "test_type": "broadcast_stress",
            "duration_hours": duration_hours,
            "start_time": datetime.now().isoformat(),
            "crashes": 0,
            "anrs": 0,
            "anr_events": [],  # ANR 事件列表，供实时报告展示
            "performance_data": [],
            "log_summary": {},
            "run_log_dir": self._run_log_dir,
            "hints_count": len(hints),
            "broadcasts_sent": 0,
            "response_monitoring": [],  # 响应监控结果列表
        }

        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"Broadcast Stress Test Start: {datetime.now()}\n")
            f.write(f"Duration: {duration_hours} hours\n")
            f.write(f"Package: {self.package.name}\n")
            f.write(f"Hints: {len(hints)} items\n")
            f.write("-" * 50 + "\n")

        # 注意：BroadcastStressTest 在 modular 模式下可能只拿到 broadcast_stress 子配置，
        # 这里尽力补齐全局 response_monitor，避免监控器使用默认匹配规则导致漏检。
        monitor_cfg = dict(self.config or {})
        if "response_monitor" not in monitor_cfg:
            try:
                cfg_path = os.path.join("conf", "test_ui_config.json")
                if os.path.exists(cfg_path):
                    import json as _json
                    with open(cfg_path, "r", encoding="utf-8") as _f:
                        _all = _json.load(_f) or {}
                    if isinstance(_all, dict) and isinstance(_all.get("response_monitor"), dict):
                        monitor_cfg["response_monitor"] = _all["response_monitor"]
            except Exception:
                pass

        monitor = StressMonitor(self.device, self.package, monitor_cfg)
        monitor._stop_monitor.clear()
        monitor._stop_logcat.clear()

        # 启动监控线程（每 2 秒采样 CPU/内存）
        monitor_thread = monitor.start_monitoring_thread(result, 2, perf_log_path)
        logcat_thread = monitor.start_logcat_capture(self.logcat_log_path)

        end_time = datetime.now() + timedelta(hours=duration_hours)
        start_time = datetime.now()
        hint_index = 0

        def _emit_progress():
            """向外部实时上报：尽量轻量，只包含报告所需字段。"""
            if not progress_cb:
                return
            try:
                partial = {
                    "test_type": result.get("test_type"),
                    "start_time": result.get("start_time"),
                    "run_log_dir": result.get("run_log_dir"),
                    "hints_count": result.get("hints_count"),
                    "broadcasts_sent": result.get("broadcasts_sent"),
                    "crashes": result.get("crashes", 0),
                    "anrs": result.get("anrs", 0),
                    "anr_events": list(result.get("anr_events") or []),
                    # 保留最新少量明细，避免无限增大影响实时更新开销
                    "response_monitoring": list((result.get("response_monitoring") or [])[-50:]),
                }
                progress_cb(partial)
            except Exception:
                # 进度回调不影响主流程
                pass

        try:
            while datetime.now() < end_time and not self._stop_event.is_set():
                hint = hints[hint_index % len(hints)]
                hint_index += 1
                hint_send_time = datetime.now()
                try:
                    # 发送广播（hint 需转义引号）
                    hint_escaped = hint.replace('"', '\\"')
                    cmd = f'adb -s {self.device.sn} shell am broadcast -a {broadcast_action} --es hint "{hint_escaped}"'
                    out = run_cmd(cmd, timeout=10)
                    result["broadcasts_sent"] += 1
                    # logging 已经带有 [%(asctime)s] 前缀，这里不再重复时间
                    log_msg = f"broadcast hint #{result['broadcasts_sent']}: {hint[:50]}..."
                    logging.info(log_msg)
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(log_msg + "\n")
                    if out and ("Error" in str(out) or "Exception" in str(out)):
                        logging.warning(f"广播命令可能失败: {out[:200]}")
                    
                    # 响应监控：参数从 config.response_monitor 读取
                    monitor_result = monitor.monitor_response(request_send_time=hint_send_time)
                    monitor_result['hint'] = hint
                    monitor_result['hint_index'] = result['broadcasts_sent']
                    monitor_result['send_time'] = hint_send_time.isoformat()
                    result['response_monitoring'].append(monitor_result)
                    
                    # 记录监控结果（仅在模型名称非空时输出“模型=XXX”）
                    model_name = monitor_result.get('model_name')
                    model_suffix = f", 模型={model_name}" if model_name else ""
                    if monitor_result['status'] == 'success':
                        logging.info(
                            f"[response-monitor] Hint #{result['broadcasts_sent']} 响应成功: "
                            f"响应时间={monitor_result.get('response_time', 0):.2f}秒, "
                            f"显示时长={monitor_result.get('display_duration', 0):.2f}秒"
                            f"{model_suffix}"
                        )
                    elif monitor_result['status'] == 'timeout_appear':
                        result['anrs'] += 1
                        result['anr_events'].append({
                            'hint_index': result['broadcasts_sent'],
                            'hint_preview': hint[:50],
                            'time': datetime.now().isoformat(),
                            'reason': monitor_result.get('error') or monitor_result['status'],
                        })
                        logging.warning(f"[response-monitor] Hint #{result['broadcasts_sent']} 无响应（ANR）")
                    else:
                        # timeout_disappear 或 error：同样计入 ANR 并记录事件
                        result['anrs'] += 1
                        result['anr_events'].append({
                            'hint_index': result['broadcasts_sent'],
                            'hint_preview': hint[:50],
                            'time': datetime.now().isoformat(),
                            'reason': monitor_result.get('error') or monitor_result['status'],
                        })
                        logging.warning(f"[response-monitor] Hint #{result['broadcasts_sent']} 监控异常: {monitor_result.get('error', 'unknown')}")
                    
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        line = (
                            f"  [响应监控] 状态={monitor_result['status']}, "
                            f"响应时间={monitor_result.get('response_time', 'N/A')}, "
                            f"显示时长={monitor_result.get('display_duration', 'N/A')}"
                        )
                        if model_name:
                            line += f", 模型={model_name}"
                        f.write(line + "\n")

                    # 检测到 ANR/error 后立即恢复：杀进程、重启前台、等待 10 秒
                    if monitor_result['status'] == 'success':
                        self._consecutive_no_response = 0
                    elif monitor_result['status'] in ('timeout_appear', 'timeout_disappear', 'error'):
                        self._consecutive_no_response += 1
                        self._restart_service_and_wait()
                        self._consecutive_no_response = 0

                    # 每条 hint 完成后实时上报进度（含 ANR 次数/事件列表）
                    _emit_progress()
                    
                    # 超时或异常时跳过当前 hint，短等待后继续下一条；成功则按剩余间隔等待
                    if monitor_result['status'] == 'success' and monitor_result.get('disappear_time'):
                        remaining_wait = max(0, interval_seconds - (datetime.now() - hint_send_time).total_seconds())
                        if remaining_wait > 0:
                            time.sleep(min(remaining_wait, interval_seconds))
                    else:
                        time.sleep(1)
                except Exception as e:
                    logging.warning(f"发送广播失败: {e}")
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(f"ERROR: {e}\n")
                    _emit_progress()
                    # 发生异常时也等待间隔时间
                    for _ in range(interval_seconds):
                        if self._stop_event.is_set() or datetime.now() >= end_time:
                            break
                        time.sleep(1)
        except Exception as e:
            logging.error(f"广播压力测试异常: {e}")
            result["error"] = str(e)
        finally:
            monitor.stop()
            if logcat_thread:
                logcat_thread.join(timeout=5)
            monitor_thread.join(timeout=10)

        result["actual_end_time"] = datetime.now().isoformat()
        end_time = datetime.now()
        crash_anr = monitor.analyze_logcat_for_crashes_anrs(start_time, end_time)
        result["crashes"] = crash_anr["crashes"]
        result["anrs"] = crash_anr["anrs"]
        # 将异常日志单独落盘
        exc_path = os.path.join(self._run_log_dir, "exceptions.log")
        StressMonitor.extract_exceptions_to_file(
            self.logcat_log_path, exc_path, start_time, end_time,
            self.package.name
        )
        logging.info(f"广播压力测试完成，发送 {result['broadcasts_sent']} 条，崩溃 {result['crashes']}，ANR {result['anrs']}")
        return result
