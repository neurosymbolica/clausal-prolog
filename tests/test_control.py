"""Tests for control builtins — time_goal/1."""

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


# ── time_goal/1 ─────────────────────────────────────────────────────────────────


class TestTimeGoal:
    def test_success_single_solution(self, capsys):
        """time_goal succeeds and reports timing for a goal with one solution."""
        # nv
        x = Var()
        goal = _call("time_goal", _call("append", [1, 2], [3, 4], x))
        mod = _make_module()
        results = [deref(x) for _ in solve(goal, mod)]
        assert results == [[1, 2, 3, 4]]
        err = capsys.readouterr().err
        assert "1 solution(s)" in err

    def test_success_multiple_solutions(self, capsys):
        """time_goal forwards all solutions and counts them in the timing line."""
        # nv
        x = Var()
        goal = _call("time_goal", _call("in_", x, [10, 20, 30]))
        results = []
        for _ in solve(goal, _make_module()):
            results.append(deref(x))
        assert results == [10, 20, 30]
        err = capsys.readouterr().err
        assert "3 solution(s)" in err

    def test_failure_zero_solutions(self, capsys):
        """time_goal reports 0 solutions when inner goal fails."""
        # nv
        x = Var()
        goal = _call("time_goal", _call("in_", x, []))
        solutions = _solve_goal(goal)
        assert solutions == []
        err = capsys.readouterr().err
        assert "0 solution(s)" in err

    def test_timing_fields_present(self, capsys):
        """Timing line contains wall and CPU fields."""
        # nv
        goal = _call("time_goal", _call("append", [], [], []))
        _solve_goal(goal)
        err = capsys.readouterr().err
        assert "wall" in err
        assert "CPU" in err

    def test_timing_format(self, capsys):
        """Timing line matches the expected pattern."""
        # nv
        goal = _call("time_goal", _call("in_", Var(), [1]))
        _solve_goal(goal)
        err = capsys.readouterr().err
        assert re.search(r"\d+ solution\(s\),\s+[\d.]+s wall,\s+[\d.]+s CPU", err)

    def test_solutions_pass_through(self, capsys):
        """time_goal is transparent — bindings from inner goal are visible."""
        # Wrap a simple multi-solution goal: in_(X, [1, 2])
        # nv
        x = Var()
        goal = _call("time_goal", _call("in_", x, [1, 2]))
        pairs = []
        for _ in solve(goal, _make_module()):
            pairs.append(deref(x))
        assert pairs == [1, 2]
        err = capsys.readouterr().err
        assert "2 solution(s)" in err

    def test_nested_time_goal(self, capsys):
        """time_goal can wrap another time_goal (nested meta calls)."""
        # nv
        x = Var()
        inner = _call("time_goal", _call("in_", x, [42]))
        outer = _call("time_goal", inner)
        results = []
        for _ in solve(outer, _make_module()):
            results.append(deref(x))
        assert results == [42]
        err = capsys.readouterr().err
        # Both inner and outer emit a timing line
        assert err.count("solution(s)") == 2


def test_time_goal_resolution_of_a_dataclass_term_still_falls_through():
    """``is_term_instance`` is also true of a ``@dataclass`` instance, whose
    class is no ``PredicateMeta`` and has no ``_row``.  The W2 rewrite of the
    ``getattr(cls, '_dispatch_fn', None)`` probe in ``_goal_dispatch_and_args``
    must keep answering ``(None, None)`` for it, not raise (roborev on
    9028f9b3, confirmed by a probe before the fix)."""
    import dataclasses
    from clausal.logic.builtins.control import _goal_dispatch_and_args

    @dataclasses.dataclass
    class NotAPredicate:
        x: int

    assert _goal_dispatch_and_args(NotAPredicate(1)) == (None, None)
