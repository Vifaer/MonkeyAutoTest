#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import time
import threading
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from collections import deque
from datetime import datetime


class MockServerHandler(BaseHTTPRequestHandler):
    """
    Mock Server请求处理器
    """

    def __init__(self, *args, **kwargs):
        self.mock_responses = kwargs.pop('mock_responses', {})
        super().__init__(*args, **kwargs)

    def do_GET(self):
        """处理GET请求"""
        self._handle_request('GET')

    def do_POST(self):
        """处理POST请求"""
        self._handle_request('POST')

    def _handle_request(self, method):
        """通用请求处理"""
        path = urlparse(self.path).path
        query = parse_qs(urlparse(self.path).query)

        # 查找匹配的mock响应
        response_data = self._find_mock_response(method, path, query)

        # 发送响应
        self.send_response(response_data.get('status', 200))
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        self.wfile.write(json.dumps(response_data.get('body', {})).encode())

        status = response_data.get('status', 200)
        logging.info(f"Mock Server响应: {method} {path} -> {status}")

        # 记录活动（供GUI或其他调用方展示）
        try:
            recorder = getattr(self, "_activity_recorder", None)
            if recorder:
                recorder({
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "method": method,
                    "path": path,
                    "status": status,
                    "query": {k: v for k, v in query.items()},
                })
        except Exception:
            pass

    def _find_mock_response(self, method, path, query):
        """查找匹配的mock响应"""
        # 默认响应
        default_response = {
            'status': 200,
            'body': {'status': 'success', 'data': []}
        }

        # 查找配置的mock响应
        for mock_config in self.mock_responses.get('responses', []):
            if (mock_config.get('method', 'GET') == method and
                mock_config.get('path') == path):

                # 检查查询参数匹配（如果配置了的话）
                if 'query' in mock_config:
                    if not self._match_query_params(query, mock_config['query']):
                        continue

                return mock_config.get('response', default_response)

        return default_response

    def _match_query_params(self, actual_query, expected_query):
        """检查查询参数是否匹配"""
        for key, expected_values in expected_query.items():
            if key not in actual_query:
                return False
            if not isinstance(expected_values, list):
                expected_values = [expected_values]
            if actual_query[key][0] not in expected_values:
                return False
        return True

    def log_message(self, format, *args):
        """重写日志方法以使用我们的日志系统"""
        logging.debug(f"Mock Server: {format % args}")


class MockServer:
    """
    Mock Server类
    用于模拟云端数据服务，支持各种异常情况的模拟
    """

    def __init__(self, host='127.0.0.1', port=8080):
        self.host = host
        self.port = port
        self.server = None
        self.server_thread = None
        self.mock_responses = {
            'responses': []
        }
        self._running = False
        self._activity = deque(maxlen=200)  # 最近请求记录
        self._lock = threading.Lock()

    def is_running(self):
        return bool(self._running and self.server_thread and self.server_thread.is_alive())

    def get_activity_snapshot(self):
        """获取最近请求的快照（list[dict]）"""
        with self._lock:
            return list(self._activity)

    def _record_activity(self, item: dict):
        with self._lock:
            self._activity.append(item)

    def start(self):
        """启动Mock Server"""
        def run_server():
            # 创建自定义处理器类
            class CustomHandler(MockServerHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, mock_responses=self.mock_responses, **kwargs)
                    # 注入活动记录器（避免跨模块依赖logging解析）
                    self._activity_recorder = self._outer._record_activity  # type: ignore

            try:
                # 将外层 self 传给 handler（通过类属性避免BaseHTTPRequestHandler签名变化）
                CustomHandler._outer = self  # type: ignore
                self.server = HTTPServer((self.host, self.port), CustomHandler)
                logging.info(f"Mock Server启动在 http://{self.host}:{self.port}")
                self._running = True
                self.server.serve_forever()
            except Exception as e:
                logging.error(f"Mock Server启动失败: {str(e)}")
            finally:
                self._running = False

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        # 等待服务器启动
        time.sleep(1)

    def stop(self):
        """停止Mock Server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logging.info("Mock Server已停止")
        self._running = False

    def configure_response(self, method, path, response_config, query_params=None):
        """
        配置Mock响应

        Args:
            method: HTTP方法 ('GET', 'POST', etc.)
            path: 请求路径
            response_config: 响应配置 {'status': int, 'body': dict}
            query_params: 查询参数匹配条件
        """
        mock_config = {
            'method': method,
            'path': path,
            'response': response_config
        }

        if query_params:
            mock_config['query'] = query_params

        self.mock_responses['responses'].append(mock_config)
        logging.info(f"配置Mock响应: {method} {path}")

    def setup_normal_response(self, path='/api/data'):
        """设置正常响应"""
        normal_response = {
            'status': 200,
            'body': {
                'status': 'success',
                'data': [
                    {'id': 1, 'name': 'Test Item 1', 'value': 100},
                    {'id': 2, 'name': 'Test Item 2', 'value': 200}
                ],
                'timestamp': int(time.time())
            }
        }
        self.configure_response('GET', path, normal_response)

    def setup_empty_response(self, path='/api/data'):
        """设置空数据响应"""
        empty_response = {
            'status': 200,
            'body': {
                'status': 'success',
                'data': [],
                'message': 'No data available'
            }
        }
        self.configure_response('GET', path, empty_response)

    def setup_malformed_response(self, path='/api/data'):
        """设置错误格式数据响应"""
        malformed_response = {
            'status': 200,
            'body': {
                'status': 'success',
                'data': 'invalid_json_format{',
                'corrupted': True
            }
        }
        self.configure_response('GET', path, malformed_response)

    def setup_error_response(self, path='/api/data', status_code=500):
        """设置错误响应"""
        error_response = {
            'status': status_code,
            'body': {
                'status': 'error',
                'message': f'Server error: {status_code}',
                'code': status_code
            }
        }
        self.configure_response('GET', path, error_response)

    def setup_delayed_response(self, path='/api/data', delay_seconds=5):
        """设置延迟响应"""
        def delayed_response():
            time.sleep(delay_seconds)
            return {
                'status': 200,
                'body': {
                    'status': 'success',
                    'data': [{'id': 1, 'name': 'Delayed Item'}],
                    'delay': delay_seconds
                }
            }

        # 注意：这里简化实现，实际延迟需要在handler中处理
        delayed_resp = {
            'status': 200,
            'body': {
                'status': 'success',
                'data': [{'id': 1, 'name': 'Delayed Item'}],
                'delay': delay_seconds
            }
        }
        self.configure_response('GET', path, delayed_resp)

    def clear_responses(self):
        """清除所有配置的响应"""
        self.mock_responses['responses'] = []
        logging.info("清除所有Mock响应配置")

    def get_server_url(self):
        """获取服务器URL"""
        return f"http://{self.host}:{self.port}"


class NetworkProxyController:
    """
    网络代理控制器
    用于控制网络代理设置，模拟弱网等情况
    """

    def __init__(self, device_sn):
        self.device_sn = device_sn
        self.proxy_host = '127.0.0.1'
        self.proxy_port = 8080

    def enable_proxy(self):
        """启用网络代理"""
        # 设置HTTP代理
        cmd = f"adb -s {self.device_sn} shell settings put global http_proxy {self.proxy_host}:{self.proxy_port}"
        result = self._run_cmd(cmd)
        logging.info("网络代理已启用")
        return result

    def disable_proxy(self):
        """禁用网络代理"""
        cmd = f"adb -s {self.device_sn} shell settings put global http_proxy :0"
        result = self._run_cmd(cmd)
        logging.info("网络代理已禁用")
        return result

    def setup_weak_network_simulation(self, delay_ms=500):
        """
        设置弱网模拟
        注意：这需要配合mitmproxy或类似工具使用
        """
        logging.info(f"设置弱网模拟，延迟: {delay_ms}ms")
        # 这里可以启动mitmproxy脚本来模拟弱网
        # mitmproxy -s weak_network.py --set delay={delay_ms}

    def reset_network_settings(self):
        """重置网络设置"""
        self.disable_proxy()
        logging.info("网络设置已重置")

    def _run_cmd(self, cmd):
        """执行ADB命令"""
        from utils.timeout_command import run as run_cmd
        return run_cmd(cmd)


# 全局Mock Server实例
_mock_server_instance = None

def get_mock_server():
    """获取Mock Server单例实例"""
    global _mock_server_instance
    if _mock_server_instance is None:
        _mock_server_instance = MockServer()
    return _mock_server_instance

def start_mock_server():
    """启动Mock Server"""
    server = get_mock_server()
    server.start()
    return server

def stop_mock_server():
    """停止Mock Server"""
    global _mock_server_instance
    if _mock_server_instance:
        _mock_server_instance.stop()
        _mock_server_instance = None