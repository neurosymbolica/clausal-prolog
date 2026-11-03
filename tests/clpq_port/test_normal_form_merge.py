# tests/clpq_port/test_normal_form_merge.py
"""The cost of nf.pl's merges in normal_form.py, and that the faster
comparison and insertion give exactly what the plain ones give.

compare_power_products and compare_bases compare two variables directly;
every other pair goes to _standard_order, which stays the reference.
normal_form's sums place a single monomial by binary search; the
reference here is nf.pl's two-way merge, normal_form_add.
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


# ---------------------------------------------------------------- cost

@pytest.mark.parametrize("shape", [_left_sum, _right_sum])
def test_a_long_sum_compares_each_new_term_a_few_times(monkeypatch, shape):
    # nf.pl merges the k-term sum so far with each new term: a left-leaning
    # sum of n variables made n^2/2 comparisons.  Placing the one new term
    # by binary search makes O(log k) each, and the end it most often
    # falls at is tried first.
    n = 2_000
    variables = [Var() for _ in range(n)]
    norm, calls = _count_comparisons(
        monkeypatch, lambda: nf.normal_form(shape(variables)))
    assert [m.powers[0][0] for m in norm] == variables
    assert calls <= 3 * n, calls


def test_a_sum_in_random_order_compares_n_log_n_times(monkeypatch):
    n = 2_000
    variables = [Var() for _ in range(n)]
    shuffled = variables[:]
    random.Random(7).shuffle(shuffled)
    norm, calls = _count_comparisons(
        monkeypatch, lambda: nf.normal_form(_left_sum(shuffled)))
    assert [m.powers[0][0] for m in norm] == variables
    assert calls <= n * 14, calls


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


# ---------------------------------------------------------------- the insertion

def _same(want, got, inputs):
    """The same monomials: the same objects where nf.pl's merge keeps one
    of *inputs*, and where it makes one, a new one with an equal
    coefficient and the very same powers list."""
    if len(want) != len(got):
        return False
    kept = {id(m) for m in inputs}
    for a, b in zip(want, got):
        if a is b:
            continue
        if id(a) in kept or id(b) in kept or a.coefficient != b.coefficient \
                or a.powers is not b.powers:
            return False
    return True


@pytest.mark.parametrize("seed", range(60))
def test_inserting_one_monomial_is_the_two_way_merge(seed):
    # A normal form built by normal_form, and one monomial: a variable
    # already in it (its coefficient adds, to zero sometimes), one that is
    # not, the constant, a power, a product, a non-linear base.
    rng = random.Random(seed)
    variables = [Var() for _ in range(12)]
    terms = [Mult(left=rng.choice([1, 2, -1, Fraction(1, 2)]), right=v)
             for v in rng.sample(variables, rng.randint(2, 12))]
    terms += [rng.choice([5, 0])]
    rng.shuffle(terms)
    base = nf.normal_form(_left_sum(terms))
    singles = []
    for monomial in base:                       # the same powers: they add
        singles.append(nf.Monomial(nf.negate_rational(monomial.coefficient),
                                   monomial.powers))
        singles.append(nf.Monomial(q(3), list(monomial.powers)))
    for v in variables:
        singles.append(nf.Monomial(q(-2), [(v, 1)]))
        singles.append(nf.Monomial(ONE, [(v, 2)]))
        singles.append(nf.Monomial(ONE, [(v, 1), (variables[-1], 1)]))
        singles.append(nf.Monomial(
            ONE, [(nf.NonlinearBase("sin", ([nf.Monomial(ONE, [(v, 1)])],)),
                   1)]))
    singles.append(nf.Monomial(q(7), []))
    failures = []
    for single in singles:
        for first, second in (([single], base), (base, [single])):
            want = nf.normal_form_add(first, second)
            got = nf._normal_form_add_fresh(first, second)
            if not _same(want, got, first + second):
                failures.append((first, second, want, got))
    assert not failures, failures[:3]
