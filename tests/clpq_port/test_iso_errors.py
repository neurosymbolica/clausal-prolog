# tests/clpq_port/test_iso_errors.py
"""Task 16 fix round: every error the port and its adapter raise is an ISO
error term, never a raw Python exception (ruling R19), and a cyclic term
raises instead of looping (security review High 2, ruling R34).

Each test asserts the whole error term.  The adapter is called in process,
bare (trail.defer False) and as a driver leaves the trail at a goal
(trail.defer True, the queue run after with run_first), whatever CLAUSAL_CLPQ says.
"""
import signal
from decimal import Decimal
from fractions import Fraction

import pytest

from clausal.logic.clpq import holzbaur as h
from clausal.logic.clpq import normal_form as nf
from clausal.logic.clpq import residual_constraints as rc
from clausal.logic.exceptions import (
    LogicException, evaluation_error, instantiation_error,
    representation_error, system_error, type_error)
from clausal.logic.pending import run_first
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.pythonic_ast.nodes import Add, ArithEq, GtE, Mult


def _trail(driver):
    trail = Trail()
    trail.defer = driver
    return trail


def _raised(call, trail=None):
    """The term *call* raises; with a driver's trail, the queue is drained
    after the call, so a woken goal's error counts too."""
    with pytest.raises(LogicException) as caught:
        call()
        if trail is not None and trail.defer:
            run_first(trail)
    return caught.value.term


class _Hang(BaseException):
    pass


def _within(seconds, call):
    """*call* or _Hang after *seconds* (a hang is the bug)."""
    def alarm(*_):
        raise _Hang()
    previous = signal.signal(signal.SIGALRM, alarm)
    signal.alarm(seconds)
    try:
        return call()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


# ---------------------------------------------------------------- cyclic terms
#
# 1.3.3 (and the local clpq.pl port on Scryer) loops on a cyclic term.
# Scryer's is/2 raises type_error(evaluable, (+)/2) on `X = 1+X, Y is X`,
# naming the functor of the compound that closes the cycle, a finite
# culprit (DEVIATIONS.md D23).

_CYCLE = type_error("evaluable", ("/", "+", 2), "normal_form/2")


def _cyclic_node(trail):
    x = Var()
    assert unify(x, Add(left=1, right=x), trail)
    return x


def _cyclic_cell(trail):
    x = Var()
    assert unify(x, ("+", 1, x), trail)
    return x


@pytest.mark.parametrize("make", [_cyclic_node, _cyclic_cell])
def test_normal_form_of_a_cyclic_term_raises(make):
    x = make(Trail())
    assert _within(5, lambda: _raised(lambda: nf.normal_form(x))) == _CYCLE


def test_a_shared_subterm_is_not_a_cycle():
    # X+X shared three levels deep is a DAG: 8*X.
    t, x, y = Trail(), Var(), Var()
    s = Add(left=x, right=x)
    s = Add(left=s, right=s)
    assert h.q_eq(y, Add(left=s, right=s), t)
    assert h.q_eq(x, 1, t)
    assert deref(y) == 8


@pytest.mark.parametrize("driver", [False, True])
def test_bb_inf_of_a_cyclic_term_raises(driver):
    # secport/cyc.clausal c3: X = 1 + X, bb_inf([X], 0, I).
    t = _trail(driver)
    x = _cyclic_node(t)
    assert _within(5, lambda: _raised(
        lambda: h.bb_inf([x], 0, Var(), t), t)) == _CYCLE


@pytest.mark.parametrize("driver", [False, True])
def test_a_cyclic_binding_of_a_delayed_variable_raises(driver):
    # secport/cyc.clausal c9: {Y*Y >= Z}, Z = 1 + Z.
    t, y, z = _trail(driver), Var(), Var()
    assert h.q_ge(Mult(left=y, right=y), z, t)
    if driver:
        assert run_first(t)
    assert _within(5, lambda: _raised(
        lambda: unify(z, Add(left=1, right=z), t), t)) == _CYCLE


@pytest.mark.parametrize("driver", [False, True])
@pytest.mark.parametrize("call", [
    lambda x, t: h.q_ge(Var(), x, t),                       # c1
    lambda x, t: h.inf(x, Var(), t),                        # c2
    lambda x, t: h.sup(x, Var(), t),
    lambda x, t: h.entailed(">=", x, 0, t),
    lambda x, t: h.clpq_constraint_block(GtE(left=Var(), right=x), t),
], ids=["q_ge", "inf", "sup", "entailed", "block"])
def test_the_adapter_refuses_a_cyclic_term(call, driver):
    # c1 and c2 raised RecursionError in clpfd's cell walk before the port
    # was reached.  The adapter's check raises what normal_form/2 raises.
    t = _trail(driver)
    x = _cyclic_node(t)
    assert _within(5, lambda: _raised(lambda: call(x, t), t)) == _CYCLE


# ---------------------------------------------------------------- blocks

def test_a_block_of_a_term_that_is_no_constraint_raises():
    # nf.pl {}/1 clause 13: illarg(type(constraint), {Rel}, 1).
    t = Trail()
    node = Add(left=1, right=2)
    assert _raised(lambda: h.clpq_constraint_block(node, t)) == \
        type_error("constraint", node, "{}/1")
    assert _raised(lambda: list(h.clpq_constraint_answers(node, t))) == \
        type_error("constraint", node, "{}/1")


def test_a_block_that_is_a_variable_raises():
    # nf.pl {}/1 clause 1 (clpq.rational(X) with X unbound).
    t = Trail()
    assert _raised(lambda: h.clpq_constraint_block(Var(), t)) == \
        instantiation_error("{}/1")
    assert _raised(lambda: list(h.clpq_constraint_answers(Var(), t))) == \
        instantiation_error("{}/1")


def test_a_disjunction_through_the_one_answer_entry_raises():
    t, x = Trail(), Var()
    block = (";", ArithEq(left=x, right=1), ArithEq(left=x, right=2))
    assert _raised(lambda: h.clpq_constraint_block(block, t)) == \
        type_error("constraint", block, "{}/1")


def test_entailed_of_an_unknown_relation_raises():
    # nf.pl negate/2 clause 11: illarg(type(constraint), entailed(Rel), 1).
    t, x = Trail(), Var()
    assert _raised(lambda: h.entailed("=>>", x, 1, t)) == \
        type_error("constraint", ("=>>", x, 1), "entailed/1")


# ---------------------------------------------------------------- in_q bounds

@pytest.mark.parametrize("bound", ["a", "1/3", ("$chars", "1"), ("f", 1)])
def test_in_q_refuses_a_bound_that_is_not_a_number(bound):
    t = Trail()
    assert _raised(lambda: h.in_q(Var(), bound, None, t)) == \
        type_error("rational", bound, "in_q/3")
    assert _raised(lambda: h.in_q(Var(), None, bound, t)) == \
        type_error("rational", bound, "in_q/3")


def test_in_q_with_an_unbound_bound_raises():
    t = Trail()
    assert _raised(lambda: h.in_q(Var(), Var(), 3, t)) == \
        instantiation_error("in_q/3")


def test_in_q_reads_a_float_bound_as_nf_pl_reads_a_float():
    # {X >= 0.1} gives 1/10 (float_to_rational); in_q's bound is that post.
    t, x, low = Trail(), Var(), Var()
    assert h.in_q(x, 0.1, 1, t)
    assert h.inf(x, low, t) and deref(low) == Fraction(1, 10)


# ---------------------------------------------------------------- numbers

_UNDEFINED = evaluation_error("undefined", "is/2")
_OVERFLOW = evaluation_error("float_overflow", "is/2")
_TOO_LARGE = representation_error("max_integer", "is/2")


@pytest.mark.parametrize("value, expected", [
    (Decimal("NaN"), _UNDEFINED), (Decimal("sNaN"), _UNDEFINED),
    (Decimal("Infinity"), _OVERFLOW), (Decimal("-Infinity"), _OVERFLOW),
    (Decimal("1E+999999999"), _TOO_LARGE),
    (Decimal("1E-999999999"), _TOO_LARGE),
], ids=["nan", "snan", "inf", "-inf", "huge", "tiny"])
@pytest.mark.parametrize("call", [
    lambda v, t: h.q_le(Var(), v, t),
    lambda v, t: h.q_eq(Var(), v, t),
    lambda v, t: h.q_ne(Var(), v, t),
    lambda v, t: h.sup(v, Var(), t),
    lambda v, t: h.bb_inf([Var()], v, Var(), t),
    lambda v, t: h.entailed("=<", Var(), v, t),
    lambda v, t: h.in_q(Var(), v, None, t),
], ids=["q_le", "q_eq", "q_ne", "sup", "bb_inf", "entailed", "in_q"])
def test_a_decimal_without_a_rational_raises(call, value, expected):
    t = Trail()
    assert _within(5, lambda: _raised(lambda: call(value, t))) == expected


def test_a_large_decimal_exponent_is_still_exact():
    t, x, low = Trail(), Var(), Var()
    assert h.q_ge(x, Decimal("1E+1000"), t)
    assert h.inf(x, low, t) and deref(low) == 10 ** 1000


def test_the_smallest_float_is_read_exactly():
    # float_to_rational took 1/5e-324 and raised OverflowError.
    t, y, low = Trail(), Var(), Var()
    assert h.q_ge(y, 5.0e-324, t)
    assert h.inf(y, low, t) and deref(low) == Fraction(5.0e-324)


def test_a_bound_past_4300_digits_prints():
    # str(int) raises ValueError above 4300 digits.
    t, y = Trail(), Var()
    assert h.q_ge(y, 10 ** 5000, t)
    assert h.dump_q([y], t, lambda v: "Y") == ["{Y >= 1" + "0" * 5000 + "}"]
    assert h.residual_q([y], t, lambda v: "Y") == \
        ["{Y >= 1" + "0" * 5000 + "}"]
    big = Fraction(1, 10 ** 5000)
    assert h.q_le(y, big + 10 ** 5000, t)
    assert rc.format_term(big, None) == "1/1" + "0" * 5000


def test_a_base_bound_to_a_non_number_raises_a_type_error():
    x = Var()
    assert unify(x, "a", Trail())
    assert _raised(lambda: nf.compare_bases(x, Var())) == \
        type_error("expression", "a", "normal_form/2")


def test_a_failing_dump_raises_a_system_error(monkeypatch):
    t, x = Trail(), Var()
    assert h.q_ge(x, 1, t)
    monkeypatch.setattr(rc, "dump", lambda *_: None)
    assert _raised(lambda: h.dump_q([x], t)) == \
        system_error("clpq_dump_failed", "dump/3")


# ---------------------------------------------------------------- lists

@pytest.mark.parametrize("value", [5, "a", ("f", 1)])
def test_bb_inf_and_dump_q_refuse_a_non_list(value):
    t = Trail()
    assert _raised(lambda: h.bb_inf(value, 0, Var(), t)) == \
        type_error("list", value, "bb_inf/3")
    assert _raised(lambda: h.dump_q(value, t)) == \
        type_error("list", value, "dump_q/2")


def test_bb_inf_and_dump_q_refuse_an_unbound_list():
    t = Trail()
    assert _raised(lambda: h.bb_inf(Var(), 0, Var(), t)) == \
        instantiation_error("bb_inf/3")
    assert _raised(lambda: h.dump_q(Var(), t)) == \
        instantiation_error("dump_q/2")


# ---------------------------------------------------------------- Fable M5

def test_a_decimal_keeps_its_scale_in_a_disjunction():
    # The non-; path binds Decimal('2.50') (D20); the ; path did 5/2.
    t, x = Trail(), Var()
    block = (";", ArithEq(left=x, right=Decimal("2.50")),
             ArithEq(left=x, right=Decimal("3.750")))
    answers = []
    for _ in h.clpq_constraint_answers(block, t):
        answers.append(repr(deref(x)))
    assert answers == ["Decimal('2.50')", "Decimal('3.750')"]
    assert is_var(deref(x))
