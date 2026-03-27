#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
应用私有目录日志拉取（adb pull）

目标：
- 依据配置文件，为不同包名选择不同的远端日志目录
- 在测试结束后自动拉取到本机 run_log_dir 下，便于报告/排查
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
import json
from typing import Any, Dict, List, Optional, Tuple

from infra.adb import run as adb_run
from utils.config_io import read_json


DEFAULT_RULES_PATH = "conf/app_log_pull_rules.json"


def _resolve_rules_path(config: Optional[Dict[str, Any]] = None) -> str:
    if isinstance(config, dict):
        p = config.get("app_log_pull_rules_path")
        if isinstance(p, str) and p.strip():
            return p.strip()
    return DEFAULT_RULES_PATH


def _load_rules(rules_path: str) -> Dict[str, Any]:
    data = read_json(rules_path, default={})
    if not isinstance(data, dict):
        return {}
    return data


def _format_template(value: str, package_name: str) -> str:
    # 当前只需要 {package} 占位符
    return value.replace("{package}", package_name)


def _find_first_file_under_dir(base_dir: str) -> Optional[str]:
    """
    找到 base_dir 下的任意一个文件（用于报告链接）。
    返回相对 base_dir 的路径（如 "NaviLogs/a.txt"），找不到返回 None。
    """
    if not base_dir or not os.path.isdir(base_dir):
        return None
    for root, _dirs, files in os.walk(base_dir):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            if os.path.isfile(full):
                rel = os.path.relpath(full, base_dir)
                return rel
    return None


def pull_app_private_logs(
    *,
    device_sn: str,
    package_name: str,
    run_log_dir: str,
    config: Optional[Dict[str, Any]] = None,
    reason: str = "",
) -> List[Dict[str, Any]]:
    """
    拉取应用私有目录日志到本机。

    返回：
    - 每个 pull 项的结果列表（用于写 manifest / debug）
    """
    sn = (device_sn or "").strip()
    pkg = (package_name or "").strip()
    if not sn or not pkg or not run_log_dir:
        return []

    rules_path = _resolve_rules_path(config)
    rules = _load_rules(rules_path)

    local_base_subdir = "app_private_logs"
    if isinstance(rules.get("local_base_subdir"), str) and rules["local_base_subdir"].strip():
        local_base_subdir = rules["local_base_subdir"].strip()
    if isinstance(config, dict) and isinstance(config.get("app_log_pull_local_base_subdir"), str):
        v = config["app_log_pull_local_base_subdir"].strip()
        if v:
            local_base_subdir = v

    adb_timeout_seconds = int(rules.get("adb_timeout_seconds", 120))
    if isinstance(config, dict) and config.get("app_log_pull_adb_timeout_seconds") is not None:
        try:
            adb_timeout_seconds = int(float(config["app_log_pull_adb_timeout_seconds"]))
        except Exception:
            pass

    packages = rules.get("packages") if isinstance(rules.get("packages"), dict) else {}
    pull_items = packages.get(pkg) or packages.get("_default") or []

    # 兼容：允许包名下是 {"pull_items": [...]}
    if isinstance(pull_items, dict):
        pull_items = pull_items.get("pull_items", [])
    if not isinstance(pull_items, list):
        pull_items = []

    if not pull_items:
        logging.info("[app-log-pull] 没有找到包名 [%s] 的拉取规则（%s），跳过", pkg, rules_path)
        return []

    local_root = os.path.join(run_log_dir, local_base_subdir)
    os.makedirs(local_root, exist_ok=True)

    manifest: List[Dict[str, Any]] = []

    for idx, item in enumerate(pull_items):
        if not isinstance(item, dict):
            continue
        remote_dir_t = (item.get("remote_dir") or item.get("remote_path") or "").strip()
        if not remote_dir_t:
            continue
        remote_dir = _format_template(remote_dir_t, pkg)

        local_subdir = (item.get("local_subdir") or "").strip()
        if not local_subdir:
            # 使用远端目录最后一段作为本地子目录名
            local_subdir = os.path.basename(remote_dir.rstrip("/")) or f"pull_{idx}"

        local_dir = os.path.join(local_root, local_subdir)
        os.makedirs(local_dir, exist_ok=True)

        logging.info(
            "[app-log-pull] 拉取应用私有日志: sn=%s pkg=%s remote=%s -> local=%s (reason=%s)",
            sn,
            pkg,
            remote_dir,
            local_dir,
            reason or "test_end",
        )

        pull_out = None
        try:
            pull_out = adb_run("pull", remote_dir, local_dir, serial=sn, timeout=adb_timeout_seconds)
        except Exception as e:
            logging.warning("[app-log-pull] adb pull 异常: %s (remote=%s)", e, remote_dir)

        # 以本地是否存在内容作为成功判断
        local_has_files = False
        try:
            local_has_files = bool(os.listdir(local_dir))
        except Exception:
            local_has_files = False

        manifest.append(
            {
                "remote_dir": remote_dir,
                "local_dir": local_dir,
                "adb_output": pull_out if isinstance(pull_out, str) else None,
                "local_has_files": local_has_files,
            }
        )

    # 写 manifest 便于追踪
    try:
        manifest_path = os.path.join(local_root, "app_log_pull_manifest.json")
        Path(manifest_path).write_text(
            json.dumps(
                {"package": pkg, "device_sn": sn, "reason": reason or "", "items": manifest},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass

    return manifest


def _resolve_pull_items(rules: Dict[str, Any], pkg: str) -> List[Dict[str, Any]]:
    packages = rules.get("packages") if isinstance(rules.get("packages"), dict) else {}
    pull_items = packages.get(pkg) or packages.get("_default") or []
    if isinstance(pull_items, dict):
        pull_items = pull_items.get("pull_items", [])
    if not isinstance(pull_items, list):
        pull_items = []
    return [x for x in pull_items if isinstance(x, dict)]


def _list_remote_dir_entries_with_sizes(
    *,
    device_sn: str,
    remote_dir: str,
    timeout_seconds: int = 10,
) -> Dict[str, int]:
    """
    使用 `adb shell ls -l` 获取远端目录下“文件”的 size。

    返回：{ filename: size_bytes }
    说明：Android/BusyBox/toybox 的 `ls -l` 输出格式可能略有差异，这里做尽量宽松解析。
    """
    sizes: Dict[str, int] = {}
    try:
        # ls -l: perms links owner group size date time name
        # name 若是软链，perms 以 l 开头 -> 跳过
        out = adb_run("shell", f'ls -l "{remote_dir}"', serial=device_sn, timeout=timeout_seconds)
        if not isinstance(out, str):
            return {}
        for line in out.splitlines():
            s = line.strip()
            if not s or s.startswith("total"):
                continue
            parts = s.split()
            if len(parts) < 6:
                continue
            perms = parts[0]
            if not perms or perms[0] != "-" :
                continue
            # size 通常为第 5 个 token（0:perms 1:links 2:owner 3:group 4:size ...）
            size_token = parts[4] if len(parts) > 4 else ""
            name = parts[-1]
            try:
                size = int(size_token)
            except Exception:
                continue
            if name:
                sizes[name] = size
    except Exception:
        return {}
    return sizes


def run_app_private_logs_incremental_pulling(
    *,
    stop_event: Any,
    device_sn: str,
    package_name: str,
    run_log_dir: str,
    config: Optional[Dict[str, Any]] = None,
    reason: str = "",
) -> None:
    """
    实时/准实时拉取应用私有日志（增量）。

    判定逻辑（尽量稳定）：
    - 目录下文件名新增：拉取
    - 目录下文件 size 发生变化：拉取（适配“同一文件持续追加”的场景）
    """
    sn = (device_sn or "").strip()
    pkg = (package_name or "").strip()
    if not sn or not pkg or not run_log_dir:
        return

    rules_path = _resolve_rules_path(config)
    rules = _load_rules(rules_path)

    inc_cfg = rules.get("incremental") if isinstance(rules.get("incremental"), dict) else {}
    enabled = bool(inc_cfg.get("enabled", True))
    if not enabled:
        return

    interval_seconds = inc_cfg.get("interval_seconds", 20)
    try:
        interval_seconds = max(1.0, float(interval_seconds))
    except Exception:
        interval_seconds = 20.0

    max_files_per_dir = inc_cfg.get("max_files_per_dir", 500)
    try:
        max_files_per_dir = int(max_files_per_dir)
    except Exception:
        max_files_per_dir = 500

    local_base_subdir = "app_private_logs"
    if isinstance(rules.get("local_base_subdir"), str) and rules["local_base_subdir"].strip():
        local_base_subdir = rules["local_base_subdir"].strip()
    if isinstance(config, dict) and isinstance(config.get("app_log_pull_local_base_subdir"), str):
        v = config["app_log_pull_local_base_subdir"].strip()
        if v:
            local_base_subdir = v

    adb_timeout_seconds = int(rules.get("adb_timeout_seconds", 120))
    if isinstance(config, dict) and config.get("app_log_pull_adb_timeout_seconds") is not None:
        try:
            adb_timeout_seconds = int(float(config["app_log_pull_adb_timeout_seconds"]))
        except Exception:
            pass

    pull_items = _resolve_pull_items(rules, pkg)
    if not pull_items:
        return

    local_root = os.path.join(run_log_dir, local_base_subdir)
    os.makedirs(local_root, exist_ok=True)

    # state：为每个 item(remote_dir/local_dir) 维护 filename->size
    # key 采用 remote_dir + local_subdir 的组合
    state: Dict[str, Dict[str, int]] = {}

    pull_records: List[Dict[str, Any]] = []

    def _state_key(remote_dir: str, local_subdir: str) -> str:
        return f"{remote_dir}||{local_subdir}"

    while True:
        if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
            break

        for idx, item in enumerate(pull_items):
            remote_dir_t = (item.get("remote_dir") or item.get("remote_path") or "").strip()
            if not remote_dir_t:
                continue
            remote_dir = _format_template(remote_dir_t, pkg)

            local_subdir = (item.get("local_subdir") or "").strip()
            if not local_subdir:
                local_subdir = os.path.basename(remote_dir.rstrip("/")) or f"pull_{idx}"

            local_dir = os.path.join(local_root, local_subdir)
            os.makedirs(local_dir, exist_ok=True)

            sk = _state_key(remote_dir, local_subdir)
            state_for_item = state.setdefault(sk, {})

            sizes = _list_remote_dir_entries_with_sizes(
                device_sn=sn,
                remote_dir=remote_dir,
                timeout_seconds=min(10, int(interval_seconds * 0.8)) if interval_seconds > 2 else 10,
            )
            if not sizes:
                continue

            for filename, size in sizes.items():
                prev_size = state_for_item.get(filename)
                # 新文件或 size 变化：拉取
                if prev_size is None or prev_size != size:
                    remote_path = f"{remote_dir.rstrip('/')}/{filename}"
                    local_path = os.path.join(local_dir, filename)
                    try:
                        adb_run("pull", remote_path, local_path, serial=sn, timeout=adb_timeout_seconds)
                    except Exception:
                        # 不中断增量循环
                        pass
                    state_for_item[filename] = size
                    pull_records.append(
                        {
                            "ts": __import__("datetime").datetime.now().isoformat(),
                            "remote_dir": remote_dir,
                            "filename": filename,
                            "size": size,
                            "local_dir": local_dir,
                        }
                    )

            # 控制状态大小，避免长测 state 无界
            if len(state_for_item) > max_files_per_dir:
                # 通过 key 排序丢弃最老/最小（这里无法可靠获取远端时间，采用简单按文件名丢弃）
                for k in sorted(state_for_item.keys())[: max(0, len(state_for_item) - max_files_per_dir)]:
                    state_for_item.pop(k, None)

        # 省电：先等一小段再重试；避免 adb 调用间隔过密
        try:
            if stop_event is not None and getattr(stop_event, "wait", None):
                stop_event.wait(interval_seconds)
            else:
                import time as _time

                _time.sleep(interval_seconds)
        except Exception:
            import time as _time

            _time.sleep(interval_seconds)

    # 结束前补写一份简要记录
    try:
        manifest_path = os.path.join(local_root, "app_log_pull_incremental_manifest.json")
        Path(manifest_path).write_text(
            json.dumps(
                {"package": pkg, "device_sn": sn, "reason": reason or "", "items": pull_records[-2000:]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def build_app_private_log_links(run_log_dir: str) -> List[Dict[str, str]]:
    """
    为报告侧返回链接信息（可选使用）。
    """
    # 返回结构保持简单：[{ "href": ..., "anchor": ... }]
    if not run_log_dir:
        return []
    local_root = os.path.join(run_log_dir, "app_private_logs")
    rel_file = _find_first_file_under_dir(local_root)
    if not rel_file:
        return []
    file_full = os.path.join(local_root, rel_file)
    if not os.path.isfile(file_full):
        return []
    return [{"file": file_full, "rel_file": rel_file}]


__all__ = ["pull_app_private_logs", "run_app_private_logs_incremental_pulling"]

