#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ADB 命令封装。

提供统一的 ADB 调用接口，供 GUI、测试与 infra 其他模块使用。
过渡期内部使用 utils.timeout_command 执行命令。
"""

from __future__ import annotations

import logging
from typing import Optional

# 过渡期：infra 可调用 utils 中尚未迁移的能力
from utils.timeout_command import run as _run_cmd


def run(
    *parts: str,
    serial: Optional[str] = None,
    timeout: int = 30,
) -> Optional[str]:
    """
    执行 ADB 命令。

    Args:
        *parts: 命令片段，如 "shell", "getprop", "ro.build.version.release"
        serial: 设备序列号，为 None 时执行 adb <parts>
        timeout: 超时秒数

    Returns:
        命令输出字符串，失败或超时返回 None
    """
    adb_cmd = _build_cmd(serial, *parts)
    out = _run_cmd(adb_cmd, timeout=timeout)
    return out if isinstance(out, str) else None


def run_shell(
    serial: str,
    shell_cmd: str,
    timeout: int = 30,
) -> Optional[str]:
    """
    在指定设备上执行 shell 命令。

    Args:
        serial: 设备序列号
        shell_cmd: shell 内要执行的命令（如 "rm -f /data/anr/*"）
        timeout: 超时秒数

    Returns:
        命令输出字符串，失败或超时返回 None
    """
    return run("shell", shell_cmd, serial=serial, timeout=timeout)


def list_devices() -> list[str]:
    """
    获取当前已连接且可用的设备列表。

    Returns:
        设备序列号列表
    """
    out = run("devices", timeout=10)
    sn_list: list[str] = []
    if isinstance(out, str):
        for line in out.splitlines():
            line = line.strip()
            if not line or line.lower().startswith("list of devices"):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                sn_list.append(parts[0])
    return sn_list


def _build_cmd(serial: Optional[str], *parts: str) -> str:
    """构建 adb 命令行字符串。"""
    base = "adb"
    if serial:
        return f"{base} -s {serial} " + " ".join(_quote(p) for p in parts)
    return f"{base} " + " ".join(_quote(p) for p in parts)


def _quote(s: str) -> str:
    """对含空格的参数加引号。"""
    if " " in s or '"' in s:
        return '"' + s.replace('"', '\\"') + '"'
    return s


__all__ = ["run", "run_shell", "list_devices"]
