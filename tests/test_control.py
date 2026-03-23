"""Tests for control builtins — TimeGoal/1."""

from __future__ import annotations

import re
import sys

import pytest

from clausal.logic.variables import Var, Trail, deref
from clausal.logic.database import Database, Module
from clausal.logic.solve import solve
from clausal.pythonic_ast.nodes import Call, LoadName


def _make_module():
    db = Database()
    return Module("test", db)


def _solve_goal(goal, mod=None):
    if mod is None:
        mod = _make_module()
    return list(solve(goal, mod))


def _call(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


# ── TimeGoal/1 ─────────────────────────────────────────────────────────────────


class TestTimeGoal:
    def test_success_single_solution(self, capsys):
        """TimeGoal succeeds and reports timing for a goal with one solution."""
        x = Var()
        goal = _call("TimeGoal", _call("Append", [1, 2], [3, 4], x))
        mod = _make_module()
        results = [deref(x) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3, 4]]
        err = capsys.readouterr().err
        assert "1 solution(s)" in err

    def test_success_multiple_solutions(self, capsys):
        """TimeGoal forwards all solutions and counts them in the timing line."""
        x = Var()
        goal = _call("TimeGoal", _call("In", x, [10, 20, 30]))
        results = []
        for _ in solve(goal, _make_module()):
            results.append(deref(x))
        assert results == [10, 20, 30]
        err = capsys.readouterr().err
        assert "3 solution(s)" in err

    def test_failure_zero_solutions(self, capsys):
        """TimeGoal reports 0 solutions when inner goal fails."""
        x = Var()
        goal = _call("TimeGoal", _call("In", x, []))
        solutions = _solve_goal(goal)
        assert solutions == []
        err = capsys.readouterr().err
        assert "0 solution(s)" in err

    def test_timing_fields_present(self, capsys):
        """Timing line contains wall and CPU fields."""
        goal = _call("TimeGoal", _call("Append", [], [], []))
        _solve_goal(goal)
        err = capsys.readouterr().err
        assert "wall" in err
        assert "CPU" in err

    def test_timing_format(self, capsys):
        """Timing line matches the expected pattern."""
        goal = _call("TimeGoal", _call("In", Var(), [1]))
        _solve_goal(goal)
        err = capsys.readouterr().err
        assert re.search(r"\d+ solution\(s\),\s+[\d.]+s wall,\s+[\d.]+s CPU", err)

    def test_solutions_pass_through(self, capsys):
        """TimeGoal is transparent — bindings from inner goal are visible."""
        # Wrap a simple multi-solution goal: In(X, [1, 2])
        x = Var()
        goal = _call("TimeGoal", _call("In", x, [1, 2]))
        pairs = []
        for _ in solve(goal, _make_module()):
            pairs.append(deref(x))
        assert pairs == [1, 2]
        err = capsys.readouterr().err
        assert "2 solution(s)" in err

    def test_nested_time_goal(self, capsys):
        """TimeGoal can wrap another TimeGoal (nested meta calls)."""
        x = Var()
        inner = _call("TimeGoal", _call("In", x, [42]))
        outer = _call("TimeGoal", inner)
        results = []
        for _ in solve(outer, _make_module()):
            results.append(deref(x))
        assert results == [42]
        err = capsys.readouterr().err
        # Both inner and outer emit a timing line
        assert err.count("solution(s)") == 2
