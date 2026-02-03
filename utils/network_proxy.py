#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import threading
import logging
from utils.timeout_command import run as run_cmd


class NetworkProxyController:
    """
    网络代理控制器
    支持Charles Proxy和mitmproxy，用于网络异常测试
    """

    def __init__(self, device_sn, proxy_type='mitmproxy'):
        self.device_sn = device_sn
        self.proxy_type = proxy_type  # 'mitmproxy' 或 'charles'
        self.proxy_process = None
        self.cert_installed = False

    def start_proxy(self, host='127.0.0.1', port=8080, script_path=None):
        """
        启动网络代理

        Args:
            host: 代理服务器地址
            port: 代理服务器端口
            script_path: mitmproxy脚本路径（用于自定义处理）
        """
        logging.info(f"启动{self.proxy_type}代理服务器")

        if self.proxy_type == 'mitmproxy':
            self._start_mitmproxy(host, port, script_path)
        elif self.proxy_type == 'charles':
            self._start_charles_proxy()
        else:
            raise ValueError(f"不支持的代理类型: {self.proxy_type}")

        # 等待代理启动
        time.sleep(3)

        # 配置设备代理设置
        self._configure_device_proxy(host, port)

        # 安装证书（如果需要）
        self._install_certificate()

        logging.info(f"{self.proxy_type}代理启动完成")

    def stop_proxy(self):
        """停止网络代理"""
        logging.info(f"停止{self.proxy_type}代理服务器")

        # 停止代理进程
        if self.proxy_process:
            self.proxy_process.terminate()
            self.proxy_process.wait()
            self.proxy_process = None

        # 重置设备代理设置
        self._reset_device_proxy()

        logging.info(f"{self.proxy_type}代理已停止")

    def _start_mitmproxy(self, host, port, script_path):
        """启动mitmproxy"""
        cmd = ['mitmproxy', '--mode', 'regular', '--listen-host', host, '--listen-port', str(port)]

        if script_path and os.path.exists(script_path):
            cmd.extend(['-s', script_path])

        try:
            self.proxy_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            logging.info(f"mitmproxy启动命令: {' '.join(cmd)}")
        except FileNotFoundError:
            logging.error("mitmproxy未安装，请先安装: pip install mitmproxy")
            raise

    def _start_charles_proxy(self):
        """启动Charles Proxy"""
        # Charles Proxy通常需要GUI启动，这里提供命令行方式
        # 注意：Charles Proxy可能需要许可证
        try:
            # 尝试启动Charles（假设已安装）
            cmd = ['charles', '--no-gui']  # 如果支持命令行模式
            self.proxy_process = subprocess.Popen(cmd)
        except FileNotFoundError:
            logging.error("Charles Proxy未找到，请确保已正确安装")
            raise

    def _configure_device_proxy(self, host, port):
        """配置Android设备代理设置"""
        # 设置全局HTTP代理
        cmd = f"adb -s {self.device_sn} shell settings put global http_proxy {host}:{port}"
        run_cmd(cmd)

        # 设置HTTPS代理（如果支持）
        cmd = f"adb -s {self.device_sn} shell settings put global https_proxy {host}:{port}"
        run_cmd(cmd)

        logging.info(f"设备代理设置已配置: {host}:{port}")

    def _reset_device_proxy(self):
        """重置设备代理设置"""
        cmd = f"adb -s {self.device_sn} shell settings put global http_proxy :0"
        run_cmd(cmd)

        cmd = f"adb -s {self.device_sn} shell settings put global https_proxy :0"
        run_cmd(cmd)

        logging.info("设备代理设置已重置")

    def _install_certificate(self):
        """安装代理证书到设备"""
        if self.cert_installed:
            return

        try:
            if self.proxy_type == 'mitmproxy':
                self._install_mitmproxy_cert()
            elif self.proxy_type == 'charles':
                self._install_charles_cert()

            self.cert_installed = True
        except Exception as e:
            logging.warning(f"证书安装失败: {str(e)}")

    def _install_mitmproxy_cert(self):
        """安装mitmproxy证书"""
        # 生成证书
        cert_path = os.path.expanduser('~/.mitmproxy/mitmproxy-ca-cert.pem')
        if not os.path.exists(cert_path):
            logging.warning("mitmproxy证书不存在，请先运行mitmproxy生成证书")
            return

        # 推送证书到设备
        device_cert_path = '/sdcard/mitmproxy-ca-cert.pem'
        cmd = f"adb -s {self.device_sn} push {cert_path} {device_cert_path}"
        run_cmd(cmd)

        # 安装证书
        cmd = f"adb -s {self.device_sn} shell certtool i {device_cert_path}"
        run_cmd(cmd)

        logging.info("mitmproxy证书已安装到设备")

    def _install_charles_cert(self):
        """安装Charles证书"""
        # Charles证书通常需要手动安装或通过特定方式
        logging.info("请手动安装Charles证书到设备")

    def enable_network_manipulation(self, config):
        """
        启用网络操作（延迟、丢包等）

        Args:
            config: 网络配置参数
                - delay: 延迟时间（毫秒）
                - loss: 丢包率（百分比）
                - bandwidth: 带宽限制
        """
        if self.proxy_type == 'mitmproxy':
            self._enable_mitmproxy_manipulation(config)
        else:
            logging.warning(f"{self.proxy_type}不支持网络操作功能")

    def _enable_mitmproxy_manipulation(self, config):
        """启用mitmproxy网络操作"""
        # 这里需要配合mitmproxy脚本来实现
        # 例如创建weak_network.py脚本来模拟网络条件
        script_content = self._generate_mitmproxy_script(config)

        script_path = 'weak_network.py'
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)

        # 如果代理已经在运行，需要重启
        if self.proxy_process:
            self.stop_proxy()
            self._start_mitmproxy('127.0.0.1', 8080, script_path)

    def _generate_mitmproxy_script(self, config):
        """生成mitmproxy脚本用于网络操作"""
        delay = config.get('delay', 0)
        loss = config.get('loss', 0)
        bandwidth = config.get('bandwidth', 0)

        script = f'''
from mitmproxy import http
import time
import random

class WeakNetwork:
    def __init__(self):
        self.delay = {delay} / 1000.0  # 转换为秒
        self.loss_rate = {loss} / 100.0
        self.bandwidth_limit = {bandwidth}  # bytes per second

    def request(self, flow: http.HTTPFlow) -> None:
        # 模拟网络延迟
        if self.delay > 0:
            time.sleep(self.delay)

        # 模拟丢包
        if random.random() < self.loss_rate:
            flow.response = http.HTTPResponse.make(
                504,
                b"Gateway Timeout - Simulated packet loss",
                {{"Content-Type": "text/plain"}}
            )
            return

        # 模拟带宽限制（简化实现）
        if self.bandwidth_limit > 0:
            # 这里可以实现带宽限制逻辑
            pass

addons = [WeakNetwork()]
'''

        return script


class NetworkConditionSimulator:
    """
    网络条件模拟器
    提供各种网络场景的模拟
    """

    def __init__(self, device_sn):
        self.device_sn = device_sn
        self.proxy_controller = NetworkProxyController(device_sn)

    def simulate_disconnect(self, duration_seconds=30):
        """
        模拟网络断开

        Args:
            duration_seconds: 断开持续时间（秒）
        """
        logging.info(f"模拟网络断开 {duration_seconds} 秒")

        # 断开网络
        self._disable_network()

        # 等待指定时间
        time.sleep(duration_seconds)

        # 恢复网络
        self._enable_network()

        logging.info("网络断开模拟完成")

    def simulate_weak_network(self, config, duration_seconds=60):
        """
        模拟弱网环境

        Args:
            config: 弱网配置 {'delay': ms, 'loss': %, 'bandwidth': bps}
            duration_seconds: 模拟持续时间
        """
        logging.info(f"模拟弱网环境 {duration_seconds} 秒")

        # 启动代理并配置弱网
        self.proxy_controller.start_proxy()
        self.proxy_controller.enable_network_manipulation(config)

        # 等待模拟时间
        time.sleep(duration_seconds)

        # 停止代理
        self.proxy_controller.stop_proxy()

        logging.info("弱网模拟完成")

    def simulate_high_latency(self, latency_ms=1000, duration_seconds=60):
        """
        模拟高延迟网络

        Args:
            latency_ms: 延迟时间（毫秒）
            duration_seconds: 模拟持续时间
        """
        config = {'delay': latency_ms, 'loss': 0, 'bandwidth': 0}
        self.simulate_weak_network(config, duration_seconds)

    def simulate_packet_loss(self, loss_rate=10, duration_seconds=60):
        """
        模拟丢包网络

        Args:
            loss_rate: 丢包率（百分比）
            duration_seconds: 模拟持续时间
        """
        config = {'delay': 0, 'loss': loss_rate, 'bandwidth': 0}
        self.simulate_weak_network(config, duration_seconds)

    def simulate_slow_network(self, bandwidth_kbps=56, duration_seconds=60):
        """
        模拟慢速网络（拨号上网速度）

        Args:
            bandwidth_kbps: 带宽限制（Kbps）
            duration_seconds: 模拟持续时间
        """
        config = {'delay': 200, 'loss': 2, 'bandwidth': bandwidth_kbps * 1024}
        self.simulate_weak_network(config, duration_seconds)

    def _disable_network(self):
        """断开设备网络"""
        # 关闭WiFi
        cmd = f"adb -s {self.device_sn} shell svc wifi disable"
        run_cmd(cmd)

        # 关闭移动数据
        cmd = f"adb -s {self.device_sn} shell svc data disable"
        run_cmd(cmd)

        logging.info("设备网络已断开")

    def _enable_network(self):
        """恢复设备网络"""
        # 开启WiFi
        cmd = f"adb -s {self.device_sn} shell svc wifi enable"
        run_cmd(cmd)

        # 开启移动数据
        cmd = f"adb -s {self.device_sn} shell svc data enable"
        run_cmd(cmd)

        logging.info("设备网络已恢复")


class NonRootNetworkSimulator:
    """
    非Root设备网络模拟器
    通过PC端网络控制实现，不需要设备root权限
    """

    def __init__(self, device_sn, method='pc_proxy'):
        """
        Args:
            device_sn: 设备序列号
            method: 模拟方法 ('pc_proxy', 'wifi_control', 'app_simulation')
        """
        self.device_sn = device_sn
        self.method = method
        self.proxy_process = None
        self.simulation_thread = None
        self.is_simulating = False

    def simulate_disconnect(self, duration_seconds=30):
        """
        模拟网络断开（非Root方式）

        Args:
            duration_seconds: 断开持续时间（秒）
        """
        logging.info(f"使用{self.method}方法模拟网络断开 {duration_seconds} 秒")

        if self.method == 'pc_proxy':
            self._simulate_disconnect_via_proxy(duration_seconds)
        elif self.method == 'wifi_control':
            self._simulate_disconnect_via_wifi(duration_seconds)
        elif self.method == 'app_simulation':
            self._simulate_disconnect_via_app(duration_seconds)
        else:
            raise ValueError(f"不支持的模拟方法: {self.method}")

        logging.info("网络断开模拟完成")

    def simulate_weak_network(self, config, duration_seconds=60):
        """
        模拟弱网环境（非Root方式）

        Args:
            config: 弱网配置 {'delay': ms, 'loss': %, 'bandwidth': bps}
            duration_seconds: 模拟持续时间
        """
        logging.info(f"使用{self.method}方法模拟弱网环境 {duration_seconds} 秒")

        if self.method == 'pc_proxy':
            self._simulate_weak_network_via_proxy(config, duration_seconds)
        elif self.method == 'wifi_control':
            self._simulate_weak_network_via_wifi(config, duration_seconds)
        elif self.method == 'app_simulation':
            self._simulate_weak_network_via_app(config, duration_seconds)
        else:
            raise ValueError(f"不支持的模拟方法: {self.method}")

        logging.info("弱网模拟完成")

    def _simulate_disconnect_via_proxy(self, duration_seconds):
        """通过PC端代理模拟断网"""
        # 启动一个阻塞所有请求的代理服务器
        from utils.pc_proxy_simulator import PCProxySimulator
        proxy = PCProxySimulator(self.device_sn)

        # 配置设备使用PC作为代理
        proxy.setup_device_proxy()

        # 启动断网模拟
        proxy.simulate_disconnect(duration_seconds)

        # 清理代理设置
        proxy.cleanup_proxy()

    def _simulate_weak_network_via_proxy(self, config, duration_seconds):
        """通过PC端代理模拟弱网"""
        from utils.pc_proxy_simulator import PCProxySimulator
        proxy = PCProxySimulator(self.device_sn)

        # 配置设备使用PC作为代理
        proxy.setup_device_proxy()

        # 启动弱网模拟
        proxy.simulate_weak_network(config, duration_seconds)

        # 清理代理设置
        proxy.cleanup_proxy()

    def _simulate_disconnect_via_wifi(self, duration_seconds):
        """通过WiFi路由器控制模拟断网"""
        from utils.wifi_controller import WiFiController
        wifi_ctrl = WiFiController()

        # 断开设备的WiFi连接
        wifi_ctrl.disconnect_device(self.device_sn, duration_seconds)

    def _simulate_weak_network_via_wifi(self, config, duration_seconds):
        """通过WiFi路由器控制模拟弱网"""
        from utils.wifi_controller import WiFiController
        wifi_ctrl = WiFiController()

        # 配置WiFi路由器模拟弱网
        wifi_ctrl.simulate_weak_network_for_device(self.device_sn, config, duration_seconds)

    def _simulate_disconnect_via_app(self, duration_seconds):
        """通过应用内部模拟断网"""
        logging.info("应用内部网络断开模拟需要应用配合实现")
        logging.info("可以通过以下方式实现:")
        logging.info("1. 修改应用代码，添加网络开关控制")
        logging.info("2. 使用应用提供的开发者选项")
        logging.info("3. 通过ADB发送广播或修改应用配置")

        # 这里可以实现一些通用的应用控制方法
        # 例如：发送广播让应用进入离线模式
        self._send_app_network_broadcast("NETWORK_DISCONNECT")
        time.sleep(duration_seconds)
        self._send_app_network_broadcast("NETWORK_RECONNECT")

    def _simulate_weak_network_via_app(self, config, duration_seconds):
        """通过应用内部模拟弱网"""
        logging.info("应用内部弱网模拟需要应用配合实现")

        # 发送弱网配置广播
        self._send_app_network_broadcast("NETWORK_WEAK_CONFIG", config)
        time.sleep(duration_seconds)
        self._send_app_network_broadcast("NETWORK_NORMAL")

    def _send_app_network_broadcast(self, action, extras=None):
        """发送网络控制广播到应用"""
        package_name = self._get_current_app_package()

        cmd = f"adb -s {self.device_sn} shell am broadcast -a {action}"

        if package_name:
            cmd += f" -n {package_name}/.NetworkControlReceiver"

        if extras:
            for key, value in extras.items():
                cmd += f" --es {key} {str(value)}"

        try:
            run_cmd(cmd)
            logging.info(f"已发送网络控制广播: {action}")
        except Exception as e:
            logging.warning(f"发送广播失败: {str(e)}")

    def _get_current_app_package(self):
        """获取当前前台应用包名"""
        try:
            cmd = f"adb -s {self.device_sn} shell dumpsys window windows"
            result = run_cmd(cmd)

            if not isinstance(result, str):
                return None

            import re
            # 只在包含 mCurrentFocus/mFocusedApp 的行上解析包名
            for line in result.splitlines():
                if "mCurrentFocus" in line or "mFocusedApp" in line:
                    match = re.search(r'([a-zA-Z0-9_.]+)/[a-zA-Z0-9_.]+', line)
                    if match:
                        return match.group(1)
        except Exception as e:
            logging.warning(f"获取当前应用包名失败: {str(e)}")

        return None