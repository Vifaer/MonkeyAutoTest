#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GUI 状态与上下文定义。

GuiContext 用于在不同 GUI 组件之间传递共享状态，
例如根窗口、日志队列、当前测试状态等，避免大量散落的全局变量。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from queue import Queue
from typing import Any, Dict


@dataclass
class GuiContext:
    """GUI 顶层上下文对象。

    当前只收口最核心的共享状态，后续可按需扩展字段。
    """

    root: Any
    log_queue: "Queue[str]"
    testing_flags: Dict[str, Any] = field(default_factory=dict)


__all__ = ["GuiContext"]

