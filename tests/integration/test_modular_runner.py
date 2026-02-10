#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
模块化稳定性测试 Runner（GUI 入口）

- 由 main.build_pytest_args 在 modular_enabled 时指定为唯一 test_target。
- 通过 conftest.py 的 modular_framework fixture 读取 CLI 参数（--module-*、--duration-hours、--package-name 等）
  并在 runner 内部执行选定模块。
- ModularStabilityTest 内部会生成：实时报告（每分钟刷新同一份 HTML）、阶段性报告（默认每 30 分钟）、最终报告。
"""

import pytest
import logging


@pytest.mark.stability
@pytest.mark.stability_smoke
@pytest.mark.requires_device
def test_modular_stability_runner(modular_framework):
    """执行模块化稳定性测试（由 CLI 参数决定启用模块）"""
    logging.info("开始执行模块化稳定性测试 Runner")
    results = modular_framework.run_selected_tests()
    assert isinstance(results, dict)
    assert results.get("tests") is not None, "测试结果缺少 tests 字段"

