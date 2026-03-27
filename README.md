# 车载端侧应用自动化测试工具

一个强大的Android应用测试框架，支持传统Monkey测试和先进的车载端侧稳定性测试。提供现代化图形用户界面，让测试人员和非技术用户也能轻松使用。

## 目录

- [快速开始](#快速开始)
- [环境要求](#环境要求)
- [配置说明](#配置说明)
- [GUI功能特性](#gui功能特性)
- [GUI使用指南](#gui使用指南)
- [功能模块说明](#功能模块说明)
- [测试原理与执行机制](#测试原理与执行机制)
- [常见操作与故障排除](#常见操作与故障排除)

## 快速开始

### 环境准备

在启动项目之前，请确保已完成以下准备工作：

1. **安装Python 3.13+**：验证安装
   ```bash
   python --version
   ```

2. **克隆或下载项目**：
   ```bash
   git clone <repository-url>
   cd MonkeyAutoTest
   ```

3. **安装项目依赖**（选择其中一种方式）：
   
   **使用uv（推荐）**：
   ```bash
   # 安装uv包管理器
   pip install uv
   
   # 同步项目依赖
   uv sync
   ```
   
   **使用pip**：
   ```bash
   # 创建并激活虚拟环境
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   # source .venv/bin/activate  # Linux/macOS
   
   # 安装依赖
   pip install -r requirements.txt
   ```

4. **配置ADB路径**：
   - 确保ADB已安装并添加到系统PATH，或
   - 在项目根目录的`tools/adb/`文件夹中放置`adb.exe`

5. **配置项目文件**：
   - 编辑`conf/project.json`配置项目信息
   - 编辑`conf/mail.ini`配置邮件发送信息（如需邮件通知）

### 启动方法

#### 方法1：GUI图形界面启动（推荐新手使用）

```bash
python gui_main.py
```

GUI界面提供直观的操作体验，适合测试人员和非技术用户使用，包含：
- 项目配置、设备状态、测试操作等功能卡片
- Monkey遮罩区域配置
- 实时日志显示和进度监控
- 一键启动传统Monkey测试或稳定性测试

#### 方法2：命令行启动传统Monkey测试

```bash
python main.py -v VERSION -s SN -p APK_PATH -r RECIPIENT
```

**参数说明：**
- `-v/--version`：项目版本（必需，从conf/project.json选择）
- `-s/--sn`：设备序列号（必需，支持多设备："dev1 dev2"）
- `-p/--path` 或 `-u/--url`：APK文件路径或下载URL（必需）
- `-r/--recipient`：邮件收件人（必需，支持多收件人）

**可选参数：**
- `-i/--uninstall`：安装前卸载旧版本
- `-t/--throttle`：Monkey事件间隔（默认700ms）
- `-c/--count`：Monkey事件数量（默认10000）

#### 方法3：命令行启动车载端侧稳定性测试 🆕

**基本启动命令：**
```bash
# 基本测试（12小时完整测试套件）
python main.py --stability -s emulator-5554 -p apks/app-debug.apk

# 快速验证（1小时）
python main.py --stability --duration 1 -s emulator-5554 -p apks/app-debug.apk

# 长时间测试（24小时）
python main.py --stability -s emulator-5554 -p apks/app-debug.apk --duration 24

# 多设备并行测试
python main.py --stability -s "device1 device2 device3" -p app.apk
```

**高级启动选项：**
```bash
# 使用pytest框架（支持CI/CD集成）
python main.py --stability -s device -p app.apk

# 专项测试
python main.py --stability --performance-only -s device -p app.apk  # 仅性能测试
python main.py --stability --robustness-only -s device -p app.apk   # 仅 Monkey 压力测试

# 自定义配置
python main.py --stability -s device -p app.apk --config my_config.json

# 禁用可选功能
python main.py --stability -s device -p app.apk --no-mock-server --no-network-proxy
```

#### 方法4：打包后的可执行文件启动（Windows）

如果需要在没有Python环境的机器上运行，可以使用打包功能：

```bash
# 首次使用需要打包
python build_exe.py  # 准备打包环境
build_exe.bat        # 执行打包

# 运行可执行文件
dist/MonkeyTestGUI.exe
```

**注意事项：**
- 打包后的EXE文件会自动携带并优先使用项目内置的 `tools/adb/adb.exe`
- 打包过程会将所有依赖打包进单一可执行文件，文件体积较大但便于分发

## 环境要求

### 系统要求
- **Python**：3.13 或更高版本 (推荐使用最新稳定版)
- **ADB**：Android Debug Bridge (已配置PATH或在项目tools/adb/目录下放置adb.exe)
- **Java**：JDK 8+ (用于APK解析)
- **操作系统**：Windows/macOS/Linux (支持Android设备连接)

### 开发环境配置

#### Python环境要求
- **Python版本**：项目要求 Python >= 3.13
- **虚拟环境**：推荐使用虚拟环境隔离项目依赖
- **uv工具**：现代Python包管理工具，用于依赖管理和环境管理

#### 环境变量配置
根据需要配置以下环境变量：

- `ADB_PATH`：指定ADB工具路径（如果不配置，程序会自动搜索系统PATH或使用内置tools/adb/adb.exe）
- `AAPT_PATH`：指定aapt工具路径（用于APK解析，程序会自动搜索系统PATH或使用内置tools/aapt/目录）
- `PYTHONPATH`：如有需要可添加项目路径

#### 依赖安装方法

**方法1：使用uv工具（推荐）**
```bash
# 安装uv（如果尚未安装）
pip install uv

# 进入项目根目录后执行
cd MonkeyAutoTest  # 或使用您的项目实际路径
uv sync

# 或者只安装运行时依赖
uv pip install -r requirements.txt
```

**方法2：使用pip**
```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# 或
.venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

**方法3：手动安装核心依赖**
```bash
pip install mitmproxy pytest pytest-html pytest-cov pytest-timeout pytest-xdist pyyaml requests ttkbootstrap matplotlib
```

#### 项目特定配置
- **ADB配置**：在项目根目录下的 `tools/adb/` 中放置 `adb.exe`，程序会自动优先使用内置adb
- **aapt配置**：在 `tools/aapt/` 中放置 `aapt.exe`，用于APK包名和启动Activity解析
- **配置文件**：确保 `conf/project.json` 和 `conf/mail.ini` 存在并正确配置
- **GUI 配置**：`conf/test_ui_config.json` 与 `baselines/performance_baseline.json` 已被 .gitignore 排除，首次使用可复制对应 `.example` 文件并重命名

## 配置说明

### 项目配置 (conf/project.json)

项目配置文件定义了所有可测试的项目版本及其相关配置。该文件是JSON格式，位于`conf/project.json`。

#### 基础配置格式

```json
{
  "版本标识符": {
    "name": "项目显示名称",
    "auto_get_apk": false
  }
}
```

#### 配置参数说明

##### 版本标识符 (Key)
- **格式**：字符串，如`"ver1"`, `"v2.1.0"`, `"stability_test"`
- **用途**：在命令行中使用`-v/--version`参数指定
- **示例**：`-v ver1` 或 `-v stability_test`

##### 通用参数

**name** (必需)
- **类型**：字符串
- **描述**：项目的显示名称，用于报告和邮件标题
- **示例**：`"车载导航应用 v1.0"`

**auto_get_apk** (可选)
- **类型**：布尔值
- **默认值**：`false`
- **描述**：是否自动获取最新APK包
  - `true`：自动从配置的源获取最新包
  - `false`：使用指定的APK文件或URL（通过`-u`或`-p`参数）

**apk_source** (当auto_get_apk为true时必需)
- **类型**：对象
- **描述**：定义APK包的获取源配置

**支持的源类型：**

**HTTP/HTTPS源**
```json
{
  "apk_source": {
    "type": "http",
    "url": "https://example.com/latest.apk",
    "download_path": "./apks/"
  }
}
```

**FTP源**
```json
{
  "apk_source": {
    "type": "ftp",
    "host": "ftp.example.com",
    "username": "user",
    "password": "pass",
    "remote_path": "/path/to/apk/",
    "filename_pattern": "app-*.apk"
  }
}
```

**本地脚本源**
```json
{
  "apk_source": {
    "type": "script",
    "script_path": "./scripts/get_latest_apk.py",
    "args": ["--branch", "master"]
  }
}
```

**参数验证规则**
- 版本标识符必须是有效的JSON对象键名
- `name` 不得为空，长度不超过100字符
- `auto_get_apk` 必须是布尔值
- 当 `auto_get_apk` 为 `true` 时，必须提供有效的 `apk_source` 配置

### 邮件配置 (conf/mail.ini)

用于配置测试结果邮件通知功能。

#### 配置格式

```ini
[mail]
smtp_server = smtp.gmail.com
smtp_port = 587
sender_email = your_email@gmail.com
sender_password = your_app_password
use_tls = True
```

### 测试UI配置 (conf/test_ui_config.json)

用于配置GUI界面中的测试参数默认值。

#### 配置格式

```json
{
  "default_params": {
    "throttle": 700,
    "count": 10000,
    "timeout": 60000,
    "mask_top": 0.0,
    "mask_bottom": 0.0,
    "mask_left": 0.0,
    "mask_right": 0.0
  },
  "network_methods": [
    {"label": "root", "value": "root"},
    {"label": "pc_proxy", "value": "pc_proxy"},
    {"label": "wifi_control", "value": "wifi_control"},
    {"label": "app_simulation", "value": "app_simulation"}
  ]
}
```

## GUI功能特性

项目提供了图形用户界面版本，无需命令行操作，适合测试人员和非技术用户使用。

### GUI启动方法

#### 方法1：直接运行Python脚本
```bash
python gui_main.py
```

#### 方法2：运行打包的可执行文件 (Windows)
```bash
# 首次使用需要打包
python build_exe.py  # 准备打包环境
build_exe.bat        # 执行打包

# 运行可执行文件
dist/MonkeyTestGUI.exe
```

### GUI核心功能

- ✅ **现代化界面设计**：采用卡片式布局，符合专业工具标准
- ✅ **直观的色彩体系**：亮蓝色主色，绿色成功，红色警告，橙色进度
- ✅ **步骤化操作引导**：完整测试套件 vs 模块化测试选择
- ✅ **实时状态监控**：设备连接状态、测试进度、详细日志
- ✅ **模块化测试支持**：可选择性启用各个测试模块
- ✅ **一键操作**：传统Monkey测试和稳定性测试一键启动
- ✅ **报告集成**：内置报告查看器，支持HTML和JSON格式
- ✅ **智能验证**：参数验证、模块依赖检查、错误提示
- ✅ **Monkey遮罩区域配置**：支持设置屏幕遮罩区域，避免在特定区域进行Monkey测试
- ✅ **测试参数自定义**：可灵活配置测试时长、网络模拟方法、多设备支持等

### GUI界面详解

#### 界面布局
```
┌─────────────────────────────────────────────────────────────┐
│ 🚀 Monkey自动化测试工具 v1.0.0                              │
│ 车载端侧应用稳定性测试平台 | v1.0.0                          │
├─────────────────┬─────────────────────────────────────────────┤
│ 📋 项目配置     │ 📱 设备状态                                 │
│ • 版本选择      │ • 连接设备列表                              │
│ • 设备配置      │ • 状态指示器                                │
│ • APK选择       │                                             │
├─────────────────┼─────────────────────────────────────────────┤
│ ⚡ 测试操作      │ 📊 测试进度                                 │
│ • 模式选择      │ • 当前状态                                  │
│ • 模块选择      │ • 进度条                                    │
│ • 操作按钮      │ • 详细信息                                  │
├─────────────────┼─────────────────────────────────────────────┤
│ 🔧 快速操作      │ 📝 实时日志                                 │
│ • 传统测试      │ • 日志显示                                  │
│ • 报告查看      │ • 保存/清空                                 │
│ • 日志清理      │                                             │
└─────────────────┴─────────────────────────────────────────────┘
```

- **顶部标题区**：显示工具名称和版本信息
- **左侧操作面板**：项目配置、测试操作、快速操作
- **右侧状态面板**：设备状态、测试进度、实时日志

#### 功能区域详解

1. **📋 项目配置卡片**
   - 选择测试项目版本
   - 配置目标设备序列号
   - 选择或浏览测试APK文件
   - 一键刷新设备连接状态

2. **⚡ 测试操作卡片**
   - **测试模式选择**：
     - 完整测试套件：运行所有测试模块
     - 模块化测试：可选择性启用特定模块
   - **模块选择**（模块化测试时）：
     - 🏗️ Monkey 模式压力测试（长时间压力测试）
     - 🔄 异常恢复测试（网络/数据异常）
     - 📊 完整性能测试（响应+资源）
     - ⚡ 仅响应性能测试（冷启动、延迟）
     - 💾 仅资源消耗测试（CPU、内存）
   - **操作按钮**：开始测试、停止测试

3. **🔧 快速操作卡片**
   - 🐒 传统Monkey测试：快速启动标准Monkey测试
   - 📄 查看测试报告：打开报告查看器窗口
   - 🗑️ 清除日志：清空实时日志显示

4. **📱 设备状态卡片**
   - 显示ADB连接的设备列表
   - 实时设备连接状态指示
   - 设备数量统计

5. **📊 测试进度卡片**
   - 当前测试状态显示
   - 进度条指示测试进度
   - 详细进度信息展示

6. **📝 实时日志卡片**
   - 实时显示测试执行日志
   - 支持日志保存和清空操作
   - 自动滚动到最新日志

7. **⚙️ 测试配置窗口**
   - 通过"打开测试配置窗口"按钮访问
   - 包含所有高级测试参数设置
   - 包括Monkey遮罩区域配置
   - 包括网络模拟方法选择
   - 包括多设备支持配置

#### 色彩体系说明
- 🔵 **亮蓝色 (#1677FF)**：主要操作按钮和链接
- 🟢 **绿色 (#52C41A)**：成功状态和确认操作
- 🔴 **红色 (#FF4D4F)**：错误状态和停止操作
- 🟠 **橙色 (#FAAD14)**：进度指示和警告信息
- ⚪ **白色/浅灰**：主要背景和卡片容器

## GUI使用指南

### 基本操作流程

1. **启动GUI**
   ```bash
   python gui_main.py
   ```

2. **配置测试环境**
   - 在"项目配置"卡片中选择测试项目版本
   - 输入目标设备序列号
   - 选择或浏览测试APK文件
   - 点击"刷新设备列表"确认设备连接

3. **选择测试模式**
   - **完整测试套件**：运行所有测试模块（推荐）
   - **模块化测试**：选择特定测试模块运行

4. **开始测试**
   - 点击"开始测试"按钮启动测试
   - 观察右侧面板的进度和日志信息
   - 测试完成后查看生成的报告

### 高级功能使用

#### Monkey遮罩区域配置
在测试配置窗口中可以设置屏幕遮罩区域，以避免在特定区域进行Monkey测试：

1. 点击"打开测试配置窗口"
2. 在"测试参数设置"区域找到"Monkey 遮罩区域（百分比 0.0 - 100.0）"
3. 设置四个边缘的遮罩百分比：
   - 上边缘：屏幕顶部遮罩百分比
   - 下边缘：屏幕底部遮罩百分比
   - 左边缘：屏幕左侧遮罩百分比
   - 右边缘：屏幕右侧遮罩百分比
4. 点击"生成当前遮罩预览"查看遮罩效果
5. 点击"打开最近遮罩图"查看最近生成的遮罩图像

#### 网络模拟方法选择
在测试配置窗口中可以选择不同的网络模拟方法：
- **root**：设备侧硬切网络（需要root权限）
- **pc_proxy**：PC端代理劫持/故障注入
- **wifi_control**：路由器侧控制
- **app_simulation**：应用内开关

#### 多设备支持
在测试配置窗口中可以配置多设备测试：
- 在"设备序列号(多个用空格分隔)"中输入多个设备序列号
- 用空格分隔多个设备

### 模块化测试说明

当选择"模块化测试"模式时，可以单独启用以下模块：

| 模块 | 适用场景 | 耗时 | 说明 |
|------|----------|------|------|
| Monkey 模式压力测试 | 验证应用基本稳定性 | 12-72小时 | 通过长时间Monkey测试验证应用稳定性 |
| 异常恢复 | 测试网络/数据异常处理 | 中等 | 模拟网络异常、数据异常等场景 |
| 完整性能 | 全面性能评估 | 较长 | 包括响应性能和资源消耗测试 |
| 仅响应性能 | 快速响应时间检查 | 短 | 专注于冷启动时间和响应延迟 |
| 仅资源消耗 | 资源使用情况监控 | 中等 | 专注于CPU和内存使用情况 |

### 常见操作

- **查看报告**：点击"查看测试报告"按钮打开报告浏览器
- **保存日志**：在日志面板中点击"保存日志"导出测试日志
- **停止测试**：点击"停止测试"按钮中断正在进行的测试
- **清空日志**：点击"清空"按钮清除日志显示
- **打开配置窗口**：点击"打开测试配置窗口"进行高级配置
- **生成遮罩预览**：在配置窗口中点击"生成当前遮罩预览"查看遮罩效果

### 状态指示器说明

- 🔵 **亮蓝色按钮**：可点击的主要操作
- 🟢 **绿色状态**：正常/成功状态
- 🔴 **红色状态**：错误/停止状态
- 🟠 **橙色进度条**：测试执行进度
- ⚪ **灰色按钮**：禁用/不可用状态

### ADB / 工具配置与故障排除

- **ADB 路径配置**
  - 推荐在项目根目录下的 `tools/adb/` 中放置 `adb.exe`（打包后的 EXE 会自动携带并优先使用该内置 adb）
  - 也可以在 GUI 右侧的 "ADB路径" 输入框中手动选择 `adb.exe`，程序会记住该路径，并在所有 `adb ...` 命令中优先使用
  - 命令行/pytest 模式下，可通过环境变量 `ADB_PATH` 指定 adb 路径，或依赖系统 PATH 中的 adb
- **aapt 配置**
  - 若项目根目录存在 `tools/aapt/aapt.exe`，将优先用于解析 APK 包名/启动 Activity
  - 否则会尝试从 `AAPT_PATH` 环境变量或 Android SDK 的 `build-tools` 目录中自动寻找 `aapt(.exe)`
- **设备未连接**：检查ADB服务是否启动，确认设备USB调试已开启
- **APK文件错误**：确认APK文件存在且未损坏
- **测试启动失败**：检查日志信息，确认所有必要参数已正确配置；若提示找不到 adb/aapt，请按上述方式配置路径
- **界面无响应**：可能是后台测试进程导致，尝试重启GUI程序

## 功能模块说明

### 传统Monkey测试模式
- 自动化Monkey压力测试
- 多设备并行测试支持
- 灵活的APK获取方式（URL下载、本地文件、自动脚本）
- 网络环境保障（Wifi Manager + simiasque）
- 智能崩溃和ANR检测与报告
- 邮件通知功能（可选）

### 车载端侧稳定性测试模式 🆕
- **Monkey 模式压力测试**：12-72小时长时间压力测试
- **异常恢复测试**：网络断开、弱网、数据异常等场景
- **性能监控**：启动时间、响应延迟、CPU/内存使用率
- **Mock服务**：模拟云端API，支持异常数据测试
- **网络代理**：弱网/断网环境模拟
- **智能报告**：HTML/JSON报告 + 性能图表
- **一键操作**：简化命令，快速启动完整测试流程

### Monkey遮罩区域功能
- **功能目的**：允许用户设置屏幕上的安全区域，避免Monkey测试在敏感区域进行操作
- **配置方式**：通过百分比设置四个边缘的遮罩区域
- **预览功能**：实时生成遮罩预览图，帮助用户确认遮罩效果
- **应用场景**：保护系统导航栏、状态栏、重要UI元素等

## 测试原理与执行机制（重点：如何施压与验证稳定性）

本项目的"压力测试/稳定性验证"本质上都是通过 **ADB 在设备上执行一系列可重复的操作**（安装/启动/停止/随机输入/网络切换/代理/抓取性能与日志），再对 **Crash/ANR/性能指标** 做统计与判定。

### 1) 传统Monkey测试（随机事件压力）

**工作原理（随机事件生成）**
- **事件来源**：Android 自带 `monkey` 工具随机生成输入事件（触摸、滑动、按键等），并注入到系统事件队列，从而驱动应用在各种路径下运行。
- **核心压力点**：高频、长时间、不可预测的 UI 操作序列会触发更多边界状态（生命周期切换、页面跳转、资源竞争、异常输入等），暴露崩溃与 ANR。

**执行机制（项目里实际做了什么）**
- **准备阶段**：安装待测 APK；安装并启动 `Wifi Manager` 与 `simiasque` 以保障测试期间网络连通性（见 `utils/addition.py`）。
- **Monkey 执行**（见 `utils/device.py:run_monkey`）：
  - `adb shell am force-stop <package>`：确保从"干净停止态"开始
  - `adb shell monkey -p <package> -s <seed> --ignore-crashes --ignore-timeouts --throttle <ms> -v <count> > <log>`：执行随机事件并落盘日志
  - 结束后再次 `force-stop`，并进入日志分析流程
- **结果采集**：`dumpsys activity` 保存现场；`DeviceLog.check()` 分析 crash/anr 并生成拆分日志，再通过邮件发送（见 `utils/log.py` + `utils/addition.py`）。

**节流时间（throttle）与事件数量（count）如何形成"压力强度"**
- **`--throttle <ms>`**：每个事件之间的间隔，越小越"密集"（更强压力），但也更容易造成设备输入队列拥塞或误判。
- **`-v <count>`**：事件总数，越大持续越久、覆盖更多随机路径。
- **经验理解**：测试时长大致与 \(count \times throttle\) 成正比（再叠加系统处理开销）。

### 2) 稳定性测试（长时压力 + 异常注入 + 性能观测）

稳定性测试入口是 `main.py --stability`，核心执行在 `utils/stability_test.py`，按模块执行：

#### 2.1 Monkey 模式压力测试（长时间压力）

**怎么施压**
- 通过 `utils/extended_monkey.py:ExtendedMonkeyTest` 执行 **12–72 小时长时 Monkey**，并按小时拆成多个阶段（避免单进程过久难以管理）。
- 每个阶段的关键动作：
  - `pm clear <package>`：清理应用数据（迫使应用反复经历"首次启动/冷启动/初始化"等高风险路径）
  - `am force-stop <package>`：重置进程
  - `adb shell monkey ... --throttle ... -v <阶段事件数>`：持续随机输入施压
  - 解析阶段日志中的 `// CRASH:` 与 `// NOT RESPONDING:` 统计 crash/anr

**怎么验证**
- **Crash/ANR**：从 monkey 日志关键字统计 + 设备日志分析。
- **性能采样**：后台线程每 30s 采样一次：
  - `top` 解析 CPU
  - `dumpsys meminfo` 解析 PSS 内存

#### 2.2 异常恢复测试（网络异常注入）

**怎么施压**
- **网络异常**：通过多种方式模拟网络不稳定：
  - **Root 设备**：利用 iptables 控制网络（见 `utils/network_proxy.py`）
  - **PC 代理**：通过 mitmproxy 注入网络延迟、丢包、故障（见 `utils/mitmproxy_mock.py`）
  - **路由器控制**：通过 Wi-Fi 控制器操作路由器（见 `utils/wifi_controller.py`）
  - **App 内模拟**：通过 Mock 服务返回异常数据（见 `utils/mock_server.py`）

**怎么验证**
- **网络恢复能力**：监测网络异常发生后，应用是否能恢复正常功能
- **数据一致性**：检查异常恢复后数据是否一致（通过 Mock 服务记录对比）
- **资源泄漏**：监测网络频繁切换是否导致内存/CPU 泄漏

#### 2.3 性能测试（可量化的压力与指标）

**怎么施压**
- **冷启动测试**：`am force-stop` + 计时启动
- **响应延迟测试**：通过 Monkey 模拟 UI 操作 + 计时
- **资源监控**：持续采样 CPU/内存/流量

**怎么验证**
- **基准对比**：与 `baselines/performance_baseline.json` 中的基线数据对比
- **阈值判断**：检查性能指标是否超出预设阈值
- **趋势分析**：长期测试中的性能变化趋势

### 3) 模块化测试（只跑你关心的压力模块）

通过 `--robustness-only`、`--performance-only` 等参数，可单独运行特定模块，便于针对性测试。

### 4) 网络模拟测试（四种方法的原理对比）

- **Root 方式**：直接在设备上操作 iptables，最精确但需要 Root 权限
- **PC 代理**：通过 mitmproxy 在 PC 端劫持流量，无需 Root，但依赖网络配置
- **路由器控制**：通过控制路由器实现网络变化，对设备无要求，但需要特定硬件
- **App 内模拟**：通过 Mock 服务返回异常数据，仅测试 App 逻辑

### 5) Mock Server 的作用（可控的数据/服务异常）

Mock 服务器（见 `utils/mock_server.py`）用于：
- **模拟 API 异常**：返回错误码、超时、异常数据
- **数据验证**：记录请求内容，验证 App 行为是否符合预期
- **可控测试**：精确控制异常发生的时机和类型

## 常见操作与故障排除

### 常见问题解决

**Q: ADB连接失败**
A: 检查设备USB调试是否开启，尝试重启ADB服务：`adb kill-server && adb start-server`

**Q: 测试过程中设备断开连接**
A: 检查USB连接稳定性，考虑使用无线ADB或更换USB线缆

**Q: Monkey测试无法启动**
A: 确认APK已正确安装，包名正确，以及设备有足够的存储空间

**Q: 长时间测试时性能数据异常**
A: 检查设备是否发热严重，可能导致降频影响性能数据

### 性能优化建议

- 对于大型应用，适当调高`--throttle`参数避免过度压力
- 合理设置测试时长，避免设备过热
- 定期清理测试产生的临时文件
- 使用遮罩功能避开系统UI区域减少干扰

### 日志分析技巧

- `logs/` 目录包含详细的测试日志
- `crash_anr.log` 记录所有崩溃和ANR事件
- `performance.log` 包含性能监控数据
- 使用 `--html-report` 参数生成可视化报告

## 工程化与代码质量

- **静态检查与格式化**
  - **ruff 检查**：`ruff check .`
  - **ruff 格式化**：`ruff format .`
- **类型检查**
  - 对核心目录做类型检查：`mypy core infra gui`
- **测试与覆盖率**
  - 运行全部测试：`pytest`
  - 查看覆盖率（已在 `pyproject.toml` 中设置默认参数）：`pytest -q`

如需查看更详细的代码规范与贡献指南，可参考根目录下的 `CODING_STYLE.md` 与 `CONTRIBUTING.md`。