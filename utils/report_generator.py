#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import logging
from datetime import datetime
from typing import Dict, Any, List
try:
    import matplotlib.pyplot as plt
    import pandas as pd
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class StabilityReportGenerator:
    """
    稳定性测试报告生成器
    生成详细的HTML和JSON格式报告
    """

    def __init__(self):
        self.template_dir = "templates"
        self.output_dir = "reports"
        os.makedirs(self.output_dir, exist_ok=True)

    def generate_comprehensive_report(self, test_results: Dict[str, Any]) -> str:
        """
        生成综合测试报告

        Args:
            test_results: 测试结果数据

        Returns:
            报告文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_filename = f"stability_report_{timestamp}"

        # 生成JSON报告
        json_path = self._generate_json_report(test_results, base_filename)

        # 生成HTML报告
        html_path = self._generate_html_report(test_results, base_filename)

        # 生成图表
        self._generate_charts(test_results, base_filename)

        logging.info(f"测试报告生成完成: {html_path}")
        return html_path

    def _generate_json_report(self, test_results: Dict[str, Any], base_filename: str) -> str:
        """生成JSON格式报告"""
        json_path = os.path.join(self.output_dir, f"{base_filename}.json")

        report_data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'generator_version': '1.0.0',
                'test_framework': 'car_stability_test'
            },
            'summary': self._generate_summary(test_results),
            'detailed_results': test_results,
            'analysis': self._generate_analysis(test_results)
        }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logging.info(f"JSON报告已生成: {json_path}")
        return json_path

    def _generate_html_report(self, test_results: Dict[str, Any], base_filename: str) -> str:
        """生成HTML格式报告"""
        html_path = os.path.join(self.output_dir, f"{base_filename}.html")

        html_content = self._build_html_content(test_results)

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

        # 系统健壮性总结
        if 'system_robustness' in tests:
            robust_result = tests['system_robustness']
            summary['test_overview']['system_robustness'] = {
                'duration_hours': robust_result.get('duration_hours', 0),
                'total_crashes': robust_result.get('crashes', 0),
                'total_anrs': robust_result.get('anrs', 0),
                'status': self._evaluate_robustness_status(robust_result)
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

            summary['test_overview']['performance'] = {
                'cold_start_time': self._summarize_performance_metric(
                    perf_tests.get('cold_start_time', {}), 'cold_start_time'
                ),
                'response_delay': self._summarize_performance_metric(
                    perf_tests.get('response_delay', {}), 'response_delay'
                ),
                'resource_usage': self._summarize_resource_usage(
                    perf_tests.get('resource_usage', {})
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
            if module_name == 'system_robustness':
                pass_rates['system_robustness'] = 1.0 if module_data.get('status') == 'PASS' else 0.0
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
            resource = perf_tests.get('resource_usage', {})
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

        resource_usage = perf_tests.get('resource_usage', {})
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

    def _build_html_content(self, test_results: Dict[str, Any]) -> str:
        """构建HTML内容"""
        summary = self._generate_summary(test_results)

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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>车载端侧应用稳定性测试报告</h1>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>设备: {summary['device_info'].get('model', 'Unknown')} ({summary['device_info'].get('sn', 'Unknown')})</p>
            <p>应用: {summary['package_info'].get('name', 'Unknown')}</p>
        </div>

        <div class="summary-grid">
            {self._build_summary_cards_html(summary)}
        </div>

        {self._build_detailed_results_html(test_results)}

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
            if module_name == 'system_robustness':
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

        return html

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
        resource_usage = perf_tests.get('resource_usage', {})
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