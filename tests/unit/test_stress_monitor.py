#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单元测试：utils/stress_monitor.py（纯逻辑：解析、包名等，不依赖真机）"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from utils.stress_monitor import StressMonitor


class TestStressMonitorGetPackageName:
    """_get_package_name 行为"""

    def test_package_with_name(self):
        device = MagicMock(sn="abc")
        package = MagicMock()
        package.name = "com.app.test"
        package.package = None
        mon = StressMonitor(device, package, {})
        assert mon._get_package_name() == "com.app.test"

    def test_package_with_package_attr(self):
        device = MagicMock(sn="abc")
        package = MagicMock(spec=[])
        package.name = None
        package.package = "com.other"
        mon = StressMonitor(device, package, {})
        assert mon._get_package_name() == "com.other"

    def test_empty_when_both_missing(self):
        device = MagicMock(sn="abc")
        package = MagicMock()
        del package.name
        del package.package
        package.name = None
        package.package = None
        mon = StressMonitor(device, package, {})
        assert mon._get_package_name() == ""


class TestParseTopOutputForCpu:
    """_parse_top_output_for_cpu 从 top 输出解析应用/设备 CPU"""

    def test_empty_output(self):
        device = MagicMock(sn="x")
        package = MagicMock(name="com.pkg")
        mon = StressMonitor(device, package, {})
        app, dev = mon._parse_top_output_for_cpu("", "com.pkg")
        assert app == 0.0
        assert dev == 0.0

    def test_user_kernel_line(self):
        device = MagicMock(sn="x")
        package = MagicMock(name="com.pkg")
        mon = StressMonitor(device, package, {})
        out = "User 15%, Kernel 5%, IOW 0%"
        app, dev = mon._parse_top_output_for_cpu(out, "com.pkg")
        assert dev == 20.0
        assert app == 0.0

    def test_process_line_with_percent(self):
        device = MagicMock(sn="x")
        package = MagicMock(name="com.pkg")
        mon = StressMonitor(device, package, {})
        out = "User 10%, Kernel 2%\n1234  com.pkg  5%  100m"
        app, dev = mon._parse_top_output_for_cpu(out, "com.pkg")
        assert app == 5.0
        assert dev == 12.0


class TestParseLogcatTimestamp:
    """_parse_logcat_timestamp 兼容 time/threadtime 格式"""

    def test_threadtime_mm_dd(self):
        device = MagicMock(sn="x")
        package = MagicMock(name="p")
        mon = StressMonitor(device, package, {})
        line = "01-15 10:30:45.123  1234  5678  D  Tag: msg"
        dt = mon._parse_logcat_timestamp(line)
        assert dt is not None
        assert dt.month == 1
        assert dt.day == 15
        assert dt.hour == 10
        assert dt.minute == 30
        assert dt.second == 45

    def test_iso_yyyy_mm_dd(self):
        device = MagicMock(sn="x")
        package = MagicMock(name="p")
        mon = StressMonitor(device, package, {})
        line = "2025-01-15 10:30:45.000  1234  D  Tag: msg"
        dt = mon._parse_logcat_timestamp(line)
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 1
        assert dt.day == 15

    def test_too_short_returns_none(self):
        device = MagicMock(sn="x")
        package = MagicMock(name="p")
        mon = StressMonitor(device, package, {})
        assert mon._parse_logcat_timestamp("") is None
        assert mon._parse_logcat_timestamp("01-15 10:30") is None
