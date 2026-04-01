from __future__ import annotations

import json
import os
import mmap
import re
import subprocess
import threading
import time
import signal
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional


def _taskkill_tree(pid: int) -> None:
    """Windows only: kill a process tree by PID."""
    if pid <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/pid", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        return


def _graceful_stop_scrcpy(
    popen: Optional[subprocess.Popen[bytes]],
    *,
    log_callback: Callable[[str], None],
    name: str,
    wait_seconds: float = 3.0,
) -> None:
    """Best-effort graceful stop for scrcpy before force-kill fallback."""
    if not popen:
        return
    try:
        if popen.poll() is not None:
            return
    except Exception:
        return

    pid = int(getattr(popen, "pid", 0) or 0)
    if pid <= 0:
        return

    # Windows: use CTRL_BREAK_EVENT to let scrcpy flush/close recorder.
    # This avoids frequent mp4 corruption ("moov atom not found") caused by hard kill.
    try:
        os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        popen.wait(timeout=max(0.8, float(wait_seconds)))
        return
    except Exception:
        pass

    try:
        log_callback(f"[record] {name} 优雅停止超时，回退 taskkill 强制结束")
    except Exception:
        pass
    _taskkill_tree(pid)


def _graceful_stop_ffmpeg_recorder(
    popen: Optional[subprocess.Popen[bytes]],
    *,
    log_callback: Callable[[str], None],
    name: str,
    wait_seconds: float = 3.0,
) -> None:
    """Try to stop ffmpeg recorder by sending 'q', fallback to force kill."""
    if not popen:
        return
    try:
        if popen.poll() is not None:
            return
    except Exception:
        return

    try:
        if popen.stdin:
            popen.stdin.write(b"q\n")
            popen.stdin.flush()
    except Exception:
        pass

    try:
        popen.wait(timeout=max(0.8, float(wait_seconds)))
        return
    except Exception:
        pass

    pid = int(getattr(popen, "pid", 0) or 0)
    if pid > 0:
        try:
            log_callback(f"[record] {name} 优雅停止超时，回退 taskkill 强制结束")
        except Exception:
            pass
        _taskkill_tree(pid)


def _start_output_reader(
    popen: subprocess.Popen[bytes],
    log_callback: Callable[[str], None],
    line_callback: Optional[Callable[[str], None]] = None,
) -> threading.Thread:
    def _worker() -> None:
        if not popen.stdout:
            return

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

        for raw in iter(popen.stdout.readline, b""):
            if not raw:
                break
            line = _decode_line(raw).rstrip("\r\n")
            if line:
                try:
                    log_callback(line)
                except Exception:
                    pass
                if line_callback:
                    try:
                        line_callback(line)
                    except Exception:
                        pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


def _resolve_adb_bin() -> str:
    """Resolve adb executable from env / project tools / PATH."""
    try:
        # Internal helper in utils/timeout_command.
        from utils.timeout_command import _resolve_adb_path  # type: ignore

        p = _resolve_adb_path()
        return p or "adb"
    except Exception:
        return os.environ.get("ADB_PATH", "").strip() or "adb"


def _parse_filter_template(template: str) -> list[str]:
    """Split a logcat filter template by whitespace, e.g. '*:E *:W'."""
    parts = (template or "").strip().split()
    # Fallback: keep original if blank
    return parts or ["*:E", "*:W"]


def _resolve_ffprobe_bin(ffmpeg_bin: str) -> Optional[str]:
    """Prefer ffprobe.exe next to ffmpeg.exe when present."""
    try:
        p = Path(ffmpeg_bin)
        if p.name.lower() == "ffmpeg.exe":
            cand = p.parent / "ffprobe.exe"
            if cand.is_file():
                return str(cand)
    except Exception:
        pass
    return None


def _probe_video_and_duration(path: Path, ffmpeg_bin: str) -> tuple[bool, float]:
    """
    Return (has_video_stream, duration_seconds).
    Prefer ffprobe JSON; fallback to parsing `ffmpeg -i` stderr.
    """
    ffprobe = _resolve_ffprobe_bin(ffmpeg_bin)
    if ffprobe:
        try:
            r = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=120,
            )
            if r.returncode == 0 and r.stdout:
                data = json.loads(r.stdout.decode("utf-8", errors="replace"))
                streams = data.get("streams") or []
                has_video = any(s.get("codec_type") == "video" for s in streams)
                dur = 0.0
                try:
                    dur = float((data.get("format") or {}).get("duration") or 0)
                except Exception:
                    dur = 0.0
                if dur <= 0:
                    for s in streams:
                        try:
                            d2 = float(s.get("duration") or 0)
                            if d2 > 0:
                                dur = max(dur, d2)
                        except Exception:
                            pass
                return has_video, max(0.0, dur)
        except Exception:
            pass

    try:
        r = subprocess.run(
            [ffmpeg_bin, "-hide_banner", "-i", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
            timeout=120,
        )
        err = (r.stderr or b"").decode("utf-8", errors="replace")
        has_video = bool(re.search(r"Stream\s+#\d+:\d+.*:\s*Video", err, re.I))
        dur = 0.0
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+)(?:\.(\d+))?", err)
        if m:
            h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            frac = m.group(4) or ""
            subsec = 0.0
            if frac.isdigit():
                try:
                    subsec = int(frac) / (10 ** len(frac))
                except Exception:
                    subsec = 0.0
            dur = h * 3600 + mn * 60 + s + subsec
        return has_video, max(0.0, dur)
    except Exception:
        return False, 0.0


def _probe_stream_start_time(path: Path, ffmpeg_bin: str, *, codec_type: str) -> float:
    """Probe first stream start_time for given codec_type (video/audio)."""
    ffprobe = _resolve_ffprobe_bin(ffmpeg_bin)
    if ffprobe:
        try:
            r = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_streams",
                    "-show_format",
                    str(path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=120,
            )
            if r.returncode == 0 and r.stdout:
                data = json.loads(r.stdout.decode("utf-8", errors="replace"))
                streams = data.get("streams") or []
                for s in streams:
                    if s.get("codec_type") != codec_type:
                        continue
                    try:
                        st = float(s.get("start_time"))
                        return st
                    except Exception:
                        pass
                try:
                    return float((data.get("format") or {}).get("start_time") or 0.0)
                except Exception:
                    return 0.0
        except Exception:
            pass
    return 0.0


@dataclass(frozen=True)
class RecordParams:
    max_fps: Optional[int] = None
    video_bit_rate: Optional[str] = None
    max_size: Optional[str] = None


class RecordSession:
    """
    Record device screen with:
    1) system audio + video (scrcpy #1)
    2) mic/environment audio (scrcpy #2 or PC dshow if mic_use_pc)
    3) precise app.log capture (StressMonitor PID + filter)
    4) ffmpeg mix + mux on stop
    """
    _MIN_VALID_MIC_BYTES = 20 * 1024
    _MIN_VALID_SYS_AUDIO_BYTES = 20 * 1024

    def __init__(
        self,
        *,
        serial: str,
        adb_path: str,
        scrcpy_path: str,
        ffmpeg_path: str,
        record_basename: str,
        output_dir: str,
        run_log_dir: Optional[str] = None,
        log_filter_template: str = "*:E *:W",
        clear_logcat_on_start: bool = False,
        delete_tmp_after_record: bool = True,
        package_name: str = "",
        mic_use_pc: bool = False,
        pc_dshow_audio_device: str = "",
        app_log_config: Optional[dict[str, Any]] = None,
        record_params: Optional[RecordParams] = None,
        audio_sample_rate: int = 44100,
        audio_bit_rate: str = "192k",
        audio_sync_offset_ms: int = 0,
        log_callback: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[str], None]] = None,
        post_delay_seconds: float = 5.0,
    ) -> None:
        self.serial = serial
        self.adb_path = adb_path
        self.scrcpy_path = scrcpy_path
        self.ffmpeg_path = ffmpeg_path
        self.record_basename = record_basename
        self.output_dir = output_dir
        self._run_log_dir_override = Path((run_log_dir or "").strip()) if run_log_dir and str(run_log_dir).strip() else None
        self.log_filter_template = log_filter_template
        self.clear_logcat_on_start = clear_logcat_on_start
        self.delete_tmp_after_record = delete_tmp_after_record
        self.package_name = package_name.strip()
        self.mic_use_pc = bool(mic_use_pc)
        self.pc_dshow_audio_device = (pc_dshow_audio_device or "").strip()
        if self.pc_dshow_audio_device in ("", "自动(按识别候选)"):
            self.pc_dshow_audio_device = ""
        self.app_log_config = app_log_config or {}
        self.post_delay_seconds = max(0.5, float(post_delay_seconds))
        self.record_params = record_params or RecordParams(max_fps=30, video_bit_rate="8M")
        self.audio_sample_rate = max(8000, int(audio_sample_rate or 44100))
        self.audio_bit_rate = (audio_bit_rate or "192k").strip() or "192k"
        self.audio_sync_offset_ms = int(audio_sync_offset_ms or 0)
        self.log_callback = log_callback or (lambda _msg: None)
        self.on_finished = on_finished

        self._lock = threading.Lock()
        self._running = False

        self._video_tmp_path: Optional[Path] = None
        self._mic_tmp_default_path: Optional[Path] = None
        self._sys_audio_tmp_path: Optional[Path] = None
        self._final_path: Optional[Path] = None  # final mp4 path (computed on stop)

        # app.log capture path (computed on start)
        self._log_path: Optional[Path] = None
        # logcat capture path (computed on start)
        self._logcat_path: Optional[Path] = None
        self._logcat_thread: Optional[threading.Thread] = None

        self._run_dir: Optional[Path] = None
        self._record_prefix: str = ""
        self._temp_prefix: str = ""
        self._start_pc_ts: Optional[float] = None
        self._end_pc_ts: Optional[float] = None
        self._start_hhmmss: str = ""
        self._device_offset_seconds: float = 0.0

        # StressMonitor references
        self._stress_monitor: Any = None
        self._app_log_thread: Optional[threading.Thread] = None
        self._mic_failed_early: bool = False
        self._video_failed_early: bool = False
        self._fatal_error_message: str = ""

        self._p_video: Optional[subprocess.Popen[bytes]] = None
        self._p_sys_audio: Optional[subprocess.Popen[bytes]] = None
        self._p_mic: Optional[subprocess.Popen[bytes]] = None
        self._p_pc_mic: Optional[subprocess.Popen[bytes]] = None
        self._reader_video: Optional[threading.Thread] = None
        self._reader_sys_audio: Optional[threading.Thread] = None
        self._reader_mic: Optional[threading.Thread] = None
        self._reader_pc_mic: Optional[threading.Thread] = None
        self._pc_mic_tmp_path: Optional[Path] = None

    def is_running(self) -> bool:
        with self._lock:
            return self._running

    def _emit(self, msg: str) -> None:
        try:
            self.log_callback(msg)
        except Exception:
            pass

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

        # 录制开始时间：用于最终文件命名 + app.log 时间窗截取
        self._start_pc_ts = time.time()
        start_local = datetime.fromtimestamp(self._start_pc_ts)
        self._start_hhmmss = start_local.strftime("%H%M%S")

        self._record_prefix = (self.record_basename or "").strip() or "record"
        start_compact = start_local.strftime("%Y%m%d%H%M%S")
        self._temp_prefix = f"{self._record_prefix}_{start_compact}"

        if self._run_log_dir_override:
            run_dir = self._run_log_dir_override
            run_dir.mkdir(parents=True, exist_ok=True)
            self._run_dir = run_dir
        else:
            run_dir = Path(self.output_dir).resolve() / self.serial / start_compact
            run_dir.mkdir(parents=True, exist_ok=True)
            self._run_dir = run_dir

        # 临时录制容器改为 mkv：异常中断时比 mp4 更不容易损坏（避免 moov 缺失）。
        self._video_tmp_path = run_dir / f"{self._temp_prefix}_video_tmp.mkv"
        # 默认 mic 先走 opus+.opus（在 linkandroid-scrcpy 上兼容性更稳）；失败再回退 aac 或 PC mic。
        self._mic_tmp_default_path = run_dir / f"{self._temp_prefix}_mic_tmp.opus"
        # 系统音独立录制，避免系统音频 demux 异常拖垮视频录制。
        self._sys_audio_tmp_path = run_dir / f"{self._temp_prefix}_sys_audio_tmp.opus"
        self._pc_mic_tmp_path = run_dir / f"{self._temp_prefix}_pc_mic_tmp.m4a"
        # 精准/全量原始日志：必须 session 私有命名，避免与稳定性测试目录里的 `app.log` 冲突。
        self._log_path = run_dir / f"{self._temp_prefix}_app.log"  # 精准采集的 app.log（后续切片输出最终日志）
        self._logcat_path = run_dir / f"{self._temp_prefix}_logcat.log"  # 本次 session 的全量 logcat（录制结束后切片输出最终日志）
        self._final_path = None  # stop 时计算

        self._emit(f"[record] run_dir: {run_dir}")
        self._emit(f"[record] record_prefix: {self._record_prefix}")
        self._emit(f"[record] start: {start_local.isoformat(timespec='seconds')} (PC)")
        self._emit(f"[record] video_tmp: {self._video_tmp_path}")
        self._emit(f"[record] mic_tmp: {self._mic_tmp_default_path}")
        self._emit(f"[record] app.log(capture): {self._log_path}")
        self._emit(f"[record] logcat.log(capture): {self._logcat_path}")

        adb_bin = _resolve_adb_bin()
        scrcpy_bin = self.scrcpy_path.strip() or "scrcpy"
        ffmpeg_bin = self.ffmpeg_path.strip() or "ffmpeg"

        # 为 utils.timeout_command 的 adb 解析设置环境变量（StressMonitor 内部依赖它）
        adb_env = (self.adb_path or "").strip()
        if adb_env and os.path.exists(adb_env):
            os.environ["ADB_PATH"] = adb_env

        # 设备时间偏移：把 PC 时间对齐到设备 time axis（用于线程时间戳切片）
        self._device_offset_seconds = self._ensure_device_time_offset(adb_bin=adb_bin)

        # 可选：清空 logcat 缓冲（用于减少噪音；但会影响并行稳定性采集）
        if self.clear_logcat_on_start:
            self._emit("[record] 开始前执行 adb logcat -c（可能影响并行稳定性采集）")
            try:
                subprocess.run(
                    [adb_bin, "-s", self.serial, "logcat", "-c"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=os.getcwd(),
                    check=False,
                )
            except Exception:
                pass

        # 1) 启动精准 app.log 采集（PID 过滤 + level/TAG/关键词）
        try:
            from utils.stress_monitor import StressMonitor
        except Exception as e:
            self._emit(f"[record] 无法导入 StressMonitor：{e}")
            self._running = False
            return

        if not self.package_name:
            self._emit("[record] package_name 为空，跳过 app.log 精准采集（将导致最终日志为空）")

        class _TmpDevice:
            def __init__(self, sn: str) -> None:
                self.sn = sn

        class _TmpPackage:
            def __init__(self, name: str) -> None:
                self.name = name

        monitor_cfg = {"app_log": self.app_log_config}
        self._stress_monitor = StressMonitor(_TmpDevice(self.serial), _TmpPackage(self.package_name), monitor_cfg)
        # 清理 stop 事件，确保采集线程能跑起来
        try:
            self._stress_monitor._stop_monitor.clear()  # type: ignore[attr-defined]
            self._stress_monitor._stop_logcat.clear()  # type: ignore[attr-defined]
        except Exception:
            pass

        self._app_log_thread = self._stress_monitor.start_app_log_capture(str(self._log_path))
        # 同时启动全量 logcat 采集；录制结束后按同一时间窗切片输出 logcat.log
        try:
            self._logcat_thread = self._stress_monitor.start_logcat_capture(
                str(self._logcat_path),
                clear_before=False,
            )
        except Exception as e:
            self._emit(f"[record] logcat 抓取启动失败（仍继续 app.log 精准采集）：{e}")

        # 2) scrcpy video-only recording（强制 no-audio，保证视频稳定产出）
        primary_video_cmd: list[str] = [
            scrcpy_bin,
            "--serial",
            self.serial,
            "--no-playback",
            "--no-control",
            "--no-audio",
            "--record",
            str(self._video_tmp_path),
        ]

        # 2b) scrcpy system audio recording (no video)
        sys_audio_cmd: list[str] = [
            scrcpy_bin,
            "--serial",
            self.serial,
            "--no-video",
            "--no-playback",
            "--no-control",
            "--audio-source=output",
            "--audio-codec=opus",
            "--record",
            str(self._sys_audio_tmp_path),
        ]
        sys_audio_tmp_aac_path = run_dir / f"{self._temp_prefix}_sys_audio_tmp.m4a"
        sys_audio_cmd_aac: list[str] = [
            scrcpy_bin,
            "--serial",
            self.serial,
            "--no-video",
            "--no-playback",
            "--no-control",
            "--audio-source=output",
            "--audio-codec=aac",
            "--record",
            str(sys_audio_tmp_aac_path),
        ]

        if self.record_params.max_fps is not None:
            primary_video_cmd.extend(["--max-fps", str(int(self.record_params.max_fps))])
        if self.record_params.video_bit_rate:
            primary_video_cmd.extend(["--video-bit-rate", str(self.record_params.video_bit_rate)])
        if self.record_params.max_size:
            primary_video_cmd.extend(["--max-size", str(self.record_params.max_size)])
        # 主录制优先固定 h264，减少部分设备/ROM 在默认编码策略上的不确定性。
        primary_video_cmd.extend(["--video-codec=h264"])

        def _build_safe_video_cmd(*, codec: str, max_fps: str, bit_rate: str, max_size: str) -> list[str]:
            return [
                scrcpy_bin,
                "--serial",
                self.serial,
                "--no-playback",
                "--no-control",
                "--no-audio",
                f"--video-codec={codec}",
                "--max-fps",
                max_fps,
                "--video-bit-rate",
                bit_rate,
                "--max-size",
                max_size,
                "--record",
                str(self._video_tmp_path),
            ]

        # 多档位降级：优先保证可录到视频轨。
        video_profiles: list[tuple[str, list[str]]] = [
            ("primary", primary_video_cmd),
            ("safe-h264-1280", _build_safe_video_cmd(codec="h264", max_fps="20", bit_rate="4M", max_size="1280")),
            ("safe-h264-1024", _build_safe_video_cmd(codec="h264", max_fps="15", bit_rate="2M", max_size="1024")),
            ("safe-h264-720", _build_safe_video_cmd(codec="h264", max_fps="12", bit_rate="1M", max_size="720")),
            ("safe-h265-1024", _build_safe_video_cmd(codec="h265", max_fps="15", bit_rate="2M", max_size="1024")),
        ]

        # 注意：不要在录屏会话里强制 --stay-awake。
        # 在部分 Android 设备（例如 MIUI/Android 15）上，scrcpy 会尝试写入全局设置
        # stay_on_while_plugged_in，可能因缺少 WRITE_SECURE_SETTINGS 直接导致 server 异常/连接失败。

        env = os.environ.copy()
        if adb_env:
            env["ADB"] = adb_env

        video_encoding_error_event = threading.Event()

        def _on_video_line(line: str) -> None:
            low = (line or "").lower()
            if (
                "capture/encoding error" in low
                or "illegalargumentexception" in low
                or ("retrying with -m" in low and "error" in low)
            ):
                video_encoding_error_event.set()

        active_video_profile_idx = 0

        def _start_video_process(cmd: list[str], *, reason: str) -> bool:
            try:
                self._emit(f"[record] 启动视频录制({reason}): {' '.join(cmd)}")
                self._p_video = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=os.getcwd(),
                    env=env,
                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                )
                self._reader_video = _start_output_reader(self._p_video, self._emit, _on_video_line)
                return True
            except Exception as e:
                self._emit(f"[record] 启动视频录制失败({reason}): {e}")
                return False

        def _start_video_profile(idx: int, *, reason: str) -> bool:
            nonlocal active_video_profile_idx
            if idx < 0 or idx >= len(video_profiles):
                return False
            active_video_profile_idx = idx
            profile_name, cmd = video_profiles[idx]
            return _start_video_process(cmd, reason=f"{reason}:{profile_name}")

        if not _start_video_profile(0, reason="start"):
            self._fatal_error_message = "视频录制启动失败：无法启动 scrcpy(video-only)。"
            self._emit(f"[record] ❌ {self._fatal_error_message}")
            self._running = False
            return

        self._emit(f"[record] scrcpy(sys-audio) 命令: {' '.join(sys_audio_cmd)}")
        self._p_sys_audio = subprocess.Popen(
            sys_audio_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),
            env=env,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
        self._reader_sys_audio = _start_output_reader(self._p_sys_audio, self._emit)

        self._ffmpeg_bin = ffmpeg_bin
        if self.mic_use_pc:
            self._emit("[record] mic source: 电脑麦克风(dshow)/PC端环境声")
        else:
            # 3) scrcpy mic/environment audio recording (no video)
            mic_cmd: list[str] = [
                scrcpy_bin,
                "--serial",
                self.serial,
                "--no-video",
                "--no-playback",
                "--no-control",
                "--audio-source=mic",
                "--audio-codec=opus",
                "--record",
                str(self._mic_tmp_default_path),
            ]
            mic_tmp_aac_path = run_dir / f"{self._temp_prefix}_mic_tmp.m4a"
            mic_cmd_aac: list[str] = [
                scrcpy_bin,
                "--serial",
                self.serial,
                "--no-video",
                "--no-playback",
                "--no-control",
                "--audio-source=mic",
                "--audio-codec=aac",
                "--record",
                str(mic_tmp_aac_path),
            ]

            if self.record_params.max_fps is not None:
                mic_cmd.extend(["--max-fps", str(int(self.record_params.max_fps))])
                mic_cmd_aac.extend(["--max-fps", str(int(self.record_params.max_fps))])
            if self.record_params.max_size:
                mic_cmd.extend(["--max-size", str(self.record_params.max_size)])
                mic_cmd_aac.extend(["--max-size", str(self.record_params.max_size)])
            self._emit(f"[record] scrcpy(mic) 命令: {' '.join(mic_cmd)}")
            self._p_mic = subprocess.Popen(
                mic_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                env=env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
            self._reader_mic = _start_output_reader(self._p_mic, self._emit)

        mic_desc = "电脑麦克风(dshow)" if self.mic_use_pc else "设备麦克风(scrcpy)"
        self._emit(f"[record] 已启动：双路 scrcpy + {mic_desc} + 精准 app.log 采集")

        def _start_pc_mic_fallback() -> bool:
            if not self._pc_mic_tmp_path:
                return False
            if self._p_pc_mic and self._p_pc_mic.poll() is None:
                return True

            ffmpeg_use = self._ffmpeg_bin
            preferred = self.pc_dshow_audio_device or ""
            device_candidates: list[str] = []
            if preferred:
                device_candidates.append(preferred)
            if "default" not in device_candidates:
                device_candidates.append("default")
            try:
                probe = subprocess.run(
                    [ffmpeg_use, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    cwd=os.getcwd(),
                    check=False,
                )
                text = (probe.stderr or b"").decode("utf-8", errors="replace")
                for line in text.splitlines():
                    if "(audio)" not in line:
                        continue
                    m = re.search(r'"([^"]+)"', line)
                    if m:
                        name = m.group(1).strip()
                        if name and name not in device_candidates:
                            device_candidates.append(name)
            except Exception:
                pass

            for dev in device_candidates:
                cmd = [
                    ffmpeg_use,
                    "-hide_banner",
                    "-y",
                    "-f",
                    "dshow",
                    "-i",
                    f"audio={dev}",
                    "-ar",
                    str(self.audio_sample_rate),
                    "-c:a",
                    "aac",
                    "-b:a",
                    self.audio_bit_rate,
                    str(self._pc_mic_tmp_path),
                ]
                try:
                    self._emit(f"[record] 尝试降级为电脑麦克风录制: {' '.join(cmd)}")
                    self._p_pc_mic = subprocess.Popen(
                        cmd,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        cwd=os.getcwd(),
                        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                    )
                    self._reader_pc_mic = _start_output_reader(self._p_pc_mic, self._emit)
                    time.sleep(1.2)
                    if self._p_pc_mic.poll() is None:
                        self._emit(f"[record] 已启用电脑麦克风降级录制，设备: {dev}")
                        return True
                    self._emit(
                        f"[record] 电脑麦克风录制启动失败（device={dev}, exit={self._p_pc_mic.returncode}）"
                    )
                except Exception as e:
                    self._emit(f"[record] 电脑麦克风录制异常（device={dev}）: {e}")
            self._emit("[record] 电脑麦克风降级录制启动失败")
            return False

        if self.mic_use_pc:
            ok = _start_pc_mic_fallback()
            if not ok:
                self._emit("[record] 警告：电脑麦克风录制启动失败，将不进行 mic 混音（至少输出系统音/视频）")

        # 失败探测：持续监听录制期间的进程退出，避免只看“启动早期”导致漏判。
        def _early_exit_watch() -> None:
            checked_video = False
            exhausted_video_profiles = False
            tried_sys_aac = False
            tried_mic_opus = False
            tried_pc_mic = False
            while self.is_running():
                time.sleep(0.8)
                try:
                    # 实时捕获编码错误：按档位逐级降参重启视频录制。
                    if video_encoding_error_event.is_set() and not exhausted_video_profiles:
                        video_encoding_error_event.clear()
                        self._emit("[record] 检测到视频编码异常，尝试切换到更保守的视频录制参数")
                        try:
                            _graceful_stop_scrcpy(
                                self._p_video,
                                log_callback=self._emit,
                                name="scrcpy(video-only)",
                                wait_seconds=1.5,
                            )
                        except Exception:
                            pass
                        next_idx = active_video_profile_idx + 1
                        if next_idx < len(video_profiles):
                            ok_safe = _start_video_profile(next_idx, reason="encoding-error-fallback")
                            if not ok_safe:
                                exhausted_video_profiles = True
                        else:
                            exhausted_video_profiles = True

                        if exhausted_video_profiles:
                            self._fatal_error_message = "视频录制异常：编码失败且保守参数重启失败，已停止录制。"
                            self._emit(f"[record] ❌ {self._fatal_error_message}")
                            try:
                                self.stop()
                            except Exception:
                                pass
                            return
                except Exception:
                    pass

                try:
                    if not checked_video and self._p_video and self._p_video.poll() is not None:
                        checked_video = True
                        self._video_failed_early = True
                        self._emit(f"[record] 警告：scrcpy(video) 可能启动失败（exit={self._p_video.returncode}）")
                        next_idx = active_video_profile_idx + 1
                        if next_idx < len(video_profiles):
                            self._emit("[record] 视频进程异常退出，尝试切换到下一档兼容参数")
                            _start_video_profile(next_idx, reason="process-exit-fallback")
                        else:
                            exhausted_video_profiles = True
                except Exception:
                    pass

                # 所有档位都失败且仍无视频轨：终止录制。
                try:
                    if exhausted_video_profiles:
                        ffmpeg_use = getattr(self, "_ffmpeg_bin", None) or self.ffmpeg_path.strip() or "ffmpeg"
                        has_video2 = False
                        try:
                            if self._video_tmp_path and self._video_tmp_path.exists():
                                has_video2, _ = _probe_video_and_duration(self._video_tmp_path, ffmpeg_use)
                        except Exception:
                            has_video2 = False

                        if not has_video2:
                            self._fatal_error_message = (
                                "视频录制异常：已尝试所有兼容参数，临时文件仍无视频轨，已停止本次录制。"
                            )
                            self._emit(f"[record] ❌ {self._fatal_error_message}")
                            try:
                                self.stop()
                            except Exception:
                                pass
                            return
                except Exception:
                    pass

                try:
                    if self._p_sys_audio and self._p_sys_audio.poll() is not None and not tried_sys_aac:
                        tried_sys_aac = True
                        self._emit(
                            f"[record] 警告：scrcpy(sys-audio) 录制中断（exit={self._p_sys_audio.returncode}），尝试切换 aac"
                        )
                        try:
                            self._emit(f"[record] 尝试重启 scrcpy(sys-audio,aac): {' '.join(sys_audio_cmd_aac)}")
                            self._p_sys_audio = subprocess.Popen(
                                sys_audio_cmd_aac,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                cwd=os.getcwd(),
                                env=env,
                                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                            )
                            self._reader_sys_audio = _start_output_reader(self._p_sys_audio, self._emit)
                            time.sleep(1.0)
                        except Exception as e:
                            self._emit(f"[record] scrcpy(sys-audio,aac) 重启失败: {e}")
                except Exception:
                    pass

                try:
                    if self._p_mic and self._p_mic.poll() is not None:
                        self._mic_failed_early = True
                        if not tried_mic_opus:
                            tried_mic_opus = True
                            self._emit(
                                f"[record] 警告：scrcpy(mic) 录制中断（exit={self._p_mic.returncode}），尝试切换 aac"
                            )
                            try:
                                self._emit(f"[record] 尝试重启 scrcpy(mic,aac): {' '.join(mic_cmd_aac)}")
                                self._p_mic = subprocess.Popen(
                                    mic_cmd_aac,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    cwd=os.getcwd(),
                                    env=env,
                                    creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                                )
                                self._reader_mic = _start_output_reader(self._p_mic, self._emit)
                                time.sleep(1.0)
                            except Exception as e:
                                self._emit(f"[record] scrcpy(mic,aac) 重启失败: {e}")

                        if self._p_mic and self._p_mic.poll() is not None and not tried_pc_mic:
                            tried_pc_mic = True
                            self._emit(
                                f"[record] scrcpy(mic) 仍不可用（exit={self._p_mic.returncode}），切换电脑麦克风降级"
                            )
                            _start_pc_mic_fallback()
                except Exception:
                    pass

        threading.Thread(target=_early_exit_watch, daemon=True).start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

            p_video = self._p_video
            p_sys_audio = self._p_sys_audio
            p_mic = self._p_mic
            p_pc_mic = self._p_pc_mic
            monitor = self._stress_monitor
            app_log_thread = self._app_log_thread
            logcat_thread = self._logcat_thread
            run_dir = self._run_dir
            capture_app_log_path = self._log_path
            capture_logcat_path = self._logcat_path

            # Clear scrcpy references early to avoid double stop.
            self._p_video = None
            self._p_sys_audio = None
            self._p_mic = None
            self._p_pc_mic = None

            self._end_pc_ts = time.time()
            end_pc_ts = self._end_pc_ts

        t = threading.Thread(
            target=self._stop_and_finalize,
            args=(
                p_video,
                p_sys_audio,
                p_mic,
                p_pc_mic,
                monitor,
                app_log_thread,
                logcat_thread,
                run_dir,
                capture_app_log_path,
                capture_logcat_path,
                end_pc_ts,
            ),
            daemon=True,
        )
        t.start()

    def _stop_and_finalize(
        self,
        p_video: Optional[subprocess.Popen[bytes]],
        p_sys_audio: Optional[subprocess.Popen[bytes]],
        p_mic: Optional[subprocess.Popen[bytes]],
        p_pc_mic: Optional[subprocess.Popen[bytes]],
        monitor: Any,
        app_log_thread: Optional[threading.Thread],
        logcat_thread: Optional[threading.Thread],
        run_dir: Optional[Path],
        capture_app_log_path: Optional[Path],
        capture_logcat_path: Optional[Path],
        end_pc_ts: Optional[float],
    ) -> None:
        final: Optional[str] = None
        try:
            self._emit("[record] 停止录制：先结束两个 scrcpy，然后等待 app.log 写入完成")

            _graceful_stop_scrcpy(p_video, log_callback=self._emit, name="scrcpy(video)")
            _graceful_stop_scrcpy(p_sys_audio, log_callback=self._emit, name="scrcpy(sys-audio)")
            _graceful_stop_scrcpy(p_mic, log_callback=self._emit, name="scrcpy(mic)")
            _graceful_stop_ffmpeg_recorder(
                p_pc_mic,
                log_callback=self._emit,
                name="ffmpeg(pc-mic)",
            )

            # 等待几秒，确保 app.log 的最后一段也写入落盘，然后再切片输出最终日志。
            time.sleep(self.post_delay_seconds)

            try:
                if monitor:
                    monitor.stop()
            except Exception:
                pass

            # 尽力 join 采集线程，避免 app.log 仍在写入时切片读取过早。
            try:
                if app_log_thread and app_log_thread.is_alive():
                    app_log_thread.join(timeout=5)
            except Exception:
                pass

            # 尽力 join logcat 采集线程，避免 logcat 切片读取过早。
            try:
                if logcat_thread and logcat_thread.is_alive():
                    logcat_thread.join(timeout=5)
            except Exception:
                pass

            if not run_dir or not capture_app_log_path or end_pc_ts is None:
                self._emit("[record] 停止失败：run_dir/app.log 或 end_ts 缺失")
            else:
                end_local = datetime.fromtimestamp(end_pc_ts)
                end_hhmmss = end_local.strftime("%H%M%S")
                start_hhmmss = self._start_hhmmss or "000000"
                self._final_path = run_dir / f"{self._record_prefix}_{start_hhmmss}-{end_hhmmss}_final.mp4"
                final_log_path = run_dir / f"{self._record_prefix}_{start_hhmmss}-{end_hhmmss}_final_app.log"

                self._emit(f"[record] end: {end_local.isoformat(timespec='seconds')} (PC)")
                self._emit(f"[record] final video: {self._final_path}")
                self._emit(f"[record] final app.log: {final_log_path}")

                # 先切片日志（高效读取，不与写入共享同一 file handle）
                sliced_count = self._slice_app_log_time_window(
                    input_path=capture_app_log_path,
                    output_path=final_log_path,
                )
                self._emit(f"[record] app.log 切片完成：{sliced_count} 行")

                # 同一时间窗：切片 logcat.log
                sliced_count_logcat = 0
                final_logcat_path = run_dir / f"{self._record_prefix}_{start_hhmmss}-{end_hhmmss}_final_logcat.log"
                if capture_logcat_path and capture_logcat_path.exists():
                    self._emit(f"[record] final logcat.log: {final_logcat_path}")
                    sliced_count_logcat = self._slice_app_log_time_window(
                        input_path=capture_logcat_path,
                        output_path=final_logcat_path,
                        log_label="logcat.log",
                    )
                    self._emit(f"[record] logcat.log 切片完成：{sliced_count_logcat} 行")
                else:
                    self._emit("[record] 警告：未找到/空的 logcat.log 捕获文件，跳过 logcat 切片")

                self._emit("[record] 开始 ffmpeg 混音合成最终视频")
                final = self._mix_with_ffmpeg()
                if final:
                    self._emit(f"[record] 录制完成：{final}")
                else:
                    self._emit("[record] 录制失败：视频轨异常或 ffmpeg 合成失败，已停止且不做降级输出")

                # 如果切片 0 行，附带 app.log 末尾片段用于排查（不阻塞写入：这里已 stop + join）
                if sliced_count <= 0:
                    try:
                        self._append_app_log_tail_for_debug(
                            input_path=capture_app_log_path,
                            output_path=final_log_path,
                            max_bytes=200_000,
                        )
                        self._emit("[record] app.log 切片为 0，已附加捕获 app.log 尾部片段用于排查")
                    except Exception:
                        pass

                if sliced_count_logcat <= 0:
                    try:
                        if capture_logcat_path and capture_logcat_path.exists():
                            self._append_log_tail_for_debug(
                                input_path=capture_logcat_path,
                                output_path=final_logcat_path,
                                log_label="logcat.log",
                                max_bytes=200_000,
                            )
                            self._emit("[record] logcat.log 切片为 0，已附加捕获 logcat.log 尾部片段用于排查")
                    except Exception:
                        pass

                # 可选：清理本次 session 的临时文件
                if self.delete_tmp_after_record:
                    try:
                        # 删除临时视频/麦克风文件
                        if self._video_tmp_path and self._video_tmp_path.exists():
                            self._video_tmp_path.unlink()
                    except Exception:
                        pass
                    try:
                        if self._sys_audio_tmp_path and self._sys_audio_tmp_path.exists():
                            self._sys_audio_tmp_path.unlink()
                    except Exception:
                        pass
                    try:
                        if run_dir and self._temp_prefix:
                            for p in run_dir.glob(f"{self._temp_prefix}_mic_tmp.*"):
                                try:
                                    if p.exists():
                                        p.unlink()
                                except Exception:
                                    pass
                            for p in run_dir.glob(f"{self._temp_prefix}_sys_audio_tmp.*"):
                                try:
                                    if p.exists():
                                        p.unlink()
                                except Exception:
                                    pass
                            for p in run_dir.glob(f"{self._temp_prefix}_pc_mic_tmp.*"):
                                try:
                                    if p.exists():
                                        p.unlink()
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    try:
                        # 删除本次 session 的 app.log 捕获文件（含轮转）
                        if capture_app_log_path and capture_app_log_path.exists():
                            capture_app_log_path.unlink()
                        backup_count2 = 3
                        try:
                            backup_count2 = int(self.app_log_config.get("backup_count", 3) or 3)
                        except Exception:
                            backup_count2 = 3
                        for i in range(1, max(1, backup_count2) + 1):
                            p = Path(str(capture_app_log_path) + f".{i}") if capture_app_log_path else None
                            if p and p.exists():
                                try:
                                    p.unlink()
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    try:
                        # 删除本次 session 的 logcat 捕获文件
                        if capture_logcat_path and capture_logcat_path.exists():
                            capture_logcat_path.unlink()
                    except Exception:
                        pass

            if self.on_finished:
                try:
                    self.on_finished(final or "")
                except Exception:
                    pass
        except Exception as e:
            self._emit(f"[record] 停止/合成过程中发生异常: {e}")
            if self.on_finished:
                try:
                    self.on_finished("")
                except Exception:
                    pass

    def _ensure_device_time_offset(self, *, adb_bin: str) -> float:
        """
        计算并缓存设备时间与本机时间差（秒）：pc_ts - device_epoch_seconds.
        用于把 PC 的 start/end 时间对齐到设备生成的 threadtime 时间戳。
        """
        try:
            out = subprocess.run(
                [adb_bin, "-s", self.serial, "shell", "date", "+%s"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                cwd=os.getcwd(),
                check=False,
            )
            txt = (out.stdout or b"").decode("utf-8", errors="replace").strip().splitlines()[-1].strip() if out.stdout else ""
            dev_epoch = float(txt) if txt else 0.0
            pc_epoch = time.time()
            # 设备时钟可能与秒级存在偏差；这里使用秒级对齐用于切片边界。
            return pc_epoch - dev_epoch if dev_epoch > 0 else 0.0
        except Exception:
            return 0.0

    def _pc_ts_to_device_dt(self, pc_ts: float) -> datetime:
        dev_epoch = pc_ts - float(self._device_offset_seconds or 0.0)
        return datetime.fromtimestamp(dev_epoch)

    @staticmethod
    def _try_parse_threadtime_dt(line: bytes, *, year_hint: int) -> Optional[datetime]:
        """
        Parse threadtime timestamp prefix:
        `MM-DD HH:MM:SS.mmm PID TID LEVEL TAG: ...`
        Returns datetime or None.
        """
        if not line or len(line) < 20 or line.startswith(b"#"):
            return None
        try:
            # Token0: MM-DD
            s1 = line.find(b" ")
            if s1 <= 0:
                return None
            s2 = line.find(b" ", s1 + 1)
            if s2 <= s1 + 1:
                return None
            mmdd_b = line[:s1].decode("ascii", errors="ignore")
            hms_b = line[s1 + 1 : s2].decode("ascii", errors="ignore")
            if len(mmdd_b) < 5 or "-" not in mmdd_b:
                return None
            mm = int(mmdd_b[0:2])
            dd = int(mmdd_b[3:5])
            if len(hms_b) < 8 or ":" not in hms_b:
                return None
            hh = int(hms_b[0:2])
            mi = int(hms_b[3:5])
            ss = int(hms_b[6:8])
            dot = hms_b.find(".")
            ms_str = hms_b[dot + 1 :] if dot != -1 and dot + 1 < len(hms_b) else "0"
            ms_str = (ms_str + "000")[:3]
            ms = int(ms_str)
            return datetime(year_hint, mm, dd, hh, mi, ss, ms * 1000)
        except Exception:
            return None

    def _slice_app_log_time_window(
        self,
        *,
        input_path: Path,
        output_path: Path,
        log_label: str = "app.log",
    ) -> int:
        """
        高效切片：基于 threadtime 的 `MM-DD HH:MM:SS.mmm` 精确匹配 start/end。
        使用 mmap + 查找秒级前缀定位，避免全文件扫描。
        """
        if self._start_pc_ts is None or self._end_pc_ts is None:
            return 0

        start_dt_device = self._pc_ts_to_device_dt(float(self._start_pc_ts))
        end_dt_device = self._pc_ts_to_device_dt(float(self._end_pc_ts))
        if end_dt_device < start_dt_device:
            start_dt_device, end_dt_device = end_dt_device, start_dt_device

        year_hint = start_dt_device.year
        start_sec_prefix = start_dt_device.strftime("%m-%d %H:%M:%S")
        start_sec_prefix_b = start_sec_prefix.encode("ascii", errors="ignore")

        try:
            backup_count = int(self.app_log_config.get("backup_count", 3) or 3)
        except Exception:
            backup_count = 3

        # 以时间顺序拼接：app.log.<N>（更旧） -> ... -> app.log.1 -> app.log（最新）
        files: list[tuple[int, Path]] = [(0, input_path)]
        for i in range(1, max(1, backup_count) + 1):
            p = Path(str(input_path) + f".{i}")
            if p.exists():
                files.append((i, p))
        files.sort(key=lambda x: x[0], reverse=True)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        written = 0

        header = (
            f"# [record] {log_label} slice: {start_dt_device.isoformat(timespec='seconds')} ~ {end_dt_device.isoformat(timespec='seconds')}\n"
        )
        try:
            with open(output_path, "w", encoding="utf-8", errors="replace") as fout:
                fout.write(header)

                started = False
                end_reached = False

                for _idx, p in files:
                    if end_reached:
                        break
                    if not p.exists():
                        continue

                    try:
                        with open(p, "rb") as f:
                            mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            try:
                                scan_pos = 0
                                if not started:
                                    pos = mm.find(start_sec_prefix_b)
                                    if pos == -1:
                                        continue
                                    scan_pos = pos
                                    started = True

                                mm_len = mm.size()
                                i = scan_pos
                                while i < mm_len:
                                    j = mm.find(b"\n", i)
                                    if j == -1:
                                        j = mm_len
                                    line = mm[i:j]
                                    i = j + 1
                                    if not line:
                                        continue
                                    dt_line = self._try_parse_threadtime_dt(line, year_hint=year_hint)
                                    if dt_line is None:
                                        continue
                                    if dt_line < start_dt_device:
                                        continue
                                    if dt_line > end_dt_device:
                                        end_reached = True
                                        break
                                    # 直接写入原始行文本（保留原有格式）
                                    fout.write(line.decode("utf-8", errors="replace") + "\n")
                                    written += 1
                            finally:
                                mm.close()
                    except Exception:
                        continue

                # 如果完全没切到，仍然保留 header，方便排查
        except Exception:
            return 0

        return written

    def _pick_mic_tmp_file(self) -> Optional[Path]:
        if not self._run_dir or not self._temp_prefix:
            return None

        assert self._mic_tmp_default_path is not None
        min_bytes = int(self._MIN_VALID_MIC_BYTES)

        # Preferred default path
        try:
            if (
                self._mic_tmp_default_path.exists()
                and self._mic_tmp_default_path.stat().st_size >= min_bytes
            ):
                return self._mic_tmp_default_path
            if self._mic_tmp_default_path.exists():
                self._emit(
                    f"[record] 忽略过小 mic 文件: {self._mic_tmp_default_path} "
                    f"(size={self._mic_tmp_default_path.stat().st_size}, min={min_bytes})"
                )
        except Exception:
            pass
        # PC mic fallback path
        try:
            if (
                self._pc_mic_tmp_path
                and self._pc_mic_tmp_path.exists()
                and self._pc_mic_tmp_path.stat().st_size >= min_bytes
            ):
                return self._pc_mic_tmp_path
            if self._pc_mic_tmp_path and self._pc_mic_tmp_path.exists():
                self._emit(
                    f"[record] 忽略过小 pc-mic 文件: {self._pc_mic_tmp_path} "
                    f"(size={self._pc_mic_tmp_path.stat().st_size}, min={min_bytes})"
                )
        except Exception:
            pass

        # Fallback: scan for <temp_prefix>*mic_tmp.*
        candidates: list[Path] = []
        try:
            for pattern in (f"{self._temp_prefix}_mic_tmp.*", f"{self._temp_prefix}_pc_mic_tmp.*"):
                for p in self._run_dir.glob(pattern):
                    try:
                        if p.is_file() and p.stat().st_size >= min_bytes:
                            candidates.append(p)
                        elif p.is_file():
                            self._emit(
                                f"[record] 忽略过小 mic 候选: {p} "
                                f"(size={p.stat().st_size}, min={min_bytes})"
                            )
                    except Exception:
                        pass
        except Exception:
            candidates = []

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def _pick_sys_audio_tmp_file(self) -> Optional[Path]:
        if not self._run_dir or not self._temp_prefix:
            return None

        min_bytes = int(self._MIN_VALID_SYS_AUDIO_BYTES)

        try:
            if (
                self._sys_audio_tmp_path
                and self._sys_audio_tmp_path.exists()
                and self._sys_audio_tmp_path.stat().st_size >= min_bytes
            ):
                return self._sys_audio_tmp_path
            if self._sys_audio_tmp_path and self._sys_audio_tmp_path.exists():
                self._emit(
                    f"[record] 忽略过小 sys-audio 文件: {self._sys_audio_tmp_path} "
                    f"(size={self._sys_audio_tmp_path.stat().st_size}, min={min_bytes})"
                )
        except Exception:
            pass

        candidates: list[Path] = []
        try:
            for pattern in (f"{self._temp_prefix}_sys_audio_tmp.*",):
                for p in self._run_dir.glob(pattern):
                    try:
                        if p.is_file() and p.stat().st_size >= min_bytes:
                            candidates.append(p)
                        elif p.is_file():
                            self._emit(
                                f"[record] 忽略过小 sys-audio 候选: {p} "
                                f"(size={p.stat().st_size}, min={min_bytes})"
                            )
                    except Exception:
                        pass
        except Exception:
            candidates = []

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0]

    def _mix_with_ffmpeg(self) -> Optional[str]:
        if not (self._video_tmp_path and self._final_path):
            return None

        video_tmp = self._video_tmp_path
        sys_audio_file = self._pick_sys_audio_tmp_file()
        mic_file = self._pick_mic_tmp_file()
        final_path = self._final_path

        if not video_tmp.exists() or video_tmp.stat().st_size <= 0:
            self._emit(f"[record] 找不到/空的 video_tmp: {video_tmp}")
            return None

        ffmpeg_bin = getattr(self, "_ffmpeg_bin", None) or self.ffmpeg_path.strip() or "ffmpeg"

        final_path.parent.mkdir(parents=True, exist_ok=True)

        has_video, _v_dur = _probe_video_and_duration(video_tmp, ffmpeg_bin)
        if not has_video:
            self._fatal_error_message = "视频录制异常：临时视频文件未检测到视频轨，已停止并判定失败。"
            self._emit(f"[record] ❌ {self._fatal_error_message}")
            return None

        video_start = _probe_stream_start_time(video_tmp, ffmpeg_bin, codec_type="video")
        sys_start = (
            _probe_stream_start_time(sys_audio_file, ffmpeg_bin, codec_type="audio")
            if sys_audio_file and sys_audio_file.exists()
            else 0.0
        )
        mic_start = (
            _probe_stream_start_time(mic_file, ffmpeg_bin, codec_type="audio")
            if mic_file and mic_file.exists()
            else 0.0
        )

        def _build_audio_input_args(path: Path, start_time: float) -> list[str]:
            # 以视频 start_time 作为主时轴基准；额外叠加可调补偿（默认 0ms）。
            offset = (start_time - video_start) + (float(self.audio_sync_offset_ms) / 1000.0)
            self._emit(
                f"[record] audio align: file={path.name}, start={start_time:.3f}, "
                f"video_start={video_start:.3f}, itsoffset={offset:.3f}s"
            )
            return ["-itsoffset", f"{offset:.3f}", "-i", str(path)]

        first_in = ["-i", str(video_tmp)]

        # 尝试链路（由强到弱）：
        # 1) sys_audio + mic amix（若两者都存在）
        # 2) sys_audio only
        # 3) mic only
        # 4) video-only（确保文件可播放）
        attempts: list[tuple[str, list[str]]] = []

        if sys_audio_file and sys_audio_file.exists() and mic_file and mic_file.exists():
            mix_cmd: list[str] = [
                ffmpeg_bin,
                "-y",
                *first_in,
                *_build_audio_input_args(sys_audio_file, sys_start),
                *_build_audio_input_args(mic_file, mic_start),
                "-filter_complex",
                "[1:a]aresample=async=1[a1];"
                "[2:a]aresample=async=1[a2];"
                "[a1][a2]amix=inputs=2:duration=longest:dropout_transition=2[aout]",
                "-map",
                "0:v:0",
                "-map",
                "[aout]",
                "-c:v",
                "copy",
                "-ar",
                str(self.audio_sample_rate),
                "-shortest",
            ]
            mix_cmd.extend(["-c:a", "aac", "-b:a", self.audio_bit_rate, str(final_path)])
            attempts.append(("mix-sys+mic", mix_cmd))

        if sys_audio_file and sys_audio_file.exists():
            sys_cmd: list[str] = [
                ffmpeg_bin,
                "-y",
                *first_in,
                *_build_audio_input_args(sys_audio_file, sys_start),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-af",
                "aresample=async=1",
                "-ar",
                str(self.audio_sample_rate),
                "-shortest",
            ]
            sys_cmd.extend(["-c:a", "aac", "-b:a", self.audio_bit_rate, str(final_path)])
            attempts.append(("sys-only", sys_cmd))

        if mic_file and mic_file.exists():
            mic_cmd: list[str] = [
                ffmpeg_bin,
                "-y",
                *first_in,
                *_build_audio_input_args(mic_file, mic_start),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-af",
                "aresample=async=1",
                "-ar",
                str(self.audio_sample_rate),
                "-shortest",
            ]
            mic_cmd.extend(["-c:a", "aac", "-b:a", self.audio_bit_rate, str(final_path)])
            attempts.append(("mic-only", mic_cmd))

        attempts.append(
            (
                "video-only",
                [
                    ffmpeg_bin,
                    "-y",
                    "-i",
                    str(video_tmp),
                    "-map",
                    "0:v:0",
                    "-c:v",
                    "copy",
                    "-an",
                    str(final_path),
                ],
            )
        )

        for stage, cmd in attempts:
            self._emit(f"[record] ffmpeg({stage}) 命令: {' '.join(cmd)}")
            try:
                rst = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    cwd=os.getcwd(),
                    check=False,
                )
            except Exception as e:
                self._emit(f"[record] ffmpeg({stage}) 执行异常: {e}")
                continue

            try:
                if final_path.exists() and final_path.stat().st_size > 0 and rst.returncode == 0:
                    return str(final_path)
            except Exception:
                pass

            try:
                err_tail = (rst.stderr or b"").decode("utf-8", errors="replace")[-400:]
            except Exception:
                err_tail = ""
            self._emit(f"[record] ffmpeg({stage}) 失败，exit={rst.returncode}，stderr_tail={err_tail}")

        return None

    def get_fatal_error_message(self) -> str:
        return (self._fatal_error_message or "").strip()

    @staticmethod
    def _append_app_log_tail_for_debug(*, input_path: Path, output_path: Path, max_bytes: int = 200_000) -> None:
        """把捕获 app.log 的末尾内容追加到最终日志，便于排查切片为 0 的原因。"""
        RecordSession._append_log_tail_for_debug(
            input_path=input_path,
            output_path=output_path,
            log_label="app.log",
            max_bytes=max_bytes,
        )

    @staticmethod
    def _append_log_tail_for_debug(
        *,
        input_path: Path,
        output_path: Path,
        log_label: str,
        max_bytes: int = 200_000,
    ) -> None:
        """把捕获日志的末尾内容追加到最终日志，便于排查切片为 0 的原因。"""
        try:
            if not input_path.exists() or input_path.stat().st_size <= 0:
                return
        except Exception:
            return

        try:
            size = input_path.stat().st_size
            start = max(0, size - max(10_000, int(max_bytes)))
            with open(input_path, "rb") as fin:
                fin.seek(start)
                chunk = fin.read(max_bytes)
            text = chunk.decode("utf-8", errors="replace")
            with open(output_path, "a", encoding="utf-8", errors="replace") as fout:
                fout.write(f"\n# [record] ---- {log_label} tail (debug) ----\n")
                fout.write(text)
                if not text.endswith("\n"):
                    fout.write("\n")
                fout.write("# [record] ---- end of tail ----\n")
        except Exception:
            return


__all__ = ["RecordSession", "RecordParams"]

