# tests/clpq_port/test_inequalities.py
"""Task 9: ineq.pl (inequalities.py), posting inequalities.

Until normal_form.py (Task 10) exists, normal forms are lists of _Monomial
records and nf.pl's split/3 is a stand-in (the normal_form_split fixture),
as in test_bounded_simplex.py.  An inequality `Lin < 0` / `Lin =< 0` is
posted the way bv.pl's 'solve_<'/1 and 'solve_=<'/1 post it:
inequalities.inequality(Homogeneous, Constant, NormalForm, Strict, Trail).
"""
import importlib.util
import pathlib
import sys
import types
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import inequalities as ineq
from clausal.logic.clpq.arithmetic import ONE, ZERO, make_rational, to_number
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER,
    BOUNDS_LOWER_UPPER, BOUNDS_LOWER_UPPER_ACTIVE, BOUNDS_NONE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, bounds_lower, bounds_lower_active,
    bounds_lower_active_upper, bounds_lower_upper, bounds_lower_upper_active,
    bounds_none, bounds_upper, bounds_upper_active, state_of, strictness)
from clausal.logic.variables import Trail, Var, deref, is_var, unify


def q(numerator, denominator=1):
    return make_rational(numerator, denominator)


def _normal_form_module_posts():
    if importlib.util.find_spec("clausal.logic.clpq.normal_form") is None:
        return False
    module = importlib.import_module("clausal.logic.clpq.normal_form")
    return hasattr(module, "post_constraint")


needs_normal_form = pytest.mark.skipif(not _normal_form_module_posts(),
                                       reason="needs Task 10")


# ---------------------------------------------------------------- helpers

class _Monomial:
    """nf.pl's monomial(K, Powers): coefficient, powers as (base, exponent)."""
    __slots__ = ("coefficient", "powers")

    def __init__(self, coefficient, powers):
        self.coefficient = coefficient
        self.powers = powers


def _normal_form(constant, *terms):
    result = []
    if constant != ZERO:
        result.append(_Monomial(constant, []))
    for variable, coefficient in terms:
        result.append(_Monomial(coefficient, [(variable, 1)]))
    return result


def _split(normal_form):
    """nf.pl split/3."""
    if normal_form and not normal_form[0].powers:
        return normal_form[1:], normal_form[0].coefficient
    return normal_form, ZERO


@pytest.fixture
def normal_form_split(monkeypatch):
    if importlib.util.find_spec("clausal.logic.clpq.normal_form") is None:
        stub = types.ModuleType("clausal.logic.clpq.normal_form")
        stub.split = _split
        monkeypatch.setitem(sys.modules, "clausal.logic.clpq.normal_form", stub)


def _post(trail, strict, constant, *terms):
    """constant + sum K*X  < 0 (strict) or =< 0, through inequality/4."""
    normal_form = _normal_form(constant, *terms)
    homogeneous, inhomogeneous = _split(normal_form)
    return ineq.inequality(homogeneous, inhomogeneous, normal_form, strict, trail)


def _upper(trail, x, value, strict):
    """{X < value} or {X =< value}: X - value (<|=<) 0."""
    return _post(trail, strict, q(-value), (x, ONE))


def _lower(trail, x, value, strict):
    """{X > value} or {X >= value}: -X + value (<|=<) 0."""
    return _post(trail, strict, q(value), (x, q(-1)))


def _assign_directly(xs, ys, trail):
    if len(xs) != len(ys):
        return False
    for x, y in zip(xs, ys):
        if not unify(x, to_number(y), trail):
            return False
    return True


def _infimum(trail, constant, *terms):
    """bv.pl infimum_linear/4 of constant + sum K*X: the value, or None."""
    result = Var()
    if not bv.infimum_linear(_normal_form(constant, *terms), (result, [], []), trail):
        return None
    return Fraction(deref(result))


def _value(x):
    form = state_of(x).linear_form
    return Fraction(*form.rest) + Fraction(*form.constant)


def _row(x):
    """x's linear form as (constant, {id(variable): coefficient})."""
    form = state_of(x).linear_form
    return (Fraction(*form.constant),
            {id(v): Fraction(*k) for v, k in form.terms})


def _depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


# ---------------------------------------------------------------- inequality_ground/2

@pytest.mark.parametrize("constant, strict, expected", [
    (-1, True, True), (0, True, False), (1, True, False),
    (-1, False, True), (0, False, True), (1, False, False)])
def test_inequality_ground(constant, strict, expected):
    assert ineq.inequality_ground(strict, q(constant)) is expected
    trail = Trail()
    assert _post(trail, strict, q(constant)) is expected


# ---------------------------------------------------------------- one new variable

@pytest.mark.parametrize("strict", [True, False])
@pytest.mark.parametrize("coefficient, constant, bounds, bits", [
    # K*X + I (<|=<) 0
    (1, 0, bounds_upper(q(0)), 0b01),          # X < 0
    (-1, 0, bounds_lower(q(0)), 0b10),         # -X < 0
    (2, -3, bounds_upper(q(3, 2)), 0b01),      # 2X - 3 < 0
    (-4, -2, bounds_lower(q(-1, 2)), 0b10),    # -4X - 2 < 0
])
def test_a_new_variable_gets_its_bound_directly(coefficient, constant, bounds,
                                                bits, strict):
    # inequality_one_variable/4 and its eight new-variable cases.
    trail = Trail()
    x = Var()
    assert _post(trail, strict, q(constant), (x, q(coefficient)))
    state = state_of(x)
    assert state.bounds == bounds
    assert strictness(state) == (bits if strict else 0b00)
    assert state.linear_form.terms == [(x, ONE)]
    assert state.component is not None


def test_a_monomial_that_is_not_linear_fails():
    # inequality/4 clause 2's head needs monomial(K, [X^1]).
    trail = Trail()
    x = Var()
    square = [_Monomial(ONE, [(x, 2)])]
    assert ineq.inequality(square, ZERO, square, True, trail) is False


# ---------------------------------------------------------------- the bound-type case analysis
#
# An independent X of each of the eight bound types is given a new bound
# through inequality/4 (an old variable: inequality_one_old_variable_* then
# update_independent_*).  The result is compared with a direct computation
# on intervals.  The existing bounds are 0 and 4 (lower, upper), each strict
# or not; the new bound is one of -1, 0, 2, 4, 5.

_TYPES = {
    BOUNDS_NONE: (None, None),
    BOUNDS_LOWER: (0, None),
    BOUNDS_UPPER: (None, 4),
    BOUNDS_LOWER_UPPER: (0, 4),
    BOUNDS_LOWER_ACTIVE: (0, None),
    BOUNDS_UPPER_ACTIVE: (None, 4),
    BOUNDS_LOWER_ACTIVE_UPPER: (0, 4),
    BOUNDS_LOWER_UPPER_ACTIVE: (0, 4),
}
_INACTIVE = {BOUNDS_NONE: BOUNDS_NONE, BOUNDS_LOWER: BOUNDS_LOWER,
             BOUNDS_UPPER: BOUNDS_UPPER, BOUNDS_LOWER_UPPER: BOUNDS_LOWER_UPPER,
             BOUNDS_LOWER_ACTIVE: BOUNDS_LOWER, BOUNDS_UPPER_ACTIVE: BOUNDS_UPPER,
             BOUNDS_LOWER_ACTIVE_UPPER: BOUNDS_LOWER_UPPER,
             BOUNDS_LOWER_UPPER_ACTIVE: BOUNDS_LOWER_UPPER}
_LOWER_ACTIVE = (BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER)
_UPPER_ACTIVE = (BOUNDS_UPPER_ACTIVE, BOUNDS_LOWER_UPPER_ACTIVE)


def _make_independent(trail, kind, bits):
    """An independent X of bound type *kind* (bounds 0 and 4 where it has
    them), strictness *bits*; an active bound is introduced with bv.pl's
    introduce_at/3, so the rest of X's row holds its value."""
    lower, upper = _TYPES[kind]
    lower_q = None if lower is None else q(lower)
    upper_q = None if upper is None else q(upper)
    inactive = {BOUNDS_NONE: bounds_none(),
                BOUNDS_LOWER: bounds_lower(lower_q),
                BOUNDS_UPPER: bounds_upper(upper_q),
                BOUNDS_LOWER_UPPER: bounds_lower_upper(lower_q, upper_q)}[_INACTIVE[kind]]
    x = Var()
    assert bv.variable_intern_with_bounds(inactive, x, bits, trail)
    if kind == BOUNDS_LOWER_ACTIVE:
        assert bv.introduce_at(x, lower_q, bounds_lower_active(lower_q), trail)
    elif kind == BOUNDS_UPPER_ACTIVE:
        assert bv.introduce_at(x, upper_q, bounds_upper_active(upper_q), trail)
    elif kind == BOUNDS_LOWER_ACTIVE_UPPER:
        assert bv.introduce_at(x, lower_q,
                               bounds_lower_active_upper(lower_q, upper_q), trail)
    elif kind == BOUNDS_LOWER_UPPER_ACTIVE:
        assert bv.introduce_at(x, upper_q,
                               bounds_lower_upper_active(lower_q, upper_q), trail)
    return x


def _interval(kind, bits):
    lower, upper = _TYPES[kind]
    return (lower, lower is not None and bool(bits & 0b10),
            upper, upper is not None and bool(bits & 0b01))


def _intersect(interval, side, value, strict):
    """The interval with one more bound: at an equal value, strict wins."""
    lower, lower_strict, upper, upper_strict = interval
    if side == "upper":
        if upper is None or value < upper:
            upper, upper_strict = value, strict
        elif value == upper:
            upper_strict = upper_strict or strict
    else:
        if lower is None or value > lower:
            lower, lower_strict = value, strict
        elif value == lower:
            lower_strict = lower_strict or strict
    return lower, lower_strict, upper, upper_strict


def _classify(interval):
    lower, lower_strict, upper, upper_strict = interval
    if lower is None or upper is None or lower < upper:
        return "interval"
    if lower == upper and not lower_strict and not upper_strict:
        return "point"
    return "empty"


def _state_interval(x):
    state = state_of(x)
    bounds = state.bounds
    lower = None if bounds.lower is None else Fraction(*bounds.lower)
    upper = None if bounds.upper is None else Fraction(*bounds.upper)
    return (lower, lower is not None and state.lower_strict,
            upper, upper is not None and state.upper_strict)


def _consistent(kind, bits):
    """1.3.3 sets a strictness bit only together with its bound."""
    lower, upper = _TYPES[kind]
    return not (bits & 0b10 and lower is None) and not (bits & 0b01 and upper is None)


_CASES = [(kind, bits, side, value, strict)
          for kind in _TYPES
          for bits in (0b00, 0b10, 0b01, 0b11)
          if _consistent(kind, bits)
          for side in ("upper", "lower")
          for value in (-1, 0, 2, 4, 5)
          for strict in (False, True)]


@pytest.mark.parametrize("kind, bits, side, value, strict", _CASES)
def test_the_bound_type_case_analysis_matches_intervals(
        normal_form_split, kind, bits, side, value, strict):
    trail = Trail()
    x = _make_independent(trail, kind, bits)
    before = _interval(kind, bits)
    expected = _intersect(before, side, value, strict)
    post = _upper if side == "upper" else _lower
    result = post(trail, x, value, strict)
    shape = _classify(expected)
    if shape == "empty":
        assert result is False
        return
    assert result is True
    if shape == "point":
        assert not is_var(deref(x)) and deref(x) == value
        return
    assert _state_interval(x) == expected
    new_kind = state_of(x).bounds.kind
    # An active bound stays active; a new bound is never made active.
    assert (new_kind in _LOWER_ACTIVE) == (kind in _LOWER_ACTIVE)
    assert (new_kind in _UPPER_ACTIVE) == (kind in _UPPER_ACTIVE)
    if new_kind in _LOWER_ACTIVE:
        assert _value(x) == expected[0]
    elif new_kind in _UPPER_ACTIVE:
        assert _value(x) == expected[2]


# ---------------------------------------------------------------- dependent variables
#
# X = A + B with 0 =< A, B =< 2: X ranges over [0, 4].  X is a dependent
# variable; a bound on it goes through update_dependent_*.  Its range after
# the bound is read with bv.pl's infimum_linear/4 (inf and sup), and its
# strictness from its state.

def _make_dependent(trail, kind, bits):
    a = Var()
    b = Var()
    assert bv.variable_intern_with_bounds(bounds_lower_upper(q(0), q(2)), a, 0, trail)
    assert bv.variable_intern_with_bounds(bounds_lower_upper(q(0), q(2)), b, 0, trail)
    form = bv.dereference(_normal_form(ZERO, (a, ONE), (b, ONE)), trail)
    x = Var()
    assert bv.variable_with_definition_intern(bounds_none(), x, form, 0, trail)
    lower, upper = {BOUNDS_NONE: (None, None), BOUNDS_LOWER: (1, None),
                    BOUNDS_UPPER: (None, 3), BOUNDS_LOWER_UPPER: (1, 3)}[kind]
    if lower is not None:
        assert _lower(trail, x, lower, bool(bits & 0b10))
    if upper is not None:
        assert _upper(trail, x, upper, bool(bits & 0b01))
    return x, a, b, lower, upper


_DEPENDENT_CASES = [(kind, bits, side, value, strict)
                    for kind in (BOUNDS_NONE, BOUNDS_LOWER, BOUNDS_UPPER,
                                 BOUNDS_LOWER_UPPER)
                    for bits in (0b00, 0b10, 0b01, 0b11)
                    if _consistent(kind, bits)
                    for side in ("upper", "lower")
                    for value in (-1, 0, 1, 2, 3, 4, 5)
                    for strict in (False, True)]


@pytest.mark.parametrize("kind, bits, side, value, strict", _DEPENDENT_CASES)
def test_bounds_on_a_dependent_variable_match_intervals(
        normal_form_split, monkeypatch, kind, bits, side, value, strict):
    monkeypatch.setattr(bv, "assign", _assign_directly)
    trail = Trail()
    x, a, b, lower, upper = _make_dependent(trail, kind, bits)
    # The range of A + B is [0, 4], closed.
    current = (0 if lower is None else lower,
               lower is not None and bool(bits & 0b10),
               4 if upper is None else upper,
               upper is not None and bool(bits & 0b01))
    expected = _intersect(current, side, value, strict)
    post = _upper if side == "upper" else _lower
    result = post(trail, x, value, strict)
    shape = _classify(expected)
    if shape == "empty":
        assert result is False
        return
    assert result is True
    if shape == "point":
        assert not is_var(deref(x)) and deref(x) == value
        return
    assert is_var(deref(x))
    assert _infimum(trail, ZERO, (x, ONE)) == expected[0]
    assert -_infimum(trail, ZERO, (x, q(-1))) == expected[2]
    state = state_of(x)
    bounds = state.bounds
    if bounds.lower is not None and Fraction(*bounds.lower) == expected[0]:
        assert state.lower_strict == expected[1]
    if bounds.upper is not None and Fraction(*bounds.upper) == expected[2]:
        assert state.upper_strict == expected[3]


@pytest.mark.parametrize("dependent", [False, True])
@pytest.mark.parametrize("side", ["upper", "lower"])
def test_a_strict_opposite_bound_fails_before_solve_bound(
        normal_form_split, monkeypatch, dependent, side):
    # The t_lu clauses check `Sold /\ 0b.. =:= 0` before solve_bound/2
    # (update_dependent_lower/5, update_independent_upper/5, ...): meeting a
    # strict opposite bound fails without solving.  (Without the check bv.pl's
    # solve/1 would fail too, later.)
    calls = []
    monkeypatch.setattr(ineq, "solve_bound",
                        lambda *arguments: calls.append(arguments) or False)
    trail = Trail()
    if dependent:
        x = _make_dependent(trail, BOUNDS_LOWER_UPPER, 0b11)[0]
        lower, upper = 1, 3
    else:
        x = _make_independent(trail, BOUNDS_LOWER_UPPER, 0b11)
        lower, upper = 0, 4
    if side == "upper":
        assert _upper(trail, x, lower, False) is False
    else:
        assert _lower(trail, x, upper, False) is False
    assert calls == []


# ---------------------------------------------------------------- more variables

@pytest.mark.parametrize("strict, bits", [(True, 0b10), (False, 0b00)])
def test_an_unconstrained_variable_absorbs_the_slack(normal_form_split, strict, bits):
    # inequality_more_variables/2 clause 1: X + Y - 3 (<|=<) 0 with X, Y
    # free: one of them is defined by 3 - other - S, S >= 0 (strict: S > 0).
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, strict, q(-3), (x, ONE), (y, ONE))
    # Exactly one of X, Y is now defined over the other and a slack.
    dependents = [v for v in (x, y) if len(state_of(v).linear_form.terms) == 2]
    assert len(dependents) == 1
    dependent = dependents[0]
    other = y if dependent is x else x
    constant, row = _row(dependent)
    assert constant == 3 and row[id(other)] == -1
    (slack_id, coefficient), = [(k, v) for k, v in row.items() if k != id(other)]
    assert coefficient == -1
    slack = [v for v, _ in state_of(dependent).linear_form.terms
             if id(v) == slack_id][0]
    assert state_of(slack).bounds == bounds_lower(ZERO)
    assert strictness(state_of(slack)) == bits
    # All three share one component.
    components = {id(deref(state_of(v).component)) for v in (x, y, slack)}
    assert len(components) == 1


def test_a_second_inequality_on_the_same_sum_bounds_the_slack(normal_form_split):
    # After X + Y =< 3 (Y := 3 - X - S), X + Y >= 1 dereferences to S - 2 =< 0:
    # one variable, so inequality_more_variables/4 bounds S, no new slack.
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, False, q(-3), (x, ONE), (y, ONE))
    assert _post(trail, False, q(1), (x, q(-1)), (y, q(-1)))
    dependent = x if len(state_of(x).linear_form.terms) == 2 else y
    slack = [v for v, _ in state_of(dependent).linear_form.terms
             if v is not x and v is not y][0]
    assert state_of(slack).bounds == bounds_lower_upper(ZERO, q(2))
    # And X + Y > 3 now fails: S < 0 against S >= 0.
    assert _post(trail, True, q(3), (x, q(-1)), (y, q(-1))) is False


@pytest.mark.parametrize("strict, bits", [(True, 0b01), (False, 0b00)])
def test_a_slack_enters_the_basis_when_nothing_is_unconstrained(
        normal_form_split, strict, bits):
    # inequality_more_variables/2 clause 2.
    trail = Trail()
    x = _make_independent(trail, BOUNDS_LOWER, 0)
    y = _make_independent(trail, BOUNDS_LOWER, 0)
    assert _post(trail, strict, q(-5), (x, ONE), (y, ONE))
    component = state_of(x).component
    basis = bv.basis(x)
    from clausal.logic.clpq.components import list_elements
    members = list_elements(basis)
    assert len(members) == 1
    slack = members[0]
    assert state_of(slack).bounds == bounds_upper(ZERO)
    assert strictness(state_of(slack)) == bits
    assert deref(state_of(slack).component) is deref(component)
    # X and Y were made active at their lower bounds: the slack is at -5.
    assert state_of(x).bounds == bounds_lower_active(ZERO)
    assert _value(slack) == -5


def test_tightening_an_active_bound_pivots_and_finds_the_implied_values(
        normal_form_split):
    # 0 =< X, 0 =< Y, X + Y =< 5.  X >= 3 moves X's active bound
    # (update_independent_lower/5, bounds_lower_active, no pivot: 3 < 5);
    # X >= 5 reaches the row's limit, pivots X into the basis and the
    # implied values X = 5, Y = 0 are bound.
    trail = Trail()
    x = _make_independent(trail, BOUNDS_LOWER, 0)
    y = _make_independent(trail, BOUNDS_LOWER, 0)
    assert _post(trail, False, q(-5), (x, ONE), (y, ONE))
    assert _lower(trail, x, 3, False)
    assert state_of(x).bounds == bounds_lower_active(q(3))
    assert _value(x) == 3
    mark = trail.mark()
    assert _lower(trail, x, 6, False) is False
    trail.undo(mark)
    assert _lower(trail, x, 5, True) is False
    trail.undo(mark)
    assert _lower(trail, x, 5, False)
    assert deref(x) == 5 and deref(y) == 0


def test_tightening_an_active_upper_bound_pivots(normal_form_split):
    # The mirror image: X =< 4, Y =< 4, X + Y >= -5 (as -X - Y - 5 =< 0).
    # X ranges down to -9 (with Y = 4).
    trail = Trail()
    x = _make_independent(trail, BOUNDS_UPPER, 0)
    y = _make_independent(trail, BOUNDS_UPPER, 0)
    assert _post(trail, False, q(-5), (x, q(-1)), (y, q(-1)))
    assert state_of(x).bounds == bounds_upper_active(q(4))
    assert _upper(trail, x, -3, False)
    assert state_of(x).bounds == bounds_upper_active(q(-3))
    assert _value(x) == -3
    mark = trail.mark()
    assert _upper(trail, x, -10, False) is False
    trail.undo(mark)
    assert _upper(trail, x, -9, True) is False
    trail.undo(mark)
    assert _upper(trail, x, -9, False)
    assert deref(x) == -9 and deref(y) == 4


def test_a_bound_on_a_dependent_variable_with_a_free_row_swaps_it_out(
        normal_form_split):
    # update_dependent_upper/5 clause 1 with an unconstrained variable in the
    # row: X = A + F with F free; X =< 1 makes F dependent instead
    # (back_substitute of F), and X becomes independent with the bound.
    trail = Trail()
    a = _make_independent(trail, BOUNDS_LOWER_UPPER, 0)
    f = Var()
    form = bv.dereference(_normal_form(q(7), (a, ONE), (f, ONE)), trail)
    x = Var()
    assert bv.variable_with_definition_intern(bounds_none(), x, form, 0, trail)
    assert _upper(trail, x, 1, False)
    assert state_of(x).bounds == bounds_upper(ONE)
    assert state_of(x).linear_form.terms == [(x, ONE)]
    constant, row = _row(f)
    assert (constant, row) == (-7, {id(a): -1, id(x): 1})


# ---------------------------------------------------------------- solve_bound/2, reconsider

def test_solve_bound_with_zero_and_with_a_value(normal_form_split):
    trail = Trail()
    x = _make_independent(trail, BOUNDS_NONE, 0)
    form = state_of(x).linear_form
    assert ineq.solve_bound(form, ZERO, trail)
    assert deref(x) == 0
    trail = Trail()
    y = _make_independent(trail, BOUNDS_NONE, 0)
    assert ineq.solve_bound(state_of(y).linear_form, q(5, 3), trail)
    assert deref(y) == Fraction(5, 3)


def test_reconsider_upper_does_nothing_inside_the_bound(normal_form_split):
    trail = Trail()
    x = _make_independent(trail, BOUNDS_NONE, 0)
    state = state_of(x)
    form = state.linear_form
    assert ineq.reconsider_upper(x, form, q(1), trail) is True
    assert ineq.reconsider_lower(x, form, q(-1), trail) is True
    assert state_of(x) is state


def test_reconsider_upper_at_the_bound_takes_a_step(normal_form_split):
    # X = A + B, 0 =< A, B =< 4, A active at 4 and B at 0: X =< 1 is not met, so
    # reconsider_upper/3 (via update_dependent_upper/5) decreases X.
    trail = Trail()
    a = _make_independent(trail, BOUNDS_LOWER_UPPER_ACTIVE, 0)    # 0..4, at 4
    b = _make_independent(trail, BOUNDS_LOWER_UPPER, 0)
    form = bv.dereference(_normal_form(ZERO, (a, ONE), (b, ONE)), trail)
    x = Var()
    assert bv.variable_with_definition_intern(bounds_none(), x, form, 0, trail)
    assert bv.basis_add(x, trail) is not False
    assert bv.undetermined_active(form, trail)
    assert _value(x) == 4
    assert _upper(trail, x, 1, False)
    assert _value(x) <= 1


# ---------------------------------------------------------------- Review Focus 3

_CHAIN_STEPS = 30
_FACTOR = Fraction(7, 13)
_ADD = Fraction(1, 3)


def _chain_value(start):
    value = Fraction(start)
    for _ in range(_CHAIN_STEPS):
        value = _FACTOR * value + _ADD
    return value


def test_review_focus_3_the_chain_on_bv_and_ineq_alone(normal_form_split, monkeypatch):
    # X_{i+1} = (7/13)*X_i + 1/3 for 30 steps, 0 =< X_0 =< 1: the infimum
    # and supremum of X_30 are exact rationals equal to Fraction arithmetic.
    monkeypatch.setattr(bv, "assign", _assign_directly)
    trail = Trail()
    x0 = Var()
    assert _lower(trail, x0, 0, False)
    assert _upper(trail, x0, 1, False)
    previous = x0
    for _ in range(_CHAIN_STEPS):
        following = Var()
        # X_{i+1} - 7/13*X_i - 1/3 = 0
        equation = _normal_form(q(-1, 3), (following, ONE), (previous, q(-7, 13)))
        assert bv.solve_equal(equation, trail)
        previous = following
    assert _infimum(trail, ZERO, (previous, ONE)) == _chain_value(0)
    assert -_infimum(trail, ZERO, (previous, q(-1))) == _chain_value(1)
    # Strict bounds on X_30 just inside and at its range.
    top = _chain_value(1)
    top_q = q(top.numerator, top.denominator)
    mark = trail.mark()
    assert _post(trail, True, top_q, (previous, q(-1))) is False   # X_30 > top
    trail.undo(mark)
    assert _post(trail, False, top_q, (previous, q(-1)))           # X_30 >= top
    assert deref(x0) == 1 and deref(previous) == top


_CHAIN_PROGRAM = """\
:- use_module(library(clpq)).
chain(X, X, 0).
chain(X0, Xn, N) :- N > 0, {X1 = 7/13*X0 + 1/3}, N1 is N-1, chain(X1, Xn, N1).
fixed(X30) :- {X0 = 1}, chain(X0, X30, 30).
range(S, I) :- {X0 >= 0, X0 =< 1}, chain(X0, X30, 30), sup(X30, S), inf(X30, I).
"""


@needs_normal_form
@pytest.mark.parametrize("goal, variables, expected", [
    ("fixed(X)", ["X"], {"X": _chain_value(1)}),
    ("range(S, I)", ["S", "I"], {"S": _chain_value(1), "I": _chain_value(0)}),
])
def test_review_focus_3_the_chain_against_the_oracle(goal, variables, expected):
    from tests.clpq_oracle import (
        Answer, clausal_answers, oracle_answers, same_solution_sets)
    oracle = oracle_answers(_CHAIN_PROGRAM, goal, variables)
    assert same_solution_sets(oracle, [Answer(expected, [])])[0]
    clausal = clausal_answers(_CHAIN_PROGRAM, goal, variables, solver="holzbaur")
    ok, why = same_solution_sets(oracle, clausal)
    assert ok, why


def test_a_strict_bound_met_by_a_non_strict_one_fails(normal_form_split):
    # {X > 0, X =< 0}: update_independent_upper/5 (t_l clause) calls
    # solve_bound/2 without reading X's strictness; bv.pl's solve/1 makes X
    # dependent and its reconsider fails at the strict optimum.
    trail = Trail()
    x = Var()
    assert _lower(trail, x, 0, True)
    assert _upper(trail, x, 0, False) is False


@needs_normal_form
def test_a_strict_bound_met_by_a_non_strict_one_fails_end_to_end():
    # The same on the oracle and through nf.pl.
    from tests.clpq_oracle import clausal_answers, oracle_answers
    program = ":- use_module(library(clpq)).\na(X) :- {X > 0, X =< 0}.\n"
    assert oracle_answers(program, "a(X)", ["X"]) == []
    assert clausal_answers(program, "a(X)", ["X"], solver="holzbaur") == []


# ---------------------------------------------------------------- depth

def test_a_long_inequality_needs_no_recursion(normal_form_split):
    # 2,000 bounded variables in one row, under a recursion limit of 200
    # frames above this test: dereference is balanced (log depth),
    # everything else is loops.  Not 50,000: posting and the implied-value
    # cascade are quadratic in bv.pl (ord_add_element in select_dependent,
    # back_substitute_collect_bindings per implied value), about 5 s at
    # 2,000 and 20 s at 4,000.
    count = 2_000
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 200)
    try:
        trail = Trail()
        variables = [_make_independent(trail, BOUNDS_LOWER, 0) for _ in range(count)]
        assert _post(trail, False, q(-1), *[(v, ONE) for v in variables])
        assert _lower(trail, variables[0], 1, False)
        assert deref(variables[0]) == 1
        assert all(deref(v) == 0 for v in variables[1:100])
    finally:
        sys.setrecursionlimit(limit)


def test_the_module_has_its_provenance_header():
    text = pathlib.Path(ineq.__file__).read_text()
    # ineq.pl's banner says version 1.3.2 (ruling R12: cite the banner).
    assert text.startswith("# Ported from the clp(q,r) 1.3.3 distribution, "
                           "file ineq.pl (banner: version 1.3.2)\n")
