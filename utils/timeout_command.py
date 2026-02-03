#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import subprocess
import datetime
import signal
from pathlib import Path


def _resolve_adb_path() -> str:
    """
    统一解析 adb.exe 路径，优先级：
    1) 环境变量 ADB_PATH
    2) 项目内置 tools/adb/adb.exe 或 tools/platform-tools/adb.exe
    3) 系统 PATH 中的 adb
    """
    adb_path = os.environ.get("ADB_PATH", "").strip()
    if adb_path and os.path.exists(adb_path):
        return adb_path

    # 项目根目录（utils/ 的上级）
    try:
        project_root = Path(__file__).resolve().parent.parent
    except Exception:
        project_root = None

    candidates = []
    if project_root:
        candidates.extend(
            [
                project_root / "tools" / "adb" / "adb.exe",
                project_root / "tools" / "platform-tools" / "adb.exe",
            ]
        )

    for cand in candidates:
        try:
            if cand and cand.exists():
                real = str(cand)
                os.environ["ADB_PATH"] = real  # 记住结果，后续可直接使用
                return real
        except Exception:
            continue

    # 最后兜底：系统 PATH 中的 adb
    from shutil import which

    w = which("adb")
    if w:
        os.environ["ADB_PATH"] = w
        return w

    return ""


def run(cmd, timeout=10):
    """
    运行带超时的 shell 命令。
    - 对 `adb ...` 命令：自动解析可用的 adb.exe（内置 or 环境变量 or PATH），替换命令前缀；
    - 返回值统一为 str（优先 utf-8 / gbk 解码），避免上层拿到 bytes 导致解析异常。
    """
    # 兼容：通过环境变量 / 内置工具统一指定 adb 可执行文件路径
    stripped = cmd.lstrip()
    if stripped.startswith("adb "):
        adb_path = _resolve_adb_path()
        if adb_path:
            # 尽量保持原命令结构，处理带空格路径
            quoted = f"\"{adb_path}\"" if " " in adb_path and not adb_path.startswith("\"") else adb_path
            # 仅替换第一个 adb 单词
            cmd = cmd.replace("adb", quoted, 1)

    try:
        # 用 subprocess.run 处理 timeout，并在 Windows 下避免 os.kill(SIGKILL) 不兼容
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        return f"error: {e}"

    out = result.stdout or b""
    err = result.stderr or b""
    data = out if out else err

    # 解码策略：优先 utf-8，其次 gbk（Windows 常见），最后 replace
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc, errors="replace")
        except Exception:
            continue
    try:
        return data.decode(errors="replace")
    except Exception:
        return str(data)
