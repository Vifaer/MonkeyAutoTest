#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
稳定性/压力测试服务层。

封装：
- 从 CLI/GUI 传入的参数构建 StabilityTestPlan
- 基于测试计划构建 pytest 参数
- 调用 pytest 执行稳定性/压力测试，并返回统一的结果概要

现阶段主要由 main.py/GUI 委托调用，后续可逐步替代散落各处的 params 字典逻辑。
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List

from core.domain.test_plan import StabilityTestPlan, ModuleSelection
from core.domain.test_result import TestResultSummary


class StabilityTestService:
    """稳定性测试服务入口。"""

    @staticmethod
    def plan_from_params(params: Dict[str, Any]) -> StabilityTestPlan:
        """从现有的 params 字典构建 StabilityTestPlan（向后兼容）。"""
        sn_list = params.get("sn_list") or []
        if isinstance(sn_list, str):
            sn_list = sn_list.split()

        duration = params.get("duration", 12)
        try:
            duration_hours = float(duration)
        except Exception:
            duration_hours = 12.0

        modules = ModuleSelection(
            monkey_stress="monkey_stress" in params.get("enabled_modules", []),
            exception_recovery="exception_recovery" in params.get("enabled_modules", []),
            performance_all="performance_all" in params.get("enabled_modules", []),
            performance_response="performance_response" in params.get("enabled_modules", []),
            performance_resource="performance_resource" in params.get("enabled_modules", []),
            broadcast_stress="broadcast_stress" in params.get("enabled_modules", []),
            tts_stress="tts_stress" in params.get("enabled_modules", []),
        )

        plan = StabilityTestPlan(
            sn_list=list(sn_list),
            duration_hours=duration_hours,
            package_name=params.get("package_name") or None,
            apk_path=params.get("apk_path") or "",
            apk_url=params.get("apk_url") or "",
            use_mock_server=params.get("use_mock_server", True),
            use_network_proxy=params.get("use_network_proxy", True),
            network_method=params.get("network_method", "root"),
            establish_baseline=params.get("establish_baseline", False),
            compare_baseline=params.get("compare_baseline", False),
            modular_enabled=params.get("modular_enabled", False),
            modules=modules,
            smoke_only=params.get("smoke_only", False),
            extra={k: v for k, v in params.items() if k not in {"sn_list", "duration"}},
        )
        return plan

    @staticmethod
    def build_pytest_args(plan: StabilityTestPlan) -> List[str]:
        """
        基于 StabilityTestPlan 构建 pytest 命令行参数。

        逻辑与原 main.build_pytest_args 基本保持一致，方便 CLI 与 GUI 复用。
        """
        # 基础 pytest 目标
        test_target = "tests/"
        if plan.smoke_only:
            test_target = "tests/integration/"
        if plan.modular_enabled:
            # 模块化稳定性：单一 runner 入口，根据参数执行模块
            test_target = "tests/integration/test_modular_runner.py"

        # 模块化测试时由 report_generator 写入单一综合报告，不在此处添加 pytest-html
        reports_dir = "reports"
        os.makedirs(reports_dir, exist_ok=True)
        pytest_args: List[str] = [test_target, "-v", "--tb=short"]

        if not plan.modular_enabled:
            mode = plan.extra.get("mode", "test")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_report_name = f"pytest_{mode}_{ts}.html"
            html_report_path = os.path.join(reports_dir, html_report_name)
            pytest_args.extend([f"--html={html_report_path}", "--self-contained-html"])

        # 设备序列号（目前只取首个，与旧逻辑保持一致）
        if plan.sn_list:
            pytest_args.extend(["--device-sn", plan.sn_list[0]])

        # 测试应用来源：优先包名，其次 APK 路径/URL
        if plan.package_name:
            pytest_args.extend(["--package-name", plan.package_name])
        elif plan.apk_path:
            pytest_args.extend(["--apk-path", plan.apk_path])
        elif plan.apk_url:
            pytest_args.extend(["--apk-url", plan.apk_url])

        MODULE_ARG_MAP = {
            "monkey_stress": "--module-robustness",
            "exception_recovery": "--module-recovery",
            "performance_all": "--module-performance",
            "performance_response": "--module-response",
            "performance_resource": "--module-resource",
            "broadcast_stress": "--module-broadcast",
            "tts_stress": "--module-tts",
        }

        if plan.modular_enabled:
            enabled_modules = plan.enabled_modules
            for module in enabled_modules:
                arg = MODULE_ARG_MAP.get(module)
                if arg:
                    pytest_args.append(arg)
        else:
            # 完整测试套件：运行所有稳定性测试
            if plan.smoke_only:
                pytest_args.extend(["-m", "stability_smoke"])
            else:
                pytest_args.extend(["-m", "stability"])

        # 基线选项
        if plan.establish_baseline:
            pytest_args.append("--establish-baseline")
        if plan.compare_baseline:
            pytest_args.append("--compare-baseline")

        # 长时间压力测试时长（小时），通过 pytest 自定义参数传递给测试配置
        try:
            pytest_args.extend(["--duration-hours", str(float(plan.duration_hours))])
        except Exception:
            # 如果转换失败则忽略，由测试侧使用默认值
            pass

        # 直接使用 Fallback 事件注入（跳过 monkey 命令）
        if plan.extra.get("use_fallback_only", False):
            pytest_args.append("--use-fallback-only")

        return pytest_args

    def run_with_pytest(self, plan: StabilityTestPlan) -> TestResultSummary:
        """使用 pytest 执行稳定性测试并返回结果概要。"""
        import pytest  # type: ignore
        import sys

        pytest_args = self.build_pytest_args(plan)
        logging.info("准备执行稳定性测试，计划: %s", asdict(plan))
        logging.info("pytest 参数: %s", " ".join(pytest_args))

        try:
            exit_code = pytest.main(pytest_args)
            success = exit_code == 0
            # 此处无法精确获知 HTML 报告路径（模块化模式下由 report_generator 生成），
            # 先返回 None，后续可结合报告管理服务补全。
            return TestResultSummary(success=success, exit_code=exit_code, html_report_path=None)
        except ImportError:
            msg = (
                "pytest 未安装，请运行 "
                "'pip install pytest pytest-html pytest-cov pytest-timeout pytest-xdist' 安装所需依赖"
            )
            logging.error(msg)
            return TestResultSummary(success=False, exit_code=-1, error_message=msg)
        except SystemExit as exc:
            # 某些情况下 pytest.main 可能触发 SystemExit，这里统一收口
            code = getattr(exc, "code", 1) or 1
            logging.error("pytest 执行触发 SystemExit，退出码: %s", code)
            return TestResultSummary(success=False, exit_code=code, error_message=str(exc))


__all__ = ["StabilityTestService"]

