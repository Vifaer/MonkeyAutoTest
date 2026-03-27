#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试结果（TestResult）领域模型。

目前作为 pytest/稳定性测试 的轻量总结对象，方便 GUI / CLI 统一处理结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class TestResultSummary:
    """稳定性测试结果概要。"""

    success: bool
    exit_code: int
    html_report_path: Optional[str] = None
    error_message: Optional[str] = None


__all__ = ["TestResultSummary"]

