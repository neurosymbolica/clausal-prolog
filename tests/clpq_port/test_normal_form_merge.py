# tests/clpq_port/test_normal_form_merge.py
"""The cost of nf.pl's merges in normal_form.py, and that the faster
comparison and insertion give exactly what the plain ones give.

compare_power_products and compare_bases compare two variables directly;
every other pair goes to _standard_order, which stays the reference.
"""
import random
from fractions import Fraction

import pytest

from clausal.logic.clpq import normal_form as nf
from clausal.logic.clpq.arithmetic import ONE, make_rational
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, unify
from clausal.pythonic_ast.nodes import Add, Mult


def q(numerator, denominator=1):
    return make_rational(numerator, denominator)


def _left_sum(variables):
    term = variables[0]
    for v in variables[1:]:
        term = Add(left=term, right=v)
    return term


def _right_sum(variables):
    term = variables[-1]
    for v in reversed(variables[:-1]):
        term = Add(left=v, right=term)
    return term


def _count_comparisons(monkeypatch, thunk):
    calls = [0]
    original = nf.compare_power_products

    def counting(first, second):
        calls[0] += 1
        return original(first, second)
    monkeypatch.setattr(nf, "compare_power_products", counting)
    result = thunk()
    monkeypatch.setattr(nf, "compare_power_products", original)
    return result, calls[0]


# ---------------------------------------------------------------- the comparison

def _random_base(rng, variables, depth=2):
    roll = rng.random()
    if depth and roll < 0.15:
        name = rng.choice(["sin", "abs", "min", "exp", "/"])
        arity = 1 if name in ("sin", "abs") else 2
        return nf.NonlinearBase(name, tuple(
            _random_normal_form(rng, variables, depth - 1)
            for _ in range(arity)))
    return rng.choice(variables)


def _random_powers(rng, variables, depth=2):
    return [(_random_base(rng, variables, depth), rng.choice([1, 1, 1, 2, -1]))
            for _ in range(rng.choice([0, 1, 1, 1, 2, 3]))]


def _random_normal_form(rng, variables, depth=1):
    return [nf.Monomial(q(rng.randint(-3, 3) or 1, rng.randint(1, 2)),
                        _random_powers(rng, variables, depth))
            for _ in range(rng.randint(0, 2))]


@pytest.mark.parametrize("seed", range(40))
def test_the_power_product_comparison_is_the_standard_order(seed):
    # Power products as nf.pl builds them, and some no merge would build
    # (unsorted, repeated bases): the comparison is _standard_order's on
    # every pair, bound bases included.
    rng = random.Random(seed)
    variables = [Var() for _ in range(4)]
    trail = Trail()
    bound = Var()
    assert unify(bound, 3, trail)
    pool = variables + [bound]
    products = [_random_powers(rng, pool) for _ in range(40)]
    mismatches = []
    for a in products:
        for b in products + [list(a)]:
            want = nf._standard_order(nf._POWER_PRODUCTS, a, b)
            got = nf.compare_power_products(a, b)
            if got != want:
                mismatches.append((a, b, want, got))
            want_bases = [nf._standard_order(nf._BASES, x, y)
                          for (x, _), (y, _) in zip(a, b)]
            got_bases = [nf.compare_bases(x, y) for (x, _), (y, _) in zip(a, b)]
            if got_bases != want_bases:
                mismatches.append(("bases", a, b, want_bases, got_bases))
    assert not mismatches, mismatches[:5]


def test_a_base_bound_to_a_non_number_raises_in_the_same_place():
    trail = Trail()
    x, y, bad = Var(), Var(), Var()
    assert unify(bad, "a", trail)
    cases = [([(x, 1), (bad, 1)], [(x, 1), (y, 1)]),     # reached: raises
             ([(x, 1), (bad, 1)], [(y, 1), (y, 1)]),     # decided before
             ([(bad, 1)], [(bad, 1)])]                   # the same base
    for a, b in cases:
        outcomes = []
        for compare in (nf.compare_power_products,
                        lambda a, b: nf._standard_order(nf._POWER_PRODUCTS,
                                                        a, b)):
            try:
                outcomes.append(compare(a, b))
            except LogicException as error:
                outcomes.append(("raised", str(error.term)))
        assert outcomes[0] == outcomes[1], (a, b, outcomes)
