"""The port's satisfiability with strict, non-strict, equal and not-equal
constraints, and bindings, against z3 (Task 15).

Two shapes, as the 2026-10-11 scripts had them:

* posts only: 3 to 12 constraints of le, lt, eq, ne over 2 to 6 variables;
* posts interleaved with 1 to 3 bindings, a variable to a small rational
  or two variables to each other (through the CLPQ_KEY hook).

The port's answer (every step succeeded, or one failed) must equal z3's
verdict on the conjunction, exactly.
"""
import random
from fractions import Fraction

import z3

from tests.clpq_port.fuzz._fuzz_common import (
    CASES, MODES, Var, at_goal, bind, new_trail, post, z3_store)
from clausal.logic.variables import unify


def constraints(rng, n, count, choices):
    rows = []
    for _ in range(count):
        a = [rng.choice(choices) for _ in range(n)]
        if not any(a):
            a[rng.randrange(n)] = 1
        rows.append((a, rng.choice(["le", "le", "lt", "lt", "eq", "ne"]),
                     rng.randint(-2, 2)))
    return rows


def posts_only(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 6)
    return n, [("c", row) for row in constraints(
        rng, n, rng.randint(3, 12), [0, 0, 1, -1, 2, -1])]


def with_bindings(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 5)
    steps = [("c", row) for row in constraints(
        rng, n, rng.randint(2, 8), [0, 0, 1, -1, 2])]
    for _ in range(rng.randint(1, 3)):
        if rng.random() < 0.3:
            step = ("u", rng.randrange(n), rng.randrange(n))
        else:
            step = ("b", rng.randrange(n),
                    Fraction(rng.randint(-4, 4), rng.choice([1, 1, 2])))
        steps.insert(rng.randint(0, len(steps)), step)
    return n, steps


def z3_verdict(n, steps):
    rows = [step[1] for step in steps if step[0] == "c"]
    solver, reals = z3_store(rows, n)
    for step in steps:
        if step[0] == "u":
            solver.add(reals[step[1]] == reals[step[2]])
        elif step[0] == "b":
            solver.add(reals[step[1]] == z3.Q(step[2].numerator, step[2].denominator))
    return solver.check() == z3.sat


def port_verdict(n, steps, defer):
    trail = new_trail(defer)
    variables = [Var() for _ in range(n)]
    for step in steps:
        if step[0] == "c":
            ok = post(trail, variables, step[1])
        elif step[0] == "u":
            ok = at_goal(trail, unify(variables[step[1]], variables[step[2]], trail))
        else:
            ok = bind(trail, variables[step[1]], step[2])
        if not ok:
            return False
    return True


def run(generate, defer, cases, salt):
    mismatches, satisfiable = [], 0
    for case in range(cases):
        n, steps = generate(salt * 100000 + case)
        want = z3_verdict(n, steps)
        satisfiable += want
        got = port_verdict(n, steps, defer)
        if got != want:
            mismatches.append((case, got, want, steps))
    return mismatches, satisfiable


@MODES
def test_posts_against_z3(defer):
    mismatches, satisfiable = run(posts_only, defer, CASES, 1)
    print(f"posts: {CASES} stores, {satisfiable} satisfiable")
    assert mismatches == []


@MODES
def test_posts_and_bindings_against_z3(defer):
    mismatches, satisfiable = run(with_bindings, defer, CASES, 2)
    print(f"posts and bindings: {CASES} stores, {satisfiable} satisfiable")
    assert mismatches == []
