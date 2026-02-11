#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
统一测试报告生成模块

支持的报告类型：传统Monkey、稳定性测试、系统健壮性、性能测试、异常恢复测试等。
所有报告使用统一的格式、结构和内容规范，并支持测试过程中的实时报告更新。
"""

import json
import os
import logging
import glob
from datetime import datetime
from typing import Dict, Any, List

# 图表依赖：matplotlib 必需，pandas 仅在部分数据处理场景使用，可选
HAS_MATPLOTLIB = False
try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    plt = None  # type: ignore

try:
    import pandas as pd  # type: ignore
except ImportError:
    pd = None  # type: ignore

# 实时报告更新间隔（秒）
# 默认 10s；可通过环境变量 MONKEYAUTOTEST_LIVE_REPORT_UPDATE_INTERVAL 覆盖
try:
    LIVE_REPORT_UPDATE_INTERVAL = int(os.environ.get("MONKEYAUTOTEST_LIVE_REPORT_UPDATE_INTERVAL", "10"))
    if LIVE_REPORT_UPDATE_INTERVAL < 1:
        LIVE_REPORT_UPDATE_INTERVAL = 10
except Exception:
    LIVE_REPORT_UPDATE_INTERVAL = 10

# 支持的测试类型（用于统一报告入口）
TEST_TYPE_MONKEY = "monkey"
TEST_TYPE_COMPREHENSIVE = "comprehensive"
TEST_TYPE_SYSTEM_ROBUSTNESS = "system_robustness"
TEST_TYPE_EXCEPTION_RECOVERY = "exception_recovery"
TEST_TYPE_PERFORMANCE = "performance"
TEST_TYPE_BROADCAST_STRESS = "broadcast_stress"
TEST_TYPE_TTS_STRESS = "tts_stress"


def _perf_app_cpu(p: Dict[str, Any]) -> float:
    """性能采样行：应用 CPU 占比（app_cpu_pct）。"""
    return float(p.get('app_cpu_pct', 0) or 0)


def _perf_app_mem_mb(p: Dict[str, Any]) -> float:
    """性能采样行：应用 PSS 内存 MB（app_memory_pss_mb / app_memory_pss_kb）。"""
    v = p.get('app_memory_pss_mb')
    if v is not None:
        return float(v)
    kb = p.get('app_memory_pss_kb', 0) or 0
    return round(kb / 1024.0, 2) if kb else 0.0


def _perf_mode(p: Dict[str, Any]) -> str:
    """性能采样行：前台/后台（app_foreground_mode）。"""
    return (p.get('app_foreground_mode') or '').lower()


def _perf_device_cpu(p: Dict[str, Any]) -> Any:
    """性能采样行：设备 CPU 占比（device_cpu_pct）。"""
    return p.get('device_cpu_pct')


def _perf_device_mem_mb(p: Dict[str, Any]) -> Any:
    """性能采样行：设备已用内存 MB（device_memory_used_mb）。"""
    return p.get('device_memory_used_mb')


def normalize_test_results(raw: Dict[str, Any], test_type: str) -> Dict[str, Any]:
    """
    将不同来源的测试结果规范化为统一结构，供报告生成使用。

    Args:
        raw: 原始结果（可能来自传统Monkey、稳定性测试、单模块测试等）
        test_type: 测试类型

    Returns:
        规范化后的 test_results，包含 device_info, package_info, tests, start_time 等
    """
    normalized = {
        'device_info': raw.get('device_info') or {},
        'package_info': raw.get('package_info') or {},
        'tests': raw.get('tests') or {},
        'start_time': raw.get('start_time') or datetime.now().isoformat(),
        'end_time': raw.get('end_time', ''),
        'metadata': raw.get('metadata') or {},
    }
    # 传统 Monkey 结果：通常只有 device_log 的 anr_cnt/crash_cnt，需放入 tests.monkey
    if test_type == TEST_TYPE_MONKEY:
        if 'tests' not in normalized or 'monkey' not in normalized['tests']:
            normalized.setdefault('tests', {})['monkey'] = {
                'crashes': raw.get('crashes', 0),
                'anrs': raw.get('anrs', 0),
                'throttle': raw.get('throttle'),
                'event_count': raw.get('count'),
                'log_path': raw.get('log_path', ''),
            }
    return normalized


class StabilityReportGenerator:
    """
    稳定性测试报告生成器
    生成详细的HTML和JSON格式报告
    """

    def __init__(self):
        self.template_dir = "templates"
        self.output_dir = "reports"
        os.makedirs(self.output_dir, exist_ok=True)
        self.intermediate_reports = []  # 存储阶段性报告路径

    def generate_report(self, test_results: Dict[str, Any],
                        test_type: str = TEST_TYPE_COMPREHENSIVE,
                        is_intermediate: bool = False,
                        device_sn: str = None,
                        package_name: str = None,
                        **kwargs) -> str:
        """
        统一报告生成入口。所有类型的测试（传统Monkey、稳定性、系统健壮性、性能、异常恢复）
        均通过此方法生成报告，确保格式、结构和内容一致。

        Args:
            test_results: 测试结果数据（可为原始结构，内部会规范化）
            test_type: 测试类型 monkey/comprehensive/system_robustness/exception_recovery/performance
            is_intermediate: 是否为阶段性/临时报告
            device_sn: 设备序列号（可选，从 test_results 推断）
            package_name: 应用包名（可选，从 test_results 推断）
            **kwargs: 其他参数传递给 generate_comprehensive_report

        Returns:
            生成的 HTML 报告路径
        """
        normalized = normalize_test_results(test_results, test_type)
        return self.generate_comprehensive_report(
            normalized,
            is_intermediate=is_intermediate,
            device_sn=device_sn,
            package_name=package_name,
            test_type=test_type,
            **kwargs
        )

    def generate_comprehensive_report(self, test_results: Dict[str, Any], 
                                     is_intermediate: bool = False,
                                     device_sn: str = None,
                                     package_name: str = None,
                                     test_type: str = "comprehensive") -> str:
        """
        生成综合测试报告

        Args:
            test_results: 测试结果数据
            is_intermediate: 是否为阶段性报告（临时报告）
            device_sn: 设备序列号
            package_name: 应用包名
            test_type: 测试类型（comprehensive/system_robustness/exception_recovery/performance）

        Returns:
            报告文件路径
        """
        # 生成唯一文件名
        base_filename = self._generate_report_filename(
            test_results, is_intermediate, device_sn, package_name, test_type
        )

        # 生成JSON报告
        json_path = self._generate_json_report(test_results, base_filename, is_intermediate)

        # 生成HTML报告
        html_path = self._generate_html_report(test_results, base_filename, is_intermediate)

        # 生成图表
        self._generate_charts(test_results, base_filename)

        if is_intermediate:
            self.intermediate_reports.append({
                'json_path': json_path,
                'html_path': html_path,
                'timestamp': datetime.now().isoformat(),
                'test_type': test_type
            })
            logging.info(f"阶段性测试报告已保存: {html_path}")
        else:
            logging.info(f"测试报告生成完成: {html_path}")
        
        return html_path

    def _generate_report_filename(self, test_results: Dict[str, Any], 
                                 is_intermediate: bool,
                                 device_sn: str = None,
                                 package_name: str = None,
                                 test_type: str = "comprehensive") -> str:
        """
        生成报告文件名，包含时间戳、测试类型、设备信息等，确保每次测试都有独立报告文件
        
        格式: {test_type}_{status}_{device_sn}_{package_name}_{timestamp}_{microseconds}
        阶段性报告格式: {test_type}_intermediate_{device_sn}_{package_name}_{timestamp}_{microseconds}
        """
        # 新命名规范（便于管理与筛选）：
        # 设备SN_测试项目_YYYYMMDD_HHMMSS（final）
        # 设备SN_测试项目_YYYYMMDD_HHMMSS_intermediate（阶段性）
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # 从test_results中提取信息
        if not device_sn:
            device_sn = test_results.get('device_info', {}).get('sn', 'unknown')
        if not package_name:
            package_name = test_results.get('package_info', {}).get('name', 'unknown')
            # 移除包名中的特殊字符，只保留字母数字和下划线
            package_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in package_name)

        # 测试项目（优先 metadata.project_key，其次环境变量，其次 test_type）
        project_key = ""
        try:
            project_key = (test_results.get("metadata", {}) or {}).get("project_key") or ""
        except Exception:
            project_key = ""
        if not project_key:
            project_key = os.environ.get("MONKEYAUTOTEST_PROJECT_KEY", "") or ""
        if not project_key:
            project_key = test_type or "unknown"
        project_key = "".join(c if (c.isalnum() or c in ("_", "-")) else "_" for c in str(project_key)).strip("_")

        sn_short = (device_sn or "unknown")[:8]
        base_filename = f"{sn_short}_{project_key}_{timestamp}"
        if is_intermediate:
            base_filename = f"{base_filename}_intermediate"

        # 避免同秒重名：若文件已存在则追加 _01/_02...
        try:
            html_path = os.path.join(self.output_dir, f"{base_filename}.html")
            idx = 1
            while os.path.exists(html_path):
                suffix = f"_{idx:02d}"
                candidate = f"{sn_short}_{project_key}_{timestamp}{suffix}"
                if is_intermediate:
                    candidate = f"{candidate}_intermediate"
                html_path = os.path.join(self.output_dir, f"{candidate}.html")
                base_filename = candidate
                idx += 1
        except Exception:
            pass
        return base_filename

    def save_intermediate_report(self, test_results: Dict[str, Any],
                                 device_sn: str = None,
                                 package_name: str = None,
                                 test_type: str = "comprehensive",
                                 phase_info: str = None) -> str:
        """
        保存阶段性测试报告
        
        Args:
            test_results: 当前测试结果数据
            device_sn: 设备序列号
            package_name: 应用包名
            test_type: 测试类型
            phase_info: 阶段信息（如 "phase_1", "system_robustness_completed"）
        
        Returns:
            报告文件路径
        """
        # 在test_results中添加阶段性标记
        if 'metadata' not in test_results:
            test_results['metadata'] = {}
        test_results['metadata']['is_intermediate'] = True
        test_results['metadata']['phase_info'] = phase_info
        test_results['metadata']['saved_at'] = datetime.now().isoformat()
        
        return self.generate_report(
            test_results,
            test_type=test_type,
            is_intermediate=True,
            device_sn=device_sn,
            package_name=package_name,
        )

    def consolidate_reports(self, final_test_results: Dict[str, Any],
                           device_sn: str = None,
                           package_name: str = None) -> str:
        """
        整合阶段性报告为最终报告
        
        Args:
            final_test_results: 最终测试结果数据
            device_sn: 设备序列号
            package_name: 应用包名
        
        Returns:
            最终报告文件路径
        """
        # 合并所有阶段性报告的数据
        if self.intermediate_reports:
            logging.info(f"开始整合 {len(self.intermediate_reports)} 个阶段性报告")
            
            # 在最终结果中记录阶段性报告信息
            if 'metadata' not in final_test_results:
                final_test_results['metadata'] = {}
            final_test_results['metadata']['intermediate_reports'] = [
                {
                    'path': report['json_path'],
                    'timestamp': report['timestamp'],
                    'test_type': report['test_type']
                }
                for report in self.intermediate_reports
            ]
            final_test_results['metadata']['intermediate_count'] = len(self.intermediate_reports)
        
        # 生成最终报告（统一入口）
        final_report_path = self.generate_report(
            final_test_results,
            test_type=TEST_TYPE_COMPREHENSIVE,
            is_intermediate=False,
            device_sn=device_sn,
            package_name=package_name,
        )
        
        # 清理阶段性报告列表
        self.intermediate_reports.clear()
        
        return final_report_path

    # ------------------------- 实时报告（测试过程中每分钟更新） -------------------------

    def create_initial_report(self, live_state: Dict[str, Any], output_path: str = None) -> str:
        """
        在测试执行前预先生成初始报告模板。
        live_state 应包含: device_info, package_info, test_params, start_time,
        current_phase('idle'), modules_done([]), run_log_dir(可选)。
        """
        if output_path is None:
            os.makedirs(self.output_dir, exist_ok=True)
            device_sn = (live_state.get('device_info') or {}).get('sn', 'unknown')[:8]
            project_key = (live_state.get("project_key") or "") or os.environ.get("MONKEYAUTOTEST_PROJECT_KEY", "") or "stability"
            project_key = "".join(c if (c.isalnum() or c in ("_", "-")) else "_" for c in str(project_key)).strip("_")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(self.output_dir, f"{device_sn}_{project_key}_{ts}.html")
        live_state.setdefault('current_phase', 'idle')
        live_state.setdefault('modules_done', [])
        live_state.setdefault('test_params', {})
        html_content = self._build_unified_report_html(live_state)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        # 同时输出轻量级 JSON，供报告查看器解析 project_key / device_sn / package_name
        json_path = os.path.splitext(output_path)[0] + ".json"
        device_info = live_state.get("device_info") or {}
        package_info = live_state.get("package_info") or {}
        dev_ver = device_info.get("build_display_id") or device_info.get("os") or ""
        app_ver = package_info.get("version_name") or ""
        meta = {
            "metadata": {
                "report_status": "live",
                "project_key": live_state.get("project_key") or os.environ.get("MONKEYAUTOTEST_PROJECT_KEY", "stability"),
                "generated_at": datetime.now().isoformat(),
                "is_live": True,
                "device_version": dev_ver,
                "app_version": app_ver,
            },
            "device_info": device_info,
            "package_info": package_info,
        }
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        logging.info(f"初始实时报告已创建: {output_path}")
        return output_path

    def update_live_report(self, live_state: Dict[str, Any], output_path: str) -> str:
        """
        更新实时报告内容。应在测试过程中每隔一定时间（如每分钟）调用一次。
        会从 run_log_dir 读取 performance_sampling.jsonl 和日志摘要。
        """
        if not output_path or not os.path.exists(output_path):
            return output_path
        run_log_dir = live_state.get('run_log_dir') or ''
        device_sn = (live_state.get('device_info') or {}).get('sn', '')
        # 从运行目录读取最新性能采样（若无则按设备 SN 找最新运行目录）
        perf_snapshot = self._read_latest_performance_snapshot(run_log_dir, device_sn=device_sn)
        live_state['performance_snapshot'] = perf_snapshot
        # 读取日志摘要（最后若干行）；若无 run_log_dir 则按 device_sn 找最新目录
        log_dir = run_log_dir or self._resolve_latest_run_log_dir(device_sn)
        log_tail = self._read_log_tail(log_dir, tail_lines=30)
        live_state['log_tail'] = log_tail
        # 从 test_results_snapshot 汇总各模块的崩溃/ANR（含广播、TTS 压力测试进行中的实时数据）
        snapshot = live_state.get('test_results_snapshot') or {}
        tests = snapshot.get('tests', {})
        modules_for_crash_anr = ('system_robustness', 'broadcast_stress', 'tts_stress')
        live_state['crashes_so_far'] = sum(tests.get(m, {}).get('crashes', 0) for m in modules_for_crash_anr)
        live_state['anrs_so_far'] = sum(tests.get(m, {}).get('anrs', 0) for m in modules_for_crash_anr)
        html_content = self._build_unified_report_html(live_state)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        # 同步更新轻量级 JSON，供报告查看器解析
        json_path = os.path.splitext(output_path)[0] + ".json"
        if os.path.exists(json_path):
            stopped = live_state.get("report_stopped", False)
            device_info = live_state.get("device_info") or {}
            package_info = live_state.get("package_info") or {}
            dev_ver = device_info.get("build_display_id") or device_info.get("os") or ""
            app_ver = package_info.get("version_name") or ""
            meta = {
                "metadata": {
                    "report_status": "stopped" if stopped else "live",
                    "project_key": live_state.get("project_key") or os.environ.get("MONKEYAUTOTEST_PROJECT_KEY", "stability"),
                    "generated_at": datetime.now().isoformat(),
                    "is_live": True,
                    "device_version": dev_ver,
                    "app_version": app_ver,
                },
                "device_info": device_info,
                "package_info": package_info,
            }
            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        return output_path

    def _read_latest_performance_snapshot(self, run_log_dir: str, max_samples: int = 1000, device_sn: str = None) -> List[Dict[str, Any]]:
        """从 run_log_dir/performance_sampling.jsonl 读取采样（支持取最早与最新各10条）。若 run_log_dir 为空则按 device_sn 查找最新运行目录。"""
        jsonl_path = None
        if run_log_dir and os.path.isdir(run_log_dir):
            jsonl_path = os.path.join(run_log_dir, "performance_sampling.jsonl")
        if (not jsonl_path or not os.path.exists(jsonl_path)) and device_sn:
            try:
                pattern = os.path.join("logs", device_sn, "*", "performance_sampling.jsonl")
                matches = glob.glob(pattern)
                if matches:
                    jsonl_path = max(matches, key=os.path.getmtime)
            except Exception:
                pass
        if not jsonl_path or not os.path.exists(jsonl_path):
            return []
        try:
            lines = []
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        lines.append(line)
            # 读取最早 10 条 + 最新 10 条（或全部若不足 20 条）
            if len(lines) <= 20:
                use_lines = lines
            else:
                use_lines = lines[:10] + lines[-10:]
            result = []
            for line in use_lines:
                try:
                    result.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
            return result
        except Exception as e:
            logging.debug(f"读取性能采样失败: {e}")
            return []

    def _resolve_latest_run_log_dir(self, device_sn: str) -> str:
        """解析设备最近一次运行的日志目录路径。"""
        if not device_sn:
            return ''
        try:
            parent = os.path.join("logs", device_sn)
            if not os.path.isdir(parent):
                return ''
            subs = [os.path.join(parent, d) for d in os.listdir(parent) if os.path.isdir(os.path.join(parent, d))]
            if not subs:
                return ''
            return max(subs, key=os.path.getmtime)
        except Exception:
            return ''

    def _read_log_tail(self, run_log_dir: str, tail_lines: int = 30) -> List[str]:
        """
        读取运行目录下主日志文件的最后若干行。
        为兼容不同模块，按优先级尝试多种日志文件名：
        - extended_monkey.log      系统健壮性/Monkey 长压
        - broadcast_stress.log     广播压力测试
        - tts_stress.log           TTS 压力测试
        - exception_recovery.log   异常恢复测试
        - performance.log          性能测试
        选中第一个存在的文件进行读取。
        """
        if not run_log_dir or not os.path.isdir(run_log_dir):
            return []
        candidates = [
            "extended_monkey.log",
            "broadcast_stress.log",
            "tts_stress.log",
            "exception_recovery.log",
            "performance.log",
        ]
        log_path = ""
        for name in candidates:
            p = os.path.join(run_log_dir, name)
            if os.path.exists(p):
                log_path = p
                break
        if not log_path:
            return []
        try:
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            return all_lines[-tail_lines:] if len(all_lines) > tail_lines else all_lines
        except Exception as e:
            logging.debug(f"读取日志尾部失败: {e}")
            return []

    def _build_log_links_html(self, run_log_dir: str) -> str:
        """
        根据 run_log_dir 生成日志文件超链接 HTML。
        报告在 reports/ 下，日志在 logs/device/ts/ 下，相对路径为 ../run_log_dir/filename。
        链接在新窗口打开，若文件不存在则显示「日志暂不可用」。
        """
        if not run_log_dir or not os.path.isdir(run_log_dir):
            return '<p class="log-links">日志目录不可用</p>'
        # 文件名 -> 锚文本（每个文件独立锚文本以便区分）
        log_candidates = [
            ("extended_monkey.log", "Monkey日志"),
            ("broadcast_stress.log", "广播测试日志"),
            ("tts_stress.log", "TTS测试日志"),
            ("logcat_monkey.log", "Monkey Logcat"),
            ("logcat_broadcast.log", "广播 Logcat"),
            ("logcat_tts.log", "TTS Logcat"),
            ("logcat_performance.log", "性能 Logcat"),
            ("logcat_performance_response.log", "性能 Logcat"),
            ("logcat_performance_resource.log", "性能 Logcat"),
            ("logcat_exception_recovery.log", "异常恢复 Logcat"),
            ("performance_sampling.jsonl", "性能日志"),
            ("exceptions.log", "崩溃/ANR异常日志"),
        ]
        rel_base = ("../" + run_log_dir.replace("\\", "/")).rstrip("/")
        links = []
        for filename, anchor in log_candidates:
            p = os.path.join(run_log_dir, filename)
            if os.path.isfile(p):
                href = f"{rel_base}/{filename}"
                links.append(
                    f'<a href="{self._escape_html(href)}" target="_blank" rel="noopener noreferrer">{self._escape_html(anchor)}</a>'
                )
        if not links:
            return '<p class="log-links">暂无可用日志文件（日志暂不可用）</p>'
        return '<p class="log-links">' + " | ".join(links) + "</p>"

    def _build_exceptions_section_html(self, run_log_dir: str, max_lines: int = 50) -> str:
        """若存在 exceptions.log，读取最后 N 条并在报告中展示。"""
        if not run_log_dir or not os.path.isdir(run_log_dir):
            return ""
        exc_path = os.path.join(run_log_dir, "exceptions.log")
        if not os.path.isfile(exc_path):
            return ""
        try:
            with open(exc_path, 'r', encoding='utf-8', errors='replace') as f:
                lines = f.readlines()
            if not lines:
                return ""
            tail = lines[-max_lines:] if len(lines) > max_lines else lines
            content = "".join(tail).strip()
            if not content:
                return ""
            escaped = self._escape_html(content).replace("\n", "<br>")
            return f"""
        <div class="section">
            <h3>异常日志（Crash/ANR/ERROR）</h3>
            <p style="color: #6c757d; font-size: 0.9em;">以下为从 logcat 提取的异常记录（最近 {len(tail)} 条）</p>
            <div class="log-box">{escaped}</div>
        </div>
            """
        except Exception as e:
            logging.debug(f"读取异常日志失败: {e}")
            return ""

    def _build_live_report_html(self, live_state: Dict[str, Any], is_initial: bool = False) -> str:
        """构建实时报告 HTML（初始或更新）。"""
        device_info = live_state.get('device_info') or {}
        package_info = live_state.get('package_info') or {}
        device_version = device_info.get('build_display_id') or device_info.get('os') or 'Unknown'
        app_version = package_info.get('version_name') or 'Unknown'
        test_params = live_state.get('test_params') or {}
        start_time_str = live_state.get('start_time') or datetime.now().isoformat()
        current_phase = live_state.get('current_phase', 'idle')
        modules_done = live_state.get('modules_done', [])
        try:
            start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if start_dt.tzinfo:
                start_dt = start_dt.replace(tzinfo=None)
        except Exception:
            start_dt = datetime.now()
        now = datetime.now()
        elapsed_seconds = (now - start_dt).total_seconds()
        elapsed_str = f"{int(elapsed_seconds // 3600)}小时{int((elapsed_seconds % 3600) // 60)}分钟"

        phase_display = {
            'idle': '等待开始',
            'system_robustness': '系统健壮性测试（Monkey/压力）',
            'exception_recovery': '异常恢复测试',
            'performance': '性能测试',
            'broadcast_stress': '广播模式压力测试',
            'tts_stress': 'TTS 模式压力测试',
        }.get(current_phase, current_phase)

        # 性能快照
        perf_snapshot = live_state.get('performance_snapshot') or []
        cpu_mem_rows = ""
        if perf_snapshot:
            for p in perf_snapshot[-10:]:
                ts = (p.get('timestamp') or '')[:19]
                cpu = _perf_app_cpu(p)
                mem_mb = _perf_app_mem_mb(p)
                mode = _perf_mode(p)
                mode_txt = "前台" if mode == "foreground" else ("后台" if mode == "background" else (mode or "-"))
                cpu_mem_rows += f"<tr><td>{ts}</td><td>{mode_txt}</td><td>{cpu}%</td><td>{mem_mb:.1f} MB</td></tr>"
        if not cpu_mem_rows:
            cpu_mem_rows = "<tr><td colspan='4'>暂无采样数据</td></tr>"

        # 日志摘要
        log_tail = live_state.get('log_tail') or []
        log_html = "<br>".join([self._escape_html(line.rstrip()) for line in log_tail]) if log_tail else "暂无日志"

        crashes = live_state.get('crashes_so_far', 0)
        anrs = live_state.get('anrs_so_far', 0)

        report_stopped = live_state.get('report_stopped', False)
        if report_stopped:
            status_badge = '<div style="background: #dc3545; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block; margin-left: 10px;">实时报告（已停止）</div>'
        elif not is_initial:
            status_badge = '<div style="background: #17a2b8; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block; margin-left: 10px;">实时报告（测试进行中）</div>'
        else:
            status_badge = '<div style="background: #6c757d; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block;">初始报告</div>'

        perf_tables_html = self._build_perf_snapshot_tables_html(perf_snapshot)

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>测试实时报告</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid #007acc; padding-bottom: 20px; }}
        .section {{ margin: 20px 0; }}
        .section h3 {{ color: #007acc; border-bottom: 1px solid #dee2e6; padding-bottom: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
        .log-box {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 12px; }}
        .footer {{ text-align: center; margin-top: 30px; color: #6c757d; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>车载端侧应用测试报告 {status_badge}</h1>
            <p>生成/更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>设备: {device_info.get('model', 'Unknown')} ({device_info.get('sn', 'Unknown')})</p>
            <p>设备版本: {device_version}</p>
            <p>应用: {package_info.get('name', 'Unknown')}</p>
            <p>应用版本: {app_version}</p>
        </div>

        <div class="section">
            <h3>测试基本信息</h3>
            <table>
                <tr><th>项目</th><th>值</th></tr>
                <tr><td>计划时长</td><td>{test_params.get('duration_hours', '-')} 小时</td></tr>
                <tr><td>Throttle</td><td>{test_params.get('throttle', '-')} ms</td></tr>
                <tr><td>开始时间</td><td>{start_time_str[:19]}</td></tr>
            </table>
        </div>

        <div class="section">
            <h3>实时测试进度与状态</h3>
            <table>
                <tr><td>已运行时间</td><td>{elapsed_str}</td></tr>
                <tr><td>当前阶段</td><td>{phase_display}</td></tr>
                <tr><td>已完成模块</td><td>{', '.join(modules_done) or '无'}</td></tr>
            </table>
        </div>

        <div class="section">
            <h3>中间测试结果（已发现 Crash/ANR）</h3>
            <table>
                <tr><td>当前崩溃次数</td><td>{crashes}</td></tr>
                <tr><td>当前 ANR 次数</td><td>{anrs}</td></tr>
            </table>
        </div>

        <div class="section">
            <h3>性能监控数据（最近采样）</h3>
            {perf_tables_html}
        </div>

        <div class="section">
            <h3>测试日志摘要</h3>
            <div class="log-box">{log_html}</div>
        </div>

        <div class="footer">
            <p>本报告在测试过程中每分钟自动更新，测试结束后将生成最终完整报告。</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def _build_perf_snapshot_tables_html(self, perf_snapshot: List[Dict[str, Any]]) -> str:
        """构建性能采样两个表格：最新10条与最早10条，均按时间倒序（新→旧）。含待测应用与设备总体 CPU/内存。"""
        has_device = bool(perf_snapshot and any(
            _perf_device_cpu(p) is not None or _perf_device_mem_mb(p) is not None for p in perf_snapshot
        ))

        def row(p: Dict[str, Any]) -> str:
            ts = (p.get('timestamp') or '')[:19]
            cpu = _perf_app_cpu(p)
            mem_mb = _perf_app_mem_mb(p)
            mode = _perf_mode(p)
            mode_txt = "前台" if mode == "foreground" else ("后台" if mode == "background" else (mode or "-"))
            base = f"<tr><td>{ts}</td><td>{mode_txt}</td><td>{cpu}%</td><td>{mem_mb:.1f} MB</td>"
            if has_device:
                dev_cpu = _perf_device_cpu(p)
                dev_mem = _perf_device_mem_mb(p)
                dev_mem_str = f"{float(dev_mem):.1f} MB" if dev_mem is not None else "-"
                base += f"<td>{dev_cpu if dev_cpu is not None else '-'}%</td><td>{dev_mem_str}</td>"
            base += "</tr>"
            return base

        if not perf_snapshot:
            cols = 6 if has_device else 4
            return f"<table><tr><th>时间</th><th>模式</th><th>应用 CPU%</th><th>应用内存 (MB)</th>" + ("<th>设备 CPU%</th><th>设备内存 (MB)</th>" if has_device else "") + f"</tr><tr><td colspan='{cols}'>暂无采样数据</td></tr></table>"

        latest_10 = perf_snapshot[-10:]
        earliest_10 = perf_snapshot[:10]
        rows_latest = "".join(row(p) for p in reversed(latest_10))
        rows_earliest = "".join(row(p) for p in reversed(earliest_10))
        header_extra = "<th>设备 CPU%</th><th>设备内存 (MB)</th>" if has_device else ""
        colspan = 6 if has_device else 4

        html = """
        <p><strong>最新 10 条采样</strong>（时间倒序；待测应用 + 设备总体）</p>
        <table>
            <tr><th>时间</th><th>模式</th><th>应用 CPU%</th><th>应用内存 (MB)</th>""" + header_extra + """</tr>
            """ + (rows_latest if rows_latest else f"<tr><td colspan='{colspan}'>无</td></tr>") + """
        </table>
        <p><strong>最早 10 条采样</strong>（时间倒序）</p>
        <table>
            <tr><th>时间</th><th>模式</th><th>应用 CPU%</th><th>应用内存 (MB)</th>""" + header_extra + """</tr>
            """ + (rows_earliest if rows_earliest else f"<tr><td colspan='{colspan}'>无</td></tr>") + """
        </table>
        """
        return html

    def _build_unified_report_html(self, live_state: Dict[str, Any]) -> str:
        """单一综合报告构建入口：实时区块 + 结果区块（来自 test_results_snapshot），根据 report_stopped 区分进行中/已停止。"""
        device_info = live_state.get('device_info') or {}
        package_info = live_state.get('package_info') or {}
        device_version = device_info.get('build_display_id') or device_info.get('os') or 'Unknown'
        app_version = package_info.get('version_name') or 'Unknown'
        test_params = live_state.get('test_params') or {}
        start_time_str = live_state.get('start_time') or datetime.now().isoformat()
        current_phase = live_state.get('current_phase', 'idle')
        modules_done = live_state.get('modules_done', [])
        try:
            start_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            if start_dt.tzinfo:
                start_dt = start_dt.replace(tzinfo=None)
        except Exception:
            start_dt = datetime.now()
        now = datetime.now()
        elapsed_seconds = (now - start_dt).total_seconds()
        elapsed_str = f"{int(elapsed_seconds // 3600)}小时{int((elapsed_seconds % 3600) // 60)}分钟"

        phase_display = {
            'idle': '等待开始',
            'system_robustness': '系统健壮性测试（Monkey/压力）',
            'exception_recovery': '异常恢复测试',
            'performance': '性能测试',
            'broadcast_stress': '广播模式压力测试',
            'tts_stress': 'TTS 模式压力测试',
        }.get(current_phase, current_phase)

        perf_snapshot = live_state.get('performance_snapshot') or []
        perf_tables_html = self._build_perf_snapshot_tables_html(perf_snapshot)
        log_tail = live_state.get('log_tail') or []
        log_html = "<br>".join([self._escape_html(line.rstrip()) for line in log_tail]) if log_tail else "暂无日志"
        crashes = live_state.get('crashes_so_far', 0)
        anrs = live_state.get('anrs_so_far', 0)

        report_stopped = live_state.get('report_stopped', False)
        snapshot = live_state.get('test_results_snapshot') or {}
        has_snapshot = bool(snapshot and snapshot.get('tests'))

        # ANR 事件列表：从 broadcast_stress / tts_stress 的 anr_events 合并，最近 20 条
        anr_events_merged = []
        tests_for_anr = snapshot.get('tests') or {}
        for mod, key in [('broadcast_stress', 'hint_index'), ('tts_stress', 'text_index')]:
            events = tests_for_anr.get(mod, {}).get('anr_events') or []
            prefix = 'Hint #' if mod == 'broadcast_stress' else 'TTS #'
            for ev in events:
                idx = ev.get(key, ev.get('hint_index', ev.get('text_index', '-')))
                preview = ev.get('hint_preview') if mod == 'broadcast_stress' else ev.get('text_preview')
                anr_events_merged.append({
                    'source': f"{prefix}{idx}",
                    'time': ev.get('time', '')[:19] if ev.get('time') else '-',
                    'reason': self._escape_html(str(ev.get('reason', '-'))[:200]),
                    'preview': self._escape_html(str((preview or '')[:50])),
                })
        anr_events_merged = anr_events_merged[-20:]
        anr_events_rows = "".join(
            f"<tr><td>{e['source']}</td><td>{e['time']}</td><td>{e['reason']}</td><td>{e['preview']}</td></tr>"
            for e in anr_events_merged
        )
        anr_events_table = (
            "<table><tr><th>序号</th><th>时间</th><th>原因</th><th>摘要</th></tr>" + anr_events_rows + "</table>"
            if anr_events_rows else "<p>暂无 ANR 事件记录</p>"
        )

        if report_stopped:
            status_badge = '<div style="background: #dc3545; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block; margin-left: 10px;">实时报告（已停止）</div>'
        elif has_snapshot:
            status_badge = '<div style="background: #17a2b8; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block; margin-left: 10px;">实时报告（测试进行中）</div>'
        else:
            status_badge = '<div style="background: #6c757d; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block;">初始报告</div>'

        live_sections = f"""
        <div class="section">
            <h3>测试基本信息</h3>
            <table>
                <tr><th>项目</th><th>值</th></tr>
                <tr><td>计划时长</td><td>{test_params.get('duration_hours', '-')} 小时</td></tr>
                <tr><td>Throttle</td><td>{test_params.get('throttle', '-')} ms</td></tr>
                <tr><td>开始时间</td><td>{start_time_str[:19]}</td></tr>
            </table>
        </div>
        <div class="section">
            <h3>实时测试进度与状态</h3>
            <table>
                <tr><td>已运行时间</td><td>{elapsed_str}</td></tr>
                <tr><td>当前阶段</td><td>{phase_display}</td></tr>
                <tr><td>已完成模块</td><td>{', '.join(modules_done) or '无'}</td></tr>
            </table>
        </div>
        <div class="section">
            <h3>中间测试结果（已发现 Crash/ANR）</h3>
            <table>
                <tr><td>当前崩溃次数</td><td>{crashes}</td></tr>
                <tr><td>当前 ANR 次数</td><td>{anrs}</td></tr>
            </table>
            <p><strong>ANR 事件列表</strong>（最近 20 条）</p>
            {anr_events_table}
        </div>
        <div class="section">
            <h3>性能监控数据（最近采样）</h3>
            {perf_tables_html}
        </div>
        <div class="section">
            <h3>测试日志摘要</h3>
            <div class="log-box">{log_html}</div>
        </div>
        """
        # 相关日志超链接（run_log_dir 来自 live_state 或从 device_sn 解析）
        device_sn = (device_info.get('sn') or '') if device_info else ''
        log_dir = live_state.get('run_log_dir') or ''
        if not log_dir and device_sn:
            log_dir = self._resolve_latest_run_log_dir(device_sn)
        if log_dir:
            live_sections += f"""
        <div class="section">
            <h3>相关日志</h3>
            {self._build_log_links_html(log_dir)}
        </div>
        """
            exc_section = self._build_exceptions_section_html(log_dir)
            if exc_section:
                live_sections += exc_section

        result_sections = ""
        if has_snapshot:
            try:
                summary = self._generate_summary(snapshot)
                # 收集 run_log_dir（优先 system_robustness / broadcast_stress / tts_stress）
                tests = snapshot.get('tests', {})
                run_log_dir = (tests.get('system_robustness') or tests.get('broadcast_stress') or tests.get('tts_stress') or {}).get('run_log_dir', '')
                if not run_log_dir:
                    run_log_dir = (tests.get('performance') or {}).get('run_log_dir', '') or (tests.get('exception_recovery') or {}).get('run_log_dir', '')
                log_links_section = self._build_log_links_html(run_log_dir) if run_log_dir else ''
                exc_section = self._build_exceptions_section_html(run_log_dir) if run_log_dir else ''
                result_sections = f"""
        <div class="summary-grid">
            {self._build_summary_cards_html(summary)}
        </div>
        {self._build_detailed_results_html(snapshot)}
        {self._build_performance_sampling_charts_html(snapshot)}
        {exc_section}
        <div class="section">
            <h3>相关日志</h3>
            {log_links_section if log_links_section else '<p class="log-links">暂无可用日志</p>'}
        </div>
        {self._build_issues_html(summary)}
        {self._build_recommendations_html(snapshot)}
        """
            except Exception as e:
                logging.debug(f"构建结果区块失败: {e}")
                result_sections = "<p>结果区块渲染异常</p>"

        footer_text = "测试已结束，以下为完整结果。" if report_stopped else "本报告在测试过程中每分钟自动更新。"
        if has_snapshot and not report_stopped:
            footer_text = "本报告在测试过程中每分钟自动更新，下方为当前已完成的模块结果。"

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>车载端侧应用稳定性测试报告</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; margin-bottom: 30px; border-bottom: 2px solid #007acc; padding-bottom: 20px; }}
        .section {{ margin: 20px 0; }}
        .section h3 {{ color: #007acc; border-bottom: 1px solid #dee2e6; padding-bottom: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f8f9fa; }}
        .log-box {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 12px; max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 12px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: #f8f9fa; padding: 20px; border-radius: 6px; border-left: 4px solid #007acc; }}
        .metric {{ display: flex; justify-content: space-between; margin: 10px 0; }}
        .metric-name {{ font-weight: 500; }}
        .metric-value {{ font-weight: bold; }}
        .status-pass {{ color: #28a745; }}
        .status-fail {{ color: #dc3545; }}
        .issues-list {{ background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 15px; margin: 20px 0; }}
        .recommendations {{ background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 4px; padding: 15px; margin: 20px 0; }}
        .footer {{ text-align: center; margin-top: 30px; color: #6c757d; font-size: 0.9em; }}
        .log-links {{ margin: 10px 0; word-break: break-all; }}
        .log-links a {{ margin-right: 8px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>车载端侧应用测试报告 {status_badge}</h1>
            <p>生成/更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>设备: {device_info.get('model', 'Unknown')} ({device_info.get('sn', 'Unknown')})</p>
            <p>设备版本: {device_version}</p>
            <p>应用: {package_info.get('name', 'Unknown')}</p>
            <p>应用版本: {app_version}</p>
        </div>
        {live_sections}
        {result_sections}
        <div class="footer">
            <p>{footer_text}</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    @staticmethod
    def _escape_html(s: str) -> str:
        return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;') if s else '')

    def _generate_json_report(self, test_results: Dict[str, Any], base_filename: str, is_intermediate: bool = False) -> str:
        """生成JSON格式报告"""
        json_path = os.path.join(self.output_dir, f"{base_filename}.json")

        # 合并metadata
        metadata = {
            'generated_at': datetime.now().isoformat(),
            'generator_version': '1.0.0',
            'test_framework': 'car_stability_test',
            'is_intermediate': is_intermediate,
            'report_status': 'intermediate' if is_intermediate else 'final'
        }

        # 如果test_results中已有metadata，合并它们
        if 'metadata' in test_results:
            metadata.update(test_results['metadata'])

        # 从 device_info / package_info 推导设备/应用版本信息，写入 metadata 方便报告查看器筛选
        try:
            dev_info = test_results.get('device_info') or {}
            pkg_info = test_results.get('package_info') or {}
            dev_ver = dev_info.get('build_display_id') or dev_info.get('os') or ""
            app_ver = pkg_info.get('version_name') or ""
            if dev_ver and not metadata.get('device_version'):
                metadata['device_version'] = dev_ver
            if app_ver and not metadata.get('app_version'):
                metadata['app_version'] = app_ver
        except Exception:
            pass
        
        report_data = {
            'metadata': metadata,
            'summary': self._generate_summary(test_results),
            'detailed_results': test_results,
            'analysis': self._generate_analysis(test_results) if not is_intermediate else {}
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logging.info(f"JSON报告已生成: {json_path}")
        return json_path

    def _generate_html_report(self, test_results: Dict[str, Any], base_filename: str, is_intermediate: bool = False) -> str:
        """生成HTML格式报告"""
        html_path = os.path.join(self.output_dir, f"{base_filename}.html")

        html_content = self._build_html_content(test_results, is_intermediate)

        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        logging.info(f"HTML报告已生成: {html_path}")
        return html_path

    def _generate_summary(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成测试总结"""
        summary = {
            'device_info': test_results.get('device_info', {}),
            'package_info': test_results.get('package_info', {}),
            'test_overview': {},
            'pass_rates': {},
            'critical_issues': []
        }

        tests = test_results.get('tests', {})

        # 传统 Monkey 测试总结
        if 'monkey' in tests:
            monkey_result = tests['monkey']
            summary['test_overview']['monkey'] = {
                'crashes': monkey_result.get('crashes', 0),
                'anrs': monkey_result.get('anrs', 0),
                'throttle': monkey_result.get('throttle'),
                'event_count': monkey_result.get('event_count'),
                'status': 'PASS' if (monkey_result.get('crashes', 0) + monkey_result.get('anrs', 0)) == 0 else 'FAIL',
            }

        # 系统健壮性总结
        if 'system_robustness' in tests:
            robust_result = tests['system_robustness']
            summary['test_overview']['system_robustness'] = {
                'duration_hours': robust_result.get('duration_hours', 0),
                'total_crashes': robust_result.get('crashes', 0),
                'total_anrs': robust_result.get('anrs', 0),
                'status': self._evaluate_robustness_status(robust_result)
            }

        # 广播压力测试总结
        if 'broadcast_stress' in tests:
            bc_result = tests['broadcast_stress']
            response_monitoring = bc_result.get('response_monitoring', [])
            success_count = sum(1 for r in response_monitoring if r.get('status') == 'success')
            timeout_appear_count = sum(1 for r in response_monitoring if r.get('status') == 'timeout_appear')
            response_times = [r.get('response_time') for r in response_monitoring if r.get('response_time') is not None]
            avg_response_time = sum(response_times) / len(response_times) if response_times else None
            
            summary['test_overview']['broadcast_stress'] = {
                'duration_hours': bc_result.get('duration_hours', 0),
                'broadcasts_sent': bc_result.get('broadcasts_sent', 0),
                'total_crashes': bc_result.get('crashes', 0),
                'total_anrs': bc_result.get('anrs', 0),
                'response_monitoring': {
                    'total': len(response_monitoring),
                    'success': success_count,
                    'timeout_appear': timeout_appear_count,
                    'avg_response_time': round(avg_response_time, 2) if avg_response_time else None,
                },
                'status': self._evaluate_robustness_status(bc_result)
            }

        # TTS 压力测试总结
        if 'tts_stress' in tests:
            tts_result = tests['tts_stress']
            response_monitoring = tts_result.get('response_monitoring', [])
            success_count = sum(1 for r in response_monitoring if r.get('status') == 'success')
            timeout_appear_count = sum(1 for r in response_monitoring if r.get('status') == 'timeout_appear')
            response_times = [r.get('response_time') for r in response_monitoring if r.get('response_time') is not None]
            avg_response_time = sum(response_times) / len(response_times) if response_times else None
            
            summary['test_overview']['tts_stress'] = {
                'duration_hours': tts_result.get('duration_hours', 0),
                'tts_played': tts_result.get('tts_played', 0),
                'total_crashes': tts_result.get('crashes', 0),
                'total_anrs': tts_result.get('anrs', 0),
                'response_monitoring': {
                    'total': len(response_monitoring),
                    'success': success_count,
                    'timeout_appear': timeout_appear_count,
                    'avg_response_time': round(avg_response_time, 2) if avg_response_time else None,
                },
                'status': self._evaluate_robustness_status(tts_result)
            }

        # 异常恢复总结
        if 'exception_recovery' in tests:
            recovery_result = tests['exception_recovery']
            scenarios = recovery_result.get('tests', {}).get('exception_recovery', {}).get('scenarios', [])
            passed_scenarios = sum(1 for s in scenarios if not s.get('app_crashed', True))

            summary['test_overview']['exception_recovery'] = {
                'total_scenarios': len(scenarios),
                'passed_scenarios': passed_scenarios,
                'pass_rate': passed_scenarios / len(scenarios) if scenarios else 0,
                'status': 'PASS' if passed_scenarios == len(scenarios) else 'FAIL'
            }

        # 性能测试总结
        if 'performance' in tests:
            perf_result = tests['performance']
            perf_tests = perf_result.get('tests', {})
            # 兼容：部分版本将资源消耗测试结果写入 tests.resource_consumption.resource_usage
            resource_fallback = {}
            try:
                resource_fallback = (tests.get('resource_consumption', {}) or {}).get('resource_usage', {}) or {}
            except Exception:
                resource_fallback = {}
            resource_raw = perf_tests.get('resource_usage') or resource_fallback

            summary['test_overview']['performance'] = {
                'cold_start_time': self._summarize_performance_metric(
                    perf_tests.get('cold_start_time', {}), 'cold_start_time'
                ),
                'response_delay': self._summarize_performance_metric(
                    perf_tests.get('response_delay', {}), 'response_delay'
                ),
                'resource_usage': self._summarize_resource_usage(
                    resource_raw or {}
                )
            }

        # 计算总体通过率
        summary['pass_rates'] = self._calculate_overall_pass_rates(summary)

        # 识别关键问题
        summary['critical_issues'] = self._identify_critical_issues(test_results)

        return summary

    def _evaluate_robustness_status(self, robust_result: Dict[str, Any]) -> str:
        """评估系统健壮性状态"""
        crashes = robust_result.get('crashes', 0)
        anrs = robust_result.get('anrs', 0)
        duration = robust_result.get('duration_hours', 1)

        # 根据测试时长设置不同的阈值
        if duration <= 1:
            max_issues = 0
        elif duration <= 12:
            max_issues = 5
        else:
            max_issues = 10

        return 'PASS' if (crashes + anrs) <= max_issues else 'FAIL'

    def _summarize_performance_metric(self, metric_result: Dict[str, Any], metric_name: str) -> Dict[str, Any]:
        """总结性能指标"""
        if not metric_result:
            return {'status': 'NOT_TESTED'}

        pass_rate = metric_result.get('pass_rate', 0)
        average = metric_result.get('average_time', metric_result.get('average_delay', 0))

        status = 'PASS' if pass_rate >= 0.8 else 'FAIL'

        return {
            'average': round(average, 2),
            'pass_rate': round(pass_rate, 3),
            'status': status,
            'target': metric_result.get('target_threshold', 0)
        }

    def _summarize_resource_usage(self, resource_result: Dict[str, Any]) -> Dict[str, Any]:
        """总结资源使用情况"""
        if not resource_result:
            return {'status': 'NOT_TESTED'}

        cpu_fg = resource_result.get('cpu_foreground', {})
        cpu_bg = resource_result.get('cpu_background', {})
        memory = resource_result.get('memory_pss', {})

        return {
            'cpu_foreground': {
                'average': round(cpu_fg.get('average', 0), 1),
                'pass_rate': round(cpu_fg.get('pass_rate', 0), 3),
                'status': 'PASS' if cpu_fg.get('pass_rate', 0) >= 0.9 else 'FAIL'
            },
            'cpu_background': {
                'average': round(cpu_bg.get('average', 0), 1),
                'pass_rate': round(cpu_bg.get('pass_rate', 0), 3),
                'status': 'PASS' if cpu_bg.get('pass_rate', 0) >= 0.95 else 'FAIL'
            },
            'memory': {
                'peak_pss': memory.get('peak', 0),
                'trend': memory.get('trend', 'unknown'),
                'memory_leak': memory.get('memory_leak_detected', False),
                'status': 'PASS' if not memory.get('memory_leak_detected', False) else 'FAIL'
            }
        }

    def _calculate_overall_pass_rates(self, summary: Dict[str, Any]) -> Dict[str, float]:
        """计算总体通过率"""
        pass_rates = {}

        # 计算各模块通过率
        for module_name, module_data in summary.get('test_overview', {}).items():
            if module_name == 'monkey':
                pass_rates['monkey'] = 1.0 if module_data.get('status') == 'PASS' else 0.0
            elif module_name == 'system_robustness':
                pass_rates['system_robustness'] = 1.0 if module_data.get('status') == 'PASS' else 0.0
            elif module_name == 'broadcast_stress':
                pass_rates['broadcast_stress'] = 1.0 if module_data.get('status') == 'PASS' else 0.0
            elif module_name == 'tts_stress':
                pass_rates['tts_stress'] = 1.0 if module_data.get('status') == 'PASS' else 0.0
            elif module_name == 'exception_recovery':
                pass_rates['exception_recovery'] = module_data.get('pass_rate', 0)
            elif module_name == 'performance':
                perf_scores = []
                for metric_name, metric_data in module_data.items():
                    if isinstance(metric_data, dict) and 'status' in metric_data:
                        perf_scores.append(1.0 if metric_data['status'] == 'PASS' else 0.0)
                    elif isinstance(metric_data, dict) and 'cpu_foreground' in metric_data:
                        # 资源使用情况
                        cpu_fg_pass = 1.0 if metric_data['cpu_foreground']['status'] == 'PASS' else 0.0
                        cpu_bg_pass = 1.0 if metric_data['cpu_background']['status'] == 'PASS' else 0.0
                        mem_pass = 1.0 if metric_data['memory']['status'] == 'PASS' else 0.0
                        perf_scores.extend([cpu_fg_pass, cpu_bg_pass, mem_pass])

                pass_rates['performance'] = sum(perf_scores) / len(perf_scores) if perf_scores else 0

        # 计算总体通过率
        all_rates = list(pass_rates.values())
        pass_rates['overall'] = sum(all_rates) / len(all_rates) if all_rates else 0

        return pass_rates

    def _identify_critical_issues(self, test_results: Dict[str, Any]) -> List[str]:
        """识别关键问题"""
        issues = []

        tests = test_results.get('tests', {})

        # 检查系统健壮性问题
        if 'system_robustness' in tests:
            robust = tests['system_robustness']
            crashes = robust.get('crashes', 0)
            anrs = robust.get('anrs', 0)
            if crashes > 0:
                issues.append(f"检测到 {crashes} 次应用崩溃")
            if anrs > 0:
                issues.append(f"检测到 {anrs} 次应用无响应(ANR)")

        # 检查广播/TTS 压力测试
        for key, label in [('broadcast_stress', '广播压力'), ('tts_stress', 'TTS压力')]:
            if key in tests:
                r = tests[key]
                crashes = r.get('crashes', 0)
                anrs = r.get('anrs', 0)
                if crashes > 0:
                    issues.append(f"{label}测试: 检测到 {crashes} 次应用崩溃")
                if anrs > 0:
                    issues.append(f"{label}测试: 检测到 {anrs} 次应用无响应(ANR)")

        # 检查异常恢复问题
        if 'exception_recovery' in tests:
            recovery = tests['exception_recovery']
            scenarios = recovery.get('tests', {}).get('exception_recovery', {}).get('scenarios', [])
            for scenario in scenarios:
                if scenario.get('app_crashed', False):
                    scenario_name = scenario.get('scenario', 'unknown')
                    issues.append(f"异常恢复失败: {scenario_name} 场景下应用崩溃")

        # 检查性能问题
        if 'performance' in tests:
            perf = tests['performance']
            perf_tests = perf.get('tests', {})

            cold_start = perf_tests.get('cold_start_time', {})
            if cold_start.get('pass_rate', 0) < 0.8:
                avg_time = cold_start.get('average_time', 0)
                issues.append(f"冷启动时间过长: {avg_time:.2f}秒")
            response_delay = perf_tests.get('response_delay', {})
            if response_delay.get('pass_rate', 0) < 0.8:
                avg_delay = response_delay.get('average_delay', 0)
                issues.append(f"响应延迟过长: {avg_delay:.2f}秒")
            resource = perf_tests.get('resource_usage') or (tests.get('resource_consumption', {}) or {}).get('resource_usage', {}) or {}
            if resource.get('memory_pss', {}).get('memory_leak_detected', False):
                issues.append("检测到内存泄漏")
            if resource.get('cpu_foreground', {}).get('pass_rate', 0) < 0.9:
                cpu_fg = resource.get('cpu_foreground', {}).get('average', 0)
                issues.append(f"前台CPU使用率过高: {cpu_fg:.1f}%")
        return issues

    def _generate_analysis(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成分析结果"""
        return {
            'recommendations': self._generate_recommendations(test_results),
            'trends': self._analyze_trends(test_results),
            'risk_assessment': self._assess_risks(test_results)
        }

    def _generate_recommendations(self, test_results: Dict[str, Any]) -> List[str]:
        """生成建议"""
        recommendations = []

        issues = self._identify_critical_issues(test_results)

        if issues:
            recommendations.append("优先解决以下关键问题:")
            recommendations.extend([f"• {issue}" for issue in issues])

        # 基于性能数据给出建议
        perf_tests = test_results.get('tests', {}).get('performance', {}).get('tests', {})

        cold_start = perf_tests.get('cold_start_time', {})
        if cold_start.get('average_time', 0) > 3.0:
            recommendations.append("优化应用冷启动性能：")
            recommendations.append("• 减少启动时的初始化工作")
            recommendations.append("• 实现懒加载机制")
            recommendations.append("• 优化资源加载顺序")

        response_delay = perf_tests.get('response_delay', {})
        if response_delay.get('average_delay', 0) > 1.5:
            recommendations.append("优化网络响应性能：")
            recommendations.append("• 实现数据缓存机制")
            recommendations.append("• 优化API请求")
            recommendations.append("• 使用数据压缩")

        resource_usage = perf_tests.get('resource_usage') or (test_results.get('tests', {}).get('resource_consumption', {}) or {}).get('resource_usage', {}) or {}
        cpu_fg = resource_usage.get('cpu_foreground', {})
        if cpu_fg.get('average', 0) > 30:
            recommendations.append("优化CPU使用率：")
            recommendations.append("• 识别并优化耗CPU的操作")
            recommendations.append("• 实现后台任务管理")
            recommendations.append("• 使用更高效的算法")

        return recommendations

    def _analyze_trends(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """分析趋势"""
        trends = {}

        # 分析性能数据的趋势
        perf_tests = test_results.get('tests', {}).get('performance', {}).get('tests', {})

        for test_name, test_data in perf_tests.items():
            if 'measurements' in test_data and len(test_data['measurements']) > 5:
                measurements = [m for m in test_data['measurements'] if m is not None]
                if len(measurements) > 5:
                    # 计算趋势（简化版本）
                    first_half = measurements[:len(measurements)//2]
                    second_half = measurements[len(measurements)//2:]

                    avg_first = sum(first_half) / len(first_half)
                    avg_second = sum(second_half) / len(second_half)

                    if avg_second > avg_first * 1.1:
                        trends[test_name] = 'deteriorating'
                    elif avg_second < avg_first * 0.9:
                        trends[test_name] = 'improving'
                    else:
                        trends[test_name] = 'stable'

        return trends

    def _assess_risks(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """风险评估"""
        risk_assessment = {
            'overall_risk': 'LOW',
            'risk_factors': [],
            'confidence_level': 'HIGH'
        }

        issues = self._identify_critical_issues(test_results)

        if len(issues) > 5:
            risk_assessment['overall_risk'] = 'HIGH'
        elif len(issues) > 2:
            risk_assessment['overall_risk'] = 'MEDIUM'
        else:
            risk_assessment['overall_risk'] = 'LOW'

        risk_assessment['risk_factors'] = issues

        # 基于测试覆盖率评估置信度
        test_coverage = len(test_results.get('tests', {}))
        if test_coverage < 2:
            risk_assessment['confidence_level'] = 'LOW'
        elif test_coverage < 3:
            risk_assessment['confidence_level'] = 'MEDIUM'

        return risk_assessment

    def _build_html_content(self, test_results: Dict[str, Any], is_intermediate: bool = False) -> str:
        """构建HTML内容"""
        summary = self._generate_summary(test_results)
        device_info = summary.get('device_info') or {}
        package_info = summary.get('package_info') or {}
        device_version = device_info.get('build_display_id') or device_info.get('os') or 'Unknown'
        app_version = package_info.get('version_name') or 'Unknown'

        # 添加阶段性报告标记
        status_badge = ""
        if is_intermediate:
            status_badge = '<div style="background: #ffc107; color: #000; padding: 5px 10px; border-radius: 4px; display: inline-block; margin-left: 10px; font-weight: bold;">阶段性报告（临时）</div>'

        html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>车载端侧应用稳定性测试报告</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 2px solid #007acc;
            padding-bottom: 20px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .summary-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 6px;
            border-left: 4px solid #007acc;
        }}
        .metric {{
            display: flex;
            justify-content: space-between;
            margin: 10px 0;
        }}
        .metric-name {{
            font-weight: 500;
        }}
        .metric-value {{
            font-weight: bold;
        }}
        .status-pass {{
            color: #28a745;
        }}
        .status-fail {{
            color: #dc3545;
        }}
        .issues-list {{
            background: #fff3cd;
            border: 1px solid #ffeaa7;
            border-radius: 4px;
            padding: 15px;
            margin: 20px 0;
        }}
        .recommendations {{
            background: #d1ecf1;
            border: 1px solid #bee5eb;
            border-radius: 4px;
            padding: 15px;
            margin: 20px 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: 600;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
            color: #6c757d;
        }}
        .log-links {{
            margin: 10px 0;
            word-break: break-all;
        }}
        .log-links a {{
            margin-right: 8px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>车载端侧应用稳定性测试报告 {status_badge}</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>设备: {device_info.get('model', 'Unknown')} ({device_info.get('sn', 'Unknown')})</p>
            <p>设备版本: {device_version}</p>
            <p>应用: {package_info.get('name', 'Unknown')}</p>
            <p>应用版本: {app_version}</p>
            {self._build_intermediate_info_html(test_results) if is_intermediate else ''}
        </div>

        <div class="summary-grid">
            {self._build_summary_cards_html(summary)}
        </div>

        {self._build_detailed_results_html(test_results)}

        {self._build_performance_sampling_charts_html(test_results)}

        {self._build_log_links_and_exceptions_html(test_results)}

        {self._build_issues_html(summary)}

        {self._build_recommendations_html(test_results)}

        <div class="footer">
            <p>报告由车载端侧稳定性测试框架自动生成</p>
        </div>
    </div>
</body>
</html>
"""
        return html

    def _build_summary_cards_html(self, summary: Dict[str, Any]) -> str:
        """构建总结卡片HTML"""
        html = ""

        # 总体通过率卡片
        overall_rate = summary.get('pass_rates', {}).get('overall', 0)
        status_class = "status-pass" if overall_rate >= 0.8 else "status-fail"

        html += f"""
        <div class="summary-card">
            <h3>总体评估</h3>
            <div class="metric">
                <span class="metric-name">总体通过率</span>
                <span class="metric-value {status_class}">{overall_rate:.1%}</span>
            </div>
        </div>
        """

        # 各模块状态卡片
        for module_name, module_data in summary.get('test_overview', {}).items():
            if module_name == 'monkey':
                status = module_data.get('status', 'UNKNOWN')
                status_class = "status-pass" if status == 'PASS' else "status-fail"
                html += f"""
                <div class="summary-card">
                    <h3>传统 Monkey 测试</h3>
                    <div class="metric">
                        <span class="metric-name">崩溃次数</span>
                        <span class="metric-value">{module_data.get('crashes', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">ANR次数</span>
                        <span class="metric-value">{module_data.get('anrs', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">状态</span>
                        <span class="metric-value {status_class}">{status}</span>
                    </div>
                </div>
                """
            elif module_name == 'system_robustness':
                status = module_data.get('status', 'UNKNOWN')
                status_class = "status-pass" if status == 'PASS' else "status-fail"
                html += f"""
                <div class="summary-card">
                    <h3>系统健壮性</h3>
                    <div class="metric">
                        <span class="metric-name">测试时长</span>
                        <span class="metric-value">{module_data.get('duration_hours', 0)}小时</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">崩溃次数</span>
                        <span class="metric-value">{module_data.get('total_crashes', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">ANR次数</span>
                        <span class="metric-value">{module_data.get('total_anrs', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">状态</span>
                        <span class="metric-value {status_class}">{status}</span>
                    </div>
                </div>
                """
            elif module_name == 'broadcast_stress':
                status = module_data.get('status', 'UNKNOWN')
                status_class = "status-pass" if status == 'PASS' else "status-fail"
                resp_mon = module_data.get('response_monitoring', {})
                html += f"""
                <div class="summary-card">
                    <h3>广播压力测试</h3>
                    <div class="metric">
                        <span class="metric-name">发送广播数</span>
                        <span class="metric-value">{module_data.get('broadcasts_sent', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">崩溃/ANR</span>
                        <span class="metric-value">{module_data.get('total_crashes', 0)}/{module_data.get('total_anrs', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">响应监控</span>
                        <span class="metric-value">成功: {resp_mon.get('success', 0)}/{resp_mon.get('total', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">平均响应时间</span>
                        <span class="metric-value">{resp_mon.get('avg_response_time', 'N/A')}秒</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">状态</span>
                        <span class="metric-value {status_class}">{status}</span>
                    </div>
                </div>
                """
            elif module_name == 'tts_stress':
                status = module_data.get('status', 'UNKNOWN')
                status_class = "status-pass" if status == 'PASS' else "status-fail"
                resp_mon = module_data.get('response_monitoring', {})
                html += f"""
                <div class="summary-card">
                    <h3>TTS 压力测试</h3>
                    <div class="metric">
                        <span class="metric-name">播放条数</span>
                        <span class="metric-value">{module_data.get('tts_played', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">崩溃/ANR</span>
                        <span class="metric-value">{module_data.get('total_crashes', 0)}/{module_data.get('total_anrs', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">响应监控</span>
                        <span class="metric-value">成功: {resp_mon.get('success', 0)}/{resp_mon.get('total', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">平均响应时间</span>
                        <span class="metric-value">{resp_mon.get('avg_response_time', 'N/A')}秒</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">状态</span>
                        <span class="metric-value {status_class}">{status}</span>
                    </div>
                </div>
                """

            elif module_name == 'exception_recovery':
                pass_rate = module_data.get('pass_rate', 0)
                status_class = "status-pass" if pass_rate >= 0.8 else "status-fail"
                html += f"""
                <div class="summary-card">
                    <h3>异常恢复</h3>
                    <div class="metric">
                        <span class="metric-name">通过场景</span>
                        <span class="metric-value">{module_data.get('passed_scenarios', 0)}/{module_data.get('total_scenarios', 0)}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-name">通过率</span>
                        <span class="metric-value {status_class}">{pass_rate:.1%}</span>
                    </div>
                </div>
                """

        return html

    def _build_detailed_results_html(self, test_results: Dict[str, Any]) -> str:
        """构建详细结果HTML"""
        html = "<h2>详细测试结果</h2>"

        tests = test_results.get('tests', {})

        # 性能测试详情
        if 'performance' in tests:
            perf_tests = tests['performance'].get('tests', {})
            html += "<h3>性能测试</h3><table>"
            html += "<tr><th>指标</th><th>平均值</th><th>达标率</th><th>状态</th></tr>"

            for test_name, test_data in perf_tests.items():
                if test_name in ['cold_start_time', 'response_delay']:
                    avg = test_data.get('average_time', test_data.get('average_delay', 0))
                    pass_rate = test_data.get('pass_rate', 0)
                    status = 'PASS' if pass_rate >= 0.8 else 'FAIL'
                    status_class = "status-pass" if status == 'PASS' else "status-fail"

                    metric_name = "冷启动时间" if test_name == 'cold_start_time' else "响应延迟"
                    unit = "秒"

                    html += f"""
                    <tr>
                        <td>{metric_name}</td>
                        <td>{avg:.2f}{unit}</td>
                        <td>{pass_rate:.1%}</td>
                        <td class="{status_class}">{status}</td>
                    </tr>
                    """

            html += "</table>"

            # 资源使用情况（前台/后台）
            resource_usage = perf_tests.get('resource_usage') or (tests.get('resource_consumption', {}) or {}).get('resource_usage', {}) or {}
            if isinstance(resource_usage, dict) and resource_usage:
                cpu_fg = resource_usage.get("cpu_foreground", {}) or {}
                cpu_bg = resource_usage.get("cpu_background", {}) or {}
                mem = resource_usage.get("memory_pss", {}) or {}
                html += "<h4>资源使用情况（数据来源：PerformanceMonitor._test_resource_usage，分别采集前台/后台）</h4>"
                html += "<table>"
                html += "<tr><th>维度</th><th>平均</th><th>峰值</th><th>阈值</th><th>达标率</th><th>状态</th></tr>"
                # 前台CPU
                html += f"""
<tr>
  <td>CPU（前台）</td>
  <td>{cpu_fg.get('average', 0):.1f}%</td>
  <td>{cpu_fg.get('peak', 0):.1f}%</td>
  <td>{cpu_fg.get('target_threshold', 30)}%</td>
  <td>{(cpu_fg.get('pass_rate', 0) or 0):.1%}</td>
  <td>{'PASS' if (cpu_fg.get('pass_rate', 0) or 0) >= 0.9 else 'FAIL'}</td>
</tr>
"""
                # 后台CPU
                html += f"""
<tr>
  <td>CPU（后台）</td>
  <td>{cpu_bg.get('average', 0):.1f}%</td>
  <td>{cpu_bg.get('peak', 0):.1f}%</td>
  <td>{cpu_bg.get('target_threshold', 1)}%</td>
  <td>{(cpu_bg.get('pass_rate', 0) or 0):.1%}</td>
  <td>{'PASS' if (cpu_bg.get('pass_rate', 0) or 0) >= 0.95 else 'FAIL'}</td>
</tr>
"""
                # 内存
                mem_peak = mem.get("peak", 0) or 0
                mem_trend = mem.get("trend", "unknown")
                leak = bool(mem.get("memory_leak_detected", False))
                html += f"""
<tr>
  <td>内存PSS</td>
  <td>{mem.get('average', 0):.0f} KB</td>
  <td>{mem_peak:.0f} KB</td>
  <td>-</td>
  <td>-</td>
  <td>{'FAIL' if leak else 'PASS'}（趋势：{mem_trend}）</td>
</tr>
"""
                html += "</table>"

        return html

    def _build_log_links_and_exceptions_html(self, test_results: Dict[str, Any]) -> str:
        """从 test_results 收集 run_log_dir，构建相关日志超链接及异常日志展示。"""
        tests = test_results.get('tests', {})
        run_log_dir = (tests.get('system_robustness') or tests.get('broadcast_stress') or tests.get('tts_stress') or {}).get('run_log_dir', '')
        if not run_log_dir:
            run_log_dir = (tests.get('performance') or {}).get('run_log_dir', '') or (tests.get('exception_recovery') or {}).get('run_log_dir', '')
        if not run_log_dir:
            return ''
        log_links = self._build_log_links_html(run_log_dir)
        exc_section = self._build_exceptions_section_html(run_log_dir)
        return exc_section + f"""
        <div class="section">
            <h3>相关日志</h3>
            {log_links}
        </div>
        """

    def _build_issues_html(self, summary: Dict[str, Any]) -> str:
        """构建问题列表HTML"""
        issues = summary.get('critical_issues', [])
        if not issues:
            return ""

        html = '<div class="issues-list"><h3>关键问题</h3><ul>'
        for issue in issues:
            html += f"<li>{issue}</li>"
        html += "</ul></div>"

        return html

    def _build_recommendations_html(self, test_results: Dict[str, Any]) -> str:
        """构建建议HTML"""
        analysis = self._generate_analysis(test_results)
        recommendations = analysis.get('recommendations', [])

        if not recommendations:
            return ""

        html = '<div class="recommendations"><h3>优化建议</h3><ul>'
        for rec in recommendations:
            html += f"<li>{rec}</li>"
        html += "</ul></div>"

        return html

    def _build_performance_sampling_charts_html(self, test_results: Dict[str, Any]) -> str:
        """从 performance_sampling.jsonl 读取 CPU / 内存采样并生成趋势图（按 mode=foreground/background 分类）。"""
        html = ""
        device_sn = test_results.get('device_info', {}).get('sn', 'unknown')

        # 优先使用本次运行目录（支持 system_robustness、broadcast_stress、tts_stress）
        tests = test_results.get('tests', {})
        run_log_dir = (tests.get('system_robustness') or tests.get('broadcast_stress') or tests.get('tts_stress') or {}).get('run_log_dir')
        jsonl_path = os.path.join(run_log_dir, "performance_sampling.jsonl") if run_log_dir else None

        # 回退：按设备 SN 查找最近一次的采样文件
        if not jsonl_path or not os.path.exists(jsonl_path):
            try:
                pattern = os.path.join("logs", device_sn, "*", "performance_sampling.jsonl")
                matches = glob.glob(pattern)
                if matches:
                    jsonl_path = max(matches, key=os.path.getmtime)
            except Exception:
                jsonl_path = None

        if not jsonl_path or not os.path.exists(jsonl_path):
            return ""

        try:
            labels = []
            cpu_fg, cpu_bg = [], []
            mem_fg, mem_bg = [], []
            device_cpu_list, device_mem_list = [], []
            with open(jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        mode = _perf_mode(data)
                        cpu = _perf_app_cpu(data)
                        mem_mb = _perf_app_mem_mb(data)
                        dev_cpu = _perf_device_cpu(data)
                        dev_mem = _perf_device_mem_mb(data)
                        if dev_cpu is not None:
                            device_cpu_list.append(float(dev_cpu))
                        else:
                            device_cpu_list.append(None)
                        if dev_mem is not None:
                            device_mem_list.append(float(dev_mem))
                        else:
                            device_mem_list.append(None)
                        ts_str = data.get('timestamp', '')
                        if ts_str:
                            try:
                                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                                labels.append(ts.strftime('%H:%M:%S'))
                            except Exception:
                                labels.append(f"#{len(labels)+1}")
                        else:
                            labels.append(f"#{len(labels)+1}")

                        # 用 None 将两种模式拆成两条线（同一时间轴）
                        if mode == "background":
                            cpu_fg.append(None)
                            mem_fg.append(None)
                            cpu_bg.append(cpu)
                            mem_bg.append(mem_mb)
                        else:
                            cpu_fg.append(cpu)
                            mem_fg.append(mem_mb)
                            cpu_bg.append(None)
                            mem_bg.append(None)
                    except json.JSONDecodeError:
                        continue

            if not labels:
                return ""

            # 截取最近 300 个点
            cap = 300
            labels_trim = labels[-cap:]
            cpu_fg_trim = cpu_fg[-cap:]
            cpu_bg_trim = cpu_bg[-cap:]
            mem_fg_trim = mem_fg[-cap:]
            mem_bg_trim = mem_bg[-cap:]
            device_cpu_trim = device_cpu_list[-cap:] if device_cpu_list else []
            device_mem_trim = device_mem_list[-cap:] if device_mem_list else []

            def _stats(xs):
                xs2 = [x for x in xs if isinstance(x, (int, float)) and x is not None]
                if not xs2:
                    return 0, 0.0, 0.0
                return len(xs2), sum(xs2) / len(xs2), max(xs2)

            fg_n, fg_cpu_avg, fg_cpu_peak = _stats(cpu_fg)
            bg_n, bg_cpu_avg, bg_cpu_peak = _stats(cpu_bg)
            fg_n_m, fg_mem_avg, fg_mem_peak = _stats(mem_fg)
            bg_n_m, bg_mem_avg, bg_mem_peak = _stats(mem_bg)
            dev_n, dev_cpu_avg, dev_cpu_peak = _stats(device_cpu_list)
            dev_n_m, dev_mem_avg, dev_mem_peak = _stats(device_mem_list)

            device_stats_html = ""
            device_charts_html = ""
            device_charts_script = ""
            if dev_n or dev_n_m:
                device_stats_html = f"""
          <p><b>设备总体</b></p>
          <ul style="margin: 8px 0 0 18px;">
            <li>设备 CPU：平均 {dev_cpu_avg:.1f}% / 峰值 {dev_cpu_peak:.1f}%（{dev_n} 点）</li>
            <li>设备内存：平均 {dev_mem_avg:.1f} MB / 峰值 {dev_mem_peak:.1f} MB（{dev_n_m} 点）</li>
          </ul>"""
                device_charts_html = """
        <h3>设备总体 CPU / 内存</h3>
        <div style="margin: 20px 0;">
            <canvas id="deviceCpuChart" style="max-width: 100%; height: 320px;"></canvas>
        </div>
        <div style="margin: 20px 0;">
            <canvas id="deviceMemoryChart" style="max-width: 100%; height: 320px;"></canvas>
        </div>"""
                device_charts_script = f"""
            const deviceCpuCtx = document.getElementById('deviceCpuChart').getContext('2d');
            new Chart(deviceCpuCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(labels_trim, ensure_ascii=False)},
                    datasets: [{{ label: '设备 CPU%', data: {json.dumps(device_cpu_trim)}, borderColor: 'rgb(54, 162, 235)', tension: 0.15, fill: false, pointRadius: 0, spanGaps: true }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ title: {{ display: true, text: '设备总体 CPU 使用率' }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
            }});
            const deviceMemCtx = document.getElementById('deviceMemoryChart').getContext('2d');
            new Chart(deviceMemCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(labels_trim, ensure_ascii=False)},
                    datasets: [{{ label: '设备内存 MB', data: {json.dumps(device_mem_trim)}, borderColor: 'rgb(255, 206, 86)', tension: 0.15, fill: false, pointRadius: 0, spanGaps: true }}]
                }},
                options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ title: {{ display: true, text: '设备总体内存使用 (MB)' }} }}, scales: {{ y: {{ beginAtZero: true }} }} }}
            }});"""

            html = f"""
        <h2>资源消耗趋势图（待测应用 + 设备总体）</h2>
        <div style="background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 6px; padding: 12px; margin: 10px 0;">
          <b>采样统计（数据来源：{os.path.basename(jsonl_path)}）</b>
          <p><b>待测应用（按模式：前台/后台）</b></p>
          <ul style="margin: 8px 0 0 18px;">
            <li>前台：CPU 平均 {fg_cpu_avg:.1f}% / 峰值 {fg_cpu_peak:.1f}%（{fg_n} 点）｜内存 平均 {fg_mem_avg:.1f}MB / 峰值 {fg_mem_peak:.1f}MB（{fg_n_m} 点）</li>
            <li>后台：CPU 平均 {bg_cpu_avg:.1f}% / 峰值 {bg_cpu_peak:.1f}%（{bg_n} 点）｜内存 平均 {bg_mem_avg:.1f}MB / 峰值 {bg_mem_peak:.1f}MB（{bg_n_m} 点）</li>
          </ul>
          {device_stats_html}
        </div>
        <h3>待测应用 CPU / 内存（按前台/后台）</h3>
        <div style="margin: 20px 0;">
            <canvas id="cpuChart" style="max-width: 100%; height: 400px;"></canvas>
        </div>
        <div style="margin: 20px 0;">
            <canvas id="memoryChart" style="max-width: 100%; height: 400px;"></canvas>
        </div>
        {device_charts_html}
        
        <script src="https://cdn.jsdelivr.net/npm/chart.js@3.9.1/dist/chart.min.js"></script>
        <script>
            const cpuCtx = document.getElementById('cpuChart').getContext('2d');
            const cpuChart = new Chart(cpuCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(labels_trim, ensure_ascii=False)},
                    datasets: [{{
                        label: 'CPU（前台）%',
                        data: {json.dumps(cpu_fg_trim)},
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.15)',
                        tension: 0.15,
                        fill: false,
                        pointRadius: 0,
                        spanGaps: true
                    }}, {{
                        label: 'CPU（后台）%',
                        data: {json.dumps(cpu_bg_trim)},
                        borderColor: 'rgb(255, 159, 64)',
                        backgroundColor: 'rgba(255, 159, 64, 0.15)',
                        tension: 0.15,
                        fill: false,
                        pointRadius: 0,
                        spanGaps: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        title: {{ display: true, text: '待测应用 CPU 使用率（按前台/后台）' }},
                        legend: {{ display: true }},
                        tooltip: {{ mode: 'index', intersect: false }}
                    }},
                    interaction: {{ mode: 'index', intersect: false }},
                    scales: {{
                        y: {{ beginAtZero: true, title: {{ display: true, text: 'CPU使用率 (%)' }} }},
                        x: {{ title: {{ display: true, text: '时间' }} }}
                    }}
                }}
            }});
            
            const memoryCtx = document.getElementById('memoryChart').getContext('2d');
            const memoryChart = new Chart(memoryCtx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(labels_trim, ensure_ascii=False)},
                    datasets: [{{
                        label: '内存（前台）MB',
                        data: {json.dumps(mem_fg_trim)},
                        borderColor: 'rgb(255, 99, 132)',
                        backgroundColor: 'rgba(255, 99, 132, 0.15)',
                        tension: 0.15,
                        fill: false,
                        pointRadius: 0,
                        spanGaps: true
                    }}, {{
                        label: '内存（后台）MB',
                        data: {json.dumps(mem_bg_trim)},
                        borderColor: 'rgb(153, 102, 255)',
                        backgroundColor: 'rgba(153, 102, 255, 0.15)',
                        tension: 0.15,
                        fill: false,
                        pointRadius: 0,
                        spanGaps: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        title: {{ display: true, text: '待测应用内存使用（按前台/后台）' }},
                        legend: {{ display: true }},
                        tooltip: {{ mode: 'index', intersect: false }}
                    }},
                    interaction: {{ mode: 'index', intersect: false }},
                    scales: {{
                        y: {{ beginAtZero: true, title: {{ display: true, text: '内存使用 (MB)' }} }},
                        x: {{ title: {{ display: true, text: '时间' }} }}
                    }}
                }}
            }});
            {device_charts_script}
        </script>
        <p style="color: #6c757d; font-size: 0.9em;">共 {len(labels)} 个采样点（展示最近 {min(cap, len(labels))} 个）。含待测应用与设备总体 CPU/内存。</p>
        """
        except Exception as e:
            logging.warning(f"生成performance_sampling.jsonl可视化图表失败: {e}")
            return ""

        return html

    def _build_intermediate_info_html(self, test_results: Dict[str, Any]) -> str:
        """构建阶段性报告信息HTML"""
        metadata = test_results.get('metadata', {})
        phase_info = metadata.get('phase_info', '')
        saved_at = metadata.get('saved_at', '')
        
        if phase_info or saved_at:
            html = '<div style="background: #fff3cd; border: 1px solid #ffc107; padding: 10px; border-radius: 4px; margin-top: 10px;">'
            html += '<p style="margin: 5px 0;"><strong>阶段性报告信息：</strong></p>'
            if phase_info:
                html += f'<p style="margin: 5px 0;">阶段: {phase_info}</p>'
            if saved_at:
                html += f'<p style="margin: 5px 0;">保存时间: {saved_at}</p>'
            html += '<p style="margin: 5px 0; color: #856404;">注意：此报告为测试过程中的临时报告，最终报告将在测试完成后生成。</p>'
            html += '</div>'
            return html
        return ''

    def _generate_charts(self, test_results: Dict[str, Any], base_filename: str):
        """生成图表"""
        if not HAS_MATPLOTLIB:
            logging.info("matplotlib未安装，跳过图表生成")
            return

        try:
            self._generate_performance_charts(test_results, base_filename)
        except Exception as e:
            logging.warning(f"生成图表失败: {str(e)}")

    def _generate_performance_charts(self, test_results: Dict[str, Any], base_filename: str):
        """生成性能图表"""
        perf_tests = test_results.get('tests', {}).get('performance', {}).get('tests', {})

        # CPU使用率图表
        resource_usage = perf_tests.get('resource_usage') or (test_results.get('tests', {}).get('resource_consumption', {}) or {}).get('resource_usage', {}) or {}
        cpu_fg = resource_usage.get('cpu_foreground', {})
        cpu_bg = resource_usage.get('cpu_background', {})

        if cpu_fg.get('measurements') or cpu_bg.get('measurements'):
            plt.figure(figsize=(12, 6))

            if cpu_fg.get('measurements'):
                plt.subplot(1, 2, 1)
                plt.plot(cpu_fg['measurements'], label='前台CPU使用率', color='blue')
                plt.axhline(y=cpu_fg.get('target_threshold', 30), color='red', linestyle='--', label='阈值(30%)')
                plt.title('前台CPU使用率')
                plt.xlabel('采样点')
                plt.ylabel('CPU使用率(%)')
                plt.legend()
                plt.grid(True)

            if cpu_bg.get('measurements'):
                plt.subplot(1, 2, 2)
                plt.plot(cpu_bg['measurements'], label='后台CPU使用率', color='green')
                plt.axhline(y=cpu_bg.get('target_threshold', 1), color='red', linestyle='--', label='阈值(1%)')
                plt.title('后台CPU使用率')
                plt.xlabel('采样点')
                plt.ylabel('CPU使用率(%)')
                plt.legend()
                plt.grid(True)

            plt.tight_layout()
            chart_path = os.path.join(self.output_dir, f"{base_filename}_cpu_usage.png")
            plt.savefig(chart_path, dpi=150, bbox_inches='tight')
            plt.close()

            logging.info(f"CPU使用率图表已生成: {chart_path}")