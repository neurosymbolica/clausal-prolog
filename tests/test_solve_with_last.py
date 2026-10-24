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


# ── builtins: FINAL on the answer they know is their last ────────────────────
# Each row drives ONE builtin as the root (call_with_last), so the flag is the
# builtin's own.  ``lasts`` is the per-answer flag list; every row also checks
# that the answers are exactly the ones plain ``call`` gives (a FINAL that
# came too early would lose the rest), and that pulling again after a last
# answer finds nothing.

from clausal.logic.atoms import mint  # noqa: E402


def _a(*names):
    return [mint(n) for n in names]


def _builtin_rows():
    V = Var
    return [
        # member/2: the answer at the last element of a proper list
        ("member", lambda: (V(), _a("a", "b", "c")), [False, False, True]),
        ("member", lambda: (mint("b"), _a("a", "b", "c")), [False]),
        ("member", lambda: (mint("c"), _a("a", "b", "c")), [True]),
        ("member", lambda: (V(), [V(), V()]), [False, True]),
        ("member", lambda: (mint("z"), _a("a")), []),
        ("memberchk", lambda: (V(), _a("a", "b")), [True]),
        # between/3: at the upper bound; check mode always
        ("between", lambda: (1, 3, V()), [False, False, True]),
        ("between", lambda: (1, 3, 3), [True]),
        ("between", lambda: (1, 3, 2), [True]),
        ("between", lambda: (3, 1, V()), []),
        # select/3, nth0/3, nth1/3: enumerating, at the last element
        ("select", lambda: (V(), _a("a", "b"), V()), [False, True]),
        ("select", lambda: (mint("a"), _a("a", "b"), V()), [False]),
        ("nth0", lambda: (V(), _a("a", "b"), V()), [False, True]),
        ("nth1", lambda: (2, _a("a", "b"), V()), [True]),
        ("nth0", lambda: (V(), _a("a", "b", "a"), mint("a")), [False, True]),
        # append/3: a fixed split is one answer; splitting, the last split
        ("append", lambda: (_a("a"), _a("b"), V()), [True]),
        ("append", lambda: (V(), V(), _a("a", "b")), [False, False, True]),
        # ... the matching split is not the last one tried (Scryer: pending)
        ("append", lambda: (V(), _a("b"), _a("a", "b")), [False]),
        # length/2
        ("length", lambda: (V(), 2), [True]),
        ("length", lambda: (_a("a"), V()), [True]),
        # semidet simple-mode builtins
        ("=", lambda: (V(), 1), [True]),
        ("is", lambda: (V(), ("+", 1, 2)), [True]),
        ("atom_length", lambda: (mint("abc"), V()), [True]),
        ("functor", lambda: (("f", 1), V(), V()), [True]),
        ("var", lambda: (V(),), [True]),
        ("msort", lambda: (_a("b", "a"), V()), [True]),
        ("last", lambda: (_a("a", "b"), V()), [True]),
        # builtins that enumerate without knowing their last answer
        ("sub_atom", lambda: (mint("ab"), V(), 1, V(), V()), [False, False]),
    ]


@pytest.mark.parametrize(
    "name,make,lasts", _builtin_rows(),
    ids=[f"{r[0]}-{i}" for i, r in enumerate(_builtin_rows())])
def test_a_builtin_marks_its_last_answer(name, make, lasts):
    m = clausal.Module(f"b_{name}")
    args = make()
    got = [last for _t, last in call_with_last(name, *args, module=m)]
    assert got == lasts
    args = make()
    assert len(list(clausal.call(name, *args, module=m))) == len(lasts)


def test_pulling_again_after_a_builtins_last_answer_finds_nothing():
    m = clausal.Module("b_pull")
    x = Var()
    it = call_with_last("member", x, _a("a", "b"), module=m)
    assert [next(it)[1], next(it)[1]] == [False, True]
    with pytest.raises(StopIteration):
        next(it)
    assert isinstance(deref(x), Var)    # the last answer's binding is undone


def test_a_woken_goal_makes_a_builtins_answer_not_last():
    """freeze/2 on X wakes when member/2 binds it, and the woken goal has
    answers of its own: the answer it ran at is not known to be last."""
    m = clausal.Module("b_freeze")
    x, y, trail = Var(), Var(), Trail()
    posted = clausal.solve(("freeze", x, ("member", y, [1, 2])), m, trail)
    next(posted)                       # the constraint stays posted
    got = [(deref(x), deref(y), last) for _t, last in
           call_with_last("member", x, _a("a"), module=m, trail=trail)]
    assert got == [(mint("a"), 1, False), (mint("a"), 2, False)]


def test_a_dif_checked_at_the_last_element_keeps_it_last():
    """dif/2's check runs inside the unification (no goal is queued), so the
    last element's answer stays last."""
    m = clausal.Module("b_dif")
    x, trail = Var(), Trail()
    posted = clausal.call("dif", x, mint("a"), module=m, trail=trail)
    next(posted)                       # the constraint stays posted
    got = [(deref(x), last) for _t, last in
           call_with_last("member", x, _a("a", "b"), module=m, trail=trail)]
    assert got == [(mint("b"), True)]
