"""Tests for yaml_module — YAML parsing and generation predicates.

Tests the Read, write, ReadAll, WriteAll, ReadFile, WriteFile, and Get
predicates, both as inline .clausal tests and direct Python-level calls.
"""

from __future__ import annotations

import pytest

from clausal.logic.solve import call, query
from clausal.logic.variables import Var, deref, Trail
from clausal.import_hook import _load_module


# ── Helpers ──────────────────────────────────────────────────────────────────

_YAML_IMPORT = '-import_from(py.yaml, [Read, write, ReadAll, WriteAll, ReadFile, WriteFile, Get])\n'


def _load(name, src_text, tmp_path):
    """write a .clausal file and load it."""
    p = tmp_path / f"{name}.clausal"
    p.write_text(_YAML_IMPORT + src_text)
    mod = _load_module(name, str(p))
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


def _first(functor, *args, module, out_index=-1):
    """Call with a Var at out_index, return first deref'd result."""
    v = Var()
    full = list(args)
    if out_index == -1:
        full.append(v)
    else:
        full.insert(out_index, v)
    for _ in call(functor, *full, module=module):
        return deref(v)
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Read/2 — parse YAML string to Python object
# ══════════════════════════════════════════════════════════════════════════════


class TestRead:

    def test_parse_scalar_int(self, tmp_path):
        mod = _load("yr1", """
read_int(S, N) <- Read(S, N)
""", tmp_path)
        assert _first("read_int", "42", module=mod) == 42

    def test_parse_scalar_float(self, tmp_path):
        mod = _load("yr2", """
read_float(S, N) <- Read(S, N)
""", tmp_path)
        assert _first("read_float", "3.14", module=mod) == 3.14

    def test_parse_scalar_string(self, tmp_path):
        mod = _load("yr3", """
read_str(S, R) <- Read(S, R)
""", tmp_path)
        assert _first("read_str", "hello world", module=mod) == "hello world"

    def test_parse_mapping(self, tmp_path):
        mod = _load("yr4", """
read_map(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_map", "name: alice\nage: 30", module=mod)
        assert result == {"name": "alice", "age": 30}

    def test_parse_sequence(self, tmp_path):
        mod = _load("yr5", """
read_seq(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_seq", "[1, 2, 3]", module=mod)
        assert result == [1, 2, 3]

    def test_parse_nested_mapping(self, tmp_path):
        mod = _load("yr6", """
read_nested(S, R) <- Read(S, R)
""", tmp_path)
        yaml_str = "server:\n  host: localhost\n  port: 8080"
        result = _first("read_nested", yaml_str, module=mod)
        assert result == {"server": {"host": "localhost", "port": 8080}}

    def test_parse_bool_true(self, tmp_path):
        mod = _load("yr7", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_val", "true", module=mod)
        assert result is True

    def test_parse_bool_false(self, tmp_path):
        mod = _load("yr8", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_val", "false", module=mod)
        assert result is False

    def test_parse_null(self, tmp_path):
        mod = _load("yr9", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_val", "null", module=mod)
        assert result is None

    def test_parse_empty_doc(self, tmp_path):
        mod = _load("yr10", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_val", "", module=mod)
        assert result is None

    def test_parse_flow_style_mapping(self, tmp_path):
        mod = _load("yr11", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        result = _first("read_val", "{a: 1, b: 2}", module=mod)
        assert result == {"a": 1, "b": 2}

    def test_parse_multiline_literal_block(self, tmp_path):
        mod = _load("yr12", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        yaml_str = "text: |\n  line one\n  line two\n"
        result = _first("read_val", yaml_str, module=mod)
        assert result == {"text": "line one\nline two\n"}

    def test_parse_list_of_mappings(self, tmp_path):
        mod = _load("yr13", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        yaml_str = "- name: alice\n  age: 30\n- name: bob\n  age: 25"
        result = _first("read_val", yaml_str, module=mod)
        assert result == [
            {"name": "alice", "age": 30},
            {"name": "bob", "age": 25},
        ]

    def test_invalid_yaml_fails(self, tmp_path):
        mod = _load("yr14", """
read_val(S, R) <- Read(S, R)
""", tmp_path)
        # Unbalanced braces — invalid YAML
        result = _first("read_val", "{a: [}", module=mod)
        assert result is None  # fails — no solution


# ══════════════════════════════════════════════════════════════════════════════
# write/2 — serialize Python object to YAML string
# ══════════════════════════════════════════════════════════════════════════════


class TestWrite:

    def test_write_mapping(self, tmp_path):
        mod = _load("yw1", """
write_val(D, S) <- write(D, S)
""", tmp_path)
        result = _first("write_val", {"x": 1}, module=mod)
        assert "x: 1" in result

    def test_write_list(self, tmp_path):
        mod = _load("yw2", """
write_val(D, S) <- write(D, S)
""", tmp_path)
        result = _first("write_val", [1, 2, 3], module=mod)
        assert "- 1" in result
        assert "- 2" in result
        assert "- 3" in result

    def test_write_scalar(self, tmp_path):
        mod = _load("yw3", """
write_val(D, S) <- write(D, S)
""", tmp_path)
        result = _first("write_val", 42, module=mod)
        assert result.strip() == "42"

    def test_write_nested(self, tmp_path):
        mod = _load("yw4", """
write_val(D, S) <- write(D, S)
""", tmp_path)
        data = {"server": {"host": "localhost", "port": 8080}}
        result = _first("write_val", data, module=mod)
        assert "server:" in result
        assert "host: localhost" in result

    def test_write_bool_null(self, tmp_path):
        mod = _load("yw5", """
write_val(D, S) <- write(D, S)
""", tmp_path)
        result = _first("write_val", {"flag": True, "val": None}, module=mod)
        assert "flag: true" in result
        assert "val: null" in result

    def test_round_trip(self, tmp_path):
        mod = _load("yw6", """
round_trip(S, R) <- (Read(S, D) and write(D, R))
""", tmp_path)
        yaml_in = "a: 1\nb: 2"
        result = _first("round_trip", yaml_in, module=mod)
        # Parse the result again to verify equivalence
        import yaml
        assert yaml.safe_load(result) == yaml.safe_load(yaml_in)


# ══════════════════════════════════════════════════════════════════════════════
# ReadAll/2 — multi-document YAML
# ══════════════════════════════════════════════════════════════════════════════


class TestReadAll:

    def test_multi_doc(self, tmp_path):
        mod = _load("yra1", """
read_all(S, R) <- ReadAll(S, R)
""", tmp_path)
        yaml_str = "a: 1\n---\nb: 2"
        result = _first("read_all", yaml_str, module=mod)
        assert result == [{"a": 1}, {"b": 2}]

    def test_single_doc(self, tmp_path):
        mod = _load("yra2", """
read_all(S, R) <- ReadAll(S, R)
""", tmp_path)
        result = _first("read_all", "x: 1", module=mod)
        assert result == [{"x": 1}]

    def test_empty_stream(self, tmp_path):
        mod = _load("yra3", """
read_all(S, R) <- ReadAll(S, R)
""", tmp_path)
        result = _first("read_all", "", module=mod)
        assert result == []


# ══════════════════════════════════════════════════════════════════════════════
# WriteAll/2 — multi-document serialization
# ══════════════════════════════════════════════════════════════════════════════


class TestWriteAll:

    def test_multi_doc_write(self, tmp_path):
        mod = _load("ywa1", """
write_all(D, S) <- WriteAll(D, S)
""", tmp_path)
        docs = [{"a": 1}, {"b": 2}]
        result = _first("write_all", docs, module=mod)
        assert "---" in result
        assert "a: 1" in result
        assert "b: 2" in result

    def test_round_trip_multi_doc(self, tmp_path):
        mod = _load("ywa2", """
round_trip_all(S, R) <- (ReadAll(S, D) and WriteAll(D, R))
""", tmp_path)
        yaml_in = "x: 1\n---\ny: 2"
        result = _first("round_trip_all", yaml_in, module=mod)
        import yaml
        assert list(yaml.safe_load_all(result)) == [{"x": 1}, {"y": 2}]


# ══════════════════════════════════════════════════════════════════════════════
# ReadFile/2, WriteFile/2 — file I/O
# ══════════════════════════════════════════════════════════════════════════════


class TestFileIO:

    def test_read_file(self, tmp_path):
        yaml_file = tmp_path / "test.yaml"
        yaml_file.write_text("name: alice\nage: 30\n")
        mod = _load("yrf1", """
read_file(P, R) <- ReadFile(P, R)
""", tmp_path)
        result = _first("read_file", str(yaml_file), module=mod)
        assert result == {"name": "alice", "age": 30}

    def test_read_nonexistent_file_fails(self, tmp_path):
        mod = _load("yrf2", """
read_file(P, R) <- ReadFile(P, R)
""", tmp_path)
        result = _first("read_file", str(tmp_path / "nope.yaml"), module=mod)
        assert result is None  # fails

    def test_write_and_read_back(self, tmp_path):
        """write data to file via Python, then read back via ReadFile."""
        yaml_file = tmp_path / "output.yaml"
        mod = _load("ywf1", """
read_back(P, V) <- (ReadFile(P, D) and Get(D, "greeting", V))
""", tmp_path)
        # write via Python first
        import yaml
        with open(yaml_file, "w") as f:
            yaml.safe_dump({"greeting": "hello", "count": 3}, f)
        assert _first("read_back", str(yaml_file), module=mod) == "hello"

    def test_write_file(self, tmp_path):
        """write data to file via WriteFile, read back via Python."""
        yaml_file = tmp_path / "written.yaml"
        mod = _load("ywf2", """
do_write(P, D) <- WriteFile(P, D)
""", tmp_path)
        data = {"color": "blue", "count": 7}
        assert _succeeds("do_write", str(yaml_file), data, module=mod)
        import yaml
        with open(yaml_file) as f:
            result = yaml.safe_load(f)
        assert result == data


# ══════════════════════════════════════════════════════════════════════════════
# Get/3 — nested structure navigation
# ══════════════════════════════════════════════════════════════════════════════


class TestGet:

    def test_single_key(self, tmp_path):
        mod = _load("yg1", """
get_val(S, K, V) <- (Read(S, D) and Get(D, K, V))
""", tmp_path)
        assert _first("get_val", "name: alice", "name", module=mod) == "alice"

    def test_nested_keys(self, tmp_path):
        mod = _load("yg2", """
get_nested(S, V) <- (Read(S, D) and Get(D, ["server", "port"], V))
""", tmp_path)
        yaml_str = "server:\n  host: localhost\n  port: 8080"
        assert _first("get_nested", yaml_str, module=mod) == 8080

    def test_list_index(self, tmp_path):
        mod = _load("yg3", """
get_idx(S, V) <- (Read(S, D) and Get(D, [0], V))
""", tmp_path)
        assert _first("get_idx", "[10, 20, 30]", module=mod) == 10

    def test_mixed_keys_and_indices(self, tmp_path):
        mod = _load("yg4", """
get_mixed(S, V) <- (Read(S, D) and Get(D, ["items", 1, "name"], V))
""", tmp_path)
        yaml_str = "items:\n  - name: first\n  - name: second"
        assert _first("get_mixed", yaml_str, module=mod) == "second"

    def test_missing_key_fails(self, tmp_path):
        mod = _load("yg5", """
get_val(S, K, V) <- (Read(S, D) and Get(D, K, V))
""", tmp_path)
        assert _first("get_val", "x: 1", "missing", module=mod) is None

    def test_index_out_of_range_fails(self, tmp_path):
        mod = _load("yg6", """
get_val(S, V) <- (Read(S, D) and Get(D, [99], V))
""", tmp_path)
        assert _first("get_val", "[1, 2]", module=mod) is None


# ══════════════════════════════════════════════════════════════════════════════
# .clausal fixture integration tests
# ══════════════════════════════════════════════════════════════════════════════


class TestFixture:
    """Load the yaml_basic.clausal fixture and run its Test predicates."""

    @pytest.fixture(autouse=True)
    def _load_fixture(self):
        import os
        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "yaml_basic.clausal"
        )
        mod = _load_module("yaml_basic", fixture)
        self.module = mod.__dict__["$module"]

    def _run_test(self, name):
        assert _succeeds("Test", name, module=self.module), \
            f"Test({name!r}) failed — no solutions"

    def test_parse_scalar_int(self):
        self._run_test("parse scalar int")

    def test_parse_scalar_string(self):
        self._run_test("parse scalar string")

    def test_parse_mapping(self):
        self._run_test("parse mapping")

    def test_parse_sequence(self):
        self._run_test("parse sequence")

    def test_parse_bool_and_null(self):
        self._run_test("parse bool and null")

    def test_parse_nested_mapping(self):
        self._run_test("parse nested mapping")

    def test_list_of_maps(self):
        self._run_test("list of maps")

    def test_config_pattern(self):
        self._run_test("config pattern")

    def test_round_trip_mapping(self):
        self._run_test("round trip mapping")

    def test_write_and_read_back(self):
        self._run_test("write and read back")
