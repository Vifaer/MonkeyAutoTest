#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网络代理与弱网模拟基础设施封装。

当前统一收口到 utils/network_proxy.py 和 utils/pc_proxy_simulator.py，
后续如需替换实现（例如引入独立进程或容器化代理）只需修改本模块。
"""

from __future__ import annotations

from typing import Any, Dict

from utils import network_proxy as _network_proxy
from utils import pc_proxy_simulator as _pc_proxy_sim


def enable_proxy(config: Dict[str, Any]) -> None:
    """根据配置启用网络代理/弱网模拟。"""
    method = config.get("method", "root")
    if method == "pc_proxy":
        _pc_proxy_sim.start_pc_proxy(config)
    else:
        _network_proxy.enable_network_proxy(config)


def disable_proxy() -> None:
    """关闭网络代理/弱网模拟。"""
    try:
        _network_proxy.disable_network_proxy()
    except Exception:
        # 忽略关闭失败，避免影响主流程
        pass
    try:
        _pc_proxy_sim.stop_pc_proxy()
    except Exception:
        pass


__all__ = ["enable_proxy", "disable_proxy"]

