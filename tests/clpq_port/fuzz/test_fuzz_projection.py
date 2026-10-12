"""Projection, feasibility and membership (Task 15).

A random store of le and eq constraints over 2 to 4 variables, posted in
two halves with a trail mark between them.  Checked:

* feasibility: the port accepts the whole store iff z3 says it is
  satisfiable;
* membership: for 40 grid points, binding every variable to the point
  succeeds iff the point satisfies the store;
* projection: dump_q on a random subset of the variables gives a residual
  that z3 proves EQUIVALENT to the store with the other variables
  existentially closed (tests/clpq_oracle.py _equivalent);
* undo: after undoing the second half, membership answers by the first
  half alone.

A first half the port rejects must be one z3 calls unsatisfiable, and
more than half the stores must be projected.
"""
import random
from fractions import Fraction

import z3

from tests.clpq_oracle import _equivalent
from tests.clpq_port.fuzz._fuzz_common import (
    CASES, MODES, Var, bind, holzbaur, new_trail, post, value_of, z3_store)
from clausal.logic.variables import is_var, deref

GRID = [Fraction(k, 2) for k in range(-8, 9)]


def generate(rng):
    n = rng.randint(2, 4)
    rows = []
    for _ in range(rng.randint(2, 7)):
        k = rng.random()
        a = [0] * n
        if k < .35:
            a[rng.randrange(n)] = 1 if rng.random() < .5 else -1
            rows.append((a, "le", rng.randint(-2, 3)))
        else:
            for i in range(n):
                a[i] = rng.choice([0, 0, 1, -1, 2, -2, 3])
            if not any(a):
                a[0] = 1
            rows.append((a, "eq" if k < .6 else "le", rng.randint(-3, 4)))
    return n, rows


def holds(rows, point):
    for a, relation, b in rows:
        total = sum(Fraction(c) * x for c, x in zip(a, point))
        if relation == "le" and total > b:
            return False
        if relation == "eq" and total != b:
            return False
    return True


def member(trail, variables, point):
    mark = trail.mark()
    ok = True
    for variable, value in zip(variables, point):
        bound = value_of(variable)
        if bound is None:
            if not bind(trail, variable, value):
                ok = False
                break
        elif Fraction(bound) != value:
            ok = False
            break
    trail.undo(mark)
    return ok


def as_text(rows, names):
    """The store as residual strings over *names*."""
    out = []
    for a, relation, b in rows:
        left = " + ".join(f"({c})*{names[i]}" for i, c in enumerate(a) if c) or "0"
        out.append(f"{left} {'=<' if relation == 'le' else '='} {b}")
    return out


def run(defer, cases):
    mismatches, projected = [], 0
    for seed in range(cases):
        rng = random.Random(seed)
        n, rows = generate(rng)
        trail = new_trail(defer)
        variables = [Var() for _ in range(n)]
        split = rng.randint(0, len(rows))
        if not all(post(trail, variables, row) for row in rows[:split]):
            solver, _ = z3_store(rows[:split], n)
            if solver.check() == z3.sat:            # a satisfiable half rejected
                mismatches.append(("first half rejected", seed, rows[:split]))
            continue
        mark = trail.mark()
        accepted = all(post(trail, variables, row) for row in rows[split:])
        solver, _ = z3_store(rows, n)
        if accepted != (solver.check() == z3.sat):
            mismatches.append(("feasibility", seed, accepted))
        if accepted:
            for _ in range(40):
                point = tuple(rng.choice(GRID) for _ in range(n))
                if member(trail, variables, point) != holds(rows, point):
                    mismatches.append(("membership", seed, point))
                    break
            chosen = [i for i in range(n) if rng.random() < .6] or [0]
            names = [f"X{i}" if i in chosen else f"_X{i}" for i in range(n)]
            by_id = {}
            targets = []
            known = {}
            for i in chosen:
                term = deref(variables[i])
                if is_var(term):
                    by_id[term._id] = names[i]
                    targets.append(term)
                else:
                    known[names[i]] = Fraction(term)
            residual = holzbaur.dump_q(targets, trail,
                                       lambda v: by_id[deref(v)._id]) if targets else []
            projected += 1
            ok, why = _equivalent(list(residual), as_text(rows, names), known)
            if not ok:
                mismatches.append(("projection", seed, residual, why))
        trail.undo(mark)
        for _ in range(20):
            point = tuple(rng.choice(GRID) for _ in range(n))
            if member(trail, variables, point) != holds(rows[:split], point):
                mismatches.append(("undo", seed, point))
                break
    return mismatches, projected


@MODES
def test_projection_feasibility_membership_and_undo(defer):
    mismatches, projected = run(defer, CASES)
    print(f"projection: {CASES} stores, {projected} projected")
    assert mismatches == []
    # A rejected store is checked against z3 above, but projects nothing;
    # the floor keeps the test from passing on stores it never projected
    # (205 of 300 and 5988 of 9000 stores are satisfiable).
    assert projected > CASES // 2
