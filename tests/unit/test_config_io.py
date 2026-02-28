#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单元测试：utils/config_io.py"""

import os
import tempfile
from pathlib import Path

import pytest

from utils.config_io import read_json, write_json, deep_merge


class TestReadJson:
    """read_json 行为测试"""

    def test_missing_file_returns_default(self):
        assert read_json("/nonexistent/path.json") is None
        assert read_json("/nonexistent/path.json", default={}) == {}
        assert read_json("/nonexistent/path.json", default=[]) == []

    def test_valid_json_returns_parsed(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"a": 1}')
            path = f.name
        try:
            assert read_json(path) == {"a": 1}
            assert read_json(Path(path)) == {"a": 1}
        finally:
            os.unlink(path)

    def test_invalid_json_returns_default(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not json")
            path = f.name
        try:
            assert read_json(path, default=None) is None
            assert read_json(path, default={}) == {}
        finally:
            os.unlink(path)


class TestWriteJson:
    """write_json 行为测试"""

    def test_writes_and_read_back(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.json")
            write_json(path, {"x": 1})
            assert read_json(path) == {"x": 1}

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sub", "out.json")
            write_json(path, {"a": 1})
            assert read_json(path) == {"a": 1}


class TestDeepMerge:
    """deep_merge 行为测试"""

    def test_shallow_override(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        assert deep_merge(base, override) == {"a": 1, "b": 3}

    def test_nested_merge(self):
        base = {"a": {"x": 1}, "b": 2}
        override = {"a": {"y": 2}}
        assert deep_merge(base, override) == {"a": {"x": 1, "y": 2}, "b": 2}

    def test_non_dict_override_replaces(self):
        base = {"a": {"x": 1}}
        override = {"a": 99}
        assert deep_merge(base, override) == {"a": 99}

    def test_empty_base(self):
        assert deep_merge({}, {"a": 1}) == {"a": 1}

    def test_empty_override(self):
        base = {"a": 1}
        assert deep_merge(base, {}) == {"a": 1}
