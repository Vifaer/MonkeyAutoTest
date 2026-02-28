#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
TTS 模式压力测试
PC 端通过 pyttsx3 将配置文本转为语音并播放，设备麦克风接收后触发应用响应
"""

import os
import sys
import time
import logging
import threading
import subprocess
import base64
from typing import Callable, Optional
from datetime import datetime, timedelta

from utils.timeout_command import run as run_cmd
from utils.stress_monitor import StressMonitor


def _play_tts_via_subprocess(text: str, timeout: int = 60) -> bool:
    """
    在独立子进程中执行 TTS 播放，每次调用使用全新引擎，避免 pyttsx3 在 Windows 上
    复用引擎导致后续播放无声音的问题。
    """
    try:
        # 使用 base64 避免引号/换行等特殊字符导致命令行解析错误
        text_b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        code = f"""
import base64
import pyttsx3
text = base64.b64decode({repr(text_b64)}).decode('utf-8')
engine = pyttsx3.init()
engine.say(text)
engine.runAndWait()
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logging.warning(f"TTS 子进程退出码 {result.returncode}: {result.stderr[:200] if result.stderr else ''}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logging.warning("TTS 子进程超时")
        return False
    except Exception as e:
        logging.warning(f"TTS 子进程异常: {e}")
        return False


class TTSStressTest:
    """TTS 模式压力测试：PC 端播放语音，设备麦克风接收，监控前台与资源"""

    def __init__(self, device, package, config):
        self.device = device
        self.package = package
        self.config = config
        self._stop_event = threading.Event()
        self._run_log_dir = os.path.join("logs", str(device.sn))
        self.log_path = ""
        self.logcat_log_path = ""
        # 连续无响应计数与自动恢复阈值（0 表示禁用自动恢复）
        rm_cfg = (config or {}).get("response_monitor") or {}
        try:
            raw = rm_cfg.get("anr_recover_threshold", 1)
            if raw is None or raw == "":
                raw = 1
            threshold = int(float(raw))
        except Exception:
            # 非法配置时退回默认 1（保留原有“1 次即重拉”的默认行为）
            threshold = 1
        if threshold < 0:
            threshold = 0  # 允许 0 表示禁用自动恢复
        self.anr_recover_threshold = threshold
        self._consecutive_no_response = 0
        logging.info("[response-monitor] anr_recover_threshold=%s (0=仅记录ANR不自动恢复)", self.anr_recover_threshold)

        # TTS 前后缀：结束词 / 唤醒词 及唤醒后等待时间（秒）
        cfg = config or {}
        try:
            self.end_phrase = (cfg.get("end_phrase") or "").strip()
        except Exception:
            self.end_phrase = ""
        try:
            self.wake_phrase = (cfg.get("wake_phrase") or "").strip()
        except Exception:
            self.wake_phrase = ""
        try:
            raw_delay = cfg.get("wake_delay_seconds", 2)
            if raw_delay is None or raw_delay == "":
                raw_delay = 2
            self.wake_delay = float(raw_delay)
        except Exception:
            self.wake_delay = 2.0
        if self.wake_delay < 0:
            self.wake_delay = 0.0

    def _load_texts(self):
        """加载语音文本列表：优先 texts_file（文本文件），否则 texts（每行一条），否则默认"""
        texts_file = self.config.get("texts_file", "").strip()
        if texts_file and os.path.isfile(texts_file):
            try:
                with open(texts_file, "r", encoding="utf-8", errors="replace") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    return lines
            except Exception as e:
                logging.warning(f"读取 texts 文件失败: {e}")
        texts = self.config.get("texts")
        if texts and isinstance(texts, list) and len(texts) > 0:
            return [str(t).strip() for t in texts if str(t).strip()]
        return ["打开设置", "介绍一下北京", "今天天气怎么样", "讲个笑话"]

    def _play_tts(self, text: str) -> bool:
        """
        使用 pyttsx3 播放文本语音。
        默认通过独立子进程执行，每次调用使用全新引擎，确保 Windows 下持续、稳定播放。
        """
        return _play_tts_via_subprocess(text)

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

    def run_tts_stress_test(self, progress_cb: Optional[Callable[[dict], None]] = None):
        """执行 TTS 模式压力测试（可选 progress_cb 用于实时上报进度）"""
        texts = self._load_texts()
        interval_seconds = int(self.config.get("interval_seconds", 30))
        duration_hours = float(self.config.get("duration_hours", 12))

        run_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        self._run_log_dir = os.path.join("logs", str(self.device.sn), run_ts)
        os.makedirs(self._run_log_dir, exist_ok=True)
        self.log_path = os.path.join(self._run_log_dir, "tts_stress.log")
        self.logcat_log_path = os.path.join(self._run_log_dir, "logcat_tts.log")
        perf_log_path = os.path.join(self._run_log_dir, "performance_sampling.jsonl")

        result = {
            "test_type": "tts_stress",
            "duration_hours": duration_hours,
            "start_time": datetime.now().isoformat(),
            "crashes": 0,
            "anrs": 0,
            "anr_events": [],  # ANR 事件列表，供实时报告展示
            "performance_data": [],
            "log_summary": {},
            "run_log_dir": self._run_log_dir,
            "texts_count": len(texts),
            "tts_played": 0,
            "response_monitoring": [],  # 响应监控结果列表
        }

        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write(f"TTS Stress Test Start: {datetime.now()}\n")
            f.write(f"Duration: {duration_hours} hours\n")
            f.write(f"Package: {self.package.name}\n")
            f.write(f"Texts: {len(texts)} items\n")
            f.write("-" * 50 + "\n")

        monitor = StressMonitor(self.device, self.package, self.config)
        monitor._stop_monitor.clear()
        monitor._stop_logcat.clear()

        monitor_thread = monitor.start_monitoring_thread(result, 2, perf_log_path)
        logcat_thread = monitor.start_logcat_capture(self.logcat_log_path)
        # 监控设备异常目录（/data/anr, /data/tombstones）
        try:
            monitor.start_exception_file_monitor(self._run_log_dir)
        except Exception:
            pass

        end_time = datetime.now() + timedelta(hours=duration_hours)
        start_time = datetime.now()
        text_index = 0

        def _emit_progress():
            if not progress_cb:
                return
            try:
                partial = {
                    "test_type": result.get("test_type"),
                    "start_time": result.get("start_time"),
                    "run_log_dir": result.get("run_log_dir"),
                    "texts_count": result.get("texts_count"),
                    "tts_played": result.get("tts_played"),
                    "crashes": result.get("crashes", 0),
                    "anrs": result.get("anrs", 0),
                    "anr_events": list(result.get("anr_events") or []),
                    "response_monitoring": list((result.get("response_monitoring") or [])[-50:]),
                }
                progress_cb(partial)
            except Exception:
                pass

        tts_available = True
        try:
            import pyttsx3  # noqa: F401
        except ImportError:
            tts_available = False
            logging.warning("未安装 pyttsx3，TTS 播放将跳过，请执行: pip install pyttsx3")

        # 响应监控是否启用（检测"由XXX模型生成"文本，适用于特定 LLM 应用）
        response_monitor_enabled = (self.config.get('response_monitor') or {}).get('enabled', False)

        try:
            while datetime.now() < end_time and not self._stop_event.is_set():
                text = texts[text_index % len(texts)]
                text_index += 1
                text_send_time = datetime.now()
                try:
                    # 每条主测试文本前按需插入结束词和唤醒词
                    if tts_available:
                        try:
                            if getattr(self, "end_phrase", ""):
                                if self._play_tts(self.end_phrase):
                                    msg = f"[TTS] 播放结束词: {self.end_phrase[:50]}"
                                    logging.info(msg)
                                    with open(self.log_path, "a", encoding="utf-8") as f:
                                        f.write(msg + "\n")
                                time.sleep(0.3)
                        except Exception as _e:
                            logging.debug(f"TTS 结束词播放异常: {_e}")
                        try:
                            if getattr(self, "wake_phrase", ""):
                                if self._play_tts(self.wake_phrase):
                                    msg = f"[TTS] 播放唤醒词: {self.wake_phrase[:50]}"
                                    logging.info(msg)
                                    with open(self.log_path, "a", encoding="utf-8") as f:
                                        f.write(msg + "\n")
                                delay = float(getattr(self, "wake_delay", 2.0) or 0.0)
                                if delay > 0:
                                    time.sleep(delay)
                        except Exception as _e:
                            logging.debug(f"TTS 唤醒词播放异常: {_e}")

                    if tts_available and self._play_tts(text):
                        result["tts_played"] += 1
                        # logging 已带 [时间] 前缀，这里只保留业务信息
                        log_msg = f"TTS #{result['tts_played']}: {text[:50]}..."
                        logging.info(log_msg)
                        with open(self.log_path, "a", encoding="utf-8") as f:
                            f.write(log_msg + "\n")
                        
                        if response_monitor_enabled:
                            # 响应监控：检测"由XXX模型生成"等 UI 文本（仅当 config.response_monitor.enabled=True 时启用）
                            monitor_result = monitor.monitor_response(request_send_time=text_send_time)
                            monitor_result['text'] = text
                            monitor_result['text_index'] = result['tts_played']
                            monitor_result['send_time'] = text_send_time.isoformat()
                            result['response_monitoring'].append(monitor_result)
                            
                            model_name = monitor_result.get('model_name')
                            model_suffix = f", 模型={model_name}" if model_name else ""
                            if monitor_result['status'] == 'success':
                                logging.info(
                                    f"[response-monitor] TTS #{result['tts_played']} 响应成功: "
                                    f"响应时间={monitor_result.get('response_time', 0):.2f}秒, "
                                    f"显示时长={monitor_result.get('display_duration', 0):.2f}秒"
                                    f"{model_suffix}"
                                )
                            elif self.anr_recover_threshold == 0:
                                # 阈值=0：仅记录到 response_monitoring，不计 ANR，不自动恢复，直接下一条
                                status = monitor_result['status']
                                err_msg = monitor_result.get('error') or status
                                logging.warning(
                                    "[response-monitor] TTS #%d 无响应（%s，已跳过；阈值=0 不统计 ANR）",
                                    result['tts_played'], err_msg
                                )
                                rm_cfg = (self.config or {}).get('response_monitor') or {}
                                logging.info(
                                    "[response-monitor] 超时明细: text_index=%s, status=%s, error=%s, "
                                    "max_wait_appear=%s, max_wait_disappear=%s, check_interval=%s",
                                    result['tts_played'], status, err_msg,
                                    rm_cfg.get('max_wait_for_appear'), rm_cfg.get('max_wait_for_disappear'),
                                    rm_cfg.get('check_interval')
                                )
                            elif monitor_result['status'] == 'timeout_appear':
                                result['anrs'] += 1
                                result['anr_events'].append({
                                    'text_index': result['tts_played'],
                                    'text_preview': text[:50],
                                    'time': datetime.now().isoformat(),
                                    'reason': monitor_result.get('error') or monitor_result['status'],
                                })
                                logging.warning(f"[response-monitor] TTS #{result['tts_played']} 无响应（ANR）")
                                rm_cfg = (self.config or {}).get('response_monitor') or {}
                                logging.info(
                                    "[response-monitor] 超时明细: text_index=%s, status=timeout_appear, error=%s, "
                                    "max_wait_appear=%s, max_wait_disappear=%s, check_interval=%s",
                                    result['tts_played'], monitor_result.get('error'),
                                    rm_cfg.get('max_wait_for_appear'), rm_cfg.get('max_wait_for_disappear'),
                                    rm_cfg.get('check_interval')
                                )
                            else:
                                result['anrs'] += 1
                                result['anr_events'].append({
                                    'text_index': result['tts_played'],
                                    'text_preview': text[:50],
                                    'time': datetime.now().isoformat(),
                                    'reason': monitor_result.get('error') or monitor_result['status'],
                                })
                                logging.warning(f"[response-monitor] TTS #{result['tts_played']} 监控异常: {monitor_result.get('error', 'unknown')}")
                                rm_cfg = (self.config or {}).get('response_monitor') or {}
                                logging.info(
                                    "[response-monitor] 超时明细: text_index=%s, status=%s, error=%s, "
                                    "max_wait_appear=%s, max_wait_disappear=%s, check_interval=%s",
                                    result['tts_played'], monitor_result.get('status'), monitor_result.get('error'),
                                    rm_cfg.get('max_wait_for_appear'), rm_cfg.get('max_wait_for_disappear'),
                                    rm_cfg.get('check_interval')
                                )
                            
                            with open(self.log_path, "a", encoding="utf-8") as f:
                                line = (
                                    f"  [响应监控] 状态={monitor_result['status']}, "
                                    f"响应时间={monitor_result.get('response_time', 'N/A')}, "
                                    f"显示时长={monitor_result.get('display_duration', 'N/A')}"
                                )
                                if model_name:
                                    line += f", 模型={model_name}"
                                f.write(line + "\n")

                            # 检测到 ANR/error 后按阈值决定是否自动恢复（阈值=0 不恢复、不计数）
                            if monitor_result['status'] == 'success':
                                self._consecutive_no_response = 0
                            elif monitor_result['status'] in ('timeout_appear', 'timeout_disappear', 'error'):
                                if self.anr_recover_threshold > 0:
                                    self._consecutive_no_response += 1
                                    if self._consecutive_no_response >= self.anr_recover_threshold:
                                        self._restart_service_and_wait()
                                        self._consecutive_no_response = 0

                            _emit_progress()
                            
                            # 超时或异常时跳过当前条，短等待后继续；成功则按剩余间隔等待
                            if monitor_result['status'] == 'success' and monitor_result.get('disappear_time'):
                                remaining_wait = max(0, interval_seconds - (datetime.now() - text_send_time).total_seconds())
                                if remaining_wait > 0:
                                    time.sleep(min(remaining_wait, interval_seconds))
                            else:
                                time.sleep(1)
                        else:
                            # 未启用响应监控：按间隔等待后执行下一条
                            for _ in range(interval_seconds):
                                if self._stop_event.is_set() or datetime.now() >= end_time:
                                    break
                                time.sleep(1)
                            _emit_progress()
                    else:
                        # 播放失败，等待间隔后重试下一条
                        for _ in range(interval_seconds):
                            if self._stop_event.is_set() or datetime.now() >= end_time:
                                break
                            time.sleep(1)
                        _emit_progress()
                except Exception as e:
                    logging.warning(f"TTS 播放异常: {e}")
                    with open(self.log_path, "a", encoding="utf-8") as f:
                        f.write(f"ERROR: {e}\n")
                    _emit_progress()
                    # 发生异常时也等待间隔时间
                    for _ in range(interval_seconds):
                        if self._stop_event.is_set() or datetime.now() >= end_time:
                            break
                        time.sleep(1)
        except Exception as e:
            logging.error(f"TTS 压力测试异常: {e}")
            result["error"] = str(e)
        finally:
            monitor.stop()
            if logcat_thread:
                logcat_thread.join(timeout=5)
            monitor_thread.join(timeout=10)

        # 若捕获到设备侧 ANR/tombstone，则在结束时导出 bugreport（可选失败，不影响主流程）
        try:
            monitor.maybe_collect_bugreport(self._run_log_dir, reason="test_end")
        except Exception as e:
            logging.warning("导出 bugreport 失败（可忽略）: %s", e)

        result["actual_end_time"] = datetime.now().isoformat()
        end_time = datetime.now()
        crash_anr = monitor.analyze_logcat_for_crashes_anrs(start_time, end_time)
        result["crashes"] = crash_anr["crashes"]
        result["anrs"] = crash_anr["anrs"]
        # 异常日志已通过稳定性总控周期性写入 app.log，此处不再单独生成 exceptions.log
        logging.info(f"TTS 压力测试完成，播放 {result['tts_played']} 条，崩溃 {result['crashes']}，ANR {result['anrs']}")
        return result
