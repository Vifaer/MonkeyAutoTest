#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
性能测试
使用 pytest 框架实现冷启动、响应延迟、资源消耗等性能测试
"""

import pytest
import logging


@pytest.mark.performance
@pytest.mark.stability
@pytest.mark.stability_smoke
@pytest.mark.requires_device
class TestPerformanceMetrics:
    """性能指标测试类"""
    
    def test_cold_start_time(self, stability_framework):
        """冷启动时间测试"""
        logging.info("开始冷启动时间测试...")
        
        performance = stability_framework.run_performance()
        
        # 检查测试结果结构
        assert 'tests' in performance, "性能测试结果结构不完整"
        
        cold_start = performance.get('tests', {}).get('cold_start_time', {})
        if cold_start:
            average_time = cold_start.get('average_time', 0)
            target_threshold = cold_start.get('target_threshold', 3.0)
            pass_rate = cold_start.get('pass_rate', 0)
            
            assert average_time <= target_threshold, \
                f"冷启动时间过长: {average_time:.2f}s > {target_threshold}s"
            assert pass_rate >= 0.8, \
                f"冷启动达标率过低: {pass_rate:.1%} < 80%"
        
        logging.info("冷启动时间测试完成")
    
    def test_response_delay(self, stability_framework):
        """响应延迟测试"""
        logging.info("开始响应延迟测试...")
        
        performance = stability_framework.run_performance()
        response_delay = performance.get('tests', {}).get('response_delay', {})
        
        if response_delay:
            average_delay = response_delay.get('average_delay', 0)
            target_threshold = response_delay.get('target_threshold', 1.5)
            pass_rate = response_delay.get('pass_rate', 0)
            
            assert average_delay <= target_threshold, \
                f"响应延迟过长: {average_delay:.2f}s > {target_threshold}s"
            assert pass_rate >= 0.85, \
                f"响应延迟达标率过低: {pass_rate:.1%} < 85%"
        
        logging.info("响应延迟测试完成")
    
    def test_cpu_usage_foreground(self, stability_framework):
        """前台CPU使用率测试"""
        logging.info("开始前台CPU使用率测试...")
        
        performance = stability_framework.run_performance()
        resource_usage = performance.get('tests', {}).get('resource_usage', {})
        cpu_fg = resource_usage.get('cpu_foreground', {})
        
        if cpu_fg:
            average = cpu_fg.get('average', 0)
            target_threshold = cpu_fg.get('target_threshold', 30.0)
            pass_rate = cpu_fg.get('pass_rate', 0)
            
            assert average <= target_threshold, \
                f"前台CPU使用率过高: {average:.1f}% > {target_threshold}%"
            assert pass_rate >= 0.9, \
                f"前台CPU达标率过低: {pass_rate:.1%} < 90%"
        
        logging.info("前台CPU使用率测试完成")
    
    def test_cpu_usage_background(self, stability_framework):
        """后台CPU使用率测试"""
        logging.info("开始后台CPU使用率测试...")
        
        performance = stability_framework.run_performance()
        resource_usage = performance.get('tests', {}).get('resource_usage', {})
        cpu_bg = resource_usage.get('cpu_background', {})
        
        if cpu_bg:
            average = cpu_bg.get('average', 0)
            target_threshold = cpu_bg.get('target_threshold', 1.0)
            pass_rate = cpu_bg.get('pass_rate', 0)
            
            assert average <= target_threshold, \
                f"后台CPU使用率过高: {average:.1f}% > {target_threshold}%"
            assert pass_rate >= 0.95, \
                f"后台CPU达标率过低: {pass_rate:.1%} < 95%"
        
        logging.info("后台CPU使用率测试完成")
    
    def test_memory_usage(self, stability_framework):
        """内存使用率测试"""
        logging.info("开始内存使用率测试...")
        
        performance = stability_framework.run_performance()
        resource_usage = performance.get('tests', {}).get('resource_usage', {})
        memory = resource_usage.get('memory_pss', {})
        
        if memory:
            memory_leak_detected = memory.get('memory_leak_detected', False)
            trend = memory.get('trend', 'unknown')
            
            assert not memory_leak_detected, "检测到内存泄漏"
            assert trend == 'stable', f"内存使用趋势不稳定: {trend}"
        
        logging.info("内存使用率测试完成")


@pytest.mark.performance
@pytest.mark.performance_response
@pytest.mark.stability
@pytest.mark.requires_device
class TestResponsePerformance:
    """响应性能测试类（仅响应相关）"""
    
    def test_cold_start_only(self, modular_framework):
        """仅测试冷启动时间"""
        from utils.performance_monitor import PerformanceMonitor
        
        perf_monitor = PerformanceMonitor(
            modular_framework.device,
            modular_framework.package,
            modular_framework.config['performance']
        )
        
        result = perf_monitor._test_cold_start_time()
        assert 'average_time' in result, "缺少平均启动时间"
        assert result['average_time'] <= result.get('target_threshold', 3.0), \
            f"冷启动时间过长: {result['average_time']:.2f}s"
    
    def test_response_delay_only(self, modular_framework):
        """仅测试响应延迟"""
        from utils.performance_monitor import PerformanceMonitor
        
        perf_monitor = PerformanceMonitor(
            modular_framework.device,
            modular_framework.package,
            modular_framework.config['performance']
        )
        
        result = perf_monitor._test_response_delay()
        assert 'average_delay' in result, "缺少平均响应延迟"
        assert result['average_delay'] <= result.get('target_threshold', 1.5), \
            f"响应延迟过长: {result['average_delay']:.2f}s"


@pytest.mark.performance
@pytest.mark.performance_resource
@pytest.mark.stability
@pytest.mark.requires_device
class TestResourceConsumption:
    """资源消耗测试类（仅资源相关）"""
    
    def test_resource_usage_only(self, modular_framework):
        """仅测试资源消耗"""
        from utils.performance_monitor import PerformanceMonitor
        
        perf_monitor = PerformanceMonitor(
            modular_framework.device,
            modular_framework.package,
            modular_framework.config['performance']
        )
        
        result = perf_monitor._test_resource_usage()
        assert 'cpu_foreground' in result, "缺少前台CPU数据"
        assert 'cpu_background' in result, "缺少后台CPU数据"
        assert 'memory_pss' in result, "缺少内存数据"
