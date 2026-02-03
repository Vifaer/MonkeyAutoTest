#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import re
import logging
from utils import timeout_command


class Package:
    def __init__(self, pkg_path):
        self.path = pkg_path
        self.filename = ""
        self.name = ""
        self.activity = ""
        self.version_name = ""
        self.source = "apk"  # apk / installed
        self.__set_pkg_info()

    @classmethod
    def from_installed(cls, device_sn: str, package_name: str):
        """
        从设备已安装应用构造 Package（不依赖APK文件）。
        主要用于“测试已安装应用”场景：跳过安装，仅复用包名/启动Activity/版本信息。
        """
        obj = cls.__new__(cls)  # bypass __init__
        obj.path = ""
        obj.filename = ""
        obj.name = (package_name or "").strip()
        obj.activity = ""
        obj.version_name = ""
        obj.source = "installed"
        obj._populate_from_device(device_sn)
        return obj

    def __set_pkg_info(self):
        # 判断路径是否存在
        if not os.path.exists(self.path):
            logging.error("package from '{}' not found".format(self.path))
            sys.exit(-1)

        # 定位 aapt 可执行文件（优先内置，再看环境变量/SDK）
        aapt = os.environ.get("AAPT_PATH", "").strip()
        if not aapt:
            try:
                project_root = os.path.dirname(os.path.dirname(__file__))
                # 项目内置 tools/aapt/aapt(.exe)
                cand_local = os.path.join(
                    project_root, "tools", "aapt", "aapt.exe" if sys.platform == "win32" else "aapt"
                )
                if os.path.exists(cand_local):
                    aapt = cand_local
            except Exception:
                aapt = ""

        if not aapt:
            sdk_root = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ""
            build_tools_dir = os.path.join(sdk_root, "build-tools") if sdk_root else ""
            if build_tools_dir and os.path.isdir(build_tools_dir):
                try:
                    # 选择版本号最大的 build-tools 目录
                    subdirs = [d for d in os.listdir(build_tools_dir)
                               if os.path.isdir(os.path.join(build_tools_dir, d))]
                    subdirs.sort(reverse=True)
                    for d in subdirs:
                        cand = os.path.join(build_tools_dir, d, "aapt.exe" if sys.platform == "win32" else "aapt")
                        if os.path.exists(cand):
                            aapt = cand
                            break
                except Exception:
                    pass

        if not aapt:
            logging.warning("[pkg_info] aapt not found（请安装 Android SDK 或设置环境变量 AAPT_PATH）")
            # 保持 filename 有值，name/activity 为空，上层仍可通过 package.path 运行 monkey
            self.filename = os.path.basename(self.path)
            return

        # 获取文件名
        self.filename = os.path.basename(self.path)
        # 获取包名/Activity（Windows 下不要依赖 `| grep`，直接解析 aapt 输出）
        aapt_cmd = f"\"{aapt}\"" if " " in aapt and not aapt.startswith("\"") else aapt
        cmd = f"{aapt_cmd} dump badging \"{self.path}\""
        rst = timeout_command.run(cmd, timeout=20)
        if rst is None:
            logging.warning("[pkg_info] time out: {}".format(cmd))
        elif isinstance(rst, str) and ("ERROR" in rst or "error:" in rst.lower()):
            logging.warning("[pkg_info] cannot execute: {}".format(cmd))
            logging.warning("[pkg_info] result: {}".format(rst))
        else:
            try:
                # package: name='com.xxx' versionCode='..' versionName='..'
                package_name = re.findall(r"package:\s+name='([^']+)'", rst)[0]
                self.name = package_name
            except Exception as e:
                logging.warning("[pkg_info] failed to regex package name from {}. {}".format(rst, e))
            try:
                # launchable-activity: name='com.xxx.MainActivity'  label='...' icon='...'
                m = re.search(r"launchable-activity:\s+name='([^']+)'", rst)
                if m:
                    self.activity = m.group(1).strip()
            except Exception as e:
                logging.warning("[pkg_info] failed to regex main activity from {}. {}".format(rst, e))

    def _populate_from_device(self, device_sn: str):
        """从设备读取包信息（存在性/版本/启动Activity）。"""
        if not self.name:
            raise ValueError("package_name is empty")

        sn = (device_sn or "").strip()
        if not sn:
            raise ValueError("device_sn is empty")

        # 1) 校验包是否存在
        cmd = f"adb -s {sn} shell pm path {self.name}"
        rst = timeout_command.run(cmd)
        if not rst or "package:" not in rst:
            raise RuntimeError(f"设备上未安装包：{self.name}")

        # 2) 版本信息（尽力解析）
        try:
            cmd = f"adb -s {sn} shell dumpsys package {self.name}"
            rst = timeout_command.run(cmd)
            if rst:
                m = re.search(r"versionName=([^\s]+)", rst)
                if m:
                    self.version_name = m.group(1).strip()
        except Exception:
            pass

        # 3) 启动 Activity（尽力解析）
        # 优先用 `cmd package resolve-activity --brief`，不同Android版本输出略有差异，做宽松解析
        resolve_cmds = [
            f"adb -s {sn} shell cmd package resolve-activity --brief -c android.intent.category.LAUNCHER {self.name}",
            f"adb -s {sn} shell cmd package resolve-activity --brief {self.name}",
        ]
        for cmd in resolve_cmds:
            try:
                rst = timeout_command.run(cmd)
                if not rst:
                    continue
                # 常见最后一行是 component: com.xxx/.MainActivity
                lines = [ln.strip() for ln in rst.splitlines() if ln.strip()]
                candidate = lines[-1] if lines else ""
                # 有些版本会输出 "name: com.xxx/.MainActivity" 或直接 "com.xxx/.MainActivity"
                m = re.search(r"([a-zA-Z0-9._]+/[\w.$]+)", candidate)
                if m:
                    comp = m.group(1)
                    # comp 可能为 com.xxx/.MainActivity，activity 只要后半段或完整都能用
                    if "/" in comp:
                        pkg, act = comp.split("/", 1)
                        # act 可能以 '.' 开头
                        self.activity = act.lstrip(".")
                    break
            except Exception:
                continue

        # 兜底：保持 activity 为空，上层可用 monkey -p 仍能跑，但 am start -n 可能失败
