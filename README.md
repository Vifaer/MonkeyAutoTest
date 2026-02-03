# 车载端侧应用自动化测试工具

一个强大的Android应用测试框架，支持传统Monkey测试和先进的车载端侧稳定性测试。

## 目录

- [功能特性](#功能特性)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [测试流程](#测试流程)
- [环境要求](#环境要求)
- [使用注意事项](#使用注意事项)

## 功能特性

### 传统Monkey测试模式
- 自动化Monkey压力测试
- 多设备并行测试支持
- 灵活的APK获取方式（URL下载、本地文件、自动脚本）
- 网络环境保障（Wifi Manager + simiasque）
- 智能崩溃和ANR检测与报告
- 邮件通知功能（可选）

### 车载端侧稳定性测试模式 🆕
- **系统健壮性测试**：12-72小时长时间压力测试
- **异常恢复测试**：网络断开、弱网、数据异常等场景
- **性能监控**：启动时间、响应延迟、CPU/内存使用率
- **Mock服务**：模拟云端API，支持异常数据测试
- **网络代理**：弱网/断网环境模拟
- **智能报告**：HTML/JSON报告 + 性能图表
- **一键操作**：简化命令，快速启动完整测试流程

## GUI版本 (推荐新用户使用)

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

### GUI功能特性

- ✅ **现代化界面设计**：采用卡片式布局，符合专业工具标准
- ✅ **直观的色彩体系**：亮蓝色主色，绿色成功，红色警告，橙色进度
- ✅ **步骤化操作引导**：完整测试套件 vs 模块化测试选择
- ✅ **实时状态监控**：设备连接状态、测试进度、详细日志
- ✅ **模块化测试支持**：可选择性启用各个测试模块
- ✅ **一键操作**：传统Monkey测试和稳定性测试一键启动
- ✅ **报告集成**：内置报告查看器，支持HTML和JSON格式
- ✅ **智能验证**：参数验证、模块依赖检查、错误提示

### GUI界面说明

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
     - 🏗️ 系统健壮性测试（长时间压力测试）
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

#### 色彩体系说明
- 🔵 **亮蓝色 (#1677FF)**：主要操作按钮和链接
- 🟢 **绿色 (#52C41A)**：成功状态和确认操作
- 🔴 **红色 (#FF4D4F)**：错误状态和停止操作
- 🟠 **橙色 (#FAAD14)**：进度指示和警告信息
- ⚪ **白色/浅灰**：主要背景和卡片容器

### GUI使用指南

#### 基本操作流程

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

#### 模块化测试说明

当选择"模块化测试"模式时，可以单独启用以下模块：

| 模块 | 适用场景 | 耗时 |
|------|----------|------|
| 系统健壮性 | 验证应用基本稳定性 | 12-72小时 |
| 异常恢复 | 测试网络/数据异常处理 | 中等 |
| 完整性能 | 全面性能评估 | 较长 |
| 仅响应性能 | 快速响应时间检查 | 短 |
| 仅资源消耗 | 资源使用情况监控 | 中等 |

#### 常见操作

- **查看报告**：点击"查看测试报告"按钮打开报告浏览器
- **保存日志**：在日志面板中点击"保存日志"导出测试日志
- **停止测试**：点击"停止测试"按钮中断正在进行的测试
- **清空日志**：点击"清空"按钮清除日志显示

#### 状态指示器说明

- 🔵 **亮蓝色按钮**：可点击的主要操作
- 🟢 **绿色状态**：正常/成功状态
- 🔴 **红色状态**：错误/停止状态
- 🟠 **橙色进度条**：测试执行进度
- ⚪ **灰色按钮**：禁用/不可用状态

#### ADB / 工具配置与故障排除

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

## 测试原理与执行机制（重点：如何施压与验证稳定性）

本项目的“压力测试/稳定性验证”本质上都是通过 **ADB 在设备上执行一系列可重复的操作**（安装/启动/停止/随机输入/网络切换/代理/抓取性能与日志），再对 **Crash/ANR/性能指标** 做统计与判定。

### 1) 传统Monkey测试（随机事件压力）

**工作原理（随机事件生成）**
- **事件来源**：Android 自带 `monkey` 工具随机生成输入事件（触摸、滑动、按键等），并注入到系统事件队列，从而驱动应用在各种路径下运行。
- **核心压力点**：高频、长时间、不可预测的 UI 操作序列会触发更多边界状态（生命周期切换、页面跳转、资源竞争、异常输入等），暴露崩溃与 ANR。

**执行机制（项目里实际做了什么）**
- **准备阶段**：安装待测 APK；安装并启动 `Wifi Manager` 与 `simiasque` 以保障测试期间网络连通性（见 `utils/addition.py`）。
- **Monkey 执行**（见 `utils/device.py:run_monkey`）：
  - `adb shell am force-stop <package>`：确保从“干净停止态”开始
  - `adb shell monkey -p <package> -s <seed> --ignore-crashes --ignore-timeouts --throttle <ms> -v <count> > <log>`：执行随机事件并落盘日志
  - 结束后再次 `force-stop`，并进入日志分析流程
- **结果采集**：`dumpsys activity` 保存现场；`DeviceLog.check()` 分析 crash/anr 并生成拆分日志，再通过邮件发送（见 `utils/log.py` + `utils/addition.py`）。

**节流时间（throttle）与事件数量（count）如何形成“压力强度”**
- **`--throttle <ms>`**：每个事件之间的间隔，越小越“密集”（更强压力），但也更容易造成设备输入队列拥塞或误判。
- **`-v <count>`**：事件总数，越大持续越久、覆盖更多随机路径。
- **经验理解**：测试时长大致与 \(count \times throttle\) 成正比（再叠加系统处理开销）。

### 2) 稳定性测试（长时压力 + 异常注入 + 性能观测）

稳定性测试入口是 `main.py --stability`，核心执行在 `utils/stability_test.py`，按模块执行：

#### 2.1 系统健壮性测试（长时间压力）

**怎么施压**
- 通过 `utils/extended_monkey.py:ExtendedMonkeyTest` 执行 **12–72 小时长时 Monkey**，并按小时拆成多个阶段（避免单进程过久难以管理）。
- 每个阶段的关键动作：
  - `pm clear <package>`：清理应用数据（迫使应用反复经历“首次启动/冷启动/初始化”等高风险路径）
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
- 由 `utils/exception_recovery.py:ExceptionRecoveryTest` 触发网络场景：
  - **断网**：在指定时长内让设备处于无网络状态
  - **弱网**：引入延迟/丢包/带宽限制等（当前实现以延迟/丢包为主）
  - **恢复**：恢复网络后观察应用是否能自愈（重新请求、UI恢复、无崩溃/ANR）

**怎么实现（root vs 非root）**
- **root（默认）**：`utils/network_proxy.py:NetworkConditionSimulator`
  - 断网：`adb shell svc wifi disable` + `svc data disable`；恢复则 enable
  - 弱网：启动 `mitmproxy`，在代理脚本中注入 delay/loss（模拟超时、慢响应、丢包）
- **非root**：`utils/network_proxy.py:NonRootNetworkSimulator`
  - `pc_proxy`：通过把设备 `http_proxy/https_proxy` 指向 PC 代理（见 `utils/pc_proxy_simulator.py`），用 503/504 等响应模拟“断网/丢包”，并可注入延迟
  - `wifi_control`：通过路由器/网络设备对指定 MAC 做断开或 QoS（见 `utils/wifi_controller.py`，其中不同路由器 API 需按现场实现/接入）
  - `app_simulation`：需要应用配合，工具会尝试通过 ADB 广播/配置让应用进入离线/弱网模式（属于“应用内模拟”思路）

#### 2.3 性能测试（可量化的压力与指标）

由 `utils/performance_monitor.py:PerformanceMonitor` 提供三类测量：
- **冷启动时间**：多次执行
  - `am force-stop` + `adb shell am start -W -n <package>/<activity>`
  - 通过 `-W` 输出的时间（或执行耗时）统计平均/最小/最大/达标率
- **响应延迟（下发→展示）**：
  - 框架预留了“触发请求/测量展示时间差”的位置（具体触发方式需要按业务 App 的 UI/接口补齐）
- **资源消耗**：
  - 前台：启动应用后持续采样 CPU/内存
  - 后台：把应用切到后台继续采样，用于发现后台异常占用
  - 结合阈值（例如前台 CPU ≤30%，后台 ≤1%）与趋势（例如内存持续增长）判定风险

### 3) 模块化测试（只跑你关心的压力模块）

模块化测试是在稳定性测试之上提供“组合开关”，入口参数包括：
- `--modular`、`--robustness-only`、`--recovery-only`、`--performance-only`、`--response-only`、`--resource-only`

**执行机制**
- `utils/stability_test.py:ModularStabilityTest` 会先做通用准备（日志初始化、应用准备/安装/校验），再按选择的模块依次执行：
  - 系统健壮性：同 2.1（长时分阶段 Monkey）
  - 异常恢复：同 2.2（断网/弱网/恢复）
  - 性能：同 2.3（冷启动/响应/资源）

### 4) 网络模拟测试（四种方法的原理对比）

- **root（设备侧硬切网络）**：
  - 通过 `svc wifi/data disable/enable` 直接改变设备网络栈状态；真实、覆盖面广，但需要 root/权限环境允许
- **pc_proxy（代理劫持/故障注入）**：
  - 把设备系统代理指向 PC，在 PC 端用代理对请求做延迟/丢包/拒绝（503/504）模拟；不需要 root，但对不走系统代理或强证书校验的 App 有限制
- **wifi_control（路由器侧控制）**：
  - 对特定设备（MAC）做断开或 QoS；更贴近真实网络，但依赖路由器能力与接口
- **app_simulation（应用内开关）**：
  - 由 App 提供“离线/弱网/错误数据”开关或调试入口；最可控但需要 App 配合开发

### 5) Mock Server 的作用（可控的数据/服务异常）

**用途**
- 在异常恢复/稳定性场景中，除了“网络不好”，更常见的是“服务返回异常数据/错误码/慢响应”。Mock Server 用来把这类异常变成 **可控、可复现** 的输入。

**工作机制（项目里实际做了什么）**
- `utils/mock_server.py:MockServer` 在 PC 本机启动一个 HTTPServer，根据配置按路径/方法返回不同 JSON（可返回空数据、错误码、错误格式等）。
- `utils/exception_recovery.py` 会在需要时确保 Mock Server 就绪，并通过：
  - `adb reverse tcp:<port> tcp:<port>`（把设备侧端口转发到 PC）
  - 配置设备 `http_proxy`（把请求导向本机/代理）
  - 从而让应用“以为在访问服务端”，但实际拿到的是可控的 Mock 响应。

> 重点理解：**Mock Server 负责“造数据/造错误”，网络模拟负责“造网络条件”，Monkey/性能测试负责“造负载与操作序列”**。三者组合起来，才能覆盖稳定性风险的主要来源。

## 快速开始

### 传统Monkey测试

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

### 车载端侧稳定性测试 🆕

#### 推荐用法（一键脚本）
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

#### 高级用法
```bash
# 使用pytest框架（支持CI/CD集成）
python main.py --stability -s device -p app.apk

# 专项测试
python main.py --stability --performance-only -s device -p app.apk  # 仅性能测试
python main.py --stability --robustness-only -s device -p app.apk   # 仅健壮性测试

# 自定义配置
python main.py --stability -s device -p app.apk --config my_config.json

# 禁用可选功能
python main.py --stability -s device -p app.apk --no-mock-server --no-network-proxy
```

#### 直接使用main.py
```bash
python main.py --stability -s SN -p APK_PATH
```

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
    "url": "http://example.com/app-latest.apk",
    "auth": {
      "username": "user",
      "password": "password"
    }
  }
}
```

**Jenkins构建产物**
```json
{
  "apk_source": {
    "type": "jenkins",
    "url": "http://jenkins.example.com/job/app/lastSuccessfulBuild/artifact/app-debug.apk",
    "auth": {
      "username": "jenkins_user",
      "password": "api_token"
    }
  }
}
```

**FTP服务器**
```json
{
  "apk_source": {
    "type": "ftp",
    "host": "ftp.example.com",
    "port": 21,
    "path": "/releases",
    "filename": "app-latest.apk",
    "username": "ftp_user",
    "password": "ftp_password"
  }
}
```

**本地文件**
```json
{
  "apk_source": {
    "type": "local",
    "path": "/path/to/app.apk"
  }
}
```

##### 稳定性测试专用配置

当版本标识符为`"stability_test"`时，可以配置详细的稳定性测试参数：

```json
{
  "stability_test": {
    "name": "车载端侧应用稳定性测试",
    "auto_get_apk": false,
    "stability_config": {
      "long_stress": { ... },
      "performance": { ... },
      "exception_recovery": { ... }
    }
  }
}
```

###### long_stress - 长时间压力测试配置

**duration_hours**
- **类型**：整数
- **默认值**：12
- **单位**：小时
- **描述**：压力测试的总时长
- **建议值**：快速验证(1-2小时)，日常测试(12小时)，完整测试(24-72小时)

**throttle**
- **类型**：整数
- **默认值**：700
- **单位**：毫秒
- **描述**：Monkey事件之间的延迟时间
- **建议值**：500-1000ms（太快可能导致事件丢失，太慢效率低下）

**event_count**
- **类型**：整数
- **默认值**：100000
- **描述**：单个测试周期内生成的事件总数
- **建议值**：根据测试时长调整，12小时约10万-50万事件

###### performance - 性能监控配置

**sample_interval**
- **类型**：整数
- **默认值**：30
- **单位**：秒
- **描述**：性能采样间隔时间
- **建议值**：10-60秒（平衡监控精度和系统开销）

**monitor_duration**
- **类型**：整数
- **默认值**：3600
- **单位**：秒
- **描述**：性能监控总时长
- **建议值**：1800-7200秒（30分钟到2小时）

**cold_start_threshold**
- **类型**：浮点数
- **默认值**：3.0
- **单位**：秒
- **描述**：冷启动时间阈值，超过此值认为启动缓慢
- **建议值**：根据应用复杂度调整，2.0-5.0秒

**response_delay_threshold**
- **类型**：浮点数
- **默认值**：1.5
- **单位**：秒
- **描述**：UI响应延迟阈值，超过此值认为响应迟缓
- **建议值**：1.0-2.0秒（根据UI复杂度调整）

**cpu_foreground_threshold**
- **类型**：浮点数
- **默认值**：30.0
- **单位**：百分比
- **描述**：前台CPU使用率阈值，超过此值认为CPU占用过高
- **建议值**：20.0-50.0%（根据应用类型调整）

**cpu_background_threshold**
- **类型**：浮点数
- **默认值**：1.0
- **单位**：百分比
- **描述**：后台CPU使用率阈值，超过此值认为后台活动异常
- **建议值**：0.5-5.0%（后台服务正常范围）

###### exception_recovery - 异常恢复测试配置

**network_disconnect_duration**
- **类型**：整数
- **默认值**：30
- **单位**：秒
- **描述**：网络断开测试的持续时间
- **建议值**：10-60秒（足够触发网络异常但不影响整体测试）

**weak_network_duration**
- **类型**：整数
- **默认值**：60
- **单位**：秒
- **描述**：弱网环境模拟的持续时间
- **建议值**：30-120秒（覆盖典型弱网场景）

**mock_server_enabled**
- **类型**：布尔值
- **默认值**：true
- **描述**：是否启用Mock服务器用于异常数据测试
- **建议值**：true（开启以获得更全面的异常测试）

**network_proxy_enabled**
- **类型**：布尔值
- **默认值**：true
- **描述**：是否启用网络代理进行弱网/断网模拟
- **建议值**：true（推荐用于网络稳定性测试）

#### 完整配置示例

```json
{
  "ver1": {
    "name": "Sample App 1",
    "auto_get_apk": false
  },
  "ver2": {
    "name": "Sample App 2",
    "auto_get_apk": true,
    "apk_source": {
      "type": "jenkins",
      "url": "http://jenkins.example.com/job/app/lastSuccessfulBuild/artifact/app-debug.apk",
      "auth": {
        "username": "jenkins_user",
        "password": "api_token"
      }
    }
  },
  "stability_test": {
    "name": "车载端侧应用稳定性测试",
    "auto_get_apk": false,
    "stability_config": {
      "long_stress": {
        "duration_hours": 12,
        "throttle": 700,
        "event_count": 100000
      },
      "performance": {
        "sample_interval": 30,
        "monitor_duration": 3600,
        "cold_start_threshold": 3.0,
        "response_delay_threshold": 1.5,
        "cpu_foreground_threshold": 30.0,
        "cpu_background_threshold": 1.0
      },
      "exception_recovery": {
        "network_disconnect_duration": 30,
        "weak_network_duration": 60,
        "mock_server_enabled": true,
        "network_proxy_enabled": true
      }
    }
  }
}
```

#### Mock Server（用于数据/服务异常场景）

项目内置 Mock Server（`utils/mock_server.py`），可用于在稳定性测试的“异常恢复”阶段模拟服务端异常数据。

- **基本原理**：在PC本机启动 Mock Server（默认 `127.0.0.1:8080`），通过 `adb reverse tcp:PORT tcp:PORT` 将设备 `127.0.0.1:PORT` 转发到PC，并设置设备系统代理 `http_proxy/https_proxy=127.0.0.1:PORT`，使应用请求导向 Mock Server。
- **注意（HTTPS/不走系统代理）**：标准库 `HTTPServer` 不支持完整的 HTTPS 代理（CONNECT）。如果应用主要走 HTTPS 或不使用系统代理，需要改用 `mitmproxy/charles`（见 `utils/network_proxy.py`）来拦截并返回自定义响应。

Mock Server 相关配置建议放到 `stability_config` 的 `mock_server` 节点（`main.py` 已支持读取）：

```json
{
  "mock_server": {
    "enabled": true,
    "mode": "mitmproxy",
    "host": "127.0.0.1",
    "port": 8080,
    "default_path": "/api/data",
    "paths": ["/api/data", "/api/list"],
    "rules_path": "conf/mock_rules.json",
    "script_path": "conf/mitmproxy_mock_rules.py"
  }
}
```

其中：
- **enabled**：是否启用（也可用命令行 `--no-mock-server` 禁用）
- **mode**：
  - `httpserver`：仅HTTP/简单代理场景（项目内置 `HTTPServer`）
  - `mitmproxy`：HTTPS代理模式（推荐，支持 CONNECT，需要证书信任）
- **host/port**：PC本机监听地址与端口
- **default_path/paths**：需要被 Mock 的接口路径列表；未提供时默认 `/api/data`
- **rules_path**：规则文件（与GUI规则编辑器一致，JSON）
- **script_path**：生成的 mitmproxy 脚本保存路径（可编辑）

**HTTPS说明：**
- `mode=mitmproxy` 时，异常恢复模块会启动 `mitmproxy` 并尝试安装证书到设备（`utils/network_proxy.py`）。
- 如果设备/系统不允许自动安装用户证书、或App不信任用户CA，HTTPS解密会失败，此时需要手动将证书加入系统信任或使用测试包允许用户CA。

#### 配置验证

项目启动时会自动验证配置文件的有效性：
- JSON格式正确性
- 必需字段存在性
- 参数值合理性（数值范围、类型检查）

**注意事项：**
- 配置文件修改后无需重启项目，会自动重新加载
- 建议为不同测试场景创建不同的版本配置
- 稳定性测试配置是可选的，未配置时使用内置默认值
- 自动获取APK功能详见：`docs/auto_get_apk_usage.md`

### 邮件配置 (conf/mail.ini) - 可选

配置邮件通知（未配置时自动保存到日志文件）：

```ini
[gmail]
host = smtp.gmail.com
user = your-email@gmail.com
passwd = base64-encoded-password
name = Your Name
sender = your-email@gmail.com
```

**注意：** 密码需要进行base64编码。如未配置有效邮件，测试结果将自动保存到logs目录。

### 稳定性测试配置 - 可选

#### 使用内置配置（推荐）
项目已内置标准测试配置，覆盖：
- **系统健壮性**：12小时压力测试，崩溃/ANR检测
- **性能测试**：启动时间≤3秒，响应延迟≤1.5秒，资源监控
- **异常恢复**：网络异常、数据异常等场景测试
- **基线管理**：性能基线建立、版本对比、差异分析

#### 基线管理功能
项目支持性能基线的建立和对比，用于跟踪版本间的性能变化：

```bash
# 建立性能基线（首次运行或强制建立）
python main.py --stability -s device_sn --establish-baseline

# 与基线进行对比
python main.py --stability -s device_sn --compare-baseline
```

**基线数据包括：**
- 冷启动时间统计（平均值、最小值、最大值、达标率）
- UI响应延迟统计
- CPU使用率（前台/后台）
- 内存使用情况（PSS值、内存泄漏检测）
- 系统稳定性指标（崩溃次数、ANR次数）

#### 模块化测试配置

项目支持模块化测试，可以独立运行各个测试模块：

```bash
# 仅运行响应性能测试
python main.py --stability -s device --response-only

# 仅运行系统健壮性测试
python main.py --stability -s device --robustness-only

# 多模块组合运行
python main.py --stability -s device --modular --robustness-only --response-only
```

**支持的独立模块：**
- `--response-only`：仅响应性能测试（冷启动、下发→展示延迟）
- `--resource-only`：仅资源消耗测试（CPU、内存使用率）
- `--robustness-only`：仅系统健壮性测试（长时间Monkey测试）
- `--recovery-only`：仅异常恢复测试（网络异常、数据异常）
- `--performance-only`：仅完整性能测试（响应+资源）

#### 自定义配置
创建JSON文件覆盖默认设置：

```json
{
  "long_stress": {
    "duration_hours": 24,
    "throttle": 500,
    "event_count": 200000
  },
  "performance": {
    "cold_start_threshold": 3.0,
    "response_delay_threshold": 1.5,
    "cpu_foreground_threshold": 30.0
  },
  "exception_recovery": {
    "network_disconnect_duration": 30,
    "mock_server_enabled": true
  }
}
```

使用自定义配置：
```bash
python main.py --stability -s device -p app.apk --config custom.json
```

## 测试流程

### 传统Monkey测试流程

1. **初始化**：创建日志目录，验证参数配置
2. **APK获取**：根据参数从URL、本地文件或自动脚本获取APK
3. **设备测试**（多线程并行）：
   - 设备日志初始化
   - APK安装部署
   - 网络环境配置（Wifi Manager + simiasque）
   - 执行Monkey压力测试
   - 崩溃和ANR日志分析
   - 结果通知（邮件或日志文件）
4. **结果归档**：保存完整日志到历史记录

### 车载端侧稳定性测试流程 🆕

#### 自动执行流程

```bash
python main.py --stability -s device -p app.apk
```

框架自动完成以下步骤：

1. **环境验证**：ADB连接、设备状态、APK有效性检查
2. **测试环境部署**：应用安装、网络代理、Mock服务配置
3. **系统健壮性测试**：长时间Monkey测试，实时崩溃检测
4. **异常恢复测试**：网络异常、数据异常等场景验证
5. **性能监控**：启动时间、响应延迟、资源使用率测量
6. **智能报告生成**：HTML/JSON报告，性能图表，问题分析

#### 并行测试支持

```bash
python main.py --stability -s "device1 device2 device3" -p app.apk
```

- 每个设备独立运行完整测试套件
- 自动负载均衡和资源管理
- 测试完成后生成汇总报告

## 环境要求

### 系统要求
- **Python**：3.8 或更高版本
- **ADB**：Android Debug Bridge (已配置PATH)
- **Java**：JDK 8+ (用于APK解析)

### 依赖安装
```bash
pip install -r requirements.txt
```

### 可选依赖
```bash
# 网络代理功能
pip install mitmproxy

# pytest框架支持
pip install pytest pytest-html

# 非Root设备网络模拟支持
pip install requests  # 用于PC端代理转发

# GUI界面支持 (tkinter已内置，无需安装)
# 如需打包成exe文件，请安装PyInstaller:
pip install pyinstaller
```

## 使用注意事项

### APK管理
- 将测试APK放置在`apks/`目录下
- 自定义APK获取逻辑：编辑`utils/get_apk.py`
- 支持URL下载、本地文件、自动脚本获取

### 邮件通知（可选）
- 配置`conf/mail.ini`启用邮件通知
- 未配置时自动保存结果到logs目录
- 支持HTML格式报告和附件

### 测试最佳实践

#### 时长选择
- **快速验证**：1-2小时（`--duration 1`）
- **日常测试**：12小时（默认）
- **完整测试**：24-72小时（`--duration 24`）

#### 多设备测试
- 使用不同序列号避免冲突
- 监控设备温度和电池状态
- 建议设备性能充足，避免干扰

#### 网络测试注意
- Mock Server默认端口8080，确保可用
- 弱网模拟可能影响其他网络应用
- **网络模拟方法选择**：
  - `root`（默认）：需要设备root权限，直接控制设备网络
  - `pc_proxy`：通过PC端代理服务器模拟，无需设备root权限
  - `wifi_control`：通过WiFi路由器控制网络条件
  - `app_simulation`：应用内部模拟，需要应用配合实现

#### 非Root设备网络模拟
对于没有root权限的设备，可以使用以下方法：

```bash
# 使用PC端代理模拟（推荐）
python main.py --stability -s <device_sn> --network-method pc_proxy

# 使用WiFi路由器控制
python main.py --stability -s <device_sn> --network-method wifi_control

# 使用应用内部模拟
python main.py --stability -s <device_sn> --network-method app_simulation
```

**注意**：非root方法可能需要额外配置和应用配合实现。

### 故障排除

#### 常见问题
- **ADB连接失败**：检查设备USB调试模式，运行`adb devices`
- **APK安装失败**：验证APK文件完整性，检查存储空间
- **网络代理异常**：确认端口未被占用，检查证书安装

#### 日志位置
- 测试日志：`logs/`目录
- 历史记录：`history_logs/`目录
- 崩溃日志：`logs/{device}/crash/`目录
- ANR日志：`logs/{device}/anr/`目录

### 已知限制
- 网络代理功能可能需要设备root权限
- 长时间测试消耗较多设备资源
- 某些异常测试可能影响设备正常使用
- Mock服务需要应用支持HTTP接口


