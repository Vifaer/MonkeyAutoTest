#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import time
import re
import random
import logging
from utils import timeout_command


class Device:
    def __init__(self, sn):
        self.sn = sn
        self.os = ""
        self.screen = ""
        self.model = ""
        self.__set_device_info()

    def __set_device_info(self):
        """从 adb devices 输出中解析设备信息，初始化基本属性。

        注意：旧实现依赖正则 `(.+?)\\s+device\\n`，在 `adb devices -l` 输出包含
        `device product:...` 时会解析失败，导致即使设备在线也被认为不存在。
        这里改为按行解析，匹配第二列等于 'device' 的 SN，更加健壮。
        """
        rst = timeout_command.run("adb devices")
        sn_list = []
        if isinstance(rst, str):
            for line in rst.splitlines():
                line = line.strip()
                if not line or line.lower().startswith("list of devices"):
                    continue
                parts = line.split()
                # 典型行：<sn>  device [product:... model:...]
                if len(parts) >= 2 and parts[1] == "device":
                    sn_list.append(parts[0])

        # 判断device是否存在
        if self.sn not in sn_list:
            msg = f"device [{self.sn}] not found"
            logging.error(msg)
            # 在库代码中不直接 sys.exit，以便由上层（CLI / GUI / pytest）决定如何处理
            raise RuntimeError(msg)
        # 获取系统版本号（兼容 Android 12/13/14 等纯数字版本）
        cmd = "adb -s {} shell getprop ro.build.version.release".format(self.sn)
        rst = timeout_command.run(cmd)
        if rst is None:
            logging.warning("[device_info] time out: {}".format(cmd))
        elif isinstance(rst, str) and "error" in rst.lower():
            logging.warning("[device_info] cannot execute: {}".format(cmd))
            logging.warning("[device_info] result: {}".format(rst))
        else:
            try:
                text = (rst or "").strip()
                m = re.search(r"\d+(?:\.\d+){0,2}", text)
                os_version = m.group(0) if m else text.split()[0]
                self.os = os_version
            except Exception as e:
                logging.warning("[device_info] failed to regex os from {}. {}".format(rst, e))
        # 获取分辨率
        # Windows 下不要依赖 `| grep`；优先用 `wm size`，再兜底 dumpsys
        cmd = "adb -s {} shell wm size".format(self.sn)
        rst = timeout_command.run(cmd)
        if rst is None:
            logging.warning("[device_info] time out: {}".format(cmd))
        elif "error" in rst:
            logging.warning("[device_info] cannot execute: {}".format(cmd))
            logging.warning("[device_info] result: {}".format(rst))
        else:
            try:
                # Physical size: 1920x1080 或 Override size: ...
                m = re.search(r"(Physical size|Override size):\s*(\d{3,5}x\d{3,5})", rst)
                if m:
                    self.screen = m.group(2)
            except Exception as e:
                logging.warning("[device_info] failed to regex screen from {}. {}".format(rst, e))
        if not self.screen:
            try:
                cmd = "adb -s {} shell dumpsys display".format(self.sn)
                rst = timeout_command.run(cmd)
                if rst:
                    m = re.search(r"mBaseDisplayInfo.*?real\s+(\d+)\s+x\s+(\d+)", rst)
                    if m:
                        self.screen = f"{m.group(1)}x{m.group(2)}"
            except Exception:
                pass
        # 获取设备名
        cmd = "adb -s {} shell getprop ro.product.model".format(self.sn)
        rst = timeout_command.run(cmd)
        if rst is None:
            logging.warning("[device_info] time out: {}".format(cmd))
        elif "error" in rst:
            logging.warning("[device_info] cannot execute: {}".format(cmd))
            logging.warning("[device_info] result: {}".format(rst))
        else:
            try:
                model = rst.strip()
                self.model = model
            except Exception as e:
                logging.warning("[device_info] failed to get model. {}".format(e))

    def install(self, package):
        """
        安装 APK 到设备。
        日志输出遵循统一规范，方便追踪推送与安装过程：
        1) 开始推送/安装提示（包含设备SN、包名、文件路径与大小）；
        2) 安装完成后的成功确认；
        3) 失败场景下记录 ADB 返回的具体错误原因。
        """
        apk_path = getattr(package, "path", "") or ""
        pkg_name = getattr(package, "name", "") or ""

        # 1) 推送/安装开始提示
        size_str = "unknown"
        if apk_path and os.path.exists(apk_path):
            try:
                size_bytes = os.path.getsize(apk_path)
                size_mb = size_bytes / (1024 * 1024)
                size_str = f"{size_mb:.2f} MB"
            except Exception as e:
                logging.debug(f"[install] failed to get apk size for {apk_path}: {e}")
        logging.info(f"[install] start installing APK on device {self.sn} "
                     f"(package={pkg_name}, path={apk_path or 'N/A'}, size={size_str})")
        logging.info("[install] pushing APK to device via adb install -r（该过程可能耗时较长，请耐心等待）")

        # 2) 调用 adb install -r（内部会完成推送 + 安装）
        cmd = "adb -s {} install -r {}".format(self.sn, apk_path)
        rst = timeout_command.run(cmd, 600)

        # 3) 结果判定与详细日志
        if rst is None:
            logging.error(f"[install] failed to install {pkg_name} on {self.sn}: adb 超时（命令: {cmd}）")
            sys.exit(-1)

        text = (rst or "").strip()
        if "Success" in text:
            logging.info(f"[install] succeeded in installing {pkg_name} on {self.sn}")
        elif "Failure" in text or "Error" in text or "error" in text.lower():
            try:
                key = re.findall(r"Failure \[(.+?)\]", text)[0]
            except Exception as e:
                logging.debug(e)
                key = "UNKNOWN"
            logging.error(f"[install] failed to install {pkg_name} on {self.sn}, reason: {key}, adb output: {text}")
            sys.exit(-1)
        else:
            # 非典型输出：既没有 Success/Failure，也不为空；记录全文，视为失败
            logging.error(f"[install] unexpected adb output when installing {pkg_name} on {self.sn}: {text}")
            sys.exit(-1)

    def uninstall(self, package):
        # 卸载包
        cmd = "adb -s {} uninstall {}".format(self.sn, package.name)
        rst = timeout_command.run(cmd, 600)
        if rst is None:
            logging.error("[uninstall] failed to uninstall, the command is: {}".format(cmd))
        elif "Success" in rst:
            logging.info("[uninstall] succeeded in uninstalling {}".format(package.name))
        elif "Failure" in rst:
            try:
                key = re.findall(r"Failure \[(.+?)\]", rst)[0]
            except Exception as e:
                logging.debug(e)
                key = "NULL"
            logging.error("[uninstall] failed to uninstall {}, reason: {}".format(package.name, key))

    def enable_simiasque(self):
        # 启动simiasque
        cmd = "adb -s {} shell am start -n org.thisisafactory.simiasque/org.thisisafactory.simiasque.MyActivity_".format(self.sn)
        timeout_command.run(cmd)
        time.sleep(1)
        # 返回桌面
        cmd = "adb -s {} shell input keyevent KEYCODE_HOME".format(self.sn)
        timeout_command.run(cmd)
        time.sleep(1)
        # 打开simiasque开关
        cmd = "adb -s {} shell am broadcast -a org.thisisafactory.simiasque.SET_OVERLAY --ez enable true".format(self.sn)
        timeout_command.run(cmd)

    def disable_simiasque(self):
        # 关闭simiasque开关
        cmd = "adb -s {} shell am broadcast -a org.thisisafactory.simiasque.SET_OVERLAY --ez enable false".format(self.sn)
        timeout_command.run(cmd)

    def enable_wifi_manager(self):
        # 启动Wifi Manager
        cmd = "adb -s {} shell am start -n com.ntflc.wifimanager/.MainActivity".format(self.sn)
        timeout_command.run(cmd)
        time.sleep(1)
        # 返回桌面
        cmd = "adb -s {} shell input keyevent KEYCODE_HOME".format(self.sn)
        timeout_command.run(cmd)

    def dumpsys_activity(self, path):
        dumpsys_name = "dumpsys_{}.txt".format(self.sn)
        # adb shell dumpsys activity
        cmd = "adb -s {} shell dumpsys activity > {}/{}".format(self.sn, path, dumpsys_name)
        logging.info(cmd)
        timeout_command.run(cmd)

    def turn_off_screen(self):
        cmd = "adb -s {} shell input keyevent POWER".format(self.sn)
        timeout_command.run(cmd)

    def run_monkey(self, package, path, throttle=700, cnt=10000):
        # 停止进程
        cmd = "adb -s {} shell am force-stop {}".format(self.sn, package.name)
        os.popen(cmd)
        time.sleep(3)
        # 生成随机数
        rand = random.randint(0, 65535)
        # 执行monkey命令
        cmd = "adb -s {} shell monkey -p {} -s {} --ignore-crashes --ignore-timeouts --throttle {} -v {} > {}".format(
            self.sn, package.name, rand, throttle, cnt, path
        )
        logging.info(cmd)
        os.popen(cmd)
        time.sleep(5)
        # 停止进程
        cmd = "adb -s {} shell am force-stop {}".format(self.sn, package.name)
        os.popen(cmd)
