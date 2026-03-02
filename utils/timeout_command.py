#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import subprocess
import threading
from pathlib import Path

# 防止 adb dumpsys 等大量输出时管道满导致死锁：读取上限（字节）
MAX_STDOUT_BYTES = 2 * 1024 * 1024
MAX_STDERR_BYTES = 512 * 1024


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


def _read_stream_capped(fh, max_bytes, buf_holder, key):
    """在后台线程中读取流，最多 max_bytes，避免管道满导致子进程阻塞。"""
    try:
        chunk_size = 65536
        total = 0
        while total < max_bytes:
            to_read = min(chunk_size, max_bytes - total)
            data = fh.read(to_read)
            if not data:
                break
            buf_holder[key].append(data)
            total += len(data)
    except Exception as e:
        logging.debug("Capped read %s error: %s", key, e)
    finally:
        try:
            fh.close()
        except Exception:
            pass


def run(cmd, timeout=10):
    """
    运行带超时的 shell 命令。
    - 使用 Popen + 上限读取 stdout/stderr，避免 adb dumpsys 等大量输出时管道满导致死锁。
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

    out_parts = []
    err_parts = []
    holder = {"out": out_parts, "err": err_parts}

    try:
        proc = subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        t_out = threading.Thread(
            target=_read_stream_capped,
            args=(proc.stdout, MAX_STDOUT_BYTES, holder, "out"),
            daemon=True,
        )
        t_err = threading.Thread(
            target=_read_stream_capped,
            args=(proc.stderr, MAX_STDERR_BYTES, holder, "err"),
            daemon=True,
        )
        t_out.start()
        t_err.start()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                except Exception:
                    pass
            logging.debug("Command timeout: %s", cmd[:100])
            t_out.join(timeout=1.0)
            t_err.join(timeout=1.0)
            return None
        t_out.join(timeout=2.0)
        t_err.join(timeout=2.0)
        out = b"".join(out_parts)
        err = b"".join(err_parts)
        data = out if out else err
        if proc.returncode != 0 and err and not data:
            data = err
        if proc.returncode != 0 and data:
            logging.debug("Command exit code %s: %s", proc.returncode, cmd[:100])
    except FileNotFoundError as e:
        logging.warning("Command not found: %s, %s", cmd[:100], e)
        return None
    except Exception as e:
        logging.warning("Command execution error: %s, %s", cmd[:100], str(e))
        return f"error: {e}"

    if not data:
        return None

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
