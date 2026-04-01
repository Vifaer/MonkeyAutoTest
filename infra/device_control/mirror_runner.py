from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


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
        # Best-effort; ignore.
        return


def _start_output_reader(
    popen: subprocess.Popen[bytes],
    log_callback: Callable[[str], None],
) -> threading.Thread:
    """Read stdout/stderr lines and forward to GUI logger."""

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
                    # Don't crash reader.
                    pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    return t


@dataclass(frozen=True)
class ScrcpyMirrorParams:
    max_fps: Optional[int] = None
    video_bit_rate: Optional[str] = None  # e.g. "8M"
    max_size: Optional[str] = None  # scrcpy format e.g. "1280"


class ScrcpyMirrorRunner:
    """
    Manage a standalone scrcpy process for on-screen mirroring.

    Constraints:
    - Must only terminate the process tree started by this instance.
    - Windows stop uses `taskkill /pid <pid> /T /F`.
    """

    def __init__(
        self,
        *,
        serial: str,
        adb_path: str,
        scrcpy_path: str,
        window_title: str = "MonkeyAutoTest - 投屏",
        always_on_top: bool = False,
        no_audio: bool = True,
        forward_audio: Optional[bool] = None,
        turn_screen_off: bool = False,
        stay_awake: bool = True,
        params: Optional[ScrcpyMirrorParams] = None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.serial = serial
        self.adb_path = adb_path
        self.scrcpy_path = scrcpy_path
        self.window_title = window_title
        self.always_on_top = always_on_top
        # 兼容两种调用方式：
        # - forward_audio=True/False（推荐）
        # - no_audio=True/False（历史参数）
        if forward_audio is None:
            self.no_audio = no_audio
        else:
            self.no_audio = not bool(forward_audio)
        self.turn_screen_off = turn_screen_off
        self.stay_awake = stay_awake
        self.params = params or ScrcpyMirrorParams()
        self.log_callback = log_callback or (lambda _msg: None)

        self._p: Optional[subprocess.Popen[bytes]] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def is_running(self) -> bool:
        return self._p is not None and (self._p.poll() is None)

    def start(self) -> None:
        with self._lock:
            if self.is_running():
                return

            scrcpy_bin = self.scrcpy_path.strip() or "scrcpy"

            cmd: list[str] = [
                scrcpy_bin,
                "--serial",
                self.serial,
                "--window-title",
                self.window_title,
            ]

            if self.stay_awake:
                cmd.append("--stay-awake")
            if self.turn_screen_off:
                cmd.append("--turn-screen-off")
            if self.always_on_top:
                cmd.append("--always-on-top")
            if self.no_audio:
                # 避免投屏会话接管设备音频，保证待测设备可正常外放。
                cmd.append("--no-audio")

            if self.params.max_fps is not None:
                cmd.extend(["--max-fps", str(int(self.params.max_fps))])
            if self.params.video_bit_rate:
                cmd.extend(["--video-bit-rate", str(self.params.video_bit_rate)])
            if self.params.max_size:
                cmd.extend(["--max-size", str(self.params.max_size)])

            # Notes:
            # - We intentionally do NOT add `--no-playback` here: mirror window is required.
            # - Scrcpy handles touch interaction itself.

            env = os.environ.copy()
            adb_bin = self.adb_path.strip()
            if adb_bin:
                env["ADB"] = adb_bin

            self._p = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd(),
                env=env,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )

            self._reader_thread = _start_output_reader(self._p, self.log_callback)
            self.log_callback(f"[mirror] scrcpy 已启动: serial={self.serial}")

    def stop(self, *, wait_seconds: float = 2.0) -> None:
        with self._lock:
            p = self._p
            self._p = None

        if not p:
            return

        pid = p.pid
        try:
            _taskkill_tree(int(pid))
        finally:
            try:
                p.wait(timeout=wait_seconds)
            except Exception:
                pass

        self.log_callback("[mirror] scrcpy 已停止")


__all__ = ["ScrcpyMirrorRunner", "ScrcpyMirrorParams"]

