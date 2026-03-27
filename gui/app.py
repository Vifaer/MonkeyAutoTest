#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GUI 应用入口封装。

提供统一的 main() 函数，便于后续脚本或打包入口调用：

    python -m gui.app

当前内部仍委托给 legacy 的 gui_main.main()，后续可逐步迁移逻辑到本模块。
"""

from __future__ import annotations

from tkinter import messagebox

try:
    # 可选：如果直接从本模块启动，需要 tk 与 ttkbootstrap
    import tkinter as tk  # noqa: F401
except Exception:  # pragma: no cover - 启动环境问题时再由 legacy 处理
    tk = None  # type: ignore

from gui_main import main as _legacy_main


def main() -> None:
    """GUI 启动入口（当前委托给 gui_main.main）。"""
    try:
        _legacy_main()
    except Exception as exc:  # 兜底保护，避免异常直接吞掉
        msg = f"GUI 启动失败: {exc}"
        try:
            messagebox.showerror("启动错误", msg)
        except Exception:
            print(msg)


if __name__ == "__main__":
    main()

