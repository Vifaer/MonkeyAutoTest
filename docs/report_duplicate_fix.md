# HTML 报告重复内容修复说明

## 问题分析

在分析 `7ff80600_broadcast_stress_test_20260212_111541.html` 报告时，发现以下重复内容：

### 1. 重复的"异常日志（Crash/ANR/ERROR）"部分
- **第一次出现**：第97-100行（实时报告区块）
- **第二次出现**：第281-285行（结果区块）
- **内容**：完全相同，都是 exceptions.log 的头部说明

### 2. 重复的"相关日志"部分
- **第一次出现**：第92-94行（实时报告区块）
- **第二次出现**：第287-290行（结果区块）
- **内容**：完全相同的日志文件链接

### 3. "详细测试结果"标题无内容
- **位置**：第139行
- **问题**：只有 `<h2>详细测试结果</h2>` 标题，没有实际内容
- **原因**：`_build_detailed_results_html` 方法只处理了 `performance` 测试，未处理 `broadcast_stress`、`tts_stress`、`monkey_stress` 等其他测试类型

## 根本原因

在 `utils/report_generator.py` 的 `_build_unified_report_html` 方法中：

1. **第884-892行**：在 `live_sections`（实时报告区块）中添加了"相关日志"和"异常日志"
2. **第904-917行**：在 `result_sections`（结果区块）中又添加了"异常日志"和"相关日志"

当报告包含快照（`has_snapshot=True`）时，两个区块都会显示，导致重复。

## 修复方案

### 修复1：消除重复的日志部分
**文件**：`utils/report_generator.py`  
**位置**：`_build_unified_report_html` 方法

**修改逻辑**：
- 当存在快照（`has_snapshot=True`）时，仅在 `result_sections` 中包含"异常日志"和"相关日志"
- 当无快照时，在 `live_sections` 中显示，保证实时报告也有日志链接

**代码变更**：
```python
# 修改前：无论是否有快照，都在 live_sections 中添加日志部分
if log_dir:
    live_sections += "相关日志" + "异常日志"

# 修改后：有快照时不在 live_sections 中添加，避免重复
if log_dir and not has_snapshot:
    live_sections += "相关日志" + "异常日志"
```

### 修复2：补充详细测试结果内容
**文件**：`utils/report_generator.py`  
**位置**：`_build_detailed_results_html` 方法

**新增内容**：
- 为 `broadcast_stress` 添加详细结果表格（发送广播数、崩溃/ANR、响应监控统计等）
- 为 `tts_stress` 添加详细结果表格（播放条数、崩溃/ANR、响应监控统计等）
- 为 `monkey_stress` 添加详细结果表格（测试时长、崩溃/ANR等）

**效果**：
- "详细测试结果"部分不再为空
- 广播压力测试的详细数据有专门的展示区域
- 报告结构更完整、逻辑更清晰

## 修复后的报告结构

修复后的报告结构（有快照时）：

1. **实时报告区块**（live_sections）
   - 测试基本信息
   - 实时测试进度与状态
   - 中间测试结果（Crash/ANR）
   - 性能监控数据
   - 测试日志摘要
   - ~~相关日志~~（已移除，避免重复）
   - ~~异常日志~~（已移除，避免重复）

2. **结果区块**（result_sections）
   - 模块异常/失败（如有）
   - 总体评估 + 各模块摘要卡片
   - **详细测试结果**（新增：包含 broadcast_stress、tts_stress、monkey_stress 的详细数据）
   - 资源消耗趋势图
   - 异常日志（仅此一处）
   - 相关日志（仅此一处）
   - 关键问题
   - 优化建议

## 验证

修复后，报告应：
- ✅ 不再有重复的"异常日志"部分
- ✅ 不再有重复的"相关日志"部分
- ✅ "详细测试结果"部分包含广播压力测试的详细数据
- ✅ 报告结构清晰，逻辑连贯
- ✅ 核心信息完整，无遗漏

## 影响范围

- **影响文件**：`utils/report_generator.py`
- **影响报告类型**：所有使用 `_build_unified_report_html` 生成的实时报告（包括 broadcast_stress、tts_stress、monkey_stress 等）
- **向后兼容**：修复不影响报告的基本功能，只是消除重复并补充缺失内容

## 使用 .bak 文件恢复被误重构的报告

在开启“按最新模板重构报告”功能后，每次成功重构都会在同一目录下生成原始 HTML 的备份文件，扩展名为 `.bak`。当某些旧报告由于 JSON 仅包含实时快照而被错误重构时，可以通过以下步骤恢复：

1. 在 `reports` 目录中找到对应的备份文件，例如：  
   - 原始报告：`7ff80600_broadcast_stress_test_20260224_104225.html`  
   - 备份文件：`7ff80600_broadcast_stress_test_20260224_104225.html.bak`
2. 关闭正在查看该报告的浏览器或 GUI 预览窗口，避免文件被占用。
3. 为当前（已重构）的 HTML 做一次临时备份（可选）：  
   - 将 `*.html` 复制为 `*.html.backup_before_restore`。
4. 将 `.bak` 文件重命名为原始文件名覆盖当前 HTML：  
   - 把 `*.html.bak` 重命名为 `*.html`。
5. 重新在浏览器或 GUI 报告查看器中打开该报告，确认内容已经恢复到重构前的版本。

注意：新版 `utils.report_regenerator.regenerate_report` 已经增加对“仅含实时快照 JSON”旧报告的识别，此类报告会被安全拒绝重构并保留原 HTML 不变，因此上述恢复流程通常只在早期误重构的个别旧报告上需要执行一次。
