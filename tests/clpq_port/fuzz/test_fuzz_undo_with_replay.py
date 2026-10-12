"""Undo with replay (Task 15).

A bounded base store over 2 to 4 variables, then 1 to 4 more steps (le,
lt, eq posts, sometimes a binding) after a trail mark, then the undo back
to the mark.  The store must then answer exactly as the base store
replayed on a fresh trail: the same bindings, the same sup and inf of two
random objectives, and the same strictness: each optimum is probed with
{Objective = Optimum}, which holds iff the optimum is attained, so a strict
bound that came back as =< after the undo shows.

A base the port rejects must be one z3 calls unsatisfiable, and more than
half the cases must have a base to undo to.
"""
import random
from fractions import Fraction

import z3

from tests.clpq_port.fuzz._fuzz_common import (
    CASES, MODES, Var, at_goal, bind, expression, holzbaur, new_trail, post, value_of,
    z3_store)


def generate(seed):
    rng = random.Random(seed)
    n = rng.randint(2, 4)

    def row():
        k = rng.random()
        relation = "eq" if k < .2 else ("lt" if k < .4 else "le")
        return ([rng.randint(-3, 3) for _ in range(n)], relation, rng.randint(-5, 8))

    base = [row() for _ in range(rng.randint(1, 4))]
    for j in range(n):
        base.append(([1 if i == j else 0 for i in range(n)], "le", rng.randint(3, 9)))
        base.append(([-1 if i == j else 0 for i in range(n)], "le", rng.randint(3, 9)))
    extra = []
    for _ in range(rng.randint(1, 4)):
        if rng.random() < .25:
            extra.append(("b", rng.randrange(n), Fraction(rng.randint(-3, 3))))
        else:
            extra.append(("c", row()))
    objectives = [[rng.randint(-3, 3) for _ in range(n)] for _ in range(2)]
    for objective in objectives:
        objective[0] = objective[0] or 1
    return n, base, extra, objectives


def probe(trail, variables, objectives):
    """sup and inf of each objective, and whether each is attained."""
    out = []
    for objective in objectives:
        for optimum in (holzbaur.sup, holzbaur.inf):
            result = Var()
            if not optimum(expression(objective, variables), result, trail):
                out.append(None)
                continue
            value = Fraction(value_of(result))
            mark = trail.mark()
            attained = at_goal(trail, holzbaur.q_eq(
                expression(objective, variables), value, trail))
            trail.undo(mark)
            out.append((value, bool(attained)))
    return out


def bindings(variables):
    return [value_of(v) for v in variables]


def run(defer, cases):
    mismatches, checked = [], 0
    for seed in range(cases):
        n, base, extra, objectives = generate(seed)
        trail = new_trail(defer)
        variables = [Var() for _ in range(n)]
        if not all(post(trail, variables, row) for row in base):
            solver, _ = z3_store(base, n)
            if solver.check() == z3.sat:            # a satisfiable base rejected
                mismatches.append((seed, "base rejected", base))
            continue
        before = bindings(variables)
        mark = trail.mark()
        for step in extra:
            ok = (post(trail, variables, step[1]) if step[0] == "c"
                  else bind(trail, variables[step[1]], step[2]))
            if not ok:
                break
        trail.undo(mark)
        after = bindings(variables)
        got = probe(trail, variables, objectives)
        replay_trail = new_trail(defer)
        replay = [Var() for _ in range(n)]
        assert all(post(replay_trail, replay, row) for row in base)
        want = probe(replay_trail, replay, objectives)
        checked += 1
        if after != before or got != want:
            mismatches.append((seed, before, after, got, want))
    return mismatches, checked


@MODES
def test_undo_leaves_the_store_as_a_replay_of_the_base(defer):
    mismatches, checked = run(defer, CASES)
    print(f"undo: {CASES} cases, {checked} with a satisfiable base")
    assert mismatches == []
    # A rejected base is checked against z3 above, but checks no undo; the
    # floor keeps the test from passing on stores it never undid (273 of
    # 300 and 8116 of 9000 bases are satisfiable).
    assert checked > CASES // 2
