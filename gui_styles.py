#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GUI样式配置文件
定义Monkey自动化测试工具的界面样式和主题
"""

import tkinter as tk
from tkinter import font

class MonkeyTestTheme:
    """Monkey测试工具主题配置"""

    # 色彩体系 - Cursor续杯工具风格
    COLORS = {
        'primary': "#1677FF",        # 主色：亮蓝色
        'success': "#52C41A",        # 成功：绿色
        'error': "#FF4D4F",          # 错误：红色
        'warning': "#FAAD14",        # 警告：橙色
        'info': "#13C2C2",           # 信息：青色

        # 中性色
        'white': "#FFFFFF",          # 白色背景
        'bg_light': "#F0F2F5",       # 浅灰背景
        'bg_dark': "#E6F7FF",        # 浅蓝背景
        'text_primary': "#333333",   # 主文字
        'text_secondary': "#666666", # 次要文字
        'border': "#D9D9D9",         # 边框色
        'shadow': "#CCCCCC",         # 阴影色
    }

    # 字体配置
    FONTS = {
        'title': ("Microsoft YaHei", 16, "bold"),      # 标题
        'subtitle': ("Microsoft YaHei", 14, "bold"),   # 副标题
        'body': ("Microsoft YaHei", 12),               # 正文
        'caption': ("Microsoft YaHei", 10),            # 说明文字
        'button': ("Microsoft YaHei", 11, "bold"),     # 按钮文字
        'mono': ("Consolas", 10),                       # 等宽字体（日志）
    }

    # 尺寸配置
    METRICS = {
        'card_padding': 20,         # 卡片内边距
        'element_spacing': 10,      # 元素间距
        'border_radius': 8,         # 圆角半径
        'shadow_depth': 2,          # 阴影深度
        'button_height': 35,        # 按钮高度
        'input_height': 30,         # 输入框高度
    }

    @classmethod
    def apply_theme(cls, root):
        """应用主题到根窗口"""
        # 设置根窗口样式
        root.configure(bg=cls.COLORS['bg_light'])

        # 配置样式
        style = cls._create_style(root)

        return style

    @classmethod
    def _create_style(cls, root):
        """创建样式对象"""
        try:
            from tkinter import ttk
            style = ttk.Style()

            # 配置按钮样式
            style.configure('TButton',
                          font=cls.FONTS['button'],
                          padding=10)

            # 配置标签样式
            style.configure('TLabel',
                          background=cls.COLORS['white'],
                          font=cls.FONTS['body'])

            # 配置输入框样式
            style.configure('TEntry',
                          font=cls.FONTS['body'],
                          padding=5)

            # 配置组合框样式
            style.configure('TCombobox',
                          font=cls.FONTS['body'])

            return style
        except ImportError:
            # 如果没有ttk，返回None
            return None

    @classmethod
    def create_card_frame(cls, parent, title="", **kwargs):
        """创建卡片式框架"""
        # 主框架
        frame = tk.Frame(
            parent,
            bg=cls.COLORS['white'],
            relief='raised',
            bd=1,
            **kwargs
        )

        # 标题（如果提供）
        if title:
            title_label = tk.Label(
                frame,
                text=title,
                font=cls.FONTS['subtitle'],
                fg=cls.COLORS['text_primary'],
                bg=cls.COLORS['white']
            )
            title_label.pack(anchor=tk.W, padx=cls.METRICS['card_padding'],
                           pady=(cls.METRICS['card_padding'], 5))

            # 分割线
            separator = tk.Frame(frame, height=1, bg=cls.COLORS['border'])
            separator.pack(fill=tk.X, padx=cls.METRICS['card_padding'])

        # 内容容器
        content = tk.Frame(frame, bg=cls.COLORS['white'])
        content.pack(fill=tk.BOTH, expand=True,
                    padx=cls.METRICS['card_padding'],
                    pady=(cls.METRICS['card_padding'] if not title else 10, cls.METRICS['card_padding']))

        return frame, content

    @classmethod
    def create_primary_button(cls, parent, text, command, **kwargs):
        """创建主要操作按钮"""
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=cls.COLORS['primary'],
            fg=cls.COLORS['white'],
            font=cls.FONTS['button'],
            relief='flat',
            cursor='hand2',
            padx=25,
            pady=8,
            **kwargs
        )

    @classmethod
    def create_secondary_button(cls, parent, text, command, **kwargs):
        """创建次要操作按钮"""
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=cls.COLORS['text_secondary'],
            fg=cls.COLORS['white'],
            font=cls.FONTS['button'],
            relief='flat',
            cursor='hand2',
            padx=15,
            pady=6,
            **kwargs
        )

    @classmethod
    def create_success_button(cls, parent, text, command, **kwargs):
        """创建成功状态按钮"""
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=cls.COLORS['success'],
            fg=cls.COLORS['white'],
            font=cls.FONTS['button'],
            relief='flat',
            cursor='hand2',
            padx=20,
            pady=8,
            **kwargs
        )

    @classmethod
    def create_error_button(cls, parent, text, command, **kwargs):
        """创建错误状态按钮"""
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=cls.COLORS['error'],
            fg=cls.COLORS['white'],
            font=cls.FONTS['button'],
            relief='flat',
            cursor='hand2',
            padx=20,
            pady=8,
            **kwargs
        )

    @classmethod
    def create_status_label(cls, parent, text, status='normal', **kwargs):
        """创建状态标签"""
        color_map = {
            'normal': cls.COLORS['text_primary'],
            'success': cls.COLORS['success'],
            'error': cls.COLORS['error'],
            'warning': cls.COLORS['warning'],
            'info': cls.COLORS['info']
        }

        return tk.Label(
            parent,
            text=text,
            fg=color_map.get(status, cls.COLORS['text_primary']),
            bg=cls.COLORS['white'],
            font=cls.FONTS['body'],
            anchor=tk.W,
            **kwargs
        )