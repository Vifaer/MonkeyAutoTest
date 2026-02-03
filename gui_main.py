#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Monkey自动化测试工具 - GUI版本
车载端侧应用自动化测试工具的图形界面

作者: MonkeyAutoTest Team
版本: 1.0.0

UI设计风格：参考Cursor续杯工具设计体系
- 主色：亮蓝色 (#1677FF)
- 成功：绿色 (#52C41A)
- 警告：红色 (#FF4D4F)
- 进度：橙色 (#FAAD14)
- 布局：卡片式设计，步骤化引导
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue
import sys
import os
import json
import time
from datetime import datetime
import subprocess
import argparse
import logging
from pathlib import Path
import shutil

# ttkbootstrap（可选）：有安装则启用主题，无安装自动回退
try:
    import ttkbootstrap as ttkb  # type: ignore
    from ttkbootstrap.constants import *  # type: ignore
    HAS_TTKBOOTSTRAP = True
except Exception:
    ttkb = None
    HAS_TTKBOOTSTRAP = False

# ttkbootstrap可用主题列表（常用）——内部使用英文ID，界面显示映射为中文
TTKBOOTSTRAP_THEMES = [
    "flatly", "cosmo", "minty", "journal", "sandstone",
    "litera", "lumen", "pulse", "united", "yeti",
    "darkly", "superhero", "cyborg", "vapor"
]

# 主题显示名称映射（中文更直观，仅用于界面展示）
# 基于 ttkbootstrap 主题实际视觉效果优化命名
TTK_THEME_LABELS = {
    "flatly": "现代蓝 (Flatly)",           # 扁平化设计，现代蓝色调
    "cosmo": "都市蓝 (Cosmo)",             # 都市风格，蓝色调
    "minty": "薄荷绿 (Minty)",             # 清新薄荷绿色调
    "journal": "米白纸感 (Journal)",       # 纸质风格，米白色背景
    "sandstone": "暖沙色 (Sandstone)",     # 沙石暖色调，棕色/米色
    "litera": "阅读白 (Litera)",           # 文学阅读风格，白色背景
    "lumen": "明亮白 (Lumen)",             # 高亮度，白色背景，高对比度
    "pulse": "活力紫 (Pulse)",             # 现代紫色调，充满活力
    "united": "暖橙红 (United)",           # 温暖橙色/红色调
    "yeti": "纯白雪 (Yeti)",               # 雪白色背景，简洁纯净
    "darkly": "深黑 (Darkly)",             # 深色主题，黑色/深灰背景
    "superhero": "深蓝暗 (Superhero)",     # 深蓝色调，暗色主题
    "cyborg": "赛博灰 (Cyborg)",           # 赛博朋克风格，灰色调暗色
    "vapor": "霓虹粉紫 (Vapor)",           # 蒸汽波风格，粉紫色调，霓虹感
}

# 设置控制台编码为UTF-8
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
except:
    pass

# 设置日志编码
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# UI设计常量
class UIColors:
    """UI色彩体系"""
    PRIMARY = "#1677FF"        # 主色：亮蓝色
    SUCCESS = "#52C41A"        # 成功：绿色
    ERROR = "#FF4D4F"          # 错误：红色
    WARNING = "#FAAD14"        # 警告：橙色
    INFO = "#13C2C2"           # 信息：青色

    # 中性色
    WHITE = "#FFFFFF"          # 白色背景
    BG_LIGHT = "#F0F2F5"       # 浅灰背景
    BG_DARK = "#E6F7FF"        # 浅蓝背景
    TEXT_PRIMARY = "#333333"   # 主文字
    TEXT_SECONDARY = "#666666" # 次要文字
    BORDER = "#D9D9D9"         # 边框色

class UIFonts:
    """UI字体设置"""
    TITLE = ("Microsoft YaHei", 16, "bold")      # 标题
    SUBTITLE = ("Microsoft YaHei", 14, "bold")   # 副标题
    BODY = ("Microsoft YaHei", 12)               # 正文
    CAPTION = ("Microsoft YaHei", 10)            # 说明文字
    BUTTON = ("Microsoft YaHei", 11, "bold")     # 按钮文字

class UIMetrics:
    """UI尺寸常量"""
    CARD_PADDING = 20         # 卡片内边距
    ELEMENT_SPACING = 10      # 元素间距
    BORDER_RADIUS = 8         # 圆角半径
    SHADOW_DEPTH = 2          # 阴影深度

# 导入项目模块
from utils import addition, ProjectLog
from utils.stability_test import StabilityTestFramework, StabilityTestRunner
from utils import Package
from utils import mock_server as mock_server_mod
from utils.config_io import read_json, write_json


class MonkeyTestGUI:
    """Monkey自动化测试工具GUI主类"""

    def __init__(self, root):
        self.root = root
        self.root.title("Monkey自动化测试工具 v1.0.0")
        self.root.geometry("1200x800")
        # 最小尺寸：避免过度压缩导致不可用；但允许更小以适配低分辨率
        self.root.minsize(980, 680)

        # 设置窗口图标（如果有的话）
        try:
            self.root.iconbitmap("icon.ico")
        except:
            pass

        # 初始化变量
        self.test_thread = None
        self.is_testing = False
        self.log_queue = queue.Queue()
        self.test_results = {}
        self.auto_scroll_var = tk.BooleanVar(value=True)
        # 测试配置相关变量（便于弹窗和主界面共享）
        self.test_mode_var = tk.StringVar(value="comprehensive")
        self.module_vars = {
            'system_robustness': tk.BooleanVar(value=True),
            'exception_recovery': tk.BooleanVar(value=True),
            'performance_response': tk.BooleanVar(value=False),
            'performance_resource': tk.BooleanVar(value=False),
            'performance_all': tk.BooleanVar(value=True)
        }
        self.duration_var = tk.StringVar(value="12")  # 数值部分
        self.duration_unit_var = tk.StringVar(value="小时")  # 单位：分钟/小时（仅GUI显示）
        self.network_method_var = tk.StringVar(value="root")
        self.baseline_establish_var = tk.BooleanVar(value=False)
        self.baseline_compare_var = tk.BooleanVar(value=False)
        self.no_mock_server_var = tk.BooleanVar(value=False)
        self.no_network_proxy_var = tk.BooleanVar(value=False)
        # pytest框架已强制启用，无需用户选择
        self.multi_devices_var = tk.StringVar(value="emulator-5554")
        self.throttle_var = tk.StringVar(value="700")
        self.count_var = tk.StringVar(value="10000")
        self.uninstall_var = tk.BooleanVar(value=False)
        # Mock Server（GUI集成）
        self.mock_host_var = tk.StringVar(value="127.0.0.1")
        self.mock_port_var = tk.StringVar(value="8080")
        self.mock_rules_path_var = tk.StringVar(value=str(Path("conf") / "mock_rules.json"))
        self._mock_server = None
        self._mock_server_started_by_gui = False
        self._mock_status_label = None
        self._mock_activity_text = None
        # 运行控制按钮占位
        self.start_test_btn = None
        self.stop_test_btn = None
        self.traditional_progress = None
        self.stability_progress = None
        # 子进程执行测试（用于可停止）
        self.test_process = None
        self._test_process_lock = threading.Lock()
        self.test_config_window = None
        self._test_summary_label = None
        self._last_saved_test_cfg = None
        # 自动保存（防抖）相关状态
        self._autosave_job = None
        self._autosave_traces_bound = False
        self._suppress_autosave = False
        # ADB设备检测状态
        self._adb_devices = {}  # sn -> {"state": "device|offline|unauthorized|...", "raw": "..."}
        self._last_adb_snapshot_key = ""
        self._device_poll_job = None
        self.device_combo = None
        self._device_status_in_config = None
        self.adb_path_var = tk.StringVar(value="")  # 允许用户显式指定 adb.exe 路径（避免PATH问题）
        # 测试应用来源：APK安装 / 已安装应用
        self.app_source_var = tk.StringVar(value="apk")  # apk / installed
        self.package_name_var = tk.StringVar(value="")
        self.package_combo = None
        self._installed_packages_cache = []
        self._app_info_label = None

        # ttkbootstrap主题增强（如果可用）
        if HAS_TTKBOOTSTRAP:
            try:
                # 让ttk控件统一主题观感
                self._ttk_style = ttkb.Style()
            except Exception:
                self._ttk_style = None
        # 主题选择（默认flatly）
        self.theme_var = tk.StringVar(value="flatly")
        # 主题下拉框显示用（中文标签），与 theme_var 映射
        self.theme_display_var = tk.StringVar(value=TTK_THEME_LABELS.get("flatly", "现代蓝 (Flatly)"))

        # 加载配置
        self.load_config()
        # 加载“测试配置”持久化参数（与 conf/project.json 分离）
        self.load_test_ui_config()

        # 创建界面
        self.create_widgets()
        # 界面创建完成后应用主题（若 ttkbootstrap 可用）
        self.apply_theme_from_config()
        # 绑定配置自动保存（在控件/变量创建完成后绑定更稳妥）
        self._bind_autosave_traces()
        # 启动设备自动轮询（实时检测ADB设备变化）
        self._start_device_polling()

        # 启动日志处理线程
        self.start_log_handler()

        # 设置窗口关闭事件
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def load_config(self):
        """加载项目配置"""
        try:
            self.project_config = addition.get_project_json()
            self.available_versions = list(self.project_config.keys())
            logging.info(f"成功加载项目配置，包含版本: {self.available_versions}")
        except UnicodeDecodeError as e:
            error_msg = f"配置文件编码错误，请确保conf/project.json使用UTF-8编码保存: {str(e)}"
            messagebox.showerror("编码错误", error_msg)
            logging.error(error_msg)
            self.project_config = {}
            self.available_versions = []
        except FileNotFoundError as e:
            error_msg = f"找不到配置文件conf/project.json: {str(e)}"
            messagebox.showerror("文件错误", error_msg)
            logging.error(error_msg)
            self.project_config = {}
            self.available_versions = []
        except json.JSONDecodeError as e:
            error_msg = f"配置文件格式错误，请检查JSON语法: {str(e)}"
            messagebox.showerror("JSON错误", error_msg)
            logging.error(error_msg)
            self.project_config = {}
            self.available_versions = []
        except Exception as e:
            error_msg = f"加载项目配置时发生未知错误: {str(e)}"
            messagebox.showerror("配置错误", error_msg)
            logging.error(error_msg)
            self.project_config = {}
            self.available_versions = []

    def create_widgets(self):
        """创建GUI界面"""
        # 设置窗口背景色
        self.root.configure(bg=UIColors.BG_LIGHT)

        # 创建主容器 - grid响应式布局
        main_container = tk.Frame(self.root, bg=UIColors.BG_LIGHT)
        main_container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        # root可伸缩
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # main_container行列权重：标题(0)固定，内容(1)可伸缩，状态栏(2)固定
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_columnconfigure(0, weight=1)

        # 标题区域
        title_frame = tk.Frame(main_container, bg=UIColors.BG_LIGHT)
        title_frame.grid(row=0, column=0, sticky="ew")
        self.create_title_area(title_frame)

        # 内容区域（左右分栏，支持拖拽调整）——只保留一个主滚动条，左右共同滚动
        content_frame = tk.Frame(main_container, bg=UIColors.BG_LIGHT)
        content_frame.grid(row=1, column=0, sticky="nsew", pady=(20, 0))
        content_frame.grid_rowconfigure(0, weight=1)
        content_frame.grid_columnconfigure(0, weight=1)

        # 主滚动容器（唯一滚动条）
        scroll_canvas = tk.Canvas(content_frame, bg=UIColors.BG_LIGHT, highlightthickness=0)
        scroll_vbar = tk.Scrollbar(content_frame, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=scroll_vbar.set)

        scroll_canvas.grid(row=0, column=0, sticky="nsew")
        scroll_vbar.grid(row=0, column=1, sticky="ns")

        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        # 让PanedWindow放在可滚动的inner里：左侧受右侧唯一滚动条控制
        scroll_inner = tk.Frame(scroll_canvas, bg=UIColors.BG_LIGHT)
        inner_id = scroll_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")

        def _on_inner_configure(_e):
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def _on_canvas_configure(e):
            # 内部宽度跟随canvas，避免横向裁切
            scroll_canvas.itemconfig(inner_id, width=e.width)

        scroll_inner.bind("<Configure>", _on_inner_configure)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)

        # 鼠标滚轮：只让“主滚动条”生效
        def _on_mousewheel(e):
            scroll_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

        scroll_canvas.bind("<Enter>", lambda _e: scroll_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        scroll_canvas.bind("<Leave>", lambda _e: scroll_canvas.unbind_all("<MouseWheel>"))

        # PanedWindow：左右面板按比例缩放 + 用户可拖拽
        self.main_pane = ttk.Panedwindow(scroll_inner, orient=tk.HORIZONTAL)
        self.main_pane.grid(row=0, column=0, sticky="nsew")
        scroll_inner.grid_rowconfigure(0, weight=1)
        scroll_inner.grid_columnconfigure(0, weight=1)

        # 左右面板容器（不再各自带滚动条，避免双滚动条）
        left_wrap = tk.Frame(self.main_pane, bg=UIColors.BG_LIGHT)
        right_wrap = tk.Frame(self.main_pane, bg=UIColors.BG_LIGHT)

        self.main_pane.add(left_wrap, weight=1)
        self.main_pane.add(right_wrap, weight=3)
        # 给左右面板设置最小宽度，避免启动时某一侧宽度被挤压为0
        try:
            self.main_pane.paneconfig(left_wrap, minsize=300)
            self.main_pane.paneconfig(right_wrap, minsize=500)
        except Exception:
            pass

        # 直接在wrap里放内容（无子滚动条）
        self.create_operation_panel(left_wrap)
        self.create_status_panel(right_wrap)

        # 底部状态栏
        status_frame = tk.Frame(main_container, bg=UIColors.BG_LIGHT)
        status_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.create_status_bar(status_frame)

        # 初始化左右比例（默认左35%右65%）
        self._pane_ratio = 0.35
        self.root.bind("<Configure>", self._on_root_resize)

        # 关键：首次启动时也要设置分隔条位置，否则左侧可能在首次布局时宽度为0，
        # 导致“只有右侧显示，调整窗口后才出现左侧”的现象。
        # 首帧布局后 + 50ms 再校准一次，覆盖不同机器的布局时序差异
        self.root.after(0, self._init_panes)
        self.root.after(50, self._init_panes)

    def _init_panes(self):
        """首次启动时初始化PanedWindow分隔条位置与滚动区域"""
        try:
            self.root.update_idletasks()
            if not (hasattr(self, "main_pane") and self.main_pane.panes()):
                return

            # 优先用PanedWindow自身宽度计算，避免root宽度不稳定导致一侧为0
            pane_w = self.main_pane.winfo_width()
            if pane_w <= 1:
                pane_w = self.root.winfo_width() - 60

            total = max(int(pane_w), 800)
            ratio = float(getattr(self, "_pane_ratio", 0.35))
            left = int(total * ratio)
            # 防止把右侧挤没：左右至少留出 300px
            left = max(300, min(left, total - 300))
            self.main_pane.sashpos(0, left)
        except Exception:
            pass

    # 注意：旧的 _create_scrollable_panel 已移除，改为“单主滚动条”方案（左右共同滚动）

    def _on_root_resize(self, event):
        """窗口缩放时，按比例调整左右面板宽度"""
        try:
            # 只在窗口宽度变化时调整
            if event is not None and event.widget is not self.root:
                return
            pane_w = self.main_pane.winfo_width() if hasattr(self, "main_pane") else 0
            if pane_w <= 1:
                pane_w = self.root.winfo_width() - 60
            total = max(int(pane_w), 800)
            left = int(total * self._pane_ratio)
            left = max(300, min(left, total - 300))
            # 只在panedwindow存在且有pane时设置
            if hasattr(self, "main_pane") and self.main_pane.panes():
                self.main_pane.sashpos(0, left)
        except Exception:
            pass

    def create_config_tab(self):
        """创建配置选项卡"""
        config_frame = ttk.Frame(self.notebook)
        self.notebook.add(config_frame, text="项目配置")

        # 项目版本选择
        ttk.Label(config_frame, text="项目版本:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.version_var = tk.StringVar()
        self.version_combo = ttk.Combobox(config_frame, textvariable=self.version_var,
                                        values=self.available_versions, state="readonly")
        self.version_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        self.version_combo.bind("<<ComboboxSelected>>", self.on_version_selected)

        # 设备序列号
        ttk.Label(config_frame, text="设备序列号:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.device_sn_var = tk.StringVar(value="emulator-5554")
        ttk.Entry(config_frame, textvariable=self.device_sn_var).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # APK路径/URL
        ttk.Label(config_frame, text="APK路径/URL:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        apk_frame = ttk.Frame(config_frame)
        apk_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        self.apk_path_var = tk.StringVar()
        ttk.Entry(apk_frame, textvariable=self.apk_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(apk_frame, text="浏览", command=self.browse_apk).pack(side=tk.RIGHT, padx=(5,0))

        # 邮件收件人
        ttk.Label(config_frame, text="邮件收件人:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.email_var = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.email_var).grid(row=3, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 刷新设备按钮
        ttk.Button(config_frame, text="刷新设备列表", command=self.refresh_devices).grid(row=4, column=0, columnspan=2, pady=10)

        # 设备列表显示
        ttk.Label(config_frame, text="连接的设备:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.devices_text = scrolledtext.ScrolledText(config_frame, height=6, width=50)
        self.devices_text.grid(row=5, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # 配置网格权重
        config_frame.columnconfigure(1, weight=1)
        config_frame.rowconfigure(5, weight=1)

        # 初始刷新设备列表
        self.refresh_devices()

    def create_traditional_test_tab(self):
        """创建传统Monkey测试选项卡"""
        test_frame = ttk.Frame(self.notebook)
        self.notebook.add(test_frame, text="传统Monkey测试")

        # Monkey参数设置
        ttk.Label(test_frame, text="Monkey参数设置", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        # 节流时间
        ttk.Label(test_frame, text="节流时间(ms):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.throttle_var = tk.StringVar(value="700")
        ttk.Entry(test_frame, textvariable=self.throttle_var).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 事件数量
        ttk.Label(test_frame, text="事件数量:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.count_var = tk.StringVar(value="10000")
        ttk.Entry(test_frame, textvariable=self.count_var).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 安装前卸载选项
        self.uninstall_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(test_frame, text="安装前卸载应用", variable=self.uninstall_var).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        # 控制按钮
        button_frame = ttk.Frame(test_frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=20)

        self.start_traditional_btn = ttk.Button(button_frame, text="开始传统测试", command=self.start_traditional_test)
        self.start_traditional_btn.pack(side=tk.LEFT, padx=5)

        self.stop_traditional_btn = ttk.Button(button_frame, text="⏹️ 停止测试", command=self.stop_test, state=["disabled"])
        self.stop_traditional_btn.pack(side=tk.LEFT, padx=5)

        # 进度显示
        ttk.Label(test_frame, text="测试进度", font=("Arial", 12, "bold")).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        self.traditional_progress = ttk.Progressbar(test_frame, orient="horizontal", mode="indeterminate")
        self.traditional_progress.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 配置网格权重
        test_frame.columnconfigure(1, weight=1)

    def create_stability_test_tab(self):
        """创建稳定性测试选项卡"""
        stability_frame = ttk.Frame(self.notebook)
        self.notebook.add(stability_frame, text="稳定性测试")

        # 测试模式选择
        ttk.Label(stability_frame, text="测试模式", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        self.test_mode_var = tk.StringVar(value="comprehensive")
        mode_frame = ttk.LabelFrame(stability_frame, text="选择测试模式")
        mode_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

        ttk.Radiobutton(mode_frame, text="完整测试套件（所有模块）", variable=self.test_mode_var,
                       value="comprehensive").grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)
        ttk.Radiobutton(mode_frame, text="模块化测试（选择性运行）", variable=self.test_mode_var,
                       value="modular").grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 模块选择区域
        self.modules_frame = ttk.LabelFrame(stability_frame, text="测试模块选择")
        self.modules_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 模块复选框变量
        self.module_vars = {
            'system_robustness': tk.BooleanVar(value=True),
            'exception_recovery': tk.BooleanVar(value=True),
            'performance_response': tk.BooleanVar(value=False),
            'performance_resource': tk.BooleanVar(value=False),
            'performance_all': tk.BooleanVar(value=True)
        }

        # 系统健壮性测试
        ttk.Checkbutton(self.modules_frame, text="系统健壮性测试 (长时间压力测试)",
                        variable=self.module_vars['system_robustness']).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 异常恢复测试
        ttk.Checkbutton(self.modules_frame, text="异常恢复测试 (网络异常、数据异常)",
                        variable=self.module_vars['exception_recovery']).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 性能测试选项
        ttk.Label(self.modules_frame, text="性能测试:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)

        ttk.Checkbutton(self.modules_frame, text="完整性能测试 (响应+资源)",
                        variable=self.module_vars['performance_all']).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        ttk.Checkbutton(self.modules_frame, text="仅响应性能测试 (冷启动、下发→展示)",
                        variable=self.module_vars['performance_response']).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        ttk.Checkbutton(self.modules_frame, text="仅资源消耗测试 (CPU、内存)",
                        variable=self.module_vars['performance_resource']).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 绑定测试模式变化事件
        self.test_mode_var.trace('w', self.on_test_mode_changed)

        # 初始化模块选择状态
        self.on_test_mode_changed()

        # 测试参数设置
        ttk.Label(stability_frame, text="测试参数设置", font=("Arial", 12, "bold")).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        # 测试时长（支持分钟/小时）
        ttk.Label(stability_frame, text="测试时长:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        duration_frame = ttk.Frame(stability_frame)
        duration_frame.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        ttk.Entry(duration_frame, textvariable=self.duration_var, width=8).pack(side=tk.LEFT, padx=(0, 5))
        duration_unit_combo = ttk.Combobox(
            duration_frame,
            textvariable=self.duration_unit_var,
            values=["分钟", "小时"],
            state="readonly",
            width=6,
        )
        duration_unit_combo.pack(side=tk.LEFT)

        # 网络模拟方法
        ttk.Label(stability_frame, text="网络模拟方法:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
        self.network_method_var = tk.StringVar(value="root")
        network_combo = ttk.Combobox(stability_frame, textvariable=self.network_method_var,
                                   values=['root', 'pc_proxy', 'wifi_control', 'app_simulation'], state="readonly")
        network_combo.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 测试选项
        options_frame = ttk.LabelFrame(stability_frame, text="测试选项")
        options_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=10)

        self.baseline_establish_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="建立性能基线", variable=self.baseline_establish_var).grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)

        self.baseline_compare_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="与基线对比", variable=self.baseline_compare_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        self.no_mock_server_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="禁用Mock Server", variable=self.no_mock_server_var).grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)

        self.no_network_proxy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="禁用网络代理", variable=self.no_network_proxy_var).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        # pytest框架已强制启用，无需用户选择

        # 多设备支持
        ttk.Label(stability_frame, text="多设备测试", font=("Arial", 12, "bold")).grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        ttk.Label(stability_frame, text="设备序列号(多个用空格分隔):").grid(row=8, column=0, sticky=tk.W, padx=5, pady=5)
        self.multi_devices_var = tk.StringVar(value="emulator-5554")
        ttk.Entry(stability_frame, textvariable=self.multi_devices_var).grid(row=8, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 控制按钮
        button_frame = ttk.Frame(stability_frame)
        button_frame.grid(row=9, column=0, columnspan=2, pady=20)

        self.start_stability_btn = ttk.Button(button_frame, text="开始稳定性测试", command=self.start_stability_test)
        self.start_stability_btn.pack(side=tk.LEFT, padx=5)

        self.stop_stability_btn = ttk.Button(button_frame, text="⏹️ 停止测试", command=self.stop_test, state=["disabled"])
        self.stop_stability_btn.pack(side=tk.LEFT, padx=5)

        # 进度显示
        ttk.Label(stability_frame, text="测试进度", font=("Arial", 12, "bold")).grid(row=10, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        self.stability_progress = ttk.Progressbar(stability_frame, orient="horizontal", mode="indeterminate")
        self.stability_progress.grid(row=11, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 配置网格权重
        stability_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)

    def create_reports_tab(self):
        """创建报告选项卡"""
        reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(reports_frame, text="测试报告")

        # 报告列表
        ttk.Label(reports_frame, text="可用报告", font=("Arial", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        # 报告列表框
        list_frame = ttk.Frame(reports_frame)
        list_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        self.reports_listbox = tk.Listbox(list_frame, height=10)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.reports_listbox.yview)
        self.reports_listbox.config(yscrollcommand=scrollbar.set)

        self.reports_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 按钮
        button_frame = ttk.Frame(reports_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="刷新报告列表", command=self.refresh_reports).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="打开报告", command=self.open_selected_report).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="删除报告", command=self.delete_selected_report).pack(side=tk.LEFT, padx=5)

        # 报告预览
        ttk.Label(reports_frame, text="报告预览", font=("Arial", 12, "bold")).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        self.report_preview = scrolledtext.ScrolledText(reports_frame, height=15, wrap=tk.WORD)
        self.report_preview.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # 配置网格权重
        reports_frame.columnconfigure(0, weight=1)
        reports_frame.columnconfigure(1, weight=1)
        reports_frame.rowconfigure(1, weight=1)
        reports_frame.rowconfigure(4, weight=1)

        # 初始刷新报告列表
        self.refresh_reports()

    def create_logs_tab(self):
        """创建日志选项卡"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="实时日志")

        # 日志显示区域
        self.log_text = scrolledtext.ScrolledText(logs_frame, wrap=tk.WORD, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 控制按钮
        button_frame = ttk.Frame(logs_frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(button_frame, text="清空日志", command=self.clear_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="保存日志", command=self.save_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="自动滚动", command=self.toggle_auto_scroll).pack(side=tk.RIGHT, padx=5)

        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(button_frame, text="自动滚动到底部", variable=self.auto_scroll_var).pack(side=tk.RIGHT, padx=5)

    def create_title_area(self, parent):
        """创建标题区域"""
        title_frame = tk.Frame(parent, bg=UIColors.WHITE, relief='raised', bd=1)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        # 顶部操作区（主题切换）
        top_actions = tk.Frame(title_frame, bg=UIColors.WHITE)
        top_actions.pack(fill=tk.X, padx=15, pady=(10, 0))

        tk.Label(
            top_actions,
            text="主题：",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE
        ).pack(side=tk.LEFT)

        self.theme_combo = ttk.Combobox(
            top_actions,
            textvariable=self.theme_display_var,
            values=[TTK_THEME_LABELS.get(t, t) for t in TTKBOOTSTRAP_THEMES],
            state="readonly",
            width=10
        )
        # 轻量化：更小宽度、更统一字体、减少占位
        try:
            self.theme_combo.configure(font=UIFonts.CAPTION)
        except Exception:
            pass
        self.theme_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_change)

        # 标题
        title_label = tk.Label(
            title_frame,
            text="🚀 Monkey自动化测试工具",
            font=UIFonts.TITLE,
            fg=UIColors.TEXT_PRIMARY,
            bg=UIColors.WHITE
        )
        title_label.pack(pady=15)

        # 副标题
        subtitle_label = tk.Label(
            title_frame,
            text="车载端侧应用稳定性测试平台 | v1.0.0",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE
        )
        subtitle_label.pack(pady=(0, 15))

    def create_operation_panel(self, parent):
        """创建左侧操作面板"""
        # 项目配置卡片
        self.create_config_card(parent)

        # 测试操作卡片
        self.create_test_operation_card(parent)
        # 快速操作卡片已与“测试操作”合并，避免功能重复

    def create_config_card(self, parent):
        """创建项目配置卡片"""
        card = self.create_card(parent, "📋 项目配置")

        # 版本选择
        ttk.Label(card, text="测试项目版本:", font=UIFonts.BODY).grid(row=0, column=0, sticky=tk.W, pady=(10, 5))
        self.version_var = tk.StringVar()
        self.version_combo = ttk.Combobox(
            card,
            textvariable=self.version_var,
            values=self.available_versions,
            state="readonly",
            font=UIFonts.BODY
        )
        self.version_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=(10, 5))
        self.version_combo.bind("<<ComboboxSelected>>", self.on_version_selected)

        # 设备选择
        ttk.Label(card, text="目标设备:", font=UIFonts.BODY).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.device_sn_var = tk.StringVar(value="emulator-5554")
        # 下拉框：显示检测到的设备SN（可手动输入兜底）
        self.device_combo = ttk.Combobox(
            card,
            textvariable=self.device_sn_var,
            values=[],
            state="readonly",
            font=UIFonts.BODY
        )
        self.device_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        self.device_combo.bind("<<ComboboxSelected>>", self._on_device_selected)

        # 设备状态提示（项目配置区内的轻量指示器）
        self._device_status_in_config = tk.Label(
            card,
            text="● 设备：未检测",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            anchor="w"
        )
        self._device_status_in_config.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(2, 6))

        # ADB 路径（Windows 上常见 PATH 未配置导致无法识别设备）
        ttk.Label(card, text="ADB路径:", font=UIFonts.BODY).grid(row=3, column=0, sticky=tk.W, pady=5)
        adb_row = tk.Frame(card, bg=UIColors.WHITE)
        adb_row.grid(row=3, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        adb_row.grid_columnconfigure(0, weight=1)
        ttk.Entry(adb_row, textvariable=self.adb_path_var, font=UIFonts.BODY).grid(row=0, column=0, sticky=tk.EW)
        self.create_action_button(
            adb_row,
            text="浏览",
            command=self.browse_adb,
            variant="secondary"
        ).grid(row=0, column=1, padx=(8, 0))

        # 测试应用选择（APK / 已安装）
        ttk.Label(card, text="测试应用:", font=UIFonts.BODY).grid(row=4, column=0, sticky=tk.W, pady=5)
        app_row = tk.Frame(card, bg=UIColors.WHITE)
        app_row.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        tk.Radiobutton(
            app_row,
            text="安装APK",
            variable=self.app_source_var,
            value="apk",
            command=self._on_app_source_changed,
            bg=UIColors.WHITE,
            font=UIFonts.BODY,
            cursor="hand2",
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            app_row,
            text="使用已安装应用",
            variable=self.app_source_var,
            value="installed",
            command=self._on_app_source_changed,
            bg=UIColors.WHITE,
            font=UIFonts.BODY,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(card, text="包名:", font=UIFonts.BODY).grid(row=5, column=0, sticky=tk.W, pady=5)
        pkg_row = tk.Frame(card, bg=UIColors.WHITE)
        pkg_row.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        pkg_row.grid_columnconfigure(0, weight=1)
        self.package_combo = ttk.Combobox(
            pkg_row,
            textvariable=self.package_name_var,
            values=[],
            state="readonly",
            font=UIFonts.BODY
        )
        self.package_combo.grid(row=0, column=0, sticky=tk.EW)
        self.package_combo.bind("<<ComboboxSelected>>", self._on_package_selected)
        self.create_action_button(
            pkg_row,
            text="扫描",
            command=self.refresh_installed_apps,
            variant="secondary"
        ).grid(row=0, column=1, padx=(8, 0))

        # APK选择
        ttk.Label(card, text="测试APK:", font=UIFonts.BODY).grid(row=6, column=0, sticky=tk.W, pady=5)
        apk_frame = tk.Frame(card, bg=UIColors.WHITE)
        apk_frame.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)

        self.apk_path_var = tk.StringVar()
        apk_entry = ttk.Entry(apk_frame, textvariable=self.apk_path_var, font=UIFonts.BODY)
        apk_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.create_action_button(
            apk_frame,
            text="浏览",
            command=self.browse_apk,
            variant="primary",
            side=tk.RIGHT,
            padx=(10, 0)
        )

        # 刷新设备按钮
        self.create_action_button(
            card,
            text="🔄 刷新设备列表",
            command=self.refresh_devices,
            variant="success"
        ).grid(row=7, column=0, columnspan=2, pady=(15, 10))

        card.columnconfigure(1, weight=1)
        self._on_app_source_changed()

    def create_test_operation_card(self, parent):
        """创建测试操作卡片（弹窗入口）"""
        card = self.create_card(parent, "⚡ 测试操作")

        info_label = tk.Label(
            card,
            text="执行控制已集成到主界面；测试参数在配置窗口中调整后会自动保存（也可点“同步配置”立即写入）。",
            font=UIFonts.BODY,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            justify=tk.LEFT
        )
        info_label.pack(fill=tk.X, pady=(10, 10))

        # 第一行：打开配置窗口
        top_row = tk.Frame(card, bg=UIColors.WHITE)
        top_row.pack(fill=tk.X, pady=(0, 10))

        self.create_action_button(
            top_row,
            text="🛠️ 打开测试配置窗口",
            command=self.open_test_config_window,
            variant="primary",
            side=tk.LEFT,
            padx=(0, 0)
        )

        # 第二行：执行控制按钮
        btn_row = tk.Frame(card, bg=UIColors.WHITE)
        btn_row.pack(fill=tk.X, pady=(0, 5))

        # 复用 self.start_test_btn / self.stop_test_btn（测试逻辑里会操作它们）
        self.start_test_btn = self.create_action_button(
            btn_row, text="▶️ 开始稳定性测试",
            command=self.start_stability_test,
            variant="primary",
            side=tk.LEFT,
            padx=(0, 10)
        )

        self.stop_test_btn = self.create_action_button(
            btn_row, text="⏹️ 停止测试",
            command=self.stop_test,
            variant="error",
            side=tk.LEFT,
            padx=(0, 10)
        )
        self.stop_test_btn.config(state="disabled")

        self.create_action_button(
            btn_row, text="🐒 运行传统Monkey测试",
            command=self.start_traditional_test,
            variant="info",
            side=tk.LEFT
        )

        # 摘要信息：放在按钮下方，全宽显示，自动换行，避免被挤压截断
        summary_wrap = tk.Frame(card, bg=UIColors.WHITE)
        summary_wrap.pack(fill=tk.X, pady=(8, 10))
        self._test_summary_label = tk.Label(
            summary_wrap,
            text="",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            justify=tk.LEFT,
            anchor="nw",
        )
        self._test_summary_label.pack(fill=tk.X)

        def _sync_summary_wrap(_e=None):
            if not self._test_summary_label:
                return
            try:
                if not self._test_summary_label.winfo_exists():
                    return
                # 留一点内边距
                w = max(200, self._test_summary_label.winfo_width() - 10)
                self._test_summary_label.config(wraplength=w)
            except Exception:
                pass

        summary_wrap.bind("<Configure>", _sync_summary_wrap)

        # 第三行：常用入口（合并原“快速操作”中的不重复功能）
        aux_row = tk.Frame(card, bg=UIColors.WHITE)
        aux_row.pack(fill=tk.X, pady=(8, 0))

        self.create_action_button(
            aux_row,
            text="📄 查看测试报告",
            command=self.show_reports_window,
            variant="warning",
            side=tk.LEFT
        )

        # Mock Server 控制与状态（轻量但可用）
        mock_row = tk.Frame(card, bg=UIColors.WHITE)
        mock_row.pack(fill=tk.X, pady=(10, 0))

        self.create_action_button(
            mock_row,
            text="🧪 启动Mock",
            command=self.start_mock_server_from_gui,
            variant="success",
            side=tk.LEFT,
            padx=(0, 10)
        )

        self.create_action_button(
            mock_row,
            text="⏹️ 停止Mock",
            command=self.stop_mock_server_from_gui,
            variant="error",
            side=tk.LEFT,
            padx=(0, 10)
        )

        self.create_action_button(
            mock_row,
            text="📝 编辑规则",
            command=self.open_mock_rules_editor,
            variant="primary",
            side=tk.LEFT
        )

        self._mock_status_label = tk.Label(
            mock_row,
            text="Mock：未启动",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            anchor="w"
        )
        self._mock_status_label.pack(side=tk.LEFT, padx=(12, 0))

        # 活动信息（最近请求）
        self._mock_activity_text = tk.Text(
            card,
            height=4,
            font=('Consolas', 9),
            bg=UIColors.BG_DARK,
            relief='flat'
        )
        self._mock_activity_text.pack(fill=tk.X, pady=(10, 0))
        self._mock_activity_text.insert(tk.END, "Mock活动：暂无\n")
        self._mock_activity_text.config(state="disabled")
        self._poll_mock_activity()

        # 初始化摘要内容
        self.update_test_operation_summary()
        self._bind_test_summary_traces()

    def update_test_operation_summary(self):
        """更新主界面“测试操作”卡片的配置摘要文本"""
        if not self._test_summary_label:
            return
        # label 可能被销毁（例如界面重建），需要防护，避免 bad window path name
        try:
            if not self._test_summary_label.winfo_exists():
                self._test_summary_label = None
                return
        except Exception:
            self._test_summary_label = None
            return

        mode = self.test_mode_var.get()
        if mode == "comprehensive":
            mode_text = "完整测试套件"
            modules_text = "系统健壮性、异常恢复、完整性能"
        else:
            mode_text = "模块化测试"
            enabled = [k for k, v in self.module_vars.items() if v.get()]
            # 显示更友好的模块名
            name_map = {
                "system_robustness": "系统健壮性",
                "exception_recovery": "异常恢复",
                "performance_all": "完整性能",
                "performance_response": "响应性能",
                "performance_resource": "资源消耗",
            }
            modules_text = "、".join([name_map.get(k, k) for k in enabled]) if enabled else "（未选择）"

        duration = self.duration_var.get()
        unit = getattr(self, "duration_unit_var", None)
        unit_txt = unit.get() if unit is not None else "小时"
        if unit_txt.startswith("分"):
            duration_display = f"{duration}min"
        else:
            duration_display = f"{duration}h"
        network = self.network_method_var.get()
        throttle = self.throttle_var.get()
        count = self.count_var.get()
        self._test_summary_label.config(
            text=f"当前模式：{mode_text} | 模块：{modules_text}\n"
                 f"稳定性：{duration_display} / 网络：{network}  |  Monkey：throttle={throttle}ms / count={count}"
        )

    def _bind_test_summary_traces(self):
        """绑定配置变量变化，实时刷新主界面摘要（避免配置修改后摘要不更新）"""
        if getattr(self, "_summary_traces_bound", False):
            return
        self._summary_traces_bound = True

        def _on_change(*_args):
            self.update_test_operation_summary()

        # StringVar/BooleanVar 的兼容写法：优先 trace_add
        vars_to_trace = [
            self.test_mode_var,
            self.duration_var,
            self.network_method_var,
            self.multi_devices_var,
            self.throttle_var,
            self.count_var,
            self.uninstall_var,
            self.baseline_establish_var,
            self.baseline_compare_var,
            self.no_mock_server_var,
            self.no_network_proxy_var,
        ]
        vars_to_trace.extend(list(self.module_vars.values()))

        for v in vars_to_trace:
            try:
                v.trace_add("write", _on_change)  # type: ignore
            except Exception:
                try:
                    v.trace("w", _on_change)
                except Exception:
                    pass

    def open_test_config_window(self):
        """打开测试配置弹窗"""
        if self.test_config_window and tk.Toplevel.winfo_exists(self.test_config_window):
            self.test_config_window.lift()
            return

        # 自动保存开启后：先 flush 一次待保存的变更，避免“打开弹窗 -> 从文件覆盖回旧值”
        try:
            self._autosave_now(force=True, notify=False)
        except Exception:
            pass
        # 仍保留“从文件读取配置”的行为（例如外部编辑了配置文件）
        self.load_test_ui_config()

        self.test_config_window = tk.Toplevel(self.root)
        self.test_config_window.title("测试配置")
        # 打开时采用合适尺寸：优先 85% 屏幕大小，但不超过/不低于推荐尺寸区间
        try:
            self.test_config_window.update_idletasks()
            sw = self.test_config_window.winfo_screenwidth()
            sh = self.test_config_window.winfo_screenheight()
            w = int(sw * 0.85)
            h = int(sh * 0.85)
            # 建议尺寸 1100x820；避免过大/过小
            w = max(1100, min(w, 1400))
            h = max(820, min(h, 1000))
            x = max(20, int((sw - w) / 2))
            y = max(20, int((sh - h) / 3))
            self.test_config_window.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.test_config_window.geometry("1100x820")
        self.test_config_window.configure(bg=UIColors.BG_LIGHT)
        self.test_config_window.minsize(1000, 700)
        self.test_config_window.grid_rowconfigure(0, weight=1)
        self.test_config_window.grid_columnconfigure(0, weight=1)

        container = tk.Frame(self.test_config_window, bg=UIColors.BG_LIGHT)
        container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # 构建“分页 + 双列”配置界面（无滚动条）
        self.build_test_config_ui(container)

    def build_test_config_ui(self, parent):
        """构建测试配置表单（合并：稳定性测试 + 传统Monkey；仅配置，不含执行控制）"""
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # 外层：上部配置区 + 底部操作区
        wrapper = tk.Frame(parent, bg=UIColors.BG_LIGHT)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        content = tk.Frame(wrapper, bg=UIColors.BG_LIGHT)
        content.grid(row=0, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)
        # 让最底行（传统Monkey参数/提示）也能拉伸，避免提示文字被截断
        content.grid_rowconfigure(2, weight=1)

        # ========== 左列：稳定性测试配置（模式 + 模块） ==========
        mode_card = self.create_card_grid(content, "🧭 稳定性测试 - 测试模式", row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        tk.Radiobutton(
            mode_card, text="完整测试套件（推荐）",
            variable=self.test_mode_var, value="comprehensive",
            command=self.on_test_mode_changed,
            bg=UIColors.WHITE, font=UIFonts.BODY, cursor='hand2'
        ).pack(anchor=tk.W, pady=4)
        tk.Radiobutton(
            mode_card, text="模块化测试（自定义模块组合）",
            variable=self.test_mode_var, value="modular",
            command=self.on_test_mode_changed,
            bg=UIColors.WHITE, font=UIFonts.BODY, cursor='hand2'
        ).pack(anchor=tk.W, pady=4)

        modules_card = self.create_card_grid(content, "🧩 稳定性测试 - 模块选择", row=1, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        self.modules_frame = tk.Frame(modules_card, bg=UIColors.WHITE)
        self.modules_frame.pack(fill=tk.BOTH, expand=True)

        modules_data = [
            ('system_robustness', '🏗️ 系统健壮性测试', '长时间压力测试'),
            ('exception_recovery', '🔄 异常恢复测试', '网络/数据异常'),
            ('performance_all', '📊 完整性能测试', '响应+资源'),
            ('performance_response', '⚡ 仅响应性能测试', '冷启动、延迟'),
            ('performance_resource', '💾 仅资源消耗测试', 'CPU、内存')
        ]
        for module_key, main_text, sub_text in modules_data:
            tk.Checkbutton(
                self.modules_frame,
                text=f"{main_text}（{sub_text}）",
                variable=self.module_vars[module_key],
                bg=UIColors.WHITE,
                font=UIFonts.BODY,
                cursor='hand2'
            ).pack(anchor=tk.W, pady=3)

        # ========== 右列：稳定性参数 + 传统Monkey 参数/提示 ==========
        params_card = self.create_card_grid(content, "🛡️ 稳定性测试 - 参数设置", row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        form = tk.Frame(params_card, bg=UIColors.WHITE)
        form.pack(fill=tk.X, pady=5)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="测试时长:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=6)
        dur_row = tk.Frame(form, bg=UIColors.WHITE)
        dur_row.grid(row=0, column=1, sticky=tk.EW, pady=6, padx=(10, 0))
        tk.Entry(dur_row, textvariable=self.duration_var, font=UIFonts.BODY, width=8).pack(side=tk.LEFT)
        ttk.Combobox(
            dur_row,
            textvariable=self.duration_unit_var,
            values=["分钟", "小时"],
            state="readonly",
            width=6,
        ).pack(side=tk.LEFT, padx=(8, 0))

        tk.Label(form, text="网络模拟方法:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=6)
        ttk.Combobox(
            form,
            textvariable=self.network_method_var,
            values=['root', 'pc_proxy', 'wifi_control', 'app_simulation'],
            state="readonly"
        ).grid(row=1, column=1, sticky=tk.EW, pady=6, padx=(10, 0))

        tk.Label(form, text="多设备SN(空格分隔):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=2, column=0, sticky=tk.W, pady=6)
        tk.Entry(form, textvariable=self.multi_devices_var, font=UIFonts.BODY).grid(row=2, column=1, sticky=tk.EW, pady=6, padx=(10, 0))

        opts_card = self.create_card_grid(content, "⚙️ 稳定性测试 - 测试选项", row=1, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        opts = [
            ("建立性能基线", self.baseline_establish_var),
            ("与基线对比", self.baseline_compare_var),
            ("禁用Mock Server", self.no_mock_server_var),
            ("禁用网络代理", self.no_network_proxy_var),
        ]
        for i, (text, var) in enumerate(opts):
            tk.Checkbutton(
                opts_card,
                text=text,
                variable=var,
                bg=UIColors.WHITE,
                font=UIFonts.BODY,
                cursor='hand2'
            ).grid(row=i // 2, column=i % 2, sticky=tk.W, padx=6, pady=6)
        opts_card.grid_columnconfigure(0, weight=1)
        opts_card.grid_columnconfigure(1, weight=1)

        # Mock Server 配置（与“禁用Mock Server”联动）
        ms_card = self.create_card_grid(content, "🧪 Mock Server - 配置", row=3, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        ms_form = tk.Frame(ms_card, bg=UIColors.WHITE)
        ms_form.pack(fill=tk.X, pady=5)
        ms_form.grid_columnconfigure(1, weight=1)

        tk.Label(ms_form, text="Host:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=6)
        tk.Entry(ms_form, textvariable=self.mock_host_var, font=UIFonts.BODY).grid(row=0, column=1, sticky=tk.EW, pady=6, padx=(10, 0))

        tk.Label(ms_form, text="Port:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=6)
        tk.Entry(ms_form, textvariable=self.mock_port_var, font=UIFonts.BODY).grid(row=1, column=1, sticky=tk.EW, pady=6, padx=(10, 0))

        tk.Label(ms_form, text="规则文件:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=2, column=0, sticky=tk.W, pady=6)
        path_row = tk.Frame(ms_form, bg=UIColors.WHITE)
        path_row.grid(row=2, column=1, sticky=tk.EW, pady=6, padx=(10, 0))
        path_row.grid_columnconfigure(0, weight=1)
        tk.Entry(path_row, textvariable=self.mock_rules_path_var, font=UIFonts.BODY).grid(row=0, column=0, sticky=tk.EW)
        self.create_action_button(
            path_row,
            text="编辑",
            command=self.open_mock_rules_editor,
            variant="primary"
        ).grid(row=0, column=1, padx=(8, 0))

        # 传统Monkey配置（放在右列底部）
        t_card = self.create_card_grid(content, "🐒 传统Monkey - 参数", row=2, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        t_form = tk.Frame(t_card, bg=UIColors.WHITE)
        t_form.pack(fill=tk.X)
        t_form.grid_columnconfigure(1, weight=1)

        tk.Label(t_form, text="节流时间(ms):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=8)
        tk.Entry(t_form, textvariable=self.throttle_var, font=UIFonts.BODY).grid(row=0, column=1, sticky=tk.EW, pady=8, padx=(10, 0))

        tk.Label(t_form, text="事件数量:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=8)
        tk.Entry(t_form, textvariable=self.count_var, font=UIFonts.BODY).grid(row=1, column=1, sticky=tk.EW, pady=8, padx=(10, 0))

        tk.Checkbutton(
            t_form, text="安装前卸载应用",
            variable=self.uninstall_var,
            bg=UIColors.WHITE, font=UIFonts.BODY, cursor='hand2'
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=8)

        t_hint = self.create_card_grid(content, "💡 传统Monkey - 提示", row=2, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        hint_label = tk.Label(
            t_hint,
            text="传统Monkey测试会自动安装/启用辅助工具（如Wifi Manager、simiasque），并执行随机事件压力测试。\n\n建议：先确认ADB连接稳定，APK路径正确。",
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.BODY,
            justify=tk.LEFT,
            anchor="nw",
            # wraplength 会根据卡片宽度动态更新，避免固定值导致“怪异换行”
            wraplength=500
        )
        hint_label.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        def _sync_hint_wrap(_e=None):
            try:
                if hint_label.winfo_exists():
                    w = max(260, t_hint.winfo_width() - 24)
                    hint_label.config(wraplength=w)
            except Exception:
                pass

        t_hint.bind("<Configure>", _sync_hint_wrap)

        # ========== 底部操作区：保存/关闭 ==========
        footer = tk.Frame(wrapper, bg=UIColors.BG_LIGHT)
        footer.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        footer.grid_columnconfigure(0, weight=1)

        tk.Label(
            footer,
            text="提示：配置会自动保存到 conf/test_ui_config.json（无需手动保存）。如需立即写入，可点击“同步配置”。",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.BG_LIGHT,
            anchor="w"
        ).grid(row=0, column=0, sticky="ew")

        btns = tk.Frame(footer, bg=UIColors.BG_LIGHT)
        btns.grid(row=0, column=1, sticky="e")

        self.create_action_button(
            btns,
            text="🔄 同步配置",
            command=self.save_test_ui_config,
            variant="success",
            side=tk.LEFT,
            padx=(0, 10)
        )

        self.create_action_button(
            btns,
            text="关闭",
            command=lambda: self.test_config_window.destroy() if self.test_config_window else None,
            variant="secondary",
            side=tk.LEFT
        )

        # 初始化模块选择状态（根据当前模式禁用/启用模块区域）
        self.on_test_mode_changed()

    def _get_test_ui_config_path(self):
        """测试配置持久化文件路径（与 conf/project.json 分离）"""
        return os.path.join("conf", "test_ui_config.json")

    def _collect_test_ui_config(self):
        """从各 tk 变量采集当前测试配置（用于保存）"""
        def _get_var(attr: str, default=""):
            v = getattr(self, attr, None)
            try:
                if v is None:
                    return default
                return v.get()
            except Exception:
                return default

        return {
            "theme": self.theme_var.get(),
            "adb_path": self.adb_path_var.get(),
            "app_source": self.app_source_var.get(),
            "package_name": self.package_name_var.get(),
            # 主界面常用配置也纳入持久化（避免用户重启丢失）
            "prj_ver": _get_var("version_var", ""),
            "device_sn": _get_var("device_sn_var", ""),
            "apk_path": _get_var("apk_path_var", ""),
            "email": _get_var("email_var", ""),
            "test_mode": self.test_mode_var.get(),
            "modules": {k: bool(v.get()) for k, v in self.module_vars.items()},
            "duration": self.duration_var.get(),
            "duration_unit": self.duration_unit_var.get(),
            "network_method": self.network_method_var.get(),
            "multi_devices": self.multi_devices_var.get(),
            "baseline_establish": bool(self.baseline_establish_var.get()),
            "baseline_compare": bool(self.baseline_compare_var.get()),
            "no_mock_server": bool(self.no_mock_server_var.get()),
            "no_network_proxy": bool(self.no_network_proxy_var.get()),
            "mock_server": {
                "mode": "mitmproxy",
                "host": self.mock_host_var.get(),
                "port": self.mock_port_var.get(),
                "rules_path": self.mock_rules_path_var.get(),
            },
            "traditional_monkey": {
                "throttle": self.throttle_var.get(),
                "count": self.count_var.get(),
                "uninstall": bool(self.uninstall_var.get()),
            },
        }

    def _apply_test_ui_config(self, cfg):
        """将配置字典应用到 tk 变量（用于加载）"""
        if not isinstance(cfg, dict):
            return

        # 主题（仅恢复选择；真正应用在界面创建后进行）
        theme = cfg.get("theme")
        if isinstance(theme, str) and theme.strip():
            self.theme_var.set(theme.strip())
            # 同步显示用中文标签（如果下拉框已创建则生效）
            label = TTK_THEME_LABELS.get(theme.strip(), theme.strip())
            try:
                self.theme_display_var.set(label)
            except Exception:
                pass

        adb_path = cfg.get("adb_path")
        if isinstance(adb_path, str):
            self.adb_path_var.set(adb_path.strip())

        app_source = cfg.get("app_source")
        if app_source in ("apk", "installed"):
            self.app_source_var.set(app_source)
        package_name = cfg.get("package_name")
        if isinstance(package_name, str):
            self.package_name_var.set(package_name.strip())

        # 主界面常用配置（可选项：不存在则不覆盖）
        prj_ver = cfg.get("prj_ver")
        if isinstance(prj_ver, str) and prj_ver.strip():
            try:
                if hasattr(self, "version_var") and self.version_var is not None:
                    self.version_var.set(prj_ver.strip())
            except Exception:
                pass
        device_sn = cfg.get("device_sn")
        if isinstance(device_sn, str) and device_sn.strip():
            try:
                if hasattr(self, "device_sn_var") and self.device_sn_var is not None:
                    self.device_sn_var.set(device_sn.strip())
            except Exception:
                pass
        apk_path = cfg.get("apk_path")
        if isinstance(apk_path, str):
            try:
                if hasattr(self, "apk_path_var") and self.apk_path_var is not None:
                    self.apk_path_var.set(apk_path.strip())
            except Exception:
                pass
        email = cfg.get("email")
        if isinstance(email, str):
            try:
                if hasattr(self, "email_var") and self.email_var is not None:
                    self.email_var.set(email.strip())
            except Exception:
                pass

        if cfg.get("test_mode") in ("comprehensive", "modular"):
            self.test_mode_var.set(cfg["test_mode"])

        modules = cfg.get("modules")
        if isinstance(modules, dict):
            for k, v in modules.items():
                if k in self.module_vars:
                    try:
                        self.module_vars[k].set(bool(v))
                    except Exception:
                        pass

        if "duration" in cfg:
            self.duration_var.set(str(cfg["duration"]))
        if "duration_unit" in cfg:
            try:
                self.duration_unit_var.set(str(cfg["duration_unit"]))
            except Exception:
                pass
        if "network_method" in cfg:
            self.network_method_var.set(str(cfg["network_method"]))
        if "multi_devices" in cfg:
            self.multi_devices_var.set(str(cfg["multi_devices"]))

        if "baseline_establish" in cfg:
            self.baseline_establish_var.set(bool(cfg["baseline_establish"]))
        if "baseline_compare" in cfg:
            self.baseline_compare_var.set(bool(cfg["baseline_compare"]))
        if "no_mock_server" in cfg:
            self.no_mock_server_var.set(bool(cfg["no_mock_server"]))
        if "no_network_proxy" in cfg:
            self.no_network_proxy_var.set(bool(cfg["no_network_proxy"]))

        tm = cfg.get("traditional_monkey")
        if isinstance(tm, dict):
            if "throttle" in tm:
                self.throttle_var.set(str(tm["throttle"]))
            if "count" in tm:
                self.count_var.set(str(tm["count"]))
            if "uninstall" in tm:
                self.uninstall_var.set(bool(tm["uninstall"]))

        ms = cfg.get("mock_server")
        if isinstance(ms, dict):
            if "host" in ms:
                self.mock_host_var.set(str(ms["host"]))
            if "port" in ms:
                self.mock_port_var.set(str(ms["port"]))
            if "rules_path" in ms:
                self.mock_rules_path_var.set(str(ms["rules_path"]))

        # 确保模块区启用/禁用状态正确
        self.on_test_mode_changed()

        # 刷新主界面摘要（如果已创建）
        self.update_test_operation_summary()

    def apply_theme_from_config(self):
        """根据当前 theme_var 应用主题（界面创建后调用更安全）"""
        try:
            if HAS_TTKBOOTSTRAP:
                self.apply_selected_theme()
        except Exception:
            pass

    def load_test_ui_config(self):
        """从文件加载测试配置（启动/打开窗口时读取；不自动写回）"""
        path = self._get_test_ui_config_path()
        cfg = read_json(path, default=None)
        if not isinstance(cfg, dict):
            return
        try:
            # 加载时禁止触发自动保存（避免“读 -> 立刻写”以及大量trace回调）
            self._suppress_autosave = True
            self._apply_test_ui_config(cfg)
            self._last_saved_test_cfg = cfg
        except Exception as e:
            logging.warning(f"加载测试配置失败: {e}")
        finally:
            self._suppress_autosave = False

    def save_test_ui_config(self):
        """手动同步测试配置到文件（自动保存已开启；此按钮用于立即写入）"""
        self._autosave_now(force=True, notify=True)

    def _bind_autosave_traces(self):
        """绑定配置变更 -> 自动保存（带防抖），对用户透明"""
        if getattr(self, "_autosave_traces_bound", False):
            return
        self._autosave_traces_bound = True

        def _on_change(*_args):
            self._schedule_autosave()

        vars_to_trace = [
            # 主题/ADB/应用选择
            getattr(self, "theme_var", None),
            getattr(self, "adb_path_var", None),
            getattr(self, "app_source_var", None),
            getattr(self, "package_name_var", None),
            # 主界面常用项
            getattr(self, "version_var", None),
            getattr(self, "device_sn_var", None),
            getattr(self, "apk_path_var", None),
            getattr(self, "email_var", None),
            # 测试配置项
            getattr(self, "test_mode_var", None),
            getattr(self, "duration_var", None),
            getattr(self, "network_method_var", None),
            getattr(self, "multi_devices_var", None),
            getattr(self, "throttle_var", None),
            getattr(self, "count_var", None),
            getattr(self, "uninstall_var", None),
            getattr(self, "baseline_establish_var", None),
            getattr(self, "baseline_compare_var", None),
            getattr(self, "no_mock_server_var", None),
            getattr(self, "no_network_proxy_var", None),
            getattr(self, "mock_host_var", None),
            getattr(self, "mock_port_var", None),
            getattr(self, "mock_rules_path_var", None),
        ]
        try:
            vars_to_trace.extend(list(self.module_vars.values()))
        except Exception:
            pass

        for v in [x for x in vars_to_trace if x is not None]:
            try:
                v.trace_add("write", _on_change)  # type: ignore
            except Exception:
                try:
                    v.trace("w", _on_change)
                except Exception:
                    pass

    def _schedule_autosave(self):
        """配置变更时调用：防抖自动保存"""
        if getattr(self, "_suppress_autosave", False):
            return
        try:
            if self._autosave_job is not None:
                self.root.after_cancel(self._autosave_job)
        except Exception:
            pass
        try:
            # 500ms 防抖：输入框连续输入不会疯狂写盘
            self._autosave_job = self.root.after(500, lambda: self._autosave_now(force=False, notify=False))
        except Exception:
            self._autosave_job = None

    def _autosave_now(self, force: bool = False, notify: bool = False):
        """立即保存一次当前配置（自动保存内部/手动同步均可调用）"""
        if getattr(self, "_suppress_autosave", False):
            return
        # 清理 pending job
        self._autosave_job = None

        path = self._get_test_ui_config_path()
        cfg = self._collect_test_ui_config()

        # 无变化则跳过写盘
        if (not force) and isinstance(self._last_saved_test_cfg, dict) and cfg == self._last_saved_test_cfg:
            return

        try:
            write_json(path, cfg, indent=2)
            self._last_saved_test_cfg = cfg
        except Exception as e:
            # 自动保存对用户透明：不弹窗、不打断交互，只记录日志
            logging.warning(f"自动保存测试配置失败: {e}")
            return

        # 手动同步：允许给用户一个轻量反馈（不弹窗）
        if notify:
            try:
                self.update_test_operation_summary()
            except Exception:
                pass
            try:
                self.update_status(f"✅ 配置已同步: {path}")
            except Exception:
                pass

    # =========================
    # Mock Server GUI 集成
    # =========================
    def _get_default_mock_rules(self):
        return {
            "responses": [
                {
                    "method": "GET",
                    "path": "/api/data",
                    "response": {"status": 200, "body": {"status": "success", "data": []}}
                }
            ]
        }

    def load_mock_rules(self):
        """从规则文件读取mock响应配置（返回dict）"""
        path = self.mock_rules_path_var.get().strip()
        if not path:
            return self._get_default_mock_rules()
        try:
            p = Path(path)
            if not p.exists():
                return self._get_default_mock_rules()
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            logging.warning(f"读取Mock规则失败: {e}")
            return self._get_default_mock_rules()

    def save_mock_rules(self, rules: dict):
        """保存mock响应规则到文件"""
        path = self.mock_rules_path_var.get().strip()
        if not path:
            path = str(Path("conf") / "mock_rules.json")
            self.mock_rules_path_var.set(path)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")

    def apply_mock_rules_to_server(self):
        """将规则应用到运行中的mock server（若已启动）"""
        if not self._mock_server:
            return
        try:
            rules = self.load_mock_rules()
            if isinstance(rules, dict) and "responses" in rules:
                self._mock_server.mock_responses = rules
                self.update_status("🧪 Mock规则已应用")
        except Exception as e:
            logging.warning(f"应用Mock规则失败: {e}")

    def start_mock_server_from_gui(self):
        """手动启动Mock Server（GUI按钮）"""
        try:
            host = self.mock_host_var.get().strip() or "127.0.0.1"
            port = int(self.mock_port_var.get().strip() or "8080")

            # 若已在运行，先停止（避免端口占用）
            if self._mock_server and self._mock_server.is_running():
                self.stop_mock_server_from_gui()

            self._mock_server = mock_server_mod.MockServer(host=host, port=port)
            self._mock_server.mock_responses = self.load_mock_rules()
            self._mock_server.start()
            self._mock_server_started_by_gui = True
            self._update_mock_status_ui()
            self.update_status(f"🧪 Mock Server已启动: http://{host}:{port}")
        except Exception as e:
            self.update_status(f"Mock Server启动失败: {e}")

    def stop_mock_server_from_gui(self):
        """手动停止Mock Server（GUI按钮）"""
        try:
            if self._mock_server:
                self._mock_server.stop()
            self._mock_server = None
            self._mock_server_started_by_gui = False
            self._update_mock_status_ui()
            self.update_status("🧪 Mock Server已停止")
        except Exception as e:
            self.update_status(f"Mock Server停止失败: {e}")

    def ensure_mock_server_running(self):
        """测试前确保mock server运行（依赖 no_mock_server_var）"""
        if self.no_mock_server_var.get():
            return
        if self._mock_server and self._mock_server.is_running():
            return
        # 自动启动：不弹窗、不打断流程
        self.start_mock_server_from_gui()

    def _update_mock_status_ui(self):
        if not self._mock_status_label:
            return
        try:
            if not self._mock_status_label.winfo_exists():
                self._mock_status_label = None
                return
        except Exception:
            self._mock_status_label = None
            return

        if self.no_mock_server_var.get():
            self._mock_status_label.config(text="Mock：已禁用", fg=UIColors.TEXT_SECONDARY)
            return

        if self._mock_server and self._mock_server.is_running():
            self._mock_status_label.config(text="Mock：运行中", fg=UIColors.SUCCESS)
        else:
            self._mock_status_label.config(text="Mock：未启动", fg=UIColors.TEXT_SECONDARY)

    def _poll_mock_activity(self):
        """定时刷新mock活动信息（最近请求）"""
        self._update_mock_status_ui()
        try:
            if self._mock_activity_text and self._mock_activity_text.winfo_exists():
                lines = []
                if self._mock_server and self._mock_server.is_running():
                    activity = self._mock_server.get_activity_snapshot()
                    for item in activity[-8:]:
                        lines.append(f"[{item.get('ts')}] {item.get('method')} {item.get('path')} -> {item.get('status')}")
                if not lines:
                    lines = ["Mock活动：暂无"]
                self._mock_activity_text.config(state="normal")
                self._mock_activity_text.delete("1.0", tk.END)
                self._mock_activity_text.insert(tk.END, "\n".join(lines) + "\n")
                self._mock_activity_text.config(state="disabled")
        except Exception:
            pass
        # 1s刷新一次
        try:
            self.root.after(1000, self._poll_mock_activity)
        except Exception:
            pass

    def open_mock_rules_editor(self):
        """打开Mock规则编辑器（JSON）"""
        win = tk.Toplevel(self.root)
        win.title("Mock Server 规则编辑")
        win.geometry("900x650")
        win.configure(bg=UIColors.BG_LIGHT)
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        container = tk.Frame(win, bg=UIColors.WHITE, relief='raised', bd=1)
        container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        container.grid_rowconfigure(1, weight=1)
        container.grid_columnconfigure(0, weight=1)

        tk.Label(
            container,
            text="规则格式：{\"responses\":[{\"method\":\"GET\",\"path\":\"/api/data\",\"query\":{...},\"response\":{\"status\":200,\"body\":{...}}}]}",
            bg=UIColors.WHITE, fg=UIColors.TEXT_SECONDARY, font=UIFonts.CAPTION, justify=tk.LEFT, anchor="w"
        ).grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 8))

        text = scrolledtext.ScrolledText(container, font=('Consolas', 10), wrap=tk.NONE)
        text.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        rules = self.load_mock_rules()
        text.insert(tk.END, json.dumps(rules, ensure_ascii=False, indent=2))

        btn_row = tk.Frame(container, bg=UIColors.WHITE)
        btn_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        btn_row.grid_columnconfigure(0, weight=1)

        def _save():
            try:
                data = json.loads(text.get("1.0", tk.END).strip() or "{}")
                if not isinstance(data, dict) or "responses" not in data:
                    messagebox.showerror("格式错误", "规则必须是包含 responses 的JSON对象")
                    return
                self.save_mock_rules(data)
                self.apply_mock_rules_to_server()
                self.log_info_ui("🧪 Mock规则已保存")
                messagebox.showinfo("保存成功", "Mock规则已保存并（如已启动）已应用。")
            except Exception as e:
                messagebox.showerror("保存失败", f"无法保存规则：{e}")

        self.create_action_button(
            btn_row,
            text="💾 保存并应用",
            command=_save,
            variant="success",
            side=tk.LEFT
        )

        self.create_action_button(
            btn_row,
            text="关闭",
            command=win.destroy,
            variant="secondary",
            side=tk.RIGHT
        )

    def create_status_panel(self, parent):
        """创建右侧状态面板"""
        # 设备状态卡片
        self.create_device_status_card(parent)

        # 测试进度卡片
        self.create_progress_card(parent)

        # 日志面板
        self.create_log_panel(parent)

    def create_device_status_card(self, parent):
        """创建设备状态卡片"""
        card = self.create_card(parent, "📱 设备状态")

        # 设备列表显示区域
        list_frame = tk.Frame(card, bg=UIColors.WHITE)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 5))

        # 设备列表标题
        ttk.Label(list_frame, text="连接的设备:", font=UIFonts.SUBTITLE).pack(anchor=tk.W)

        # 设备列表文本框
        self.devices_text = scrolledtext.ScrolledText(
            list_frame,
            height=8,
            font=('Consolas', 10),
            bg=UIColors.BG_DARK,
            relief='flat'
        )
        self.devices_text.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        # 设备状态指示器
        status_frame = tk.Frame(card, bg=UIColors.WHITE)
        status_frame.pack(fill=tk.X, pady=(10, 5))

        self.device_status_label = tk.Label(
            status_frame,
            text="● 状态未知",
            font=UIFonts.BODY,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE
        )
        self.device_status_label.pack(anchor=tk.W)

        # 应用信息（包名/版本）
        self._app_info_label = tk.Label(
            status_frame,
            text="应用：未选择",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE
        )
        self._app_info_label.pack(anchor=tk.W, pady=(4, 0))

        # 初始刷新设备列表
        self.refresh_devices()

    def create_progress_card(self, parent):
        """创建测试进度卡片"""
        card = self.create_card(parent, "📊 测试进度")

        # 进度信息
        self.progress_info_label = tk.Label(
            card,
            text="当前状态：未开始测试",
            font=UIFonts.BODY,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE
        )
        self.progress_info_label.pack(anchor=tk.W, pady=(10, 5))

        # 进度条
        self.progress_bar = ttk.Progressbar(
            card,
            orient="horizontal",
            mode="indeterminate",
            style="TProgressbar"
        )
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))

        # 进度详情
        self.progress_detail_label = tk.Label(
            card,
            text="",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            justify=tk.LEFT
        )
        self.progress_detail_label.pack(anchor=tk.W, pady=(0, 10))

    def create_log_panel(self, parent):
        """创建日志面板"""
        card = self.create_card(parent, "📝 实时日志")

        # 日志文本框
        self.log_text = scrolledtext.ScrolledText(
            card,
            height=12,
            font=('Consolas', 10),
            bg=UIColors.BG_DARK,
            relief='flat'
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(10, 5))

        # 日志控制按钮
        log_buttons_frame = tk.Frame(card, bg=UIColors.WHITE)
        log_buttons_frame.pack(fill=tk.X, pady=(0, 10))

        self.create_action_button(
            log_buttons_frame,
            text="💾 保存日志",
            command=self.save_logs,
            variant="secondary",
            side=tk.RIGHT,
            padx=(5, 0)
        )

        self.create_action_button(
            log_buttons_frame,
            text="🗑️ 清空",
            command=self.clear_logs,
            variant="secondary",
            side=tk.RIGHT
        )

    def create_card(self, parent, title):
        """创建卡片式容器"""
        # 卡片框架
        card = tk.Frame(
            parent,
            bg=UIColors.WHITE,
            relief='raised',
            bd=1
        )
        card.pack(fill=tk.X, pady=(0, 15))

        # 卡片标题
        title_label = tk.Label(
            card,
            text=title,
            font=UIFonts.SUBTITLE,
            fg=UIColors.TEXT_PRIMARY,
            bg=UIColors.WHITE
        )
        title_label.pack(anchor=tk.W, padx=UIMetrics.CARD_PADDING, pady=(UIMetrics.CARD_PADDING, 5))

        # 分割线
        separator = tk.Frame(card, height=1, bg=UIColors.BORDER)
        separator.pack(fill=tk.X, padx=UIMetrics.CARD_PADDING)

        # 内容容器
        content = tk.Frame(card, bg=UIColors.WHITE)
        content.pack(fill=tk.BOTH, expand=True, padx=UIMetrics.CARD_PADDING, pady=UIMetrics.CARD_PADDING)

        return content

    def create_card_grid(self, parent, title, row, column, **grid_kwargs):
        """
        创建可用于 grid 布局的卡片容器（解决 create_card 内部 pack 与 grid 混用导致内容不显示的问题）

        Returns:
            content_frame: 用于放置内容的Frame
        """
        card_outer = tk.Frame(
            parent,
            bg=UIColors.WHITE,
            relief='raised',
            bd=1
        )
        card_outer.grid(row=row, column=column, **grid_kwargs)

        title_label = tk.Label(
            card_outer,
            text=title,
            font=UIFonts.SUBTITLE,
            fg=UIColors.TEXT_PRIMARY,
            bg=UIColors.WHITE
        )
        title_label.pack(anchor=tk.W, padx=UIMetrics.CARD_PADDING, pady=(UIMetrics.CARD_PADDING, 5))

        separator = tk.Frame(card_outer, height=1, bg=UIColors.BORDER)
        separator.pack(fill=tk.X, padx=UIMetrics.CARD_PADDING)

        content = tk.Frame(card_outer, bg=UIColors.WHITE)
        content.pack(fill=tk.BOTH, expand=True, padx=UIMetrics.CARD_PADDING, pady=UIMetrics.CARD_PADDING)

        return content

    # ===== 统一按钮工厂 & 状态日志封装 =====
    def create_action_button(self, parent, text, command, variant="primary", **pack_kwargs):
        """
        创建统一风格的操作按钮
        variant: primary/success/error/warning/secondary/info
        """
        color_map = {
            "primary": UIColors.PRIMARY,
            "success": UIColors.SUCCESS,
            "error": UIColors.ERROR,
            "warning": UIColors.WARNING,
            "secondary": UIColors.TEXT_SECONDARY,
            "info": UIColors.INFO,
        }
        bg = color_map.get(variant, UIColors.PRIMARY)
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=UIColors.WHITE,
            font=UIFonts.BUTTON,
            relief='flat',
            cursor='hand2'
        )
        if pack_kwargs:
            btn.pack(**pack_kwargs)
        return btn

    def log_info_ui(self, message: str):
        """同时写入日志与状态栏的信息级别输出"""
        logging.info(message)
        self.update_status(message)

    def log_warning_ui(self, message: str):
        logging.warning(message)
        self.update_status(message)

    def log_error_ui(self, message: str):
        logging.error(message)
        self.update_status(message)

    def create_status_bar(self, parent):
        """创建状态栏"""
        self.status_bar = tk.Label(
            parent,
            text="✓ 系统就绪",
            font=UIFonts.CAPTION,
            fg=UIColors.SUCCESS,
            bg=UIColors.BG_LIGHT,
            anchor=tk.W
        )
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

    def on_theme_change(self, _event=None):
        """主题选择变化事件：选择即应用，并自动保存到配置文件"""
        # 从显示用中文标签映射回英文主题ID
        label = self.theme_display_var.get().strip()
        # 先按 value 精确匹配
        key = None
        for k, v in TTK_THEME_LABELS.items():
            if v == label:
                key = k
                break
        # 回退：如果用户 somehow 选择了英文ID
        if key is None and label in TTKBOOTSTRAP_THEMES:
            key = label
        if not key:
            return
        self.theme_var.set(key)
        self.apply_selected_theme()
        # 由统一的自动保存机制落盘（带防抖）
        self._schedule_autosave()

    def apply_selected_theme(self):
        """应用当前选择的ttkbootstrap主题"""
        theme = self.theme_var.get().strip()
        if not HAS_TTKBOOTSTRAP:
            # 未安装ttkbootstrap：静默回退（不展示冗余状态控件）
            self.update_status("未安装 ttkbootstrap，主题不可用")
            return

        try:
            # ttkbootstrap 主题切换
            if hasattr(self, "_ttk_style") and self._ttk_style is not None:
                self._ttk_style.theme_use(theme)
            else:
                # fallback
                ttkb.Style().theme_use(theme)

            self.update_status(f"🎨 已切换主题：{theme}")
        except Exception as e:
            self.update_status(f"主题切换失败: {str(e)}")

    def save_theme_to_config(self):
        """仅保存主题到测试配置文件（不覆盖其它配置项）"""
        path = self._get_test_ui_config_path()
        try:
            cfg = read_json(path, default={}) or {}
            if not isinstance(cfg, dict):
                cfg = {}
            cfg["theme"] = self.theme_var.get().strip()
            write_json(path, cfg, indent=2)
        except Exception as e:
            logging.warning(f"保存主题配置失败: {e}")

    def show_reports_window(self):
        """显示报告查看窗口"""
        # 创建新窗口
        reports_window = tk.Toplevel(self.root)
        reports_window.title("测试报告查看器")
        reports_window.geometry("800x600")
        reports_window.configure(bg=UIColors.BG_LIGHT)

        # 报告列表
        list_frame = tk.Frame(reports_window, bg=UIColors.WHITE, relief='raised', bd=1)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # 报告标题
        title_label = tk.Label(
            list_frame,
            text="📄 可用测试报告",
            font=UIFonts.SUBTITLE,
            fg=UIColors.TEXT_PRIMARY,
            bg=UIColors.WHITE
        )
        title_label.pack(anchor=tk.W, padx=UIMetrics.CARD_PADDING, pady=(UIMetrics.CARD_PADDING, 5))

        # 分割线
        separator = tk.Frame(list_frame, height=1, bg=UIColors.BORDER)
        separator.pack(fill=tk.X, padx=UIMetrics.CARD_PADDING)

        # 报告列表框
        self.reports_listbox = tk.Listbox(
            list_frame,
            font=UIFonts.BODY,
            bg=UIColors.BG_LIGHT,
            relief='flat',
            selectbackground=UIColors.PRIMARY,
            selectforeground=UIColors.WHITE
        )
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.reports_listbox.yview)
        self.reports_listbox.config(yscrollcommand=scrollbar.set)

        self.reports_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=UIMetrics.CARD_PADDING, pady=UIMetrics.CARD_PADDING)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=UIMetrics.CARD_PADDING)

        # 按钮区域
        buttons_frame = tk.Frame(list_frame, bg=UIColors.WHITE)
        buttons_frame.pack(fill=tk.X, padx=UIMetrics.CARD_PADDING, pady=(0, UIMetrics.CARD_PADDING))

        self.create_action_button(
            buttons_frame,
            text="📖 打开报告",
            command=self.open_selected_report,
            variant="primary",
            side=tk.LEFT,
            padx=(0, 10)
        )

        self.create_action_button(
            buttons_frame,
            text="🔄 刷新列表",
            command=self.refresh_reports,
            variant="success",
            side=tk.LEFT
        )

        # 初始刷新报告列表
        self.refresh_reports()

    def on_version_selected(self, event):
        """版本选择事件处理"""
        version = self.version_var.get()
        if version in self.project_config:
            config = self.project_config[version]
            # 检查是否有模块配置，如果有则自动设置
            if 'modular_config' in config:
                modular_config = config['modular_config']
                enabled_modules = modular_config.get('enabled_modules', [])
                self.update_module_selection(enabled_modules)
            self.log_info_ui(f"已选择项目版本: {version}")

    def on_test_mode_changed(self, *args):
        """测试模式变化事件处理"""
        mode = self.test_mode_var.get()
        modules_frame = getattr(self, "modules_frame", None)
        # modules_frame 可能来自已关闭的配置窗口（widget 已销毁），需要防护
        if modules_frame is not None:
            try:
                if not modules_frame.winfo_exists():
                    modules_frame = None
                    self.modules_frame = None
            except Exception:
                modules_frame = None
                self.modules_frame = None
        if mode == "comprehensive":
            # 完整测试模式：启用所有主要模块
            self.module_vars['system_robustness'].set(True)
            self.module_vars['exception_recovery'].set(True)
            self.module_vars['performance_all'].set(True)
            self.module_vars['performance_response'].set(False)
            self.module_vars['performance_resource'].set(False)
            # Frame不支持state参数，需要逐个禁用子组件
            if modules_frame:
                for child in modules_frame.winfo_children():
                    try:
                        child.config(state='disabled')
                    except:
                        pass
        else:
            # 模块化测试模式：允许用户选择
            # Frame不支持state参数，需要逐个启用子组件
            if modules_frame:
                for child in modules_frame.winfo_children():
                    try:
                        child.config(state='normal')
                    except:
                        pass

    def update_module_selection(self, enabled_modules):
        """根据配置更新模块选择状态"""
        # 重置所有模块
        for var in self.module_vars.values():
            var.set(False)

        # 根据配置启用相应模块
        for module in enabled_modules:
            if module in self.module_vars:
                self.module_vars[module].set(True)

    def browse_apk(self):
        """浏览APK文件"""
        filename = filedialog.askopenfilename(
            title="选择APK文件",
            filetypes=[("APK files", "*.apk"), ("All files", "*.*")]
        )
        if filename:
            self.apk_path_var.set(filename)

    def browse_adb(self):
        """选择 adb 可执行文件（主要解决 Windows PATH 未配置的问题）"""
        filename = filedialog.askopenfilename(
            title="选择 adb 可执行文件（adb.exe）",
            filetypes=[("adb", "adb.exe"), ("Executable", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.adb_path_var.set(filename)
            # 选择后立即刷新一次
            self.refresh_devices()
            # ADB可用后，已安装应用扫描也可能成功
            self.refresh_installed_apps()

    def _get_adb_cmd(self):
        """
        获取可用的 adb 命令（优先使用用户配置的 adb_path，其次尝试 PATH 与常见SDK路径）
        Returns:
            list[str]: 用于 subprocess.run 的命令前缀，比如 ["adb"] 或 ["C:\\...\\adb.exe"]
        """
        # 1) 用户显式指定
        p = (self.adb_path_var.get() or "").strip()
        if p:
            if os.path.exists(p):
                return [p]
            # 如果填写了 "adb" 这种，也允许走 which
            if shutil.which(p):
                return [p]

        # 1.5) 项目内置 adb（与 timeout_command 约定：tools/adb/adb.exe）
        try:
            project_root = os.path.dirname(os.path.abspath(__file__))
            cand = os.path.join(project_root, "tools", "adb", "adb.exe")
            if os.path.exists(cand):
                return [cand]
        except Exception:
            pass

        # 2) PATH
        w = shutil.which("adb")
        if w:
            return ["adb"]

        # 3) 常见SDK路径（环境变量）
        for env_key in ("ANDROID_HOME", "ANDROID_SDK_ROOT", "ANDROID_SDK_HOME"):
            root = os.environ.get(env_key)
            if root:
                cand = os.path.join(root, "platform-tools", "adb.exe")
                if os.path.exists(cand):
                    return [cand]

        # 4) 兜底：常见默认安装位置（Android Studio SDK）
        localappdata = os.environ.get("LOCALAPPDATA", "")
        userprofile = os.environ.get("USERPROFILE", "")
        candidates = [
            os.path.join(localappdata, "Android", "Sdk", "platform-tools", "adb.exe"),
            os.path.join(userprofile, "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
        ]
        for cand in candidates:
            if cand and os.path.exists(cand):
                return [cand]

        return []

    def _ensure_adb_env(self):
        """将 ADB 路径写入环境变量，供 utils/timeout_command 统一替换 `adb ...` 使用"""
        p = (self.adb_path_var.get() or "").strip()
        if p and os.path.exists(p):
            os.environ["ADB_PATH"] = p

    def _on_app_source_changed(self):
        """切换测试应用来源：控制包名/APK控件的启用状态"""
        mode = self.app_source_var.get()
        # 包名下拉仅在已安装模式启用
        try:
            if self.package_combo and self.package_combo.winfo_exists():
                self.package_combo.configure(state="readonly" if mode == "installed" else "disabled")
        except Exception:
            pass
        self._update_app_info_label()

    def refresh_installed_apps(self):
        """扫描设备上已安装应用包名（默认扫描第三方 -3），填充到包名下拉"""
        self._ensure_adb_env()
        # NOTE: validate_selected_device 依赖 self._adb_devices 缓存；用户可能未点“刷新设备列表”就直接点“扫描”
        # 这里做一次兜底刷新，避免“扫描功能看起来失效”
        sn = (self.device_sn_var.get() or "").strip()
        ok, msg = self.validate_selected_device(sn)
        if not ok:
            try:
                # 避免递归触发 refresh_devices -> refresh_installed_apps
                if getattr(self, "_refreshing_installed_apps", False):
                    raise RuntimeError(msg)
                self._refreshing_installed_apps = True
                self.refresh_devices()
            except Exception:
                pass
            finally:
                try:
                    self._refreshing_installed_apps = False
                except Exception:
                    pass
            ok, msg = self.validate_selected_device(sn)
            if not ok:
                self._installed_packages_cache = []
                self._update_app_info_label(error=msg)
                return

        adb_cmd = self._get_adb_cmd()
        if not adb_cmd:
            self._installed_packages_cache = []
            self._update_app_info_label(error="未找到 adb（请先配置ADB路径）")
            return

        try:
            # 先扫第三方应用（-3），若为空再回退扫描全部（兼容部分设备/ROM 返回异常情况）
            def _run_pm_list(extra_args):
                return subprocess.run(
                    [*adb_cmd, "-s", sn, "shell", "pm", "list", "packages", *extra_args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=25
                )

            result = _run_pm_list(["-3"])
            # 如果adb命令失败，给出更明确提示（stderr里通常包含 unauthorized/offline/no devices 等）
            if getattr(result, "returncode", 0) != 0:
                err = (result.stderr or "").strip() or f"adb返回码: {result.returncode}"
                self._installed_packages_cache = []
                self._update_app_info_label(error=f"扫描失败：{err}")
                return
            pkgs = []
            for ln in (result.stdout or "").splitlines():
                ln = ln.strip()
                if ln.startswith("package:"):
                    pkgs.append(ln.split("package:", 1)[1].strip())
            # 如果第三方列表为空，回退扫描全部包名（更符合“扫描已安装app”的直觉）
            if not pkgs:
                result2 = _run_pm_list([])
                if getattr(result2, "returncode", 0) == 0:
                    for ln in (result2.stdout or "").splitlines():
                        ln = ln.strip()
                        if ln.startswith("package:"):
                            pkgs.append(ln.split("package:", 1)[1].strip())
            pkgs = sorted(set([p for p in pkgs if p]))
            self._installed_packages_cache = pkgs
            if self.package_combo and self.package_combo.winfo_exists():
                self.package_combo["values"] = pkgs
            self._update_app_info_label()
        except Exception as e:
            self._installed_packages_cache = []
            self._update_app_info_label(error=str(e))

    def _on_package_selected(self, _event=None):
        self._update_app_info_label()

    def _get_installed_app_basic_info(self, sn: str, package_name: str):
        """获取已安装应用基础信息（存在性 + versionName）"""
        self._ensure_adb_env()
        adb_cmd = self._get_adb_cmd()
        if not adb_cmd:
            return {}
        pkg = (package_name or "").strip()
        if not pkg:
            return {}
        try:
            r = subprocess.run([*adb_cmd, "-s", sn, "shell", "pm", "path", pkg], capture_output=True, text=True, timeout=10)
            if "package:" not in (r.stdout or ""):
                return {"missing": True}
            r2 = subprocess.run([*adb_cmd, "-s", sn, "shell", "dumpsys", "package", pkg], capture_output=True, text=True, timeout=10)
            info = {"missing": False}
            if r2.stdout:
                import re as _re
                m = _re.search(r"versionName=([^\s]+)", r2.stdout)
                if m:
                    info["versionName"] = m.group(1).strip()
            return info
        except Exception:
            return {}

    def _update_app_info_label(self, error: str = ""):
        """右侧设备状态卡片中显示应用信息（包名/版本）"""
        if not self._app_info_label:
            return
        try:
            if not self._app_info_label.winfo_exists():
                self._app_info_label = None
                return
        except Exception:
            self._app_info_label = None
            return

        if error:
            self._app_info_label.config(text=f"应用：{error}", fg=UIColors.WARNING)
            return

        mode = self.app_source_var.get()
        if mode == "installed":
            sn = (self.device_sn_var.get() or "").strip()
            pkg = (self.package_name_var.get() or "").strip()
            if not pkg:
                self._app_info_label.config(text="应用：已安装模式（未选择包名）", fg=UIColors.TEXT_SECONDARY)
                return
            info = self._get_installed_app_basic_info(sn, pkg)
            if info.get("missing"):
                self._app_info_label.config(text=f"应用：{pkg}（设备未安装）", fg=UIColors.ERROR)
                return
            ver = info.get("versionName")
            if ver:
                self._app_info_label.config(text=f"应用：{pkg} | 版本：{ver}", fg=UIColors.SUCCESS)
            else:
                self._app_info_label.config(text=f"应用：{pkg}", fg=UIColors.SUCCESS)
        else:
            apk = (self.apk_path_var.get() or "").strip()
            if apk:
                self._app_info_label.config(text=f"应用：APK安装（{os.path.basename(apk)}）", fg=UIColors.TEXT_SECONDARY)
            else:
                self._app_info_label.config(text="应用：APK安装（未选择APK）", fg=UIColors.TEXT_SECONDARY)

    def refresh_devices(self):
        """刷新设备列表（手动按钮/自动轮询都会调用）"""
        try:
            adb_cmd = self._get_adb_cmd()
            if not adb_cmd:
                raise FileNotFoundError("未找到 adb（请在“ADB路径”选择 adb.exe，或将 adb 加入 PATH）")
            result = subprocess.run([*adb_cmd, 'devices', '-l'], capture_output=True, text=True, timeout=10)
            devices, pretty_lines = self._parse_adb_devices_output(result.stdout)
            self._adb_devices = devices

            # 右侧“设备状态”卡片：格式化展示（清晰标识连接状态）
            if hasattr(self, "devices_text") and self.devices_text:
                self.devices_text.delete(1.0, tk.END)
                if pretty_lines:
                    self.devices_text.insert(tk.END, "\n".join(pretty_lines) + "\n")
                else:
                    self.devices_text.insert(tk.END, "未检测到设备。请确认已安装ADB，并使用USB/网络连接设备。\n")

            # 统计已连接数量
            connected = [sn for sn, info in devices.items() if info.get("state") == "device"]
            offline = [sn for sn, info in devices.items() if info.get("state") == "offline"]
            unauthorized = [sn for sn, info in devices.items() if info.get("state") == "unauthorized"]

            # 更新状态指示器（右侧卡片）
            if hasattr(self, "device_status_label") and self.device_status_label:
                if connected:
                    extra = []
                    if offline:
                        extra.append(f"离线{len(offline)}")
                    if unauthorized:
                        extra.append(f"未授权{len(unauthorized)}")
                    suffix = f"（{', '.join(extra)}）" if extra else ""
                    self.device_status_label.config(
                        text=f"● 已连接 {len(connected)} 个设备{suffix}",
                        fg=UIColors.SUCCESS
                    )
                else:
                    # 没有可用device时，按是否存在“异常状态设备”给出更具体提示
                    if offline or unauthorized:
                        msg = "● 设备不可用："
                        parts = []
                        if offline:
                            parts.append(f"离线{len(offline)}")
                        if unauthorized:
                            parts.append(f"未授权{len(unauthorized)}（请在设备上允许USB调试）")
                        msg += " / ".join(parts)
                        self.device_status_label.config(text=msg, fg=UIColors.WARNING)
                    else:
                        self.device_status_label.config(text="● 未检测到设备连接", fg=UIColors.ERROR)

            # 更新左侧项目配置区下拉框候选
            if self.device_combo and self.device_combo.winfo_exists():
                values = list(devices.keys())
                self.device_combo["values"] = values

                # 若当前选择为空/默认值且检测到设备，则自动选中第一个“已连接”设备
                current = (self.device_sn_var.get() or "").strip()
                if values:
                    if (not current) or (current == "emulator-5554" and current not in devices):
                        preferred = connected[0] if connected else values[0]
                        self.device_sn_var.set(preferred)
                        self._on_device_selected()
                else:
                    # 没有设备时，不强制清空用户输入，但提示状态
                    pass

            # 左侧项目配置区轻量状态提示
            self._update_device_status_in_config()

            # 联动刷新应用信息（已安装模式时顺便扫描包名）
            if self.app_source_var.get() == "installed":
                self.refresh_installed_apps()
            else:
                self._update_app_info_label()

            self.update_status("✅ 设备列表已刷新")
        except Exception as e:
            try:
                if hasattr(self, "devices_text") and self.devices_text:
                    self.devices_text.delete(1.0, tk.END)
                    self.devices_text.insert(tk.END, f"获取设备列表失败: {str(e)}\n")
            except Exception:
                pass
            try:
                if hasattr(self, "device_status_label") and self.device_status_label:
                    self.device_status_label.config(text="● 设备检测失败", fg=UIColors.ERROR)
            except Exception:
                pass
            self._update_device_status_in_config(error=str(e))
            self._update_app_info_label(error=str(e))
            self.update_status("❌ 获取设备列表失败")

    def _parse_adb_devices_output(self, output: str):
        """
        解析 `adb devices -l` 输出
        Returns:
            devices: dict(sn -> {"state": state, "raw": raw_line})
            pretty_lines: list[str] 供 UI 展示（带中文状态）
        """
        devices = {}
        pretty_lines = []
        if not isinstance(output, str):
            return devices, pretty_lines

        lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
        # 跳过第一行 "List of devices attached"
        for ln in lines:
            if ln.lower().startswith("list of devices"):
                continue
            # 常见格式：
            # emulator-5554    device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 device:...
            parts = ln.split()
            if len(parts) < 2:
                continue
            sn = parts[0].strip()
            state = parts[1].strip()
            devices[sn] = {"state": state, "raw": ln}

        # 美化输出：明确标识连接状态
        state_map = {
            "device": ("已连接", UIColors.SUCCESS),
            "offline": ("离线", UIColors.WARNING),
            "unauthorized": ("未授权", UIColors.WARNING),
        }
        # 注意：这里不直接用颜色（因为 scrolledtext 是纯文本），用标签文字表达
        for sn, info in devices.items():
            st = info.get("state", "unknown")
            zh = state_map.get(st, (st, UIColors.TEXT_SECONDARY))[0]
            pretty_lines.append(f"{sn:<24} [{zh}]")

        return devices, pretty_lines

    def _update_device_status_in_config(self, error: str = ""):
        """更新项目配置区里的设备状态提示（连接数量/当前选择状态）"""
        label = self._device_status_in_config
        if not label:
            return
        try:
            if not label.winfo_exists():
                self._device_status_in_config = None
                return
        except Exception:
            self._device_status_in_config = None
            return

        if error:
            label.config(text=f"● 设备检测失败：{error}", fg=UIColors.ERROR)
            return

        devices = self._adb_devices or {}
        connected = [sn for sn, info in devices.items() if info.get("state") == "device"]
        current = (self.device_sn_var.get() or "").strip()
        current_state = devices.get(current, {}).get("state")

        if not devices:
            label.config(text="● 设备：未检测到（请连接设备并点击刷新）", fg=UIColors.TEXT_SECONDARY)
            return

        if current and current in devices:
            if current_state == "device":
                label.config(text=f"● 已连接 {len(connected)} 台 | 当前：{current}（可用）", fg=UIColors.SUCCESS)
            else:
                label.config(text=f"● 已检测 {len(devices)} 台 | 当前：{current}（{current_state}）", fg=UIColors.WARNING)
        else:
            if connected:
                label.config(text=f"● 已连接 {len(connected)} 台 | 请选择目标设备", fg=UIColors.SUCCESS)
            else:
                label.config(text=f"● 已检测 {len(devices)} 台，但无可用设备（device）", fg=UIColors.WARNING)

    def _on_device_selected(self, _event=None):
        """用户从下拉框选择设备：同步并即时校验状态"""
        self._update_device_status_in_config()
        # 若稳定性测试的多设备列表为空或仍是默认值，则同步为当前设备
        try:
            sn = (self.device_sn_var.get() or "").strip()
            if not sn:
                return
            current_multi = (self.multi_devices_var.get() or "").strip()
            if (not current_multi) or (current_multi == "emulator-5554"):
                self.multi_devices_var.set(sn)
        except Exception:
            pass

    def _start_device_polling(self):
        """启动设备自动轮询：当连接状态变化时及时刷新界面"""
        # 避免重复启动
        try:
            if self._device_poll_job is not None:
                return
        except Exception:
            pass

        def _poll():
            try:
                adb_cmd = self._get_adb_cmd()
                if not adb_cmd:
                    return
                result = subprocess.run([*adb_cmd, 'devices', '-l'], capture_output=True, text=True, timeout=10)
                devices, _pretty = self._parse_adb_devices_output(result.stdout)
                # 用一个稳定key判断是否变化（避免每次都重刷UI导致闪烁）
                key = "|".join([f"{sn}:{devices[sn].get('state')}" for sn in sorted(devices.keys())])
                if key != self._last_adb_snapshot_key:
                    self._last_adb_snapshot_key = key
                    # 变化时刷新完整UI（包含列表、下拉框、状态指示器）
                    self.refresh_devices()
            except Exception:
                # 自动轮询失败不弹窗，避免打扰；状态留给手动刷新处理
                pass
            finally:
                try:
                    self._device_poll_job = self.root.after(2000, _poll)
                except Exception:
                    self._device_poll_job = None

        # 先立即跑一次
        _poll()

    def validate_selected_device(self, sn: str):
        """验证所选设备是否处于可连接状态（state==device）"""
        sn = (sn or "").strip()
        if not sn:
            return False, "未选择设备序列号"
        devices = self._adb_devices or {}
        if sn not in devices:
            return False, f"设备 {sn} 未在ADB设备列表中（请刷新设备列表）"
        state = devices.get(sn, {}).get("state")
        if state != "device":
            if state == "unauthorized":
                return False, f"设备 {sn} 未授权（请在设备上允许USB调试授权）"
            if state == "offline":
                return False, f"设备 {sn} 离线（请重新插拔/重连）"
            return False, f"设备 {sn} 不可用（状态：{state}）"
        return True, ""

    def refresh_reports(self):
        """刷新报告列表"""
        self.reports_listbox.delete(0, tk.END)

        reports_dir = "reports"
        if os.path.exists(reports_dir):
            for file in os.listdir(reports_dir):
                if file.endswith(('.html', '.json')):
                    self.reports_listbox.insert(tk.END, file)

        self.update_status("报告列表已刷新")

    def open_selected_report(self):
        """打开选中的报告"""
        selection = self.reports_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个报告文件")
            return

        report_file = self.reports_listbox.get(selection[0])
        report_path = os.path.join("reports", report_file)

        if report_file.endswith('.html'):
            # 打开HTML报告
            try:
                import webbrowser
                webbrowser.open(f"file://{os.path.abspath(report_path)}")
                self.update_status(f"已打开报告: {report_file}")
            except Exception as e:
                messagebox.showerror("错误", f"无法打开报告: {str(e)}")
        elif report_file.endswith('.json'):
            # 显示JSON报告内容
            try:
                with open(report_path, 'r', encoding='utf-8') as f:
                    content = json.dumps(json.load(f), indent=2, ensure_ascii=False)
                self.report_preview.delete(1.0, tk.END)
                self.report_preview.insert(tk.END, content)
                self.update_status(f"已加载JSON报告: {report_file}")
            except Exception as e:
                messagebox.showerror("错误", f"无法读取报告: {str(e)}")

    def delete_selected_report(self):
        """删除选中的报告"""
        selection = self.reports_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个报告文件")
            return

        report_file = self.reports_listbox.get(selection[0])
        report_path = os.path.join("reports", report_file)

        if messagebox.askyesno("确认删除", f"确定要删除报告文件 {report_file} 吗？"):
            try:
                os.remove(report_path)
                self.refresh_reports()
                self.update_status(f"已删除报告: {report_file}")
            except Exception as e:
                messagebox.showerror("错误", f"删除报告失败: {str(e)}")

    def start_traditional_test(self):
        """开始传统Monkey测试"""
        if self.is_testing:
            messagebox.showwarning("⚠️ 警告", "测试正在进行中，请先停止当前测试")
            return

        # 验证必要参数
        if not self.version_var.get():
            messagebox.showerror("❌ 错误", "请选择项目版本")
            return

        if not self.device_sn_var.get():
            messagebox.showerror("❌ 错误", "请输入设备序列号")
            return
        ok, msg = self.validate_selected_device(self.device_sn_var.get())
        if not ok:
            messagebox.showerror("❌ 设备不可用", msg)
            return
        # 确保底层 adb 命令可用（PATH未配置时）
        self._ensure_adb_env()

        # 更新UI状态（按钮可能尚未创建）
        if self.start_test_btn:
            self.start_test_btn.config(state="disabled", bg=UIColors.TEXT_SECONDARY)
        if self.stop_test_btn:
            self.stop_test_btn.config(state="normal")
        if self.progress_bar:
            self.progress_bar.start()
        if self.progress_info_label:
            self.progress_info_label.config(text="当前状态：正在运行传统Monkey测试", fg=UIColors.PRIMARY)

        # 启动测试线程
        self.is_testing = True
        self.test_thread = threading.Thread(target=self.run_traditional_test)
        self.test_thread.daemon = True
        self.test_thread.start()

        self.update_status("🐒 开始传统Monkey测试...")

    def start_stability_test(self):
        """开始稳定性测试"""
        if self.is_testing:
            messagebox.showwarning("⚠️ 警告", "测试正在进行中，请先停止当前测试")
            return

        if not self.device_sn_var.get():
            messagebox.showerror("❌ 错误", "请输入设备序列号")
            return
        # 设备选择验证：至少确保当前设备可连接（对多设备场景也给出提示）
        ok, msg = self.validate_selected_device(self.device_sn_var.get())
        if not ok:
            messagebox.showerror("❌ 设备不可用", msg)
            return
        self._ensure_adb_env()

        # 已安装应用模式：必须选择包名并校验存在
        if self.app_source_var.get() == "installed":
            pkg = (self.package_name_var.get() or "").strip()
            if not pkg:
                messagebox.showerror("❌ 错误", "请选择设备上已安装的应用包名（点击“扫描”）")
                return
            info = self._get_installed_app_basic_info((self.device_sn_var.get() or "").strip(), pkg)
            if info.get("missing"):
                messagebox.showerror("❌ 包不存在", f"设备上未安装包名：{pkg}")
                return

        # 检查模块选择
        test_mode = self.test_mode_var.get()
        if test_mode == "modular":
            enabled_modules = [module for module, var in self.module_vars.items() if var.get()]
            if not enabled_modules:
                messagebox.showerror("❌ 错误", "请至少选择一个测试模块")
                return
            logging.info(f"模块化测试模式，启用的模块: {enabled_modules}")
            self.progress_info_label.config(text="当前状态：正在运行模块化稳定性测试", fg=UIColors.PRIMARY)
        else:
            logging.info("完整测试套件模式")
            if self.progress_info_label:
                self.progress_info_label.config(text="当前状态：正在运行完整稳定性测试", fg=UIColors.PRIMARY)

        # 若启用 Mock Server，则在测试开始前确保本地Mock服务就绪（最小侵入集成）
        if not self.no_mock_server_var.get():
            self.ensure_mock_server_running()

        # 更新UI状态
        if self.start_test_btn:
            self.start_test_btn.config(state="disabled", bg=UIColors.TEXT_SECONDARY)
        if self.stop_test_btn:
            self.stop_test_btn.config(state="normal")
        if self.progress_bar:
            self.progress_bar.start()

        # 启动测试线程
        self.is_testing = True
        self.test_thread = threading.Thread(target=self.run_stability_test)
        self.test_thread.daemon = True
        self.test_thread.start()

        self.update_status("🚀 开始稳定性测试...")

    def run_traditional_test(self):
        """运行传统Monkey测试"""
        try:
            # 用子进程执行 main.py（可通过 stop_test 强制终止）
            prj_ver = (self.version_var.get() or "").strip()
            sn = (self.device_sn_var.get() or "").strip()
            apk_path = (self.apk_path_var.get() or "").strip()
            throttle = str(int(self.throttle_var.get()))
            count = str(int(self.count_var.get()))
            need_uninstall = "true" if bool(self.uninstall_var.get()) else "false"
            # 兼容：某些初始化路径或测试场景下可能尚未创建 email_var，兜底为空字符串
            if hasattr(self, "email_var") and self.email_var is not None:
                rcpt = (self.email_var.get() or "").strip()
            else:
                rcpt = ""

            cmd = [
                sys.executable, "main.py",
                "-v", prj_ver,
                "-s", sn,
                "-i", need_uninstall,
                "-t", throttle,
                "-c", count,
            ]
            if apk_path:
                cmd.extend(["-p", apk_path])
            if rcpt:
                cmd.extend(["-r", rcpt])

            exit_code = self._run_test_subprocess(cmd, title="传统Monkey测试")
            if exit_code != 0 and self.is_testing:
                raise RuntimeError(f"子进程退出码: {exit_code}")

            if self.is_testing:
                self.log_queue.put("传统Monkey测试完成")
                self.update_status("传统Monkey测试完成")

        except Exception as e:
            error_msg = f"传统Monkey测试失败: {str(e)}"
            self.log_queue.put(error_msg)
            self.update_status(error_msg)

        finally:
            # 清理UI状态
            self.root.after(0, self.reset_traditional_ui)

    def run_stability_test(self):
        """运行稳定性测试"""
        try:
            # 构建基础参数（duration 支持分钟/小时，统一换算为“小时”传递给底层）
            raw_duration = (self.duration_var.get() or "").strip()
            try:
                dur_value = float(raw_duration)
            except Exception:
                dur_value = 0.0
            unit_txt = getattr(self, "duration_unit_var", None)
            unit_val = unit_txt.get() if unit_txt is not None else "小时"
            if unit_val.startswith("分"):
                duration_hours = max(dur_value / 60.0, 0.0)
            else:
                duration_hours = max(dur_value, 0.0)

            # 构建基础参数
            params = {
                'mode': 'stability',
                'sn_list': self.multi_devices_var.get().split(),
                'config_path': None,
                'duration': duration_hours,
                'use_mock_server': not self.no_mock_server_var.get(),
                'use_network_proxy': not self.no_network_proxy_var.get(),
                'network_method': self.network_method_var.get(),
                'establish_baseline': self.baseline_establish_var.get(),
                'compare_baseline': self.baseline_compare_var.get(),
                'apk_url': "",
                'apk_path': self.apk_path_var.get(),
                'package_name': (self.package_name_var.get() or "").strip() if self.app_source_var.get() == "installed" else "",
                # GUI 入口：仅运行标记为 stability_smoke 的轻量用例（避免参数化长压用例重复跑多种时长）
                'smoke_only': True,
            }

            # 添加模块化测试参数
            test_mode = self.test_mode_var.get()
            if test_mode == "modular":
                enabled_modules = [module for module, var in self.module_vars.items() if var.get()]
                params['modular_enabled'] = True
                params['enabled_modules'] = enabled_modules
            else:
                params['modular_enabled'] = False
                params['enabled_modules'] = []

            # 初始化日志
            project_log = ProjectLog()
            project_log.set_up()

            # 用子进程执行 pytest（可通过 stop_test 强制终止）
            from main import build_pytest_args
            pytest_args = build_pytest_args(params)
            cmd = [sys.executable, "-m", "pytest", *pytest_args]
            exit_code = self._run_test_subprocess(cmd, title="稳定性测试")
            if exit_code != 0 and self.is_testing:
                raise RuntimeError(f"pytest退出码: {exit_code}")

            if self.is_testing:
                self.log_queue.put("稳定性测试完成")
                self.update_status("稳定性测试完成")

        except Exception as e:
            error_msg = f"稳定性测试失败: {str(e)}"
            self.log_queue.put(error_msg)
            self.update_status(error_msg)

        finally:
            # 清理UI状态
            self.root.after(0, self.reset_stability_ui)

    def stop_test(self):
        """停止测试"""
        if self.is_testing:
            self.is_testing = False
            self.log_queue.put("正在停止测试（尝试终止子进程）...")
            self.update_status("正在停止测试（尝试终止子进程）...")
            if self.stop_test_btn:
                self.stop_test_btn.config(state="disabled")
            self._terminate_running_test_process()

    def _terminate_running_test_process(self):
        """终止当前测试子进程（Windows下杀进程树）"""
        with self._test_process_lock:
            p = self.test_process
        if not p:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True, text=True)
            else:
                try:
                    p.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            with self._test_process_lock:
                self.test_process = None

    def _run_test_subprocess(self, cmd, title: str = "测试"):
        """
        在后台线程中执行子进程，并把stdout/stderr转发到GUI日志；支持 stop_test 通过 taskkill 强制终止。
        Returns:
            int: 进程退出码（被 stop 杀掉时通常为非0）
        """
        # 确保只存在一个测试进程
        self._terminate_running_test_process()

        self.log_queue.put(f"{title}启动: {' '.join([str(x) for x in cmd])}")
        try:
            creationflags = 0
            if sys.platform == "win32":
                creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            env = os.environ.copy()
            # 让子进程尽量输出 UTF-8（避免 pytest/live log 乱码）
            env.setdefault("PYTHONUTF8", "1")
            env.setdefault("PYTHONIOENCODING", "utf-8")
            # Windows 控制台编码也可能影响第三方工具输出
            env.setdefault("LC_ALL", "C.UTF-8")
            p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,
                cwd=os.getcwd(),
                creationflags=creationflags,
                env=env,
            )
            with self._test_process_lock:
                self.test_process = p

            def _decode_line(b: bytes) -> str:
                for enc in ("utf-8", "gbk"):
                    try:
                        return b.decode(enc, errors="replace")
                    except Exception:
                        continue
                try:
                    return b.decode(errors="replace")
                except Exception:
                    return str(b)

            if p.stdout:
                for raw in iter(p.stdout.readline, b""):
                    if not raw:
                        break
                    line = _decode_line(raw).rstrip("\r\n")
                    if line:
                        self.log_queue.put(line)
                    if not self.is_testing:
                        break

            try:
                exit_code = p.wait(timeout=5 if not self.is_testing else None)
            except Exception:
                try:
                    exit_code = p.poll() or -1
                except Exception:
                    exit_code = -1
            return int(exit_code if exit_code is not None else -1)
        finally:
            with self._test_process_lock:
                self.test_process = None

    def reset_traditional_ui(self):
        """重置传统测试UI状态"""
        if self.start_test_btn:
            self.start_test_btn.config(state="normal", bg=UIColors.PRIMARY)
        if self.stop_test_btn:
            self.stop_test_btn.config(state="disabled")
        if self.progress_bar:
            self.progress_bar.stop()
        if self.progress_info_label:
            self.progress_info_label.config(text="当前状态：传统测试已完成", fg=UIColors.SUCCESS)
        self.is_testing = False

    def reset_stability_ui(self):
        """重置稳定性测试UI状态"""
        if self.start_test_btn:
            self.start_test_btn.config(state="normal", bg=UIColors.PRIMARY)
        if self.stop_test_btn:
            self.stop_test_btn.config(state="disabled")
        if self.progress_bar:
            self.progress_bar.stop()
        if self.progress_info_label:
            self.progress_info_label.config(text="当前状态：稳定性测试已完成", fg=UIColors.SUCCESS)
        self.is_testing = False
        # 如果Mock Server是由GUI自动拉起的，测试结束后自动回收（不影响用户手动启用）
        try:
            if self._mock_server_started_by_gui:
                self.stop_mock_server_from_gui()
        except Exception:
            pass

    def clear_logs(self):
        """清空日志"""
        self.log_text.delete(1.0, tk.END)

    def save_logs(self):
        """保存日志"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                self.update_status(f"日志已保存到: {filename}")
            except Exception as e:
                messagebox.showerror("错误", f"保存日志失败: {str(e)}")

    def toggle_auto_scroll(self):
        """切换自动滚动"""
        # 这个功能可以通过复选框实现，这里只是占位
        pass

    def start_log_handler(self):
        """启动日志处理线程"""
        def log_handler():
            while True:
                try:
                    message = self.log_queue.get(timeout=1)
                    self.root.after(0, self.append_log, message)
                except queue.Empty:
                    continue

        thread = threading.Thread(target=log_handler, daemon=True)
        thread.start()

    def append_log(self, message):
        """添加日志到文本框"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, log_line)

        if self.auto_scroll_var.get():
            self.log_text.see(tk.END)

        # 限制日志行数（保持最后1000行）
        lines = self.log_text.get(1.0, tk.END).split('\n')
        if len(lines) > 1000:
            self.log_text.delete(1.0, f"{len(lines) - 1000}.0")

    def update_status(self, message):
        """更新状态栏"""
        # 检查status_bar是否已创建
        if hasattr(self, 'status_bar') and self.status_bar:
            self.status_bar.config(text=message)
        self.log_queue.put(message)

    def on_closing(self):
        """窗口关闭事件处理"""
        if self.is_testing:
            if messagebox.askyesno("确认退出", "测试正在进行中，确定要退出吗？"):
                self.stop_test()
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    """主函数"""
    try:
        # 优先使用ttkbootstrap主题窗口
        if HAS_TTKBOOTSTRAP:
            root = ttkb.Window(themename="flatly")  # 主题可替换：cosmo / flatly / journal / minty等
        else:
            root = tk.Tk()
        app = MonkeyTestGUI(root)
        root.mainloop()
    except UnicodeEncodeError as e:
        error_msg = f"界面编码错误: {str(e)}\n请确保系统支持UTF-8编码"
        print(error_msg)
        messagebox.showerror("编码错误", error_msg)
    except ImportError as e:
        error_msg = f"缺少必要的模块: {str(e)}\n请确保已安装所有依赖包"
        print(error_msg)
        messagebox.showerror("导入错误", error_msg)
    except Exception as e:
        error_msg = f"程序启动失败: {str(e)}"
        print(error_msg)
        try:
            messagebox.showerror("启动错误", error_msg)
        except:
            print("无法显示错误对话框")


if __name__ == "__main__":
    main()