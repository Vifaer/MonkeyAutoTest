#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
报告服务。

封装报告生成与重构能力，供 GUI、CLI 与稳定性测试使用。
过渡期内部委托给 utils.report_generator 与 utils.report_regenerator。
"""

from __future__ import annotations

from typing import Tuple

# 过渡期：core 可调用 utils 中尚未迁移的能力
from utils.report_regenerator import regenerate_report as _regenerate_report


def regenerate_report(report_path: str) -> Tuple[bool, str]:
    """
    使用最新模板重构单个 HTML 报告。

    仅在能够找到有效测试数据（JSON 或 performance_sampling.jsonl）时才真正重构，
    否则返回失败信息并保持原报告不变。

    Args:
        report_path: HTML 报告文件路径

    Returns:
        (成功标志, 消息字符串)
    """
    return _regenerate_report(report_path)


def create_report_generator():
    """
    创建报告生成器实例，用于实时报告与最终报告。

    Returns:
        StabilityReportGenerator 实例
    """
    from utils.report_generator import StabilityReportGenerator

    return StabilityReportGenerator()


__all__ = ["regenerate_report", "create_report_generator"]
