"""Tests for clausal.modules.py.process — Process and subprocess predicates."""

from __future__ import annotations

import time

import pytest

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.modules.py.process import (
    shell, shell_output, process_create, sleep,
    _shell_1, _shell_2, _shell_output_2, _shell_output_3,
    _process_create_3, _process_create_4, _sleep_1,
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
    gen = dispatch(None, None, None, None, *args, trail)
    solutions = []
    for parent, value in gen:
        if value is DONE:
            break
        solutions.append(value)
    return solutions, trail


# ── shell/1 ────────────────────────────────────────────────────────────


class TestShell1:
    def test_true_succeeds(self):
        # nv
        sols, _ = simple_solutions(_shell_1, "true")
        assert len(sols) == 1

    def test_false_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_1, "false")
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_1, Var())
        assert len(sols) == 0

    def test_non_string_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_1, 42)
        assert len(sols) == 0

    def test_trampoline_multi_arity(self):
        # Arity 1 via multi-dispatch
        # nv
        sols, _ = trampoline_solutions(shell, "true")
        assert len(sols) == 1


# ── shell/2 ────────────────────────────────────────────────────────────


class TestShell2:
    def test_true_exit_zero(self):
        # nv
        code = Var()
        sols, trail = simple_solutions(_shell_2, "true", code)
        assert len(sols) == 1
        assert deref(code) == 0

    def test_false_exit_one(self):
        # nv
        code = Var()
        sols, trail = simple_solutions(_shell_2, "false", code)
        assert len(sols) == 1
        assert deref(code) == 1

    def test_trampoline(self):
        # nv
        code = Var()
        sols, trail = trampoline_solutions(shell, "true", code)
        assert len(sols) == 1
        assert deref(code) == 0


# ── shell_output/2 ─────────────────────────────────────────────────────


class TestShellOutput2:
    def test_captures_stdout(self):
        # nv
        output = Var()
        sols, trail = simple_solutions(_shell_output_2, "echo hello", output)
        assert len(sols) == 1
        assert deref(output).strip() == "hello"

    def test_nonzero_exit_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_output_2, "false", Var())
        assert len(sols) == 0

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_shell_output_2, Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        output = Var()
        sols, trail = trampoline_solutions(shell_output, "echo world", output)
        assert len(sols) == 1
        assert deref(output).strip() == "world"


# ── shell_output/3 ─────────────────────────────────────────────────────


class TestShellOutput3:
    def test_captures_stdout_and_stderr(self):
        # nv
        out, err = Var(), Var()
        sols, trail = simple_solutions(
            _shell_output_3, "echo out && echo err >&2", out, err
        )
        assert len(sols) == 1
        assert deref(out).strip() == "out"
        assert deref(err).strip() == "err"

    def test_trampoline(self):
        # nv
        out, err = Var(), Var()
        sols, trail = trampoline_solutions(
            shell_output, "echo hello && echo warn >&2", out, err
        )
        assert len(sols) == 1
        assert deref(out).strip() == "hello"
        assert deref(err).strip() == "warn"


# ── process_create/3 ──────────────────────────────────────────────────


class TestProcessCreate3:
    def test_runs_program(self):
        # nv
        result = Var()
        sols, trail = simple_solutions(
            _process_create_3, "echo", ["hello"], result
        )
        assert len(sols) == 1
        r = deref(result)
        assert isinstance(r, DictTerm)
        assert r.data["exit_code"] == 0
        assert "hello" in r.data["stdout"]

    def test_nonexistent_program_fails(self):
        # nv
        sols, _ = simple_solutions(
            _process_create_3, "/nonexistent_program_xyz", [], Var()
        )
        assert len(sols) == 0

    def test_unbound_program_fails(self):
        # nv
        sols, _ = simple_solutions(_process_create_3, Var(), [], Var())
        assert len(sols) == 0

    def test_unbound_args_fails(self):
        # nv
        sols, _ = simple_solutions(_process_create_3, "echo", Var(), Var())
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        result = Var()
        sols, trail = trampoline_solutions(
            process_create, "echo", ["test"], result
        )
        assert len(sols) == 1
        r = deref(result)
        assert r.data["exit_code"] == 0


# ── process_create/4 ──────────────────────────────────────────────────


class TestProcessCreate4:
    def test_with_cwd(self, tmp_path):
        # nv
        result = Var()
        opts = DictTerm({"cwd": str(tmp_path)})
        sols, trail = simple_solutions(
            _process_create_4, "pwd", [], opts, result
        )
        assert len(sols) == 1
        r = deref(result)
        assert str(tmp_path) in r.data["stdout"]

    def test_with_timeout(self):
        # nv
        result = Var()
        opts = DictTerm({"timeout": 0.01})
        sols, _ = simple_solutions(
            _process_create_4, "sleep", ["10"], opts, result
        )
        # Should fail due to timeout
        assert len(sols) == 0

    def test_with_input(self):
        # nv
        result = Var()
        opts = DictTerm({"input": "hello from stdin"})
        sols, trail = simple_solutions(
            _process_create_4, "cat", [], opts, result
        )
        assert len(sols) == 1
        r = deref(result)
        assert r.data["stdout"] == "hello from stdin"

    def test_trampoline(self):
        # nv
        result = Var()
        opts = DictTerm({})
        sols, trail = trampoline_solutions(
            process_create, "echo", ["trampoline"], opts, result
        )
        assert len(sols) == 1
        r = deref(result)
        assert "trampoline" in r.data["stdout"]


# ── sleep/1 ──────────────────────────────────────────────────────────


class TestSleep:
    def test_sleeps(self):
        # nv
        start = time.monotonic()
        sols, _ = simple_solutions(_sleep_1, 0.05)
        elapsed = time.monotonic() - start
        assert len(sols) == 1
        assert elapsed >= 0.04  # allow small tolerance

    def test_unbound_fails(self):
        # nv
        sols, _ = simple_solutions(_sleep_1, Var())
        assert len(sols) == 0

    def test_non_numeric_fails(self):
        # nv
        sols, _ = simple_solutions(_sleep_1, "not a number")
        assert len(sols) == 0

    def test_trampoline(self):
        # nv
        sols, _ = trampoline_solutions(sleep, 0.01)
        assert len(sols) == 1
