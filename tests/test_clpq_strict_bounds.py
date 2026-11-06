"""Strict bounds inside the legacy CLP(Q) simplex.

The legacy solver kept ``l < r`` as ``l =< r`` plus a passive disequality
``l =\\= r``, checked only when variables were fixed or after a binding or
an equality.  A strict bound closed by inequalities alone was accepted:
``{X >= 0}, {Y >= 0}, {S = X + Y}, {S < 0}`` succeeded in 18 of its 24
posting orders, ``{X < Y}, {Y < X}`` succeeded, and so did ``{X < Y, X >=
3, Y =< 3}``.  ``bb_inf/3`` ignored strictness (``{X > 0, X =< 2}``,
``bb_inf([X], X, I)`` failed; ``I = 1``).

The simplex now keeps each bound with its strictness and its assignment as
delta-rationals ``c + k*d`` (Dutertre and de Moura), so feasibility decides
strictness on every post.  Each case runs on both solvers, so the port
(``holzbaur``) pins the expected answer.  The last class is a seeded
differential of the two solvers over random small stores.
"""
import itertools
import random
from fractions import Fraction

import pytest

from clausal.logic.clpq import holzbaur as _holzbaur
from clausal.logic.clpq import legacy as _legacy
from clausal.logic.variables import Trail, Var, deref, is_var, unify

SOLVERS = pytest.mark.parametrize("solver", [_legacy, _holzbaur],
                                  ids=["legacy", "holzbaur"])


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


@SOLVERS
@pytest.mark.parametrize("order", list(itertools.permutations(range(4))),
                         ids=lambda o: "".join(map(str, o)))
def test_a_sum_of_nonnegatives_below_zero_fails_in_every_order(solver, order):
    ok, _, _ = _run(solver, [SUM_STORE[i] for i in order])
    assert not ok


@SOLVERS
@pytest.mark.parametrize("order", list(itertools.permutations(range(4))),
                         ids=lambda o: "".join(map(str, o)))
def test_the_nonstrict_control_fails_in_every_order(solver, order):
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


@SOLVERS
@pytest.mark.parametrize("name", list(CLOSED))
def test_a_closed_strict_bound_fails(solver, name):
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


@SOLVERS
@pytest.mark.parametrize("case", range(len(OPEN)))
def test_an_open_strict_bound_succeeds_with_the_ports_inf_and_sup(
        solver, case):
    store, expr, (lo, hi) = OPEN[case]
    ok, trail, names = _run(solver, store)
    assert ok
    i, s = Var(), Var()
    e = _term(expr, names)
    assert solver.inf(e, i, trail) and deref(i) == lo
    assert solver.sup(e, s, trail) and deref(s) == hi


@SOLVERS
def test_a_long_strict_chain_is_open(solver):
    xs = [f"X{i}" for i in range(30)]
    store = [("<", a, b) for a, b in zip(xs, xs[1:])]
    store += [(">=", xs[0], 0), ("=<", xs[-1], 1)]
    ok, trail, names = _run(solver, store)
    assert ok
    s = Var()
    assert solver.sup(names["X15"], s, trail) and deref(s) == 1


@SOLVERS
def test_maximize_of_an_open_bound_fails(solver):
    # The supremum 3 is not attained.
    ok, trail, names = _run(solver, [("<", "X", 3)])
    assert ok
    assert not solver.maximize(names["X"], Var(), trail)


@SOLVERS
def test_minimize_of_a_closed_bound_succeeds(solver):
    ok, trail, names = _run(solver, [("<", "X", 3), (">=", "X", 0)])
    assert ok
    m = Var()
    assert solver.minimize(names["X"], m, trail) and deref(m) == 0


def test_legacy_maximize_does_not_bind_another_variable_onto_its_strict_bound():
    # X = 3 is attained; Y keeps 0 < Y < 1 and must take a value inside it.
    ok, trail, names = _run(_legacy, [("=<", "X", 3), (">", "Y", 0),
                                      ("<", "Y", 1)])
    assert ok
    m = Var()
    assert _legacy.maximize(names["X"], m, trail) and deref(m) == 3
    y = deref(names["Y"])
    assert is_var(y) or 0 < y < 1


# ── bb_inf ───────────────────────────────────────────────────────────────────

BB = [
    ([(">", "X", 0), ("=<", "X", 2)], "X", 1),
    ([(">", "X", 1), ("<", "X", 3)], "X", 2),
    ([(">", ("*", 2, "X"), 1), ("=<", "X", 5)], "X", 1),
    ([(">", "X", "Y"), (">=", "Y", 2), ("=<", "X", 10)], "X", 3),
]


@SOLVERS
@pytest.mark.parametrize("case", range(len(BB)))
def test_bb_inf_respects_a_strict_bound(solver, case):
    store, var, expected = BB[case]
    ok, trail, names = _run(solver, store)
    assert ok
    i = Var()
    assert solver.bb_inf([names[var]], names[var], i, trail)
    assert deref(i) == expected


@SOLVERS
def test_bb_inf_with_no_integer_inside_open_bounds_fails(solver):
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


@SOLVERS
@pytest.mark.parametrize("case", range(len(BINDINGS)))
def test_a_strict_bound_and_bindings(solver, case):
    steps, expected = BINDINGS[case]
    ok, _, _ = _run(solver, steps)
    assert ok == expected


@SOLVERS
def test_after_strict_bounds_x_takes_a_value_inside_them(solver):
    ok, trail, names = _run(solver, [(">", "X", 0), ("<", "X", "Y"),
                                     ("=<", "Y", 1)])
    assert ok
    assert unify(names["X"], Fraction(1, 2), trail)
    v = Var()
    assert solver.inf(names["Y"], v, trail) and deref(v) == Fraction(1, 2)


# ── Backtracking ─────────────────────────────────────────────────────────────

@SOLVERS
def test_a_strict_bound_is_undone_on_backtracking(solver):
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


@SOLVERS
def test_a_strictness_tightened_on_one_branch_is_undone(solver):
    ok, trail, names = _run(solver, [("=<", "X", 1), (">=", "X", 0)])
    assert ok
    mark = trail.mark()
    assert _step(solver, ("<", "X", 1), names, trail)
    assert not _step(solver, (">=", "X", 1), names, trail)
    trail.undo(mark)
    assert _step(solver, (">=", "X", 1), names, trail)
    assert deref(names["X"]) == 1


# ── Residuals ────────────────────────────────────────────────────────────────

def test_legacy_projects_strictness_through_an_eliminated_variable():
    # Y is projected away; X < Y < 3 leaves X < 3 (it printed X =< 3).
    ok, trail, names = _run(_legacy, [("<", "X", "Y"), ("<", "Y", 3)])
    assert ok
    x = names["X"]
    assert _legacy.dump_q([x], trail, lambda v: "X") == ["{X < 3}"]


def test_legacy_prints_a_strict_bound_as_before():
    ok, trail, names = _run(_legacy, [("<", "X", 3), (">=", "X", 0)])
    assert ok
    x = names["X"]
    assert _legacy.residual_q([x], trail, lambda v: "X") == [
        "{X >= 0}", "{X < 3}"]
    ok, trail, names = _run(_legacy, [("<", "X", "Y")])
    assert _legacy.residual_q([names["X"], names["Y"]], trail,
                              lambda v: "X" if v is names["X"] else "Y") == [
        "{X - Y < 0}"]


# ── A seeded differential: legacy against the port ──────────────────────────

_RELATIONS = ["<", "<", "=<", ">", ">=", "=", "=\\="]


def _random_expression(rng, variables):
    expr = None
    for v in variables:
        c = rng.choice([0, 0, 1, -1, 2, Fraction(1, 2)])
        if not c:
            continue
        term = v if c == 1 else ("*", c, v)
        expr = term if expr is None else ("+", expr, term)
    return expr if expr is not None else rng.choice(variables)


def random_store(seed):
    """3 to 10 steps over 2 to 5 variables: posts mixing the six relations
    (against a constant, or another expression), with an occasional
    binding to a small rational or to another variable and an occasional
    in_q/3; and an expression to read sup/2 and inf/2 of."""
    rng = random.Random(seed)
    names = [f"V{i}" for i in range(rng.randint(2, 5))]
    steps = []
    for _ in range(rng.randint(3, 10)):
        r = rng.random()
        if r < 0.1:
            value = Fraction(rng.randint(-3, 3), rng.choice([1, 2]))
            if value.denominator == 1:
                value = int(value)    # an integral value is an int
            steps.append(("bind", rng.choice(names), value))
        elif r < 0.14:
            a, b = rng.sample(names, 2)
            steps.append(("bind", a, b))
        elif r < 0.24:
            steps.append(("in_q", rng.choice(names),
                          rng.choice([None, rng.randint(-3, 2)]),
                          rng.choice([None, rng.randint(-2, 3)])))
        else:
            right = (_random_expression(rng, names) if rng.random() < 0.3
                     else rng.randint(-2, 2))
            steps.append((rng.choice(_RELATIONS),
                          _random_expression(rng, names), right))
    return steps, _random_expression(rng, names)


def outcome(solver, steps, expr):
    """``(True, sup, inf)`` of *expr* (None where unbounded) when every
    step succeeds, else ``(False,)``."""
    trail, names = Trail(), {}
    for step in steps:
        if not _step(solver, step, names, trail):
            return (False,)
    e = _term(expr, names)
    bounds = []
    for read in (solver.sup, solver.inf):
        r = Var()
        bounds.append(deref(r) if read(e, r, trail) else None)
    return (True, *bounds)


@pytest.mark.parametrize("block", range(4))
def test_legacy_agrees_with_the_port_on_random_stores(block):
    """Seeds 0 to 399 (a sweep of 13,000 more, 2026-10-28, found none);
    13 of the first 2,000 differed before the strict bounds moved into
    the simplex, every one a store legacy wrongly accepted."""
    mismatches = []
    for seed in range(block * 100, block * 100 + 100):
        steps, expr = random_store(seed)
        if outcome(_legacy, steps, expr) != outcome(_holzbaur, steps, expr):
            mismatches.append((seed, steps))
    assert not mismatches, mismatches[:3]
