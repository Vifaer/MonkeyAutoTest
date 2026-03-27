#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
日志初始化封装。

提供统一的 setup_logging 入口，内部委托给 utils.log，
避免在多个模块中直接调用 logging.basicConfig 或 utils.log.setup_logging。
"""

from __future__ import annotations

import logging
from typing import Any

from utils.log import setup_logging as _setup_logging


def setup_logging(level: int = logging.INFO, **kwargs: Any) -> None:
    """初始化全局日志配置。"""
    _setup_logging(level=level, **kwargs)


__all__ = ["setup_logging"]

