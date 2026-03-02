#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试运行控制：暂停/继续
通过控制文件实现 GUI 与 pytest 子进程间的状态共享。
"""

import json
import logging
import os
from typing import Callable, Optional

# 控制文件路径（项目根目录下的 conf/）
_CONF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "conf")
RUN_CONTROL_PATH = os.path.join(_CONF_DIR, "stability_run_control.json")

# 暂停超时：超过此时长则自动终止测试（秒）
PAUSE_TIMEOUT_SECONDS = 30 * 60  # 30 分钟

# 暂停等待循环中的轮询间隔（秒）
PAUSE_POLL_INTERVAL = 5


def is_paused() -> bool:
    """
    读取控制文件，判断当前是否处于暂停状态。
    文件不存在或解析异常时返回 False（未暂停）。
    """
    try:
        path = RUN_CONTROL_PATH
        if not os.path.isfile(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return False
        return bool(data.get("pause", False))
    except Exception as e:
        logging.debug("读取运行控制文件失败 %s: %s", RUN_CONTROL_PATH, e)
        return False


def set_paused(pause: bool) -> bool:
    """
    写入控制文件，设置暂停状态。
    供 GUI 或测试进程（如暂停超时终止时）调用。
    返回是否写入成功。
    """
    try:
        path = RUN_CONTROL_PATH
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"pause": pause}, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logging.warning("写入运行控制文件失败 %s: %s", RUN_CONTROL_PATH, e)
        return False


def wait_while_paused_or_timeout(
    on_timeout: Optional[Callable[[], None]],
    stop_event: Optional[object] = None,
    timeout_seconds: int = PAUSE_TIMEOUT_SECONDS,
    poll_interval: int = PAUSE_POLL_INTERVAL,
) -> bool:
    """
    若当前处于暂停状态，进入等待循环，直到：
    - 用户点击继续（is_paused() 变为 False）：返回 True，调用方继续执行
    - 暂停超时：调用 on_timeout()，返回 False，调用方应终止
    - stop_event 已设置（如用户点击停止）：返回 False

    Args:
        on_timeout: 暂停超时时调用的回调（无参数），用于设置 _stop_event 等
        stop_event: 可选，需有 .is_set() 方法，若已 set 则立即返回 False
        timeout_seconds: 暂停超时秒数
        poll_interval: 轮询间隔秒数

    Returns:
        True 表示可继续执行，False 表示应终止
    """
    import time

    if not is_paused():
        return True
    pause_start = time.time()
    logging.info("测试已暂停，等待用户继续（超过 %d 分钟将自动终止）", timeout_seconds // 60)
    while True:
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            logging.info("测试在暂停期间收到停止信号，终止执行")
            return False
        if not is_paused():
            logging.info("用户已继续，恢复测试")
            return True
        elapsed = time.time() - pause_start
        if elapsed >= timeout_seconds:
            logging.warning("暂停已超过 %d 分钟，自动终止测试", timeout_seconds // 60)
            if on_timeout:
                try:
                    on_timeout()
                except Exception as e:
                    logging.warning("暂停超时回调执行异常: %s", e)
            set_paused(False)  # 清除暂停状态，避免下次启动误判
            return False
        time.sleep(min(poll_interval, timeout_seconds - elapsed))
