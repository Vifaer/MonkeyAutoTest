from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Optional
from pathlib import Path

import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
import subprocess
import re

from gui.toolkit import UIColors, UIFONTS, ToolTip
from infra.adb import run_shell
from infra.device_control.mirror_runner import ScrcpyMirrorParams, ScrcpyMirrorRunner
from infra.device_control.record_session import RecordParams, RecordSession


def _safe_int(v: str, default: int) -> int:
    try:
        n = int(str(v).strip())
        return n if n > 0 else default
    except Exception:
        return default


def _timestamp_basename() -> str:
    return "record_" + datetime.now().strftime("%Y%m%d_%H%M%S")


_DSHOW_AUTO_LABEL = "自动(按识别候选)"


def _refresh_dshow_devices(gui: object, combo: ttk.Combobox, refresh_btn: Optional[tk.Button] = None) -> None:
    """
    列出可用 dshow 音频输入设备并填充到下拉框。
    运行在后台线程，避免卡 UI。
    """

    def _ui_set_busy(is_busy: bool, status_text: str = "") -> None:
        try:
            if refresh_btn is not None:
                refresh_btn.config(state="disabled" if is_busy else "normal")
                if status_text:
                    refresh_btn.config(text=status_text)
        except Exception:
            pass

    def _worker() -> None:
        _ui_set_busy(True)
        try:
            # ffmpeg 不再由 GUI 提供配置项；录屏/设备枚举默认使用 tools/ffmpeg.exe
            ffmpeg_bin = str(Path("tools") / "ffmpeg.exe")
            if not Path(ffmpeg_bin).exists():
                ffmpeg_bin = "ffmpeg"

            probe = subprocess.run(
                [ffmpeg_bin, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                check=False,
            )
            text = (probe.stderr or b"").decode("utf-8", errors="replace")

            names: list[str] = []
            for line in text.splitlines():
                if "(audio)" not in line:
                    continue
                m = re.search(r'"([^"]+)"', line)
                if not m:
                    continue
                name = m.group(1).strip()
                if not name:
                    continue
                if name not in names:
                    names.append(name)

            values = [_DSHOW_AUTO_LABEL, "default"] + names

            def _ui() -> None:
                try:
                    combo["values"] = values
                    # 若当前值不在 candidates 中，则回退到自动
                    cur = ""
                    try:
                        cur = combo.get()
                    except Exception:
                        cur = ""
                    if not cur or cur not in values:
                        if hasattr(gui, "pc_dshow_audio_device_var"):
                            getattr(gui, "pc_dshow_audio_device_var").set(_DSHOW_AUTO_LABEL)
                        else:
                            combo.set(_DSHOW_AUTO_LABEL)
                finally:
                    _ui_set_busy(False)

            try:
                gui.root.after(0, _ui)
            except Exception:
                _ui()
        except Exception as e:
            try:
                gui.root.after(
                    0,
                    lambda: (
                        messagebox.showerror("错误", f"dshow 设备枚举失败: {e}"),
                        _ui_set_busy(False),
                    ),
                )
            except Exception:
                try:
                    messagebox.showerror("错误", f"dshow 设备枚举失败: {e}")
                except Exception:
                    pass

    # start background thread
    threading.Thread(target=_worker, daemon=True).start()


def create_device_control_tab_ui(gui: object, parent: tk.Frame) -> None:
    """
    Build the "设备控制" tab UI.

    Notes:
    - `gui` is expected to be MonkeyTestGUI instance (duck typing).
    - This module only handles UI and calling infra runners.
    """

    # Ensure parent has a sensible background.
    try:
        parent.configure(bg=UIColors.BG_LIGHT)
    except Exception:
        pass

    container = tk.Frame(parent, bg=UIColors.BG_LIGHT)
    container.pack(fill=tk.BOTH, expand=True)

    # -------------------------
    # 投屏 / 触控
    # -------------------------
    mirror_card = gui.create_card(container, "📱 投屏/触控")

    # Device status row
    sn_row = tk.Frame(mirror_card, bg=UIColors.WHITE)
    sn_row.pack(fill=tk.X, pady=(0, 8))

    tk.Label(
        sn_row,
        text="当前设备SN:",
        font=UIFONTS.BODY,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
    ).pack(side=tk.LEFT, padx=(0, 10))

    sn_display = tk.Label(
        sn_row,
        textvariable=gui.device_sn_var,
        font=UIFONTS.BODY,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_PRIMARY,
        anchor="w",
        justify=tk.LEFT,
    )
    sn_display.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # scrcpy path row
    scrcpy_row = tk.Frame(mirror_card, bg=UIColors.WHITE)
    scrcpy_row.pack(fill=tk.X, pady=(0, 8))

    tk.Label(
        scrcpy_row,
        text="scrcpy路径(可空走PATH):",
        font=UIFONTS.BODY,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
    ).pack(side=tk.LEFT, padx=(0, 10))

    scrcpy_entry = ttk.Entry(scrcpy_row, textvariable=gui.scrcpy_path_var)
    scrcpy_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ToolTip(scrcpy_entry, "不填则使用系统环境变量 PATH 查找 scrcpy.exe。")

    # Buttons
    btn_row = tk.Frame(mirror_card, bg=UIColors.WHITE)
    btn_row.pack(fill=tk.X, pady=(0, 8))

    mirror_start_btn = gui.create_action_button(
        btn_row,
        text="▶️ 开始投屏",
        command=lambda: _start_mirror(gui, mirror_start_btn, mirror_stop_btn),
        variant="primary",
        width=12,
    )
    mirror_start_btn.pack(side=tk.LEFT, padx=(0, 10))

    mirror_stop_btn = gui.create_action_button(
        btn_row,
        text="⏹ 停止投屏",
        command=lambda: _stop_mirror(gui, mirror_start_btn, mirror_stop_btn),
        variant="error",
        width=12,
    )
    mirror_stop_btn.pack(side=tk.LEFT)
    mirror_stop_btn.config(state="disabled")

    # -------------------------
    # 录屏（双路 scrcpy + logcat + ffmpeg 混音）
    # -------------------------
    record_card = gui.create_card(container, "🎥 录屏（系统音 + 麦克风 + 日志）")

    output_row = tk.Frame(record_card, bg=UIColors.WHITE)
    output_row.pack(fill=tk.X, pady=(0, 6))

    tk.Label(
        output_row,
        text="录制文件名:",
        font=UIFONTS.BODY,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
    ).pack(side=tk.LEFT, padx=(0, 10))

    record_basename_entry = ttk.Entry(record_card, textvariable=gui.record_basename_var)
    record_basename_entry.pack(fill=tk.X, padx=0, pady=(0, 6))
    ToolTip(record_basename_entry, "不填将自动使用时间戳：record_YYYYMMDD_HHMMSS")

    # records dir (fixed)
    records_dir_label = tk.Label(
        record_card,
        text=f"输出目录：{getattr(gui, 'records_dir_var', tk.StringVar(value='records')).get() if hasattr(gui, 'records_dir_var') else 'records'}",
        font=UIFONTS.CAPTION,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
        anchor="w",
    )
    records_dir_label.pack(fill=tk.X, padx=0, pady=(0, 6))

    options_frame = tk.Frame(record_card, bg=UIColors.WHITE)
    options_frame.pack(fill=tk.X, pady=(0, 8))

    clear_logcat_cb = tk.Checkbutton(
        options_frame,
        text="开始录制前清空 logcat（风险：可能影响并行稳定性采集）",
        variable=gui.logcat_clear_on_record_start_var,
        bg=UIColors.WHITE,
        font=UIFONTS.BODY,
        cursor="hand2",
        wraplength=430,
        justify=tk.LEFT,
    )
    clear_logcat_cb.pack(anchor="w", padx=0, pady=(0, 6))

    delete_tmp_cb = tk.Checkbutton(
        options_frame,
        text="停止录制后删除临时文件（video/mic/logcat）",
        variable=gui.delete_tmp_after_record_var,
        bg=UIColors.WHITE,
        font=UIFONTS.BODY,
        cursor="hand2",
        wraplength=430,
        justify=tk.LEFT,
    )
    delete_tmp_cb.pack(anchor="w", padx=0, pady=(0, 6))

    mic_use_pc_cb = tk.Checkbutton(
        options_frame,
        # 语义与 RecordSession 入参做反向映射（见 _start_recording）
        text="录音麦克风：设备麦克风(scrcpy)（可能影响设备外放；不勾选则使用电脑麦克风(dshow)/环境声）",
        variable=gui.mic_use_pc_var,
        bg=UIColors.WHITE,
        font=UIFONTS.BODY,
        cursor="hand2",
        wraplength=430,
        justify=tk.LEFT,
    )
    mic_use_pc_cb.pack(anchor="w", padx=0, pady=(0, 6))

    dshow_audio_frame = tk.Frame(options_frame, bg=UIColors.WHITE)
    dshow_audio_frame.pack(fill=tk.X, pady=(0, 6))

    tk.Label(
        dshow_audio_frame,
        text="dshow 音频源设备：",
        font=UIFONTS.BODY,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
        anchor="w",
    ).pack(side=tk.LEFT, padx=(0, 10))

    auto_label = "自动(按识别候选)"
    # 默认先给一个最常见值，避免下拉为空
    dshow_values = [auto_label, "default"]
    dshow_audio_combo = ttk.Combobox(
        dshow_audio_frame,
        textvariable=gui.pc_dshow_audio_device_var,
        values=dshow_values,
        state="readonly",
        width=44,
    )
    dshow_audio_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

    refresh_btn = gui.create_action_button(
        dshow_audio_frame,
        text="刷新dshow设备",
        command=lambda: _refresh_dshow_devices(gui, dshow_audio_combo, refresh_btn),
        variant="secondary",
        width=12,
    )
    refresh_btn.pack(side=tk.LEFT, padx=(10, 0))

    def _toggle_dshow_state() -> None:
        # mic_use_pc_var 勾选：使用设备麦克风(scrcpy)
        # 未勾选：使用电脑端 dshow（避免设备麦克风对外放音频的潜在干扰）
        use_pc_mic = not bool(getattr(gui, "mic_use_pc_var").get())
        try:
            dshow_audio_combo.config(state="readonly" if use_pc_mic else "disabled")
        except Exception:
            pass
        try:
            refresh_btn.config(state="normal" if use_pc_mic else "disabled")
        except Exception:
            pass

    # 初始状态 + 响应勾选变化
    mic_use_pc_cb.config(command=_toggle_dshow_state)
    _toggle_dshow_state()

    # Record params
    params_frame = tk.Frame(record_card, bg=UIColors.WHITE)
    params_frame.pack(fill=tk.X, pady=(0, 6))

    max_fps_row = tk.Frame(params_frame, bg=UIColors.WHITE)
    max_fps_row.pack(fill=tk.X, pady=(0, 6))
    tk.Label(max_fps_row, text="max_fps(默认30):", font=UIFONTS.BODY, bg=UIColors.WHITE, fg=UIColors.TEXT_SECONDARY).pack(
        side=tk.LEFT, padx=(0, 10)
    )
    max_fps_entry = ttk.Entry(max_fps_row, textvariable=gui.record_max_fps_var, width=8)
    max_fps_entry.pack(side=tk.LEFT)

    vbr_row = tk.Frame(params_frame, bg=UIColors.WHITE)
    vbr_row.pack(fill=tk.X, pady=(0, 6))
    tk.Label(vbr_row, text="video_bit_rate(默认8M):", font=UIFONTS.BODY, bg=UIColors.WHITE, fg=UIColors.TEXT_SECONDARY).pack(
        side=tk.LEFT, padx=(0, 10)
    )
    vbr_entry = ttk.Entry(vbr_row, textvariable=gui.record_video_bit_rate_var)
    vbr_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    max_size_row = tk.Frame(params_frame, bg=UIColors.WHITE)
    max_size_row.pack(fill=tk.X, pady=(0, 6))
    tk.Label(max_size_row, text="max_size(可空):", font=UIFONTS.BODY, bg=UIColors.WHITE, fg=UIColors.TEXT_SECONDARY).pack(
        side=tk.LEFT, padx=(0, 10)
    )
    max_size_entry = ttk.Entry(max_size_row, textvariable=gui.record_max_size_var)
    max_size_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ToolTip(max_size_entry, "例如：1280 或 1920（scrcpy 支持格式）。留空则使用默认。")

    record_btn_row = tk.Frame(record_card, bg=UIColors.WHITE)
    record_btn_row.pack(fill=tk.X, pady=(0, 8))

    record_start_btn = gui.create_action_button(
        record_btn_row,
        text="⏺ 开始录制",
        command=lambda: _start_recording(gui, record_start_btn, record_stop_btn),
        variant="success",
        width=12,
    )
    record_start_btn.pack(side=tk.LEFT, padx=(0, 10))

    record_stop_btn = gui.create_action_button(
        record_btn_row,
        text="⏹ 停止录制并合成",
        command=lambda: _stop_recording(gui, record_start_btn, record_stop_btn),
        variant="error",
        width=18,
    )
    record_stop_btn.pack(side=tk.LEFT)
    record_stop_btn.config(state="disabled")

    record_status_var = tk.StringVar(value="未录制")
    record_status_label = tk.Label(
        record_card,
        textvariable=record_status_var,
        font=UIFONTS.CAPTION,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
        anchor="w",
        justify=tk.LEFT,
    )
    record_status_label.pack(fill=tk.X, pady=(0, 6))

    gui._device_control_record_status_var = record_status_var
    gui._device_control_record_status_label = record_status_label

    # 合成完成后的快速访问按钮/路径
    final_actions_frame = tk.Frame(record_card, bg=UIColors.WHITE)
    final_actions_frame.pack(fill=tk.X, pady=(0, 6))

    open_dir_btn = gui.create_action_button(
        final_actions_frame,
        text="打开录制目录",
        command=lambda: None,
        variant="secondary",
        width=14,
    )
    open_dir_btn.pack(side=tk.LEFT, padx=(0, 10))
    open_dir_btn.config(state="disabled")

    play_video_btn = gui.create_action_button(
        final_actions_frame,
        text="播放视频",
        command=lambda: None,
        variant="secondary",
        width=10,
    )
    play_video_btn.pack(side=tk.LEFT)
    play_video_btn.config(state="disabled")

    final_path_var = tk.StringVar(value="")
    final_path_label = tk.Label(
        record_card,
        textvariable=final_path_var,
        font=UIFONTS.BODY,
        bg=UIColors.WHITE,
        fg=UIColors.TEXT_SECONDARY,
        anchor="w",
        justify=tk.LEFT,
        wraplength=520,
    )
    final_path_label.pack(fill=tk.X, pady=(0, 6))

    gui._device_control_record_final_path_var = final_path_var
    gui._device_control_open_dir_btn = open_dir_btn
    gui._device_control_play_video_btn = play_video_btn


def _start_mirror(gui: object, mirror_start_btn: tk.Button, mirror_stop_btn: tk.Button) -> None:
    serial = str(getattr(gui, "device_sn_var").get() or "").strip()  # type: ignore[union-attr]
    if not serial:
        messagebox.showwarning("提示", "请先填写设备序列号")
        return

    def _worker() -> None:
        try:
            try:
                getattr(gui, "_ensure_adb_env")()
            except Exception:
                pass

            scrcpy_params = ScrcpyMirrorParams(
                max_fps=_safe_int(getattr(gui, "record_max_fps_var").get(), 30),  # type: ignore[union-attr]
                video_bit_rate=str(getattr(gui, "record_video_bit_rate_var").get() or "8M"),  # type: ignore[union-attr]
                max_size=str(getattr(gui, "record_max_size_var").get() or "") or None,  # type: ignore[union-attr]
            )

            gui._mirror_runner = ScrcpyMirrorRunner(
                serial=serial,
                adb_path=str(getattr(gui, "adb_path_var").get() or ""),  # type: ignore[union-attr]
                scrcpy_path=str(getattr(gui, "scrcpy_path_var").get() or ""),  # type: ignore[union-attr]
                window_title="MonkeyAutoTest - 投屏",
                params=scrcpy_params,
                log_callback=lambda msg: getattr(gui, "log_queue").put(msg),
            )
            gui._mirror_runner.start()

            gui.root.after(0, lambda: (mirror_start_btn.config(state="disabled"), mirror_stop_btn.config(state="normal")))
            gui.root.after(0, lambda: gui.update_status("投屏已启动"))
        except Exception as e:
            gui.root.after(0, lambda: gui.update_status(f"投屏启动失败: {e}"))

    threading.Thread(target=_worker, daemon=True).start()


def _stop_mirror(gui: object, mirror_start_btn: tk.Button, mirror_stop_btn: tk.Button) -> None:
    runner: Optional[ScrcpyMirrorRunner] = getattr(gui, "_mirror_runner", None)
    if not runner:
        return
    try:
        runner.stop()
    except Exception:
        pass

    mirror_start_btn.config(state="normal")
    mirror_stop_btn.config(state="disabled")
    try:
        gui.update_status("投屏已停止")
    except Exception:
        pass


def _start_recording(gui: object, record_start_btn: tk.Button, record_stop_btn: tk.Button) -> None:
    serial = str(getattr(gui, "device_sn_var").get() or "").strip()  # type: ignore[union-attr]
    if not serial:
        messagebox.showwarning("提示", "请先填写设备序列号")
        return

    pkg = str(getattr(gui, "package_name_var").get() or "").strip()  # type: ignore[union-attr]
    if not pkg:
        messagebox.showwarning("提示", "请先选择设备上已安装的应用包名（用于精准采集 app.log）")
        return

    def _worker() -> None:
        try:
            try:
                getattr(gui, "_ensure_adb_env")()
            except Exception:
                pass

            basename = str(getattr(gui, "record_basename_var").get() or "").strip()  # type: ignore[union-attr]
            if not basename:
                basename = _timestamp_basename()

            # Disable buttons immediately (UI thread schedule).
            gui.root.after(0, lambda: record_start_btn.config(state="disabled"))
            gui.root.after(0, lambda: record_stop_btn.config(state="normal"))

            gui.root.after(0, lambda: getattr(gui, "_device_control_record_status_var").set(f"录制中：{basename}"))
            gui.root.after(0, lambda: gui.update_status(f"开始录制：{basename}"))
            gui.root.after(
                0,
                lambda: (
                    getattr(gui, "_device_control_record_final_path_var", tk.StringVar(value="")).set(""),
                    (getattr(gui, "_device_control_open_dir_btn", None).config(state="disabled") if getattr(gui, "_device_control_open_dir_btn", None) else None),
                    (getattr(gui, "_device_control_play_video_btn", None).config(state="disabled") if getattr(gui, "_device_control_play_video_btn", None) else None),
                ),
            )

            params = RecordParams(
                max_fps=_safe_int(getattr(gui, "record_max_fps_var").get(), 30),  # type: ignore[union-attr]
                video_bit_rate=str(getattr(gui, "record_video_bit_rate_var").get() or "8M"),  # type: ignore[union-attr]
                max_size=str(getattr(gui, "record_max_size_var").get() or "") or None,  # type: ignore[union-attr]
            )

            # 录屏输出目录对齐：优先复用稳定性测试 run_log_dir（与 app.log 同目录）
            # 稳定性实时报告文件名 ts 格式：YYYYMMDD_HHMMSS（带下划线），目录名要求不带下划线。
            run_log_dir_override = ""
            try:
                live_report_path = (getattr(gui, "_current_live_report_path", "") or "").strip()
                if live_report_path and os.path.exists(live_report_path):
                    base = os.path.basename(live_report_path)
                    m = re.match(r"^(?P<sn>[^_]+)_.+_(?P<ts>\\d{8}_\\d{6})\\.html$", base)
                    if m:
                        ts_with_us = (m.group("ts") or "").strip()
                        ts_no_us = ts_with_us.replace("_", "")
                        # 按 plan：sn 使用当前 GUI 的 device_sn_var（即当前录制目标）
                        run_log_dir_override = os.path.join("logs", serial, ts_no_us)
            except Exception:
                run_log_dir_override = ""

            if not run_log_dir_override:
                # 无实时报告时：按录制开始时间创建新的 run_log_dir
                ts_no_us = datetime.now().strftime("%Y%m%d%H%M%S")
                run_log_dir_override = os.path.join("logs", serial, ts_no_us)

            try:
                os.makedirs(run_log_dir_override, exist_ok=True)
            except Exception:
                # 若创建目录失败，交由 RecordSession 自行兜底（仍尽力写入）
                pass

            def _on_finished(final_path: str) -> None:
                def _ui() -> None:
                    record_stop_btn.config(state="disabled")
                    record_start_btn.config(state="normal")
                    if final_path:
                        # 展示最终路径 + 提供一键打开目录/播放
                        try:
                            getattr(gui, "_device_control_record_status_var").set("录制完成（已合成）")
                        except Exception:
                            pass
                        try:
                            getattr(gui, "_device_control_record_final_path_var").set(f"最终视频：{final_path}")
                        except Exception:
                            pass

                        try:
                            open_btn = getattr(gui, "_device_control_open_dir_btn", None)
                            if open_btn:
                                final_dir = os.path.dirname(final_path) or ""
                                open_btn.config(
                                    state="normal",
                                    command=lambda p=final_dir: os.startfile(p) if p and os.path.exists(p) else None,
                                )
                        except Exception:
                            pass

                        try:
                            play_btn = getattr(gui, "_device_control_play_video_btn", None)
                            if play_btn:
                                play_btn.config(
                                    state="normal",
                                    command=lambda p=final_path: os.startfile(p) if p and os.path.exists(p) else None,
                                )
                        except Exception:
                            pass
                        gui.update_status("录制完成（已合成）")
                    else:
                        try:
                            getattr(gui, "_device_control_record_status_var").set("合成失败（请查看实时日志）")
                        except Exception:
                            pass
                        try:
                            getattr(gui, "_device_control_record_final_path_var").set("合成失败：最终视频未生成")
                        except Exception:
                            pass
                        try:
                            open_btn = getattr(gui, "_device_control_open_dir_btn", None)
                            if open_btn:
                                open_btn.config(state="disabled", command=lambda: None)
                        except Exception:
                            pass
                        try:
                            play_btn = getattr(gui, "_device_control_play_video_btn", None)
                            if play_btn:
                                play_btn.config(state="disabled", command=lambda: None)
                        except Exception:
                            pass
                        gui.update_status("录制结束但合成失败")

                try:
                    gui.root.after(0, _ui)
                except Exception:
                    pass

            session = RecordSession(
                serial=serial,
                adb_path=str(getattr(gui, "adb_path_var").get() or ""),  # type: ignore[union-attr]
                scrcpy_path=str(getattr(gui, "scrcpy_path_var").get() or ""),  # type: ignore[union-attr]
                ffmpeg_path=str(Path("tools") / "ffmpeg.exe"),
                record_basename=basename,
                output_dir="logs",
                clear_logcat_on_start=bool(getattr(gui, "logcat_clear_on_record_start_var").get()),  # type: ignore[union-attr]
                delete_tmp_after_record=bool(getattr(gui, "delete_tmp_after_record_var").get()),  # type: ignore[union-attr]
                # mic_use_pc_var=False 时不使用设备麦克风：RecordSession mic_use_pc=True (= PC dshow)
                mic_use_pc=not bool(getattr(gui, "mic_use_pc_var").get()),  # type: ignore[union-attr]
                pc_dshow_audio_device=str(getattr(gui, "pc_dshow_audio_device_var").get() or ""),  # type: ignore[union-attr]
                package_name=pkg,
                app_log_config=getattr(gui, "_get_app_log_for_config")(),
                record_params=params,
                run_log_dir=run_log_dir_override,
                log_callback=lambda msg: getattr(gui, "log_queue").put(msg),
                on_finished=_on_finished,
            )

            gui._record_session = session
            session.start()
            if not session.is_running():
                raise RuntimeError("录制会话启动失败（可能无法创建 app.log 或其它资源）")
        except Exception as e:
            gui.root.after(0, lambda: record_start_btn.config(state="normal"))
            gui.root.after(0, lambda: record_stop_btn.config(state="disabled"))
            gui.root.after(0, lambda: gui.update_status(f"录制启动失败: {e}"))

    # Start in background because scrcpy/logcat process creation may take a moment.
    threading.Thread(target=_worker, daemon=True).start()


def _stop_recording(gui: object, record_start_btn: tk.Button, record_stop_btn: tk.Button) -> None:
    session: Optional[RecordSession] = getattr(gui, "_record_session", None)
    if not session:
        return

    # Disable to prevent double stop
    record_stop_btn.config(state="disabled")
    record_start_btn.config(state="disabled")
    try:
        getattr(gui, "_device_control_record_status_var").set("停止中：合成中...")
    except Exception:
        pass
    try:
        gui.update_status("停止录制，合成中...")
    except Exception:
        pass

    try:
        session.stop()
    except Exception as e:
        gui.log_queue.put(f"[record] 停止失败: {e}")
        gui.root.after(0, lambda: record_start_btn.config(state="normal"))
        gui.root.after(0, lambda: record_stop_btn.config(state="disabled"))

