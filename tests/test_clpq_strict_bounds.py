"""Strict bounds in CLP(Q): the port of clp(q,r) 1.3.3 decides them.

The solver Clausal shipped before the port (retired 2026-11-05) once
kept ``l < r`` as ``l =< r`` plus a passive disequality ``l =\\= r``,
checked only when variables were fixed or after a binding or
an equality.  A strict bound closed by inequalities alone was accepted:
``{X >= 0}, {Y >= 0}, {S = X + Y}, {S < 0}`` succeeded in 18 of its 24
posting orders, ``{X < Y}, {Y < X}`` succeeded, and so did ``{X < Y, X >=
3, Y =< 3}``.  ``bb_inf/3`` ignored strictness (``{X > 0, X =< 2}``,
``bb_inf([X], X, I)`` failed; ``I = 1``).

These cases ran on both solvers while both existed; the port
(``holzbaur``) pinned the expected answers, which now stand on their own.
"""
import itertools
from fractions import Fraction

import pytest

from clausal.logic.clpq import holzbaur as solver
from clausal.logic.variables import Trail, Var, deref, unify


def _term(spec, names):
    """A str names a variable, a tuple ``(op, a, b)`` is an arithmetic cell
    over specs, anything else a number."""
    if isinstance(spec, str):
        return names.setdefault(spec, Var())
    if isinstance(spec, tuple):
        return (spec[0],) + tuple(_term(s, names) for s in spec[1:])
    return spec


def _step(solver, step, names, trail):
    """One post (``(op, l, r)``), binding (``("bind", name, value)``) or
    domain (``("in_q", name, lo, hi)``); its success."""
    op = step[0]
    if op == "bind":
        value = step[2]
        if isinstance(value, str):
            value = _term(value, names)
        return unify(_term(step[1], names), value, trail)
    if op == "in_q":
        return solver.in_q(_term(step[1], names), step[2], step[3], trail)
    rel = {"<": solver.q_lt, "=<": solver.q_le, ">": solver.q_gt,
           ">=": solver.q_ge, "=": solver.q_eq, "=\\=": solver.q_ne}[op]
    return rel(_term(step[1], names), _term(step[2], names), trail)


def _run(solver, steps, trail=None, names=None):
    trail = Trail() if trail is None else trail
    names = {} if names is None else names
    return all(_step(solver, s, names, trail) for s in steps), trail, names


# ── A strict bound closed by inequalities ────────────────────────────────────

SUM_STORE = [(">=", "X", 0), (">=", "Y", 0), ("=", "S", ("+", "X", "Y")),
             ("<", "S", 0)]


@pytest.mark.parametrize("order", list(itertools.permutations(range(4))),
                         ids=lambda o: "".join(map(str, o)))
def test_a_sum_of_nonnegatives_below_zero_fails_in_every_order(order):
    ok, _, _ = _run(solver, [SUM_STORE[i] for i in order])
    assert not ok


@pytest.mark.parametrize("order", list(itertools.permutations(range(4))),
                         ids=lambda o: "".join(map(str, o)))
def test_the_nonstrict_control_fails_in_every_order(order):
    store = SUM_STORE[:3] + [("=<", "S", -1)]
    ok, _, _ = _run(solver, [store[i] for i in order])
    assert not ok


CLOSED = {
    "cycle": [("<", "X", "Y"), ("<", "Y", "X")],
    "cycle_of_three": [("<", "X", "Y"), ("<", "Y", "Z"), ("<", "Z", "X")],
    "closed_by_bounds": [("<", "X", "Y"), (">=", "X", 3), ("=<", "Y", 3)],
    "closed_by_in_q": [("<", "X", "Y"), ("in_q", "X", 3, 10),
                       ("in_q", "Y", 0, 3)],
    "bounds_first": [(">=", "X", 3), ("=<", "Y", 3), ("<", "X", "Y")],
    "strict_against_strict": [(">", "X", 0), ("<", "X", 0)],
    "strict_against_point": [(">=", "X", 0), ("=<", "X", 0), ("<", "X", 0)],
    "scaled": [("<", ("*", 2, "X"), ("*", 2, "Y")), (">=", "X", "Y")],
    "through_a_row": [("<", ("+", "X", "Y"), 2), (">=", "X", 1),
                      (">=", "Y", 1)],
    "through_an_equality": [("=", "Z", ("-", "X", "Y")), ("<", "Z", 0),
                            (">=", "X", "Y")],
}


@pytest.mark.parametrize("name", list(CLOSED))
def test_a_closed_strict_bound_fails(name):
    ok, _, _ = _run(solver, CLOSED[name])
    assert not ok


# ── Strict bounds that are not closed ────────────────────────────────────────

OPEN = [
    # store, expression, (inf, sup)
    ([(">", "X", 0), ("<", "X", 1)], "X", (0, 1)),
    ([("<", "X", "Y"), (">=", "X", 0), ("=<", "Y", 1)], "X", (0, 1)),
    ([("<", "X", "Y"), (">=", "X", 0), ("=<", "Y", 1)], "Y", (0, 1)),
    ([("<", "X", "Y"), (">=", "X", 0), ("=<", "Y", 1)],
     ("-", "Y", "X"), (0, 1)),
    ([(">=", "X", 0), (">=", "Y", 0), ("=", "S", ("+", "X", "Y")),
      ("<", "S", 1)], "S", (0, 1)),
    ([("<", "X", "Y"), ("<", "Y", "Z"), (">=", "X", 0), ("=<", "Z", 3)],
     "Y", (0, 3)),
    ([(">", ("+", "X", "Y"), 2), ("=<", "X", 1), ("=<", "Y", 3)],
     "Y", (1, 3)),
]


@pytest.mark.parametrize("case", range(len(OPEN)))
def test_an_open_strict_bound_succeeds_with_the_ports_inf_and_sup(
        case):
    store, expr, (lo, hi) = OPEN[case]
    ok, trail, names = _run(solver, store)
    assert ok
    i, s = Var(), Var()
    e = _term(expr, names)
    assert solver.inf(e, i, trail) and deref(i) == lo
    assert solver.sup(e, s, trail) and deref(s) == hi


def test_a_long_strict_chain_is_open():
    xs = [f"X{i}" for i in range(30)]
    store = [("<", a, b) for a, b in zip(xs, xs[1:])]
    store += [(">=", xs[0], 0), ("=<", xs[-1], 1)]
    ok, trail, names = _run(solver, store)
    assert ok
    s = Var()
    assert solver.sup(names["X15"], s, trail) and deref(s) == 1


def test_maximize_of_an_open_bound_fails():
    # The supremum 3 is not attained.
    ok, trail, names = _run(solver, [("<", "X", 3)])
    assert ok
    assert not solver.maximize(names["X"], Var(), trail)


def test_minimize_of_a_closed_bound_succeeds():
    ok, trail, names = _run(solver, [("<", "X", 3), (">=", "X", 0)])
    assert ok
    m = Var()
    assert solver.minimize(names["X"], m, trail) and deref(m) == 0


# ── bb_inf ───────────────────────────────────────────────────────────────────

BB = [
    ([(">", "X", 0), ("=<", "X", 2)], "X", 1),
    ([(">", "X", 1), ("<", "X", 3)], "X", 2),
    ([(">", ("*", 2, "X"), 1), ("=<", "X", 5)], "X", 1),
    ([(">", "X", "Y"), (">=", "Y", 2), ("=<", "X", 10)], "X", 3),
]


@pytest.mark.parametrize("case", range(len(BB)))
def test_bb_inf_respects_a_strict_bound(case):
    store, var, expected = BB[case]
    ok, trail, names = _run(solver, store)
    assert ok
    i = Var()
    assert solver.bb_inf([names[var]], names[var], i, trail)
    assert deref(i) == expected


def test_bb_inf_with_no_integer_inside_open_bounds_fails():
    ok, trail, names = _run(solver, [(">", "X", 1), ("<", "X", 2)])
    assert ok
    assert not solver.bb_inf([names["X"]], names["X"], Var(), trail)


# ── Strict bounds and bindings ───────────────────────────────────────────────

BINDINGS = [
    ([("<", "X", "Y"), ("bind", "X", 1), ("bind", "Y", 1)], False),
    ([("<", "X", "Y"), ("bind", "X", 1), ("bind", "Y", 2)], True),
    ([("<", "X", "Y"), ("bind", "X", "Y")], False),
    ([("<", "X", "Y"), ("<", "Y", "Z"), ("bind", "X", 0), ("bind", "Z", 0)],
     False),
    ([("<", "X", "Y"), ("<", "Y", "Z"), ("bind", "X", 0), ("bind", "Z", 1)],
     True),
    ([("<", "X", "Y"), ("<", "Y", "Z"), ("bind", "X", 0), ("bind", "Z", 1),
      ("bind", "Y", 1)], False),
    ([("<", "X", "Y"), ("<", "Y", "Z"), ("bind", "X", 0), ("bind", "Z", 1),
      ("bind", "Y", Fraction(1, 2))], True),
    ([("<", "X", 3), ("bind", "X", 3)], False),
    ([("<", ("+", "X", "Y"), 3), ("bind", "X", 1), ("=<", 2, "Y")], False),
    ([("<", "X", "Y"), ("=<", "Y", 3), ("bind", "X", 3)], False),
    ([("<", "X", "Y"), ("=", "X", "Y")], False),
    # A disequality an earlier equality already contradicts (the
    # differential's two other finds; the strict bound is incidental).
    ([("=", ("+", "X", "Y"), 1), ("=\\=", ("+", "X", "Y"), 1)], False),
    ([("<", ("+", "Y", ("*", Fraction(1, 2), "Z")), 0),
      ("=", ("+", "X", ("*", Fraction(1, 2), "Y")), -2),
      ("=\\=", ("+", "X", ("*", Fraction(1, 2), "Y")), -2)], False),
    ([("=", ("+", "X", "Y"), 1), ("=\\=", ("+", "X", "Y"), 2)], True),
]


@pytest.mark.parametrize("case", range(len(BINDINGS)))
def test_a_strict_bound_and_bindings(case):
    steps, expected = BINDINGS[case]
    ok, _, _ = _run(solver, steps)
    assert ok == expected


def test_after_strict_bounds_x_takes_a_value_inside_them():
    ok, trail, names = _run(solver, [(">", "X", 0), ("<", "X", "Y"),
                                     ("=<", "Y", 1)])
    assert ok
    assert unify(names["X"], Fraction(1, 2), trail)
    v = Var()
    assert solver.inf(names["Y"], v, trail) and deref(v) == Fraction(1, 2)


# ── Backtracking ─────────────────────────────────────────────────────────────

def test_a_strict_bound_is_undone_on_backtracking():
    ok, trail, names = _run(solver, [(">=", "X", 0), ("=<", "X", 2)])
    assert ok
    mark = trail.mark()
    assert _step(solver, ("<", "X", 1), names, trail)
    assert not _step(solver, ("bind", "X", 1), names, trail)
    trail.undo(mark)
    # X < 1 is gone: X = 1 is fine now, and X = 2 too.
    mark = trail.mark()
    assert _step(solver, ("bind", "X", 1), names, trail)
    trail.undo(mark)
    assert _step(solver, ("bind", "X", 2), names, trail)


def test_a_strictness_tightened_on_one_branch_is_undone():
    ok, trail, names = _run(solver, [("=<", "X", 1), (">=", "X", 0)])
    assert ok
    mark = trail.mark()
    assert _step(solver, ("<", "X", 1), names, trail)
    assert not _step(solver, (">=", "X", 1), names, trail)
    trail.undo(mark)
    assert _step(solver, (">=", "X", 1), names, trail)
    assert deref(names["X"]) == 1
