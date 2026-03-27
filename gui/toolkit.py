#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GUI 工具与基础 UI 元素。

从原始的 gui_main.py 中抽离出的通用 UI 常量与控件：
- 颜色/字体/尺寸常量
- Tooltip 悬浮提示组件

后续其他 gui 子模块应优先从本文件导入这些基础元素，
避免在多个文件中重复定义样式与行为。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont


class UIColors:
    """UI 色彩体系"""

    PRIMARY = "#1677FF"  # 主色：亮蓝色
    SUCCESS = "#52C41A"  # 成功：绿色
    ERROR = "#FF4D4F"  # 错误：红色
    WARNING = "#FAAD14"  # 警告：橙色
    INFO = "#13C2C2"  # 信息：青色

    # 中性色
    WHITE = "#FFFFFF"  # 白色背景
    BG_LIGHT = "#F0F2F5"  # 浅灰背景
    BG_DARK = "#E6F7FF"  # 浅蓝背景
    TEXT_PRIMARY = "#333333"  # 主文字
    TEXT_SECONDARY = "#666666"  # 次要文字
    BORDER = "#D9D9D9"  # 边框色


class UIFonts:
    """UI 字体设置

    注意：
    - 这里给出的是“默认占位值”
    - 实际运行时会在 MonkeyTestGUI.__init__ 中使用 tk.font.Font
      重新初始化并挂载到同名属性，便于后续动态缩放
    """

    TITLE = ("Microsoft YaHei", 14, "bold")  # 标题
    SUBTITLE = ("Microsoft YaHei", 12, "bold")  # 副标题
    BODY = ("Microsoft YaHei", 11)  # 正文
    CAPTION = ("Microsoft YaHei", 9)  # 说明文字
    BUTTON = ("Microsoft YaHei", 10, "bold")  # 按钮文字
    MONO = ("Consolas", 9)  # 等宽字体（日志/设备列表）


class UIMetrics:
    """UI 尺寸常量"""

    CARD_PADDING = 20  # 卡片内边距
    ELEMENT_SPACING = 10  # 元素间距
    BORDER_RADIUS = 8  # 圆角半径
    SHADOW_DEPTH = 2  # 阴影深度


# 向后兼容：大量代码使用全大写 UIFONTS 访问字体，保持别名
UIFONTS = UIFonts


class ToolTip:
    """悬浮提示工具类，与现有 UI 风格保持一致"""

    def __init__(self, widget: tk.Widget, text: str, delay: int = 500) -> None:
        """
        Args:
            widget: 要添加提示的控件
            text: 提示文本（支持多行，使用 \\n 分隔）
            delay: 显示延迟（毫秒）
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window: tk.Toplevel | None = None
        self.id: str | None = None
        self.x = self.y = 0

        # 防止被垃圾回收：将自身挂到控件上
        try:
            setattr(self.widget, "_tooltip", self)
        except Exception:
            pass

        # 为有提示的控件增加统一的视觉标识（如下划线或“ⓘ”）
        self._mark_widget_with_hint()

        # 绑定事件
        self.widget.bind("<Enter>", self.on_enter)
        self.widget.bind("<Leave>", self.on_leave)
        self.widget.bind("<Motion>", self.on_motion)

    def _mark_widget_with_hint(self) -> None:
        """为绑定了 Tooltip 的控件增加统一的视觉标识（幂等）"""
        w = self.widget
        try:
            # 已经标记过则不重复处理
            if getattr(w, "_has_tooltip_marker", False):
                return
            # 仅对常见文本控件添加标记，避免影响 Entry/Text 等输入内容
            text_widgets = (
                tk.Label,
                tk.Checkbutton,
                tk.Radiobutton,
                ttk.Label,
                ttk.Checkbutton,
                ttk.Radiobutton,
            )
            if isinstance(w, text_widgets):
                # 优先尝试使用带下划线的字体
                try:
                    font_name = w.cget("font")
                except Exception:
                    font_name = ""
                if font_name:
                    try:
                        base_font = tkfont.nametofont(font_name)
                        marker_font = base_font.copy()
                        marker_font.configure(underline=1)
                        w.configure(font=marker_font)
                        setattr(w, "_tooltip_font", marker_font)
                    except Exception:
                        # 退化为在文本末尾追加“ⓘ”
                        try:
                            text = w.cget("text")
                            if text and "ⓘ" not in text:
                                w.configure(text=f"{text} ⓘ")
                        except Exception:
                            pass
                else:
                    # 没有字体配置时，仅追加“ⓘ”标记
                    try:
                        text = w.cget("text")
                        if text and "ⓘ" not in text:
                            w.configure(text=f"{text} ⓘ")
                    except Exception:
                        pass
                setattr(w, "_has_tooltip_marker", True)
        except Exception:
            # 任何异常都静默忽略，不影响主界面
            pass

    def on_enter(self, event=None) -> None:  # type: ignore[override]
        """鼠标进入时，延迟显示提示"""
        self.schedule()

    def on_leave(self, event=None) -> None:  # type: ignore[override]
        """鼠标离开时，隐藏提示"""
        self.unschedule()
        self.hide_tip()

    def on_motion(self, event) -> None:  # type: ignore[override]
        """鼠标移动时，更新提示位置"""
        self.x = event.x_root + 10
        self.y = event.y_root + 10

    def schedule(self) -> None:
        """安排显示提示"""
        self.unschedule()
        self.id = self.widget.after(self.delay, self.show_tip)

    def unschedule(self) -> None:
        """取消显示提示"""
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show_tip(self) -> None:
        """显示提示窗口"""
        if self.tip_window:
            return

        # 创建提示窗口
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)  # 无边框
        self.tip_window.wm_geometry(f"+{self.x}+{self.y}")

        # 设置样式
        frame = tk.Frame(
            self.tip_window,
            bg=UIColors.WHITE,
            relief="solid",
            borderwidth=1,
            highlightbackground=UIColors.BORDER,
            highlightthickness=1,
        )
        frame.pack(fill=tk.BOTH, expand=True)

        # 创建文本标签
        # wraplength 需足够大，避免将「- 删除：」「- 重构：」等列表项拆成「-」单独一行
        label = tk.Label(
            frame,
            text=self.text,
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_PRIMARY,
            font=UIFonts.CAPTION,
            justify=tk.LEFT,
            wraplength=800,  # 保证每行约 70 个中文字符，避免列表项被拆行
            padx=10,
            pady=8,
        )
        label.pack()

        # 更新位置（确保不超出屏幕）
        self.tip_window.update_idletasks()
        width = self.tip_window.winfo_width()
        height = self.tip_window.winfo_height()

        # 获取屏幕尺寸
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()

        # 调整位置，避免超出屏幕
        x = self.x
        y = self.y
        if x + width > screen_width:
            x = screen_width - width - 10
        if y + height > screen_height:
            y = screen_height - height - 10

        self.tip_window.wm_geometry(f"+{x}+{y}")

    def hide_tip(self) -> None:
        """隐藏提示窗口"""
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


__all__ = ["UIColors", "UIFonts", "UIMetrics", "UIFONTS", "ToolTip"]

