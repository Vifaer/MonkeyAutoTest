#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
配置读取与合并的统一入口。

当前主要封装对 utils.addition / utils.config_io 等模块的调用，
后续可在不影响上层调用的前提下调整底层实现。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from utils import addition
from utils.config_io import read_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_config() -> Dict[str, Any]:
    """加载 conf/project.json 项目配置。"""
    return addition.get_project_json()


def load_test_ui_config(path: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    """加载 GUI 持久化配置 conf/test_ui_config.json。"""
    if path is None:
        path = PROJECT_ROOT / "conf" / "test_ui_config.json"
    return read_json(str(path), default={})


__all__ = ["load_project_config", "load_test_ui_config"]

