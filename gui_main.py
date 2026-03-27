#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端侧自动化测试工具 - GUI版本
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
from tkinter import ttk, scrolledtext, filedialog, messagebox, simpledialog
import threading
import queue
import sys
import os
import json
from datetime import datetime
import subprocess
import logging
from pathlib import Path
import shutil
import tkinter.font as tkfont

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

# 使用统一的日志配置（避免重复 basicConfig）
from utils.log import setup_logging
setup_logging(level=logging.INFO)

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# UI 设计常量与通用控件从 gui.toolkit 统一引入
from gui.toolkit import UIColors, UIFonts, UIMetrics, UIFONTS, ToolTip
from gui.state import GuiContext

# 导入项目模块
from utils import addition, ProjectLog
from utils.stability_test import StabilityTestFramework, StabilityTestRunner
from utils import Package
from infra.mock_server import create_mock_server, apply_rules
from utils.config_io import read_json, write_json
from core.services.report_service import regenerate_report


class MonkeyTestGUI:
    """端侧自动化测试工具GUI主类"""

    def __init__(self, root):
        self.root = root
        # GUI 顶层上下文：后续子组件可复用
        self.context = GuiContext(root=self.root, log_queue=queue.Queue())
        # Tk 主线程标识（用于线程安全更新 UI）
        try:
            import threading as _threading
            self._ui_thread_id = _threading.get_ident()
        except Exception:
            self._ui_thread_id = None
        self.root.title("端侧自动化测试工具 v1.0.0")
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
        # 包名下拉框：置顶与筛选（conf/test_ui_config.json -> pinned_packages）
        self.pinned_packages = []
        self._installed_packages_all = []  # 扫描到的完整包名（已按置顶排序）
        # 测试配置相关变量（便于弹窗和主界面共享）
        self.test_mode_var = tk.StringVar(value="comprehensive")
        self.module_vars = {
            'monkey_stress': tk.BooleanVar(value=True),
            'exception_recovery': tk.BooleanVar(value=True),
            'performance_response': tk.BooleanVar(value=False),
            'performance_all': tk.BooleanVar(value=True),
            'broadcast_stress': tk.BooleanVar(value=False),
            'tts_stress': tk.BooleanVar(value=False),
        }
        # 稳定性测试时长：底层仍使用 duration_var + duration_unit_var（供 run_stability_test 的转换逻辑复用）
        self.duration_var = tk.StringVar(value="12")  # 数值部分
        self.duration_unit_var = tk.StringVar(value="小时")  # 单位：分钟/小时（仅GUI显示）
        # GUI 展示：预设方案（用户只选方案，不手填数值）
        self.duration_preset_var = tk.StringVar(value="长期压力测试（12小时）")
        self.network_method_var = tk.StringVar(value="root")
        self.baseline_establish_var = tk.BooleanVar(value=False)
        self.baseline_compare_var = tk.BooleanVar(value=False)
        self.no_mock_server_var = tk.BooleanVar(value=False)
        self.no_network_proxy_var = tk.BooleanVar(value=False)
        self.use_fallback_only_var = tk.BooleanVar(value=False)  # 直接使用Fallback事件注入
        # pytest框架已强制启用，无需用户选择
        self.multi_devices_var = tk.StringVar(value="emulator-5554")
        # Mock Server（GUI集成）
        self.mock_host_var = tk.StringVar(value="127.0.0.1")
        self.mock_port_var = tk.StringVar(value="8080")
        self.mock_rules_path_var = tk.StringVar(value=str(Path("conf") / "mock_rules.json"))
        # 性能监控配置
        self.performance_clickable_elements_var = tk.StringVar(value="AI Power,智能体广场,对话收藏")
        # Monkey 遮罩区域（百分比，0-100）
        self.monkey_mask_top_var = tk.StringVar(value="0.0")
        self.monkey_mask_bottom_var = tk.StringVar(value="0.0")
        self.monkey_mask_left_var = tk.StringVar(value="0.0")
        self.monkey_mask_right_var = tk.StringVar(value="0.0")
        # 广播/TTS 压力测试配置
        self.broadcast_hints_var = tk.StringVar(value="介绍一下白居易\n讲个笑话\n今天天气怎么样")
        self.broadcast_hints_file_var = tk.StringVar(value="")
        self.tts_texts_var = tk.StringVar(value="打开设置\n介绍一下北京\n今天天气怎么样")
        self.tts_texts_file_var = tk.StringVar(value="")
        self.tts_end_phrase_var = tk.StringVar(value="")
        self.tts_wake_phrase_var = tk.StringVar(value="")
        self.tts_wake_delay_var = tk.StringVar(value="2")
        # TTS 播报间隔/音量（音量为百分比 0-100）
        self.tts_interval_seconds_var = tk.StringVar(value="30")
        self.tts_volume_percent_var = tk.StringVar(value="100")
        # app.log 差异化采集配置
        self.app_log_enabled_var = tk.BooleanVar(value=True)
        self.app_log_extra_packages_var = tk.StringVar(value="")
        self.app_log_package_process_map_var = tk.StringVar(value="")
        self.app_log_include_process_names_var = tk.StringVar(value="")
        self.app_log_levels_var = tk.StringVar(value="VDIWEF")
        self.app_log_tags_include_var = tk.StringVar(value="")
        self.app_log_tags_exclude_var = tk.StringVar(value="")
        self.app_log_keywords_include_var = tk.StringVar(value="")
        self.app_log_keywords_exclude_var = tk.StringVar(value="")
        self.app_log_output_subdir_var = tk.StringVar(value="")
        self.app_log_max_file_mb_var = tk.StringVar(value="50")
        self.app_log_backup_count_var = tk.StringVar(value="3")
        self.app_log_flush_interval_ms_var = tk.StringVar(value="500")
        self.app_log_batch_lines_var = tk.StringVar(value="50")
        self.app_log_pid_refresh_seconds_var = tk.StringVar(value="2")
        # 响应监控参数（广播/TTS 共用，当前仅 logcat 模式，不再支持 UI 正则；发送后立即开始监控）
        self.response_monitor_max_wait_appear_var = tk.StringVar(value="6")
        self.response_monitor_check_interval_var = tk.StringVar(value="0.1")
        self.response_monitor_max_wait_disappear_var = tk.StringVar(value="300")
        # 连续 ANR/无响应后自动恢复的触发阈值（次数），默认 1 次即触发
        self.response_monitor_anr_recover_threshold_var = tk.StringVar(value="1")
        self._mock_server = None
        self._mock_server_started_by_gui = False
        self._mock_status_label = None
        self._mock_activity_text = None
        # 运行控制按钮占位
        self.start_test_btn = None
        self.stop_test_btn = None
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
        # 报告自动刷新（便于实时报告查看）
        self._report_poll_job = None
        self.device_combo = None
        self._device_status_in_config = None
        self.adb_path_var = tk.StringVar(value="")  # 允许用户显式指定 adb.exe 路径（避免PATH问题）
        # 应用类型：系统应用 / 普通应用（用于安装/卸载等操作；测试仅针对已安装应用）
        self.app_type_var = tk.StringVar(value="normal")  # system / normal
        self.package_name_var = tk.StringVar(value="")
        self.apk_path_var = tk.StringVar(value="")  # 兼容配置保存/加载及传统测试等
        self.version_var = tk.StringVar(value="")
        self.version_display_var = tk.StringVar(value="")  # 测试模块选择下拉框显示 name
        self.package_combo = None
        self._installed_packages_cache = []
        self._app_info_label = None
        # 测试报告：用于 stop 时标记“已停止”的 live 报告路径
        self._current_live_report_path = ""

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

        # 初始化可缩放字体（使用 tk.font.Font 对象，后续可动态调整大小）
        self._font_base_sizes = {
            "TITLE": 14,
            "SUBTITLE": 12,
            "BODY": 11,
            "CAPTION": 9,
            "BUTTON": 10,
            "MONO": 9,
        }
        # 最小字体大小约束（避免高 DPI 小窗口下过小）
        self._font_min_sizes = {
            "TITLE": 12,
            "SUBTITLE": 11,
            "BODY": 10,
            "CAPTION": 8,
            "BUTTON": 10,
            "MONO": 9,
        }
        self._init_font_objects()

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

    def _init_font_objects(self):
        """初始化可缩放字体对象并覆盖 UIFONTS.*"""
        def _font(name, size, weight=None, family="Microsoft YaHei"):
            return tkfont.Font(root=self.root, family=family, size=size, weight=weight or "normal")

        UIFONTS.TITLE = _font("TITLE", self._font_base_sizes["TITLE"], weight="bold")
        UIFONTS.SUBTITLE = _font("SUBTITLE", self._font_base_sizes["SUBTITLE"], weight="bold")
        UIFONTS.BODY = _font("BODY", self._font_base_sizes["BODY"])
        UIFONTS.CAPTION = _font("CAPTION", self._font_base_sizes["CAPTION"])
        UIFONTS.BUTTON = _font("BUTTON", self._font_base_sizes["BUTTON"], weight="bold")
        UIFONTS.MONO = tkfont.Font(root=self.root, family="Consolas", size=self._font_base_sizes["MONO"])

    def _scale_fonts(self, width_hint=None):
        """根据窗口宽度比例缩放字体，避免文字截断"""
        try:
            base_width = 1200
            w = width_hint or self.root.winfo_width()
            if w <= 0:
                return
            scale = w / base_width
            # 缩放范围略收紧，避免大屏时字体过大；小屏仍保持可读性
            scale = max(0.85, min(1.2, scale))
            # 避免频繁更新：仅当显著变化时调整
            if getattr(self, "_last_font_scale", None) and abs(self._last_font_scale - scale) < 0.05:
                return
            self._last_font_scale = scale

            for name, base in self._font_base_sizes.items():
                font_obj = getattr(UIFonts, name, None)
                if isinstance(font_obj, tkfont.Font):
                    new_size = int(round(base * scale))
                    # 应用最小字体约束
                    min_size = self._font_min_sizes.get(name, new_size)
                    new_size = max(new_size, min_size)
                    font_obj.configure(size=new_size)
        except Exception:
            pass

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
        # 先做一次字体缩放，确保初始字号与窗口宽度匹配
        self.root.update_idletasks()
        self._scale_fonts(self.root.winfo_width())

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
        self._scroll_canvas = scroll_canvas

        scroll_canvas.grid(row=0, column=0, sticky="nsew")
        scroll_vbar.grid(row=0, column=1, sticky="ns")

        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        # 让PanedWindow放在可滚动的inner里：左侧受右侧唯一滚动条控制
        scroll_inner = tk.Frame(scroll_canvas, bg=UIColors.BG_LIGHT)
        inner_id = scroll_canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
        self._scroll_inner = scroll_inner
        self._scroll_inner_id = inner_id

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
        self.root.after(150, self._init_panes)
        # 刷新一次滚动区域，避免初始未显示内容
        self.root.after_idle(self._refresh_scroll_region)
        self.root.after(120, self._refresh_scroll_region)

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
            # 更新滚动区域，避免首帧未渲染完全
            self._refresh_scroll_region()
        except Exception:
            pass

    def _refresh_scroll_region(self, *_e):
        """刷新主滚动区域，确保内容初始即显示"""
        try:
            if hasattr(self, "_scroll_canvas") and hasattr(self, "_scroll_inner_id"):
                self._scroll_canvas.update_idletasks()
                self._scroll_canvas.configure(scrollregion=self._scroll_canvas.bbox("all"))
                # 确保内部宽度跟随canvas
                w = self._scroll_canvas.winfo_width()
                if w > 0:
                    self._scroll_canvas.itemconfig(self._scroll_inner_id, width=w)
        except Exception:
            pass

    # 注意：旧的 _create_scrollable_panel 已移除，改为“单主滚动条”方案（左右共同滚动）

    def _on_root_resize(self, event):
        """窗口缩放时，按比例调整左右面板宽度"""
        try:
            # 只在窗口宽度变化时调整
            if event is not None and event.widget is not self.root:
                return
            # 字体等比例缩放
            self._scale_fonts(self.root.winfo_width())
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

        # 测试模块选择（与首页卡片一致：显示 name，内部用 key）
        ttk.Label(config_frame, text="测试模块选择:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        version_names = [self.project_config.get(k, {}).get("name", k) for k in self.available_versions]
        config_tab_version_combo = ttk.Combobox(config_frame, textvariable=self.version_display_var,
                                                values=version_names, state="readonly")
        config_tab_version_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)
        config_tab_version_combo.bind("<<ComboboxSelected>>", self.on_version_selected)
        ToolTip(config_tab_version_combo, "选择测试模块（来自 conf/project.json）。选中后会同步模块说明与自定义模块组合。")
        # 若已从配置加载了 prj_ver（key），同步显示名称
        if self.version_var.get() and not self.version_display_var.get():
            self.version_display_var.set(self.project_config.get(self.version_var.get(), {}).get("name", self.version_var.get()))

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
        self.devices_text = scrolledtext.ScrolledText(config_frame, height=3, width=50)
        self.devices_text.grid(row=5, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # 配置网格权重
        config_frame.columnconfigure(1, weight=1)
        config_frame.rowconfigure(5, weight=1)

        # 初始刷新设备列表
        self.refresh_devices()

    def create_stability_test_tab(self):
        """创建稳定性测试选项卡"""
        stability_frame = ttk.Frame(self.notebook)
        self.notebook.add(stability_frame, text="稳定性测试")

        # 模块选择区域
        self.modules_frame = ttk.LabelFrame(stability_frame, text="自定义模块组合")
        self.modules_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        ToolTip(self.modules_frame, "选择要执行的稳定性测试模块：Monkey 模式压力测试（长时间压力）、异常恢复（网络/数据异常）、完整性能、仅响应性能等。勾选后将运行相应测试。")

        # 模块复选框变量
        self.module_vars = {
            'monkey_stress': tk.BooleanVar(value=True),
            'exception_recovery': tk.BooleanVar(value=True),
            'performance_response': tk.BooleanVar(value=False),
            'performance_all': tk.BooleanVar(value=True),
            'broadcast_stress': tk.BooleanVar(value=False),
            'tts_stress': tk.BooleanVar(value=False),
        }

        # Monkey 模式压力测试
        ttk.Checkbutton(self.modules_frame, text="Monkey 模式压力测试 (长时间压力测试)",
                        variable=self.module_vars['monkey_stress']).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 异常恢复测试
        ttk.Checkbutton(self.modules_frame, text="异常恢复测试 (网络异常、数据异常)",
                        variable=self.module_vars['exception_recovery']).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 性能测试选项
        ttk.Label(self.modules_frame, text="性能测试:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)

        ttk.Checkbutton(self.modules_frame, text="完整性能测试 (响应+资源)",
                        variable=self.module_vars['performance_all']).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        ttk.Checkbutton(self.modules_frame, text="仅响应性能测试 (冷启动、下发→展示)",
                        variable=self.module_vars['performance_response']).grid(row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=2)

        # 测试参数设置
        ttk.Label(stability_frame, text="测试参数设置", font=("Arial", 12, "bold")).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

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
        # 同时在水平与垂直方向填充，便于内部 Monkey 遮罩区域正常展示
        options_frame.grid(row=6, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=10)

        self.baseline_establish_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="建立性能基线", variable=self.baseline_establish_var).grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)

        self.baseline_compare_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="与基线对比", variable=self.baseline_compare_var).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        self.no_mock_server_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="禁用Mock Server", variable=self.no_mock_server_var).grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)

        self.no_network_proxy_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(options_frame, text="禁用网络代理", variable=self.no_network_proxy_var).grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        # Monkey 遮罩区域配置（百分比）
        mask_frame = ttk.LabelFrame(options_frame, text="Monkey 遮罩区域（百分比 0.0 - 100.0）")
        mask_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=(8, 4))

        ttk.Label(mask_frame, text="上边缘:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(mask_frame, width=6, textvariable=self.monkey_mask_top_var).grid(row=0, column=1, sticky=tk.W, padx=(0, 10), pady=2)
        ttk.Label(mask_frame, text="%   下边缘:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(mask_frame, width=6, textvariable=self.monkey_mask_bottom_var).grid(row=0, column=3, sticky=tk.W, padx=(0, 10), pady=2)

        ttk.Label(mask_frame, text="左边缘:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(mask_frame, width=6, textvariable=self.monkey_mask_left_var).grid(row=1, column=1, sticky=tk.W, padx=(0, 10), pady=2)
        ttk.Label(mask_frame, text="%   右边缘:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(mask_frame, width=6, textvariable=self.monkey_mask_right_var).grid(row=1, column=3, sticky=tk.W, padx=(0, 10), pady=2)

        # 遮罩预览与最近一次测试遮罩图查看
        preview_btn = ttk.Button(mask_frame, text="🔍 生成当前遮罩预览", command=self.preview_monkey_mask_overlay)
        preview_btn.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(4, 2))

        open_last_btn = ttk.Button(mask_frame, text="🖼️ 打开最近遮罩图", command=self.open_latest_safe_region_overlay)
        open_last_btn.grid(row=2, column=2, columnspan=2, sticky=tk.W, padx=5, pady=(4, 2))

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

        self.pause_stability_btn = ttk.Button(button_frame, text="⏸ 暂停", command=self.pause_test, state=["disabled"])
        self.pause_stability_btn.pack(side=tk.LEFT, padx=5)
        self.resume_stability_btn = ttk.Button(button_frame, text="▶ 继续", command=self.resume_test, state=["disabled"])
        self.resume_stability_btn.pack(side=tk.LEFT, padx=5)
        self.stop_stability_btn = ttk.Button(button_frame, text="⏹️ 停止测试", command=self.stop_test, state=["disabled"])
        self.stop_stability_btn.pack(side=tk.LEFT, padx=5)

        # 进度显示
        ttk.Label(stability_frame, text="测试进度", font=("Arial", 12, "bold")).grid(row=10, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        self.stability_progress = ttk.Progressbar(stability_frame, orient="horizontal", mode="indeterminate")
        self.stability_progress.grid(row=11, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

        # 配置网格权重
        # 1. 整体稳定性选项卡：让右侧列可伸展，并为包含测试选项的第 6 行分配权重
        stability_frame.columnconfigure(1, weight=1)
        stability_frame.rowconfigure(6, weight=1)

        # 2. 测试选项区域：保证两列等宽，并为 Monkey 遮罩所在的第 2 行分配权重，避免内容被压缩/遮挡
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)
        options_frame.rowconfigure(2, weight=1)

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
        ttk.Button(button_frame, text="♻ 重构报告", command=self.refactor_selected_report).pack(side=tk.LEFT, padx=5)

        # 报告预览
        ttk.Label(reports_frame, text="报告预览", font=("Arial", 12, "bold")).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=10)

        self.report_preview = scrolledtext.ScrolledText(reports_frame, height=15, wrap=tk.WORD)
        self.report_preview.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        self.reports_listbox.bind("<<ListboxSelect>>", self._on_report_selection_changed)

        # 配置网格权重
        reports_frame.columnconfigure(0, weight=1)
        reports_frame.columnconfigure(1, weight=1)
        reports_frame.rowconfigure(1, weight=1)
        reports_frame.rowconfigure(4, weight=1)

        # 初始刷新报告列表
        self.refresh_reports()
        # 启动报告自动刷新，便于看到进行中的实时报告
        self._start_report_polling()

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

        # 主容器：使用grid布局，确保标题区域居中，主题选择在右侧
        main_container = tk.Frame(title_frame, bg=UIColors.WHITE)
        main_container.pack(fill=tk.X, padx=15, pady=(10, 15))
        
        # 配置grid列：左侧弹性空间 | 标题区域（居中） | 右侧弹性空间（包含主题选择）
        main_container.grid_columnconfigure(0, weight=1)  # 左侧弹性空间
        main_container.grid_columnconfigure(1, weight=0)  # 标题区域（不拉伸，居中）
        main_container.grid_columnconfigure(2, weight=1)  # 右侧弹性空间

        # 标题和副标题容器（居中显示，不受右侧影响）
        title_container = tk.Frame(main_container, bg=UIColors.WHITE)
        title_container.grid(row=0, column=1)

        # 主标题（在标题容器中居中）
        title_label = tk.Label(
            title_container,
            text="🚀 端侧自动化测试工具",
            font=UIFonts.TITLE,
            fg=UIColors.TEXT_PRIMARY,
            bg=UIColors.WHITE
        )
        title_label.pack()

        # 副标题（在标题容器中居中）
        subtitle_label = tk.Label(
            title_container,
            text="车载端侧应用稳定性测试平台 | v1.0.0",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE
        )
        subtitle_label.pack(pady=(5, 0))

        # 主题选择（右侧，绝对定位，不影响标题居中）
        theme_container = tk.Frame(main_container, bg=UIColors.WHITE)
        theme_container.grid(row=0, column=2, sticky=tk.E, padx=(10, 0))

        # 紧凑的标签（使用图标或简短文字）
        theme_label = tk.Label(
            theme_container,
            text="🎨",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            cursor='hand2'
        )
        theme_label.pack(side=tk.LEFT, padx=(0, 3))
        # 添加提示说明
        ToolTip(theme_label, "选择界面主题")

        # 紧凑的下拉框（减小宽度，优化显示）
        self.theme_combo = ttk.Combobox(
            theme_container,
            textvariable=self.theme_display_var,
            values=[TTK_THEME_LABELS.get(t, t) for t in TTKBOOTSTRAP_THEMES],
            state="readonly",
            width=8  # 从10减小到8，节省水平空间
        )
        # 轻量化：更小宽度、更统一字体、减少占位
        try:
            self.theme_combo.configure(font=UIFonts.CAPTION)
        except Exception:
            pass
        self.theme_combo.pack(side=tk.LEFT)
        self.theme_combo.bind("<<ComboboxSelected>>", self.on_theme_change)

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

        # 测试模块选择（下拉显示 name，内部使用 key）
        ttk.Label(card, text="测试模块选择:", font=UIFonts.BODY).grid(row=0, column=0, sticky=tk.W, pady=(10, 5))
        version_names = [self.project_config.get(k, {}).get("name", k) for k in self.available_versions]
        self.version_combo = ttk.Combobox(
            card,
            textvariable=self.version_display_var,
            values=version_names,
            state="readonly",
            font=UIFonts.BODY
        )
        self.version_combo.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=(10, 5))
        self.version_combo.bind("<<ComboboxSelected>>", self.on_version_selected)
        ToolTip(self.version_combo, "选择测试模块（来自 conf/project.json）。选中后下方显示该模块说明。")
        # 方案 C：当前选中模块的说明（只读）
        ttk.Label(card, text="模块说明:", font=UIFonts.BODY).grid(row=1, column=0, sticky=tk.N+tk.W, pady=(5, 2))
        self.module_description_text = tk.Text(
            card, height=3, wrap=tk.WORD, state=tk.DISABLED,
            font=UIFonts.CAPTION, bg=UIColors.WHITE, fg=UIColors.TEXT_PRIMARY,
            relief=tk.FLAT, padx=4, pady=4
        )
        self.module_description_text.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=(5, 5))
        self._update_module_description()

        # 设备选择
        ttk.Label(card, text="目标设备:", font=UIFonts.BODY).grid(row=2, column=0, sticky=tk.W, pady=5)
        self.device_sn_var = tk.StringVar(value="emulator-5554")
        # 下拉框：显示检测到的设备SN（可手动输入兜底）
        self.device_combo = ttk.Combobox(
            card,
            textvariable=self.device_sn_var,
            values=[],
            state="readonly",
            font=UIFonts.BODY
        )
        self.device_combo.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
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
        self._device_status_in_config.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 6))

        # ADB 路径（Windows 上常见 PATH 未配置导致无法识别设备）
        ttk.Label(card, text="ADB路径:", font=UIFonts.BODY).grid(row=4, column=0, sticky=tk.W, pady=5)
        adb_row = tk.Frame(card, bg=UIColors.WHITE)
        adb_row.grid(row=4, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        adb_row.grid_columnconfigure(0, weight=1)
        ttk.Entry(adb_row, textvariable=self.adb_path_var, font=UIFonts.BODY).grid(row=0, column=0, sticky=tk.EW)
        self.create_action_button(
            adb_row,
            text="浏览",
            command=self.browse_adb,
            variant="secondary"
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(card, text="包名:", font=UIFonts.BODY).grid(row=5, column=0, sticky=tk.W, pady=5)
        pkg_row = tk.Frame(card, bg=UIColors.WHITE)
        pkg_row.grid(row=5, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        pkg_row.grid_columnconfigure(0, weight=1)
        self.package_combo = ttk.Combobox(
            pkg_row,
            textvariable=self.package_name_var,
            values=[],
            state="normal",  # 支持输入片段筛选
            font=UIFonts.BODY
        )
        self.package_combo.grid(row=0, column=0, sticky=tk.EW)
        self.package_combo.bind("<<ComboboxSelected>>", self._on_package_selected)
        self.package_combo.bind("<KeyRelease>", self._on_package_filter_keyrelease)
        self.package_combo.bind("<FocusIn>", self._on_package_filter_focus_in)
        self.create_action_button(
            pkg_row,
            text="扫描",
            command=self.refresh_installed_apps,
            variant="secondary"
        ).grid(row=0, column=1, padx=(8, 0))

        # 应用类型（系统应用 / 普通应用，用于安装/卸载等操作；测试仅针对已安装应用）
        ttk.Label(card, text="应用类型:", font=UIFonts.BODY).grid(row=6, column=0, sticky=tk.W, pady=5)
        app_row = tk.Frame(card, bg=UIColors.WHITE)
        app_row.grid(row=6, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=5)
        tk.Radiobutton(
            app_row,
            text="系统应用",
            variable=self.app_type_var,
            value="system",
            command=self._on_app_type_changed,
            bg=UIColors.WHITE,
            font=UIFonts.BODY,
            cursor="hand2",
        ).pack(side=tk.LEFT)
        tk.Radiobutton(
            app_row,
            text="普通应用",
            variable=self.app_type_var,
            value="normal",
            command=self._on_app_type_changed,
            bg=UIColors.WHITE,
            font=UIFonts.BODY,
            cursor="hand2",
        ).pack(side=tk.LEFT, padx=(10, 0))

        # 刷新设备列表 + 安装APK + 卸载应用
        btn_row = tk.Frame(card, bg=UIColors.WHITE)
        btn_row.grid(row=7, column=0, columnspan=2, pady=(15, 10))
        self.create_action_button(btn_row, text="🔄 刷新设备列表", command=self.refresh_devices, variant="success").pack(side=tk.LEFT, padx=(0, 8))
        self.create_action_button(btn_row, text="📦 安装APK", command=self._on_install_apk_clicked, variant="primary").pack(side=tk.LEFT, padx=(0, 8))
        self.create_action_button(btn_row, text="🗑️ 卸载应用", command=self._on_uninstall_app_clicked, variant="secondary").pack(side=tk.LEFT)

        card.columnconfigure(1, weight=1)
        # 初始化：若尚未有选中版本，选第一个
        if self.available_versions and not self.version_var.get():
            self.version_var.set(self.available_versions[0])
            self.version_display_var.set(self.project_config.get(self.available_versions[0], {}).get("name", self.available_versions[0]))
            self._update_module_description()
        self._on_app_type_changed()

    def create_test_operation_card(self, parent):
        """创建测试操作卡片（弹窗入口）"""
        card = self.create_card(parent, "⚡ 测试操作")

        info_label = tk.Label(
            card,
            text="测试参数在配置窗口中调整后会自动保存",
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

        self.pause_test_btn = self.create_action_button(
            btn_row, text="⏸ 暂停",
            command=self.pause_test,
            variant="secondary",
            side=tk.LEFT,
            padx=(0, 5)
        )
        self.pause_test_btn.config(state="disabled")
        self.resume_test_btn = self.create_action_button(
            btn_row, text="▶ 继续",
            command=self.resume_test,
            variant="secondary",
            side=tk.LEFT,
            padx=(0, 10)
        )
        self.resume_test_btn.config(state="disabled")
        self.stop_test_btn = self.create_action_button(
            btn_row, text="⏹️ 停止测试",
            command=self.stop_test,
            variant="error",
            side=tk.LEFT,
            padx=(0, 10)
        )
        self.stop_test_btn.config(state="disabled")

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
            command=self.show_reports_window_v2,
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

        enabled = [k for k, v in self.module_vars.items() if v.get()]
        name_map = {
            "monkey_stress": "Monkey 模式压力测试",
            "exception_recovery": "异常恢复",
            "performance_all": "完整性能",
            "performance_response": "响应性能",
        }
        modules_text = "、".join([name_map.get(k, k) for k in enabled]) if enabled else "（未选择）"
        mode_text = "完整测试套件" if (enabled and len(enabled) >= 3) else "自定义模块"

        duration = self.duration_var.get()
        unit = getattr(self, "duration_unit_var", None)
        unit_txt = unit.get() if unit is not None else "小时"
        if unit_txt.startswith("分"):
            duration_display = f"{duration}min"
        else:
            duration_display = f"{duration}h"
        network = self.network_method_var.get()
        self._test_summary_label.config(
            text=f"当前模式：{mode_text} | 模块：{modules_text}\n"
                 f"稳定性：{duration_display} / 网络：{network}"
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
        cfg_canvas = tk.Canvas(container, bg=UIColors.BG_LIGHT, highlightthickness=0)
        cfg_vbar = ttk.Scrollbar(container, orient="vertical", command=cfg_canvas.yview)
        cfg_canvas.configure(yscrollcommand=cfg_vbar.set)
        cfg_vbar.pack(side=tk.RIGHT, fill=tk.Y)
        cfg_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        cfg_inner = tk.Frame(cfg_canvas, bg=UIColors.BG_LIGHT)
        cfg_inner_id = cfg_canvas.create_window((0, 0), window=cfg_inner, anchor="nw")
        cfg_inner.bind("<Configure>", lambda e: cfg_canvas.configure(scrollregion=cfg_canvas.bbox("all")))
        cfg_canvas.bind("<Configure>", lambda e: cfg_canvas.itemconfig(cfg_inner_id, width=e.width))
        cfg_canvas.bind("<Enter>", lambda e: cfg_canvas.bind_all("<MouseWheel>", lambda ev: cfg_canvas.yview_scroll(int(-ev.delta / 120), "units")))
        cfg_canvas.bind("<Leave>", lambda e: cfg_canvas.unbind_all("<MouseWheel>"))

        self.build_test_config_ui(cfg_inner)

    def build_test_config_ui(self, parent):


        """
        构建“测试配置”主窗口。
        仅展示各功能大类的入口按钮，具体配置在独立子窗口中完成。
        """
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # 外层：上部入口区 + 底部操作区
        wrapper = tk.Frame(parent, bg=UIColors.BG_LIGHT)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        content = tk.Frame(wrapper, bg=UIColors.BG_LIGHT)
        content.grid(row=0, column=0, sticky="nsew", padx=20, pady=10)
        content.grid_columnconfigure(0, weight=1)
        for i in range(5):
            content.grid_rowconfigure(i, weight=0)

        # 0) 置顶包名列表（扫描应用时这些包在顶部显示）
        pinned_card = self.create_card_grid(
            content,
            "📌 置顶包名列表（pinned_packages）",
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 0),
            pady=(0, 10),
        )
        tk.Label(
            pinned_card,
            text="每行一个包名，扫描设备应用时这些包会在列表顶部显示。",
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.CAPTION,
            justify=tk.LEFT,
            anchor="w",
            wraplength=700,
        ).pack(fill=tk.X, pady=(0, 6))
        from tkinter import scrolledtext as _st
        self.pinned_packages_text = _st.ScrolledText(
            pinned_card,
            height=3,
            width=60,
            font=UIFonts.MONO,
            wrap=tk.NONE,
        )
        self.pinned_packages_text.pack(fill=tk.X, pady=(0, 5))
        try:
            if getattr(self, "pinned_packages", None):
                self.pinned_packages_text.insert("1.0", "\n".join(self.pinned_packages))
        except Exception:
            pass

        # 1) 稳定性测试配置
        stability_card = self.create_card_grid(
            content,
            "🧭 稳定性测试配置",
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 0),
            pady=(0, 10),
        )
        tk.Label(
            stability_card,
            text="配置稳定性测试的测试模式、模块选择、时长、网络模拟、测试选项等参数。",
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.BODY,
            justify=tk.LEFT,
            anchor="w",
            wraplength=700,
        ).pack(fill=tk.X, pady=(0, 8))
        self.create_action_button(
            stability_card,
            text="打开稳定性测试配置...",
            command=self.open_stability_config_dialog,
            variant="primary",
            width=22,
            side=tk.LEFT,
            padx=(0, 10),
        )

        # 2) Mock Server 配置
        mock_card = self.create_card_grid(
            content,
            "🧪 Mock Server 配置",
            row=2,
            column=0,
            sticky="nsew",
            padx=(0, 0),
            pady=(0, 10),
        )
        tk.Label(
            mock_card,
            text="配置 Mock Server 的 Host / Port / 规则文件等信息，并与异常恢复测试联动。",
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.BODY,
            justify=tk.LEFT,
            anchor="w",
            wraplength=700,
        ).pack(fill=tk.X, pady=(0, 8))
        self.create_action_button(
            mock_card,
            text="打开 Mock Server 配置...",
            command=self.open_mock_server_config_dialog,
            variant="primary",
            width=22,
            side=tk.LEFT,
            padx=(0, 10),
        )

        # 3) 性能监控配置
        perf_card = self.create_card_grid(
            content,
            "⚡ 性能监控配置",
            row=3,
            column=0,
            sticky="nsew",
            padx=(0, 0),
            pady=(0, 0),
        )
        tk.Label(
            perf_card,
            text="配置响应性能监控所使用的可点击元素列表等参数。",
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.BODY,
            justify=tk.LEFT,
            anchor="w",
            wraplength=700,
        ).pack(fill=tk.X, pady=(0, 8))
        self.create_action_button(
            perf_card,
            text="打开性能监控配置...",
            command=self.open_performance_monitor_config_dialog,
            variant="primary",
            width=22,
            side=tk.LEFT,
            padx=(0, 10),
        )

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
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")

        btns = tk.Frame(footer, bg=UIColors.BG_LIGHT)
        btns.grid(row=0, column=1, sticky="e")

        self.create_action_button(
            btns,
            text="🔄 同步配置",
            command=self.save_test_ui_config,
            variant="success",
            width=12,
            side=tk.LEFT,
            padx=(0, 10),
        )
        self.create_action_button(
            btns,
            text="关闭",
            command=lambda: self.test_config_window.destroy() if self.test_config_window else None,
            variant="secondary",
            width=12,
            side=tk.LEFT,
        )

    def _get_test_ui_config_path(self):
        """测试配置持久化文件路径（与 conf/project.json 分离）"""
        return os.path.join("conf", "test_ui_config.json")

    def _get_broadcast_hints_for_config(self):
        """获取广播Hints配置：优先从配置弹窗的文本框读取，否则从 var"""
        try:
            w = getattr(self, "_broadcast_hints_text", None)
            if w and w.winfo_exists():
                raw = w.get("1.0", tk.END)
                return [line.strip() for line in str(raw).splitlines() if line.strip()]
        except Exception:
            pass
        v = getattr(self, "broadcast_hints_var", None)
        if v and v.get():
            return [line.strip() for line in v.get().splitlines() if line.strip()]
        return ["介绍一下白居易", "讲个笑话"]

    def _get_tts_texts_for_config(self):
        """获取 TTS 文本配置：优先从配置弹窗的文本框读取，否则从 var"""
        try:
            w = getattr(self, "_tts_texts_text", None)
            if w and w.winfo_exists():
                raw = w.get("1.0", tk.END)
                return [line.strip() for line in str(raw).splitlines() if line.strip()]
        except Exception:
            pass
        v = getattr(self, "tts_texts_var", None)
        if v and v.get():
            return [line.strip() for line in v.get().splitlines() if line.strip()]
        return ["打开设置", "介绍一下北京"]

    def _get_response_monitor_for_config(self):
        """获取响应监控配置：时间参数（仅 logcat 模式，发送后立即监控）"""
        def _num(var_attr, default):
            v = getattr(self, var_attr, None)
            if v is None:
                return default
            try:
                return float(v.get())
            except (TypeError, ValueError):
                try:
                    return float(v.get())
                except (TypeError, ValueError):
                    return default
        cfg = {
            "max_wait_for_appear": _num("response_monitor_max_wait_appear_var", 6),
            "check_interval": _num("response_monitor_check_interval_var", 0.1),
            "max_wait_for_disappear": _num("response_monitor_max_wait_disappear_var", 300),
        }
        # 连续 ANR/无响应次数阈值：0 表示禁用自动恢复，>0 表示连续 N 次后触发
        try:
            v = getattr(self, "response_monitor_anr_recover_threshold_var", None)
            if v is not None:
                threshold = int(float(v.get() or "1"))
            else:
                threshold = 1
        except Exception:
            threshold = 1
        if threshold < 0:
            threshold = 0
        cfg["anr_recover_threshold"] = threshold
        return cfg

    def _get_app_log_for_config(self):
        """获取 app.log 采集配置（差异化采集策略）"""
        def _num(var_attr, default, cast=float, min_v=None):
            v = getattr(self, var_attr, None)
            if v is None:
                return default
            try:
                x = cast(v.get())
            except Exception:
                return default
            if min_v is not None:
                try:
                    if x < min_v:
                        return min_v
                except Exception:
                    return default
            return x

        return {
            "enabled": bool(getattr(self, "app_log_enabled_var", tk.BooleanVar(value=True)).get()),
            "extra_packages_csv": (getattr(self, "app_log_extra_packages_var", tk.StringVar(value="")).get() or "").strip(),
            "package_process_map": (getattr(self, "app_log_package_process_map_var", tk.StringVar(value="")).get() or "").strip(),
            "include_process_names_csv": (getattr(self, "app_log_include_process_names_var", tk.StringVar(value="")).get() or "").strip(),
            "levels": (getattr(self, "app_log_levels_var", tk.StringVar(value="VDIWEF")).get() or "VDIWEF").strip(),
            "tags_include_csv": (getattr(self, "app_log_tags_include_var", tk.StringVar(value="")).get() or "").strip(),
            "tags_exclude_csv": (getattr(self, "app_log_tags_exclude_var", tk.StringVar(value="")).get() or "").strip(),
            "keywords_include_csv": (getattr(self, "app_log_keywords_include_var", tk.StringVar(value="")).get() or "").strip(),
            "keywords_exclude_csv": (getattr(self, "app_log_keywords_exclude_var", tk.StringVar(value="")).get() or "").strip(),
            "output_subdir": (getattr(self, "app_log_output_subdir_var", tk.StringVar(value="")).get() or "").strip(),
            "max_file_mb": _num("app_log_max_file_mb_var", 50.0, float, 1.0),
            "backup_count": int(_num("app_log_backup_count_var", 3, int, 1)),
            "flush_interval_ms": int(_num("app_log_flush_interval_ms_var", 500, int, 50)),
            "batch_lines": int(_num("app_log_batch_lines_var", 50, int, 1)),
            "pid_refresh_seconds": float(_num("app_log_pid_refresh_seconds_var", 2.0, float, 0.5)),
        }

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

        # 同步 pinned_packages_text（若存在）到内存列表
        try:
            widget = getattr(self, "pinned_packages_text", None)
            if widget is not None and widget.winfo_exists():
                raw = widget.get("1.0", tk.END)
                pkgs = []
                for line in str(raw).splitlines():
                    p = line.strip()
                    if p:
                        pkgs.append(p)
                # 去重保序
                seen = set()
                cleaned = []
                for p in pkgs:
                    if p in seen:
                        continue
                    seen.add(p)
                    cleaned.append(p)
                self.pinned_packages = cleaned
        except Exception:
            pass

        return {
            "theme": self.theme_var.get(),
            "adb_path": self.adb_path_var.get(),
            "app_type": self.app_type_var.get(),
            "package_name": self.package_name_var.get(),
            "pinned_packages": list(self.pinned_packages) if isinstance(self.pinned_packages, list) else [],
            # 主界面常用配置也纳入持久化（避免用户重启丢失）
            "prj_ver": (self.version_var.get() or "").strip(),
            "device_sn": _get_var("device_sn_var", ""),
            "apk_path": _get_var("apk_path_var", ""),
            "email": _get_var("email_var", ""),
            "test_mode": self.test_mode_var.get(),
            "modules": {k: bool(v.get()) for k, v in self.module_vars.items()},
            "duration_preset": getattr(self, "duration_preset_var", tk.StringVar(value="")).get(),
            "duration": self.duration_var.get(),
            "duration_unit": self.duration_unit_var.get(),
            "network_method": self.network_method_var.get(),
            "multi_devices": self.multi_devices_var.get(),
            "baseline_establish": bool(self.baseline_establish_var.get()),
            "baseline_compare": bool(self.baseline_compare_var.get()),
            "no_mock_server": bool(self.no_mock_server_var.get()),
            "no_network_proxy": bool(self.no_network_proxy_var.get()),
            "use_fallback_only": bool(self.use_fallback_only_var.get()),
            "mock_server": {
                "mode": "mitmproxy",
                "host": self.mock_host_var.get(),
                "port": self.mock_port_var.get(),
                "rules_path": self.mock_rules_path_var.get(),
            },
            "performance_monitor": {
                "clickable_elements": self.performance_clickable_elements_var.get(),
            },
            "monkey_mask": {
                "top": self.monkey_mask_top_var.get(),
                "bottom": self.monkey_mask_bottom_var.get(),
                "left": self.monkey_mask_left_var.get(),
                "right": self.monkey_mask_right_var.get(),
            },
            "broadcast_stress": {
                "hints": self._get_broadcast_hints_for_config(),
                "hints_file": getattr(self, "broadcast_hints_file_var", tk.StringVar(value="")).get().strip(),
            },
            "tts_stress": {
                "texts": self._get_tts_texts_for_config(),
                "texts_file": getattr(self, "tts_texts_file_var", tk.StringVar(value="")).get().strip(),
                "end_phrase": getattr(self, "tts_end_phrase_var", tk.StringVar(value="")).get().strip(),
                "wake_phrase": getattr(self, "tts_wake_phrase_var", tk.StringVar(value="")).get().strip(),
                "wake_delay_seconds": getattr(self, "tts_wake_delay_var", tk.StringVar(value="2")).get().strip(),
                "interval_seconds": getattr(self, "tts_interval_seconds_var", tk.StringVar(value="30")).get().strip(),
                "volume_percent": getattr(self, "tts_volume_percent_var", tk.StringVar(value="100")).get().strip(),
            },
            "app_log": self._get_app_log_for_config(),
            "response_monitor": self._get_response_monitor_for_config(),
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

        app_type = cfg.get("app_type")
        if app_type in ("system", "normal"):
            self.app_type_var.set(app_type)
        package_name = cfg.get("package_name")
        if isinstance(package_name, str):
            self.package_name_var.set(package_name.strip())
        pinned = cfg.get("pinned_packages")
        if isinstance(pinned, list):
            seen = set()
            cleaned = []
            for p in pinned:
                p = (p or "").strip()
                if not p or p in seen:
                    continue
                seen.add(p)
                cleaned.append(p)
            self.pinned_packages = cleaned

        # 主界面常用配置（可选项：不存在则不覆盖）
        prj_ver = cfg.get("prj_ver")
        if isinstance(prj_ver, str) and prj_ver.strip():
            try:
                if hasattr(self, "version_var") and self.version_var is not None:
                    self.version_var.set(prj_ver.strip())
                if hasattr(self, "version_display_var") and self.version_display_var is not None:
                    name = getattr(self, "project_config", {}).get(prj_ver.strip(), {}).get("name", prj_ver.strip())
                    self.version_display_var.set(name)
                self._update_module_description()
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
        # 预设方案优先：恢复方案选择，并同步到底层 duration_var/duration_unit_var
        dp = cfg.get("duration_preset")
        if isinstance(dp, str) and dp.strip() and hasattr(self, "duration_preset_var"):
            try:
                self.duration_preset_var.set(dp.strip())
                # 同步应用（兼容 combobox 尚未创建的情况）
                try:
                    self.on_duration_preset_changed()
                except Exception:
                    pass
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
        if "use_fallback_only" in cfg:
            self.use_fallback_only_var.set(bool(cfg["use_fallback_only"]))

        ms = cfg.get("mock_server")
        if isinstance(ms, dict):
            if "host" in ms:
                self.mock_host_var.set(str(ms["host"]))
            if "port" in ms:
                self.mock_port_var.set(str(ms["port"]))
            if "rules_path" in ms:
                self.mock_rules_path_var.set(str(ms["rules_path"]))

        pm = cfg.get("performance_monitor")
        if isinstance(pm, dict):
            if "clickable_elements" in pm:
                self.performance_clickable_elements_var.set(str(pm["clickable_elements"]))

        mm = cfg.get("monkey_mask")
        if isinstance(mm, dict):
            if "top" in mm:
                self.monkey_mask_top_var.set(str(mm["top"]))
            if "bottom" in mm:
                self.monkey_mask_bottom_var.set(str(mm["bottom"]))
            if "left" in mm:
                self.monkey_mask_left_var.set(str(mm["left"]))
            if "right" in mm:
                self.monkey_mask_right_var.set(str(mm["right"]))

        bc = cfg.get("broadcast_stress")
        if isinstance(bc, dict):
            if "hints" in bc and isinstance(bc["hints"], list):
                self.broadcast_hints_var.set("\n".join(str(h) for h in bc["hints"]))
            if "hints_file" in bc:
                self.broadcast_hints_file_var.set(str(bc["hints_file"]))
        tts = cfg.get("tts_stress")
        if isinstance(tts, dict):
            if "texts" in tts and isinstance(tts["texts"], list):
                self.tts_texts_var.set("\n".join(str(t) for t in tts["texts"]))
            if "texts_file" in tts:
                self.tts_texts_file_var.set(str(tts["texts_file"]))
            if "end_phrase" in tts:
                self.tts_end_phrase_var.set(str(tts["end_phrase"] or ""))
            if "wake_phrase" in tts:
                self.tts_wake_phrase_var.set(str(tts["wake_phrase"] or ""))
            if "wake_delay_seconds" in tts and tts["wake_delay_seconds"] is not None:
                self.tts_wake_delay_var.set(str(tts["wake_delay_seconds"]))
            if "interval_seconds" in tts and tts["interval_seconds"] is not None:
                self.tts_interval_seconds_var.set(str(tts["interval_seconds"]))
            if "volume_percent" in tts and tts["volume_percent"] is not None:
                self.tts_volume_percent_var.set(str(tts["volume_percent"]))
        app_log = cfg.get("app_log")
        if isinstance(app_log, dict):
            if "enabled" in app_log:
                self.app_log_enabled_var.set(bool(app_log["enabled"]))
            if "extra_packages_csv" in app_log:
                self.app_log_extra_packages_var.set(str(app_log["extra_packages_csv"] or ""))
            if "package_process_map" in app_log:
                self.app_log_package_process_map_var.set(str(app_log["package_process_map"] or ""))
            if "include_process_names_csv" in app_log:
                self.app_log_include_process_names_var.set(str(app_log["include_process_names_csv"] or ""))
            if "levels" in app_log:
                self.app_log_levels_var.set(str(app_log["levels"] or "VDIWEF"))
            if "tags_include_csv" in app_log:
                self.app_log_tags_include_var.set(str(app_log["tags_include_csv"] or ""))
            if "tags_exclude_csv" in app_log:
                self.app_log_tags_exclude_var.set(str(app_log["tags_exclude_csv"] or ""))
            if "keywords_include_csv" in app_log:
                self.app_log_keywords_include_var.set(str(app_log["keywords_include_csv"] or ""))
            if "keywords_exclude_csv" in app_log:
                self.app_log_keywords_exclude_var.set(str(app_log["keywords_exclude_csv"] or ""))
            if "output_subdir" in app_log:
                self.app_log_output_subdir_var.set(str(app_log["output_subdir"] or ""))
            if "max_file_mb" in app_log and app_log["max_file_mb"] is not None:
                self.app_log_max_file_mb_var.set(str(app_log["max_file_mb"]))
            if "backup_count" in app_log and app_log["backup_count"] is not None:
                self.app_log_backup_count_var.set(str(app_log["backup_count"]))
            if "flush_interval_ms" in app_log and app_log["flush_interval_ms"] is not None:
                self.app_log_flush_interval_ms_var.set(str(app_log["flush_interval_ms"]))
            if "batch_lines" in app_log and app_log["batch_lines"] is not None:
                self.app_log_batch_lines_var.set(str(app_log["batch_lines"]))
            if "pid_refresh_seconds" in app_log and app_log["pid_refresh_seconds"] is not None:
                self.app_log_pid_refresh_seconds_var.set(str(app_log["pid_refresh_seconds"]))

        rm = cfg.get("response_monitor")
        if isinstance(rm, dict):
            if "max_wait_for_appear" in rm and rm["max_wait_for_appear"] is not None:
                self.response_monitor_max_wait_appear_var.set(str(rm["max_wait_for_appear"]))
            if "check_interval" in rm and rm["check_interval"] is not None:
                self.response_monitor_check_interval_var.set(str(rm["check_interval"]))
            if "max_wait_for_disappear" in rm and rm["max_wait_for_disappear"] is not None:
                self.response_monitor_max_wait_disappear_var.set(str(rm["max_wait_for_disappear"]))
            if "anr_recover_threshold" in rm and rm["anr_recover_threshold"] is not None:
                self.response_monitor_anr_recover_threshold_var.set(str(rm["anr_recover_threshold"]))

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
            
            # 加载 GUI 特定配置（字体、窗口大小等）
            gui_cfg = cfg.get("gui", {})
            if isinstance(gui_cfg, dict):
                # 最小窗口大小
                min_width = gui_cfg.get("min_window_width")
                min_height = gui_cfg.get("min_window_height")
                if min_width and min_height:
                    try:
                        self.root.minsize(int(min_width), int(min_height))
                    except Exception:
                        pass
                
                # 字体缩放
                font_scale = gui_cfg.get("font_scale")
                if font_scale:
                    try:
                        scale_factor = float(font_scale)
                        for name in self._font_base_sizes:
                            self._font_base_sizes[name] = int(self._font_base_sizes.get(name, 11) * scale_factor)
                        self._scale_fonts(self.root.winfo_width())
                    except Exception:
                        pass
        except Exception as e:
            logging.warning("加载测试配置失败: %s", e)
        finally:
            self._suppress_autosave = False

    def save_test_ui_config(self):
        """手动同步测试配置到文件（自动保存已开启；此按钮用于立即写入）"""
        self._autosave_now(force=True, notify=True)

    def preview_monkey_mask_overlay(self):
        """
        基于当前 GUI 中配置的 Monkey 遮罩百分比，生成一张最新的遮罩预览图并打开。
        该预览会：
        - 直接使用当前设备截图
        - 按百分比计算上下左右的非可操作区域
        - 在 logs/<sn>/safe_region_overlay.png 中输出预览图
        """
        sn = (self.device_sn_var.get() or "").strip()
        if not sn:
            messagebox.showwarning("提示", "请先填写设备序列号")
            return

        # 解析百分比输入（容错：非法输入按 0.0 处理）
        def _parse_pct(var):
            try:
                v = float(var.get())
                if v < 0:
                    v = 0.0
                if v > 100:
                    v = 100.0
                return v
            except Exception:
                return 0.0

        top_pct = _parse_pct(self.monkey_mask_top_var)
        bottom_pct = _parse_pct(self.monkey_mask_bottom_var)
        left_pct = _parse_pct(self.monkey_mask_left_var)
        right_pct = _parse_pct(self.monkey_mask_right_var)

        # 使用 ExtendedMonkeyTest 的安全区域 + 截图遮罩逻辑生成预览
        try:
            from utils.extended_monkey import ExtendedMonkeyTest
        except Exception as e:
            messagebox.showerror("错误", f"无法导入 ExtendedMonkeyTest，用于生成遮罩预览:\n{e}")
            return

        class _TmpDevice:
            def __init__(self, sn_val: str):
                self.sn = sn_val

        class _TmpPackage:
            def __init__(self, pkg_name: str):
                self.name = pkg_name or "dummy.app"
                # 预览不依赖 activity，这里给个占位
                self.activity = ""

        device = _TmpDevice(sn)
        pkg_name = (self.package_name_var.get() or "").strip()
        package = _TmpPackage(pkg_name)

        # 构造仅包含 monkey_mask 的 精简 long_stress 配置
        cfg = {
            "duration_hours": 0.1,
            "monkey_mask": {
                "top": top_pct,
                "bottom": bottom_pct,
                "left": left_pct,
                "right": right_pct,
            },
        }

        try:
            tester = ExtendedMonkeyTest(device, package, cfg)
            # 调用内部安全区域计算，会自动基于 monkey_mask + 截图生成 safe_region_overlay.png
            tester._get_safe_touch_region()
        except Exception as e:
            messagebox.showerror("错误", f"生成遮罩预览失败:\n{e}")
            return

        # 预览文件路径（预览使用 ExtendedMonkeyTest 的兜底路径：logs/<sn>/safe_region_overlay.png）
        overlay_path = os.path.join("logs", sn, "safe_region_overlay.png")
        if not os.path.isfile(overlay_path):
            messagebox.showinfo("提示", f"未找到遮罩预览文件：{overlay_path}")
            return

        try:
            if sys.platform == "win32":
                os.startfile(overlay_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", overlay_path])
            else:
                subprocess.Popen(["xdg-open", overlay_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开遮罩预览文件:\n{overlay_path}\n错误: {e}")

    def open_latest_safe_region_overlay(self):
        """
        打开当前设备最近一次 Monkey 模式压力测试生成的 safe_region_overlay.png。
        查找规则：
        logs/<sn>/<时间戳>/safe_region_overlay.png （按时间戳子目录从新到旧）
        若未找到，再退回 logs/<sn>/safe_region_overlay.png（例如仅做预览时生成）
        """
        sn = (self.device_sn_var.get() or "").strip()
        if not sn:
            messagebox.showwarning("提示", "请先填写设备序列号")
            return

        base_dir = os.path.join("logs", sn)
        candidate = None
        try:
            if os.path.isdir(base_dir):
                subdirs = [
                    d for d in os.listdir(base_dir)
                    if os.path.isdir(os.path.join(base_dir, d))
                ]
                # 只考虑纯数字且长度>=8的目录名，按名称倒序近似认为时间戳从新到旧
                subdirs = sorted(
                    [d for d in subdirs if d.isdigit()],
                    reverse=True
                )
                for d in subdirs:
                    p = os.path.join(base_dir, d, "safe_region_overlay.png")
                    if os.path.isfile(p):
                        candidate = p
                        break
        except Exception:
            candidate = None

        # 兜底：预览时使用的 logs/<sn>/safe_region_overlay.png
        if not candidate:
            p = os.path.join(base_dir, "safe_region_overlay.png")
            if os.path.isfile(p):
                candidate = p

        if not candidate:
            messagebox.showinfo("提示", "未找到最近的遮罩图文件，请先运行一次 Monkey 模式压力测试或生成遮罩预览。")
            return

        try:
            if sys.platform == "win32":
                os.startfile(candidate)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", candidate])
            else:
                subprocess.Popen(["xdg-open", candidate])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开遮罩图文件:\n{candidate}\n错误: {e}")

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
            getattr(self, "app_type_var", None),
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
            getattr(self, "baseline_establish_var", None),
            getattr(self, "baseline_compare_var", None),
            getattr(self, "no_mock_server_var", None),
            getattr(self, "no_network_proxy_var", None),
            getattr(self, "mock_host_var", None),
            getattr(self, "mock_port_var", None),
            getattr(self, "mock_rules_path_var", None),
            getattr(self, "performance_clickable_elements_var", None),
            getattr(self, "monkey_mask_top_var", None),
            getattr(self, "monkey_mask_bottom_var", None),
            getattr(self, "monkey_mask_left_var", None),
            getattr(self, "monkey_mask_right_var", None),
            # 响应监控（广播/TTS 共用）
            getattr(self, "response_monitor_wait_after_send_var", None),
            getattr(self, "response_monitor_max_wait_appear_var", None),
            getattr(self, "response_monitor_check_interval_var", None),
            getattr(self, "response_monitor_max_wait_disappear_var", None),
            # app.log 精准采集配置
            getattr(self, "app_log_enabled_var", None),
            getattr(self, "app_log_extra_packages_var", None),
            getattr(self, "app_log_package_process_map_var", None),
            getattr(self, "app_log_include_process_names_var", None),
            getattr(self, "app_log_levels_var", None),
            getattr(self, "app_log_tags_include_var", None),
            getattr(self, "app_log_tags_exclude_var", None),
            getattr(self, "app_log_keywords_include_var", None),
            getattr(self, "app_log_keywords_exclude_var", None),
            getattr(self, "app_log_output_subdir_var", None),
            getattr(self, "app_log_max_file_mb_var", None),
            getattr(self, "app_log_backup_count_var", None),
            getattr(self, "app_log_flush_interval_ms_var", None),
            getattr(self, "app_log_batch_lines_var", None),
            getattr(self, "app_log_pid_refresh_seconds_var", None),
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
            # 自动保存失败：记录日志，并在状态栏给出明确提示（不弹窗、不打断输入）
            logging.warning(f"自动保存测试配置失败: {e}")
            try:
                # 若主界面已准备好状态栏，则给出一条轻量级提示
                self.update_status(f"配置保存失败: {e}")
            except Exception:
                pass
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

            self._mock_server = create_mock_server(host=host, port=port)
            apply_rules(self._mock_server, self.load_mock_rules())
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
        if getattr(self, "_mock_rules_win", None) and self._mock_rules_win.winfo_exists():
            self._mock_rules_win.lift()
            self._mock_rules_win.focus_force()
            return
        win = tk.Toplevel(self.root)
        self._mock_rules_win = win
        win.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_mock_rules_win", None), win.destroy()))
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
            font=UIFonts.MONO,
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
            font=UIFonts.MONO,
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

    def create_collapsible_section(self, parent, title: str, default_open: bool = True):
        """
        在卡片内部创建一个可折叠的小节容器，用于承载次级/三级配置项。
        返回 (section_frame, body_frame)，调用方负责对 section_frame 进行 grid/pack。
        """
        section = tk.Frame(parent, bg=UIColors.WHITE)
        section.grid_columnconfigure(0, weight=1)

        header = tk.Frame(section, bg=UIColors.WHITE)
        header.grid(row=0, column=0, sticky="ew")

        indicator_var = tk.StringVar(value="▼" if default_open else "▶")

        body = tk.Frame(section, bg=UIColors.WHITE)

        def _toggle():
            # 折叠/展开 body，并切换指示符
            if body.winfo_ismapped():
                body.grid_remove()
                indicator_var.set("▶")
            else:
                body.grid(row=1, column=0, sticky="ew", pady=(2, 0))
                indicator_var.set("▼")

        btn = tk.Button(
            header,
            textvariable=indicator_var,
            width=2,
            command=_toggle,
            bg=UIColors.WHITE,
            bd=0,
            relief="flat",
            cursor="hand2",
        )
        btn.pack(side=tk.LEFT)

        tk.Label(
            header,
            text=title,
            font=UIFonts.BODY,
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_PRIMARY,
        ).pack(side=tk.LEFT, padx=(2, 0))

        if default_open:
            body.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        return section, body

    # ===== 统一按钮工厂 & 状态日志封装 =====
    def create_action_button(self, parent, text, command, variant="primary", width=None, **pack_kwargs):
        """
        创建统一风格的操作按钮
        variant: primary/success/error/warning/secondary/info
        width: 可选，按钮最小宽度（字符数），用于统一多按钮尺寸
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
        kw = dict(
            master=parent,
            text=text,
            command=command,
            bg=bg,
            fg=UIColors.WHITE,
            font=UIFonts.BUTTON,
            relief='flat',
            cursor='hand2',
        )
        if width is not None:
            kw["width"] = width
        btn = tk.Button(**kw)
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

    # ==================== 报告查看器 V2（详细列表 + 筛选 + 迁移命名） ====================

    def _migrate_report_filenames_once(self):
        """将旧命名报告迁移为新命名规范（尽力而为）。只执行一次。"""
        if getattr(self, "_report_migrated", False):
            return
        self._report_migrated = True
        reports_dir = "reports"
        if not os.path.isdir(reports_dir):
            return
        import re

        def _safe_rename(old_path: str, new_path: str):
            if old_path == new_path:
                return new_path
            base, ext = os.path.splitext(new_path)
            cand = new_path
            idx = 1
            while os.path.exists(cand):
                cand = f"{base}_{idx:02d}{ext}"
                idx += 1
            os.replace(old_path, cand)
            return cand

        for fn in list(os.listdir(reports_dir)):
            if not fn.endswith((".html", ".json")):
                continue
            old_path = os.path.join(reports_dir, fn)
            # 1) report_generator 旧格式：testType_status_sn_pkg_YYYYMMDD_HHMMSS_micro.html
            m = re.match(r"^(?P<type>[^_]+)_(final|intermediate)_(?P<sn>[^_]+)_(?P<pkg>[^_]+)_(?P<ts>\\d{8}_\\d{6})_\\d{6}(?P<ext>\\.(html|json))$", fn)
            if m:
                project = m.group("type")
                sn = (m.group("sn") or "unknown")[:8]
                ts = m.group("ts")
                is_intermediate = "intermediate" in fn
                base = f"{sn}_{project}_{ts}"
                if is_intermediate:
                    base = f"{base}_intermediate"
                new_fn = base + m.group("ext")
                new_path = os.path.join(reports_dir, new_fn)
                try:
                    new_path = _safe_rename(old_path, new_path)
                    # 同步迁移同 basename 的另一种扩展名
                    other_ext = ".json" if new_path.endswith(".html") else ".html"
                    other_old = os.path.join(reports_dir, os.path.splitext(fn)[0] + other_ext)
                    if os.path.exists(other_old):
                        other_new = os.path.splitext(new_path)[0] + other_ext
                        _safe_rename(other_old, other_new)
                except Exception:
                    pass
                continue
            # 2) live_旧格式：live_sn_pkg_ts.html
            m2 = re.match(r"^live_(?P<sn>[^_]+)_[^_]+_(?P<ts>\\d{8}_\\d{6})\\.html$", fn)
            if m2:
                sn = (m2.group("sn") or "unknown")[:8]
                ts = m2.group("ts")
                project = os.environ.get("MONKEYAUTOTEST_PROJECT_KEY", "") or "stability"
                new_fn = f"{sn}_{project}_{ts}_live.html"
                try:
                    _safe_rename(old_path, os.path.join(reports_dir, new_fn))
                except Exception:
                    pass

    def show_reports_window_v2(self):
        """测试报告查看器（详细列表 + 多条件筛选）"""
        if getattr(self, "_reports_viewer_win", None) and self._reports_viewer_win.winfo_exists():
            self._reports_viewer_win.lift()
            self._reports_viewer_win.focus_force()
            return
        self._migrate_report_filenames_once()

        win = tk.Toplevel(self.root)
        self._reports_viewer_win = win
        win.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_reports_viewer_win", None), win.destroy()))
        win.title("测试报告查看器")
        # 适当加宽窗口，避免筛选区与按钮被压缩
        win.geometry("1300x700")
        try:
            win.minsize(1100, 650)
        except Exception:
            pass
        win.configure(bg=UIColors.BG_LIGHT)

        # 筛选区
        filters = tk.Frame(win, bg=UIColors.WHITE, relief="raised", bd=1)
        filters.pack(fill=tk.X, padx=15, pady=(15, 10))

        self._rf_type = tk.StringVar(value="全部")
        self._rf_sn = tk.StringVar(value="")
        self._rf_pkg = tk.StringVar(value="")
        self._rf_status = tk.StringVar(value="全部")
        self._rf_date_from = tk.StringVar(value="")  # YYYYMMDD
        self._rf_date_to = tk.StringVar(value="")    # YYYYMMDD
        # 版本筛选：设备版本（ro.build.display.id）与应用版本（versionName）
        self._rf_device_ver = tk.StringVar(value="")
        self._rf_app_ver = tk.StringVar(value="")

        tk.Label(filters, text="测试项目:", bg=UIColors.WHITE).grid(row=0, column=0, padx=(10, 4), pady=8, sticky="w")
        type_combo = ttk.Combobox(filters, textvariable=self._rf_type, values=["全部"], state="readonly", width=18)
        type_combo.grid(row=0, column=1, padx=(0, 10), pady=8)
        tk.Label(filters, text="设备SN:", bg=UIColors.WHITE).grid(row=0, column=2, padx=(0, 4), pady=8, sticky="w")
        ttk.Entry(filters, textvariable=self._rf_sn, width=14).grid(row=0, column=3, padx=(0, 10), pady=8)
        tk.Label(filters, text="应用包名:", bg=UIColors.WHITE).grid(row=0, column=4, padx=(0, 4), pady=8, sticky="w")
        ttk.Entry(filters, textvariable=self._rf_pkg, width=22).grid(row=0, column=5, padx=(0, 10), pady=8)

        tk.Label(filters, text="状态:", bg=UIColors.WHITE).grid(row=1, column=0, padx=(10, 4), pady=(0, 10), sticky="w")
        ttk.Combobox(filters, textvariable=self._rf_status, values=["全部", "初始", "阶段性", "最终", "实时(进行中)", "实时(已停止)"], state="readonly", width=18).grid(row=1, column=1, padx=(0, 10), pady=(0, 10))
        tk.Label(filters, text="日期从(YYYYMMDD):", bg=UIColors.WHITE).grid(row=1, column=2, padx=(0, 4), pady=(0, 10), sticky="w")
        ttk.Entry(filters, textvariable=self._rf_date_from, width=14).grid(row=1, column=3, padx=(0, 10), pady=(0, 10))
        tk.Label(filters, text="到:", bg=UIColors.WHITE).grid(row=1, column=4, padx=(0, 4), pady=(0, 10), sticky="w")
        ttk.Entry(filters, textvariable=self._rf_date_to, width=10).grid(row=1, column=5, padx=(0, 10), pady=(0, 10), sticky="w")
        tk.Label(filters, text="设备版本:", bg=UIColors.WHITE).grid(row=2, column=0, padx=(10, 4), pady=(0, 10), sticky="w")
        ttk.Entry(filters, textvariable=self._rf_device_ver, width=18).grid(row=2, column=1, padx=(0, 10), pady=(0, 10))
        tk.Label(filters, text="应用版本:", bg=UIColors.WHITE).grid(row=2, column=2, padx=(0, 4), pady=(0, 10), sticky="w")
        ttk.Entry(filters, textvariable=self._rf_app_ver, width=14).grid(row=2, column=3, padx=(0, 10), pady=(0, 10))

        btns = tk.Frame(filters, bg=UIColors.WHITE)
        btns.grid(row=0, column=6, rowspan=2, padx=(0, 10), pady=8, sticky="e")
        self.create_action_button(btns, text="🔄 刷新", command=lambda: _refresh(), variant="success", side=tk.LEFT, padx=(0, 8))
        self.create_action_button(btns, text="📖 打开", command=lambda: _open_selected(), variant="primary", side=tk.LEFT, padx=(0, 8))
        self.create_action_button(btns, text="🗑️ 删除", command=lambda: _delete_selected(), variant="error", side=tk.LEFT, padx=(0, 8))
        self.create_action_button(btns, text="♻ 重构", command=lambda: _refactor_selected(), variant="warning", side=tk.LEFT)

        # 列表区（Treeview）
        body = tk.Frame(win, bg=UIColors.WHITE, relief="raised", bd=1)
        body.pack(fill=tk.BOTH, expand=True, padx=15, pady=(0, 8))

        # 底部使用提示（可发现性增强）
        footer = tk.Frame(win, bg=UIColors.BG_LIGHT)
        footer.pack(fill=tk.X, padx=15, pady=(0, 12))
        hint_text = (
            "支持 Ctrl/Shift 多选；点击「删除」可批量删除；"
            "在上方筛选区可按 SN/包名/状态/日期/版本过滤；双击行或点「打开」查看报告。"
        )
        hint_lbl = tk.Label(
            footer,
            text=hint_text,
            bg=UIColors.BG_LIGHT,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.CAPTION,
            anchor="w",
            justify=tk.LEFT,
            wraplength=1200,
        )
        hint_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
        # 悬浮帮助（内容较多时不占用布局）
        help_lbl = tk.Label(
            footer,
            text="更多帮助",
            bg=UIColors.BG_LIGHT,
            fg=UIColors.PRIMARY,
            font=UIFonts.CAPTION,
            cursor="hand2",
        )
        help_lbl.pack(side=tk.RIGHT, padx=(10, 0))
        ToolTip(
            help_lbl,
            "报告查看器使用说明：\n"
            "- 多选：按住 Ctrl 逐条选择；按住 Shift 选择连续范围\n"
            "- 打开：选中一条后点「📖 打开」或在列表中双击\n"
            "- 删除：支持多选批量删除（谨慎操作，删除不可恢复）\n"
            "- 重构：对旧报告应用最新模板（会生成 .bak 备份）\n"
            "- 筛选：可按 测试项目/设备SN/包名/状态/日期范围/设备版本/应用版本 过滤\n"
            "- 已运行时间：优先从伴生 JSON 的 start/end_time 计算，缺失时会尝试从 HTML 解析",
            delay=300,
        )

        # 增加“已运行时间”列
        columns = ("project", "sn", "device_ver", "pkg", "app_ver", "status", "runtime", "time", "size", "file")
        tree = ttk.Treeview(body, columns=columns, show="headings", height=18, selectmode="extended")
        tree.heading("project", text="测试项目")
        tree.heading("sn", text="设备SN")
        tree.heading("device_ver", text="设备版本")
        tree.heading("pkg", text="应用包名")
        tree.heading("app_ver", text="应用版本")
        tree.heading("status", text="状态")
        tree.heading("runtime", text="已运行时间")
        tree.heading("time", text="时间")
        tree.heading("size", text="大小")
        tree.heading("file", text="文件名")

        # 计算“8 个字符”对应的大致像素宽度，作为各列默认宽度上限
        try:
            base_font = tkfont.nametofont(tree.cget("font"))
            char8_width = base_font.measure("中" * 8)
        except Exception:
            # 兜底：给一个相对保守的默认宽度
            char8_width = 120

        # 大部分列默认宽度约为 8 个字符，文件名/包名等信息列适当放大一些，
        # 用户仍可手动拖拽列宽查看更多内容。
        tree.column("project", width=char8_width, anchor="w", stretch=True)
        tree.column("sn", width=int(char8_width * 0.8), anchor="w", stretch=True)
        tree.column("device_ver", width=char8_width, anchor="w", stretch=True)
        tree.column("pkg", width=int(char8_width * 1.5), anchor="w", stretch=True)
        tree.column("app_ver", width=char8_width, anchor="w", stretch=True)
        tree.column("status", width=int(char8_width * 0.9), anchor="w", stretch=True)
        tree.column("runtime", width=char8_width, anchor="w", stretch=True)
        tree.column("time", width=char8_width, anchor="w", stretch=True)
        tree.column("size", width=int(char8_width * 0.8), anchor="e", stretch=True)
        tree.column("file", width=int(char8_width * 1.5), anchor="w", stretch=True)

        vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=10)

        # iid -> report path
        file_map = {}

        def _parse_new_name(filename: str):
            import re
            # 支持 project 含下划线，如 robustness_only_test
            m = re.match(r"^(?P<sn>[^_]+)_(?P<project>.+)_(?P<date>\d{8})_(?P<time>\d{6})(?P<suffix>_(?:live|intermediate))?\.html$", filename)
            if not m:
                return None
            sn = m.group("sn")
            project = m.group("project")
            dt = f"{m.group('date')}_{m.group('time')}"
            suffix = m.group("suffix") or ""
            return sn, project, dt, suffix

        def _get_status_from_html(path: str):
            """仅基于 HTML 内容的回退状态解析（兼容旧报告）"""
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(4096)
                if "实时报告（已停止）" in head:
                    return "实时(已停止)"
                if "实时报告（测试进行中）" in head:
                    return "实时(进行中)"
                if "初始报告" in head:
                    return "初始"
            except Exception:
                pass
            return "最终"

        def _read_report_metadata_from_json(html_path: str):
            """从报告伴生 JSON 读取 device_sn / package_name / project_key / report_status / 版本信息。"""
            json_path = os.path.splitext(html_path)[0] + ".json"
            if not os.path.exists(json_path):
                return {}
            try:
                with open(json_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                meta = {}
                detailed = data.get("detailed_results") if isinstance(data.get("detailed_results"), dict) else {}
                dev = (data.get("device_info") or detailed.get("device_info") or {})
                pkg = (data.get("package_info") or detailed.get("package_info") or {})
                m = (data.get("metadata") or {})
                meta["sn"] = dev.get("sn", "")
                meta["pkg"] = pkg.get("name", "")
                meta["project"] = m.get("project_key", "")
                meta["report_status"] = m.get("report_status", "")
                # 版本信息：优先使用 metadata 中预计算的字段，其次回退到 device_info / package_info
                meta["device_version"] = m.get("device_version") or dev.get("build_display_id") or dev.get("os", "")
                meta["app_version"] = m.get("app_version") or pkg.get("version_name", "")
                # 运行时间相关字段：尽力从最终报告结构中提取 start/end_time
                if detailed:
                    meta["start_time"] = detailed.get("start_time")
                    meta["end_time"] = detailed.get("end_time") or m.get("generated_at")
                return meta
            except Exception:
                return {}

        def _compute_runtime_str_from_meta(jmeta: dict, fallback_time: str) -> str:
            """基于 JSON 元数据的 start/end_time 计算已运行时间；失败时返回 '-'。"""
            from datetime import datetime as _dt
            if not isinstance(jmeta, dict):
                return "-"
            start = jmeta.get("start_time")
            end = jmeta.get("end_time") or jmeta.get("generated_at") or fallback_time
            if not start or not end:
                return "-"
            try:
                s = _dt.fromisoformat(str(start).replace("Z", "+00:00"))
                e = _dt.fromisoformat(str(end).replace("Z", "+00:00"))
                if s.tzinfo:
                    s = s.replace(tzinfo=None)
                if e.tzinfo:
                    e = e.replace(tzinfo=None)
            except Exception:
                return "-"
            if e <= s:
                return "0小时0分钟"
            delta = e - s
            seconds = int(delta.total_seconds())
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}小时{minutes}分钟"

        def _get_runtime_from_html(path: str) -> str:
            """从统一/实时报告 HTML 中解析“已运行时间”一行。"""
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(8192)
            except Exception:
                return "-"
            import re as _re
            m = _re.search(r"<td>已运行时间</td><td>([^<]+)</td>", head)
            if m:
                text = m.group(1).strip()
                return text or "-"
            return "-"

        def _map_status_from_metadata(jmeta: dict, suffix: str, path: str) -> str:
            """基于 JSON 元数据优先判定报告状态，文件名/HTML 作为回退。"""
            code = (jmeta.get("report_status") or "").lower()
            if code == "initial":
                return "初始"
            if code == "intermediate":
                return "阶段性"
            if code == "final":
                return "最终"
            if code == "live":
                return "实时(进行中)"
            if code == "stopped":
                return "实时(已停止)"

            # 若无有效状态码，则按文件名后缀与 HTML 内容回退
            if suffix == "_intermediate":
                return "阶段性"
            if suffix == "_live":
                return _get_status_from_html(path)
            # 无后缀：尝试从 HTML 判断是否为实时/初始
            return _get_status_from_html(path)

        def _refresh():
            # 清空
            for iid in tree.get_children():
                tree.delete(iid)
            file_map.clear()

            reports_dir = "reports"
            if not os.path.isdir(reports_dir):
                return

            # 收集
            items = []
            for fn in os.listdir(reports_dir):
                if not fn.endswith(".html"):
                    continue
                info = _parse_new_name(fn)
                path = os.path.join(reports_dir, fn)
                mtime = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S")
                size_kb = int(os.path.getsize(path) / 1024)
                jmeta = _read_report_metadata_from_json(path)
                if info:
                    sn, project, dt, suffix = info
                    status = _map_status_from_metadata(jmeta, suffix, path)
                    date_val = dt.split("_")[0]
                else:
                    # 旧/未知命名：仍显示在列表中，其余字段尽量从 JSON/HTML 推断
                    sn = "unknown"
                    project = "unknown"
                    status = _map_status_from_metadata(jmeta, suffix="", path=path)
                    date_val = mtime.split(" ")[0].replace("-", "")

                pkg = jmeta.get("pkg") or ""
                device_ver = jmeta.get("device_version") or ""
                app_ver = jmeta.get("app_version") or ""
                # 运行时间：优先用 JSON 中的 start/end_time 计算；否则从 HTML 中解析
                runtime_str = _compute_runtime_str_from_meta(jmeta, mtime)
                if runtime_str == "-":
                    runtime_str = _get_runtime_from_html(path)
                items.append({
                    "project": project,
                    "sn": sn,
                    "device_version": device_ver,
                    "pkg": pkg,
                    "app_version": app_ver,
                    "status": status,
                    "runtime": runtime_str,
                    "time": mtime,
                    "size": f"{size_kb}KB",
                    "file": fn,
                    "path": path,
                    "date": date_val,
                })

            # 填充测试项目下拉候选
            try:
                projects = sorted(set([i["project"] for i in items if i.get("project")]))
                proj_values = ["全部"] + projects
                type_combo["values"] = proj_values
            except Exception:
                pass

            # 过滤
            t_project = (self._rf_type.get() or "").strip()
            t_sn = (self._rf_sn.get() or "").strip().lower()
            t_pkg = (self._rf_pkg.get() or "").strip().lower()
            t_status = (self._rf_status.get() or "").strip()
            d_from = (self._rf_date_from.get() or "").strip()
            d_to = (self._rf_date_to.get() or "").strip()
            t_dev_ver = (self._rf_device_ver.get() or "").strip().lower()
            t_app_ver = (self._rf_app_ver.get() or "").strip().lower()

            def _in_range(d: str) -> bool:
                if d_from and d < d_from:
                    return False
                if d_to and d > d_to:
                    return False
                return True

            filtered = []
            for i in items:
                if t_project and t_project != "全部" and i["project"] != t_project:
                    continue
                if t_status and t_status != "全部" and i["status"] != t_status:
                    continue
                if t_sn and t_sn not in (i["sn"] or "").lower():
                    continue
                if t_pkg and t_pkg not in (i["pkg"] or "").lower():
                    continue
                if t_dev_ver and t_dev_ver not in (i.get("device_version") or "").lower():
                    continue
                if t_app_ver and t_app_ver not in (i.get("app_version") or "").lower():
                    continue
                if not _in_range(i.get("date", "")):
                    continue
                filtered.append(i)

            # 时间倒序
            filtered.sort(key=lambda x: x.get("time", ""), reverse=True)

            for idx, i in enumerate(filtered):
                iid = f"r{idx}"
                tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        i["project"],
                        i["sn"],
                        i.get("device_version", ""),
                        i["pkg"],
                        i.get("app_version", ""),
                        i["status"],
                        i.get("runtime", "-"),
                        i["time"],
                        i["size"],
                        i["file"],
                    ),
                )
                file_map[iid] = i["path"]

        def _selected_paths():
            """返回所有选中报告的文件路径列表"""
            sel = tree.selection()
            paths = []
            for iid in sel:
                p = file_map.get(iid)
                if p:
                    paths.append(p)
            return paths

        def _open_selected():
            paths = _selected_paths()
            if not paths:
                messagebox.showwarning("提示", "请先选择至少一条报告", parent=win)
                return
            try:
                import webbrowser
                for path in paths:
                    webbrowser.open(os.path.abspath(path))
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def _delete_selected():
            paths = _selected_paths()
            if not paths:
                messagebox.showwarning("提示", "请先选择至少一条报告", parent=win)
                return
            if len(paths) == 1:
                msg = f"确定删除报告文件？\n{os.path.basename(paths[0])}"
            else:
                msg = f"确定删除选中的 {len(paths)} 个报告文件？"
            if not messagebox.askyesno("确认删除", msg, parent=win):
                return
            try:
                for path in paths:
                    base = os.path.splitext(path)[0]
                    for ext in (".html", ".json"):
                        p = base + ext
                        if os.path.exists(p):
                            os.remove(p)
                _refresh()
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def _refactor_selected():
            paths = [p for p in _selected_paths() if p.lower().endswith(".html")]
            if not paths:
                messagebox.showwarning("提示", "请先选择至少一条 HTML 报告", parent=win)
                return
            self._do_refactor_reports(paths, parent=win)

        _refresh()

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
        
        # 初始化报告文件映射字典（用于存储索引到文件名的映射，因为Listbox不支持tags）
        self.report_file_map = {}

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
            text="🗑️ 删除报告",
            command=self.delete_selected_report,
            variant="error",
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

        self.create_action_button(
            buttons_frame,
            text="♻ 重构报告",
            command=self.refactor_selected_report,
            variant="warning",
            side=tk.LEFT,
            padx=(10, 0),
        )

        # 初始刷新报告列表
        self.refresh_reports()

    def refactor_selected_report(self):
        """重构旧版报告选项卡中选中的单个报告"""
        selection = self.reports_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个报告文件")
            return
        index = selection[0]
        report_file = self.report_file_map.get(index)
        if not report_file:
            display_text = self.reports_listbox.get(index)
            report_file = display_text.split("|")[-1].strip() if "|" in display_text else display_text.strip()
        if not report_file:
            messagebox.showerror("错误", "无法获取报告文件名")
            return
        # 仅支持 HTML 报告，若选中 JSON，则尝试映射到同名 HTML
        if report_file.lower().endswith(".json"):
            base = os.path.splitext(report_file)[0]
            html_candidate = base + ".html"
            html_path = os.path.join("reports", html_candidate)
            if not os.path.exists(html_path):
                messagebox.showwarning("提示", "仅支持重构 HTML 报告，请选择 .html 文件")
                return
            report_file = html_candidate
        elif not report_file.lower().endswith(".html"):
            messagebox.showwarning("提示", "仅支持重构 HTML 报告，请选择 .html 文件")
            return

        report_path = os.path.join("reports", report_file)
        if not os.path.exists(report_path):
            messagebox.showerror("错误", "报告文件不存在: %s" % report_file)
            return

        self._do_refactor_reports([report_path], parent=self.root)

    def on_version_selected(self, event=None):
        """测试模块选择事件：同步 key、加载模块、更新模块说明（方案 C）"""
        name = self.version_display_var.get()
        key = self._version_name_to_key(name)
        if key:
            self.version_var.set(key)
        version = self.version_var.get()
        if version in self.project_config:
            config = self.project_config[version]
            if "modular_config" in config:
                enabled_modules = config["modular_config"].get("enabled_modules", [])
                self.update_module_selection(enabled_modules)
            self.log_info_ui(f"已选择测试模块: {config.get('name', version)}")
        self._update_module_description()

    def on_test_mode_changed(self, *args):
        """测试模式变化事件处理（测试模式已移除，保留以兼容配置加载，确保模块选择可用）"""
        modules_frame = getattr(self, "modules_frame", None)
        if modules_frame is not None:
            try:
                if not modules_frame.winfo_exists():
                    modules_frame = None
                    self.modules_frame = None
            except Exception:
                modules_frame = None
                self.modules_frame = None
        if modules_frame:
            for child in modules_frame.winfo_children():
                try:
                    child.config(state='normal')
                except Exception:
                    pass
        if hasattr(self, 'preset_combos_widget'):
            try:
                self.preset_combos_widget.config(state='readonly')
            except Exception:
                pass
        self._update_preset_combo_display()

    def on_duration_preset_changed(self, event=None):
        """
        测试方案（预设时长）选择变化：
        - 更新界面说明文字
        - 同步到底层 duration_var / duration_unit_var（供 run_stability_test 复用）
        """
        preset = (getattr(self, "duration_preset_var", None).get() or "").strip() if hasattr(self, "duration_preset_var") else ""

        preset_map = {
            "快速测试（30分钟）": ("30", "分钟", "快速测试：约30分钟，适合冒烟验证/快速回归。"),
            "标准测试（2小时）": ("2", "小时", "标准测试：约2小时，适合日常回归与基础稳定性验证。"),
            "深度测试（6小时）": ("6", "小时", "深度测试：约6小时，适合较充分覆盖与问题复现。"),
            "长期压力测试（12小时）": ("12", "小时", "长期压力：约12小时，适合压力与稳定性验证。"),
            "持久稳定性测试（24小时）": ("24", "小时", "持久稳定：约24小时，适合长时间稳定性监控。"),
        }

        # 兜底：如果配置里写了旧值/自定义值，保持不改动底层数值
        if preset not in preset_map:
            if hasattr(self, "duration_preset_desc_label") and self.duration_preset_desc_label is not None:
                try:
                    self.duration_preset_desc_label.config(text="")
                except Exception:
                    pass
            return

        dur, unit, desc = preset_map[preset]
        try:
            self.duration_var.set(dur)
        except Exception:
            pass
        try:
            self.duration_unit_var.set(unit)
        except Exception:
            pass

        if hasattr(self, "duration_preset_desc_label") and self.duration_preset_desc_label is not None:
            try:
                self.duration_preset_desc_label.config(text=desc)
            except Exception:
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
        
        # 更新预设组合选择框显示
        self._update_preset_combo_display()

    def on_preset_combo_selected(self, event=None):
        """处理预设组合选择"""
        preset_name = self.preset_combos_var.get()
        if preset_name == "自定义":
            return  # 不改变当前选择
        
        # 先检查是否是保存的自定义组合
        saved_combo = self._load_saved_combo(preset_name)
        if saved_combo:
            enabled_modules = saved_combo.get('enabled_modules', [])
            # 重置所有模块
            for var in self.module_vars.values():
                var.set(False)
            # 启用保存的模块
            for module in enabled_modules:
                if module in self.module_vars:
                    self.module_vars[module].set(True)
            return
        
        # 根据预设名称设置模块
        preset_configs = {
            "完整测试套件（全部模块）": {
                'monkey_stress': True,
                'exception_recovery': True,
                'performance_all': True,
                'performance_response': False,
            },
            "仅 Monkey 压力测试": {
                'monkey_stress': True,
                'exception_recovery': False,
                'performance_all': False,
                'performance_response': False,
            },
            "仅异常恢复": {
                'monkey_stress': False,
                'exception_recovery': True,
                'performance_all': False,
                'performance_response': False,
            },
            "仅性能测试（完整）": {
                'monkey_stress': False,
                'exception_recovery': False,
                'performance_all': True,
                'performance_response': False,
            },
            "仅响应性能": {
                'monkey_stress': False,
                'exception_recovery': False,
                'performance_all': False,
                'performance_response': True,
            },
            "Monkey 压力+异常恢复": {
                'monkey_stress': True,
                'exception_recovery': True,
                'performance_all': False,
                'performance_response': False,
            },
            "Monkey 压力+性能测试": {
                'monkey_stress': True,
                'exception_recovery': False,
                'performance_all': True,
                'performance_response': False,
            }
        }
        
        if preset_name in preset_configs:
            config = preset_configs[preset_name]
            for module_key, enabled in config.items():
                if module_key in self.module_vars:
                    self.module_vars[module_key].set(enabled)

    def on_module_selection_changed(self):
        """模块选择变化时的回调，更新预设组合显示"""
        self._update_preset_combo_display()

    def _update_preset_combo_display(self):
        """根据当前模块选择更新预设组合显示"""
        try:
            # 获取当前选中的模块
            current_selection = {
                'monkey_stress': self.module_vars['monkey_stress'].get(),
                'exception_recovery': self.module_vars['exception_recovery'].get(),
                'performance_all': self.module_vars['performance_all'].get(),
                'performance_response': self.module_vars['performance_response'].get(),
            }
            
            # 检查是否匹配预设组合
            preset_configs = {
                "完整测试套件（全部模块）": {
                    'monkey_stress': True,
                    'exception_recovery': True,
                    'performance_all': True,
                    'performance_response': False,
                },
                "仅 Monkey 压力测试": {
                    'monkey_stress': True,
                    'exception_recovery': False,
                    'performance_all': False,
                    'performance_response': False,
                },
                "仅异常恢复": {
                    'monkey_stress': False,
                    'exception_recovery': True,
                    'performance_all': False,
                    'performance_response': False,
                },
                "仅性能测试（完整）": {
                    'monkey_stress': False,
                    'exception_recovery': False,
                    'performance_all': True,
                    'performance_response': False,
                },
                "仅响应性能": {
                    'monkey_stress': False,
                    'exception_recovery': False,
                    'performance_all': False,
                    'performance_response': True,
                },
                "Monkey 压力+异常恢复": {
                    'monkey_stress': True,
                    'exception_recovery': True,
                    'performance_all': False,
                    'performance_response': False,
                },
                "Monkey 压力+性能测试": {
                    'monkey_stress': True,
                    'exception_recovery': False,
                    'performance_all': True,
                    'performance_response': False,
                }
            }
            
            # 检查是否完全匹配某个预设
            for preset_name, preset_config in preset_configs.items():
                if current_selection == preset_config:
                    if hasattr(self, 'preset_combos_var'):
                        self.preset_combos_var.set(preset_name)
                    return
            
            # 检查是否匹配保存的自定义组合
            config_path = self._get_test_ui_config_path()
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                        config = json.load(f)
                        saved_combos = config.get('saved_module_combos', {})
                        for combo_name, combo_config in saved_combos.items():
                            saved_modules = combo_config.get('enabled_modules', [])
                            saved_selection = {key: key in saved_modules for key in self.module_vars.keys()}
                            if current_selection == saved_selection:
                                if hasattr(self, 'preset_combos_var'):
                                    self.preset_combos_var.set(combo_name)
                                return
                except Exception:
                    pass
            
            # 不匹配任何预设，显示为"自定义"
            if hasattr(self, 'preset_combos_var'):
                self.preset_combos_var.set("自定义")
        except Exception as e:
            logging.debug(f"更新预设组合显示失败: {e}")

    def save_current_module_combo(self):
        """保存当前模块组合为自定义配置"""
        enabled_modules = [key for key, var in self.module_vars.items() if var.get()]
        if not enabled_modules:
            messagebox.showwarning("警告", "请至少选择一个测试模块")
            return
        
        # 获取自定义名称
        combo_name = simpledialog.askstring(
            "保存模块组合",
            "请输入组合名称:",
            initialvalue=f"自定义组合_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        if not combo_name:
            return
        
        # 保存到配置文件
        try:
            config_path = self._get_test_ui_config_path()
            config = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                        config = json.load(f)
                except Exception:
                    pass
            
            if 'saved_module_combos' not in config:
                config['saved_module_combos'] = {}
            
            config['saved_module_combos'][combo_name] = {
                'enabled_modules': enabled_modules,
                'created_at': datetime.now().isoformat()
            }
            
            with open(config_path, 'w', encoding='utf-8', errors='replace') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            # 更新下拉框选项
            self._refresh_preset_combos()
            
            messagebox.showinfo("成功", f"模块组合 '{combo_name}' 已保存")
            self.log_info_ui(f"已保存模块组合: {combo_name}")
        except Exception as e:
            messagebox.showerror("错误", f"保存模块组合失败: {str(e)}")
            logging.error(f"保存模块组合失败: {e}")

    def _load_saved_combo(self, combo_name):
        """加载保存的自定义组合"""
        try:
            config_path = self._get_test_ui_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                    config = json.load(f)
                    saved_combos = config.get('saved_module_combos', {})
                    return saved_combos.get(combo_name)
        except Exception as e:
            logging.debug(f"加载保存的组合失败: {e}")
        return None

    def _refresh_preset_combos(self):
        """刷新预设组合下拉框，加载保存的自定义组合"""
        try:
            if not hasattr(self, 'preset_combos_var') or not hasattr(self, 'preset_combos_widget'):
                return
            
            # 基础预设组合
            base_combos = [
                "自定义",
                "完整测试套件（全部模块）",
                "仅 Monkey 压力测试",
                "仅异常恢复",
                "仅性能测试（完整）",
                "仅响应性能",
                "Monkey 压力+异常恢复",
                "Monkey 压力+性能测试"
            ]
            
            # 加载保存的自定义组合
            saved_combos = []
            config_path = self._get_test_ui_config_path()
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                        config = json.load(f)
                        saved_combos = list(config.get('saved_module_combos', {}).keys())
                except Exception:
                    pass
            
            # 合并选项（自定义组合放在分隔线后）
            if saved_combos:
                all_combos = base_combos + ["---"] + saved_combos
            else:
                all_combos = base_combos
            
            # 更新下拉框
            self.preset_combos_widget['values'] = all_combos
        except Exception as e:
            logging.debug(f"刷新预设组合失败: {e}")

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

    def _version_name_to_key(self, name):
        """根据下拉显示的名称取回 project.json 中的 config key"""
        if not name:
            return ""
        for k, cfg in getattr(self, "project_config", {}).items():
            if cfg.get("name") == name:
                return k
        return name if name in getattr(self, "project_config", {}) else ""

    def _update_module_description(self):
        """方案 C：根据当前选中的测试模块更新模块说明只读区"""
        try:
            desc_widget = getattr(self, "module_description_text", None)
            if not desc_widget or not desc_widget.winfo_exists():
                return
            key = self.version_var.get()
            if not key:
                key = self._version_name_to_key(self.version_display_var.get())
            config = getattr(self, "project_config", {}).get(key, {})
            desc = config.get("description", "")
            desc_widget.config(state=tk.NORMAL)
            desc_widget.delete(1.0, tk.END)
            desc_widget.insert(tk.END, desc or "（无说明）")
            desc_widget.config(state=tk.DISABLED)
        except Exception:
            pass

    def _on_app_type_changed(self):
        """应用类型切换（系统/普通）；包名始终用于已安装应用测试"""
        self._update_app_info_label()

    def refresh_installed_apps(self):
        """扫描设备上已安装应用包名（包含系统应用），填充到包名下拉"""
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
            # 需求：下拉框需要展示所有已安装包名（包含系统应用），因此默认扫描全部包名。
            # 若设备/ROM 执行 `pm list packages` 超时或异常，再回退为（第三方 -3 + 系统 -s）的并集。
            def _run_pm_list(extra_args):
                return subprocess.run(
                    [*adb_cmd, "-s", sn, "shell", "pm", "list", "packages", *extra_args],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60
                )

            pkgs = []
            result = _run_pm_list([])
            if getattr(result, "returncode", 0) == 0:
                for ln in (result.stdout or "").splitlines():
                    ln = ln.strip()
                    if ln.startswith("package:"):
                        pkgs.append(ln.split("package:", 1)[1].strip())
            else:
                # 如果adb命令失败，给出更明确提示（stderr里通常包含 unauthorized/offline/no devices 等）
                err = (result.stderr or "").strip() or (result.stdout or "").strip() or f"adb返回码: {result.returncode}"
                logging.warning(f"扫描全部包名失败，尝试回退扫描（-3 + -s）：{err}")

            # 回退：第三方 + 系统（并集）
            if not pkgs:
                for extra in (["-3"], ["-s"]):
                    r = _run_pm_list(extra)
                    if getattr(r, "returncode", 0) != 0:
                        continue
                    for ln in (r.stdout or "").splitlines():
                        ln = ln.strip()
                        if ln.startswith("package:"):
                            pkgs.append(ln.split("package:", 1)[1].strip())

            if not pkgs:
                self._installed_packages_cache = []
                self._update_app_info_label(error="扫描失败：未获取到任何包名（请确认设备已连接且已授权）")
                return

            pkgs = sorted(set([p for p in pkgs if p]))
            # pinned_packages 置顶（仅对当前已安装包生效）
            try:
                pinned = [p for p in (self.pinned_packages or []) if p in pkgs]
                pinned_set = set(pinned)
                rest = [p for p in pkgs if p not in pinned_set]
                pkgs = pinned + rest
            except Exception:
                pass
            self._installed_packages_cache = pkgs
            self._installed_packages_all = pkgs[:]
            if self.package_combo and self.package_combo.winfo_exists():
                self.package_combo["values"] = pkgs
                # 若用户正在输入筛选，刷新 values 后重新应用筛选
                self._apply_package_filter((self.package_name_var.get() or "").strip())
            self._update_app_info_label()
        except Exception as e:
            self._installed_packages_cache = []
            self._installed_packages_all = []
            self._update_app_info_label(error=str(e))

    def _on_package_selected(self, _event=None):
        self._update_app_info_label()

    def _on_package_filter_focus_in(self, _event=None):
        # 聚焦时若无筛选文本，确保 values 为全量列表
        try:
            if self.package_combo and self.package_combo.winfo_exists():
                if not (self.package_name_var.get() or "").strip():
                    self.package_combo["values"] = self._installed_packages_all or self._installed_packages_cache or []
        except Exception:
            pass

    def _on_package_filter_keyrelease(self, _event=None):
        """包名下拉框输入筛选：输入片段（如 llm）仅展示包含该片段的包名。"""
        text = (self.package_name_var.get() or "").strip()
        self._apply_package_filter(text)

    def _apply_package_filter(self, text: str):
        try:
            if not (self.package_combo and self.package_combo.winfo_exists()):
                return
            all_pkgs = self._installed_packages_all or self._installed_packages_cache or []
            t = (text or "").strip().lower()
            if not t:
                self.package_combo["values"] = all_pkgs
                return
            filtered = [p for p in all_pkgs if t in (p or "").lower()]
            self.package_combo["values"] = filtered
        except Exception:
            pass

    def _pin_packages(self, packages):
        """将包名加入 pinned_packages（置顶），并立即落盘到 test_ui_config.json。"""
        try:
            if not isinstance(packages, list):
                packages = [packages]
            pkgs = []
            for p in packages:
                p = (p or "").strip()
                if p:
                    pkgs.append(p)
            if not pkgs:
                return
            existing = list(self.pinned_packages or [])
            seen = set()
            new_list = []
            # 新包置顶（按传入顺序）
            for p in pkgs:
                if p in seen:
                    continue
                seen.add(p)
                new_list.append(p)
            # 保留旧的（去重）
            for p in existing:
                if p in seen:
                    continue
                seen.add(p)
                new_list.append(p)
            self.pinned_packages = new_list
            # 立即同步配置（保证“安装后自动置顶”持久化）
            try:
                self.save_test_ui_config()
            except Exception:
                self._schedule_autosave()
        except Exception:
            pass

    def _on_install_apk_clicked(self):
        """安装APK：多选文件，按当前「应用类型」执行普通安装或系统安装（含 root+remount+push+重启）"""
        from tkinter import filedialog
        try:
            from utils import app_installer
        except ImportError:
            messagebox.showerror("❌ 错误", "未找到 utils.app_installer 模块")
            return
        ok, msg = self.validate_selected_device((self.device_sn_var.get() or "").strip())
        if not ok:
            messagebox.showerror("❌ 设备不可用", msg)
            return
        self._ensure_adb_env()
        paths = filedialog.askopenfilenames(
            title="选择 APK 文件（可多选）",
            filetypes=[("APK 文件", "*.apk"), ("所有文件", "*.*")]
        )
        if not paths:
            return
        paths = [p for p in paths if p and os.path.isfile(p)]
        if not paths:
            messagebox.showwarning("未选择文件", "请选择有效的 APK 文件")
            return
        adb_cmd = self._get_adb_cmd()
        if not adb_cmd:
            messagebox.showerror("❌ 错误", "未找到 adb，请配置 ADB 路径")
            return
        sn = (self.device_sn_var.get() or "").strip()
        is_system = self.app_type_var.get() == "system"

        if is_system:
            if not messagebox.askyesno(
                "确认系统应用安装",
                "系统应用安装将执行：root → remount → 推送至 /vendor/app/<包名>/ → 重启设备。\n设备会重启，请保存工作。是否继续？"
            ):
                return

            # 后台执行，避免主线程冻结
            try:
                import threading
                import tkinter as _tk
                from tkinter import ttk as _ttk
            except Exception:
                threading = None  # type: ignore

            win = tk.Toplevel(self.root)
            win.title("系统应用安装中…")
            win.configure(bg=UIColors.BG_LIGHT)
            win.geometry("520x220")
            win.resizable(False, False)
            try:
                win.transient(self.root)
                win.grab_set()
            except Exception:
                pass

            title = tk.Label(win, text="正在安装系统应用（后台执行）", bg=UIColors.BG_LIGHT, fg=UIColors.TEXT_PRIMARY, font=UIFonts.SUBTITLE)
            title.pack(anchor="w", padx=16, pady=(16, 6))
            status_var = tk.StringVar(value="准备开始…")
            status_lbl = tk.Label(win, textvariable=status_var, bg=UIColors.BG_LIGHT, fg=UIColors.TEXT_SECONDARY, font=UIFonts.BODY, wraplength=480, justify=tk.LEFT)
            status_lbl.pack(anchor="w", padx=16, pady=(0, 10))
            bar = _ttk.Progressbar(win, mode="indeterminate")
            bar.pack(fill="x", padx=16, pady=(0, 10))
            bar.start(10)

            hint = tk.Label(
                win,
                text="提示：该过程包含 root/remount/push/reboot/等待上线，期间设备会重启。",
                bg=UIColors.BG_LIGHT,
                fg=UIColors.TEXT_SECONDARY,
                font=UIFonts.CAPTION,
                wraplength=480,
                justify=tk.LEFT,
            )
            hint.pack(anchor="w", padx=16, pady=(0, 12))

            def _set_status(text: str):
                # 线程安全更新窗口文案 + 状态栏
                try:
                    self.root.after(0, lambda: status_var.set(str(text)))
                except Exception:
                    pass
                self.update_status(text)

            def _finish(success: bool, err_msg: str):
                def _ui_done():
                    try:
                        bar.stop()
                    except Exception:
                        pass
                    try:
                        win.grab_release()
                    except Exception:
                        pass
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    if success:
                        # 解析安装包名并置顶
                        try:
                            from utils import Package
                            installed_pkgs = []
                            installed_desc = []
                            for p in paths:
                                try:
                                    pkg = Package(p)
                                    if pkg.name:
                                        installed_pkgs.append(pkg.name)
                                        label = pkg.app_label or os.path.basename(p)
                                        installed_desc.append(f"{label} ({pkg.name})")
                                except Exception:
                                    continue
                            if installed_pkgs:
                                self._pin_packages(installed_pkgs)
                                self.log_info_ui("系统应用安装成功（已重启）： " + ", ".join(installed_desc))
                        except Exception:
                            pass
                        messagebox.showinfo("安装完成", "系统应用已推送并已重启设备，请等待设备就绪后使用。")
                        # 刷新设备列表可能耗时，放到后台
                        try:
                            threading.Thread(target=self.refresh_devices, daemon=True).start()
                        except Exception:
                            self.refresh_devices()
                    else:
                        messagebox.showerror("❌ 系统应用安装失败", err_msg or "未知错误")
                try:
                    self.root.after(0, _ui_done)
                except Exception:
                    _ui_done()

            def _worker():
                try:
                    _set_status("开始系统应用安装…")
                    success, err_msg = app_installer.system_install(
                        adb_cmd, sn, paths,
                        status_callback=lambda t: _set_status(t),
                        reboot_timeout=120,
                    )
                    _finish(bool(success), err_msg or "")
                except Exception as e:
                    _finish(False, str(e))

            try:
                if threading is None:
                    raise RuntimeError("threading 不可用")
                threading.Thread(target=_worker, daemon=True).start()
            except Exception:
                # 兜底：若线程不可用则同步执行（保持功能可用）
                _worker()
        else:
            success, err_msg = app_installer.normal_install(adb_cmd, sn, paths)
            if success:
                # 解析安装包名与应用名，并置顶
                try:
                    from utils import Package
                    installed_pkgs = []
                    installed_desc = []
                    for p in paths:
                        try:
                            pkg = Package(p)
                            if pkg.name:
                                installed_pkgs.append(pkg.name)
                                label = pkg.app_label or os.path.basename(p)
                                installed_desc.append(f"{label} ({pkg.name})")
                        except Exception:
                            continue
                    if installed_pkgs:
                        self._pin_packages(installed_pkgs)
                        self.log_info_ui("安装成功： " + ", ".join(installed_desc))
                    else:
                        self.update_status("已安装：%s" % ", ".join(os.path.basename(p) for p in paths))
                except Exception:
                    self.update_status("已安装：%s" % ", ".join(os.path.basename(p) for p in paths))
                self.refresh_installed_apps()
            else:
                messagebox.showerror("❌ 安装失败", err_msg)

    def _on_uninstall_app_clicked(self):
        """卸载当前选中的已安装应用"""
        ok, msg = self.validate_selected_device((self.device_sn_var.get() or "").strip())
        if not ok:
            messagebox.showerror("❌ 设备不可用", msg)
            return
        pkg = (self.package_name_var.get() or "").strip()
        if not pkg:
            messagebox.showwarning("未选择包名", "请先在「包名」下拉框选择要卸载的应用（可先点击「扫描」）")
            return
        if not messagebox.askyesno("确认卸载", f"确定要卸载应用 {pkg} 吗？"):
            return
        self._ensure_adb_env()
        adb_cmd = self._get_adb_cmd()
        if not adb_cmd:
            messagebox.showerror("❌ 错误", "未找到 adb，请配置 ADB 路径")
            return
        sn = (self.device_sn_var.get() or "").strip()
        try:
            from utils import app_installer
            success, err_msg = app_installer.uninstall(adb_cmd, sn, pkg)
            if success:
                self.update_status(f"已卸载：{pkg}")
                self.package_name_var.set("")
                self.refresh_installed_apps()
            else:
                messagebox.showerror("卸载失败", err_msg or "未知错误")
        except ImportError:
            # 兜底：直接 adb uninstall
            r = subprocess.run([*adb_cmd, "-s", sn, "uninstall", pkg], capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                messagebox.showerror("卸载失败", r.stderr or r.stdout or "未知错误")
            else:
                self.update_status(f"已卸载：{pkg}")
                self.package_name_var.set("")
                self.refresh_installed_apps()
        except Exception as e:
            messagebox.showerror("卸载异常", str(e))

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
            r = subprocess.run(
                [*adb_cmd, "-s", sn, "shell", "pm", "path", pkg],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "package:" not in (r.stdout or ""):
                return {"missing": True}
            r2 = subprocess.run(
                [*adb_cmd, "-s", sn, "shell", "dumpsys", "package", pkg],
                capture_output=True,
                text=True,
                timeout=5,
            )
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

        sn = (self.device_sn_var.get() or "").strip()
        pkg = (self.package_name_var.get() or "").strip()
        if not pkg:
            self._app_info_label.config(text="应用：未选择包名（请扫描已安装应用）", fg=UIColors.TEXT_SECONDARY)
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

    def refresh_devices(self):
        """刷新设备列表（手动按钮/自动轮询都会调用）"""
        try:
            adb_cmd = self._get_adb_cmd()
            if not adb_cmd:
                raise FileNotFoundError("未找到 adb（请在“ADB路径”选择 adb.exe，或将 adb 加入 PATH）")
            result = subprocess.run(
                [*adb_cmd, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=5,
            )
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

            # 联动刷新应用信息（扫描已安装包名）
            self.refresh_installed_apps()

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
                result = subprocess.run(
                    [*adb_cmd, "devices", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
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

    def _start_report_polling(self, interval_ms: int = 10000):
        """启动报告列表自动刷新（用于显示实时报告）"""
        try:
            if self._report_poll_job is not None:
                return
        except Exception:
            pass

        def _poll():
            try:
                self.refresh_reports()
            except Exception:
                pass
            finally:
                try:
                    self._report_poll_job = self.root.after(interval_ms, _poll)
                except Exception:
                    self._report_poll_job = None

        _poll()

    def _stop_report_polling(self):
        """停止报告列表自动刷新"""
        try:
            if self._report_poll_job is not None:
                self.root.after_cancel(self._report_poll_job)
        except Exception:
            pass
        self._report_poll_job = None

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

    def _get_stability_target_sn_list(self) -> list[str]:
        """
        稳定性测试的目标设备列表来源统一：
        - 优先 multi_devices_var（多设备输入）
        - 否则回退 device_sn_var（单设备选择）
        """
        sn_list: list[str] = []
        try:
            if getattr(self, "multi_devices_var", None) is not None:
                raw = (self.multi_devices_var.get() or "").strip()
                if raw:
                    sn_list = raw.split()
        except Exception:
            sn_list = []
        if not sn_list:
            try:
                raw = (self.device_sn_var.get() or "").strip()
                if raw:
                    sn_list = [raw]
            except Exception:
                sn_list = []
        # 去掉空串，保证至少一次调用后可控
        return [s for s in sn_list if (s or "").strip()]

    def _install_and_verify_apk(self, device_sn: str, apk_path: str) -> tuple:
        """
        在测试开始前执行 APK 安装并验证。
        返回 (成功, 错误信息)，成功时错误信息为 None。
        """
        try:
            from utils import Device, Package
        except ImportError as e:
            return False, f"无法加载 Device/Package 模块：{e}"

        apk_path = (apk_path or "").strip()
        if not apk_path or not os.path.isfile(apk_path):
            return False, "APK 文件路径无效或文件不存在"

        self.update_status("📦 正在准备安装（解析 APK 信息）...")
        try:
            package = Package(apk_path)
        except SystemExit:
            return False, "解析 APK 失败（请确保 APK 文件有效）"
        except Exception as e:
            return False, f"解析 APK 失败：{e}"

        if not getattr(package, "name", ""):
            return False, "无法解析 APK 包名（请确保已安装 Android SDK 或设置 AAPT_PATH）"

        adb_cmd = self._get_adb_cmd()
        if not adb_cmd:
            return False, "未找到 ADB 命令，请配置 ADB 路径"

        base_cmd = list(adb_cmd) + ["-s", device_sn]

        # 卸载旧版本
        self.update_status("📦 正在卸载旧版本...")
        try:
            subprocess.run(
                base_cmd + ["uninstall", package.name],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            self.log_queue.put(f"卸载提示：{e}")

        # 安装 APK
        self.update_status("📦 正在安装 APK 到设备，请稍候...")
        try:
            result = subprocess.run(
                base_cmd + ["install", "-r", apk_path],
                capture_output=True,
                text=True,
                timeout=600,
            )
            out = (result.stdout or "") + (result.stderr or "")
            if "Success" not in out:
                return False, f"APK 安装失败：{out.strip() or 'adb 未返回成功信息'}"
        except subprocess.TimeoutExpired:
            return False, "APK 安装超时（600 秒），请检查设备连接和 APK 大小"
        except Exception as e:
            return False, f"APK 安装异常：{e}"

        # 验证安装
        self.update_status("📦 正在验证安装...")
        try:
            v = subprocess.run(
                base_cmd + ["shell", "pm", "path", package.name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "package:" not in (v.stdout or ""):
                return False, f"安装验证失败：设备上未找到应用 {package.name}"
        except Exception as e:
            return False, f"验证安装失败：{e}"

        self.update_status("✅ APK 安装验证成功，开始执行测试...")
        return True, None

    def refresh_reports(self):
        """刷新报告列表（在后台线程执行 I/O，避免阻塞主线程）"""
        def _do_refresh() -> list:
            reports_dir = "reports"
            if not os.path.exists(reports_dir):
                return []
            report_files = []
            for file in os.listdir(reports_dir):
                if file.endswith(('.html', '.json')):
                    file_path = os.path.join(reports_dir, file)
                    try:
                        mtime = os.path.getmtime(file_path)
                        file_time = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
                        file_size = os.path.getsize(file_path)
                        report_info = self._parse_report_filename(file)
                        report_info['file_time'] = file_time
                        report_info['file_size'] = file_size
                        report_info['filename'] = file
                        report_files.append(report_info)
                    except Exception as e:
                        logging.warning("解析报告文件信息失败 %s: %s", file, e)
                        report_files.append({
                            'filename': file, 'file_time': '', 'test_type': 'unknown',
                            'status': 'unknown', 'device_sn': '', 'package_name': ''
                        })
            report_files.sort(key=lambda x: x.get('file_time', ''), reverse=True)
            return report_files

        def _on_done(files: list) -> None:
            # 仅在 reports_listbox 已初始化时才更新旧版报告列表区域
            if not hasattr(self, "reports_listbox") or self.reports_listbox is None:
                # 控件尚未创建时静默跳过，避免在应用启动早期触发异常
                if not files:
                    self.update_status("报告目录不存在或为空")
                return
            self.reports_listbox.delete(0, tk.END)
            self.report_file_map = {}
            if not files:
                self.update_status("报告目录不存在或为空")
                return
            for report_info in files:
                display_text = self._format_report_display(report_info)
                index = self.reports_listbox.size()
                self.reports_listbox.insert(tk.END, display_text)
                self.report_file_map[index] = report_info['filename']
            self.update_status("报告列表已刷新，共 %d 个报告" % len(files))

        def _run() -> None:
            try:
                files = _do_refresh()
                self.root.after(0, lambda: _on_done(files))
            except Exception as e:
                logging.exception("刷新报告列表异常")
                self.root.after(0, lambda: self.update_status("刷新报告列表失败: %s" % str(e)))

        threading.Thread(target=_run, daemon=True).start()

    def _strip_html_for_preview(self, html_str: str, max_chars: int = 2000) -> str:
        """从 HTML 中提取纯文本用于预览，避免完整 HTML 导致卡顿。"""
        if not html_str:
            return ""
        import re
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html_str, flags=re.I)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text

    def _on_report_selection_changed(self, event=None) -> None:
        """列表选中变化时在后台加载报告摘要并更新预览（纯文本，避免大 HTML 卡顿）。"""
        sel = self.reports_listbox.curselection()
        if not sel:
            return
        index = sel[0]
        report_file = self.report_file_map.get(index)
        if not report_file:
            display_text = self.reports_listbox.get(index)
            report_file = display_text.split("|")[-1].strip() if "|" in display_text else display_text.strip()
        if not report_file:
            return
        report_path = os.path.join("reports", report_file)

        def _load_preview() -> None:
            try:
                if not os.path.exists(report_path):
                    self.root.after(0, lambda: self._set_report_preview_text("文件不存在。"))
                    return
                with open(report_path, "r", encoding="utf-8", errors="replace") as f:
                    raw = f.read(65536)
                if report_file.endswith(".html"):
                    text = self._strip_html_for_preview(raw, 2000)
                elif report_file.endswith(".json"):
                    text = raw[:2000] + ("..." if len(raw) > 2000 else "")
                else:
                    text = raw[:2000] + ("..." if len(raw) > 2000 else "")
                self.root.after(0, lambda t=(text or "(无内容)"): self._set_report_preview_text(t))
            except Exception as e:
                self.root.after(0, lambda msg=("预览加载失败: %s" % str(e)): self._set_report_preview_text(msg))

        threading.Thread(target=_load_preview, daemon=True).start()

    def _set_report_preview_text(self, text: str) -> None:
        """在主线程更新报告预览区域（仅文本，避免大 HTML 卡顿）。"""
        if getattr(self, "report_preview", None) is None:
            return
        self.report_preview.delete(1.0, tk.END)
        self.report_preview.insert(tk.END, text)

    def _parse_report_filename(self, filename: str) -> dict:
        """
        解析报告文件名，提取测试类型、状态、设备信息等
        
        实际格式: {sn_short}_{project_key}_{timestamp}[_intermediate][_NN].{ext}
        """
        info = {
            'test_type': 'unknown',
            'status': 'final',
            'device_sn': '',
            'project_key': '',
            'timestamp': ''
        }
        
        try:
            # 移除扩展名
            base_name = os.path.splitext(filename)[0]
            parts = base_name.split('_')
            
            # 格式: {sn_short}_{project_key}_{timestamp}[_intermediate][_NN]
            if len(parts) >= 3:
                info['device_sn'] = parts[0]  # 设备序列号（前8位）
                info['project_key'] = parts[1]  # 测试项目键
                # 检查是否有 intermediate
                if '_intermediate' in base_name:
                    info['status'] = 'intermediate'
                    # 移除 intermediate 标记
                    parts = [p for p in parts if p != 'intermediate']
                # 时间戳是剩余部分（可能包含 _NN 后缀）
                if len(parts) >= 3:
                    info['timestamp'] = '_'.join(parts[2:])
                    # 从 project_key 推断 test_type
                    if info['project_key'] in ('monkey_stress', 'comprehensive', 'exception_recovery', 
                                               'performance', 'broadcast_stress', 'tts_stress'):
                        info['test_type'] = info['project_key']
            
            # 尝试从JSON文件中读取更多信息（过大则跳过，避免阻塞）
            json_path = os.path.join("reports", filename.replace('.html', '.json'))
            if os.path.exists(json_path):
                try:
                    if os.path.getsize(json_path) > 2 * 1024 * 1024:
                        pass
                    else:
                        with open(json_path, 'r', encoding='utf-8', errors='replace') as f:
                            json_data = json.load(f)
                        metadata = json_data.get('metadata', {})
                        if 'generated_at' in metadata:
                            info['file_time'] = metadata['generated_at']
                        if 'report_status' in metadata:
                            info['status'] = metadata['report_status']
                        if 'is_intermediate' in metadata:
                            info['status'] = 'intermediate' if metadata['is_intermediate'] else 'final'
                        if 'project_key' in metadata:
                            info['project_key'] = metadata['project_key']
                            info['test_type'] = metadata.get('test_type', metadata.get('project_key', 'unknown'))
                except Exception:
                    pass
        except Exception as e:
            logging.debug("解析文件名失败 %s: %s", filename, e)
        
        return info

    def _format_report_display(self, report_info: dict) -> str:
        """格式化报告显示文本"""
        filename = report_info.get('filename', 'unknown')

        # 若文件名本身已采用 pytest_xxx_YYYYMMDD_HHMMSS.html 规则，直接显示文件名，保持一致
        if filename.lower().endswith('.html') and filename.startswith('pytest_'):
            return filename

        test_type = report_info.get('test_type', 'unknown')
        status = report_info.get('status', 'unknown')
        file_time = report_info.get('file_time', '')
        device_sn = report_info.get('device_sn', '')
        package_name = report_info.get('package_name', '')
        
        # 格式化测试类型显示
        type_display = {
            'comprehensive': '综合测试',
            'system_robustness': 'Monkey 模式压力测试',
            'exception_recovery': '异常恢复',
            'performance': '性能测试'
        }.get(test_type, '未知测试' if test_type == 'unknown' else test_type)
        
        # 格式化状态显示
        status_display = {
            'final': '最终报告',
            'intermediate': '阶段性报告',
            'unknown': '未知状态'
        }.get(status, status)
        
        # 构建更清晰的显示文本
        # 格式: [测试类型] 状态 - 设备信息 - 应用信息 - 时间
        display_parts = []
        
        # 测试类型和状态
        if type_display != '未知测试':
            display_parts.append(f"{type_display} - {status_display}")
        else:
            display_parts.append(status_display)
        
        # 设备信息
        if device_sn and device_sn != 'unknown':
            display_parts.append(f"设备: {device_sn[:8]}")
        
        # 应用信息
        if package_name and package_name != 'unknown':
            # 截断过长的包名
            pkg_display = package_name[:15] + "..." if len(package_name) > 15 else package_name
            display_parts.append(f"应用: {pkg_display}")
        
        # 时间信息
        if file_time:
            # 只显示日期和时间，不显示秒
            time_display = file_time[:16] if len(file_time) >= 16 else file_time
            display_parts.append(f"时间: {time_display}")
        
        # 如果解析失败，至少显示文件名
        if not display_parts or (test_type == 'unknown' and status == 'unknown' and not device_sn and not package_name):
            # 尝试从文件名中提取基本信息
            base_name = os.path.splitext(filename)[0]
            if '_' in base_name:
                parts = base_name.split('_')
                if len(parts) >= 2:
                    display_parts = [f"测试报告 - {parts[0]} - {parts[1]}"]
            else:
                display_parts = [f"测试报告 - {base_name[:30]}"]
        
        display_text = " | ".join(display_parts)
        
        # 如果太长，截断
        if len(display_text) > 100:
            display_text = display_text[:97] + "..."
        
        return display_text

    def open_selected_report(self):
        """打开选中的报告（在后台线程执行打开/读取，避免阻塞 UI）"""
        selection = self.reports_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个报告文件")
            return
        index = selection[0]
        report_file = self.report_file_map.get(index)
        if not report_file:
            display_text = self.reports_listbox.get(index)
            report_file = display_text.split("|")[-1].strip() if "|" in display_text else display_text.strip()
            if not report_file:
                messagebox.showerror("错误", "无法获取报告文件名")
                return
        report_path = os.path.join("reports", report_file)
        if not os.path.exists(report_path):
            messagebox.showerror("错误", "报告文件不存在: %s" % report_file)
            return

        def _open_html() -> None:
            try:
                import webbrowser
                abs_path = os.path.abspath(report_path)
                if os.name == "nt":
                    abs_path = abs_path.replace("\\", "/")
                webbrowser.open("file:///%s" % abs_path)
                self.root.after(0, lambda: self.update_status("已打开报告: %s" % report_file))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("错误", "无法打开报告: %s" % str(e)))

        def _open_json() -> None:
            try:
                with open(report_path, "r", encoding="utf-8", errors="replace") as f:
                    content = json.dumps(json.load(f), indent=2, ensure_ascii=False)
                self.root.after(0, lambda c=content: self._show_json_report_window(report_file, c))
                self.root.after(0, lambda: self.update_status("已打开JSON报告: %s" % report_file))
            except Exception as e:
                self.root.after(0, lambda err=str(e): messagebox.showerror("错误", "无法读取报告: %s" % err))

        if report_file.endswith(".html"):
            threading.Thread(target=_open_html, daemon=True).start()
        elif report_file.endswith(".json"):
            threading.Thread(target=_open_json, daemon=True).start()
        else:
            def _open_other() -> None:
                try:
                    import subprocess
                    import platform
                    if platform.system() == "Windows":
                        os.startfile(report_path)
                    elif platform.system() == "Darwin":
                        subprocess.call(["open", report_path])
                    else:
                        subprocess.call(["xdg-open", report_path])
                    self.root.after(0, lambda: self.update_status("已打开报告: %s" % report_file))
                except Exception as e:
                    self.root.after(0, lambda: messagebox.showerror("错误", "无法打开报告: %s" % str(e)))
            threading.Thread(target=_open_other, daemon=True).start()

    def _do_refactor_reports(self, report_paths, parent=None):
        """在后台线程中重构一批报告文件，避免阻塞 UI"""

        def worker():
            success_count = 0
            fail_items = []
            total = len(report_paths)
            for report_path in report_paths:
                filename = os.path.basename(report_path)
                try:
                    self.root.after(
                        0,
                        lambda f=filename: self.update_status(f"正在重构报告: {f}（请稍候）"),
                    )
                    ok, msg = regenerate_report(report_path)
                except Exception as e:
                    ok = False
                    msg = f"重构失败: {filename}: {e}"
                    logging.exception("重构报告时发生异常: %s", report_path)

                def _notify(m=msg):
                    try:
                        self.update_status(m)
                    except Exception:
                        pass
                    try:
                        self.append_log(m)
                    except Exception:
                        pass

                self.root.after(0, _notify)

                if ok:
                    success_count += 1
                else:
                    fail_items.append((filename, msg))

            def _final():
                # 刷新两个入口的列表视图
                try:
                    self.refresh_reports()
                except Exception:
                    pass
                summary = f"报告重构完成：成功 {success_count} 个，失败 {len(fail_items)} 个（共 {total} 个）"
                try:
                    if parent is not None:
                        messagebox.showinfo("重构完成", summary, parent=parent)
                    else:
                        messagebox.showinfo("重构完成", summary)
                except Exception:
                    # 在无父窗口或窗口已销毁等情况下静默忽略
                    logging.debug("显示重构结果对话框失败")

            self.root.after(0, _final)

        threading.Thread(target=worker, daemon=True).start()

    def _show_json_report_window(self, report_file: str, content: str) -> None:
        """在主线程创建并显示 JSON 报告窗口（由 open_selected_report 经 after 调用）。"""
        json_window = tk.Toplevel(self.root)
        json_window.title("JSON报告查看器 - %s" % report_file)
        json_window.geometry("900x700")
        json_window.configure(bg=UIColors.BG_LIGHT)
        title_label = tk.Label(
            json_window,
            text="\u2702 %s" % report_file,
            font=UIFonts.SUBTITLE,
            fg=UIColors.TEXT_PRIMARY,
            bg=UIColors.BG_LIGHT,
        )
        title_label.pack(anchor=tk.W, padx=20, pady=(20, 10))
        text_widget = scrolledtext.ScrolledText(
            json_window,
            font=("Consolas", 10),
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_PRIMARY,
            wrap=tk.WORD,
            relief="flat",
            padx=10,
            pady=10,
        )
        text_widget.pack(fill=tk.BOTH, expand=True, padx=20, pady=(0, 20))
        text_widget.insert(tk.END, content)
        text_widget.config(state="disabled")

    def delete_selected_report(self):
        """删除选中的报告"""
        selection = self.reports_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择一个报告文件")
            return

        # 从映射字典中获取实际文件名
        index = selection[0]
        report_file = self.report_file_map.get(index)
        if not report_file:
            # 如果映射中没有，尝试从显示文本中提取（备用方案）
            display_text = self.reports_listbox.get(index)
            report_file = display_text.split('|')[-1].strip() if '|' in display_text else display_text.strip()
            if not report_file:
                messagebox.showerror("错误", "无法获取报告文件名")
                return
        
        report_path = os.path.join("reports", report_file)

        if messagebox.askyesno("确认删除", f"确定要删除报告文件 {report_file} 吗？"):
            try:
                os.remove(report_path)
                self.refresh_reports()
                self.update_status(f"已删除报告: {report_file}")
            except Exception as e:
                messagebox.showerror("错误", f"删除报告失败: {str(e)}")

    def start_stability_test(self):
        """开始稳定性测试"""
        if self.is_testing:
            messagebox.showwarning("⚠️ 警告", "测试正在进行中，请先停止当前测试")
            return

        if not self.device_sn_var.get():
            messagebox.showerror("❌ 错误", "请输入设备序列号")
            return
        # 设备选择验证：确保稳定性测试实际目标设备可连接
        sn_list = self._get_stability_target_sn_list()
        if not sn_list:
            messagebox.showerror("❌ 错误", "未找到稳定性测试目标设备序列号")
            return

        ok, msg = self.validate_selected_device(sn_list[0])
        if not ok:
            # 如果 multi_devices_var 残留了旧设备，且当前 device_sn_var 是可用设备，则自动切换到它
            current_single = (self.device_sn_var.get() or "").strip()
            if current_single and current_single != sn_list[0]:
                ok2, _ = self.validate_selected_device(current_single)
                if ok2:
                    sn_list = [current_single]
                    try:
                        # 同步到多设备输入框，避免后续 run_stability_test 仍用旧值
                        self.multi_devices_var.set(current_single)
                    except Exception:
                        pass
                    ok, msg = True, ""

        if not ok:
            messagebox.showerror("❌ 设备不可用", msg)
            return
        self._ensure_adb_env()

        # 必须选择已安装应用包名并校验存在
        pkg = (self.package_name_var.get() or "").strip()
        if not pkg:
            messagebox.showerror("❌ 错误", "请选择设备上已安装的应用包名（点击“扫描”）")
            return
        info = self._get_installed_app_basic_info((sn_list[0] or "").strip(), pkg)
        if info.get("missing"):
            messagebox.showerror("❌ 包不存在", f"设备上未安装包名：{pkg}")
            return

        # 检查模块选择（测试模式已移除，直接使用模块选择区域）
        enabled_modules = [module for module, var in self.module_vars.items() if var.get()]
        if not enabled_modules:
            messagebox.showerror("❌ 错误", "请至少选择一个测试模块")
            return
        logging.info(f"启用的测试模块: {enabled_modules}")
        if self.progress_info_label:
            self.progress_info_label.config(text="当前状态：正在运行稳定性测试", fg=UIColors.PRIMARY)

        # 若启用 Mock Server，则在测试开始前确保本地Mock服务就绪（最小侵入集成）
        if not self.no_mock_server_var.get():
            self.ensure_mock_server_running()

        # 清除暂停状态，确保新测试从运行态开始
        try:
            from utils.run_control import set_paused
            set_paused(False)
        except Exception:
            pass

        # 更新UI状态
        if self.start_test_btn:
            self.start_test_btn.config(state="disabled", bg=UIColors.TEXT_SECONDARY)
        for btn in (getattr(self, "stop_test_btn", None), getattr(self, "stop_stability_btn", None)):
            if btn:
                btn.config(state="normal")
        for btn in (getattr(self, "pause_test_btn", None), getattr(self, "pause_stability_btn", None)):
            if btn:
                btn.config(state="normal")
        for btn in (getattr(self, "resume_test_btn", None), getattr(self, "resume_stability_btn", None)):
            if btn:
                btn.config(state="disabled")
        if self.progress_bar:
            self.progress_bar.start()

        # 启动测试线程
        self.is_testing = True
        self.test_thread = threading.Thread(target=self.run_stability_test)
        self.test_thread.daemon = True
        self.test_thread.start()

        self.update_status("🚀 开始稳定性测试...")

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

            # 统一目标设备列表与 start_stability_test 校验逻辑一致
            sn_list = self._get_stability_target_sn_list()
            if not sn_list:
                sn_list = [(self.device_sn_var.get() or "").strip()]

            # 构建基础参数
            params = {
                'mode': 'stability',
                'sn_list': sn_list,
                'config_path': None,
                'duration': duration_hours,
                'use_mock_server': not self.no_mock_server_var.get(),
                'use_network_proxy': not self.no_network_proxy_var.get(),
                'network_method': self.network_method_var.get(),
                'establish_baseline': self.baseline_establish_var.get(),
                'compare_baseline': self.baseline_compare_var.get(),
                'use_fallback_only': self.use_fallback_only_var.get(),  # 直接使用Fallback事件注入
                'apk_url': "",
                'apk_path': "",
                'package_name': (self.package_name_var.get() or "").strip(),
                # GUI 入口：仅运行标记为 stability_smoke 的轻量用例（避免参数化长压用例重复跑多种时长）
                'smoke_only': True,
            }

            # 添加模块化测试参数（直接使用模块选择区域，测试模式已移除）
            enabled_modules = [module for module, var in self.module_vars.items() if var.get()]
            params['modular_enabled'] = True
            params['enabled_modules'] = enabled_modules

            # 初始化日志
            project_log = ProjectLog()
            project_log.set_up()

            # 用子进程执行 pytest（可通过 stop_test 强制终止）
            from core.services.stability_service import StabilityTestService
            plan = StabilityTestService.plan_from_params(params)
            pytest_args = StabilityTestService.build_pytest_args(plan)
            cmd = [sys.executable, "-m", "pytest", *pytest_args]
            exit_code = self._run_test_subprocess(cmd, title="稳定性测试")
            if exit_code != 0 and self.is_testing:
                self.log_queue.put(f"测试异常结束（退出码: {exit_code}），请查看上方日志排查。")
                self.update_status(f"测试异常结束（退出码: {exit_code}）")
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

    def pause_test(self):
        """暂停测试（子进程将进入等待，超时 30 分钟自动终止）"""
        try:
            from utils.run_control import set_paused
            set_paused(True)
            self.update_status("已暂停测试，点击「继续」恢复；暂停超过 30 分钟将自动终止")
            for btn in (getattr(self, "pause_test_btn", None), getattr(self, "pause_stability_btn", None)):
                if btn:
                    btn.config(state="disabled")
            for btn in (getattr(self, "resume_test_btn", None), getattr(self, "resume_stability_btn", None)):
                if btn:
                    btn.config(state="normal")
        except Exception as e:
            self.update_status(f"暂停失败: {e}")

    def resume_test(self):
        """继续测试"""
        try:
            from utils.run_control import set_paused
            set_paused(False)
            self.update_status("已继续测试")
            for btn in (getattr(self, "pause_test_btn", None), getattr(self, "pause_stability_btn", None)):
                if btn:
                    btn.config(state="normal")
            for btn in (getattr(self, "resume_test_btn", None), getattr(self, "resume_stability_btn", None)):
                if btn:
                    btn.config(state="disabled")
        except Exception as e:
            self.update_status(f"继续失败: {e}")

    def stop_test(self):
        """停止测试"""
        if self.is_testing:
            self.is_testing = False
            self.update_status("正在停止测试（尝试终止子进程）...")
            for btn in (getattr(self, "stop_test_btn", None), getattr(self, "stop_stability_btn", None)):
                if btn:
                    btn.config(state="disabled")
            for btn in (getattr(self, "pause_test_btn", None), getattr(self, "pause_stability_btn", None)):
                if btn:
                    btn.config(state="disabled")
            for btn in (getattr(self, "resume_test_btn", None), getattr(self, "resume_stability_btn", None)):
                if btn:
                    btn.config(state="disabled")
            try:
                from utils.run_control import set_paused
                set_paused(False)
            except Exception:
                pass
            self._terminate_running_test_process()
            # 同步更新实时报告状态为“已停止”
            try:
                self._mark_live_report_stopped()
            except Exception:
                pass
            # 手动停止时：若设备侧存在与目标应用相关的 ANR/tombstone，则补采 bugreport
            try:
                self._collect_bugreport_after_manual_stop()
            except Exception:
                pass

    def _collect_bugreport_after_manual_stop(self):
        """
        stop_test 会强制终止 pytest 子进程（Windows 下 taskkill /T /F），子进程无法在 finally 中补采 bugreport。
        这里由 GUI 进程在后台线程做一次兜底：
        - 解析当前 live report 路径推断 run_log_dir（logs/<sn>/<ts>）
        - 若推断失败，则对多设备 sn 列表取各自 logs/<sn>/ 下最新目录
        - 若发现设备侧与包名匹配的 ANR/tombstone，导出 adb bugreport 到 run_log_dir/bugreport/
        """
        pkg = (getattr(self, "package_name_var", None).get() or "").strip() if getattr(self, "package_name_var", None) else ""
        if not pkg:
            return
        sn_list = []
        try:
            s = (getattr(self, "multi_devices_var", None).get() or "").strip() if getattr(self, "multi_devices_var", None) else ""
            sn_list = [x.strip() for x in s.split() if x.strip()]
        except Exception:
            sn_list = []
        if not sn_list:
            try:
                sn = (getattr(self, "device_sn_var", None).get() or "").strip() if getattr(self, "device_sn_var", None) else ""
                if sn:
                    sn_list = [sn]
            except Exception:
                sn_list = []
        if not sn_list:
            return

        # 尝试从当前 live report 推断 sn / ts -> run_log_dir
        inferred = {}  # sn -> run_log_dir
        try:
            import os as _os
            import re as _re
            rp = (getattr(self, "_current_live_report_path", "") or "").strip()
            if rp and _os.path.exists(rp):
                base = _os.path.basename(rp)
                m = _re.match(r"^(?P<sn>[^_]+)_.+_(?P<ts>\d{8}_\d{6})\.html$", base)
                if m:
                    sn0 = (m.group("sn") or "").strip()
                    ts0 = (m.group("ts") or "").strip()
                    if sn0 and ts0:
                        inferred[sn0] = _os.path.join("logs", sn0, ts0)
        except Exception:
            inferred = {}

        def _latest_run_dir(sn: str) -> str:
            import os as _os
            root = _os.path.join("logs", sn)
            if not _os.path.isdir(root):
                return ""
            try:
                dirs = [d for d in _os.listdir(root) if _os.path.isdir(_os.path.join(root, d))]
                if not dirs:
                    return ""
                # 优先按 mtime
                latest = max(dirs, key=lambda d: _os.path.getmtime(_os.path.join(root, d)))
                return _os.path.join(root, latest)
            except Exception:
                return ""

        def _worker():
            try:
                from utils.stress_monitor import StressMonitor
            except Exception:
                return
            for sn in sn_list:
                run_dir = inferred.get(sn) or _latest_run_dir(sn)
                if not run_dir:
                    continue
                try:
                    out = StressMonitor.collect_bugreport_if_needed(sn, pkg, run_dir, reason="manual_stop")
                    if out:
                        try:
                            self.log_queue.put(f"[bugreport] 已导出: {out}")
                        except Exception:
                            pass
                except Exception:
                    continue

        try:
            t = threading.Thread(target=_worker, daemon=True)
            t.start()
        except Exception:
            pass

    def _mark_live_report_stopped(self):
        """将当前 live 实时报告标记为“已停止”，并记录停止时间/简要信息。"""
        path = (getattr(self, "_current_live_report_path", "") or "").strip()
        if not path or not os.path.exists(path):
            return
        stop_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                html = f.read()
        except Exception:
            return
        # 1) badge 改为红色“已停止”
        try:
            import re as _re
            html = _re.sub(
                r"<div[^>]*>实时报告（测试进行中）</div>",
                "<div style=\"background: #dc3545; color: #fff; padding: 5px 10px; border-radius: 4px; display: inline-block; margin-left: 10px;\">实时报告（已停止）</div>",
                html,
                count=1,
            )
        except Exception:
            pass
        # 2) 插入停止信息（若已存在则不重复插入）
        if "停止时间" not in html:
            insert_block = f"""
<div class="section">
  <h3>停止信息</h3>
  <table>
    <tr><td>状态</td><td>已停止（用户点击停止测试）</td></tr>
    <tr><td>停止时间</td><td>{stop_time}</td></tr>
    <tr><td>说明</td><td>停止后不再更新；进度以停止前最后一次报告更新为准。</td></tr>
  </table>
</div>
"""
            marker = "<div class=\"footer\">"
            if marker in html:
                html = html.replace(marker, insert_block + marker, 1)
        try:
            with open(path, "w", encoding="utf-8", errors="replace") as f:
                f.write(html)
        except Exception:
            return
        # 同步更新伴生 JSON 的 report_status
        json_path = os.path.splitext(path)[0] + ".json"
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                data.setdefault("metadata", {})["report_status"] = "stopped"
                data.setdefault("metadata", {})["stopped_at"] = stop_time
                with open(json_path, "w", encoding="utf-8", errors="replace") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        # 让报告列表尽快体现修改时间
        try:
            self.refresh_reports()
        except Exception:
            pass

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
        self._last_test_exit_code = None

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
            # 报告命名/展示所需：测试项目 key（来自首页“测试模块选择”）
            try:
                prj_key = (getattr(self, "version_var", None).get() or "").strip() if getattr(self, "version_var", None) else ""
                if prj_key:
                    env["MONKEYAUTOTEST_PROJECT_KEY"] = prj_key
            except Exception:
                pass
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
                        # 捕获子进程输出的实时报告路径（用于 stop 时标记“已停止”）
                        try:
                            import re as _re
                            m = _re.search(r"实时报告已启动.*?:\s*(.+\\.html)", line)
                            if not m:
                                m = _re.search(r"初始实时报告已创建:\\s*(.+\\.html)", line)
                            if m:
                                self._current_live_report_path = m.group(1).strip()
                        except Exception:
                            pass
                        # 统一GUI日志格式：为子进程输出补齐时间戳（已带 [YYYY-..] 的行不重复包裹）
                        if line.startswith("[") and "]" in line[:32]:
                            self.log_queue.put(line)
                        else:
                            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            self.log_queue.put(f"[{ts}] {line}")
                    if not self.is_testing:
                        break

            try:
                exit_code = p.wait(timeout=5 if not self.is_testing else None)
            except Exception:
                try:
                    exit_code = p.poll() or -1
                except Exception:
                    exit_code = -1
            self._last_test_exit_code = int(exit_code if exit_code is not None else -1)
            return self._last_test_exit_code
        finally:
            with self._test_process_lock:
                self.test_process = None
            if getattr(self, "_last_test_exit_code", None) is not None:
                try:
                    self.log_queue.put("测试进程已退出，退出码: %s" % self._last_test_exit_code)
                except Exception:
                    pass

    def reset_stability_ui(self):
        """重置稳定性测试UI状态"""
        if self.start_test_btn:
            self.start_test_btn.config(state="normal", bg=UIColors.PRIMARY)
        for btn in (getattr(self, "stop_test_btn", None), getattr(self, "stop_stability_btn", None)):
            if btn:
                btn.config(state="disabled")
        for btn in (getattr(self, "pause_test_btn", None), getattr(self, "pause_stability_btn", None)):
            if btn:
                btn.config(state="disabled")
        for btn in (getattr(self, "resume_test_btn", None), getattr(self, "resume_stability_btn", None)):
            if btn:
                btn.config(state="disabled")
        try:
            from utils.run_control import set_paused
            set_paused(False)
        except Exception:
            pass
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
                with open(filename, 'w', encoding='utf-8', errors='replace') as f:
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
        """添加日志到文本框。统一入口：仅对尚未包含时间戳的消息补时间戳，避免重复。"""
        import re
        import time as _time
        msg_stripped = message.strip()
        # 去重：同一条消息被重复投递到 log_queue 时（常见于 update_status + 额外 log_queue.put），避免连续重复显示
        try:
            now = _time.monotonic()
            last_msg = getattr(self, "_last_log_message", "")
            last_ts = getattr(self, "_last_log_ts", 0.0)
            if msg_stripped and msg_stripped == last_msg and (now - last_ts) < 0.5:
                return
            self._last_log_message = msg_stripped
            self._last_log_ts = now
        except Exception:
            pass
        # 已包含时间戳的格式（任一种即视为已格式化，不再重复添加）：
        # 1) [2026-02-05 10:45:00] [INFO] 消息  （logging 常用）
        # 2) 2026-02-05 10:45:00 [INFO] 消息
        already_formatted = (
            re.match(r'^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\]\s+\[', msg_stripped) is not None
            or re.match(r'^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+\[', msg_stripped) is not None
        )
        if already_formatted or not msg_stripped:
            log_line = f"{message}\n" if message else "\n"
        else:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{ts}] {message}\n"
        self.log_text.insert(tk.END, log_line)

        if self.auto_scroll_var.get():
            self.log_text.see(tk.END)

        # 限制日志行数（保持最后1000行）
        lines = self.log_text.get(1.0, tk.END).split('\n')
        if len(lines) > 1000:
            self.log_text.delete(1.0, f"{len(lines) - 1000}.0")

    def update_status(self, message):
        """更新状态栏（线程安全）"""
        msg = str(message)
        # 日志队列允许跨线程写入
        try:
            self.log_queue.put(msg)
        except Exception:
            pass

        def _apply():
            try:
                if hasattr(self, 'status_bar') and self.status_bar:
                    self.status_bar.config(text=msg)
            except Exception:
                pass

        # Tk UI 只能在主线程更新；后台线程调用时用 after 投递
        try:
            import threading as _threading
            if getattr(self, "_ui_thread_id", None) is not None and _threading.get_ident() != self._ui_thread_id:
                try:
                    self.root.after(0, _apply)
                except Exception:
                    pass
            else:
                _apply()
        except Exception:
            _apply()

    def on_closing(self):
        """窗口关闭事件处理"""
        if self.is_testing:
            if messagebox.askyesno("确认退出", "测试正在进行中，确定要退出吗？"):
                self.stop_test()
                try:
                    self._stop_report_polling()
                except Exception:
                    pass
                self.root.destroy()
        else:
            try:
                self._stop_report_polling()
            except Exception:
                pass
            self.root.destroy()
    
    def open_stability_config_dialog(self):
        if getattr(self, "_stability_cfg_win", None) and tk.Toplevel.winfo_exists(self._stability_cfg_win):
            self._stability_cfg_win.lift()
            return

        win = tk.Toplevel(self.root)
        self._stability_cfg_win = win
        win.title("稳定性测试配置")
        win.configure(bg=UIColors.BG_LIGHT)
        win.minsize(800, 600)

        frame = tk.Frame(win, bg=UIColors.BG_LIGHT)
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        stab_canvas = tk.Canvas(frame, bg=UIColors.BG_LIGHT, highlightthickness=0)
        stab_vbar = ttk.Scrollbar(frame, orient="vertical", command=stab_canvas.yview)
        stab_canvas.configure(yscrollcommand=stab_vbar.set)
        stab_vbar.pack(side=tk.RIGHT, fill=tk.Y)
        stab_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        content = tk.Frame(stab_canvas, bg=UIColors.BG_LIGHT)
        content_id = stab_canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda e: stab_canvas.configure(scrollregion=stab_canvas.bbox("all")))
        stab_canvas.bind("<Configure>", lambda e: stab_canvas.itemconfig(content_id, width=e.width))
        stab_canvas.bind("<Enter>", lambda e: stab_canvas.bind_all("<MouseWheel>", lambda ev: stab_canvas.yview_scroll(int(-ev.delta / 120), "units")))
        stab_canvas.bind("<Leave>", lambda e: stab_canvas.unbind_all("<MouseWheel>"))
        content.grid_columnconfigure(0, weight=1)
        content.grid_columnconfigure(1, weight=1)

        # 1) 模块选择 + 预设组合（测试模式已移除，模块选择直接控制运行内容）
        modules_card = self.create_card_grid(content, "🧩 自定义模块组合", row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        ToolTip(modules_card, "选择要执行的稳定性测试模块：Monkey 模式压力测试（长时间压力）、异常恢复（网络/数据异常）、完整性能、仅响应性能等。勾选后将运行相应测试。")

        preset_frame = tk.Frame(modules_card, bg=UIColors.WHITE)
        preset_frame.pack(fill=tk.X, padx=5, pady=(5, 10))
        tk.Label(
            preset_frame,
            text="快速选择预设组合:",
            font=UIFonts.BODY,
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_PRIMARY,
        ).pack(side=tk.LEFT, padx=(0, 10))

        self.preset_combos_var = getattr(self, "preset_combos_var", tk.StringVar(value="自定义"))
        self.preset_combos_widget = ttk.Combobox(
            preset_frame,
            textvariable=self.preset_combos_var,
            values=[
                "自定义",
                "完整测试套件（全部模块）",
                "仅 Monkey 压力测试",
                "仅异常恢复",
                "仅性能测试（完整）",
                "仅响应性能",
                "Monkey 压力+异常恢复",
                "Monkey 压力+性能测试",
            ],
            state="readonly",
            width=25,
        )
        self.preset_combos_widget.pack(side=tk.LEFT, padx=(0, 10))
        ToolTip(
            self.preset_combos_widget,
            "测试模块预设组合：\n- 选择常用组合快速勾选下方模块，例如“完整测试套件”、“仅 Monkey 压力测试”等。\n- 选择“自定义”时，可手动勾选/取消各模块复选框。"
        )
        self.preset_combos_widget.bind("<<ComboboxSelected>>", self.on_preset_combo_selected)
        try:
            self._refresh_preset_combos()
        except Exception:
            pass

        tk.Button(
            preset_frame,
            text="💾 保存当前组合",
            command=self.save_current_module_combo,
            bg=UIColors.INFO,
            fg=UIColors.WHITE,
            font=UIFonts.BUTTON,
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=2,
        ).pack(side=tk.LEFT)

        self.modules_frame = tk.Frame(modules_card, bg=UIColors.WHITE)
        self.modules_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        modules_data = [
            ("monkey_stress", "🏗️ Monkey 模式压力测试", "长时间压力测试"),
            ("exception_recovery", "🔄 异常恢复测试", "网络/数据异常"),
            ("performance_all", "📊 完整性能测试", "响应+资源"),
            ("performance_response", "⚡ 仅响应性能测试", "冷启动、延迟"),
            ("broadcast_stress", "📡 广播模式压力测试", "adb broadcast 调用应用能力"),
            ("tts_stress", "🔊 TTS 模式压力测试", "PC 端语音播放 + 设备麦克风接收"),
        ]
        for key, main_text, sub_text in modules_data:
            cb = tk.Checkbutton(
                self.modules_frame,
                text=f"{main_text}（{sub_text}）",
                variable=self.module_vars[key],
                bg=UIColors.WHITE,
                font=UIFonts.BODY,
                cursor="hand2",
                command=self.on_module_selection_changed,
            )
            cb.pack(anchor=tk.W, pady=3)
            if key == "monkey_stress":
                tip = "Monkey 模式压力测试：\n-使用adb monkey进行长时间随机事件压力。\n-建议配合性能监控与 Monkey 遮罩区域一起使用。"
            elif key == "exception_recovery":
                tip = "异常恢复测试：\n-覆盖网络断开、弱网、Mock Server 等异常场景。\n-需正确配置 Mock Server 与网络代理选项。"
            elif key == "performance_all":
                tip = "完整性能测试：\n-同时评估响应性能与资源消耗（CPU/内存等）。"
            elif key == "performance_response":
                tip = "仅响应性能测试：\n-关注冷启动时间与交互响应延迟，不采集长期资源趋势。"
            elif key == "broadcast_stress":
                tip = "广播模式压力测试：\n-通过 adb broadcast 发送Hint调用应用能力。\n-Hints文本与文件、响应监控参数由下方配置。"
            elif key == "tts_stress":
                tip = "TTS 模式压力测试：\n-PC 端播放语音，设备麦克风接收后由应用响应。\n-文本内容与文件、响应监控参数由下方配置。"
            else:
                tip = "测试模块。"
            ToolTip(cb, tip)

        # 3) 参数设置（时长 + 网络 + 多设备）
        params_card = self.create_card_grid(content, "🛡️ 参数设置", row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        form = tk.Frame(params_card, bg=UIColors.WHITE)
        form.pack(fill=tk.X, pady=5)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="测试方案:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=6)
        dur_row = tk.Frame(form, bg=UIColors.WHITE)
        dur_row.grid(row=0, column=1, sticky=tk.EW, pady=6, padx=(10, 0))
        dur_row.grid_columnconfigure(0, weight=0)
        dur_row.grid_columnconfigure(1, weight=1)

        self.duration_preset_combo = ttk.Combobox(
            dur_row,
            textvariable=self.duration_preset_var,
            values=[
                "快速测试（30分钟）",
                "标准测试（2小时）",
                "深度测试（6小时）",
                "长期压力测试（12小时）",
                "持久稳定性测试（24小时）",
            ],
            state="readonly",
            width=18,
        )
        self.duration_preset_combo.grid(row=0, column=0, sticky=tk.W)
        ToolTip(
            self.duration_preset_combo,
            "测试方案预设时长：\n-快速测试：约 30 分钟。\n-标准测试：约 2 小时。\n-深度测试：约 6 小时。\n-长期/持久压力测试：12~24 小时。\n可在主界面中进一步调整具体时长。"
        )
        self.duration_preset_combo.bind("<<ComboboxSelected>>", self.on_duration_preset_changed)

        self.duration_preset_desc_label = tk.Label(
            dur_row,
            text="",
            font=UIFonts.CAPTION,
            fg=UIColors.TEXT_SECONDARY,
            bg=UIColors.WHITE,
            anchor="w",
        )
        self.duration_preset_desc_label.grid(row=0, column=1, sticky=tk.EW, padx=(10, 0))
        try:
            self.on_duration_preset_changed()
        except Exception:
            pass

        tk.Label(form, text="网络模拟方法:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=6)
        network_combo = ttk.Combobox(
            form,
            textvariable=self.network_method_var,
            values=["root", "pc_proxy", "wifi_control", "app_simulation"],
            state="readonly",
        )
        network_combo.grid(row=1, column=1, sticky=tk.EW, pady=6, padx=(10, 0))
        ToolTip(
            network_combo,
            "网络模拟方法：\n-root：通过 root 权限直接控制网络。\n-pc_proxy：通过 PC 端代理（如 mitmproxy）注入流量。\n-wifi_control：通过 Wi-Fi 控制网络状态。\n-app_simulation：由应用自身模拟网络行为。\n请与 Mock Server/网络代理配置配合使用。"
        )

        tk.Label(form, text="多设备SN(空格分隔):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=2, column=0, sticky=tk.W, pady=6)
        multi_sn_entry = tk.Entry(form, textvariable=self.multi_devices_var, font=UIFonts.BODY)
        multi_sn_entry.grid(row=2, column=1, sticky=tk.EW, pady=6, padx=(10, 0))
        ToolTip(
            multi_sn_entry,
            "多设备序列号：\n-使用空格分隔多个 Android 设备 SN，例如：\n  7ff80600 emulator-5554\n-仅在需要同时对多台设备执行稳定性测试时填写。"
        )

        # 广播/TTS 配置
        broadcast_tts_card = self.create_card_grid(content, "📡 广播 / 🔊 TTS 配置", row=2, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 10))
        bc_frame = tk.Frame(broadcast_tts_card, bg=UIColors.WHITE)
        bc_frame.pack(fill=tk.X, padx=5, pady=5)
        bc_frame.grid_columnconfigure(1, weight=1)
        bc_hints_label = tk.Label(bc_frame, text="广播Hints(每行一条):", font=UIFonts.BODY, bg=UIColors.WHITE)
        bc_hints_label.grid(row=0, column=0, sticky=tk.NW, pady=4)
        bc_text = tk.Text(bc_frame, height=3, width=40, font=UIFonts.BODY)
        bc_text.grid(row=0, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        bc_text.insert("1.0", getattr(self, "broadcast_hints_var", tk.StringVar(value="")).get() or "介绍一下白居易\n讲个笑话")
        self._broadcast_hints_text = bc_text
        ToolTip(
            bc_hints_label,
            "广播Hints列表：\n-每行一条Hint文本，将按顺序循环发送。\n-可搭配Hints文件使用：若文件存在且配置了路径，则以文件内容为准。"
        )
        bc_hints_file_label = tk.Label(bc_frame, text="Hints文件路径(可选):", font=UIFonts.BODY, bg=UIColors.WHITE)
        bc_hints_file_label.grid(row=1, column=0, sticky=tk.W, pady=4)
        bc_hints_file_entry = tk.Entry(bc_frame, textvariable=getattr(self, "broadcast_hints_file_var", tk.StringVar(value="")), font=UIFonts.BODY)
        bc_hints_file_entry.grid(row=1, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        ToolTip(
            bc_hints_file_label,
            "广播Hints文件路径：\n-可选配置，指向包含Hint文本的UTF-8文本文件。\n-每行一条Hint，若配置了文件，将优先使用文件内容。\n-支持绝对路径或相对于项目根目录的路径。"
        )
        tts_label = tk.Label(bc_frame, text="TTS 文本(每行一条):", font=UIFonts.BODY, bg=UIColors.WHITE)
        tts_label.grid(row=2, column=0, sticky=tk.NW, pady=4)
        tts_text = tk.Text(bc_frame, height=3, width=40, font=UIFonts.BODY)
        tts_text.grid(row=2, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        tts_text.insert("1.0", getattr(self, "tts_texts_var", tk.StringVar(value="")).get() or "打开设置\n介绍一下北京")
        self._tts_texts_text = tts_text
        ToolTip(
            tts_label,
            "TTS 文本列表：\n-每行一条，将依次通过 PC 端 TTS 播放。\n-建议使用短句，方便设备识别（如“打开设置”、“介绍一下北京”）。\n-若配置了 TTS 文本文件，将优先使用文件内容。"
        )
        tts_file_label = tk.Label(bc_frame, text="TTS 文本文件路径(可选):", font=UIFonts.BODY, bg=UIColors.WHITE)
        tts_file_label.grid(row=3, column=0, sticky=tk.W, pady=4)
        tts_file_entry = tk.Entry(bc_frame, textvariable=getattr(self, "tts_texts_file_var", tk.StringVar(value="")), font=UIFonts.BODY)
        tts_file_entry.grid(row=3, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        ToolTip(
            tts_file_label,
            "TTS 文本文件路径：\n-可选配置，指向包含 TTS 文本的 UTF-8 文本文件。\n-每行一条，将依次播放。\n-支持绝对路径或相对于项目根目录的路径。"
        )
        # TTS 结束词 / 唤醒词及等待时间配置
        end_phrase_label = tk.Label(bc_frame, text="结束词(可选):", font=UIFonts.BODY, bg=UIColors.WHITE)
        end_phrase_label.grid(row=4, column=0, sticky=tk.W, pady=4)
        end_phrase_entry = tk.Entry(
            bc_frame,
            textvariable=getattr(self, "tts_end_phrase_var", tk.StringVar(value="")),
            font=UIFonts.BODY,
        )
        end_phrase_entry.grid(row=4, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        ToolTip(
            end_phrase_label,
            "结束词：\n-每条 TTS 语料开始前可选播放的结束词/收尾指令。\n-例如“本轮测试结束”、“上一条结束”等。\n-留空则不播放结束词。"
        )

        wake_phrase_label = tk.Label(bc_frame, text="唤醒词(可选):", font=UIFonts.BODY, bg=UIColors.WHITE)
        wake_phrase_label.grid(row=5, column=0, sticky=tk.W, pady=4)
        wake_phrase_entry = tk.Entry(
            bc_frame,
            textvariable=getattr(self, "tts_wake_phrase_var", tk.StringVar(value="")),
            font=UIFonts.BODY,
        )
        wake_phrase_entry.grid(row=5, column=1, sticky=tk.EW, padx=(10, 0), pady=4)
        ToolTip(
            wake_phrase_label,
            "唤醒词：\n-每条 TTS 语料前的唤醒指令，例如“你好，小助手”。\n-留空则不播放唤醒词。"
        )

        wake_delay_label = tk.Label(bc_frame, text="唤醒后等待(秒):", font=UIFonts.BODY, bg=UIColors.WHITE)
        wake_delay_label.grid(row=6, column=0, sticky=tk.W, pady=4)
        wake_delay_entry = tk.Entry(
            bc_frame,
            textvariable=getattr(self, "tts_wake_delay_var", tk.StringVar(value="2")),
            font=UIFonts.BODY,
            width=10,
        )
        wake_delay_entry.grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            wake_delay_label,
            "唤醒后等待时间：\n-单位：秒，默认 2 秒。\n-播放完唤醒词后，等待多少秒再播放实际测试语料。"
        )

        tts_interval_label = tk.Label(bc_frame, text="TTS 间隔(秒):", font=UIFonts.BODY, bg=UIColors.WHITE)
        tts_interval_label.grid(row=7, column=0, sticky=tk.W, pady=4)
        tts_interval_entry = tk.Entry(
            bc_frame,
            textvariable=getattr(self, "tts_interval_seconds_var", tk.StringVar(value="30")),
            font=UIFonts.BODY,
            width=10,
        )
        tts_interval_entry.grid(row=7, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            tts_interval_label,
            "TTS 播报间隔：\n-单位：秒，默认 30 秒。\n-每条正文播报（含唤醒词/等待）完成后，会按该间隔进入下一条。\n-启用响应监控时，会根据实际耗时补齐剩余间隔。"
        )

        tts_volume_label = tk.Label(bc_frame, text="TTS 音量(%):", font=UIFonts.BODY, bg=UIColors.WHITE)
        tts_volume_label.grid(row=8, column=0, sticky=tk.W, pady=4)
        tts_volume_entry = tk.Entry(
            bc_frame,
            textvariable=getattr(self, "tts_volume_percent_var", tk.StringVar(value="100")),
            font=UIFonts.BODY,
            width=10,
        )
        tts_volume_entry.grid(row=8, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            tts_volume_label,
            "TTS 播报音量：\n-范围 0–100，默认 100。\n-该音量用于 TTS 引擎输出音量（pyttsx3 volume），并不会改变系统主音量。\n-若耳机仍偏小，请同时提高系统音量或耳机自身音量。"
        )

        # 响应监控参数（广播/TTS 共用，仅 logcat 模式，发送后立即开始监控）
        max_appear_label = tk.Label(bc_frame, text="最大等待出现(秒):", font=UIFonts.BODY, bg=UIColors.WHITE)
        max_appear_label.grid(row=9, column=0, sticky=tk.W, pady=4)
        max_appear_entry = tk.Entry(bc_frame, textvariable=getattr(self, "response_monitor_max_wait_appear_var", tk.StringVar(value="6")), font=UIFonts.BODY, width=10)
        max_appear_entry.grid(row=9, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            max_appear_label,
            "最大等待出现时间：\n-单位：秒。\n-在发送Hint/TTS 后，最多等待多少秒内出现“响应已显示”的标志。\n-典型取值 3–10 秒，过小可能误判 ANR。"
        )
        check_interval_label = tk.Label(bc_frame, text="检测间隔(秒):", font=UIFonts.BODY, bg=UIColors.WHITE)
        check_interval_label.grid(row=10, column=0, sticky=tk.W, pady=4)
        check_interval_entry = tk.Entry(bc_frame, textvariable=getattr(self, "response_monitor_check_interval_var", tk.StringVar(value="0.1")), font=UIFonts.BODY, width=10)
        check_interval_entry.grid(row=10, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            check_interval_label,
            "检测间隔：\n-单位：秒。\n-控制轮询 logcat 的频率，间隔越小监控越精细，但 logcat 开销越大。\n-建议范围 0.05–1.0。"
        )
        max_disappear_label = tk.Label(bc_frame, text="最大等待消失(秒):", font=UIFonts.BODY, bg=UIColors.WHITE)
        max_disappear_label.grid(row=11, column=0, sticky=tk.W, pady=4)
        max_disappear_entry = tk.Entry(bc_frame, textvariable=getattr(self, "response_monitor_max_wait_disappear_var", tk.StringVar(value="300")), font=UIFonts.BODY, width=10)
        max_disappear_entry.grid(row=11, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            max_disappear_label,
            "最大等待消失时间：\n-单位：秒。\n-控制“响应卡片/界面”在出现后，最多允许停留多久仍未消失。\n-超过该时间将视为超时（timeout_disappear）。"
        )
        anr_threshold_label = tk.Label(bc_frame, text="连续 ANR/无响应次数阈值:", font=UIFonts.BODY, bg=UIColors.WHITE)
        anr_threshold_label.grid(row=12, column=0, sticky=tk.W, pady=4)
        anr_threshold_entry = tk.Entry(
            bc_frame,
            textvariable=getattr(self, "response_monitor_anr_recover_threshold_var", tk.StringVar(value="1")),
            font=UIFonts.BODY,
            width=10,
        )
        anr_threshold_entry.grid(row=12, column=1, sticky=tk.W, padx=(10, 0), pady=4)
        ToolTip(
            anr_threshold_label,
            "连续 ANR/无响应次数阈值：\n-0：禁用自动杀进程并重拉应用，仅记录 ANR。\n-正整数 N：连续 N 次 timeout_appear/timeout_disappear/error 后才触发自动重拉。\n示例：1=首次无响应即重拉；3=连续 3 次无响应才重拉。"
        )
        ToolTip(broadcast_tts_card, "广播模式：adb broadcast 发送Hint；TTS 模式：PC 端播放语音，设备麦克风接收。响应监控：仅基于 logcat 关键字与时间参数统计响应与展示时长。")

        # app.log 差异化采集配置
        app_log_card = self.create_card_grid(content, "🧾 App Log 精准采集", row=3, column=0, columnspan=2, sticky="ew", padx=0, pady=(0, 10))
        app_log_frame = tk.Frame(app_log_card, bg=UIColors.WHITE)
        app_log_frame.pack(fill=tk.X, padx=5, pady=5)
        app_log_frame.grid_columnconfigure(1, weight=1)
        app_log_frame.grid_columnconfigure(3, weight=1)

        app_log_enabled_cb = tk.Checkbutton(
            app_log_frame,
            text="启用 App Log 精准采集（推荐）",
            variable=getattr(self, "app_log_enabled_var", tk.BooleanVar(value=True)),
            bg=UIColors.WHITE,
            font=UIFonts.BODY,
            cursor="hand2",
        )
        app_log_enabled_cb.grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(2, 6))

        tk.Label(app_log_frame, text="额外包名(逗号分隔):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_extra_packages_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=1, column=1, sticky=tk.EW, padx=(8, 14), pady=4)
        tk.Label(app_log_frame, text="进程名(逗号分隔):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=2, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_include_process_names_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=1, column=3, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="包名-进程映射:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=2, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_package_process_map_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=2, column=1, columnspan=3, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="级别过滤:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=3, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_levels_var", tk.StringVar(value="VDIWEF")), font=UIFonts.BODY, width=14).grid(row=3, column=1, sticky=tk.W, padx=(8, 14), pady=4)
        tk.Label(app_log_frame, text="包含TAG(逗号):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=3, column=2, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_tags_include_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=3, column=3, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="排除TAG(逗号):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=4, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_tags_exclude_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=4, column=1, sticky=tk.EW, padx=(8, 14), pady=4)
        tk.Label(app_log_frame, text="包含关键词(逗号):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=4, column=2, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_keywords_include_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=4, column=3, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="排除关键词(逗号):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=5, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_keywords_exclude_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=5, column=1, sticky=tk.EW, padx=(8, 14), pady=4)
        tk.Label(app_log_frame, text="输出子目录:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=5, column=2, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_output_subdir_var", tk.StringVar(value="")), font=UIFonts.BODY).grid(row=5, column=3, sticky=tk.EW, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="单文件上限(MB):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=6, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_max_file_mb_var", tk.StringVar(value="50")), font=UIFonts.BODY, width=10).grid(row=6, column=1, sticky=tk.W, padx=(8, 14), pady=4)
        tk.Label(app_log_frame, text="备份份数:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=6, column=2, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_backup_count_var", tk.StringVar(value="3")), font=UIFonts.BODY, width=10).grid(row=6, column=3, sticky=tk.W, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="刷新PID秒:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=7, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_pid_refresh_seconds_var", tk.StringVar(value="2")), font=UIFonts.BODY, width=10).grid(row=7, column=1, sticky=tk.W, padx=(8, 14), pady=4)
        tk.Label(app_log_frame, text="批量行数:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=7, column=2, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_batch_lines_var", tk.StringVar(value="50")), font=UIFonts.BODY, width=10).grid(row=7, column=3, sticky=tk.W, padx=(8, 0), pady=4)

        tk.Label(app_log_frame, text="落盘周期(ms):", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=8, column=0, sticky=tk.W, pady=4)
        tk.Entry(app_log_frame, textvariable=getattr(self, "app_log_flush_interval_ms_var", tk.StringVar(value="500")), font=UIFonts.BODY, width=10).grid(row=8, column=1, sticky=tk.W, padx=(8, 14), pady=4)

        ToolTip(
            app_log_card,
            "App Log 精准采集：\n-默认监控当前 APK 进程，可附加多个包名与进程名。\n-支持级别/TAG/关键词过滤、文件轮转和实时落盘策略。\n-包名-进程映射格式示例：com.demo.app:main,remote;com.demo.other:worker。"
        )

        # 4) 测试选项
        opts_card = self.create_card_grid(content, "⚙️ 测试选项", row=4, column=1, sticky="nsew", padx=(10, 0), pady=(0, 10))
        opts = [
            ("建立性能基线", self.baseline_establish_var,
             "建立性能基线：\n-在本次测试结束后，将当前性能结果保存为基线。\n-适合在版本较稳定时执行，用于后续版本对比。"),
            ("与基线对比", self.baseline_compare_var,
             "与基线对比：\n-将本次测试结果与历史基线进行对比，生成对比报告。\n-建议在已有基线的前提下勾选。"),
            ("禁用Mock Server", self.no_mock_server_var,
             "禁用 Mock Server：\n-不再启用 Mock Server 注入或回放流量。\n-适合联调真实后端环境时使用。"),
            ("禁用网络代理", self.no_network_proxy_var,
             "禁用网络代理：\n-不通过 HTTP 代理转发流量。\n-避免与其他网络调试工具冲突。"),
            ("直接使用Fallback事件注入", self.use_fallback_only_var,
             "直接使用 Fallback 事件注入：\n-跳过 adb monkey，改用 adb input tap/swipe/key 等方式注入事件。\n-适合 Monkey 不稳定或不支持的环境。"),
        ]
        for i, (text, var, tip) in enumerate(opts):
            cb = tk.Checkbutton(
                opts_card,
                text=text,
                variable=var,
                bg=UIColors.WHITE,
                font=UIFonts.BODY,
                cursor="hand2",
            )
            cb.grid(row=i // 2, column=i % 2, sticky=tk.W, padx=6, pady=6)
            ToolTip(cb, tip)
        opts_card.grid_columnconfigure(0, weight=1)
        opts_card.grid_columnconfigure(1, weight=1)

        # 5) Monkey 遮罩区域（与稳定性强相关，也放在此子窗口中）
        mask_card = self.create_card_grid(content, "🔲 Monkey 遮罩区域（百分比 0.0 - 100.0）", row=4, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        mask_form = tk.Frame(mask_card, bg=UIColors.WHITE)
        mask_form.pack(fill=tk.X, pady=5)
        mask_form.grid_columnconfigure(1, weight=1)
        mask_form.grid_columnconfigure(3, weight=1)

        tk.Label(mask_form, text="上边缘:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=4)
        mask_top_entry = tk.Entry(mask_form, width=8, textvariable=self.monkey_mask_top_var, font=UIFonts.BODY)
        mask_top_entry.grid(row=0, column=1, sticky=tk.W, padx=(2, 10), pady=4)
        tk.Label(mask_form, text="%   下边缘:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=2, sticky=tk.W, pady=4)
        mask_bottom_entry = tk.Entry(mask_form, width=8, textvariable=self.monkey_mask_bottom_var, font=UIFonts.BODY)
        mask_bottom_entry.grid(row=0, column=3, sticky=tk.W, padx=(2, 10), pady=4)

        tk.Label(mask_form, text="左边缘:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=4)
        mask_left_entry = tk.Entry(mask_form, width=8, textvariable=self.monkey_mask_left_var, font=UIFonts.BODY)
        mask_left_entry.grid(row=1, column=1, sticky=tk.W, padx=(2, 10), pady=4)
        tk.Label(mask_form, text="%   右边缘:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=2, sticky=tk.W, pady=4)
        mask_right_entry = tk.Entry(mask_form, width=8, textvariable=self.monkey_mask_right_var, font=UIFonts.BODY)
        mask_right_entry.grid(row=1, column=3, sticky=tk.W, padx=(2, 10), pady=4)

        mask_tip = (
            "Monkey 遮罩区域（百分比 0.0–100.0）：\n"
            "-定义 Monkey 可点击区域相对于屏幕的上下左右边界百分比。\n"
            "-例如：上/下均为 10.0，左/右为 0.0，表示上下各保留 10% 不点击，中间 80% 为可点击区。\n"
            "-建议保留 5–10% 以避免点到状态栏、导航栏等系统区域。"
        )
        for w in (mask_top_entry, mask_bottom_entry, mask_left_entry, mask_right_entry):
            ToolTip(w, mask_tip)

        self.create_action_button(
            mask_form,
            text="🔍 生成当前遮罩预览",
            command=self.preview_monkey_mask_overlay,
            variant="info",
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=(6, 2))
        self.create_action_button(
            mask_form,
            text="🖼️ 打开最近遮罩图",
            command=self.open_latest_safe_region_overlay,
            variant="secondary",
        ).grid(row=2, column=2, columnspan=2, sticky=tk.W, pady=(6, 2), padx=(10, 0))

    def open_mock_server_config_dialog(self):
        if getattr(self, "_mock_server_cfg_win", None) and tk.Toplevel.winfo_exists(self._mock_server_cfg_win):
            self._mock_server_cfg_win.lift()
            return

        win = tk.Toplevel(self.root)
        self._mock_server_cfg_win = win
        win.title("Mock Server 配置")
        win.configure(bg=UIColors.BG_LIGHT)
        win.minsize(600, 300)

        frame = tk.Frame(win, bg=UIColors.BG_LIGHT)
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        card = self.create_card_grid(frame, "🧪 Mock Server - 连接与规则", row=0, column=0, sticky="nsew")
        form = tk.Frame(card, bg=UIColors.WHITE)
        form.pack(fill=tk.X, pady=5)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="Host:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=6)
        tk.Entry(form, textvariable=self.mock_host_var, font=UIFonts.BODY).grid(
            row=0, column=1, sticky=tk.EW, pady=6, padx=(10, 0)
        )

        tk.Label(form, text="Port:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=1, column=0, sticky=tk.W, pady=6)
        tk.Entry(form, textvariable=self.mock_port_var, font=UIFonts.BODY).grid(
            row=1, column=1, sticky=tk.EW, pady=6, padx=(10, 0)
        )

        tk.Label(form, text="规则文件:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=2, column=0, sticky=tk.W, pady=6)
        path_row = tk.Frame(form, bg=UIColors.WHITE)
        path_row.grid(row=2, column=1, sticky=tk.EW, pady=6, padx=(10, 0))
        path_row.grid_columnconfigure(0, weight=1)
        tk.Entry(path_row, textvariable=self.mock_rules_path_var, font=UIFonts.BODY).grid(
            row=0, column=0, sticky=tk.EW
        )
        self.create_action_button(
            path_row,
            text="编辑",
            command=self.open_mock_rules_editor,
            variant="primary",
        ).grid(row=0, column=1, padx=(8, 0))

    def open_performance_monitor_config_dialog(self):
        if getattr(self, "_perf_monitor_cfg_win", None) and tk.Toplevel.winfo_exists(self._perf_monitor_cfg_win):
            self._perf_monitor_cfg_win.lift()
            return

        win = tk.Toplevel(self.root)
        self._perf_monitor_cfg_win = win
        win.title("性能监控配置")
        win.configure(bg=UIColors.BG_LIGHT)
        win.minsize(600, 300)

        frame = tk.Frame(win, bg=UIColors.BG_LIGHT)
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        card = self.create_card_grid(frame, "⚡ 响应延迟测试配置", row=0, column=0, sticky="nsew")
        form = tk.Frame(card, bg=UIColors.WHITE)
        form.pack(fill=tk.X, pady=5)
        form.grid_columnconfigure(1, weight=1)

        tk.Label(form, text="可点击元素列表:", font=UIFonts.BODY, bg=UIColors.WHITE).grid(row=0, column=0, sticky=tk.W, pady=6)
        tk.Entry(form, textvariable=self.performance_clickable_elements_var, font=UIFonts.BODY).grid(
            row=0, column=1, sticky=tk.EW, pady=6, padx=(10, 0)
        )

        hint_text = "多个元素用逗号分隔，例如：AI Power,智能体广场,对话收藏\n每次测试会随机选择与上次不同的元素"
        tk.Label(
            form,
            text=hint_text,
            bg=UIColors.WHITE,
            fg=UIColors.TEXT_SECONDARY,
            font=UIFonts.CAPTION,
            justify=tk.LEFT,
            anchor="nw",
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(0, 6), padx=(0, 10))


def main():
    """主函数"""
    try:
        # 优先使用ttkbootstrap主题窗口
        if HAS_TTKBOOTSTRAP:
            root = ttkb.Window(themename="flatly")  # 主题可替换：cosmo / flatly / journal / minty等
        else:
            root = tk.Tk()
        # 默认启动即最大化，方便查看完整界面（保持跨平台兼容，Windows 用 zoomed）
        try:
            root.state('zoomed')
        except Exception:
            try:
                root.attributes('-zoomed', True)
            except Exception:
                pass
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