import json
import logging
import os
from pathlib import Path
from typing import Dict, Tuple

import glob

from utils.report_generator import StabilityReportGenerator


def _parse_report_filename_basic(filename: str) -> Dict[str, str]:
    """
    解析报告文件名的基础信息。

    约定格式: {sn_short}_{project_key}_{timestamp}[_intermediate][_NN].html
    """
    info: Dict[str, str] = {
        "device_sn_short": "",
        "project_key": "",
        "timestamp": "",
    }
    try:
        base = os.path.splitext(os.path.basename(filename))[0]
        parts = base.split("_")
        if len(parts) >= 3:
            info["device_sn_short"] = parts[0]
            info["project_key"] = parts[1]
            # 去掉可能的 intermediate 标记
            cleaned_parts = [p for p in parts[2:] if p != "intermediate"]
            if cleaned_parts:
                info["timestamp"] = "_".join(cleaned_parts)
    except Exception as e:
        logging.debug("基础解析报告文件名失败 %s: %s", filename, e)
    return info


def _ensure_run_log_dir(test_results: Dict, filename_info: Dict[str, str]) -> None:
    """确保 tests 中至少有一个模块带 run_log_dir，必要时基于 SN + 时间戳进行推断。"""
    tests = test_results.get("tests") or {}
    # 若已有任意模块包含 run_log_dir，则直接返回
    for key in (
        "monkey_stress",
        "broadcast_stress",
        "tts_stress",
        "performance",
        "exception_recovery",
        "system_robustness",
    ):
        if isinstance(tests.get(key), dict) and tests.get(key, {}).get("run_log_dir"):
            return

    device_sn = (test_results.get("device_info") or {}).get("sn") or ""
    if not device_sn:
        device_sn = filename_info.get("device_sn_short") or ""
    if not device_sn:
        return

    logs_root = os.path.join("logs", device_sn)
    if not os.path.isdir(logs_root):
        return

    # 优先尝试与时间戳匹配的子目录
    ts = filename_info.get("timestamp") or ""
    candidates = []
    for name in os.listdir(logs_root):
        full = os.path.join(logs_root, name)
        if not os.path.isdir(full):
            continue
        if ts and ts in name:
            candidates.append(full)
    if not candidates:
        # 回退为最新修改时间
        subdirs = [
            os.path.join(logs_root, d)
            for d in os.listdir(logs_root)
            if os.path.isdir(os.path.join(logs_root, d))
        ]
        if not subdirs:
            return
        candidates = [max(subdirs, key=os.path.getmtime)]

    # 选择第一个存在 performance_sampling.jsonl 的目录
    run_dir = ""
    for c in candidates:
        if os.path.isfile(os.path.join(c, "performance_sampling.jsonl")):
            run_dir = c
            break
    if not run_dir:
        return

    # 写回到 tests 结构，优先已有的模块
    preferred_keys = [
        "broadcast_stress",
        "tts_stress",
        "monkey_stress",
        "performance",
        "exception_recovery",
        "system_robustness",
    ]
    for key in preferred_keys:
        if key in tests and isinstance(tests.get(key), dict):
            tests[key]["run_log_dir"] = run_dir
            return
    # 若都不存在，则挂到 performance 模块下
    perf = tests.setdefault("performance", {})
    perf["run_log_dir"] = run_dir


def _has_performance_sampling(test_results: Dict, filename_info: Dict[str, str]) -> bool:
    """
    检查是否能找到 performance_sampling.jsonl。

    若无法找到，则认为不满足重构图表需求，保持原报告不变。
    """
    tests = test_results.get("tests") or {}
    run_log_dir = (
        (tests.get("monkey_stress") or {}).get("run_log_dir")
        or (tests.get("broadcast_stress") or {}).get("run_log_dir")
        or (tests.get("tts_stress") or {}).get("run_log_dir")
        or (tests.get("performance") or {}).get("run_log_dir")
        or (tests.get("exception_recovery") or {}).get("run_log_dir")
    )
    if run_log_dir and os.path.isfile(os.path.join(run_log_dir, "performance_sampling.jsonl")):
        return True

    device_sn = (test_results.get("device_info") or {}).get("sn") or ""
    if not device_sn:
        device_sn = filename_info.get("device_sn_short") or ""
    if not device_sn:
        return False

    try:
        pattern = os.path.join("logs", device_sn, "*", "performance_sampling.jsonl")
        matches = glob.glob(pattern)
        return bool(matches)
    except Exception:
        return False


def regenerate_report(report_path: str) -> Tuple[bool, str]:
    """
    使用最新模板重构单个 HTML 报告。

    仅在能够找到 performance_sampling.jsonl 时才真正重构，
    否则返回失败信息并保持原报告不变。
    """
    try:
        report_path = os.path.abspath(report_path)
        if not os.path.exists(report_path):
            return False, f"重构失败: 报告文件不存在 {report_path}"
        if not report_path.lower().endswith(".html"):
            return False, f"重构失败: 仅支持 HTML 报告文件 ({os.path.basename(report_path)})"

        filename_info = _parse_report_filename_basic(os.path.basename(report_path))
        json_path = os.path.splitext(report_path)[0] + ".json"

        test_results: Dict = {}

        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    data = {}

                has_detailed = isinstance(data.get("detailed_results"), dict)
                has_tests_top = isinstance(data.get("tests"), dict)
                has_device_pkg = isinstance(data.get("device_info"), dict) and isinstance(
                    data.get("package_info"), dict
                )

                # 类型 A：统一报告 JSON（包含 detailed_results 或 tests）
                if has_detailed or has_tests_top:
                    if has_detailed:
                        test_results = data.get("detailed_results") or {}
                        if not isinstance(test_results, dict):
                            test_results = {}
                    else:
                        # 顶层直接包含 tests（旧格式），包装成 test_results
                        test_results = {
                            "tests": data.get("tests") or {},
                        }

                    # 合并设备/应用信息，避免 Unknown
                    if "device_info" not in test_results or not isinstance(
                        test_results.get("device_info"), dict
                    ):
                        if isinstance(data.get("device_info"), dict):
                            test_results["device_info"] = data["device_info"]
                    if "package_info" not in test_results or not isinstance(
                        test_results.get("package_info"), dict
                    ):
                        if isinstance(data.get("package_info"), dict):
                            test_results["package_info"] = data["package_info"]

                    # 合并 metadata：以 JSON 中 metadata 为准
                    metadata = data.get("metadata") or {}
                    if isinstance(metadata, dict):
                        mr = test_results.setdefault("metadata", {})
                        if isinstance(mr, dict):
                            mr.update(metadata)
                else:
                    # 类型 B 或未知：仅含实时快照信息或旧格式，不包含完整测试结果，拒绝重构
                    return (
                        False,
                        f"重构失败: 报告 JSON 中不包含完整测试结果（可能为旧版实时快照），未修改原报告 {os.path.basename(report_path)}",
                    )
            except Exception as e:
                logging.warning("读取报告伴生 JSON 失败 %s: %s", json_path, e)
                return (
                    False,
                    f"重构失败: 读取报告 JSON 失败（{e}），未修改原报告 {os.path.basename(report_path)}",
                )
        else:
            # 无 JSON 时构造最小结构（通常为极旧报告），保守按无 tests 处理
            sn = filename_info.get("device_sn_short") or "unknown"
            test_results = {
                "device_info": {"sn": sn},
                "package_info": {},
                "tests": {},
                "metadata": {},
            }

        # 补全/推断 run_log_dir
        _ensure_run_log_dir(test_results, filename_info)

        # 无法找到性能采样文件时，不重构，保持原报告
        if not _has_performance_sampling(test_results, filename_info):
            return (
                False,
                f"重构失败: 未找到性能采样文件 performance_sampling.jsonl（未修改原报告 {os.path.basename(report_path)}）",
            )

        # 没有 tests 结构时，不重构，避免生成空白报告
        tests_obj = test_results.get("tests")
        if not isinstance(tests_obj, dict) or not tests_obj:
            return (
                False,
                f"重构失败: 报告 JSON 中缺少 tests 结果（可能为旧版实时快照），未修改原报告 {os.path.basename(report_path)}",
            )

        # 判断是否阶段性报告
        is_intermediate = False
        meta = test_results.get("metadata") or {}
        if isinstance(meta, dict):
            if meta.get("is_intermediate"):
                is_intermediate = True
            else:
                status = str(meta.get("report_status", "")).lower()
                if status == "intermediate":
                    is_intermediate = True
        if not is_intermediate:
            base = os.path.splitext(os.path.basename(report_path))[0]
            if "_intermediate" in base:
                is_intermediate = True

        gen = StabilityReportGenerator()
        try:
            html = gen._build_html_content(test_results, is_intermediate=is_intermediate)
        except Exception as e:
            logging.exception("使用 StabilityReportGenerator 构建 HTML 失败: %s", e)
            return False, f"重构失败: 构建 HTML 报告出错（{e}）"

        # 备份原文件并写入新内容
        try:
            bak_path = report_path + ".bak"
            Path(bak_path).write_bytes(Path(report_path).read_bytes())
        except Exception as e:
            logging.warning("备份原报告失败 %s: %s", report_path, e)
            # 备份失败时，为了安全起见，不继续覆盖
            return False, f"重构失败: 备份原报告失败（{e}），未修改原文件"

        try:
            Path(report_path).write_text(html, encoding="utf-8")
        except Exception as e:
            logging.exception("写入重构后报告失败 %s: %s", report_path, e)
            return (
                False,
                f"重构失败: 写入新报告失败（{e}），可使用同目录下 .bak 文件手动恢复",
            )

        return (
            True,
            f"报告重构成功: {os.path.basename(report_path)}（已在同目录生成备份 .bak）",
        )
    except Exception as e:
        logging.exception("重构报告过程中发生未预期异常: %s", e)
        return False, f"重构失败: 未预期异常（{e}）"

