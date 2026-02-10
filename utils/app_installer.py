# -*- coding: utf-8 -*-
"""
APK 安装：普通应用（adb install -r）与系统应用（root + remount + push + 重启）。
供 GUI「安装APK」与后续脚本调用。
"""

import os
import subprocess
import time
import logging
from typing import List, Tuple, Optional, Callable

logger = logging.getLogger(__name__)

# 系统应用安装目标分区（Android 常见 vendor 分区应用目录）
VENDOR_APP_DIR = "/vendor/app"


def _run(
    adb_cmd: List[str],
    sn: str,
    args: List[str],
    timeout: int = 60,
    capture: bool = True,
) -> Tuple[int, str, str]:
    """执行 adb -s SN + args，返回 (returncode, stdout, stderr)。"""
    cmd = [*adb_cmd, "-s", sn] + args
    try:
        r = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return (
            r.returncode,
            (r.stdout or "").strip(),
            (r.stderr or "").strip(),
        )
    except subprocess.TimeoutExpired as e:
        return -1, "", f"命令超时（{timeout}s）"
    except Exception as e:
        return -1, "", str(e)


def normal_install(
    adb_cmd: List[str],
    sn: str,
    apk_paths: List[str],
) -> Tuple[bool, str]:
    """
    普通应用安装：对每个 APK 执行 adb install -r。
    返回 (全部成功, 错误信息)；若全部成功则错误信息为空。
    """
    if not adb_cmd or not sn:
        return False, "adb 命令或设备序列号为空"
    errors = []
    for path in apk_paths:
        path = (path or "").strip()
        if not path or not os.path.isfile(path):
            continue
        code, out, err = _run(adb_cmd, sn, ["install", "-r", path], timeout=120)
        if code != 0:
            errors.append(f"{os.path.basename(path)}: {err or out or '安装失败'}")
    if errors:
        return False, "\n".join(errors)
    return True, ""


def _get_package_name_from_apk(apk_path: str) -> Optional[str]:
    """从 APK 解析包名；失败返回 None（不触发 sys.exit）。"""
    try:
        from utils.package import Package
    except ImportError:
        return None
    try:
        pkg = Package(apk_path)
        return (pkg.name or "").strip() or None
    except SystemExit:
        return None
    except Exception as e:
        logger.warning("解析 APK 包名失败 %s: %s", apk_path, e)
        return None


def system_install(
    adb_cmd: List[str],
    sn: str,
    apk_paths: List[str],
    status_callback: Optional[Callable[[str], None]] = None,
    reboot_timeout: int = 120,
) -> Tuple[bool, str]:
    """
    系统应用安装：adb root -> remount -> push 到 /vendor/app/<包名>/ -> 重启 -> 等待设备就绪。
    status_callback 可选，用于 GUI 更新状态文案。
    返回 (成功, 错误信息)。
    """
    def status(msg: str) -> None:
        if status_callback:
            status_callback(msg)
        logger.info("[system_install] %s", msg)

    if not adb_cmd or not sn:
        return False, "adb 命令或设备序列号为空"
    valid_paths = [p for p in apk_paths if (p or "").strip() and os.path.isfile((p or "").strip())]
    if not valid_paths:
        return False, "未选择有效 APK 文件"

    # 1) root
    status("正在获取 root 权限…")
    code, out, err = _run(adb_cmd, sn, ["root"], timeout=15)
    if code != 0:
        return False, f"adb root 失败: {err or out}"
    time.sleep(1)

    # 2) remount（使 /vendor 可写；部分设备为 remount 或 remount /vendor）
    status("正在 remount 分区…")
    code, out, err = _run(adb_cmd, sn, ["remount"], timeout=15)
    if code != 0:
        # 部分 ROM 需要 remount /vendor
        code2, out2, err2 = _run(adb_cmd, sn, ["shell", "mount", "-o", "rw,remount", "/vendor"], timeout=10)
        if code2 != 0:
            return False, f"remount 失败: {err or out}; 尝试 remount /vendor 也失败: {err2 or out2}"

    # 3) 解析包名并 push 到 /vendor/app/<包名>/
    for path in valid_paths:
        path = path.strip()
        pkg_name = _get_package_name_from_apk(path)
        if not pkg_name:
            return False, f"无法解析 APK 包名，请确认文件有效: {os.path.basename(path)}"
        remote_dir = f"{VENDOR_APP_DIR}/{pkg_name}"
        remote_file = f"{remote_dir}/{os.path.basename(path)}"
        status(f"正在推送 {os.path.basename(path)} 到 {remote_dir} …")
        code, out, err = _run(adb_cmd, sn, ["shell", "mkdir", "-p", remote_dir], timeout=10)
        if code != 0:
            return False, f"创建目录 {remote_dir} 失败: {err or out}"
        code, out, err = _run(adb_cmd, sn, ["push", path, remote_file], timeout=120)
        if code != 0:
            return False, f"push {os.path.basename(path)} 失败: {err or out}"

    # 4) 重启
    status("正在重启设备…")
    code, out, err = _run(adb_cmd, sn, ["reboot"], timeout=10)
    if code != 0 and "restarting" not in (out + err).lower():
        return False, f"adb reboot 失败: {err or out}"

    # 5) 等待设备重新上线
    status("等待设备重启就绪…")
    deadline = time.monotonic() + reboot_timeout
    while time.monotonic() < deadline:
        time.sleep(3)
        code, out, err = _run(adb_cmd, sn, ["get-state"], timeout=5)
        if code == 0 and (out or "").strip().lower() == "device":
            status("设备已就绪")
            return True, ""
        # get-state 在设备未就绪时可能失败，继续轮询
    return False, f"等待设备就绪超时（{reboot_timeout}s），请手动确认设备已连接"


def uninstall(adb_cmd: List[str], sn: str, package_name: str) -> Tuple[bool, str]:
    """卸载已安装应用。返回 (成功, 错误信息)。"""
    if not adb_cmd or not sn or not (package_name or "").strip():
        return False, "参数不完整"
    code, out, err = _run(adb_cmd, sn, ["uninstall", (package_name or "").strip()], timeout=30)
    if code != 0:
        return False, err or out or "卸载失败"
    return True, ""
