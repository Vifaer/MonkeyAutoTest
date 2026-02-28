#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import subprocess
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
    - 超时返回 None；非零退出返回包含 stderr 的字符串；解码失败使用 errors="replace" 兜底。
    """
    stripped = cmd.lstrip()
    if stripped.startswith("adb "):
        adb_path = _resolve_adb_path()
        if adb_path:
            quoted = f'"{adb_path}"' if " " in adb_path and not adb_path.startswith('"') else adb_path
            cmd = cmd.replace("adb", quoted, 1)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logging.debug("Command timeout: %s", cmd[:100])
        return None
    except subprocess.CalledProcessError as e:
        logging.warning("Command failed with non-zero exit: %s, stderr: %s", cmd[:100], (e.stderr or b"")[:200])
        data = e.stderr or e.stdout or b""
    except Exception as e:
        logging.warning("Command execution error: %s, %s", cmd[:100], str(e))
        return f"error: {e}"

    out = result.stdout or b""
    err = result.stderr or b""
    data = out if out else err

    # 解码策略：优先 utf-8，其次 gbk（Windows 常见），最后 replace
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc, errors="replace")
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    try:
        return data.decode(errors="replace")
    except UnicodeDecodeError:
        logging.warning("Failed to decode command output, using replacement: %s", cmd[:100])
        return data.decode(errors="replace")
    except Exception as e:
        logging.warning("Unexpected decode error: %s", str(e))
        return str(data)
