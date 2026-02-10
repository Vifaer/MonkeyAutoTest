#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import statistics
import os
import threading
from datetime import datetime
from utils.timeout_command import run as run_cmd
import re
import hashlib
import xml.etree.ElementTree as ET


class PerformanceMonitor:
    """
    性能监控类
    监控应用启动时间、响应延迟、CPU使用率、内存使用率等指标
    """

    def __init__(self, device, package, config):
        self.device = device
        self.package = package
        self.config = config
        # 记录上次点击的元素，确保每次点击与上一次不同
        self._last_clicked_element = None

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

        run_ts = datetime.now().strftime("%Y%m%d%H%M%S")
        run_log_dir = os.path.join("logs", str(self.device.sn), run_ts)
        os.makedirs(run_log_dir, exist_ok=True)
        logcat_log_path = os.path.join(run_log_dir, "logcat_performance.log")

        results = {
            'test_type': 'performance',
            'start_time': datetime.now().isoformat(),
            'max_duration_seconds': max_duration_seconds,
            'run_log_dir': run_log_dir,
            'tests': {}
        }
        
        from utils.stress_monitor import StressMonitor
        monitor = StressMonitor(self.device, self.package, self.config)
        monitor._stop_logcat.clear()
        logcat_thread = monitor.start_logcat_capture(logcat_log_path)
        
        try:
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

            # 资源消耗监控：改为在长压/稳定性测试过程中并行采集，不再单独跑独立测试
            logging.info("资源消耗监控已与压力/稳定性测试并行采集，性能测试阶段不单独运行")
            results['tests']['resource_usage'] = {
                'skipped': True,
                'reason': 'monitored_in_stress',
                'note': 'CPU/内存监控在压力/稳定性测试线程并行采样，不在性能测试中单独执行'
            }

            results['end_time'] = datetime.now().isoformat()
            results['actual_duration_seconds'] = time.time() - test_start_time
        finally:
            monitor.stop()
            if logcat_thread:
                logcat_thread.join(timeout=5)

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
            'detailed_measurements': [],  # 详细测量数据（包含超时标记等）
            'average_delay': 0,
            'min_delay': 0,
            'max_delay': 0,
            'standard_deviation': 0,
            'pass_rate': 0.0,
            'target_threshold': 1.5,  # 1.5秒
            'timeout_count': 0,  # 超时次数
            'total_tests': 0  # 总测试次数
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
            delay_data = self._measure_response_delay_with_details()

            if delay_data and delay_data.get('delay') is not None:
                delay = delay_data['delay']
                result['measurements'].append(delay)
                result['detailed_measurements'].append(delay_data)
                result['total_tests'] += 1
                
                if delay_data.get('is_timeout', False):
                    result['timeout_count'] += 1
                    logging.info(f"本次响应延迟: {delay:.2f}s (超时)")
                else:
                    logging.info(f"本次响应延迟: {delay:.2f}s (正常完成，UI稳定时长: {delay_data.get('stable_duration', 0):.2f}s)")
            else:
                logging.warning(f"第 {i + 1} 次响应延迟测试失败")
                result['measurements'].append(None)
                result['detailed_measurements'].append(None)

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

            logging.info(f"响应延迟测试完成 - 平均: {result['average_delay']:.2f}s, 达标率: {result['pass_rate']:.1%}, "
                        f"超时次数: {result['timeout_count']}/{result['total_tests']}")

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
                m = re.search(r"([a-zA-Z0-9._]+)/([a-zA-Z0-9_.$]+)", cand)
                if m:
                    pkg_part, act_part = m.group(1).strip(), m.group(2).strip()
                    # 确保 activity 非空，避免 "Bad component name: pkg/"
                    if pkg_part and act_part:
                        launcher_component = f"{pkg_part}/{act_part}"
                        break
        except Exception as e:
            logging.debug(f"解析 LAUNCHER Activity 失败，退回包内配置: {e}")

        if not launcher_component:
            # 兜底：使用 Package 提供的 activity（可能来自 aapt 或手工配置）
            activity = getattr(self.package, "activity", "") or ""
            if activity:
                launcher_component = f"{self.package.name}/{activity}"
            else:
                # activity 为空时避免 "Bad component name: pkg/" 错误，改用 MAIN/LAUNCHER
                launcher_component = None

        if launcher_component:
            cmd = f"adb -s {self.device.sn} shell am start -W -n {launcher_component}"
        else:
            cmd = (f"adb -s {self.device.sn} shell am start -W "
                   f"-a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {self.package.name}")
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
        测量响应延迟（兼容旧接口，返回延迟值）
        
        流程：
        1. 记录点击开始时间
        2. 触发数据请求（点击元素）
        3. 监控UI变化直到页面加载完成
        4. 返回响应延迟数据
        """
        delay_data = self._measure_response_delay_with_details()
        if delay_data and delay_data.get('delay') is not None:
            return delay_data['delay']
        return None

    def _measure_response_delay_with_details(self):
        """
        测量响应延迟（返回详细数据）
        
        流程：
        1. 获取点击前的基准UI快照
        2. 记录点击开始时间
        3. 触发数据请求（点击元素）
        4. 等待一小段时间让UI开始响应
        5. 监控UI变化直到页面加载完成
        6. 返回详细的响应延迟数据
        
        Returns:
            dict: {
                'delay': float,  # 响应延迟（秒）
                'click_start_time': float,  # 点击开始时间（时间戳）
                'last_change_time': float,  # 最后一次UI变化时间（时间戳）
                'response_time': float,  # 响应完成时间（时间戳）
                'is_timeout': bool,  # 是否超时
                'stable_duration': float  # UI稳定持续时间（秒）
            } 或 None
        """
        # 步骤1：点击前立即获取基准UI快照（越贴近点击越好）
        baseline_ui_hash = None
        baseline_major_hash = None
        dynamic_ignore_keys = set()
        try:
            # 先短时间采样“背景动态节点”（轮播/实时数据等），用于后续比对过滤
            dynamic_ignore_keys = self._learn_dynamic_ui_keys(sample_count=6, interval=0.2, timeout=3)

            snap = self._capture_ui_snapshot(timeout=5)
            baseline_ui = snap.get("xml") if snap else None
            if baseline_ui:
                baseline_ui_hash = hashlib.md5(baseline_ui.encode('utf-8', errors='ignore')).hexdigest()
                baseline_major_hash, _ = self._ui_snapshot_signatures(baseline_ui, ignore_keys=dynamic_ignore_keys)
                if not baseline_major_hash:
                    baseline_major_hash = baseline_ui_hash
                logging.debug(
                    f"获取点击前基准UI快照（method={snap.get('method')}, "
                    f"dur={snap.get('duration', 0):.3f}s, major={baseline_major_hash[:8]}..., "
                    f"dyn_ignore={len(dynamic_ignore_keys)}）"
                )
        except Exception as e:
            logging.warning(f"获取点击前基准UI快照失败: {e}")

        # 步骤2：记录点击开始时间（用于兼容字段）
        click_start_time = time.time()

        # 步骤3：触发数据请求（点击元素）；点击完成后再记录时刻
        self._trigger_data_request()
        click_executed_time = time.time()

        # 步骤4：立即开始监控（不等待，确保能捕获最快的UI变化）
        # 步骤5：等待响应完成（基于UI变化检测，传入 major 签名；以 click_executed_time 为延迟起点）
        response_data = self._wait_for_response(
            click_start_time, baseline_ui_hash, click_executed_time,
            baseline_major_hash=baseline_major_hash,
            dynamic_ignore_keys=dynamic_ignore_keys
        )

        if response_data and response_data.get('delay') is not None:
            # 添加点击开始时间到返回数据
            response_data['click_start_time'] = click_start_time
            
            # 记录详细信息
            if response_data.get('is_timeout'):
                logging.warning(f"响应延迟检测超时，延迟: {response_data['delay']:.3f}秒（最后一次UI变化时间）")
            else:
                logging.debug(f"响应延迟: {response_data['delay']:.3f}秒，UI稳定时长: {response_data.get('stable_duration', 0):.3f}秒")
            
            return response_data
        else:
            logging.warning("响应延迟检测失败，无法获取有效数据")
            return None

    # ===== 响应延迟：更精准的“首次稳定”检测（过滤轮询/轮播等周期性微变化） =====
    def _ui_snapshot_signatures(self, ui_xml: str, ignore_keys=None):
        """
        从 uiautomator dump 的 XML 中提取两个层级的签名：
        - major：结构性签名，用于判定“显著变化”；过滤动态控件（轮播/进度条/计时器等）的瞬时出现与消失，减少误判。
        - minor：包含归一化后的文本（时间戳/数字/计数等已脱敏），用于辅助调试，不参与稳定判定。

        动态内容过滤：时间、日期、纯数字、bounds 不参与 major；minor 中数字/时间格式统一为占位符。
        """
        if not ui_xml:
            return "", ""

        lt = ui_xml.find("<")
        if lt > 0:
            ui_xml = ui_xml[lt:]

        def _norm_text(s: str) -> str:
            if not s:
                return ""
            s = s.strip()
            s = re.sub(r"\s+", " ", s)
            # 数字整体替换为占位符
            s = re.sub(r"\d+", "#", s)
            # 时间格式 HH:MM 或 HH:MM:SS -> #:#
            s = re.sub(r"#:#(#)?", "#:#", s)
            # 日期格式 YYYY-MM-DD 等已因数字替换变为 #-#-#，可再归一
            s = re.sub(r"#-#-#(-#)*", "#-#", s)
            return s

        # 仅用于 major：视为“动态/瞬时”的 class 片段，出现时该 node 不参与 major，避免进度条/计时器导致频繁变化（不排除 ViewPager/AdapterView，以保留真实页面内容变化）
        _transient_class_pattern = re.compile(
            r"ProgressBar|LoadingIndicator|Chronometer|Timer|Marquee|ViewFlipper",
            re.I
        )

        try:
            root = ET.fromstring(ui_xml)
        except Exception:
            h = hashlib.md5(ui_xml.encode("utf-8", errors="ignore")).hexdigest()
            return h, h

        major_tokens = []
        minor_tokens = []

        ignore_keys = ignore_keys or set()
        for node in root.iter():
            tag = (node.tag or "").lower()
            if tag == "hierarchy":
                continue
            if tag != "node":
                continue

            cls = node.get("class", "")
            rid = node.get("resource-id", "")
            pkg = node.get("package", "")
            clickable = node.get("clickable", "")
            enabled = node.get("enabled", "")

            # 动态区域过滤：点击前学习得到的“背景动态节点”
            node_key = self._node_key(pkg=pkg, cls=cls, rid=rid)
            if node_key and node_key in ignore_keys:
                continue

            # major：结构性字段；排除纯动态控件（轮播、进度条等），避免其出现/消失造成误判“显著变化”
            if _transient_class_pattern.search(cls):
                continue
            major_tokens.append(f"{pkg}|{cls}|{rid}|c={clickable}|e={enabled}")

            # minor：归一化文本，用于调试
            txt = _norm_text(node.get("text", ""))
            desc = _norm_text(node.get("content-desc", ""))
            if txt or desc:
                minor_tokens.append(f"{pkg}|{cls}|{rid}|t={txt}|d={desc}")

        major_tokens.sort()
        minor_tokens.sort()
        major_blob = "\n".join(major_tokens)
        minor_blob = "\n".join(minor_tokens)

        major_hash = hashlib.md5(major_blob.encode("utf-8", errors="ignore")).hexdigest()
        minor_hash = hashlib.md5(minor_blob.encode("utf-8", errors="ignore")).hexdigest()
        return major_hash, minor_hash

    def _node_key(self, pkg: str, cls: str, rid: str) -> str:
        """
        生成用于过滤的节点 key。优先使用 resource-id；为空时返回空串（避免把大量无 id 节点误当作动态区）。
        """
        rid = (rid or "").strip()
        if not rid:
            return ""
        return f"{pkg}|{cls}|{rid}"

    def _extract_node_keys(self, ui_xml: str):
        """
        从 UI XML 中抽取可用于动态过滤的 node keys（仅含 resource-id 的节点）。
        """
        if not ui_xml:
            return set()
        lt = ui_xml.find("<")
        if lt > 0:
            ui_xml = ui_xml[lt:]
        try:
            root = ET.fromstring(ui_xml)
        except Exception:
            return set()

        keys = set()
        for node in root.iter():
            if (node.tag or "").lower() != "node":
                continue
            pkg = node.get("package", "")
            cls = node.get("class", "")
            rid = node.get("resource-id", "")
            k = self._node_key(pkg=pkg, cls=cls, rid=rid)
            if k:
                keys.add(k)
        return keys

    def _learn_dynamic_ui_keys(self, sample_count=6, interval=0.2, timeout=3):
        """
        点击前短时采样 UI，学习“背景动态节点”（resource-id 级别）。
        规则：在 sample_count 次采样中出现次数既不是 0 也不是 sample_count 的 key，视为动态。
        """
        start = time.time()
        seen_counts = {}
        for _ in range(max(2, int(sample_count))):
            if time.time() - start > timeout:
                break
            snap = self._capture_ui_snapshot(timeout=3)
            xml = snap.get("xml") if snap else None
            keys = self._extract_node_keys(xml)
            for k in keys:
                seen_counts[k] = seen_counts.get(k, 0) + 1
            time.sleep(max(0.05, float(interval)))

        total = max(1, min(int(sample_count), sum(1 for _ in range(1))))  # 仅用于边界保护
        # 注意：真实采样次数可能因 timeout 缩短，这里用 seen_counts 的最大计数近似
        if seen_counts:
            total = max(seen_counts.values())

        dynamic = {k for k, c in seen_counts.items() if 0 < c < total}
        return dynamic

    def _capture_ui_snapshot(self, timeout=3):
        """
        获取 UI XML 快照（优先使用 exec-out 直出，避免 dump 到文件再 cat 的额外耗时）。

        Returns:
            dict: {
              'xml': str|None,
              'start': float,
              'end': float,
              'duration': float,
              'method': 'exec-out'|'file'
            }
        """
        start = time.time()
        # 方法1：exec-out 直出（通常更快）
        try:
            cmd = f"adb -s {self.device.sn} exec-out uiautomator dump /dev/tty"
            out = run_cmd(cmd, timeout=timeout)
            end = time.time()
            if isinstance(out, str) and "<hierarchy" in out:
                # 可能包含提示行，截取第一个 '<'
                lt = out.find("<")
                if lt > 0:
                    out = out[lt:]
                return {
                    "xml": out,
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "method": "exec-out",
                }
        except Exception:
            pass

        # 方法2：落盘再读取（兼容旧设备/旧 adb）
        try:
            cmd = f"adb -s {self.device.sn} shell uiautomator dump /sdcard/ui_snapshot.xml"
            run_cmd(cmd, timeout=timeout)
            cmd = f"adb -s {self.device.sn} shell cat /sdcard/ui_snapshot.xml"
            out = run_cmd(cmd, timeout=timeout)
            end = time.time()
            if isinstance(out, str) and out.strip():
                return {
                    "xml": out,
                    "start": start,
                    "end": end,
                    "duration": end - start,
                    "method": "file",
                }
        except Exception:
            end = time.time()
            return {"xml": None, "start": start, "end": end, "duration": end - start, "method": "file"}

        end = time.time()
        return {"xml": None, "start": start, "end": end, "duration": end - start, "method": "unknown"}

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
        activity = getattr(self.package, "activity", "") or ""
        if activity:
            cmd = f"adb -s {self.device.sn} shell am start -n {self.package.name}/{activity}"
        else:
            cmd = (f"adb -s {self.device.sn} shell am start "
                   f"-a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {self.package.name}")
        run_cmd(cmd)

    def _move_app_to_background(self):
        """将应用置于后台"""
        cmd = f"adb -s {self.device.sn} shell input keyevent KEYCODE_HOME"
        run_cmd(cmd)

    def _trigger_data_request(self):
        """
        触发数据请求：点击页面中的可点击元素
        
        可点击元素列表从配置中读取（GUI可配置），
        每次点击会选择与上一次不同的元素。
        """
        import random
        import xml.etree.ElementTree as ET
        
        # 从配置中读取可点击元素列表（GUI可配置）
        clickable_elements = self.config.get('clickable_elements', ["AI Power", "智能体广场", "对话收藏"])
        
        # 如果配置中是字符串（逗号分隔），则解析为列表
        if isinstance(clickable_elements, str):
            clickable_elements = [e.strip() for e in clickable_elements.split(',') if e.strip()]
        
        # 确保是列表且不为空
        if not isinstance(clickable_elements, list) or len(clickable_elements) == 0:
            clickable_elements = ["AI Power", "智能体广场", "对话收藏"]
            logging.warning("可点击元素配置无效，使用默认值")
        
        # 如果只有一个元素，直接使用
        if len(clickable_elements) == 1:
            target_element = clickable_elements[0]
        else:
            # 确保每次点击与上一次不同
            available_elements = [e for e in clickable_elements if e != self._last_clicked_element]
            if not available_elements:
                # 如果所有元素都被点击过（理论上不应该发生），则重置
                available_elements = clickable_elements
                logging.debug("所有元素都已点击过，重置选择")
            
            target_element = random.choice(available_elements)
        
        # 记录本次点击的元素
        self._last_clicked_element = target_element
        
        logging.debug(f"尝试点击元素: {target_element}")
        
        # 获取UI层次结构
        cmd = f"adb -s {self.device.sn} shell uiautomator dump /sdcard/ui_dump.xml"
        result = run_cmd(cmd, timeout=5)
        
        if result is None:
            logging.warning("无法获取UI层次结构，使用备用方法")
            return
        
        # 读取UI dump文件
        cmd = f"adb -s {self.device.sn} shell cat /sdcard/ui_dump.xml"
        ui_xml = run_cmd(cmd, timeout=5)
        
        if not ui_xml:
            logging.warning("无法读取UI dump文件")
            return
        
        try:
            # 解析XML
            root = ET.fromstring(ui_xml)
            
            # 查找包含目标文本的可点击元素
            found = False
            for node in root.iter():
                # 检查文本内容
                text = node.get('text', '')
                content_desc = node.get('content-desc', '')
                clickable = node.get('clickable', 'false')
                bounds = node.get('bounds', '')
                
                # 检查是否匹配目标元素且可点击
                if (target_element in text or target_element in content_desc) and clickable == 'true' and bounds:
                    # 解析bounds获取中心点坐标
                    # bounds格式: [x1,y1][x2,y2]
                    import re
                    match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                    if match:
                        x1, y1, x2, y2 = map(int, match.groups())
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        
                        # 点击元素中心点
                        cmd = f"adb -s {self.device.sn} shell input tap {center_x} {center_y}"
                        run_cmd(cmd, timeout=3)
                        logging.info(f"已点击元素 '{target_element}' (坐标: {center_x}, {center_y})")
                        found = True
                        break
            
            if not found:
                logging.warning(f"未找到可点击元素 '{target_element}'，尝试使用文本搜索")
                # 备用方案：使用文本搜索（可能不够精确）
                # 这里可以添加更复杂的搜索逻辑
                
        except Exception as e:
            logging.warning(f"解析UI dump失败: {e}，使用备用点击方法")
            # 备用方案：如果解析失败，可以尝试使用坐标点击（需要预先知道元素位置）

    def _wait_for_response(self, click_start_time, baseline_ui_hash=None, click_executed_time=None,
                           baseline_major_hash=None, dynamic_ignore_keys=None):
        """
        等待响应完成：基于UI变化的页面加载完成检测机制（优化版）

        检测策略：
        1. 使用 baseline_major 签名比对，仅判定“显著变化”，过滤轮播/时间戳/计数器等动态内容。
        2. 点击后高频检测（0.05s 间隔）快速捕获首次变化，随后 0.2s 间隔；延迟以“快照开始时刻”计，避免把 dump/cat 耗时算入。
        3. “首次稳定”窗口（默认 0.5s）：major 连续不变达到阈值即视为加载完成，响应延迟 = 首次 major 变化时刻 - 点击时刻。
        4. major 用于判定是否重置稳定窗口，minor 仅辅助调试、不参与稳定判定。

        Args:
            click_start_time: 点击开始时间（time.time()）
            baseline_ui_hash: 点击前基准 UI 原始哈希（兼容用）
            click_executed_time: 点击执行完成时间（用于更精确的延迟起点）
            baseline_major_hash: 点击前基准 major 签名（用于显著变化判定，避免误判）

        Returns:
            dict: response_time, delay, last_change_time, is_timeout, stable_duration
        """
        high_freq_duration = 4.0   # 高频检测持续时间（秒）
        high_freq_interval = 0.10  # 高频检测间隔（秒）——注意实际频率受快照获取耗时限制
        normal_interval = 0.30     # 正常检测间隔（秒）
        stable_threshold = 3.0     # 变化后 3s 内不再变化视为加载完成（按需求）
        max_wait_time = 30.0

        last_major_hash = baseline_major_hash or baseline_ui_hash
        last_minor_hash = None
        last_change_time = None
        last_change_snapshot_start = None  # 发生变化的那次快照的开始时刻（用于精确延迟）
        stable_start_time = None
        first_change_detected = False

        if click_executed_time:
            actual_click_time = click_executed_time
        else:
            actual_click_time = click_start_time

        logging.info(f"开始监控UI变化（点击时间: {actual_click_time:.3f}）")

        # 第一层：若发生 Activity/焦点窗口变化，直接判定为“显著响应”（不受页面内部自动刷新影响）
        focus_before = self._get_current_focus()

        # 第一次快照：用于尽早建立“点击后”状态（并记录耗时）
        try:
            snap = self._capture_ui_snapshot(timeout=3)
            initial_ui = snap.get("xml") if snap else None
            if initial_ui:
                major_hash, minor_hash = self._ui_snapshot_signatures(initial_ui, ignore_keys=dynamic_ignore_keys)
                last_major_hash = major_hash or hashlib.md5(initial_ui.encode('utf-8', errors='ignore')).hexdigest()
                last_minor_hash = minor_hash or last_major_hash

                if baseline_major_hash and last_major_hash != baseline_major_hash:
                    # 变化发生在 (actual_click_time, snap.end] 之间。用“时间窗中点”估计首次变化时刻，避免恒为 0。
                    first_change_detected = True
                    win_start = max(actual_click_time, snap.get("start", actual_click_time))
                    win_end = max(win_start, snap.get("end", win_start))
                    est_change = (win_start + win_end) / 2.0
                    last_change_time = est_change
                    last_change_snapshot_start = snap.get("start")
                    delay = est_change - actual_click_time
                    logging.info(
                        f"检测到UI立即变化（延迟: {delay:.3f}秒，method={snap.get('method')}, "
                        f"win={win_end - win_start:.3f}s）"
                    )
                else:
                    logging.debug(
                        f"获取初始UI快照（method={snap.get('method')}, dur={snap.get('duration', 0):.3f}s, "
                        f"major={last_major_hash[:8] if last_major_hash else ''}...），等待UI变化"
                    )
            else:
                if not last_major_hash:
                    last_major_hash = ""
        except Exception as e:
            logging.warning(f"获取初始UI快照失败: {e}")
            if not last_major_hash:
                last_major_hash = ""

        while time.time() - actual_click_time < max_wait_time:
            current_time = time.time()
            elapsed = current_time - actual_click_time

            if elapsed < high_freq_duration:
                check_interval = high_freq_interval
            else:
                check_interval = normal_interval

            try:
                snap = self._capture_ui_snapshot(timeout=3)
                current_ui = snap.get("xml") if snap else None
                if not current_ui:
                    time.sleep(check_interval)
                    continue

                # Activity/焦点变化优先：导航类响应最可靠
                focus_now = self._get_current_focus()
                if focus_before and focus_now and focus_now != focus_before and not first_change_detected:
                    first_change_detected = True
                    last_change_time = time.time()
                    stable_start_time = None
                    logging.info(f"检测到窗口焦点变化（{focus_before} -> {focus_now}），判定为显著响应")
                    # 焦点变化后仍需等待首次稳定（3s 无 major 变化）
                    focus_before = focus_now

                current_major_hash, current_minor_hash = self._ui_snapshot_signatures(
                    current_ui, ignore_keys=dynamic_ignore_keys
                )
                if not current_major_hash:
                    current_major_hash = hashlib.md5(current_ui.encode('utf-8', errors='ignore')).hexdigest()
                if not current_minor_hash:
                    current_minor_hash = current_major_hash

                major_changed = current_major_hash != last_major_hash
                if major_changed:
                    last_major_hash = current_major_hash
                    last_minor_hash = current_minor_hash
                    # 变化发生在上一次快照结束后到本次快照结束之间，使用时间窗中点估计
                    win_start = max(actual_click_time, (snap.get("start") or time.time()))
                    win_end = max(win_start, (snap.get("end") or win_start))
                    est_change = (win_start + win_end) / 2.0
                    last_change_time = est_change
                    last_change_snapshot_start = snap.get("start")

                    if not first_change_detected:
                        first_change_detected = True
                        change_delay = est_change - actual_click_time
                        logging.info(
                            f"首次检测到UI显著变化（延迟: {change_delay:.3f}秒，method={snap.get('method')}, "
                            f"win={win_end - win_start:.3f}s）"
                        )
                    else:
                        logging.debug(f"检测到UI显著变化（延迟: {est_change - actual_click_time:.3f}秒）")

                    stable_start_time = None
                else:
                    last_minor_hash = current_minor_hash
                    if not first_change_detected:
                        if elapsed > 5.0:
                            logging.warning(f"点击后{elapsed:.1f}秒仍未检测到UI显著变化，可能页面无响应或变化不明显")
                    else:
                        if stable_start_time is None:
                            stable_start_time = current_time
                            logging.debug(f"UI开始稳定（距离最后变化: {current_time - (last_change_time or current_time):.3f}秒）")
                        else:
                            stable_duration = current_time - stable_start_time
                            if stable_duration >= stable_threshold:
                                response_time = current_time
                                if last_change_time is None:
                                    delay = 0.0
                                    logging.warning("点击后未检测到UI显著变化，响应延迟为0（可能页面无响应）")
                                else:
                                    delay = last_change_time - actual_click_time
                                stable_duration_final = current_time - stable_start_time

                                logging.info(f"页面加载完成 - 响应延迟: {delay:.3f}秒，UI稳定时长: {stable_duration_final:.3f}秒")

                                return {
                                    'response_time': response_time,
                                    'delay': delay,
                                    'last_change_time': last_change_time or actual_click_time,
                                    'is_timeout': False,
                                    'stable_duration': stable_duration_final
                                }
            except Exception as e:
                logging.warning(f"UI检测过程出错: {e}，继续监控")
                time.sleep(normal_interval)
                continue

            time.sleep(check_interval)

        current_time = time.time()
        total_wait_time = current_time - actual_click_time

        if last_change_time is None:
            delay = 0.0
            logging.warning(f"响应延迟检测超时（等待{total_wait_time:.3f}秒），且未检测到任何UI显著变化，延迟为0")
        else:
            delay = last_change_time - actual_click_time
            logging.warning(f"响应延迟检测超时（等待{total_wait_time:.3f}秒），返回最后一次显著变化时间（延迟: {delay:.3f}秒）")

        return {
            'response_time': current_time,
            'delay': delay,
            'last_change_time': last_change_time or actual_click_time,
            'is_timeout': True,
            'stable_duration': current_time - (stable_start_time or actual_click_time) if stable_start_time else 0
        }

    def _get_current_focus(self):
        """
        获取当前窗口焦点（Activity/Window），用于检测页面跳转类的“显著响应”。
        解析 dumpsys window 输出中的 mCurrentFocus 或 mFocusedApp。
        """
        try:
            cmd = f"adb -s {self.device.sn} shell dumpsys window windows"
            out = run_cmd(cmd, timeout=3)
            if not isinstance(out, str) or not out:
                return None
            for line in out.splitlines():
                line = line.strip()
                if "mCurrentFocus=" in line:
                    return line.split("mCurrentFocus=", 1)[1].strip()
                if "mFocusedApp=" in line:
                    return line.split("mFocusedApp=", 1)[1].strip()
        except Exception:
            return None
        return None