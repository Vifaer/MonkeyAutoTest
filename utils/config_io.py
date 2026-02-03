#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
通用配置读写工具（小而稳，避免到处散落 try/except）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: str | Path, data: Any, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典（override 优先）"""
    result: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

