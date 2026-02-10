
from mitmproxy import http
import time
import random

class WeakNetwork:
    def __init__(self):
        self.delay = 500 / 1000.0  # 转换为秒
        self.loss_rate = 5 / 100.0
        self.bandwidth_limit = 1024  # bytes per second

    def request(self, flow: http.HTTPFlow) -> None:
        # 模拟网络延迟
        if self.delay > 0:
            time.sleep(self.delay)

        # 模拟丢包
        if random.random() < self.loss_rate:
            flow.response = http.HTTPResponse.make(
                504,
                b"Gateway Timeout - Simulated packet loss",
                {"Content-Type": "text/plain"}
            )
            return

        # 模拟带宽限制（简化实现）
        if self.bandwidth_limit > 0:
            # 这里可以实现带宽限制逻辑
            pass

addons = [WeakNetwork()]
