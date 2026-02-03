@echo off
chcp 65001 >nul
echo Monkey自动化测试工具 - Windows打包脚本
echo ========================================

REM 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python环境
    echo 请确保Python已安装并添加到PATH
    pause
    exit /b 1
)

echo ✓ 检测到Python环境

REM 检查PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo 正在安装PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo 错误: PyInstaller安装失败
        pause
        exit /b 1
    )
)

echo ✓ PyInstaller已安装

REM 创建输出目录
if not exist "dist" mkdir dist
if not exist "build" mkdir build

echo 正在清理旧的构建文件...
if exist "dist\\MonkeyTestGUI.exe" del "dist\\MonkeyTestGUI.exe"

echo 开始打包GUI应用...
python -m PyInstaller --clean --onefile --windowed --name=MonkeyTestGUI gui_main.py

if errorlevel 1 (
    echo 错误: 打包失败
    echo 尝试使用spec文件重新打包...
    if exist "MonkeyTestGUI.spec" (
        pyinstaller MonkeyTestGUI.spec
        if errorlevel 1 (
            echo 错误: spec文件打包也失败
            pause
            exit /b 1
        )
    ) else (
        pause
        exit /b 1
    )
)

echo.
echo ✓ 打包完成！
echo.
echo 可执行文件位置: dist\\MonkeyTestGUI.exe
echo.
echo 运行方法:
echo   双击 dist\\MonkeyTestGUI.exe 启动GUI界面
echo   或在命令行中运行: dist\\MonkeyTestGUI.exe
echo.
echo 注意事项:
echo - 首次运行可能需要一些时间来初始化
echo - 确保系统中已安装ADB工具
echo - 测试设备需要开启USB调试模式
echo.
pause