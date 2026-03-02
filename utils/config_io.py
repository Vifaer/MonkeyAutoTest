#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
通用配置读写工具（小而稳，避免到处散落 try/except）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def read_json(path: str | Path, default: Any = None) -> Any:
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: str | Path, data: Any, indent: int = 2) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """递归合并字典（override 优先）"""
    result: Dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_stability_config(config_path: str | Path | None = None) -> Dict[str, Any]:
    """
    统一加载稳定性测试配置。
    
    优先级：
    1. 命令行/GUI 传入的 config_path
    2. conf/test_ui_config.json
    3. conf/project.json 中的 stability_test.stability_config
    4. 内建默认值
    
    Returns:
        合并后的配置字典，包含 long_stress、performance、exception_recovery 等段
    """
    import os
    import logging
    
    # 内建默认配置
    default_config = {
        'long_stress': {
            'duration_hours': 12,
            'throttle': 700,
            'event_count': 100000
        },
        'performance': {
            'sample_interval': 30,
            'monitor_duration': 3600,
            'cold_start_threshold': 3.0,
            'response_delay_threshold': 1.5,
            'cpu_foreground_threshold': 30.0,
            'cpu_background_threshold': 1.0
        },
        'exception_recovery': {
            'network_disconnect_duration': 30,
            'weak_network_duration': 60,
            'mock_server_enabled': True,
            'network_proxy_enabled': True
        },
        'broadcast_stress': {
            'duration_hours': 12,
            'interval_seconds': 30,
            'broadcast_action': 'com.cei.llm.INPUT_HINT_TO_LLM',
            'hints': [],
            'hints_file': ''
        },
        'tts_stress': {
            'duration_hours': 12,
            'interval_seconds': 30,
            'texts': [],
            'texts_file': ''
        }
    }
    
    config = dict(default_config)
    
    # 优先级 3: 从 project.json 加载 stability_test.stability_config
    try:
        project_cfg = read_json("conf/project.json", default={})
        if isinstance(project_cfg, dict):
            stability_test = project_cfg.get("stability_test", {})
            if isinstance(stability_test, dict):
                stability_config = stability_test.get("stability_config", {})
                if isinstance(stability_config, dict):
                    config = deep_merge(config, stability_config)
    except Exception as e:
        logging.debug("从 project.json 加载配置失败: %s", e)
    
    # 优先级 2: 从 test_ui_config.json 加载
    try:
        gui_cfg_path = os.path.join("conf", "test_ui_config.json")
        gui_cfg = read_json(gui_cfg_path, default={})
        if isinstance(gui_cfg, dict):
            # 合并 mock_server，并归一化端口类型（GUI 通常以字符串形式保存）
            ms = gui_cfg.get("mock_server")
            if isinstance(ms, dict):
                if "mock_server" not in config:
                    config["mock_server"] = {}
                config["mock_server"].update(ms)
                try:
                    port_val = config["mock_server"].get("port", 8080)
                    if port_val not in (None, ""):
                        config["mock_server"]["port"] = int(port_val)
                except Exception as e:
                    logging.warning("从 test_ui_config.json 解析 mock_server.port 失败（%r），回退 8080: %s", port_val, e)
                    config["mock_server"]["port"] = 8080
            
            # 合并 monkey_mask 到 long_stress
            mm = gui_cfg.get("monkey_mask")
            if isinstance(mm, dict):
                if "long_stress" not in config:
                    config["long_stress"] = {}
                config["long_stress"]["monkey_mask"] = mm
            
            # 合并 broadcast_stress
            bs = gui_cfg.get("broadcast_stress")
            if isinstance(bs, dict):
                config["broadcast_stress"] = deep_merge(config.get("broadcast_stress", {}), bs)
            
            # 合并 tts_stress
            ts = gui_cfg.get("tts_stress")
            if isinstance(ts, dict):
                config["tts_stress"] = deep_merge(config.get("tts_stress", {}), ts)
            
            # 合并 response_monitor
            rm = gui_cfg.get("response_monitor")
            if isinstance(rm, dict):
                config["response_monitor"] = rm
    except Exception as e:
        logging.debug("从 test_ui_config.json 加载配置失败: %s", e)
    
    # 优先级 1: 命令行/GUI 传入的 config_path
    if config_path:
        try:
            override_cfg = read_json(config_path, default={})
            if isinstance(override_cfg, dict):
                config = deep_merge(config, override_cfg)
        except Exception as e:
            logging.warning("加载指定配置文件失败: %s", e)
    
    return config

