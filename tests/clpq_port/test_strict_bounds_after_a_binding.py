# tests/clpq_port/test_strict_bounds_after_a_binding.py
"""Task 13b (DEVIATIONS.md D19): after a binding's reconsider pass, the
port checks that every strict bound can still hold, so a binding that
leaves strict constraints unsatisfiable fails.

The fuzz posts a random linear store with strict and non-strict
constraints, then binds its variables one at a time, and checks after
each step that the port accepts exactly when z3 finds the store and the
bindings so far satisfiable.  A binding is the engine's unify (through the
CLPQ_KEY hook) or a posted `{X = K}`.  Each case runs bare and under a
driver (`trail.defer`, the woken goals run with pending.run_first).

CLAUSAL_SLOW_TESTS=1 runs the large seed count as well.
"""
import os
import random
from fractions import Fraction

import pytest
import z3

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import normal_form as nf
from clausal.logic.coroutining import _freeze_var
from clausal.logic.pending import run_first
from clausal.logic.variables import Trail, Var, deref, is_var, unify

_RELATIONS = ("<", "=<", ">", ">=", "<", ">")


def random_case(seed):
    """(number of variables, constraints, bindings) for *seed*: each
    constraint is (relation, [(coefficient, index), ...], constant); each
    binding (index, value, how), *how* "unify" or "post".  A value "inf"
    or "sup" is the variable's inf or sup at that point (0 where there is
    none): an open end of a strict interval is where a binding can leave
    the store unsatisfiable (the reproducer binds X4 to its inf)."""
    rng = random.Random(seed)
    count = rng.randint(3, 6)
    constraints = []
    for _ in range(rng.randint(4, 10)):
        chosen = rng.sample(range(count), rng.randint(2, 3))
        terms = [(rng.choice((-3, -2, -1, 1, 2, 3)), index) for index in chosen]
        constraints.append((rng.choice(_RELATIONS), terms, rng.randint(-6, 6)))
    order = rng.sample(range(count), rng.randint(1, count))
    bindings = [(index, rng.choice(("inf", "sup", "inf", "sup",
                                    rng.randint(-3, 3))),
                 rng.choice(("unify", "post")))
                for index in order]
    return count, constraints, bindings


def _expression(terms, variables):
    expression = None
    for coefficient, index in terms:
        term = ("*", coefficient, variables[index])
        expression = term if expression is None else ("+", expression, term)
    return expression


def _z3_constraint(relation, terms, constant, reals):
    left = z3.Sum([coefficient * reals[index] for coefficient, index in terms])
    if relation == "<":
        return left < constant
    if relation == "=<":
        return left <= constant
    if relation == ">":
        return left > constant
    if relation == ">=":
        return left >= constant
    return left == constant


def _satisfiable(solver):
    verdict = solver.check()
    assert verdict != z3.unknown
    return verdict == z3.sat


def _step(trail, operation):
    """Run one post or binding as its mode does: under a driver, the goals
    it woke run to their first answer."""
    if not operation():
        return False
    return not trail.defer or run_first(trail)


def check_case(seed, defer):
    """Disagreements between the port and z3 for *seed*, as text (empty
    when there are none), and the number of bindings checked."""
    count, constraints, bindings = random_case(seed)
    reals = [z3.Real(f"X{index}") for index in range(count)]
    solver = z3.Solver()
    for relation, terms, constant in constraints:
        solver.add(_z3_constraint(relation, terms, constant, reals))
    if not _satisfiable(solver):
        return [], 0                      # bindings only; posting is not checked here
    trail = Trail()
    trail.defer = defer
    variables = [Var() for _ in range(count)]
    try:
        for relation, terms, constant in constraints:
            term = (relation, _expression(terms, variables), constant)
            if not _step(trail, lambda term=term: nf.post_constraint(term, trail)):
                return [f"seed {seed}: the satisfiable store fails"], 0
        problems = []
        checked = 0
        for index, value, how in bindings:
            variable = variables[index]
            if value == "inf" or value == "sup":
                value = _optimum(bv.inf if value == "inf" else bv.sup,
                                 variable, trail)
            if how == "unify":
                accepted = _step(trail, lambda: unify(variable, value, trail))
            else:
                accepted = _step(trail, lambda: nf.post_constraint(
                    ("=", variable, value), trail))
            solver.add(reals[index] == value)
            expected = _satisfiable(solver)
            checked += 1
            if accepted != expected:
                problems.append(f"seed {seed}, X{index} = {value} by {how}: "
                                f"port {accepted}, z3 {expected}")
            if not accepted or not expected:
                break
        return problems, checked
    finally:
        trail.defer = False


def _optimum(optimum, variable, trail):
    """The inf or sup of *variable* (0 where there is none), the store as
    it was."""
    mark = trail.mark()
    result = Var()
    found = optimum(variable, result, trail)
    value = _value(result) if found else None
    trail.undo(mark)
    return 0 if value is None else value


def run_fuzz(seeds, defer):
    problems = []
    checked = 0
    for seed in seeds:
        found, count = check_case(seed, defer)
        problems += found
        checked += count
    return problems, checked


#: Seeds above 1500 where 1.3.3's single pass accepts an unsatisfiable
#: binding (found on 30,000 seeds before D19; 73 there, 4 below 1500).
_PINNED = (1920, 2352, 2409, 2487, 2511, 2815, 4329, 4788, 5028, 5314)


@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_binding_is_accepted_exactly_when_z3_finds_it_satisfiable(defer):
    problems, checked = run_fuzz(list(range(1500)) + list(_PINNED), defer)
    assert not problems, "\n".join(problems[:10])
    assert checked >= 1900, checked


@pytest.mark.skipif(os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
                    reason="set CLAUSAL_SLOW_TESTS=1 for the large seed count")
@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_binding_is_accepted_exactly_when_z3_finds_it_satisfiable_slow(defer):
    problems, checked = run_fuzz(range(1500, 30000), defer)
    assert not problems, "\n".join(problems[:10])


# ------------------------------------------------- goals woken by the passes

def _value(term):
    term = deref(term)
    return None if is_var(term) else Fraction(term)


@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_frozen_goal_on_a_variable_the_passes_bind_runs(defer):
    # {X + Y >= 2, X - Y >= 0, Y >= 1}, freeze(Y, ...), X = 1: the
    # binding implies Y = 1, and the frozen goal runs once, bare or under
    # a driver.
    trail = Trail()
    trail.defer = defer
    x, y = Var(), Var()
    runs = []

    def goal():
        runs.append(_value(y))
        yield None
    try:
        for term in ((">=", ("+", x, y), 2), (">=", ("-", x, y), 0),
                     (">=", y, 1)):
            assert _step(trail, lambda term=term: nf.post_constraint(term, trail))
        _freeze_var(y, goal, trail)
        assert _step(trail, lambda: unify(x, 1, trail))
    finally:
        trail.defer = False
    assert runs == [1] and _value(y) == 1


@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_frozen_goal_survives_inf_and_sup(defer):
    # inf/sup pivot under a mark and undo (Task 8); a goal frozen on a
    # store variable is still there afterwards and runs when the variable
    # is bound.
    trail = Trail()
    trail.defer = defer
    x, y, low, high = Var(), Var(), Var(), Var()
    runs = []

    def goal():
        runs.append(_value(y))
        yield None
    try:
        for term in ((">=", ("+", x, y), 2), ("=<", ("-", x, y), 4),
                     (">", y, 0), ("<", y, 3)):
            assert _step(trail, lambda term=term: nf.post_constraint(term, trail))
        _freeze_var(y, goal, trail)
        assert _step(trail, lambda: bv.inf(x, low, trail))
        assert _step(trail, lambda: bv.sup(y, high, trail))
        assert runs == []
        assert _step(trail, lambda: unify(y, 2, trail))
    finally:
        trail.defer = False
    assert runs == [2]
    assert _value(low) == -1 and _value(high) == 3
