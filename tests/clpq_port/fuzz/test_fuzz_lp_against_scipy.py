"""The port's sup/inf/maximize/minimize against scipy's HiGHS (Task 15).

Random LPs of 2 to 5 variables with bounds, inequalities and sometimes an
equation, in three shapes (normal, degenerate right-hand sides, no
equation).  For each objective and each of sup, inf, maximize, minimize the
port's answer (a value, unbounded, or infeasible at the post) must equal
HiGHS's within 1e-6.  Each value the port gives is also checked EXACTLY
with z3: the store reaches it and nothing goes past it.  After maximize or
minimize the store must imply objective = optimum (sup = inf = optimum);
the port leaves an optimal face free (bv.pl), so a point is not checked.

The one known disagreement that is not the port's: HiGHS presolve can call
an unbounded LP infeasible.  Each such case is confirmed with z3 (the store
satisfiable and the objective unbounded) and counted, never skipped
unchecked.
"""
import random
from fractions import Fraction

import numpy as np
import z3
from scipy.optimize import linprog

from tests.clpq_port.fuzz._fuzz_common import (
    CASES, MODES, Var, deref, expression, holzbaur, new_trail, post, value_of,
    z3_store, z3_sum)

OPERATIONS = [("sup", "max"), ("inf", "min"), ("maximize", "max"),
              ("minimize", "min")]


def generate(rng, shape):
    n = rng.randint(2, 5)
    bounds = []
    for _ in range(n):
        k = rng.random()
        low = rng.randint(-3, 2)
        if k < .25:
            bounds.append((None, None))
        elif k < .45:
            bounds.append((low, None))
        elif k < .6:
            bounds.append((None, low))
        elif k < .7:
            bounds.append((low, low))
        else:
            bounds.append((low, low + rng.randint(0, 4)))
    inequalities, equations = [], []
    for _ in range(rng.randint(1, 6)):
        a = [rng.randint(-3, 3) for _ in range(n)]
        if any(a):
            inequalities.append((a, rng.randint(-2, 8) if shape != "degenerate" else 0))
    if shape != "no_equation" and rng.random() < .4:
        a = [rng.randint(-2, 2) for _ in range(n)]
        if any(a):
            equations.append((a, rng.randint(-3, 3)))
    objective = [rng.randint(-3, 3) for _ in range(n)]
    if not any(objective):
        objective[0] = 1
    return n, bounds, inequalities, equations, objective


def constraints_of(n, bounds, inequalities, equations):
    """The LP as (coefficients, relation, constant) rows, in posting order."""
    rows = []
    for i, (low, high) in enumerate(bounds):
        unit = [1 if j == i else 0 for j in range(n)]
        if low is not None:
            rows.append(([-c for c in unit], "le", -low))
        if high is not None:
            rows.append((unit, "le", high))
    rows += [(a, "eq", b) for a, b in equations]
    rows += [(a, "le", b) for a, b in inequalities]
    return rows


def highs(n, bounds, inequalities, equations, objective, sense):
    c = np.array(objective, float) * (-1 if sense == "max" else 1)
    result = linprog(c, A_ub=[a for a, _ in inequalities] or None,
                     b_ub=[b for _, b in inequalities] or None,
                     A_eq=[a for a, _ in equations] or None,
                     b_eq=[b for _, b in equations] or None,
                     bounds=bounds, method="highs")
    if result.status == 2:
        return "infeasible"
    if result.status == 3:
        return "unbounded"
    if result.status != 0:
        return ("status", result.status)
    return -result.fun if sense == "max" else result.fun


def z3_unbounded(rows, n, objective, sense):
    """z3, exactly: the store is satisfiable and the objective unbounded."""
    solver, reals = z3_store(rows, n)
    if solver.check() != z3.sat:
        return False
    optimizer = z3.Optimize()
    optimizer.add(solver.assertions())
    target = z3_sum(objective, reals)
    handle = optimizer.maximize(target) if sense == "max" else optimizer.minimize(target)
    if optimizer.check() != z3.sat:
        return False
    bound = optimizer.upper(handle) if sense == "max" else optimizer.lower(handle)
    return "oo" in str(bound)


def z3_confirms_optimum(rows, n, objective, sense, value):
    """z3, exactly: the store reaches *value* and nothing goes past it."""
    solver, reals = z3_store(rows, n)
    target = z3_sum(objective, reals)
    exact = z3.Q(value.numerator, value.denominator)
    solver.push()
    solver.add(target == exact)
    reached = solver.check() == z3.sat
    solver.pop()
    solver.add(target > exact if sense == "max" else target < exact)
    return reached and solver.check() == z3.unsat


def port(rows, n, objective, operation, defer):
    """The port's answer: a Fraction, 'unbounded' or 'infeasible'; and,
    after maximize/minimize, whether the store implies the optimum."""
    trail = new_trail(defer)
    variables = [Var() for _ in range(n)]
    for row in rows:
        if not post(trail, variables, row):
            return "infeasible", True
    result = Var()
    if not getattr(holzbaur, operation)(expression(objective, variables), result, trail):
        return "unbounded", True
    value = Fraction(deref(result))
    implied = True
    if operation in ("maximize", "minimize"):
        for probe in (holzbaur.sup, holzbaur.inf):
            r = Var()
            got = expression(objective, variables)
            if not probe(got, r, trail) or Fraction(value_of(r)) != value:
                implied = False
    return value, implied


def run(shape, defer, cases):
    mismatches, presolve = [], []
    for seed in range(cases):
        rng = random.Random(seed)
        n, bounds, inequalities, equations, objective = generate(rng, shape)
        rows = constraints_of(n, bounds, inequalities, equations)
        for operation, sense in OPERATIONS:
            want = highs(n, bounds, inequalities, equations, objective, sense)
            got, implied = port(rows, n, objective, operation, defer)
            if isinstance(got, Fraction):
                same = (not isinstance(want, (str, tuple))
                        and abs(float(got) - want) < 1e-6
                        and z3_confirms_optimum(rows, n, objective, sense, got)
                        and implied)
            else:
                same = got == want
                if not same and want == "infeasible" and got == "unbounded" \
                        and z3_unbounded(rows, n, objective, sense):
                    presolve.append((seed, operation))
                    same = True
            if not same:
                mismatches.append((seed, operation, got, want, implied))
    return mismatches, presolve


@MODES
def test_lp_normal_against_highs(defer):
    mismatches, presolve = run("normal", defer, CASES)
    print(f"normal: {CASES} LPs x 4 operations, presolve cases {len(presolve)}")
    assert mismatches == []


@MODES
def test_lp_degenerate_against_highs(defer):
    mismatches, presolve = run("degenerate", defer, CASES)
    print(f"degenerate: {CASES} LPs x 4 operations, presolve cases {len(presolve)}")
    assert mismatches == []


@MODES
def test_lp_without_equations_against_highs(defer):
    mismatches, presolve = run("no_equation", defer, CASES)
    print(f"no_equation: {CASES} LPs x 4 operations, presolve cases {len(presolve)}")
    assert mismatches == []
