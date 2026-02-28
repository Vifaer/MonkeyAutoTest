#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单元测试：utils/timeout_command.py（_resolve_adb_path 等，mock 环境）"""

import os
from unittest.mock import patch

import pytest

from utils import timeout_command as timeout_module


class TestResolveAdbPath:
    """_resolve_adb_path 在不同环境下的行为"""

    def test_env_ADB_PATH_exists_returns_it(self):
        with patch.dict(os.environ, {"ADB_PATH": "/custom/adb"}, clear=False):
            with patch("os.path.exists", return_value=True):
                assert timeout_module._resolve_adb_path() == "/custom/adb"

    def test_which_adb_used_when_no_env_candidates_missing(self):
        with patch.dict(os.environ, {"ADB_PATH": ""}, clear=False):
            with patch("os.path.exists", return_value=False):
                with patch("pathlib.Path.exists", return_value=False):
                    with patch("shutil.which") as which:
                        which.return_value = "/usr/bin/adb"
                        r = timeout_module._resolve_adb_path()
                        assert r == "/usr/bin/adb"

    def test_returns_empty_when_nothing_found(self):
        with patch.dict(os.environ, {"ADB_PATH": ""}, clear=False):
            with patch("os.path.exists", return_value=False):
                with patch("pathlib.Path.exists", return_value=False):
                    with patch("shutil.which", return_value=None):
                        r = timeout_module._resolve_adb_path()
                        assert r == ""
