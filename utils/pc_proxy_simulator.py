#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import socket
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from utils.timeout_command import run as run_cmd


class PCProxySimulator:
    """
    PC端代理模拟器
    通过在PC上运行代理服务器来模拟网络条件，无需设备root权限
    """

    def __init__(self, device_sn, proxy_port=8888):
        self.device_sn = device_sn
        self.proxy_port = proxy_port
        self.proxy_server = None
        self.server_thread = None
        self.is_running = False

        # 网络模拟配置
        self.network_config = {
            'delay': 0,      # 延迟(ms)
            'loss': 0,       # 丢包率(%)
            'bandwidth': 0,  # 带宽限制(bps)
            'disconnect': False  # 是否断网
        }

    def setup_device_proxy(self):
        """配置设备使用PC作为代理"""
        # 获取PC的IP地址
        pc_ip = self._get_pc_ip()

        logging.info(f"配置设备使用PC代理: {pc_ip}:{self.proxy_port}")

        # 设置设备HTTP代理
        cmd = f"adb -s {self.device_sn} shell settings put global http_proxy {pc_ip}:{self.proxy_port}"
        run_cmd(cmd)

        # 设置设备HTTPS代理（如果支持）
        cmd = f"adb -s {self.device_sn} shell settings put global https_proxy {pc_ip}:{self.proxy_port}"
        run_cmd(cmd)

        logging.info("设备代理设置完成")

    def cleanup_proxy(self):
        """清理设备代理设置"""
        logging.info("清理设备代理设置")

        # 重置HTTP代理
        cmd = f"adb -s {self.device_sn} shell settings put global http_proxy :0"
        run_cmd(cmd)

        # 重置HTTPS代理
        cmd = f"adb -s {self.device_sn} shell settings put global https_proxy :0"
        run_cmd(cmd)

        # 停止代理服务器
        self.stop_proxy_server()

        logging.info("代理设置已清理")

    def simulate_disconnect(self, duration_seconds):
        """模拟网络断开"""
        logging.info(f"开始断网模拟，持续 {duration_seconds} 秒")

        # 启动代理服务器
        self.start_proxy_server()

        # 设置断网模式
        self.network_config['disconnect'] = True

        # 等待指定时间
        time.sleep(duration_seconds)

        # 恢复正常
        self.network_config['disconnect'] = False

        logging.info("断网模拟结束")

    def simulate_weak_network(self, config, duration_seconds):
        """模拟弱网环境"""
        logging.info(f"开始弱网模拟，持续 {duration_seconds} 秒")

        # 启动代理服务器
        self.start_proxy_server()

        # 设置弱网参数
        self.network_config.update({
            'delay': config.get('delay', 0),
            'loss': config.get('loss', 0),
            'bandwidth': config.get('bandwidth', 0),
            'disconnect': False
        })

        logging.info(f"弱网配置: 延迟={self.network_config['delay']}ms, "
                    f"丢包={self.network_config['loss']}%, "
                    f"带宽={self.network_config['bandwidth']}bps")

        # 等待指定时间
        time.sleep(duration_seconds)

        # 恢复正常网络
        self.network_config = {
            'delay': 0,
            'loss': 0,
            'bandwidth': 0,
            'disconnect': False
        }

        logging.info("弱网模拟结束")

    def start_proxy_server(self):
        """启动代理服务器"""
        if self.is_running:
            return

        logging.info(f"启动代理服务器，端口: {self.proxy_port}")

        try:
            self.proxy_server = HTTPServer(('0.0.0.0', self.proxy_port), NetworkProxyHandler)
            self.proxy_server.network_config = self.network_config

            self.server_thread = threading.Thread(target=self.proxy_server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()

            self.is_running = True
            logging.info("代理服务器启动成功")

        except Exception as e:
            logging.error(f"启动代理服务器失败: {str(e)}")
            raise

    def stop_proxy_server(self):
        """停止代理服务器"""
        if not self.is_running:
            return

        logging.info("停止代理服务器")

        if self.proxy_server:
            self.proxy_server.shutdown()
            self.proxy_server.server_close()
            self.proxy_server = None

        if self.server_thread:
            self.server_thread.join(timeout=5)
            self.server_thread = None

        self.is_running = False
        logging.info("代理服务器已停止")

    def _get_pc_ip(self):
        """获取PC的IP地址"""
        try:
            # 创建socket连接来获取本机IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logging.warning(f"获取PC IP失败: {str(e)}，使用localhost")
            return "127.0.0.1"


class NetworkProxyHandler(BaseHTTPRequestHandler):
    """网络代理请求处理器"""

    def do_GET(self):
        """处理GET请求"""
        self._handle_request()

    def do_POST(self):
        """处理POST请求"""
        self._handle_request()

    def do_PUT(self):
        """处理PUT请求"""
        self._handle_request()

    def do_DELETE(self):
        """处理DELETE请求"""
        self._handle_request()

    def _handle_request(self):
        """处理网络请求"""
        config = self.server.network_config

        try:
            # 检查是否断网模式
            if config['disconnect']:
                self._send_disconnect_response()
                return

            # 模拟网络延迟
            if config['delay'] > 0:
                delay_seconds = config['delay'] / 1000.0
                time.sleep(delay_seconds)

            # 模拟丢包
            if config['loss'] > 0:
                import random
                if random.random() * 100 < config['loss']:
                    self._send_packet_loss_response()
                    return

            # 模拟带宽限制（简化实现）
            if config['bandwidth'] > 0:
                # 这里可以实现更复杂的带宽限制逻辑
                pass

            # 转发请求到实际目标
            self._forward_request()

        except Exception as e:
            logging.error(f"处理请求失败: {str(e)}")
            self._send_error_response(500, "Internal Server Error")

    def _send_disconnect_response(self):
        """发送断网响应"""
        self.send_response(503)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Service Unavailable - Network Disconnected")

    def _send_packet_loss_response(self):
        """发送丢包响应"""
        self.send_response(504)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Gateway Timeout - Packet Loss Simulated")

    def _forward_request(self):
        """转发请求到实际目标"""
        # 这里实现简单的HTTP代理转发
        # 实际实现可能需要更复杂的代理逻辑
        try:
            # 解析目标URL
            if self.path.startswith('http://') or self.path.startswith('https://'):
                target_url = self.path
            else:
                # 相对路径，转发到默认目标
                target_url = f"http://httpbin.org{self.path}"

            # 使用requests库转发请求（需要安装requests）
            try:
                import requests
                if self.command == 'GET':
                    response = requests.get(target_url, timeout=30)
                elif self.command == 'POST':
                    content_length = int(self.headers.get('Content-Length', 0))
                    post_data = self.rfile.read(content_length) if content_length > 0 else None
                    response = requests.post(target_url, data=post_data, timeout=30)
                else:
                    # 其他方法暂不支持
                    self._send_error_response(405, "Method Not Allowed")
                    return

                # 返回响应
                self.send_response(response.status_code)
                for header, value in response.headers.items():
                    self.send_header(header, value)
                self.end_headers()
                self.wfile.write(response.content)

            except ImportError:
                # 如果没有requests，发送简单响应
                self._send_error_response(500, "Proxy forwarding requires requests library")

        except Exception as e:
            logging.error(f"转发请求失败: {str(e)}")
            self._send_error_response(502, "Bad Gateway")

    def _send_error_response(self, code, message):
        """发送错误响应"""
        self.send_response(code)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(message.encode())

    def log_message(self, format, *args):
        """重写日志方法以使用logging"""
        logging.debug(f"Proxy request: {format % args}")