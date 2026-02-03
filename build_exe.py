#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""MonkeyAutoTest - PyInstaller build helper

This script generates a clean PyInstaller .spec and an optional Windows .bat helper,
then runs PyInstaller to build the GUI executable.

Usage:
  python build_exe.py

Notes:
- Build outputs (build/, dist/, *.spec, *.exe) are intentionally ignored by .gitignore.
"""

from __future__ import annotations

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SPEC_NAME = "MonkeyTestGUI.spec"
EXE_NAME = "MonkeyTestGUI"
ENTRY = "gui_main.py"


def _run(cmd: list[str]) -> int:
    return subprocess.call(cmd, cwd=str(PROJECT_ROOT))


def check_pyinstaller() -> bool:
    try:
        import PyInstaller  # noqa: F401
        return True
    except Exception:
        return False


def write_spec_file() -> Path:
    spec_path = PROJECT_ROOT / SPEC_NAME

    # Keep this list explicit to avoid missing imports when building on Windows.
    hiddenimports = [
        "tkinter",
        "tkinter.ttk",
        "tkinter.scrolledtext",
        "tkinter.filedialog",
        "tkinter.messagebox",
        "utils.device",
        "utils.package",
        "utils.log",
        "utils.addition",
        "utils.get_apk",
        "utils.timeout_command",
        "utils.stability_test",
        "utils.performance_monitor",
        "utils.exception_recovery",
        "utils.extended_monkey",
        "utils.mock_server",
        "utils.network_proxy",
        "utils.pc_proxy_simulator",
        "utils.wifi_controller",
        "utils.baseline_manager",
        "utils.report_generator",
        "libs.send_mail",
    ]

    datas = [
        ("conf", "conf"),
        ("utils", "utils"),
        ("libs", "libs"),
        ("apks", "apks"),
        # 可选：内置 adb/aapt 等工具（若存在 tools 目录则一并打包）
        ("tools", "tools"),
        ("requirements.txt", "."),
        ("README.md", "."),
    ]

    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{ENTRY}'],
    pathex=['{PROJECT_ROOT.as_posix()}'],
    binaries=[],
    datas={datas!r},
    hiddenimports={hiddenimports!r},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{EXE_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
"""

    spec_path.write_text(spec_content, encoding="utf-8")
    print(f"Created spec: {spec_path}")
    return spec_path


def write_build_bat() -> Path:
    bat_path = PROJECT_ROOT / "build_exe.bat"
    bat_content = """@echo off
chcp 65001 >nul
setlocal

echo MonkeyAutoTest GUI build
echo =======================

python --version >nul 2>&1
if errorlevel 1 (
  echo ERROR: python not found
  exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
  echo Installing PyInstaller...
  pip install pyinstaller
  if errorlevel 1 (
    echo ERROR: failed to install pyinstaller
    exit /b 1
  )
)

python build_exe.py
exit /b %errorlevel%
"""

    bat_path.write_text(bat_content, encoding="utf-8")
    print(f"Created/updated bat: {bat_path}")
    return bat_path


def main() -> int:
    if not (PROJECT_ROOT / ENTRY).exists():
        print(f"ERROR: entry not found: {ENTRY}")
        return 2

    if not check_pyinstaller():
        print("PyInstaller not installed. Run: pip install pyinstaller")
        return 2

    write_spec_file()
    write_build_bat()

    print("Running PyInstaller...")
    return _run([sys.executable, "-m", "PyInstaller", "--noconfirm", SPEC_NAME])


if __name__ == "__main__":
    raise SystemExit(main())
