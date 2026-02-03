#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
性能基线管理器
建立、保存和对比性能基线数据
"""

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import statistics


class BaselineManager:
    """
    性能基线管理器
    负责建立、保存和对比性能基线数据
    """

    def __init__(self, baseline_dir="baselines"):
        self.baseline_dir = baseline_dir
        os.makedirs(baseline_dir, exist_ok=True)
        self.baseline_file = os.path.join(baseline_dir, "performance_baseline.json")

    def establish_baseline(self, test_results: Dict[str, Any], version: str) -> str:
        """
        建立性能基线

        Args:
            test_results: 测试结果数据
            version: 应用版本

        Returns:
            基线文件路径
        """
        logging.info(f"为版本 {version} 建立性能基线")

        baseline_data = {
            'metadata': {
                'version': version,
                'established_at': datetime.now().isoformat(),
                'baseline_manager_version': '1.0.0'
            },
            'performance_metrics': self._extract_performance_metrics(test_results),
            'stability_metrics': self._extract_stability_metrics(test_results),
            'thresholds': self._calculate_thresholds(test_results)
        }

        # 保存基线数据
        with open(self.baseline_file, 'w', encoding='utf-8') as f:
            json.dump(baseline_data, f, indent=2, ensure_ascii=False)

        logging.info(f"性能基线已建立: {self.baseline_file}")
        return self.baseline_file

    def compare_with_baseline(self, test_results: Dict[str, Any], version: str) -> Dict[str, Any]:
        """
        与基线进行对比

        Args:
            test_results: 当前测试结果
            version: 应用版本

        Returns:
            对比结果
        """
        if not os.path.exists(self.baseline_file):
            logging.warning("未找到性能基线文件，无法进行对比")
            return {
                'comparison_available': False,
                'reason': 'baseline_not_found'
            }

        # 加载基线数据
        with open(self.baseline_file, 'r', encoding='utf-8') as f:
            baseline_data = json.load(f)

        comparison_result = {
            'comparison_available': True,
            'baseline_version': baseline_data['metadata']['version'],
            'baseline_established': baseline_data['metadata']['established_at'],
            'current_version': version,
            'comparison_time': datetime.now().isoformat(),
            'performance_comparison': {},
            'stability_comparison': {},
            'overall_assessment': 'unknown'
        }

        # 对比性能指标
        current_metrics = self._extract_performance_metrics(test_results)
        baseline_metrics = baseline_data['performance_metrics']

        comparison_result['performance_comparison'] = self._compare_performance_metrics(
            current_metrics, baseline_metrics, baseline_data['thresholds']
        )

        # 对比稳定性指标
        current_stability = self._extract_stability_metrics(test_results)
        baseline_stability = baseline_data['stability_metrics']

        comparison_result['stability_comparison'] = self._compare_stability_metrics(
            current_stability, baseline_stability
        )

        # 总体评估
        comparison_result['overall_assessment'] = self._assess_overall_status(comparison_result)

        return comparison_result

    def _extract_performance_metrics(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """提取性能指标"""
        metrics = {}

        if 'tests' in test_results and 'performance' in test_results['tests']:
            perf_tests = test_results['tests']['performance']

            # 冷启动时间
            if 'cold_start_time' in perf_tests:
                cold_start = perf_tests['cold_start_time']
                metrics['cold_start_time'] = {
                    'average': cold_start.get('average_time', 0),
                    'min': cold_start.get('min_time', 0),
                    'max': cold_start.get('max_time', 0),
                    'pass_rate': cold_start.get('pass_rate', 0)
                }

            # 响应延迟
            if 'response_delay' in perf_tests:
                response_delay = perf_tests['response_delay']
                metrics['response_delay'] = {
                    'average': response_delay.get('average_delay', 0),
                    'min': response_delay.get('min_delay', 0),
                    'max': response_delay.get('max_delay', 0),
                    'pass_rate': response_delay.get('pass_rate', 0)
                }

            # 资源消耗
            if 'resource_usage' in perf_tests:
                resource_usage = perf_tests['resource_usage']
                metrics['resource_usage'] = {
                    'cpu_foreground_avg': resource_usage.get('cpu_foreground', {}).get('average', 0),
                    'cpu_foreground_peak': resource_usage.get('cpu_foreground', {}).get('peak', 0),
                    'cpu_background_avg': resource_usage.get('cpu_background', {}).get('average', 0),
                    'cpu_background_peak': resource_usage.get('cpu_background', {}).get('peak', 0),
                    'memory_pss_avg': resource_usage.get('memory_pss', {}).get('average', 0),
                    'memory_pss_peak': resource_usage.get('memory_pss', {}).get('peak', 0),
                    'memory_leak_detected': resource_usage.get('memory_pss', {}).get('memory_leak_detected', False)
                }

        return metrics

    def _extract_stability_metrics(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """提取稳定性指标"""
        metrics = {}

        if 'tests' in test_results:
            tests = test_results['tests']

            # 系统健壮性
            if 'system_robustness' in tests:
                robust_result = tests['system_robustness']
                metrics['system_robustness'] = {
                    'crashes': robust_result.get('crashes', 0),
                    'anrs': robust_result.get('anrs', 0),
                    'test_duration_hours': robust_result.get('duration_hours', 0)
                }

            # 异常恢复
            if 'exception_recovery' in tests:
                recovery_tests = tests['exception_recovery']
                if 'scenarios' in recovery_tests:
                    scenarios = recovery_tests['scenarios']
                    metrics['exception_recovery'] = {
                        'network_disconnect_tests': len([s for s in scenarios if s.get('scenario') == 'network_disconnect']),
                        'weak_network_tests': len([s for s in scenarios if s.get('scenario') == 'weak_network']),
                        'data_exception_tests': len([s for s in scenarios if 'data' in s.get('scenario', '')])
                    }

        return metrics

    def _calculate_thresholds(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """计算性能阈值"""
        thresholds = {
            'cold_start_time_max': 3.0,  # 3秒
            'response_delay_max': 1.5,   # 1.5秒
            'cpu_foreground_max': 30.0,  # 30%
            'cpu_background_max': 1.0,   # 1%
            'memory_growth_threshold': 10.0  # 10MB
        }

        # 从测试结果中动态调整阈值（如果需要）
        metrics = self._extract_performance_metrics(test_results)

        if 'cold_start_time' in metrics:
            # 设置为平均值的120%作为阈值
            avg_time = metrics['cold_start_time']['average']
            if avg_time > 0:
                thresholds['cold_start_time_max'] = avg_time * 1.2

        return thresholds

    def _compare_performance_metrics(self, current: Dict[str, Any],
                                   baseline: Dict[str, Any],
                                   thresholds: Dict[str, Any]) -> Dict[str, Any]:
        """对比性能指标"""
        comparison = {}

        # 冷启动时间对比
        if 'cold_start_time' in current and 'cold_start_time' in baseline:
            comparison['cold_start_time'] = self._compare_metric(
                current['cold_start_time']['average'],
                baseline['cold_start_time']['average'],
                thresholds.get('cold_start_time_max', 3.0),
                'lower_better'  # 数值越低越好
            )

        # 响应延迟对比
        if 'response_delay' in current and 'response_delay' in baseline:
            comparison['response_delay'] = self._compare_metric(
                current['response_delay']['average'],
                baseline['response_delay']['average'],
                thresholds.get('response_delay_max', 1.5),
                'lower_better'
            )

        # CPU使用率对比
        if 'resource_usage' in current and 'resource_usage' in baseline:
            comparison['cpu_foreground'] = self._compare_metric(
                current['resource_usage']['cpu_foreground_avg'],
                baseline['resource_usage']['cpu_foreground_avg'],
                thresholds.get('cpu_foreground_max', 30.0),
                'lower_better'
            )

        return comparison

    def _compare_stability_metrics(self, current: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
        """对比稳定性指标"""
        comparison = {}

        # 崩溃和ANR对比（数值越低越好）
        if 'system_robustness' in current and 'system_robustness' in baseline:
            comparison['crashes'] = self._compare_metric(
                current['system_robustness']['crashes'],
                baseline['system_robustness']['crashes'],
                0,  # 理想值为0
                'lower_better'
            )
            comparison['anrs'] = self._compare_metric(
                current['system_robustness']['anrs'],
                baseline['system_robustness']['anrs'],
                0,
                'lower_better'
            )

        return comparison

    def _compare_metric(self, current_value: float, baseline_value: float,
                       threshold: float, trend: str) -> Dict[str, Any]:
        """对比单个指标"""
        if trend == 'lower_better':
            # 数值越低越好
            if current_value <= threshold and baseline_value <= threshold:
                # 都在正常范围内
                if current_value <= baseline_value:
                    status = 'improved'
                    change_percent = ((baseline_value - current_value) / baseline_value * 100) if baseline_value > 0 else 0
                else:
                    status = 'degraded'
                    change_percent = ((current_value - baseline_value) / baseline_value * 100) if baseline_value > 0 else 0
            elif current_value <= threshold:
                status = 'improved'
                change_percent = float('inf')  # 从异常到正常
            else:
                status = 'degraded'
                change_percent = float('-inf')  # 仍然异常或更差
        else:
            # 数值越高越好（如果有这种指标）
            status = 'unknown'
            change_percent = 0

        return {
            'current_value': current_value,
            'baseline_value': baseline_value,
            'threshold': threshold,
            'status': status,
            'change_percent': change_percent,
            'within_threshold': current_value <= threshold
        }

    def _assess_overall_status(self, comparison_result: Dict[str, Any]) -> str:
        """评估总体状态"""
        perf_comparison = comparison_result.get('performance_comparison', {})
        stability_comparison = comparison_result.get('stability_comparison', {})

        # 检查是否有严重退化
        degraded_count = 0
        total_metrics = 0

        for metric_name, metric_data in perf_comparison.items():
            total_metrics += 1
            if metric_data.get('status') == 'degraded':
                degraded_count += 1

        for metric_name, metric_data in stability_comparison.items():
            total_metrics += 1
            if metric_data.get('status') == 'degraded':
                degraded_count += 1

        if degraded_count == 0:
            return 'excellent'  # 没有退化
        elif degraded_count / total_metrics <= 0.3:
            return 'good'  # 少量退化
        elif degraded_count / total_metrics <= 0.7:
            return 'concerning'  # 中等退化
        else:
            return 'critical'  # 大量退化

    def list_baselines(self) -> List[Dict[str, Any]]:
        """列出所有可用的基线"""
        baselines = []

        if os.path.exists(self.baseline_file):
            try:
                with open(self.baseline_file, 'r', encoding='utf-8') as f:
                    baseline_data = json.load(f)
                    baselines.append({
                        'version': baseline_data['metadata']['version'],
                        'established_at': baseline_data['metadata']['established_at'],
                        'file_path': self.baseline_file
                    })
            except Exception as e:
                logging.error(f"读取基线文件失败: {str(e)}")

        return baselines

    def export_baseline_report(self, comparison_result: Dict[str, Any], output_path: str) -> str:
        """导出基线对比报告"""
        report = {
            'report_type': 'baseline_comparison',
            'generated_at': datetime.now().isoformat(),
            'comparison_data': comparison_result
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logging.info(f"基线对比报告已导出: {output_path}")
        return output_path