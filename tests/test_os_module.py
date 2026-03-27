"""Tests for clausal.modules.py.os — OS interaction predicates."""

from __future__ import annotations

import os
import sys

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.os import (
    EnvironmentVariable, SetEnvironmentVariable, UnsetEnvironmentVariable,
    WorkingDirectory, ChangeDirectory, Pid, Argv, Platform, CPUCount,
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


# ── EnvironmentVariable/2 ───────────────────────────────────────────────


class TestEnvironmentVariable:
    def test_get_home(self):
        v = Var()
        sols, trail = simple_solutions(_environment_variable_2, "HOME", v)
        assert len(sols) == 1
        assert deref(v) == os.environ.get("HOME")

    def test_get_path(self):
        v = Var()
        sols, trail = simple_solutions(_environment_variable_2, "PATH", v)
        assert len(sols) == 1
        assert deref(v) == os.environ["PATH"]

    def test_missing_var_fails(self):
        v = Var()
        sols, _ = simple_solutions(
            _environment_variable_2, "_CLAUSAL_NONEXISTENT_VAR_", v
        )
        assert len(sols) == 0

    def test_enumerate_all(self):
        """Unbound name enumerates all env vars."""
        name, value = Var(), Var()
        trail = Trail()
        count = 0
        for _ in _environment_variable_2(name, value, trail, None):
            count += 1
        assert count >= 3  # PATH, HOME, etc. should exist

    def test_unify_value_check(self):
        """when value is pre-bound to the correct value, succeeds."""
        home = os.environ.get("HOME", "")
        if not home:
            pytest.skip("HOME not set")
        sols, _ = simple_solutions(_environment_variable_2, "HOME", home)
        assert len(sols) == 1

    def test_unify_value_wrong_fails(self):
        """when value is pre-bound to wrong value, fails."""
        sols, _ = simple_solutions(
            _environment_variable_2, "HOME", "definitely_not_home"
        )
        assert len(sols) == 0

    def test_trampoline(self):
        v = Var()
        sols, trail = trampoline_solutions(EnvironmentVariable, "PATH", v)
        assert len(sols) == 1
        assert deref(v) == os.environ["PATH"]


# ── SetEnvironmentVariable/2 ───────────────────────────────────────────


class TestSetEnvironmentVariable:
    def test_set_and_get(self):
        key = "_CLAUSAL_TEST_SET_VAR_"
        try:
            sols, _ = simple_solutions(_set_environment_variable_2, key, "hello")
            assert len(sols) == 1
            assert os.environ[key] == "hello"
        finally:
            os.environ.pop(key, None)

    def test_unbound_name_fails(self):
        sols, _ = simple_solutions(_set_environment_variable_2, Var(), "val")
        assert len(sols) == 0

    def test_unbound_value_fails(self):
        sols, _ = simple_solutions(_set_environment_variable_2, "KEY", Var())
        assert len(sols) == 0

    def test_non_string_name_fails(self):
        sols, _ = simple_solutions(_set_environment_variable_2, 42, "val")
        assert len(sols) == 0


# ── UnsetEnvironmentVariable/1 ─────────────────────────────────────────


class TestUnsetEnvironmentVariable:
    def test_set_then_unset(self):
        key = "_CLAUSAL_TEST_UNSET_VAR_"
        os.environ[key] = "temp"
        sols, _ = simple_solutions(_unset_environment_variable_1, key)
        assert len(sols) == 1
        assert key not in os.environ

    def test_nonexistent_fails(self):
        sols, _ = simple_solutions(
            _unset_environment_variable_1, "_CLAUSAL_NONEXISTENT_UNSET_"
        )
        assert len(sols) == 0

    def test_unbound_fails(self):
        sols, _ = simple_solutions(_unset_environment_variable_1, Var())
        assert len(sols) == 0


# ── WorkingDirectory/1 ─────────────────────────────────────────────────


class TestWorkingDirectory:
    def test_returns_string(self):
        v = Var()
        sols, trail = simple_solutions(_working_directory_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_matches_os_getcwd(self):
        v = Var()
        sols, trail = simple_solutions(_working_directory_1, v)
        assert deref(v) == os.getcwd()

    def test_trampoline(self):
        v = Var()
        sols, trail = trampoline_solutions(WorkingDirectory, v)
        assert len(sols) == 1
        assert deref(v) == os.getcwd()


# ── ChangeDirectory/1 ──────────────────────────────────────────────────


class TestChangeDirectory:
    def test_change_and_verify(self, tmp_path):
        original = os.getcwd()
        try:
            sols, _ = simple_solutions(_change_directory_1, str(tmp_path))
            assert len(sols) == 1
            assert os.getcwd() == str(tmp_path)
        finally:
            os.chdir(original)

    def test_nonexistent_fails(self):
        sols, _ = simple_solutions(_change_directory_1, "/nonexistent_dir_xyz")
        assert len(sols) == 0

    def test_unbound_fails(self):
        sols, _ = simple_solutions(_change_directory_1, Var())
        assert len(sols) == 0


# ── Pid/1 ──────────────────────────────────────────────────────────────


class TestPid:
    def test_returns_int(self):
        v = Var()
        sols, trail = simple_solutions(_pid_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, int)
        assert result > 0

    def test_matches_os_getpid(self):
        v = Var()
        sols, trail = simple_solutions(_pid_1, v)
        assert deref(v) == os.getpid()

    def test_trampoline(self):
        v = Var()
        sols, trail = trampoline_solutions(Pid, v)
        assert len(sols) == 1
        assert deref(v) == os.getpid()


# ── Argv/1 ─────────────────────────────────────────────────────────────


class TestArgv:
    def test_returns_list(self):
        v = Var()
        sols, trail = simple_solutions(_argv_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, list)

    def test_trampoline(self):
        v = Var()
        sols, trail = trampoline_solutions(Argv, v)
        assert len(sols) == 1
        assert isinstance(deref(v), list)


# ── Platform/1 ─────────────────────────────────────────────────────────


class TestPlatform:
    def test_returns_known_platform(self):
        v = Var()
        sols, trail = simple_solutions(_platform_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert result == sys.platform

    def test_trampoline(self):
        v = Var()
        sols, trail = trampoline_solutions(Platform, v)
        assert len(sols) == 1
        assert deref(v) == sys.platform


# ── CPUCount/1 ─────────────────────────────────────────────────────────


class TestCPUCount:
    def test_returns_positive_int(self):
        v = Var()
        sols, trail = simple_solutions(_cpu_count_1, v)
        assert len(sols) == 1
        result = deref(v)
        assert isinstance(result, int)
        assert result > 0

    def test_matches_os_cpu_count(self):
        v = Var()
        sols, trail = simple_solutions(_cpu_count_1, v)
        assert deref(v) == os.cpu_count()

    def test_trampoline(self):
        v = Var()
        sols, trail = trampoline_solutions(CPUCount, v)
        assert len(sols) == 1
        assert deref(v) == os.cpu_count()
