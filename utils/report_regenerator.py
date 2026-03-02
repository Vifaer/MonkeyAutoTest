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


def _infer_start_end_time_from_perf_jsonl(run_log_dir: str) -> Dict[str, str]:
    """
    从 run_log_dir/performance_sampling.jsonl 推断 start_time/end_time（ISO 字符串）。
    仅用于重构“实时快照 JSON”这类缺少 start/end 的报告，便于报告查看器计算运行时间。
    """
    out: Dict[str, str] = {}
    if not run_log_dir or not os.path.isdir(run_log_dir):
        return out
    jsonl_path = os.path.join(run_log_dir, "performance_sampling.jsonl")
    if not os.path.isfile(jsonl_path):
        return out
    try:
        first_ts = ""
        last_ts = ""
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                ts = str(obj.get("timestamp") or "").strip()
                if not ts:
                    continue
                if not first_ts:
                    first_ts = ts
                last_ts = ts
        if first_ts:
            out["start_time"] = first_ts
        if last_ts:
            out["end_time"] = last_ts
    except Exception as e:
        logging.debug("从 performance_sampling.jsonl 推断时间失败 %s: %s", jsonl_path, e)
    return out


def _resolve_logs_root(device_sn: str, device_sn_short: str) -> str:
    """
    解析 logs 根目录。device_sn 可能是完整 SN 或短 SN（文件名取前8位）。
    若 logs/<device_sn> 不存在，尝试 logs/<prefix>* 前缀匹配（如 7ff80600 匹配 7ff80600xxxxxxxx）。
    """
    logs_base = os.path.join("logs", device_sn)
    if os.path.isdir(logs_base):
        return logs_base
    # 当 device_sn 来自文件名短格式时，尝试前缀匹配
    prefix = device_sn_short or device_sn
    if not prefix:
        return ""
    try:
        parent = os.path.dirname(logs_base)
        if not os.path.isdir(parent):
            return ""
        for name in os.listdir(parent):
            if name.startswith(prefix) and os.path.isdir(os.path.join(parent, name)):
                return os.path.join(parent, name)
    except Exception:
        pass
    return ""


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
    device_sn_short = filename_info.get("device_sn_short") or ""
    if not device_sn:
        device_sn = device_sn_short
    if not device_sn and not device_sn_short:
        return

    logs_root = _resolve_logs_root(device_sn, device_sn_short)
    if not logs_root or not os.path.isdir(logs_root):
        return

    # 从文件名时间戳提取可匹配部分（如 test_20260228_152840 -> 20260228, 20260228152840）
    ts = filename_info.get("timestamp") or ""
    ts_digits = "".join(c for c in ts if c.isdigit())  # 用于匹配 YYYYMMDDHHMMSS 格式目录名

    candidates = []
    for name in os.listdir(logs_root):
        full = os.path.join(logs_root, name)
        if not os.path.isdir(full):
            continue
        # 匹配：完整 ts 包含于目录名、或数字部分匹配（20260228152840 in name）
        if ts and ts in name:
            candidates.append(full)
        elif ts_digits and ts_digits in name:
            candidates.append(full)
        elif ts_digits and len(ts_digits) >= 8 and name.isdigit() and name.startswith(ts_digits[:8]):
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
    # 若都不存在，按 filename 的 project_key 优先创建对应模块，否则挂到 performance
    project_key = filename_info.get("project_key") or ""
    if project_key in preferred_keys:
        tests.setdefault(project_key, {})["run_log_dir"] = run_dir
    else:
        perf = tests.setdefault("performance", {})
        perf["run_log_dir"] = run_dir


def _find_run_log_dir_by_glob(test_results: Dict, filename_info: Dict[str, str]) -> str:
    """
    通过 glob 查找包含 performance_sampling.jsonl 的 run_log_dir。
    当 _ensure_run_log_dir 未能填充时用作兜底。
    """
    device_sn = (test_results.get("device_info") or {}).get("sn") or ""
    device_sn_short = filename_info.get("device_sn_short") or ""
    if not device_sn:
        device_sn = device_sn_short
    if not device_sn and not device_sn_short:
        return ""
    try:
        logs_dir = "logs"
        if not os.path.isdir(logs_dir):
            return ""
        # 精确匹配
        pattern = os.path.join(logs_dir, device_sn, "*", "performance_sampling.jsonl")
        matches = glob.glob(pattern)
        if matches:
            return os.path.dirname(max(matches, key=os.path.getmtime))
        # 前缀匹配
        prefix = device_sn_short or device_sn
        if prefix:
            for name in os.listdir(logs_dir):
                if name.startswith(prefix):
                    p = os.path.join(logs_dir, name, "*", "performance_sampling.jsonl")
                    matches = glob.glob(p)
                    if matches:
                        return os.path.dirname(max(matches, key=os.path.getmtime))
    except Exception:
        pass
    return ""


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
    device_sn_short = filename_info.get("device_sn_short") or ""
    if not device_sn:
        device_sn = device_sn_short
    if not device_sn and not device_sn_short:
        return False

    try:
        # 先精确匹配
        pattern = os.path.join("logs", device_sn, "*", "performance_sampling.jsonl")
        matches = glob.glob(pattern)
        if matches:
            return True
        # 再尝试前缀匹配（device_sn 为短格式时）
        prefix = device_sn_short or device_sn
        if prefix:
            logs_dir = "logs"
            if os.path.isdir(logs_dir):
                for name in os.listdir(logs_dir):
                    if name.startswith(prefix):
                        p = os.path.join(logs_dir, name, "*", "performance_sampling.jsonl")
                        matches = glob.glob(p)
                        if matches:
                            return True
    except Exception:
        pass
    return False


def _write_upgraded_json_sidecar(json_path: str, test_results: Dict) -> None:
    """
    将伴生 JSON 写为统一格式（至少包含 detailed_results），供报告查看器读取 start/end_time。
    注意：此函数仅在重构成功写入 HTML 前调用；写失败不影响主流程。
    """
    try:
        data = {
            "metadata": test_results.get("metadata") if isinstance(test_results.get("metadata"), dict) else {},
            "detailed_results": test_results,
        }
        Path(json_path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logging.debug("升级写入伴生 JSON 失败 %s: %s", json_path, e)


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
                    # 类型 C：实时快照 JSON（仅含 metadata/device_info/package_info），
                    # 尝试从 JSON 与文件名推断最小 test_results，再通过 _ensure_run_log_dir 补全 run_log_dir
                    if (
                        isinstance(data.get("device_info"), dict)
                        or isinstance(data.get("package_info"), dict)
                        or filename_info.get("device_sn_short")
                    ):
                        device_info = data.get("device_info")
                        if not isinstance(device_info, dict):
                            device_info = {}
                        if not device_info.get("sn") and filename_info.get("device_sn_short"):
                            device_info = dict(device_info)
                            device_info["sn"] = filename_info["device_sn_short"]
                        package_info = data.get("package_info") if isinstance(data.get("package_info"), dict) else {}
                        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
                        test_results = {
                            "device_info": device_info,
                            "package_info": package_info,
                            "tests": {},
                            "metadata": metadata or {},
                        }
                        # 继续执行 _ensure_run_log_dir 等后续流程
                    else:
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

        # 若 _ensure_run_log_dir 未填充 tests，尝试通过 glob 直接查找 performance_sampling.jsonl 并补全
        tests_obj = test_results.get("tests") or {}
        if not isinstance(tests_obj, dict) or not tests_obj:
            run_dir = _find_run_log_dir_by_glob(test_results, filename_info)
            if run_dir:
                project_key = filename_info.get("project_key") or ""
                preferred = (
                    "broadcast_stress", "tts_stress", "monkey_stress",
                    "performance", "exception_recovery", "system_robustness",
                )
                key = project_key if project_key in preferred else "performance"
                test_results.setdefault("tests", {})[key] = {"run_log_dir": run_dir}
                tests_obj = test_results.get("tests") or {}

        # 为“实时快照 JSON”补齐 start_time/end_time（用于报告查看器的运行时间显示）
        try:
            if isinstance(test_results.get("tests"), dict):
                any_run_dir = ""
                for _k, _v in (test_results.get("tests") or {}).items():
                    if isinstance(_v, dict) and _v.get("run_log_dir"):
                        any_run_dir = str(_v.get("run_log_dir"))
                        break
                inferred = _infer_start_end_time_from_perf_jsonl(any_run_dir)
                if inferred.get("start_time") and not test_results.get("start_time"):
                    test_results["start_time"] = inferred["start_time"]
                if inferred.get("end_time") and not test_results.get("end_time"):
                    test_results["end_time"] = inferred["end_time"]
        except Exception:
            pass

        # 无法找到性能采样文件时，不重构，保持原报告
        if not _has_performance_sampling(test_results, filename_info):
            return (
                False,
                f"重构失败: 未找到性能采样文件 performance_sampling.jsonl（未修改原报告 {os.path.basename(report_path)}）",
            )

        # 没有 tests 结构时，不重构，避免生成空白报告
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

        # 重构成功前，同步升级伴生 JSON（便于查看器计算运行时间）
        _write_upgraded_json_sidecar(json_path, test_results)

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

