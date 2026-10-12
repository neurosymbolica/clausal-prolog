# tests/clpq_port/test_strict_bounds_after_a_binding.py
"""Task 13b (DEVIATIONS.md D19): after a binding's reconsider pass, the
port checks that every strict bound can still hold, so a binding that
leaves strict constraints unsatisfiable fails.

The fuzz posts a random linear store with strict, non-strict and `=`
constraints, then takes steps: a binding of one variable, as the
engine's unify (through the CLPQ_KEY hook) or a posted `{X = K}`, or a
posted equation `{aX + bY (+ cZ) = K}`.  After each post and each step
it checks that the port accepts exactly when z3 finds everything so far
satisfiable.  Each case runs bare and under a driver (`trail.defer`, the
woken goals run with pending.run_first).

CLAUSAL_SLOW_TESTS=1 runs the large seed count as well.
"""
import os
import random
from fractions import Fraction

import pytest
import z3

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_UPPER, BOUNDS_UPPER,
    state_of)
from clausal.logic.clpq.components import (
    component_all_variables, list_elements)
from clausal.logic.clpq.linear_forms import independent
from clausal.logic.clpq import normal_form as nf
from clausal.logic.coroutining import _freeze_var
from clausal.logic.pending import run_first
from clausal.logic.variables import Trail, Var, deref, is_var, unify

_RELATIONS = ("<", "=<", ">", ">=", "<", ">", "=")


def random_case(seed):
    """(number of variables, constraints, steps) for *seed*: each
    constraint is (relation, [(coefficient, index), ...], constant).  A
    step is (terms, value, how): *how* "unify" or "post" binds the one
    variable of *terms* (`X = K` or `{X = K}`), "equation" posts
    `{aX + bY (+ cZ) = K}`.  A value "inf" or "sup" is that of the
    variable or sum at that point (0 where there is none): an open end of a
    strict interval is where a binding can leave the store unsatisfiable
    (the reproducer binds X4 to its inf)."""
    rng = random.Random(seed)
    count = rng.randint(3, 6)
    constraints = []
    for _ in range(rng.randint(4, 10)):
        chosen = rng.sample(range(count), rng.randint(2, 3))
        terms = [(rng.choice((-3, -2, -1, 1, 2, 3)), index) for index in chosen]
        constraints.append((rng.choice(_RELATIONS), terms, rng.randint(-6, 6)))
    steps = []
    for index in rng.sample(range(count), rng.randint(1, count)):
        value = rng.choice(("inf", "sup", "inf", "sup", rng.randint(-3, 3)))
        how = rng.choice(("unify", "post", "equation", "equation"))
        if how == "equation":
            chosen = rng.sample(range(count), rng.randint(2, min(3, count)))
            terms = [(rng.choice((-3, -2, -1, 1, 2, 3)), other)
                     for other in chosen]
        else:
            terms = [(1, index)]
        steps.append((terms, value, how))
    return count, constraints, steps


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
    when there are none), and the number of posts and steps checked: each
    constraint of the store as it is posted, then each step."""
    count, constraints, steps = random_case(seed)
    reals = [z3.Real(f"X{index}") for index in range(count)]
    solver = z3.Solver()
    trail = Trail()
    trail.defer = defer
    variables = [Var() for _ in range(count)]
    problems = []
    checked = 0
    try:
        for relation, terms, constant in constraints:
            term = (relation, _expression(terms, variables), constant)
            accepted = _step(trail, lambda term=term: nf.post_constraint(term, trail))
            solver.add(_z3_constraint(relation, terms, constant, reals))
            expected = _satisfiable(solver)
            checked += 1
            if accepted != expected:
                problems.append(f"seed {seed}, posting {term[0]} {terms} "
                                f"{constant}: port {accepted}, z3 {expected}")
            if not accepted or not expected:
                return problems, checked
        for terms, value, how in steps:
            expression = _expression(terms, variables)
            if value == "inf" or value == "sup":
                value = _optimum(bv.inf if value == "inf" else bv.sup,
                                 expression, trail)
            if how == "unify":
                accepted = _step(trail, lambda: unify(variables[terms[0][1]],
                                                      value, trail))
            else:
                accepted = _step(trail, lambda: nf.post_constraint(
                    ("=", expression, value), trail))
            solver.add(_z3_constraint("=", terms, value, reals))
            expected = _satisfiable(solver)
            checked += 1
            if accepted != expected:
                problems.append(f"seed {seed}, {terms} = {value} by {how}: "
                                f"port {accepted}, z3 {expected}")
            if not accepted or not expected:
                break
        return problems, checked
    finally:
        trail.defer = False


def _optimum(optimum, expression, trail):
    """The inf or sup of *expression* (0 where there is none), the store
    as it was."""
    mark = trail.mark()
    result = Var()
    found = optimum(expression, result, trail)
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


#: Seeds above 1500 where, with the check of D19 switched off, the port
#: accepts an unsatisfiable step (26 in 30,000 seeds in each mode: 15
#: equations, 7 posted bindings, 4 unifications; none below 1500).
_PINNED = (2352, 2621, 3241, 4931, 6270, 6550, 10910, 11321, 12722, 14265,
           16276, 16979, 19586, 19803, 20660, 22075, 22570, 23310, 23764,
           24239, 26397, 26490, 26904, 27211, 28042, 28706)


@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_binding_is_accepted_exactly_when_z3_finds_it_satisfiable(defer):
    problems, checked = run_fuzz(list(range(1500)) + list(_PINNED), defer)
    assert not problems, "\n".join(problems[:10])
    assert checked >= 10000, checked


@pytest.mark.skipif(os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
                    reason="set CLAUSAL_SLOW_TESTS=1 for the large seed count")
@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_binding_is_accepted_exactly_when_z3_finds_it_satisfiable_slow(defer):
    problems, checked = run_fuzz(range(1500, 30000), defer)
    assert not problems, "\n".join(problems[:10])


# ------------------------------------------------- the invariant the check uses

def basis_invariant_violations(component):
    """What strictly_satisfiable relies on, at the point it runs: the row
    of every bounded basis variable holds only nonbasic variables at an
    active bound, and every basis value is within its bounds.  A nonbasic
    variable without an active bound (its value an implicit 0, which can
    be outside its bounds) is then only in rows of unbounded variables,
    so the store without strictness has a point with it inside its own
    interval.  Returns the violations, as text."""
    from clausal.logic.clpq.arithmetic import add, compare
    violations = []
    members = component_all_variables(deref(component))
    for member in list_elements(members) if members is not None else []:
        variable = deref(member)
        if not is_var(variable):
            continue
        state = state_of(variable)
        if state is None or state.linear_form is None or state.bounds is None:
            continue
        form = state.linear_form
        kind = state.bounds.kind
        if independent(form, variable) or kind not in (
                BOUNDS_LOWER, BOUNDS_UPPER, BOUNDS_LOWER_UPPER):
            continue
        value = add(form.rest, form.constant)
        if kind != BOUNDS_UPPER and compare(value, state.bounds.lower) < 0:
            violations.append(f"{variable} below its lower bound")
        if kind != BOUNDS_LOWER and compare(value, state.bounds.upper) > 0:
            violations.append(f"{variable} above its upper bound")
        for term_variable, _ in form.terms:
            term_state = state_of(term_variable)
            if term_state is None or term_state.bounds is None \
                    or term_state.bounds.kind < BOUNDS_LOWER_ACTIVE:
                violations.append(f"{term_variable} in the row of {variable}"
                                  " has no active bound")
    return violations


def test_the_check_runs_where_its_invariant_holds(monkeypatch):
    # The invariant the check's argument (D19) and its two refusals on a
    # failed determine_active_decrease or decrease_step rest on.
    calls = []
    check = bv.strictly_satisfiable

    def checked(component, trail):
        calls.append(basis_invariant_violations(component))
        return check(component, trail)
    monkeypatch.setattr(bv, "strictly_satisfiable", checked)
    for defer in (False, True):
        run_fuzz(list(range(1000)) + list(_PINNED), defer)
    assert len(calls) >= 800, len(calls)
    bad = [violations for violations in calls if violations]
    assert not bad, bad[:3]


# ------------------------------------------------- goals woken by a binding

def _value(term):
    term = deref(term)
    return None if is_var(term) else Fraction(term)


@pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])
def test_a_frozen_goal_on_a_variable_a_binding_implies_runs(defer):
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
