"""Tests for clausal.modules.py.os — OS interaction predicates."""

from __future__ import annotations

import os
import sys

import pytest

from clausal.logic.cells import chars, is_chars
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.os import (
    environment_variable, set_environment_variable, unset_environment_variable,
    working_directory, change_directory, pid, argv, platform, cpu_count,
    _environment_variable_2, _set_environment_variable_2,
    _unset_environment_variable_1, _working_directory_1,
    _change_directory_1, _pid_1, _argv_1, _platform_1, _cpu_count_1,
)
from clausal.logic.trampoline import DONE


# ── Helpers ──────────────────────────────────────────────────────────────


def simple_solutions(fn, *args):
    """Run a simple-mode builtin and collect solutions."""
    trail = Trail()
    results = list(fn(*args, trail, None))
    return results, trail


def raised(fn, *args):
    """The error term a simple-mode builtin raises.  RULED 2026-10-02: an
    argument of the wrong type raises type_error, an unbound required one
    instantiation_error -- neither fails the goal."""
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as info:
        list(fn(*args, Trail(), None))
    return info.value.term


def trampoline_solutions(pred, *args):
    """Run a trampoline-protocol predicate and collect solution snapshots."""
    trail = Trail()
    dispatch = pred._get_dispatch()
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── environment_variable/2 ───────────────────────────────────────────────


class TestEnvironmentVariable:
    def test_get_home(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_environment_variable_2, chars("HOME"), v)
        assert len(sols) == 1
        assert deref(v) == chars(os.environ.get("HOME"))

    def test_get_path(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_environment_variable_2, chars("PATH"), v)
        assert len(sols) == 1
        assert deref(v) == chars(os.environ["PATH"])

    def test_missing_var_fails(self):
        # nv
        v = Var()
        sols, _ = simple_solutions(
            _environment_variable_2, chars("_CLAUSAL_NONEXISTENT_VAR_"), v
        )
        assert len(sols) == 0

    def test_enumerate_all(self):
        """Unbound name enumerates all env vars."""
        # nv
        name, value = Var(), Var()
        trail = Trail()
        count = 0
        for _ in _environment_variable_2(name, value, trail, None):
            count += 1
        assert count >= 3  # PATH, HOME, etc. should exist

    def test_unify_value_check(self):
        """when value is pre-bound to the correct value, succeeds."""
        # nv
        home = os.environ.get("HOME", "")
        if not home:
            pytest.skip("HOME not set")
        sols, _ = simple_solutions(_environment_variable_2, chars("HOME"), chars(home))
        assert len(sols) == 1

    def test_unify_value_wrong_fails(self):
        """when value is pre-bound to wrong value, fails."""
        # nv
        sols, _ = simple_solutions(
            _environment_variable_2, chars("HOME"), chars("definitely_not_home")
        )
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        v = Var()
        sols, trail = trampoline_solutions(environment_variable, chars("PATH"), v)
        assert len(sols) == 1
        assert deref(v) == chars(os.environ["PATH"])


# ── set_environment_variable/2 ───────────────────────────────────────────


class TestSetEnvironmentVariable:
    def test_set_and_get(self):
        # nv
        key = "_CLAUSAL_TEST_SET_VAR_"
        try:
            sols, _ = simple_solutions(_set_environment_variable_2, chars(key), chars("hello"))
            assert len(sols) == 1
            assert os.environ[key] == "hello"
        finally:
            os.environ.pop(key, None)

    def test_unbound_name_raises(self):
        # nv
        term = raised(_set_environment_variable_2, Var(), chars("val"))
        assert term == ('error', 'instantiation_error', ('/', 'set_environment_variable', 2))

    def test_unbound_value_raises(self):
        # nv
        term = raised(_set_environment_variable_2, chars("KEY"), Var())
        assert term == ('error', 'instantiation_error', ('/', 'set_environment_variable', 2))

    def test_non_string_name_raises(self):
        # nv
        term = raised(_set_environment_variable_2, 42, chars("val"))
        assert term == ('error', ('type_error', 'text', 42), ('/', 'set_environment_variable', 2))


# ── unset_environment_variable/1 ─────────────────────────────────────────


class TestUnsetEnvironmentVariable:
    def test_set_then_unset(self):
        # nv
        key = "_CLAUSAL_TEST_UNSET_VAR_"
        os.environ[key] = "temp"
        sols, _ = simple_solutions(_unset_environment_variable_1, chars(key))
        assert len(sols) == 1
        assert key not in os.environ

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(
            _unset_environment_variable_1, chars("_CLAUSAL_NONEXISTENT_UNSET_")
        )
        assert len(sols) == 0

    def test_unbound_raises(self):
        # nv
        term = raised(_unset_environment_variable_1, Var())
        assert term == ('error', 'instantiation_error', ('/', 'unset_environment_variable', 1))


# ── working_directory/1 ─────────────────────────────────────────────────


class TestWorkingDirectory:
    def test_returns_string(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_working_directory_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert is_chars(result)
        assert len(result) > 0

    def test_matches_os_getcwd(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_working_directory_1, v)
        assert deref(v) == chars(os.getcwd())

    def test_trampoline(self):
        # nv
        v = Var()
        sols, trail = trampoline_solutions(working_directory, v)
        assert len(sols) == 1
        assert deref(v) == chars(os.getcwd())


# ── change_directory/1 ──────────────────────────────────────────────────


class TestChangeDirectory:
    def test_change_and_verify(self, tmp_path):
        # nv
        original = os.getcwd()
        try:
            sols, _ = simple_solutions(_change_directory_1, chars(str(tmp_path)))
            assert len(sols) == 1
            assert os.getcwd() == str(tmp_path)
        finally:
            os.chdir(original)

    def test_nonexistent_fails(self):
        # nv
        sols, _ = simple_solutions(_change_directory_1, chars("/nonexistent_dir_xyz"))
        assert len(sols) == 0

    def test_unbound_raises(self):
        # nv
        term = raised(_change_directory_1, Var())
        assert term == ('error', 'instantiation_error', ('/', 'change_directory', 1))


# ── pid/1 ──────────────────────────────────────────────────────────────


class TestPid:
    def test_returns_int(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_pid_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, int)
        assert result > 0

    def test_matches_os_getpid(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_pid_1, v)
        assert deref(v) == os.getpid()

    def test_trampoline(self):
        # nv
        v = Var()
        sols, trail = trampoline_solutions(pid, v)
        assert len(sols) == 1
        assert deref(v) == os.getpid()


# ── argv/1 ─────────────────────────────────────────────────────────────


class TestArgv:
    def test_returns_list(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_argv_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, list)

    def test_trampoline(self):
        # nv
        v = Var()
        sols, trail = trampoline_solutions(argv, v)
        assert len(sols) == 1
        assert isinstance(deref(v), list)


# ── platform/1 ─────────────────────────────────────────────────────────


class TestPlatform:
    def test_returns_known_platform(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_platform_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert result == chars(sys.platform)

    def test_trampoline(self):
        # nv
        v = Var()
        sols, trail = trampoline_solutions(platform, v)
        assert len(sols) == 1
        assert deref(v) == chars(sys.platform)


# ── cpu_count/1 ─────────────────────────────────────────────────────────


class TestCPUCount:
    def test_returns_positive_int(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_cpu_count_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, int)
        assert result > 0

    def test_matches_os_cpu_count(self):
        # nv
        v = Var()
        sols, trail = simple_solutions(_cpu_count_1, v)
        assert deref(v) == os.cpu_count()

    def test_trampoline(self):
        # nv
        v = Var()
        sols, trail = trampoline_solutions(cpu_count, v)
        assert len(sols) == 1
        assert deref(v) == os.cpu_count()
