"""``solve_with_last`` / ``call_with_last``: a caller learns that a solution
is the LAST one without pulling again.

The signal is True only when the engine KNOWS no choice point is left (the
solution reached the root as ``FINAL``), and False when it does not know.
Every test that sees ``last=True`` pulls again and asserts that nothing
comes: soundness over coverage.
"""

from __future__ import annotations

import pytest

import clausal
from clausal.logic.solve import call_with_last, solve_with_last
from clausal.logic.trampoline import DONE, FINAL
from clausal.logic.variables import Trail, Var, deref, unify


class _Pred:
    """A goal object whose dispatch is a hand-written trampoline generator
    binding its argument to each of *values*, the last one as FINAL when
    *final*."""

    def __init__(self, values, final):
        self.values, self.final = values, final

    def _get_dispatch(self):
        values, final = self.values, self.final

        def dispatch(this, proceed, fail, catcher, x, trail):
            for i, v in enumerate(values):
                mark = trail.mark()
                if unify(x, v, trail):
                    last = final and i == len(values) - 1
                    yield (proceed, FINAL if last else None)
                trail.undo(mark)
            yield (fail, DONE)
        return dispatch


def _pairs(it, x):
    return [(deref(x), last) for _trail, last in it]


def test_the_functions_are_exported():
    assert clausal.solve_with_last is solve_with_last
    assert clausal.call_with_last is call_with_last
    assert "solve_with_last" in clausal.__all__
    assert "call_with_last" in clausal.__all__


def test_a_final_root_solution_is_marked_last():
    x = Var()
    assert _pairs(call_with_last(_Pred([1, 2], True), x), x) == [
        (1, False), (2, True)]


def test_without_final_no_solution_is_marked_last():
    x = Var()
    assert _pairs(call_with_last(_Pred([1, 2], False), x), x) == [
        (1, False), (2, False)]


def test_after_a_last_solution_the_bindings_are_undone():
    """A retired root is not resumed, so the driver undoes its bindings when
    the iterator is advanced past the last solution, as an exhausted search
    does."""
    x, trail = Var(), Trail()
    it = call_with_last(_Pred([7], True), x, trail=trail)
    _t, last = next(it)
    assert last is True and deref(x) == 7
    with pytest.raises(StopIteration):
        next(it)
    assert isinstance(deref(x), Var)


def test_plain_call_also_stops_and_undoes_at_a_final_solution():
    x = Var()
    got = [deref(x) for _ in clausal.call(_Pred([1, 2], True), x)]
    assert got == [1, 2]
    assert isinstance(deref(x), Var)


def test_trivial_goals():
    m = clausal.Module("trivial_goals")
    assert [last for _t, last in solve_with_last(True, m)] == [True]
    assert list(solve_with_last(False, m)) == []
