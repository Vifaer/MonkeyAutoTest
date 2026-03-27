#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
设备异常目录清理。

测试前清空 /data/anr、/data/tombstones，排除历史干扰。
部分设备需要 root 才能访问；失败仅记录 warning，不中断测试。
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from infra.adb import run_shell, run


def clear_device_exception_dirs(device_sn: str) -> None:
    """
    清空设备异常目录，排除历史 ANR/tombstone 干扰。

    目录：/data/anr、/data/tombstones
    策略：先普通权限，失败后尝试 su -c，再尝试 adb root 后清理。
    失败仅记录 warning，不抛出异常。

    Args:
        device_sn: 设备序列号
    """
    if not device_sn:
        return

    def _has_err(s: str) -> bool:
        return any(
            k in s
            for k in (
                "Permission denied",
                "Operation not permitted",
                "not permitted",
                "Read-only file system",
                "No such file or directory",
            )
        )

    def _run_shell(cmd: str, timeout: int) -> Optional[str]:
        out = run_shell(device_sn, cmd, timeout=timeout)
        return out if isinstance(out, str) else None

    def _run_su(cmd: str, timeout: int) -> Optional[str]:
        out = run_shell(device_sn, f'su -c "{cmd}"', timeout=timeout)
        return out if isinstance(out, str) else None

    def _try_adb_root() -> bool:
        try:
            out = run("root", serial=device_sn, timeout=15)
            s = str(out or "").lower()
            if "root" in s or "restarting" in s:
                time.sleep(2.0)
                return True
        except Exception:
            pass
        return False

    for d in ("/data/anr", "/data/tombstones"):
        try:
            out = _run_shell(f"rm -f {d}/*", timeout=8)
            if out is not None:
                s = out.strip()
                if not _has_err(s):
                    logging.info("[device-exc] 清理目录成功: %s", d)
                    continue
                if "No such file or directory" in s:
                    logging.info("[device-exc] 目录不存在（视为已清理）: %s", d)
                    continue
                logging.warning("[device-exc] 清理目录失败（无权限/只读）%s: %s", d, s[:200])
            else:
                logging.warning("[device-exc] 清理目录失败（命令超时）: %s", d)

            out2 = _run_su(f"rm -f {d}/*", timeout=20)
            if out2 is not None:
                s2 = out2.strip()
                if not _has_err(s2):
                    logging.info("[device-exc] 清理目录成功（su）: %s", d)
                    continue
                if "No such file or directory" in s2:
                    logging.info("[device-exc] 目录不存在（su，视为已清理）: %s", d)
                    continue
                if any(
                    x in s2.lower()
                    for x in ("not found", "su: not found", "permission denied", "not permitted")
                ):
                    logging.warning("[device-exc] su 清理失败 %s: %s", d, s2[:200])
                else:
                    logging.warning("[device-exc] su 清理失败（返回异常）%s: %s", d, s2[:200])
            else:
                logging.warning("[device-exc] su 清理超时: %s", d)

            if _try_adb_root():
                out3 = _run_shell(f"rm -f {d}/*", timeout=20)
                if out3 is not None:
                    s3 = out3.strip()
                    if not _has_err(s3):
                        logging.info("[device-exc] 清理目录成功（adb root）: %s", d)
                        continue
                    if "No such file or directory" in s3:
                        logging.info("[device-exc] 目录不存在（adb root，视为已清理）: %s", d)
                        continue
                    logging.warning("[device-exc] adb root 后清理仍失败 %s: %s", d, s3[:200])
                else:
                    logging.warning("[device-exc] adb root 后清理超时: %s", d)
            else:
                logging.warning("[device-exc] adb root 不可用/失败，无法提升权限清理: %s", d)
        except Exception as e:
            logging.warning("[device-exc] 清理目录失败（可忽略）%s: %s", d, e)


__all__ = ["clear_device_exception_dirs"]
