#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mock Server 基础设施封装。

对外暴露轻量的创建/管理函数，内部仍复用 utils.mock_server.MockServer 实现，
便于后续在不改动上层调用的前提下替换底层。
"""

from __future__ import annotations

from typing import Any, Dict

from utils.mock_server import MockServer


def create_mock_server(host: str = "127.0.0.1", port: int = 8080) -> MockServer:
    """创建 MockServer 实例，便于 GUI 与测试代码统一调用。"""
    return MockServer(host=host, port=port)


def apply_rules(server: MockServer, rules: Dict[str, Any]) -> None:
    """将规则字典直接赋给服务器的 mock_responses 字段（保持与现实现兼容）。"""
    if not isinstance(rules, dict):
        return
    if "responses" in rules:
        server.mock_responses = rules


__all__ = ["MockServer", "create_mock_server", "apply_rules"]

