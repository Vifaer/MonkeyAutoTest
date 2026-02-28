#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Monkey 模式压力测试
使用 pytest 框架实现长时间压力测试
"""

import pytest
import logging
from utils.stability_test import TestModule


@pytest.mark.monkey_stress
@pytest.mark.stability
@pytest.mark.slow
@pytest.mark.requires_device
class TestSystemRobustness:
    """Monkey 模式压力测试类"""
    
    @pytest.mark.stability_smoke
    def test_long_stress_test(self, stability_framework):
        """长时间压力测试（GUI入口：仅运行此用例）"""
        # 运行Monkey 模式压力测试
        result = stability_framework.run_monkey_stress()
        
        # 断言测试结果
        assert 'crashes' in result, "测试结果缺少崩溃信息"
        assert 'anrs' in result, "测试结果缺少ANR信息"
        
        # 根据测试时长获取可接受的崩溃和ANR次数
        duration_hours = stability_framework.config.get('long_stress', {}).get('duration_hours', 12)
        max_crashes = self._get_acceptable_crash_count(duration_hours)
        max_anrs = self._get_acceptable_anr_count(duration_hours)
        
        crashes = result.get('crashes', 0)
        anrs = result.get('anrs', 0)
        
        assert crashes <= max_crashes, \
            f"崩溃次数过多: {crashes} > {max_crashes} (测试时长: {duration_hours}小时)"
        assert anrs <= max_anrs, \
            f"ANR次数过多: {anrs} > {max_anrs} (测试时长: {duration_hours}小时)"
        
        logging.info(f"Monkey 模式压力测试完成: 崩溃 {crashes} 次, ANR {anrs} 次")
    
    @pytest.mark.parametrize("duration_hours", [1, 12, 24])
    @pytest.mark.skip(reason="参数化测试，GUI模式下不运行，仅用于CI/CD")
    def test_stress_test_duration(self, stability_framework, duration_hours):
        """不同时长的压力测试（参数化，仅用于CI/CD，GUI模式下跳过）"""
        # 修改配置中的测试时长
        stability_framework.config['long_stress']['duration_hours'] = duration_hours
        
        result = stability_framework.run_monkey_stress()
        
        max_crashes = self._get_acceptable_crash_count(duration_hours)
        max_anrs = self._get_acceptable_anr_count(duration_hours)
        
        crashes = result.get('crashes', 0)
        anrs = result.get('anrs', 0)
        
        assert crashes <= max_crashes, \
            f"崩溃次数过多: {crashes} > {max_crashes}"
        assert anrs <= max_anrs, \
            f"ANR次数过多: {anrs} > {max_anrs}"
    
    def _get_acceptable_crash_count(self, duration_hours):
        """根据测试时长获取可接受的崩溃次数"""
        if duration_hours <= 1:
            return 0  # 1小时内不允许崩溃
        elif duration_hours <= 12:
            return 2  # 12小时内最多2次崩溃
        else:
            return 5  # 24小时内最多5次崩溃
    
    def _get_acceptable_anr_count(self, duration_hours):
        """根据测试时长获取可接受的ANR次数"""
        if duration_hours <= 1:
            return 0  # 1小时内不允许ANR
        elif duration_hours <= 12:
            return 3  # 12小时内最多3次ANR
        else:
            return 8  # 24小时内最多8次ANR
