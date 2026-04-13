"""Tests for clausal.modules.py.json — JSON predicates."""

from __future__ import annotations

import os

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.json import (
    Parse, Generate, PrettyGenerate, Get, ReadFile, WriteFile,
    _parse_2, _generate_2, _pretty_generate_2,
    _get_3, _read_file_2, _write_file_2,
    _python_to_clausal, _clausal_to_python,
)
from clausal.terms import DictTerm
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── Converter unit tests ────────────────────────────────────────────────


class TestConverters:
    def test_python_to_clausal_dict(self):
        # nv
        result = _python_to_clausal({"a": 1, "b": 2})
        assert isinstance(result, DictTerm)
        assert result.data == {"a": 1, "b": 2}

    def test_python_to_clausal_nested(self):
        # nv
        result = _python_to_clausal({"a": {"b": 1}})
        assert isinstance(result, DictTerm)
        inner = result.data["a"]
        assert isinstance(inner, DictTerm)
        assert inner.data == {"b": 1}

    def test_python_to_clausal_list(self):
        # nv
        result = _python_to_clausal([1, {"a": 2}])
        assert isinstance(result, list)
        assert result[0] == 1
        assert isinstance(result[1], DictTerm)

    def test_python_to_clausal_scalars(self):
        # nv
        assert _python_to_clausal("hello") == "hello"
        assert _python_to_clausal(42) == 42
        assert _python_to_clausal(3.14) == 3.14
        assert _python_to_clausal(True) is True
        assert _python_to_clausal(None) is None

    def test_clausal_to_python_dict_term(self):
        # nv
        dt = DictTerm({"x": 1, "y": 2})
        result = _clausal_to_python(dt)
        assert result == {"x": 1, "y": 2}

    def test_clausal_to_python_nested(self):
        # nv
        dt = DictTerm({"a": DictTerm({"b": 1})})
        result = _clausal_to_python(dt)
        assert result == {"a": {"b": 1}}

    def test_clausal_to_python_list(self):
        # nv
        result = _clausal_to_python([1, DictTerm({"a": 2})])
        assert result == [1, {"a": 2}]

    def test_clausal_to_python_unbound_var_raises(self):
        # nv
        with pytest.raises(TypeError, match="unbound variable"):
            _clausal_to_python(Var())


# ── Parse/2 ─────────────────────────────────────────────────────────────


class TestParse:
    def test_simple_object(self):
        # nv
        t = Var()
        sols, trail = simple_solutions(_parse_2, '{"a": 1, "b": 2}', t)
        assert len(sols) == 1
        result = deref(t)
        assert isinstance(result, DictTerm)
        assert result.data["a"] == 1
        assert result.data["b"] == 2

    def test_nested_object(self):
        # nv
        t = Var()
        sols, trail = simple_solutions(_parse_2, '{"a": {"b": 3}}', t)
        assert len(sols) == 1
        result = deref(t)
        inner = result.data["a"]
        assert isinstance(inner, DictTerm)
        assert inner.data["b"] == 3

    def test_array(self):
        # nv
        t = Var()
        sols, trail = simple_solutions(_parse_2, '[1, 2, 3]', t)
        assert len(sols) == 1
        assert deref(t) == [1, 2, 3]

    def test_string_scalar(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, '"hello"', t)
        assert len(sols) == 1
        assert deref(t) == "hello"

    def test_number_int(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, '42', t)
        assert len(sols) == 1
        assert deref(t) == 42

    def test_number_float(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, '3.14', t)
        assert len(sols) == 1
        assert deref(t) == 3.14

    def test_bool(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, 'true', t)
        assert len(sols) == 1
        assert deref(t) is True

    def test_null(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, 'null', t)
        assert len(sols) == 1
        assert deref(t) is None

    def test_empty_object(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, '{}', t)
        assert len(sols) == 1
        result = deref(t)
        assert isinstance(result, DictTerm)
        assert result.data == {}

    def test_empty_array(self):
        # nv
        t = Var()
        sols, _ = simple_solutions(_parse_2, '[]', t)
        assert len(sols) == 1
        assert deref(t) == []

    def test_unbound_string_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_2, Var(), Var())
        assert len(sols) == 0

    def test_invalid_json_fails(self):
        # nv
        sols, _ = simple_solutions(_parse_2, '{bad json}', Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        t = Var()
        sols, trail = trampoline_solutions(Parse, '{"x": 1}', t)
        assert len(sols) == 1
        assert isinstance(deref(t), DictTerm)


# ── Generate/2 ──────────────────────────────────────────────────────────


class TestGenerate:
    def test_dict_term(self):
        # nv
        s = Var()
        dt = DictTerm({"a": 1})
        sols, trail = simple_solutions(_generate_2, dt, s)
        assert len(sols) == 1
        import json
        assert json.loads(deref(s)) == {"a": 1}

    def test_nested(self):
        # nv
        s = Var()
        dt = DictTerm({"a": DictTerm({"b": 2})})
        sols, trail = simple_solutions(_generate_2, dt, s)
        assert len(sols) == 1
        import json
        assert json.loads(deref(s)) == {"a": {"b": 2}}

    def test_list(self):
        # nv
        s = Var()
        sols, trail = simple_solutions(_generate_2, [1, 2, 3], s)
        assert len(sols) == 1
        assert deref(s) == "[1, 2, 3]"

    def test_scalars(self):
        # nv
        s = Var()
        sols, _ = simple_solutions(_generate_2, "hello", s)
        assert len(sols) == 1
        assert deref(s) == '"hello"'

    def test_unbound_var_fails(self):
        """Unbound term fails (can't serialize)."""
        # nv
        sols, _ = simple_solutions(_generate_2, Var(), Var())
        assert len(sols) == 0

    def test_round_trip(self):
        """Parse then generate yields equivalent JSON."""
        # nv
        import json
        original = '{"name": "alice", "scores": [1, 2, 3]}'
        t = Var()
        simple_solutions(_parse_2, original, t)
        s = Var()
        simple_solutions(_generate_2, deref(t), s)
        assert json.loads(deref(s)) == json.loads(original)


# ── PrettyGenerate/2 ───────────────────────────────────────────────────


class TestPrettyGenerate:
    def test_indented(self):
        # nv
        s = Var()
        dt = DictTerm({"a": 1})
        sols, trail = simple_solutions(_pretty_generate_2, dt, s)
        assert len(sols) == 1
        result = deref(s)
        assert "\n" in result
        assert "  " in result


# ── Get/3 ──────────────────────────────────────────────────────────────


class TestGet:
    def test_key_bound(self):
        # nv
        v = Var()
        dt = DictTerm({"name": "alice", "age": 30})
        sols, trail = simple_solutions(_get_3, dt, "name", v)
        assert len(sols) == 1
        assert deref(v) == "alice"

    def test_key_not_found_fails(self):
        # nv
        sols, _ = simple_solutions(_get_3, DictTerm({"a": 1}), "z", Var())
        assert len(sols) == 0

    def test_key_unbound_enumerates(self):
        # nv
        dt = DictTerm({"x": 1, "y": 2, "z": 3})
        pairs = []
        trail = Trail()
        for _ in _get_3(dt, Var(), Var(), trail, None):
            # We need fresh vars each iteration to collect properly
            pass
        # Better: collect via separate calls
        keys_found = set()
        for key in ["x", "y", "z"]:
            k, v = Var(), Var()
            t = Trail()
            sols = list(_get_3(dt, k, v, t, None))
            # k is unbound at start — but we passed a fresh Var here,
            # let's test with bound keys instead for simplicity
        # Test enumeration properly with unbound key
        k, v = Var(), Var()
        trail = Trail()
        count = 0
        for _ in _get_3(dt, k, v, trail, None):
            count += 1
        assert count == 3

    def test_not_dict_term_fails(self):
        # nv
        sols, _ = simple_solutions(_get_3, "not a dict", "key", Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        v = Var()
        dt = DictTerm({"a": 42})
        sols, trail = trampoline_solutions(Get, dt, "a", v)
        assert len(sols) == 1
        assert deref(v) == 42


# ── ReadFile/2 & WriteFile/2 ───────────────────────────────────────────


class TestFileIO:
    def test_round_trip(self, tmp_path):
        # nv
        path = str(tmp_path / "test.json")
        dt = DictTerm({"hello": "world", "n": 42})
        sols, _ = simple_solutions(_write_file_2, path, dt)
        assert len(sols) == 1

        t = Var()
        sols, trail = simple_solutions(_read_file_2, path, t)
        assert len(sols) == 1
        result = deref(t)
        assert isinstance(result, DictTerm)
        assert result.data["hello"] == "world"
        assert result.data["n"] == 42

    def test_read_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, "/nonexistent/file.json", Var())
        assert len(sols) == 0

    def test_write_unbound_term_fails(self):
        # nv
        sols, _ = simple_solutions(_write_file_2, "/tmp/test.json", Var())
        assert len(sols) == 0

    def test_read_unbound_path_fails(self):
        # nv
        sols, _ = simple_solutions(_read_file_2, Var(), Var())
        assert len(sols) == 0
