#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试计划（TestPlan）领域模型。

用于在 GUI / CLI / pytest 之间传递“要跑什么测试”的结构化信息，
替代到处散落的 params 字典。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModuleSelection:
    """稳定性测试模块选择开关。"""

    monkey_stress: bool = False
    exception_recovery: bool = False
    performance_all: bool = False
    performance_response: bool = False
    performance_resource: bool = False
    broadcast_stress: bool = False
    tts_stress: bool = False

    def enabled_module_keys(self) -> List[str]:
        """返回启用的模块标识列表，保持与现有实现的字符串一致。"""
        mapping = {
            "monkey_stress": self.monkey_stress,
            "exception_recovery": self.exception_recovery,
            "performance_all": self.performance_all,
            "performance_response": self.performance_response,
            "performance_resource": self.performance_resource,
            "broadcast_stress": self.broadcast_stress,
            "tts_stress": self.tts_stress,
        }
        return [k for k, v in mapping.items() if v]


@dataclass
class StabilityTestPlan:
    """车载端侧稳定性测试计划的顶层描述。"""

    sn_list: List[str]
    duration_hours: float

    # 应用来源
    package_name: Optional[str] = None
    apk_path: str = ""
    apk_url: str = ""

    # 功能开关
    use_mock_server: bool = True
    use_network_proxy: bool = True
    network_method: str = "root"

    # 基线相关
    establish_baseline: bool = False
    compare_baseline: bool = False

    # 模块化控制
    modular_enabled: bool = False
    modules: ModuleSelection = field(default_factory=ModuleSelection)
    smoke_only: bool = False

    # 额外参数透传（便于与现有 params 字典兼容）
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def enabled_modules(self) -> List[str]:
        """与旧实现保持兼容的启用模块列表。"""
        # 如果 extra 中已有显式 enabled_modules，则优先使用
        enabled = self.extra.get("enabled_modules")
        if isinstance(enabled, list) and enabled:
            return list(enabled)
        return self.modules.enabled_module_keys()


__all__ = ["ModuleSelection", "StabilityTestPlan"]

