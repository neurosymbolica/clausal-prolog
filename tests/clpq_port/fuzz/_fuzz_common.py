"""What the four Task 15 fuzzers share.

The fuzzers run the PORT through the legacy-compatible API
(``clausal.logic.clpq.holzbaur``, the names ``CLAUSAL_CLPQ=holzbaur``
exports), imported directly so that they test the port whichever solver the
switch selects.  Each runs in two modes: bare (``trail.defer`` False) and
under a driver (``trail.defer`` True, the goals the hooks queue run at the
goal boundary after each step, as ``pending.run_first``).

They rewrite the reviewer scripts of 2026-10-11 (an LP check against scipy,
a strictness check against z3, an undo check with a replay, a projection
check), which drove legacy's internals, for the port.

``CLPQ_FUZZ=full`` runs 9,000 cases per fuzzer and mode; the default is 300.
"""
import os

import pytest
import z3

from clausal.logic.clpq import holzbaur
from clausal.logic.pending import run_first
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.terms import Add, Mult

CASES = 9000 if os.environ.get("CLPQ_FUZZ") == "full" else 300

MODES = pytest.mark.parametrize("defer", [False, True], ids=["bare", "driver"])

POST = {"le": holzbaur.q_le, "lt": holzbaur.q_lt, "eq": holzbaur.q_eq,
        "ne": holzbaur.q_ne}

Z3_RELATION = {"le": lambda a, b: a <= b, "lt": lambda a, b: a < b,
               "eq": lambda a, b: a == b, "ne": lambda a, b: a != b}


def expression(coefficients, variables):
    """sum(c*x) as the API's cells; 0 when every coefficient is 0."""
    result = None
    for coefficient, variable in zip(coefficients, variables):
        if coefficient:
            term = Mult(left=coefficient, right=variable)
            result = term if result is None else Add(left=result, right=term)
    return 0 if result is None else result


def new_trail(defer):
    trail = Trail()
    trail.defer = defer
    return trail


def at_goal(trail, succeeded):
    """A step's result, then the goal boundary: the goals it queued run to
    their first answer (a no-op bare, where nothing is queued)."""
    return bool(succeeded) and run_first(trail)


def post(trail, variables, constraint):
    """One (coefficients, relation, constant) constraint, then the boundary."""
    coefficients, relation, constant = constraint
    return at_goal(trail, POST[relation](expression(coefficients, variables),
                                         constant, trail))


def bind(trail, variable, value):
    """`X = value` (an int when integral), then the boundary."""
    if getattr(value, "denominator", 1) == 1:
        value = int(value)
    return at_goal(trail, unify(variable, value, trail))


def z3_sum(coefficients, variables):
    return z3.Sum([c * x for c, x in zip(coefficients, variables) if c] or
                  [z3.RealVal(0)])


def z3_store(constraints, n):
    """A solver holding *constraints* over Reals x0..x{n-1}, and those Reals."""
    reals = [z3.Real(f"x{i}") for i in range(n)]
    solver = z3.Solver()
    for coefficients, relation, constant in constraints:
        solver.add(Z3_RELATION[relation](z3_sum(coefficients, reals), constant))
    return solver, reals


def value_of(term):
    """A bound term's value, or None for a variable."""
    term = deref(term)
    return None if is_var(term) else term


__all__ = ["CASES", "MODES", "POST", "Var", "at_goal", "bind", "deref",
           "expression", "holzbaur", "is_var", "new_trail", "post",
           "value_of", "z3_store", "z3_sum"]
