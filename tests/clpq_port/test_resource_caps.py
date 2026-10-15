# tests/clpq_port/test_resource_caps.py
"""DEVIATIONS.md D24, ruling D51: the port's resource caps.

1.3.3 has no limit on four kinds of work: the nodes of a bb_inf search (a
store with no integer point branches for ever), the work of those nodes
(it grows with the store), the terms a projection writes (Fourier-Motzkin
is exponential) and the terms and coefficient bits of an expansion
(`(Y + 1)^N` costs about N^3, a product of k sums makes 2^k terms).  The
port caps each and raises `error(resource_error(R), _)` past the cap,
never failing or answering in part.  For each cap: the D24 repro raises
within seconds, a case at its cap answers, the same case one under its
cap raises, and raising the cap lets it through.

The in-process tests call the adapter whatever CLAUSAL_CLPQ says and set
the caps through clausal.logic.clpq.limits.  The flags and catch/3 run in
a `clausal` subprocess under CLAUSAL_CLPQ=holzbaur, where the flags exist.
The sandbox's refusal of the flags is in tests/test_sandbox.py.
"""
import os
import pathlib
import random
import signal
import subprocess
import sys
import threading
from fractions import Fraction
from math import comb

import pytest

import clausal.logic.clpq as clpq
from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq import limits
from clausal.logic.clpq import normal_form as nf
from clausal.logic.exceptions import LogicException
from clausal.logic.variables import Trail, Var, deref, is_var, walk
from clausal.pythonic_ast.nodes import Add, ArithEq, Div, IsoIntPow, Mult

ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture
def caps():
    """limits.set_limit, every cap put back after the test."""
    saved = {resource: limits.limit(resource) for resource in limits.DEFAULTS}
    yield limits.set_limit
    for resource, value in saved.items():
        limits.set_limit(resource, value)


@pytest.fixture
def used(monkeypatch):
    """The most of each cap a test used: cap -> count.  Read where a count
    is checked, and where a meter closes (the back substitution checks
    only past the cap)."""
    most = {}
    check = limits.check
    stop = limits.stop

    def recording(cap, count, what):
        most[cap] = max(most.get(cap, 0), count)
        return check(cap, count, what)

    def closing(token):
        meter = limits._METER.get()
        if meter is not None:
            most[meter.cap] = max(most.get(meter.cap, 0), meter.used)
        return stop(token)
    monkeypatch.setattr(limits, "check", recording)
    monkeypatch.setattr(limits, "stop", closing)
    return most


class _Hang(BaseException):
    pass


def _within(seconds, call):
    """*call*, or _Hang after *seconds*."""
    def alarm(*_):
        raise _Hang()
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(seconds)
    try:
        return call()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _raised(call):
    with pytest.raises(LogicException) as caught:
        call()
    return caught.value.term


def _is_resource_error(term, resource):
    """`error(resource_error(R), _)`, Scryer's shape: the context is a
    variable."""
    return (type(term) is tuple and len(term) == 3 and term[0] == "error"
            and term[1] == ("resource_error", resource)
            and type(deref(term[2])).__name__.endswith("Var"))


def _sum(coefficients, variables):
    result = None
    for coefficient, variable in zip(coefficients, variables):
        if coefficient:
            term = Mult(left=coefficient, right=variable)
            result = term if result is None else Add(left=result, right=term)
    return result


# ---------------------------------------------------------------- nodes

def _no_integer_point():
    """D24 High 1: `{X >= 0, Y >= 0, 2*X - 2*Y =:= 1}, bb_inf([X, Y], X, I)`."""
    trail, x, y = Trail(), Var(), Var()
    assert h.q_ge(x, 0, trail) and h.q_ge(y, 0, trail)
    assert h.q_eq(_sum([2, -2], [x, y]), 1, trail)
    return h.bb_inf([x, y], x, Var(), trail)


def _integer_optimum():
    """min X + Y with 3X + 5Y >= 17 and 7X - 4Y =< 9 over the integers:
    a search of a few nodes; the infimum."""
    trail, x, y, infimum = Trail(), Var(), Var(), Var()
    assert h.q_ge(x, 0, trail) and h.q_ge(y, 0, trail)
    assert h.q_ge(_sum([3, 5], [x, y]), 17, trail)
    assert h.q_le(_sum([7, -4], [x, y]), 9, trail)
    assert h.bb_inf([x, y], _sum([1, 1], [x, y]), infimum, trail)
    return deref(infimum)


def test_bb_inf_without_an_integer_point_raises_clpq_nodes(caps):
    caps("clpq_nodes", 2000)
    term = _within(60, lambda: _raised(_no_integer_point))
    assert _is_resource_error(term, "clpq_nodes")


def test_bb_inf_without_an_integer_point_raises_at_the_default_cap():
    assert limits.limit("clpq_nodes") == limits.DEFAULTS["clpq_nodes"]
    term = _within(120, lambda: _raised(_no_integer_point))
    assert _is_resource_error(term, "clpq_nodes")


def test_bb_inf_answers_at_its_node_cap_and_raises_under_it(
        caps, monkeypatch):
    # A node is a pass of branch_and_bound_loop: one reoptimize each.
    from clausal.logic.clpq import branch_and_bound
    passes = []
    reoptimize = branch_and_bound.branch_and_bound_reoptimize

    def counting(objective, trail):
        passes.append(1)
        return reoptimize(objective, trail)
    monkeypatch.setattr(branch_and_bound, "branch_and_bound_reoptimize",
                        counting)
    expected = _integer_optimum()
    nodes = len(passes)
    assert nodes > 2                    # the search branches
    caps("clpq_nodes", nodes)
    assert _integer_optimum() == expected
    caps("clpq_nodes", nodes - 1)
    assert _is_resource_error(_raised(_integer_optimum), "clpq_nodes")
    caps("clpq_nodes", nodes)           # raising the cap lets it through
    assert _integer_optimum() == expected


# ---------------------------------------------------------------- projection

#: D24 Medium 3, the security review's probe `proj.py 101 5 1`: 15 random
#: `=<` constraints on 5 variables (random.Random(101)), projected onto
#: the first two.  1.3.3's answer has 13 constraints, after 7 to 13 s.
_SEED_101 = [
    ([1, 3, -2, 1, -1], 8), ([-3, 2, 1, -2, 1], 4), ([-1, 0, 2, 3, -2], 6),
    ([0, -3, -1, -2, -2], 2), ([0, 3, 1, -1, -2], 8), ([3, -1, -2, 2, 3], 7),
    ([0, -2, -3, 0, 0], 5), ([-2, -3, 2, 3, 1], 6), ([2, 3, -1, 0, 3], 7),
    ([-2, 0, -3, 0, 2], 7), ([-3, 3, 0, -2, 1], 2), ([-1, 3, -3, -1, 2], 6),
    ([-3, -1, 1, 3, -2], 1), ([0, -2, -1, -3, 3], 3), ([0, 2, 2, 3, -1], 8)]

#: A smaller projection: 6 of those constraints on 4 variables.
_SMALL = [(row[:4], bound) for row, bound in _SEED_101[:6]]


def _project(rows):
    trail = Trail()
    variables = [Var() for _ in rows[0][0]]
    for coefficients, bound in rows:
        assert h.q_le(_sum(coefficients, variables), bound, trail)
    names = {variables[0]._id: "X1", variables[1]._id: "X2"}
    return h.dump_q(variables[:2], trail, lambda v: names[v._id])


_SLOW = pytest.mark.skipif(
    os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
    reason="about 10 to 30 s, set CLAUSAL_SLOW_TESTS=1")


def _seeded(seed, n):
    """The security review's probe store: 3n random `=<` constraints on n
    variables (coefficients in -3..3, bounds in 1..9)."""
    rnd = random.Random(seed)
    rows = []
    for _ in range(3 * n):
        coefficients = [rnd.randint(-3, 3) for _ in range(n)]
        rows.append((coefficients, rnd.randint(1, 9)))
    return rows


def test_the_seeded_rows_are_the_d24_probe():
    assert _seeded(101, 5) == _SEED_101


@_SLOW
def test_the_d24_projection_answers_at_the_default_cap():
    # Ruling D51: the defaults refuse no query that 1.3.3 answers in
    # reasonable time.  Seed 101 at n = 5 (7 to 13 s) answers.
    assert limits.limit("clpq_projection") \
        == limits.DEFAULTS["clpq_projection"]
    assert len(_within(120, lambda: _project(_SEED_101))) == 13


@_SLOW
def test_a_projection_at_n_6_raises_at_the_default_cap():
    # Seed 101 at n = 6 runs past two minutes in 1.3.3.
    term = _within(120, lambda: _raised(lambda: _project(_seeded(101, 6))))
    assert _is_resource_error(term, "clpq_projection")


def test_the_d24_projection_raises_under_a_lower_cap(caps):
    caps("clpq_projection", 100_000)
    term = _within(60, lambda: _raised(lambda: _project(_SEED_101)))
    assert _is_resource_error(term, "clpq_projection")


def test_a_projection_answers_at_its_cap_and_raises_under_it(caps, used):
    expected = _project(_SMALL)
    assert expected
    rows = used["clpq_projection"]
    caps("clpq_projection", rows)
    assert _project(_SMALL) == expected
    caps("clpq_projection", rows - 1)
    assert _is_resource_error(_raised(lambda: _project(_SMALL)),
                              "clpq_projection")
    caps("clpq_projection", rows)       # raising the cap lets it through
    assert _project(_SMALL) == expected


def test_derived_constraints_are_charged_before_they_are_made(
        caps, monkeypatch):
    # Fourier-Motzkin charges an elimination's cross product before it
    # makes a row of it: a cap that the first charge passes raises from
    # that charge, not from a later pivot.
    charges = []
    charge = limits.charge
    meters = []

    def recording(units, caps_charged):
        if "clpq_projection" in caps_charged:
            meter = limits._METER.get()
            while meter is not None and meter.cap != "clpq_projection":
                meter = meter.parent
            charges.append((sys._getframe(2).f_code.co_name, units,
                            meter.used + units))
        return charge(units, caps_charged)
    monkeypatch.setattr(limits, "charge", recording)
    _project(_SMALL)
    first = next(entry for entry in charges
                 if entry[0] == "fourier_motzkin_eliminate_internal"
                 and entry[1] > 0)
    caps("clpq_projection", first[2] - 1)
    with pytest.raises(LogicException) as caught:
        _project(_SMALL)
    assert _is_resource_error(caught.value.term, "clpq_projection")
    names = []
    frame = caught.tb
    while frame is not None:
        names.append(frame.tb_frame.f_code.co_name)
        frame = frame.tb_next
    assert names[-5:-1] == ["fourier_motzkin_eliminate_internal",
                            "charge_projection", "recording", "charge"], \
        names


def test_the_projection_counter_stops_with_the_projection(caps):
    caps("clpq_projection", 1)
    _raised(lambda: _project(_SMALL))
    assert not limits.metering()
    # Pivots outside a projection are not counted.
    trail, x, y = Trail(), Var(), Var()
    assert h.q_le(_sum([1, 1], [x, y]), 4, trail)
    assert h.q_ge(y, 0, trail)
    value = Var()
    assert h.sup(x, value, trail) and deref(value) == 4


# ---------------------------------------------------------------- power

def _power(base, exponent):
    trail, x = Trail(), Var()
    return h.q_eq(x, IsoIntPow(left=base, right=exponent), trail)


def test_a_huge_power_raises_clpq_expansion_at_once():
    # D24 Medium 4: {X = (Y + 1)^(10^7)} did not finish.
    term = _within(10, lambda: _raised(lambda: _power(Add(left=Var(), right=1),
                                                      10 ** 7)))
    assert _is_resource_error(term, "clpq_expansion")


def test_a_power_answers_at_its_cap_and_raises_under_it(caps):
    # (Y + 1)^N has N + 1 terms.
    caps("clpq_expansion", 201)
    assert _power(Add(left=Var(), right=1), 200)
    caps("clpq_expansion", 200)
    assert _is_resource_error(
        _raised(lambda: _power(Add(left=Var(), right=1), 200)), "clpq_expansion")
    # A negative exponent expands the same power first.
    assert _is_resource_error(
        _raised(lambda: _power(Add(left=Var(), right=1), -200)), "clpq_expansion")
    caps("clpq_expansion", 201)             # raising the cap lets it through
    assert _power(Add(left=Var(), right=1), -200)


def test_the_power_count_is_the_terms_of_the_expansion(caps):
    # (Y + Z + W)^N has binomial(N + 2, 2) terms: 66 at N = 10.
    def cube_sum():
        return _power(Add(left=Add(left=Var(), right=Var()), right=Var()), 10)
    caps("clpq_expansion", 66)
    assert cube_sum()
    caps("clpq_expansion", 65)
    assert _is_resource_error(_raised(cube_sum), "clpq_expansion")


def test_a_power_of_one_term_is_one_term(caps):
    # A monomial's power is one term, whatever the exponent; its
    # coefficient's bits still count (below).
    caps("clpq_expansion", 1)
    assert _power(Mult(left=2, right=Var()), 50)


def test_the_power_count_is_exact_for_sums_of_more_terms(caps):
    # power_size builds binomial(N + T - 1, T - 1) a factor at a time and
    # stops early only past the cap: at the cap it is exact.
    for count in range(2, 6):
        norm = nf.normal_form(_sum([1] * count, [Var() for _ in range(count)]))
        for exponent in range(2, 9):
            expected = comb(exponent + count - 1, count - 1)
            caps("clpq_expansion", expected)
            assert nf.power_size(exponent, norm)[0] == expected
            limits.charge_expansion(*nf.power_size(exponent, norm), "test")
            caps("clpq_expansion", expected - 1)
            with pytest.raises(LogicException):
                limits.charge_expansion(*nf.power_size(exponent, norm),
                                        "test")


def test_big_coefficients_raise_on_their_bits(caps):
    # D24 F4: (10^1000*Y + 1)^2000 has 2001 terms but took 46 s and
    # 1.7 GB.  Its coefficients' bits are counted before it expands.
    big = Add(left=Mult(left=10 ** 1000, right=Var()), right=1)
    term = _within(10, lambda: _raised(lambda: _power(big, 2000)))
    assert _is_resource_error(term, "clpq_expansion")
    terms, bits = nf.power_size(30, nf.normal_form(big))
    assert terms == 31 and bits == 31 * 30 * (3321 + 1)
    # The larger estimate: each term as the largest coefficient, exact
    # log2 (30 * log2(2 * 10^1000)) ...
    largest = nf.largest_coefficient_bits(30, nf.normal_form(big))
    assert terms * int(largest) > bits
    bits = terms * limits.coefficient_charge(largest)
    # ... and 10^1000*Y, a product with a big coefficient: its 3321 bits
    bits += int(nf.largest_log2(nf.normal_form(10 ** 1000)))
    caps("clpq_expansion_bits", bits)
    assert _power(big, 30)
    caps("clpq_expansion_bits", bits - 1)
    assert _is_resource_error(_raised(lambda: _power(big, 30)),
                              "clpq_expansion")


def test_a_power_of_a_monomial_with_coefficient_1_makes_no_bits():
    # Review N3: Y^(10^8) is one monomial, 1^N; it answers at once.
    assert _within(10, lambda: _power(Var(), 10 ** 8))
    assert nf.power_size(10 ** 8, nf.normal_form(Var())) == (1, 0)


def test_a_power_of_a_monomial_counts_its_coefficient_bits(caps):
    # (2^64*Y)^(10^7) builds a coefficient of 640,000,000 bits.
    big = Mult(left=2 ** 64, right=Var())
    term = _within(10, lambda: _raised(lambda: _power(big, 10 ** 7)))
    assert _is_resource_error(term, "clpq_expansion")
    terms, bits = nf.power_size(1000, nf.normal_form(big))
    assert (terms, bits) == (1, 64_000)
    bits += 64                  # 2^64*Y, a product with a big coefficient
    caps("clpq_expansion_bits", bits)
    assert _power(big, 1000)
    caps("clpq_expansion_bits", bits - 1)
    assert _is_resource_error(_raised(lambda: _power(big, 1000)),
                              "clpq_expansion")


def test_a_power_s_count_includes_its_multinomial_bits():
    # (Y + Z)^10: 11 terms, each coefficient under 2^10 (binomials), and
    # the base's coefficients 1: the bits are the multinomial's alone
    # (review N5b: dropping them went unnoticed).
    norm = nf.normal_form(Add(left=Var(), right=Var()))
    assert nf.power_size(10, norm) == (11, 11 * 10)
    norm = nf.normal_form(Add(left=Add(left=Var(), right=Var()),
                              right=Var()))
    assert nf.power_size(10, norm) == (66, 66 * 10 * 2)


def test_one_huge_coefficient_raises_on_its_own_bits():
    # Review R2: one integer of n bits costs about n^1.6 to build, so
    # under the total bits cap (3*Y)^(10^8) took 131 s, (Y/3)^(10^8)
    # 133 s and (3^1000*Y)^120000 ran past 150 s.  Their largest
    # coefficient is checked before it is built.
    for base, exponent in [(Mult(left=3, right=Var()), 10 ** 8),
                           (Div(left=Var(), right=3), 10 ** 8),
                           (Mult(left=7, right=Var()), 3 * 10 ** 7),
                           (Mult(left=3 ** 1000, right=Var()), 120_000)]:
        term = _within(10, lambda: _raised(lambda: _power(base, exponent)))
        assert _is_resource_error(term, "clpq_expansion")
        assert nf.largest_coefficient_bits(exponent, nf.normal_form(base)) \
            > limits.DEFAULTS["clpq_coefficient_bits"]


def test_a_huge_power_of_a_number_raises_on_its_bits():
    # Review R2: 3^(10^8) is one integer of 158,496,250 bits too.
    term = _within(10, lambda: _raised(lambda: _power(3, 10 ** 8)))
    assert _is_resource_error(term, "clpq_expansion")
    term = _within(10, lambda: _raised(lambda: _power(3, -(10 ** 8))))
    assert _is_resource_error(term, "clpq_expansion")
    assert _power(1, 10 ** 8) and _power(-1, 10 ** 8 + 1)
    # An exponent past the float range: no OverflowError on the estimate.
    assert _is_resource_error(_raised(lambda: _power(3, 10 ** 400)),
                              "clpq_expansion")
    assert _is_resource_error(
        _raised(lambda: _power(Mult(left=3, right=Var()), 10 ** 400)),
        "clpq_expansion")
    assert _power(1, 10 ** 400) and _power(Var(), 10 ** 400)


def test_a_coefficient_answers_at_its_cap_and_raises_under_it(caps):
    # (3*Y)^1000: one coefficient of log2(3^1000) = 1584.96 bits.
    base = Mult(left=3, right=Var())
    bits = nf.largest_coefficient_bits(1000, nf.normal_form(base))
    assert 1584 < bits < 1585
    caps("clpq_coefficient_bits", 1585)
    assert _power(base, 1000)
    assert _power(base, -1000)
    caps("clpq_coefficient_bits", 1584)
    assert _is_resource_error(_raised(lambda: _power(base, 1000)),
                              "clpq_expansion")
    assert _is_resource_error(_raised(lambda: _power(base, -1000)),
                              "clpq_expansion")
    assert _is_resource_error(_raised(lambda: _power(3, 1000)),
                              "clpq_expansion")
    caps("clpq_coefficient_bits", 1585)     # raising the cap lets it through
    assert _power(3, 1000)


def test_the_ruled_powers_answer_at_the_default_caps():
    # Ruling D51 (review N4): (Y + 1)^9999 and Y^(10^8) answer; so do
    # (10^1000*Y + 1)^240 and a coefficient of a million bits.
    assert _within(30, lambda: _power(Add(left=Var(), right=1), 9999))
    assert _within(10, lambda: _power(Var(), 10 ** 8))
    assert _within(30, lambda: _power(
        Add(left=Mult(left=10 ** 1000, right=Var()), right=1), 240))
    assert _within(30, lambda: _power(Mult(left=3, right=Var()), 10 ** 6))


def _root(exponent, value):
    """{Y^exponent = value}: (the answer, Y)."""
    trail, y = Trail(), Var()
    return h.q_eq(IsoIntPow(left=y, right=exponent), value, trail), y


def test_a_root_s_power_raises_on_its_bits(caps):
    # Review R2b: {Y^(1/10^8) = 3} solved Y = 3^(10^8) exactly through
    # nonlinear_invertible, unchecked: 131 s (132 s for -1/10^8).  That
    # power is checked before it is built, as any power of a number is.
    for numerator in (1, -1):
        exponent = Div(left=numerator, right=10 ** 8)
        term = _within(10, lambda: _raised(lambda: _root(exponent, 3)))
        assert _is_resource_error(term, "clpq_expansion")
    # Y^(1/1000) = 3 builds 3^1000, 1584.96 bits.
    caps("clpq_coefficient_bits", 1585)
    answered, y = _root(Div(left=1, right=1000), 3)
    assert answered and deref(y) == 3 ** 1000
    answered, y = _root(Div(left=-1, right=1000), 3)
    assert answered and deref(y) == Fraction(1, 3 ** 1000)
    caps("clpq_coefficient_bits", 1584)
    for numerator in (1, -1):
        assert _is_resource_error(
            _raised(lambda: _root(Div(left=numerator, right=1000), 3)),
            "clpq_expansion")


def test_a_costly_coefficient_charges_its_bits_squared():
    # Review R2c: past limits.COSTLY_BITS a coefficient charges the total
    # bits * bits / COSTLY_BITS, its bits up to it.
    costly = limits.COSTLY_BITS
    assert limits.coefficient_charge(1584.96) == 1584
    assert limits.coefficient_charge(costly) == costly
    assert limits.coefficient_charge(2 * costly) == 4 * costly
    # At the defaults the total admits one coefficient at the coefficient
    # cap, not two (review R2c: sixteen were admitted, in 76 s).
    one = limits.coefficient_charge(limits.DEFAULTS["clpq_coefficient_bits"])
    assert one <= limits.DEFAULTS["clpq_expansion_bits"] < 2 * one


def _costly_bits(monkeypatch, bits):
    """limits.COSTLY_BITS at *bits*, for scaled-down cases."""
    monkeypatch.setattr(limits, "COSTLY_BITS", bits)


def test_powers_under_the_coefficient_cap_are_charged_their_cost(
        caps, monkeypatch):
    # Review R2c: sixteen powers of (3*Y)^12000000, each under the
    # coefficient cap, were admitted in 76 s.  Scaled down: (3*Y)^1000
    # charges its coefficient's exact 1584 bits (power_size's floor
    # counts 1000), and past COSTLY_BITS = 1000 their cost, 2509.
    def powers(count):
        total = IsoIntPow(left=Mult(left=3, right=Var()), right=1000)
        for _ in range(count - 1):
            total = Add(left=total,
                        right=IsoIntPow(left=Mult(left=3, right=Var()),
                                        right=1000))
        return h.q_eq(Var(), total, Trail())
    caps("clpq_expansion_bits", 4000)
    _costly_bits(monkeypatch, 1000)
    assert powers(1)
    assert _is_resource_error(_raised(lambda: powers(2)), "clpq_expansion")
    _costly_bits(monkeypatch, 10 ** 9)      # their bits alone: 3168
    assert powers(2)
    assert _is_resource_error(_raised(lambda: powers(3)), "clpq_expansion")


def test_powers_of_numbers_are_charged_to_the_total(caps, monkeypatch):
    # Review R2c: a power of a number was checked against the coefficient
    # cap alone, so 3^12000000 * ... was bounded by nothing in its number
    # of factors (four took 59 s).  3^1000 charges 1584 bits, 2509 past
    # COSTLY_BITS = 1000.
    def powers(count, combine):
        total = IsoIntPow(left=3, right=1000)
        for _ in range(count - 1):
            total = combine(left=total, right=IsoIntPow(left=3, right=1000))
        return h.q_eq(Var(), total, Trail())
    caps("clpq_expansion_bits", 4000)
    _costly_bits(monkeypatch, 1000)
    for combine in (Add, Mult):
        assert powers(1, combine)
        assert _is_resource_error(_raised(lambda: powers(2, combine)),
                                  "clpq_expansion")
    _costly_bits(monkeypatch, 10 ** 9)
    assert powers(2, Add)                   # their bits alone: 3168
    assert _is_resource_error(_raised(lambda: powers(3, Add)),
                              "clpq_expansion")


def test_a_product_of_big_numbers_raises_on_its_coefficient(caps):
    # Review R2c: a monomial times a monomial was checked against no cap:
    # 3^1000 * 3^1000 builds one coefficient of 3169.9 bits.
    def product():
        return h.q_eq(Var(), Mult(left=Mult(left=3 ** 1000, right=3 ** 1000),
                                  right=Var()), Trail())

    def quotient():
        return h.q_eq(Var(), Div(left=Mult(left=3 ** 1000, right=Var()),
                                 right=3 ** 1000), Trail())
    caps("clpq_coefficient_bits", 3170)
    assert product() and quotient()
    caps("clpq_coefficient_bits", 3169)
    assert _is_resource_error(_raised(product), "clpq_expansion")
    assert _is_resource_error(_raised(quotient), "clpq_expansion")


def test_a_product_of_two_big_factors_is_charged_their_cost(
        caps, monkeypatch, used):
    # Two big factors cost more than their bits (limits.coefficient_charge);
    # a big one times a small one costs its bits.
    _costly_bits(monkeypatch, 1000)
    big = 3 ** 1000                                     # 1584.96 bits
    assert h.q_eq(Var(), Mult(left=Mult(left=big, right=big), right=Var()),
                  Trail())
    # big * big: 3169 bits, charged 3169^2 // 1000; then times Y: 3169
    assert used["clpq_expansion_bits"] == 3169 ** 2 // 1000 + 3169
    used.clear()
    assert h.q_eq(Var(), Mult(left=Mult(left=big, right=7), right=Var()),
                  Trail())
    # big * 7: 1587 bits; times Y: 1587
    assert used["clpq_expansion_bits"] == 2 * 1587


def test_a_chain_of_products_of_a_huge_number_raises_at_the_defaults():
    # Each product of a 19,000,000-bit number with a small one costs its
    # bits and is charged them: ten fit under the default total, an
    # eleventh raises, at once (no product is past the coefficient cap).
    huge = 1 << 19_000_000
    term = huge
    for factor in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        term = Mult(left=term, right=factor)
    term = _within(30, lambda: _raised(
        lambda: h.q_eq(Var(), Mult(left=term, right=Var()), Trail())))
    assert _is_resource_error(term, "clpq_expansion")
    # The control: two terms with that coefficient answer.
    assert _within(30, lambda: h.q_eq(
        Var(), Add(left=Mult(left=huge, right=Var()),
                   right=Mult(left=huge, right=Var())), Trail()))


def test_a_repaired_product_of_big_numbers_raises_on_its_coefficient(caps):
    # The repair multiplies a bound factor in: A*B*Y, then A and B bound
    # to 3^1000, builds a coefficient of 3169.9 bits.
    def bound_late():
        trail, a, b, y = Trail(), Var(), Var(), Var()
        assert h.q_eq(Var(), Mult(left=Mult(left=a, right=b), right=y),
                      trail)
        return h.q_eq(a, 3 ** 1000, trail) and h.q_eq(b, 3 ** 1000, trail)
    caps("clpq_coefficient_bits", 3170)
    assert bound_late()
    caps("clpq_coefficient_bits", 3169)
    assert _is_resource_error(_raised(bound_late), "clpq_expansion")


@_SLOW
def test_near_cap_powers_raise_on_the_total_at_the_defaults():
    # Review R2c at scale: (3*Y)^12600000 alone answers (a ruled case,
    # about 4 s on the box), and two powers of (3*Y)^12000000 raise
    # before the second is built.
    assert _within(120, lambda: _power(Mult(left=3, right=Var()),
                                       12_600_000))
    two = Add(left=IsoIntPow(left=Mult(left=3, right=Var()),
                             right=12_000_000),
              right=IsoIntPow(left=Mult(left=3, right=Var()),
                              right=12_000_000))
    term = _within(120, lambda: _raised(lambda: h.q_eq(Var(), two, Trail())))
    assert _is_resource_error(term, "clpq_expansion")


# ---------------------------------------------------------------- products

def _product(k):
    """(A1 + B1) * (A2 + B2) * ... * (Ak + Bk), as nodes: 2^k terms."""
    variables = [Var() for _ in range(2 * k)]
    product = Add(left=variables[0], right=variables[1])
    for index in range(1, k):
        product = Mult(left=product,
                       right=Add(left=variables[2 * index],
                                 right=variables[2 * index + 1]))
    return product


def _post_product(k):
    return h.q_eq(Var(), _product(k), Trail())


def test_a_product_of_sums_raises_at_the_default_cap():
    # D24 F3: 18 factors (2^18 terms) ran past 120 s and 1 GB.
    term = _within(30, lambda: _raised(lambda: _post_product(18)))
    assert _is_resource_error(term, "clpq_expansion")


def test_a_product_of_14_sums_answers_at_the_default_cap():
    # Ruling D51 (review N4): 14 sums, 32,764 terms over the steps, answer.
    assert _within(60, lambda: _post_product(14))


def test_a_product_answers_at_its_cap_and_raises_under_it(caps, used):
    assert _post_product(6)
    terms = used["clpq_expansion"]
    assert terms == sum(2 ** index for index in range(2, 7))   # cumulative
    caps("clpq_expansion", terms)
    assert _post_product(6)
    caps("clpq_expansion", terms - 1)
    assert _is_resource_error(_raised(lambda: _post_product(6)),
                              "clpq_expansion")


def _big_product(k, coefficient):
    """(c*A1 + B1) * ... * (c*Ak + Bk)."""
    variables = [Var() for _ in range(2 * k)]

    def factor(index):
        return Add(left=Mult(left=coefficient, right=variables[2 * index]),
                   right=variables[2 * index + 1])
    product = factor(0)
    for index in range(1, k):
        product = Mult(left=product, right=factor(index))
    return product


def test_a_product_counts_its_coefficient_bits(caps, used):
    # Each step multiplies two sums with big coefficients: their bits are
    # charged before the product is made (review N5, product bits).
    coefficient = 10 ** 300
    assert h.q_eq(Var(), _big_product(4, coefficient), Trail())
    bits = used["clpq_expansion_bits"]
    assert bits > 4 * 2 * 3 * 996      # the 4-sum product's own coefficients
    caps("clpq_expansion_bits", bits)
    assert h.q_eq(Var(), _big_product(4, coefficient), Trail())
    caps("clpq_expansion_bits", bits - 1)
    assert _is_resource_error(
        _raised(lambda: h.q_eq(Var(), _big_product(4, coefficient), Trail())),
        "clpq_expansion")


# ---------------------------------------------------------------- repair

def _sums_with_late_exponents(k, coefficient=1):
    """X = (c*A1 + B1)^N1 * ... * (c*Ak + Bk)^Nk posted with every Ni
    unbound, as (trail, [N1, ..., Nk]): binding Ni to 1 wakes the delayed
    equation, whose repair multiplies one more sum in (review N1)."""
    trail = Trail()
    exponents = [Var() for _ in range(k)]
    product = None
    for exponent in exponents:
        first = Var() if coefficient == 1 \
            else Mult(left=coefficient, right=Var())
        factor = IsoIntPow(left=Add(left=first, right=Var()), right=exponent)
        product = factor if product is None else Mult(left=product,
                                                      right=factor)
    assert h.q_eq(Var(), product, trail)
    return trail, exponents


def _bind_all(trail, exponents):
    from clausal.logic.variables import unify
    for exponent in exponents:
        if not unify(exponent, 1, trail):
            return False
    return True


def test_a_repair_charges_a_monomial_times_a_sum(caps):
    # The i-th binding multiplies 2^(i-1) monomials by a sum of 2: each
    # wake-up's repair charges 2^i terms.  Six sums: at most 64 in one
    # wake-up, 126 over all six.
    trail, exponents = _sums_with_late_exponents(6)
    assert _bind_all(trail, exponents)
    caps("clpq_expansion", 126)
    trail, exponents = _sums_with_late_exponents(6)
    assert _bind_all(trail, exponents)
    caps("clpq_expansion", 125)
    trail, exponents = _sums_with_late_exponents(6)
    assert _is_resource_error(
        _raised(lambda: _bind_all(trail, exponents)), "clpq_expansion")


def test_a_repair_charges_its_coefficients_bits(caps, used):
    # Review N5b: the repair's charge counts the bits of the sum it
    # multiplies in, not its terms alone.
    coefficient = 10 ** 300
    trail, exponents = _sums_with_late_exponents(3, coefficient)
    assert _bind_all(trail, exponents)
    bits = used["clpq_expansion_bits"]
    assert bits >= 2 * 996          # a sum of two, one coefficient 10^300
    caps("clpq_expansion_bits", bits)
    trail, exponents = _sums_with_late_exponents(3, coefficient)
    assert _bind_all(trail, exponents)
    caps("clpq_expansion_bits", bits - 1)
    trail, exponents = _sums_with_late_exponents(3, coefficient)
    assert _is_resource_error(
        _raised(lambda: _bind_all(trail, exponents)), "clpq_expansion")


def test_a_constraint_s_count_persists_across_its_wake_ups(caps):
    # A cap each wake-up fits alone (the last one charges 64) still
    # raises: the delayed constraint carries its count to the next
    # wake-up (limits.CARRIED).
    caps("clpq_expansion", 64)
    trail, exponents = _sums_with_late_exponents(6)
    assert _is_resource_error(
        _raised(lambda: _bind_all(trail, exponents)), "clpq_expansion")
    assert limits.CARRIED.get() is None


# ---------------------------------------------------------------- work

def _wide_no_integer_point(width, seed=1, bound=lambda index: 10 ** 6,
                           difference=1):
    """D24 F2: the store with no integer point, and *width* more variables
    each tied to X and Y: every node's pivots rewrite every row.  The
    i-th of them is bounded by *bound(i)*; with *difference* even, there
    is an integer point."""
    rng = random.Random(seed)
    trail, x, y = Trail(), Var(), Var()
    others = [Var() for _ in range(width)]
    assert h.q_ge(x, 0, trail) and h.q_ge(y, 0, trail)
    assert h.q_eq(_sum([2, -2], [x, y]), difference, trail)
    for index, z in enumerate(others):
        assert h.q_ge(z, 0, trail)
        assert h.q_le(_sum([1, rng.randint(-3, 3) or 1, rng.randint(1, 3)],
                           [z, x, y]), bound(index), trail)
        assert h.q_ge(_sum([1, -1], [z, x]), -5, trail)
    return lambda: h.bb_inf([x, y] + others, x, Var(), trail)


def test_a_wide_search_raises_clpq_work_at_the_default_cap():
    # Under the node cap, 20 more variables took 79 s and 490 MB.
    search = _wide_no_integer_point(20)
    term = _within(90, lambda: _raised(search))
    assert _is_resource_error(term, "clpq_work")


def test_bb_inf_answers_at_its_work_cap_and_raises_under_it(caps, used):
    expected = _integer_optimum()
    work = used["clpq_work"]
    assert work > 0
    caps("clpq_work", work)
    assert _integer_optimum() == expected
    caps("clpq_work", work - 1)
    assert _is_resource_error(_raised(_integer_optimum), "clpq_work")


def test_an_equation_in_a_search_is_charged(caps):
    # back_substitute_collect_bindings (an equation's substitution) charges
    # an open meter as back_substitute_variables does.
    from clausal.logic.clpq import bounded_simplex
    calls = []
    original = bounded_simplex.back_substitute_collect_bindings

    def counting(*arguments):
        calls.append(limits._METER.get().used)
        result = original(*arguments)
        calls[-1] = limits._METER.get().used - calls[-1]
        return result
    bounded_simplex.back_substitute_collect_bindings = counting
    trail, x, y, z = Trail(), Var(), Var(), Var()
    token = limits.start("clpq_work", "test")
    try:
        assert h.q_le(_sum([1, 1, 1], [x, y, z]), 9, trail)
        assert h.q_ge(_sum([1, -1], [x, y]), 1, trail)
        assert h.q_eq(_sum([1, 2], [x, z]), 4, trail)
    finally:
        limits.stop(token)
        bounded_simplex.back_substitute_collect_bindings = original
    assert calls and all(charged > 0 for charged in calls), calls


def test_a_back_substitution_charges_the_rows_it_reads(caps):
    # The walk over the component costs whether or not a row holds the
    # variable (D24 F2: in a wide store most rows do not): a substitution
    # of a variable no row holds still charges a unit per row read.
    from clausal.logic.clpq import bounded_simplex
    from clausal.logic.clpq.attributes import state_of
    from clausal.logic.clpq.linear_forms import LinearForm
    from clausal.logic.clpq.arithmetic import ONE, ZERO
    trail, targets, _ = _small_store()
    members = bounded_simplex.all_variables(targets[0])
    rows = 0
    node = deref(members)
    while type(node).__name__ == "ListCell":
        state = state_of(deref(node.head))
        if state is not None and state.linear_form is not None:
            rows += 1
        node = deref(node.rest)
    assert rows > 2
    absent = Var()
    token = limits.start("clpq_work", "test")
    try:
        bounded_simplex.back_substitute_variables(
            members, absent, LinearForm(ZERO, ONE, []), trail)
        assert limits._METER.get().used == rows
    finally:
        limits.stop(token)


def test_row_size_counts_each_64_bits_of_a_coefficient():
    from clausal.logic.clpq import bounded_simplex
    from clausal.logic.clpq.linear_forms import LinearForm
    small = LinearForm((3, 1), (0, 1), [(Var(), (5, 7)), (Var(), (1, 1))])
    big = LinearForm((3, 1), (0, 1), [(Var(), (2 ** 200, 7)),
                                      (Var(), (1, 1))])
    big_constant = LinearForm((2 ** 130, 1), (0, 1), [(Var(), (1, 1))])
    # a unit for the row, and one for each value plus one per 64 bits
    assert bounded_simplex.row_size(small) == 1 + 2 + 2
    assert bounded_simplex.row_size(big) == 1 + 2 + 2 + (201 + 3) // 64
    assert bounded_simplex.row_size(big_constant) == 1 + 2 + 1 + (131 + 1) // 64
    assert bounded_simplex.small_row_size(small) == 5
    assert bounded_simplex._row_sizer(small) is bounded_simplex.small_row_size
    assert bounded_simplex._row_sizer(big) is bounded_simplex.row_size


def test_a_big_substitution_charges_each_row_s_size(caps):
    # A substitution with a coefficient past 64 bits charges every row it
    # writes by row_size (its coefficients' words), not the small count.
    from clausal.logic.clpq import bounded_simplex
    from clausal.logic.clpq.attributes import state_of
    from clausal.logic.clpq.linear_forms import LinearForm
    from clausal.logic.clpq.arithmetic import ONE, ZERO
    trail, targets, _ = _small_store()
    members = bounded_simplex.all_variables(targets[0])
    variable = None
    node = deref(members)
    while type(node).__name__ == "ListCell":
        state = state_of(deref(node.head))
        if state is not None and state.linear_form is not None \
                and state.linear_form.terms:
            variable = state.linear_form.terms[0][0]
            break
        node = deref(node.rest)
    assert variable is not None
    form = LinearForm(ZERO, (2 ** 300, 1), [(Var(), ONE)])
    token = limits.start("clpq_work", "test")
    try:
        bounded_simplex.back_substitute_variables(members, variable, form,
                                                  trail)
        used = limits._METER.get().used
    finally:
        limits.stop(token)
    rows, sizes = 0, 0
    node = deref(members)
    while type(node).__name__ == "ListCell":
        state = state_of(deref(node.head))
        node = deref(node.rest)
        if state is not None and state.linear_form is not None:
            rows += 1
            if state.linear_form.rest[0].bit_length() > 64:     # rewritten
                sizes += bounded_simplex.row_size(state.linear_form)
    assert sizes > 0 and used == rows + sizes


def _huge_bound(digits):
    """Review R1's probe (bigrow.py): the i-th bound a rational with a
    numerator of *digits* digits and a denominator of twice as many
    trits, so every row's constant is huge while every pivot row's
    coefficients are small."""
    return lambda index: Fraction(10 ** digits + 2 * index + 1,
                                  3 ** (2 * digits) + 7 * index)


def _charged_rows(monkeypatch):
    """The units the back substitution charges the bb_inf searches,
    summed as each search's meter closes: a list of one.  It adds to the
    meter in place (review N2), so the meter is what is read."""
    total = [0]
    stop = limits.stop

    def closing(token):
        meter = limits._METER.get()
        if meter is not None and meter.cap == "clpq_work":
            total[0] += meter.used
        return stop(token)
    monkeypatch.setattr(limits, "stop", closing)
    return total


def test_rows_with_huge_constants_are_charged_their_size(caps, monkeypatch):
    # Review R1: a small substitution charged only for itself, so rows
    # holding 2,000-digit constants were charged as small ones and the
    # search ran 96 s to the work cap.  The same search charges each such
    # row its constant's words now: 12.9 times the small store's units
    # over the same 30 nodes (2.7 times before, from the few big
    # substitutions).
    total = _charged_rows(monkeypatch)
    caps("clpq_nodes", 30)
    assert _is_resource_error(_raised(_wide_no_integer_point(10)),
                              "clpq_nodes")
    small = total[0]
    total[0] = 0
    assert _is_resource_error(
        _raised(_wide_no_integer_point(10, bound=_huge_bound(2000))),
        "clpq_nodes")
    assert total[0] > 8 * small, (small, total[0])


def test_a_search_over_huge_constants_raises_clpq_work_quickly(caps):
    # Review R1: under a work cap of 200,000 the 2,000-digit store raises
    # within seconds, as the same store with small bounds does.
    caps("clpq_work", 200_000)
    search = _wide_no_integer_point(20, bound=_huge_bound(2000))
    term = _within(60, lambda: _raised(search))
    assert _is_resource_error(term, "clpq_work")


def test_a_feasible_search_over_huge_constants_answers():
    # The control: the same shape with an integer point, every bound
    # about 3 * 10^6 but a ratio of 2,000-digit integers, answers at the
    # default caps.
    def bound(index):
        return Fraction(3 * 10 ** 2000 + 2 * index + 1, 10 ** 1994)
    search = _wide_no_integer_point(20, bound=bound, difference=2)
    assert _within(60, search)


def test_an_equation_s_substitution_charges_rows_with_huge_constants(caps):
    # Review round 4 (Low): back_substitute_collect_bindings, an
    # equation's substitution, reads each written row's constant and rest
    # too: a small substitution into rows holding 600-digit constants
    # charges each its row_size, not 3 + terms.
    from clausal.logic.clpq import bounded_simplex
    from clausal.logic.clpq.attributes import state_of
    from clausal.logic.clpq.linear_forms import LinearForm
    from clausal.logic.clpq.arithmetic import ONE, ZERO
    trail = Trail()
    variables = [Var() for _ in range(4)]
    huge = _huge_bound(600)
    for index in range(4):       # an equation's row keeps its constant
        assert h.q_eq(_sum([1, 2, 1], [variables[index],
                                       variables[(index + 1) % 4], Var()]),
                      huge(index), trail)
    members = bounded_simplex.all_variables(variables[0])

    def rows():
        found = []
        node = deref(members)
        while type(node).__name__ == "ListCell":
            state = state_of(deref(node.head))
            node = deref(node.rest)
            if state is not None and state.linear_form is not None:
                found.append(state.linear_form)
        return found
    before = rows()
    # a variable two big rows hold, replaced by another the store orders
    variable, other = before[0].terms[0][0], before[0].terms[1][0]
    assert sum(any(deref(term) is deref(variable) for term, _ in row.terms)
               for row in before) >= 2
    form = LinearForm(ZERO, ZERO, [(other, ONE)])      # small
    token = limits.start("clpq_work", "test")
    try:
        assert bounded_simplex.back_substitute_collect_bindings(
            members, variable, form, [], trail)
        used = limits._METER.get().used
    finally:
        limits.stop(token)
    after = rows()
    assert len(after) == len(before)
    written = [row for row, old in zip(after, before) if row is not old]
    sizes = sum(bounded_simplex.row_size(row) for row in written)
    small = sum(3 + len(row.terms) for row in written)
    assert len(written) >= 2 and sizes > 2 * small, (sizes, small)
    assert used == len(after) + sizes


def test_small_row_size_reads_the_constant_and_the_rest():
    # Review R1: the fast path reads a written row's constant and rest,
    # and charges row_size once the magnitudes of their numerators and
    # denominators sum to 2^64 (each then fits in 64 bits).
    from clausal.logic.clpq import bounded_simplex
    from clausal.logic.clpq.linear_forms import LinearForm
    terms = [(Var(), (5, 7)), (Var(), (1, 1))]
    for constant, rest in [((10 ** 600, 3 ** 1200), (0, 1)),
                           ((0, 1), (-(2 ** 300), 1)),
                           ((2 ** 200, 1), (1, 2 ** 100))]:
        form = LinearForm(constant, rest, terms)
        assert bounded_simplex.small_row_size(form) \
            == bounded_simplex.row_size(form) > 5
    edge = LinearForm((-(2 ** 62), 2 ** 62), (2 ** 62, 2 ** 62 - 1), terms)
    assert bounded_simplex.small_row_size(edge) == 5    # 2^64 - 1: small
    past = LinearForm((-(2 ** 62), 2 ** 62), (2 ** 62, 2 ** 62), terms)
    assert bounded_simplex.small_row_size(past) \
        == bounded_simplex.row_size(past)


def test_fourier_motzkin_charges_rows_as_wide_as_their_widest_source(
        monkeypatch):
    # Each elimination charges its cross product's count times one more
    # than the widest row it comes from, worked out just before.
    from clausal.logic.clpq import fourier_motzkin
    events = []
    cardinality = fourier_motzkin.cross_product_cardinality
    widest = fourier_motzkin._widest
    charge = limits.charge_projection

    def counting(occurrences, count):
        result = cardinality(occurrences, count)
        events.append(("count", result))
        return result

    def measuring(occurrences):
        result = widest(occurrences)
        events.append(("width", result))
        return result

    def recording(units):
        if sys._getframe(1).f_code.co_name \
                == "fourier_motzkin_eliminate_internal":
            events.append(("charge", units))
        return charge(units)
    monkeypatch.setattr(fourier_motzkin, "cross_product_cardinality",
                        counting)
    monkeypatch.setattr(fourier_motzkin, "_widest", measuring)
    monkeypatch.setattr(limits, "charge_projection", recording)
    _project(_SMALL)
    checked = 0
    for index, (kind, units) in enumerate(events):
        if kind != "charge":
            continue
        count = next(v for k, v in reversed(events[:index]) if k == "count")
        width = next(v for k, v in reversed(events[:index]) if k == "width")
        assert units == count * (width + 1)
        checked += width > 0 and count > 0
    assert checked


# ---------------------------------------------------------------- meters

def _small_store():
    """The _SMALL store, posted: (trail, the two targets, a namer)."""
    trail = Trail()
    variables = [Var() for _ in _SMALL[0][0]]
    for coefficients, bound in _SMALL:
        assert h.q_le(_sum(coefficients, variables), bound, trail)
    names = {variables[0]._id: "X1", variables[1]._id: "X2"}
    return trail, variables[:2], lambda v: names[v._id]


def test_a_nested_call_is_charged_to_the_call_around_it(caps):
    # A projection under an open search meter charges both: the outer cap
    # bounds the whole.  Only the projection runs under the outer meter.
    trail, targets, name = _small_store()
    expected = h.dump_q(targets, trail, name)
    token = limits.start("clpq_work", "outer")
    try:
        assert h.dump_q(targets, trail, name) == expected
        outer = limits._METER.get().used
    finally:
        limits.stop(token)
    assert outer > 0
    caps("clpq_work", outer - 1)
    token = limits.start("clpq_work", "outer")
    try:
        assert _is_resource_error(
            _raised(lambda: h.dump_q(targets, trail, name)), "clpq_work")
    finally:
        limits.stop(token)
    assert not limits.metering()


def test_each_thread_counts_its_own_calls(caps, used):
    # D24 F5: four threads, each projection under the cap alone, never
    # raise for each other's work.
    _project(_SMALL)
    caps("clpq_projection", used["clpq_projection"])
    switch = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    outcomes = []

    def worker():
        for _ in range(10):
            try:
                _project(_SMALL)
                outcomes.append("ok")
            except LogicException as error:
                outcomes.append(repr(error.term))
    threads = [threading.Thread(target=worker) for _ in range(4)]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sys.setswitchinterval(switch)
    assert outcomes == ["ok"] * 40


def test_set_limit_refuses_what_is_not_a_positive_int(caps):
    for value in (0, -1, 1.5, True, "10"):
        with pytest.raises(ValueError):
            caps("clpq_nodes", value)


# ---------------------------------------------------------------- Prolog

_PROGRAM = """\
:- module(caps_probe, [noint/1, project/1, big/2, post/1, caught/2,
                       power/3, product/2, rep/1]).
:- use_module(library(clpq)).
noint(I) :- {X >= 0, Y >= 0, 2*X - 2*Y =:= 1}, bb_inf([X, Y], X, I).
big(X1, X2) :-
    {X1 + 3*X2 - 2*X3 + X4 =< 8, -3*X1 + 2*X2 + X3 - 2*X4 =< 4,
     -X1 + 2*X3 + 3*X4 =< 6, -3*X2 - X3 - 2*X4 =< 2,
     3*X2 + X3 - X4 =< 8, 3*X1 - X2 - 2*X3 + 2*X4 =< 7}.
project(C) :- big(X1, X2), dump_q([X1, X2], C).
post(C) :- 'clpq.rational'(C).
caught(G, R) :- catch(G, error(resource_error(R), _), true).
power(N, X, Y) :- E = (Y + 1)^N, {X = E}.
product(K, X) :- length(L, K), sums(L, P), {X = P}.
sums([A], (A + _)).
sums([A, B|T], (A + _) * P) :- sums([B|T], P).
late([], 1, []).
late([A, B|T], (A + B)^N * R, [N|Ns]) :- late(T, R, Ns).
ones([]).
ones([1|T]) :- ones(T).
rep(K) :- K2 is 2*K, length(L, K2), late(L, P, Ns), {_ = P}, ones(Ns).
"""


def _program(directory):
    path = directory / "caps_probe.pl"
    path.write_text(_PROGRAM)
    return path


def _clausal(tmp_path, goal, solver="holzbaur"):
    env = dict(os.environ, CLAUSAL_CLPQ=solver, CLAUSAL_PL_FRONTEND="native",
               PYTHONPATH=str(ROOT))
    return subprocess.run(
        [sys.executable, "-m", "clausal", "-g", goal,
         str(_program(tmp_path))],
        cwd=ROOT, env=env, stdin=subprocess.DEVNULL, capture_output=True,
        text=True, timeout=600)


_HOLZBAUR = pytest.mark.skipif(clpq.SOLVER != "holzbaur",
                               reason="needs CLAUSAL_CLPQ=holzbaur")


@pytest.fixture
def probe(tmp_path, monkeypatch, caps):
    """The program loaded in this process (the native .pl front end)."""
    from clausal.import_hook import _load_module
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    path = _program(tmp_path)
    return _load_module("caps_probe", str(path)).__dict__["$module"]


def _caught(module, goal):
    """R where catch(Goal, error(resource_error(R), _), true) caught one;
    None where Goal answered."""
    from clausal.logic.solve import call
    resource = Var()
    answers = [walk(resource) for _ in call("caught", goal, resource,
                                             module=module)]
    assert len(answers) == 1
    return None if is_var(answers[0]) else answers[0]


@_HOLZBAUR
def test_catch_takes_each_resource_error(probe, caps):
    caps("clpq_nodes", 500)
    caps("clpq_projection", 10)
    caps("clpq_expansion", 10)
    x, y = Var(), Var()
    power = ArithEq(left=x, right=IsoIntPow(left=Add(left=y, right=1),
                                            right=10))
    assert _caught(probe, ("noint", Var())) == "clpq_nodes"
    assert _caught(probe, ("project", Var())) == "clpq_projection"
    assert _caught(probe, ("post", power)) == "clpq_expansion"
    x, y = Var(), Var()
    assert _caught(probe, ("post", ArithEq(
        left=x, right=IsoIntPow(left=Add(left=y, right=1), right=9)))) \
        is None


@_HOLZBAUR
def test_set_prolog_flag_sets_each_cap(probe, caps):
    from clausal.logic.solve import call
    for resource, flag in limits.FLAGS.items():
        value = Var()
        assert [walk(value) for _ in call(
            "current_prolog_flag", flag, value, module=probe)] \
            == [limits.limit(resource)]
        assert len(list(call("set_prolog_flag", flag, 77, module=probe))) == 1
        assert limits.limit(resource) == 77


def test_the_flags_read_and_set_each_cap(tmp_path):
    reads = ", ".join(f"current_prolog_flag({flag}, V{index})"
                      for index, flag in enumerate(limits.FLAGS.values()))
    result = _clausal(
        tmp_path, reads + ", set_prolog_flag(clpq_max_expansion, 7), "
        "current_prolog_flag(clpq_max_expansion, D)")
    assert result.stdout.strip() == ", ".join(
        f"V{index} = {limits.DEFAULTS[cap]}"
        for index, cap in enumerate(limits.FLAGS)) + ", D = 7.", \
        result.stderr


def test_catch_takes_the_errors_in_a_program(tmp_path):
    # Every cap from .pl source.  A literal {X = (Y+1)^3} is refused at
    # load (the front end lowers linear {} only), but a term bound at run
    # time is posted: power/3 and product/2 reach the expansion cap.
    result = _clausal(
        tmp_path,
        "set_prolog_flag(clpq_max_nodes, 500), "
        "set_prolog_flag(clpq_max_projection, 10), "
        "caught(noint(_), R1), caught(project(_), R2), "
        "caught(power(10000000, _, _), R3), caught(product(18, _), R4), "
        "power(3, X, Y)")
    assert result.stdout.strip().startswith(
        "R1 = clpq_nodes, R2 = clpq_projection, R3 = clpq_expansion, "
        "R4 = clpq_expansion, {"), result.stderr
    assert "Y^3" in result.stdout, result.stdout


def test_a_product_repaired_a_binding_at_a_time_raises(tmp_path):
    # Review N1, from .pl source: K sums each to an unbound exponent, then
    # every exponent bound to 1.  Each binding's repair multiplies one more
    # sum in; the constraint's count runs over its wake-ups.  4 sums
    # answer; 17 (52 s and 265 MB before) raise.
    result = _clausal(tmp_path, "rep(4), caught(rep(17), R)")
    assert result.stdout.strip() == "R = clpq_expansion.", result.stderr


def test_a_cap_flag_takes_a_positive_integer_only(tmp_path):
    result = _clausal(
        tmp_path,
        "catch(set_prolog_flag(clpq_max_nodes, 0), E1, true), "
        "catch(set_prolog_flag(clpq_max_nodes, ten), E2, true)")
    assert result.stdout.strip() == (
        "E1 = error(domain_error(flag_value,clpq_max_nodes+0),"
        "set_prolog_flag/2), "
        "E2 = error(domain_error(flag_value,clpq_max_nodes+ten),"
        "set_prolog_flag/2)."), result.stderr


def test_the_answer_printer_reports_the_projection_cap(tmp_path):
    # The -g printer projects every answer: past the cap it reports the
    # error and prints no answer, partial or whole.
    whole = _clausal(tmp_path, "big(X1, X2)")
    assert whole.returncode == 0 and "{" in whole.stdout, whole.stderr
    result = _clausal(
        tmp_path, "set_prolog_flag(clpq_max_projection, 10), big(X1, X2)")
    assert result.returncode != 0
    assert "resource_error(clpq_projection)" in result.stderr
    assert "{" not in result.stdout


def test_the_legacy_switch_has_no_cap_flags(tmp_path):
    result = _clausal(
        tmp_path, "catch(current_prolog_flag(clpq_max_nodes, _), E, true)",
        solver="legacy")
    assert result.stdout.strip() == (
        "E = error(domain_error(prolog_flag,clpq_max_nodes),"
        "current_prolog_flag/2)."), result.stderr
