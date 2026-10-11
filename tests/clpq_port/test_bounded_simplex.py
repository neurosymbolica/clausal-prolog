# tests/clpq_port/test_bounded_simplex.py
"""Task 8: bv.pl (bounded_simplex.py), the simplex with bounded variables.

Most tests build the store the way ineq.pl builds it, with bv.pl's own
predicates (_slack), and write normal forms as lists of _Monomial records,
the shape nf.pl's (normal_form.py) monomials have; the tests through nf.pl
post with normal_form.post_constraint.
"""
import random
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq.arithmetic import ONE, ZERO, make_rational
from clausal.logic.clpq.attributes import (
    BOUNDS_NONE, Bounds, SolverState, bounds_lower, bounds_lower_active,
    bounds_lower_active_upper, bounds_lower_upper, bounds_lower_upper_active,
    bounds_none, bounds_upper, bounds_upper_active, put_state, state_of,
    strictness, strictness_fields, with_changes)
from clausal.logic.clpq.components import (
    COMPONENT_KEY, component_all_variables, list_elements)
from clausal.logic.clpq.linear_forms import LinearForm
from clausal.logic.variables import Trail, Var, deref, get_attr, is_var

def q(numerator, denominator=1):
    return make_rational(numerator, denominator)


# ---------------------------------------------------------------- helpers

class _Monomial:
    """nf.pl's monomial(K, Powers): the shape bounded_simplex reads
    (coefficient, powers as (base, exponent) pairs)."""
    __slots__ = ("coefficient", "powers")

    def __init__(self, coefficient, powers):
        self.coefficient = coefficient
        self.powers = powers


def _normal_form(constant, *terms):
    """[monomial(I, []), monomial(K, [X^1]), ...], the constant dropped when
    zero, as nf.pl keeps it."""
    result = []
    if constant != ZERO:
        result.append(_Monomial(constant, []))
    for variable, coefficient in terms:
        result.append(_Monomial(coefficient, [(variable, 1)]))
    return result


@pytest.fixture
def normal_form_split():
    """Tests written before nf.pl was ported ask for this; nf.pl's split/3
    is normal_form.split now, so it provides nothing."""


def _bounded(trail, bounds, strict=0):
    """A variable with a bound, as ineq.pl's one-variable cases intern it."""
    x = Var()
    assert bv.variable_intern_with_bounds(bounds, x, strict, trail)
    return x


def _slack(trail, constant, *terms, strict=0b00):
    """constant + sum K*X =< 0 with more than one variable and none
    unconstrained: ineq.pl inequality_more_variables/2, second branch."""
    form = bv.dereference(_normal_form(constant, *terms), trail)
    assert form is not None
    assert bv.unconstrained(form) is None
    s = Var()
    assert bv.variable_with_definition_intern(bounds_upper(ZERO), s, form,
                                              strict, trail)
    assert bv.basis_add(s, trail) is not False
    assert bv.determine_active_decrease(form, trail)
    return s, bv.reconsider(s, trail)


def _value(x):
    """The current value of x: R + I of its linear form."""
    form = state_of(x).linear_form
    return Fraction(*form.rest) + Fraction(*form.constant)


def _snapshot(variables):
    states = {}
    for x in variables:
        state = state_of(x)
        states[id(x)] = state
        if state is not None and state.component is not None:
            states[("component", id(x))] = get_attr(state.component, COMPONENT_KEY)
    return states


def _same_snapshot(before, variables):
    after = _snapshot(variables)
    return all(after[key] is before[key] for key in before)


def _depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


def _box(trail):
    """0 =< X =< 2, 0 =< Y =< 3, X + 2*Y =< 6."""
    x = _bounded(trail, bounds_lower_upper(q(0), q(2)))
    y = _bounded(trail, bounds_lower_upper(q(0), q(3)))
    s, ok = _slack(trail, q(-6), (x, q(1)), (y, q(2)))
    assert ok
    return x, y, s


def _objective(trail, *terms):
    """minimize_linear/1 up to iterate_decrease: Dep defined by the terms."""
    form = bv.dereference(_normal_form(ZERO, *terms), trail)
    dependent = Var()
    assert bv.variable_with_definition_intern(bounds_none(), dependent, form,
                                              0, trail)
    assert bv.determine_active_decrease(form, trail)
    return dependent


def _assign_directly(xs, ys, trail):
    """bv.pl assign/2 without nf.pl: X = Y for each pair."""
    from clausal.logic.clpq.arithmetic import to_number
    from clausal.logic.variables import unify
    if len(xs) != len(ys):
        return False
    for x, y in zip(xs, ys):
        if not unify(x, to_number(y), trail):
            return False
    return True


# ---------------------------------------------------------------- the brief's three tests, through nf.pl

def test_inf_and_sup_leave_the_store_as_it_was():
    from clausal.logic.clpq.normal_form import post_constraint
    from clausal.pythonic_ast.nodes import LtE
    from clausal.terms import Add, Mult
    # The states are compared by identity; the dump comparison under
    # same_solution_sets needs dump/3 (Task 12).
    trail = Trail()
    x, y = Var(), Var()
    assert post_constraint(LtE(left=0, right=x), trail)
    assert post_constraint(LtE(left=x, right=2), trail)
    assert post_constraint(LtE(left=0, right=y), trail)
    assert post_constraint(LtE(left=y, right=3), trail)
    assert post_constraint(LtE(left=Add(left=x, right=Mult(left=2, right=y)), right=6), trail)
    before = _snapshot([x, y])
    infimum, supremum = Var(), Var()
    assert bv.inf(Add(left=x, right=Mult(left=3, right=y)), infimum, trail)
    assert bv.sup(Add(left=x, right=Mult(left=3, right=y)), supremum, trail)
    assert deref(infimum) == 0 and deref(supremum) == 9
    assert _same_snapshot(before, [x, y])


def test_review_focus_1_a_strict_bound_comes_back_strict_after_backtracking():
    # {X < 3}, ({X =< 2}, fail ; true), sup(X, S) gives S = 3.
    from clausal.logic.clpq.normal_form import post_constraint
    from clausal.pythonic_ast.nodes import Lt, LtE
    trail = Trail()
    x = Var()
    assert post_constraint(Lt(left=x, right=3), trail)
    mark = trail.mark()
    assert post_constraint(LtE(left=x, right=2), trail)
    trail.undo(mark)
    supremum = Var()
    assert bv.sup(x, supremum, trail)
    assert deref(supremum) == 3
    assert state_of(x).upper_strict is True


def test_the_box_lp_maximum_is_9_at_0_3():
    # minimize_linear ends in {Dep =:= Inf}, which binds Dep; itf3.pl's hook
    # carries that to X and Y (Task 11).
    from clausal.logic.clpq.normal_form import post_constraint
    from clausal.pythonic_ast.nodes import LtE
    from clausal.terms import Add, Mult
    trail = Trail()
    x, y = Var(), Var()
    for constraint in (LtE(left=0, right=x), LtE(left=x, right=2), LtE(left=0, right=y), LtE(left=y, right=3),
                       LtE(left=Add(left=x, right=Mult(left=2, right=y)), right=6)):
        assert post_constraint(constraint, trail)
    assert bv.maximize(Add(left=x, right=Mult(left=3, right=y)), trail)
    assert deref(x) == 0 and deref(y) == 3


# ---------------------------------------------------------------- the same three on bv.pl alone

def test_infimum_linear_leaves_the_store_as_it_was(normal_form_split, monkeypatch):
    monkeypatch.setattr(bv, "assign", _assign_directly)
    trail = Trail()
    x, y, s = _box(trail)
    before = _snapshot([x, y, s])
    infimum = Var()
    objective = _normal_form(ZERO, (x, q(-1)), (y, q(-3)))
    assert bv.infimum_linear(objective, (infimum, [], []), trail)
    assert deref(infimum) == -9
    assert _same_snapshot(before, [x, y, s])
    supremum_term = Var()
    assert bv.infimum_linear(_normal_form(ZERO, (x, q(1)), (y, q(3))),
                             (supremum_term, [], []), trail)
    assert deref(supremum_term) == 0
    assert _same_snapshot(before, [x, y, s])


def test_an_unbounded_infimum_fails_and_leaves_the_store_as_it_was(
        normal_form_split, monkeypatch):
    monkeypatch.setattr(bv, "assign", _assign_directly)
    trail = Trail()
    x = _bounded(trail, bounds_lower(q(1)))
    before = _snapshot([x])
    assert bv.infimum_linear(_normal_form(ZERO, (x, q(-1))),
                             (Var(), [], []), trail) is False
    assert _same_snapshot(before, [x])
    infimum = Var()
    assert bv.infimum_linear(_normal_form(ZERO, (x, q(1))),
                             (infimum, [], []), trail)
    assert deref(infimum) == 1


def test_a_strict_bound_comes_back_strict_and_sup_is_3(normal_form_split, monkeypatch):
    # Review Focus 1 on bv.pl alone: {X < 3} is variable_intern(t_u(3), X,
    # 0b01) (ineq.pl inequality_one_variable_strict_positive_constant); the
    # {X =< 2} inside the failed branch replaces the bound and strictness.
    monkeypatch.setattr(bv, "assign", _assign_directly)
    trail = Trail()
    x = _bounded(trail, bounds_upper(q(3)), strict=0b01)
    mark = trail.mark()
    put_state(x, with_changes(state_of(x), bounds=bounds_upper(q(2)),
                              upper_strict=False), trail)
    trail.undo(mark)
    assert state_of(x).bounds == bounds_upper(q(3))
    assert strictness(state_of(x)) == 0b01
    negated = Var()        # sup(X, S) is inf(-X, -S)
    assert bv.infimum_linear(_normal_form(ZERO, (x, q(-1))),
                             (negated, [], []), trail)
    assert deref(negated) == -3


def test_the_box_lp_reaches_9_at_0_3(normal_form_split):
    trail = Trail()
    x, y, s = _box(trail)
    objective = _objective(trail, (x, q(-1)), (y, q(-3)))
    assert bv.iterate_decrease(objective, trail) == q(-9)
    assert (_value(x), _value(y)) == (0, 3)
    assert _value(s) == 0


# ---------------------------------------------------------------- pivot row algebra

def _fraction_rows(variables):
    """Every linear form as {variable id: Fraction} plus the constant R + I."""
    rows = {}
    for x in variables:
        form = state_of(x).linear_form
        coefficients = {id(v): Fraction(*k) for v, k in form.terms}
        rows[id(x)] = (Fraction(*form.constant) + Fraction(*form.rest), coefficients)
    return rows


def _substitute(row, variable_id, definition):
    constant, coefficients = row
    if variable_id not in coefficients:
        return row
    k = coefficients[variable_id]
    result = {key: value for key, value in coefficients.items() if key != variable_id}
    for key, value in definition[1].items():
        result[key] = result.get(key, 0) + k * value
        if result[key] == 0:
            del result[key]
    return constant + k * definition[0], result


@pytest.mark.parametrize("seed", range(12))
def test_a_pivot_agrees_with_fraction_substitution(normal_form_split, seed):
    rng = random.Random(seed)
    trail = Trail()
    independents = []
    for _ in range(4):
        x = Var()
        assert bv.variable_intern(x, trail) is not None
        independents.append(x)
    dependents = []
    for _ in range(3):
        terms = [(x, q(rng.randint(-5, 5) or 1, rng.randint(1, 4)))
                 for x in independents]
        form = bv.dereference(_normal_form(q(rng.randint(-9, 9)), *terms), trail)
        d = Var()
        assert bv.variable_with_definition_intern(bounds_none(), d, form, 0, trail)
        dependents.append(d)
    every = independents + dependents
    before = _fraction_rows(every)
    dependent = dependents[rng.randrange(3)]
    independent = independents[rng.randrange(4)]
    # Dep = c + k*Indep + rest  gives  Indep = (Dep - c - rest)/k
    constant, coefficients = before[id(dependent)]
    k = coefficients[id(independent)]
    definition = ((-constant) / k,
                  {key: -value / k for key, value in coefficients.items()
                   if key != id(independent)})
    definition[1][id(dependent)] = 1 / k
    assert bv.pivot(dependent, independent, bounds_none(), trail)
    after = _fraction_rows(every)
    for x in every:
        if x is dependent:
            assert after[id(x)] == (0, {id(x): 1})
            continue
        if x is independent:
            assert after[id(x)] == definition
            continue
        assert after[id(x)] == _substitute(before[id(x)], id(independent), definition)


def test_pivot_moves_the_active_bound_into_the_rest():
    # pivot/3 writes -Abv into the rest of the new row (bv.pl lines 984-994).
    trail = Trail()
    x = _bounded(trail, bounds_lower_active(q(2)))
    form = LinearForm(q(1), ZERO, [(x, q(3))])
    d = Var()
    assert bv.variable_with_definition_intern(bounds_upper(q(10)), d, form, 0, trail)
    assert bv.pivot(d, x, bounds_upper_active(q(10)), trail)
    assert state_of(d).bounds == bounds_upper_active(q(10))
    # X = (D - 1)/3 with D at its active bound 10: the rest holds 10/3, so
    # X's value R + I is 3, and D's own row is D with the rest 10
    x_form = state_of(x).linear_form
    assert x_form.constant == q(-1, 3) and x_form.rest == q(10, 3)
    assert x_form.terms == [(d, q(1, 3))]
    assert _value(x) == 3
    d_form = state_of(d).linear_form
    assert (d_form.constant, d_form.rest, d_form.terms) == (ZERO, q(10), [(d, ONE)])


def test_pivot_without_the_bounds_ignores_them():
    trail = Trail()
    x = Var()
    bv.variable_intern(x, trail)
    d = Var()
    assert bv.variable_with_definition_intern(
        bounds_none(), d, LinearForm(q(4), ZERO, [(x, q(2))]), 0, trail)
    assert bv.pivot_ignoring_bounds(d, x, trail)
    x_form = state_of(x).linear_form
    assert (x_form.constant, x_form.rest, x_form.terms) == (q(-2), ZERO, [(d, q(1, 2))])


# ---------------------------------------------------------------- bound types

def test_deactivate_bound_drops_the_activity_only():
    trail = Trail()
    cases = [
        (bounds_lower(q(1)), bounds_lower(q(1))),
        (bounds_upper(q(1)), bounds_upper(q(1))),
        (bounds_lower_upper(q(1), q(2)), bounds_lower_upper(q(1), q(2))),
        (bounds_lower_active(q(1)), bounds_lower(q(1))),
        (bounds_upper_active(q(1)), bounds_upper(q(1))),
        (bounds_lower_active_upper(q(1), q(2)), bounds_lower_upper(q(1), q(2))),
        (bounds_lower_upper_active(q(1), q(2)), bounds_lower_upper(q(1), q(2))),
    ]
    for given, expected in cases:
        x = _bounded(trail, given)
        assert bv.deactivate_bound(given, x, trail)
        assert state_of(x).bounds == expected
    # bv.pl has no deactivate_bound/2 clause for t_none
    assert bv.deactivate_bound(bounds_none(), _bounded(trail, bounds_none()), trail) is False


def test_select_active_bound():
    assert bv.select_active_bound(bounds_lower_active(q(1))) == q(1)
    assert bv.select_active_bound(bounds_lower_active_upper(q(1), q(2))) == q(1)
    assert bv.select_active_bound(bounds_upper_active(q(2))) == q(2)
    assert bv.select_active_bound(bounds_lower_upper_active(q(1), q(2))) == q(2)
    for inactive in (bounds_none(), bounds_lower(q(1)), bounds_upper(q(1)),
                     bounds_lower_upper(q(1), q(2))):
        assert bv.select_active_bound(inactive) == ZERO


def test_bound_swap_delta_and_narrowing():
    assert bv.bound_swap_delta(bounds_lower_active_upper(q(1), q(4))) == q(-3)
    assert bv.bound_swap_delta(bounds_lower_upper_active(q(1), q(4))) == q(3)
    assert bv.bound_swap_delta(bounds_lower(q(1))) is None
    trail = Trail()
    x = _bounded(trail, bounds_upper(q(5)))
    assert bv.narrow_upper(bounds_upper(q(5)), x, q(4), trail)
    assert state_of(x).bounds == bounds_upper(q(4))
    assert bv.narrow_upper(bounds_lower_upper(q(1), q(5)), x, q(3), trail)
    assert state_of(x).bounds == bounds_lower_upper(q(1), q(3))
    assert bv.narrow_upper(bounds_lower(q(1)), x, q(3), trail) is False
    assert bv.narrow_lower(bounds_lower(q(1)), x, q(2), trail)
    assert state_of(x).bounds == bounds_lower(q(2))
    assert bv.narrow_lower(bounds_lower_upper(q(1), q(5)), x, q(2), trail)
    assert state_of(x).bounds == bounds_lower_upper(q(2), q(5))
    assert bv.narrow_lower(bounds_upper(q(1)), x, q(3), trail) is False


def test_determine_active_picks_the_bound_by_the_sign_of_k_times_s():
    trail = Trail()
    x = _bounded(trail, bounds_lower_upper(q(1), q(4)))
    y = _bounded(trail, bounds_lower_upper(q(1), q(4)))
    # K*S < 0 activates the lower bound, K*S > 0 the upper (case_signum)
    form = LinearForm(ZERO, ZERO, [(x, q(1)), (y, q(-1))])
    assert bv.determine_active_decrease(form, trail)
    assert state_of(x).bounds == bounds_lower_active_upper(q(1), q(4))
    assert state_of(y).bounds == bounds_lower_upper_active(q(1), q(4))
    # introduce_at moved the values into the rest of each form
    assert _value(x) == 1 and _value(y) == 4
    z = _bounded(trail, bounds_lower(q(2)))
    assert bv.determine_active_increase(LinearForm(ZERO, ZERO, [(z, q(-1))]), trail)
    assert state_of(z).bounds == bounds_lower_active(q(2))
    # bv.pl has no determine_active/4 clause for t_none: an unbounded
    # variable in the objective fails
    w = _bounded(trail, bounds_none())
    assert bv.determine_active_decrease(LinearForm(ZERO, ZERO, [(w, ONE)]), trail) is False


def test_undetermined_active_activates_the_lower_bound_first():
    trail = Trail()
    x = _bounded(trail, bounds_lower_upper(q(1), q(4)))
    u = _bounded(trail, bounds_upper(q(7)))
    assert bv.undetermined_active(LinearForm(ZERO, ZERO, [(x, ONE), (u, ONE)]), trail)
    assert state_of(x).bounds == bounds_lower_active_upper(q(1), q(4))
    assert state_of(u).bounds == bounds_upper_active(q(7))


def test_bound_inner_cases():
    trail = Trail()
    x = _bounded(trail, bounds_none())
    form = LinearForm(q(1), ZERO, [(x, q(2))])          # Dep = 1 + 2X
    assert bv.lower_bound_inner(bounds_lower(q(5)), x, form) == \
        (bounds_lower_active(q(5)), q(2))
    assert bv.lower_bound_inner(bounds_upper(q(5)), x, form) is None
    assert bv.upper_bound_inner(bounds_upper(q(5)), x, form) == \
        (bounds_upper_active(q(5)), q(2))
    assert bv.upper_bound_inner(bounds_lower(q(5)), x, form) is None
    assert bv.lower_bound_inner(bounds_lower_upper(q(-3), q(5)), x, form) == \
        (bounds_lower_active_upper(q(-3), q(5)), q(-2))
    assert bv.upper_bound_inner(bounds_lower_upper(q(-3), q(5)), x, form) == \
        (bounds_lower_upper_active(q(-3), q(5)), q(2))
    negative = LinearForm(q(1), ZERO, [(x, q(-2))])     # Dep = 1 - 2X
    assert bv.lower_bound_inner(bounds_lower_upper(q(-3), q(5)), x, negative) == \
        (bounds_lower_upper_active(q(-3), q(5)), q(-2))
    assert bv.upper_bound_inner(bounds_lower_upper(q(-3), q(5)), x, negative) == \
        (bounds_lower_active_upper(q(-3), q(5)), q(2))
    for active in (bounds_none(), bounds_lower_active(q(1))):
        assert bv.lower_bound_inner(active, x, form) is None


def test_bounds_record_and_strictness_bits():
    assert bounds_none() == Bounds(BOUNDS_NONE, None, None)
    assert repr(bounds_lower_upper_active(q(1), q(2))) == \
        "bounds_lower_upper_active((1, 1), (2, 1))"
    assert strictness_fields(0b10) == (True, False)
    assert strictness_fields(0b01) == (False, True)
    assert strictness(SolverState(lower_strict=True, upper_strict=True)) == 0b11


# ---------------------------------------------------------------- the basis under undo

def test_basis_add_drop_and_pivot_are_undone():
    trail = Trail()
    a = _bounded(trail, bounds_none())
    b = _bounded(trail, bounds_none())
    c = Var()
    form = LinearForm(ZERO, ZERO, [(a, ONE), (b, ONE)])
    assert bv.variable_with_definition_intern(bounds_upper(ZERO), c, form, 0, trail)
    assert bv.basis(c) is None                        # [] : no basis yet
    mark = trail.mark()
    assert list_elements(bv.basis_add(c, trail)) == [c]
    assert list_elements(bv.basis(a)) == [c]
    inner = trail.mark()
    assert bv.basis_pivot(c, a, trail)
    assert list_elements(bv.basis(a)) == [a]
    assert bv.basis_drop(a, trail)
    assert bv.basis(a) is None
    trail.undo(inner)
    assert list_elements(bv.basis(a)) == [c]
    trail.undo(mark)
    assert bv.basis(a) is None
    assert bv.basis(Var()) is False                   # no component: fails


def test_variable_intern_gives_one_component_and_keeps_existing_attributes():
    trail = Trail()
    x = Var()
    component = bv.variable_intern(x, trail)
    assert component is not None
    state = state_of(x)
    assert state.bounds == bounds_none() and strictness(state) == 0
    assert state.linear_form.terms == [(x, ONE)]
    assert is_var(state.variable_order)
    assert list_elements(component_all_variables(component)) == [x]
    assert deref(bv.variable_intern(x, trail)) is deref(component)
    bounded = _bounded(trail, bounds_lower(q(1)), strict=0b10)
    bv.variable_intern(bounded, trail)
    assert state_of(bounded).bounds == bounds_lower(q(1))
    assert state_of(bounded).lower_strict is True


def test_dereference_variable_makes_a_linear_variable_without_a_component():
    trail = Trail()
    x = Var()
    form = bv.dereference_variable(x, trail)
    assert form.terms == [(x, ONE)] and form.constant == ZERO
    assert state_of(x).component is None
    assert bv.dereference_variable(x, trail) is form


def test_dereference_folds_dependent_variables_in(normal_form_split):
    trail = Trail()
    x = Var()
    bv.variable_intern(x, trail)
    d = Var()
    assert bv.variable_with_definition_intern(
        bounds_none(), d, LinearForm(q(1), ZERO, [(x, q(2))]), 0, trail)
    form = bv.dereference(_normal_form(q(5), (d, q(3)), (x, q(-6))), trail)
    assert form.constant == q(8) and form.terms == []


# ---------------------------------------------------------------- solve and reconsider

def test_solve_binds_a_lone_variable_and_aliases_two_into_one_component(normal_form_split):
    trail = Trail()
    x = Var()
    assert bv.solve_equal(_normal_form(q(-3), (x, q(1))), trail)
    assert deref(x) == 3
    a, b = Var(), Var()
    assert bv.solve_equal(_normal_form(q(-3), (a, q(1)), (b, q(1))), trail)
    assert is_var(deref(a)) and is_var(deref(b))
    assert deref(state_of(a).component) is deref(state_of(b).component)
    # one of them is now dependent: its form holds the other
    forms = [state_of(a).linear_form, state_of(b).linear_form]
    assert sorted(len(f.terms) for f in forms) == [1, 1]
    assert any(f.constant == q(3) for f in forms)


def test_solve_fails_on_a_false_ground_equation(normal_form_split):
    assert bv.solve_equal(_normal_form(q(1)), Trail()) is False
    assert bv.solve_equal(_normal_form(ZERO), Trail()) is True


def test_solve_not_equal(normal_form_split):
    trail = Trail()
    assert bv.solve_not_equal(_normal_form(q(1)), trail) is True
    assert bv.solve_not_equal(_normal_form(ZERO), trail) is False
    x, y = Var(), Var()
    assert bv.solve_not_equal(_normal_form(q(1), (x, ONE), (y, ONE)), trail)
    assert deref(state_of(x).component) is deref(state_of(y).component)


def test_reconsider_finds_implied_values(normal_form_split):
    # X >= 0, Y >= 0, X + Y =< 0  implies  X = 0 and Y = 0
    trail = Trail()
    x = _bounded(trail, bounds_lower(ZERO))
    y = _bounded(trail, bounds_lower(ZERO))
    s, ok = _slack(trail, ZERO, (x, ONE), (y, ONE))
    assert ok
    assert deref(x) == 0 and deref(y) == 0


def test_reconsider_fails_on_an_infeasible_row(normal_form_split):
    # X >= 1, Y >= 0, X + Y =< 0
    trail = Trail()
    x = _bounded(trail, bounds_lower(q(1)))
    y = _bounded(trail, bounds_lower(ZERO))
    s, ok = _slack(trail, ZERO, (x, ONE), (y, ONE))
    assert ok is False


def test_reconsider_respects_strictness_at_the_optimum(normal_form_split):
    # X >= 0, Y >= 0, X + Y < 0 : the optimum meets a strict bound, fails
    trail = Trail()
    x = _bounded(trail, bounds_lower(ZERO))
    y = _bounded(trail, bounds_lower(ZERO))
    s, ok = _slack(trail, ZERO, (x, ONE), (y, ONE), strict=0b01)
    assert ok is False


def test_reconsider_pivots_an_infeasible_row_into_range(normal_form_split):
    # 2 =< X =< 5, Y >= 0, X + Y =< 3 is feasible; inf(X + Y) = 2
    trail = Trail()
    x = _bounded(trail, bounds_lower_upper(q(2), q(5)))
    y = _bounded(trail, bounds_lower(ZERO))
    s, ok = _slack(trail, q(-3), (x, ONE), (y, ONE))
    assert ok
    assert 2 <= _value(x) + _value(y) <= 3
    objective = _objective(trail, (x, ONE), (y, ONE))
    assert bv.iterate_decrease(objective, trail) == q(2)
    objective = _objective(trail, (x, q(-1)), (y, q(-1)))
    assert bv.iterate_decrease(objective, trail) == q(-3)


def test_detach_bounds_drops_a_dependent_from_the_basis(normal_form_split):
    trail = Trail()
    x, y, s = _box(trail)
    assert list_elements(bv.basis(x)) == [s]
    assert bv.detach_bounds(s, trail)
    assert bv.basis(x) is None
    assert state_of(s).bounds == bounds_none()


def test_unconstrained_selects_a_free_variable():
    trail = Trail()
    x = _bounded(trail, bounds_lower(ZERO))
    free = _bounded(trail, bounds_none())
    form = LinearForm(q(1), ZERO, [(x, q(2)), (free, q(3))])
    variable, coefficient, rest = bv.unconstrained(form)
    assert variable is free and coefficient == q(3)
    assert rest.terms == [(x, q(2))]
    assert bv.unconstrained(LinearForm(q(1), ZERO, [(x, q(2))])) is None


def test_preference_takes_the_lower_category_and_the_later_on_ties():
    assert bv.preference((2, "a", ONE), (2, "b", ONE)) == (2, "b", ONE)
    assert bv.preference((1, "a", ONE), (3, "b", ONE)) == (1, "a", ONE)
    assert bv.preference((4, "a", ONE), (3, "b", ONE)) == (3, "b", ONE)


def test_export_binding():
    from clausal.logic.variables import Var as V
    trail = Trail()
    x = V()
    assert bv.export_binding(x, q(1, 2), trail) and deref(x) == Fraction(1, 2)
    y = V()
    assert bv.export_binding(ZERO, y, trail) and deref(y) == 0
    z = V()
    assert bv.export_bindings([(z, q(7))], trail) and deref(z) == 7
    assert bv.export_binding(q(2), z, trail) is False


# ---------------------------------------------------------------- dump

def test_dump_variable_writes_bounds_with_their_strictness():
    trail = Trail()
    x = _bounded(trail, bounds_none())
    v = Var()
    assert bv.variable_with_definition_intern(
        bounds_lower_upper(q(1), q(4)), v, LinearForm(q(2), ZERO, [(x, q(2))]),
        0b10, trail)
    form = state_of(v).linear_form
    result = bv.dump_variable(state_of(v).bounds, v, form.constant, form.terms)
    # 2 + 2X > 1  is  X > -1/2 ;  2 + 2X =< 4  is  X =< 1
    assert result == [(">", x, q(-1, 2)), ("=<", x, q(1))]
    assert bv.dump_variable(bounds_none(), x, ZERO, [(x, ONE)]) == []
    assert bv.dump_variable(bounds_none(), v, q(2), [(x, q(2))]) == \
        [("=", v, ("+", q(2), ("*", q(2), x)))]
    assert bv.dump_disequation(v, [(x, q(2))], q(4)) == [("=\\=", x, q(-2))]
    assert bv.dump_strict(0, "n", "s") == "n"
    assert bv.dump_strict(2, "n", "s") == "s"


# ---------------------------------------------------------------- depth

def test_long_rows_and_long_bases_need_no_recursion(normal_form_split):
    trail = Trail()
    count = 3000
    xs = [_bounded(trail, bounds_lower_upper(ZERO, ONE)) for _ in range(count)]
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 150)
    try:
        # one slack over every variable: sum X =< count/2
        s, ok = _slack(trail, q(-(count // 2)), *[(x, ONE) for x in xs])
        assert ok
        # many basis rows: X_i - X_{i+1} =< 0 for a stretch
        for i in range(200):
            _, ok = _slack(trail, ZERO, (xs[i], ONE), (xs[i + 1], q(-1)))
            assert ok
        objective = _objective(trail, *[(x, q(-1)) for x in xs[:40]])
        assert bv.iterate_decrease(objective, trail) == q(-40)
    finally:
        sys.setrecursionlimit(limit)


def _lower_bounded_row(strict):
    """X =< 0, Y =< 0 and a dependent S = X + Y with the lower bound 0."""
    trail = Trail()
    x = _bounded(trail, bounds_upper(ZERO))
    y = _bounded(trail, bounds_upper(ZERO))
    form = LinearForm(ZERO, ZERO, [(x, ONE), (y, ONE)])
    s = Var()
    assert bv.variable_with_definition_intern(bounds_lower(ZERO), s, form,
                                              strict, trail)
    assert bv.basis_add(s, trail) is not False
    assert bv.determine_active_increase(form, trail)
    return trail, x, y, s


def test_an_optimum_meeting_a_lower_bound_implies_values_unless_strict():
    trail, x, y, s = _lower_bounded_row(0b00)
    assert bv.reconsider(s, trail)
    assert deref(x) == 0 and deref(y) == 0
    trail, x, y, s = _lower_bounded_row(0b10)
    assert bv.reconsider(s, trail) is False


def test_a_failed_step_in_reconsider_basis_variable_is_undone(monkeypatch):
    # The step's condition fails after the bound swap changed X's type; 1.3.3
    # undoes that by failing, the port by undoing to its mark.
    trail = Trail()
    x = _bounded(trail, bounds_lower_active_upper(ZERO, q(2)))
    s = Var()
    assert bv.variable_with_definition_intern(
        bounds_lower(ONE), s, LinearForm(ZERO, ZERO, [(x, ONE)]), 0, trail)
    assert bv.basis_add(s, trail) is not False
    monkeypatch.setattr(bv, "back_substitute_delta", lambda *arguments: False)
    assert bv.reconsider_basis_variable(s, trail) is None
    assert state_of(x).bounds == bounds_lower_active_upper(ZERO, q(2))


def test_solving_an_old_free_variable_binds_the_rows_that_become_constant(
        normal_form_split):
    # X + Y = 3, then X = 1: category 2 in one component is rank increasing,
    # so Y's row becomes constant and Y is bound too.
    trail = Trail()
    x, y = Var(), Var()
    assert bv.solve_equal(_normal_form(q(-3), (x, ONE), (y, ONE)), trail)
    assert bv.solve_equal(_normal_form(q(-1), (x, ONE)), trail)
    assert deref(x) == 1 and deref(y) == 2


def test_a_cascade_of_implied_values_needs_no_recursion(normal_form_split):
    # X_i >= 0 and sum X_i =< 0: every implied X_i = 0 is found by a solve/5
    # that 1.3.3 calls in tail position from rcbl_opt, which then calls rcbl
    # again; one level per variable.
    trail = Trail()
    count = 300
    xs = [_bounded(trail, bounds_lower(ZERO)) for _ in range(count)]
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 150)
    try:
        _, ok = _slack(trail, ZERO, *[(x, ONE) for x in xs])
    finally:
        sys.setrecursionlimit(limit)
    assert ok
    assert all(deref(x) == 0 for x in xs)


def test_dereference_of_a_non_linear_monomial_raises(normal_form_split):
    # DEVIATIONS.md D9: 1.3.3's dereference_balanced/4 recurses without end.
    trail = Trail()
    x = Var()
    with pytest.raises(ValueError):
        bv.dereference([_Monomial(ONE, [(x, 2)])], trail)
    with pytest.raises(ValueError):
        bv.dereference([_Monomial(ONE, [(x, 1)]), _Monomial(ONE, [(x, 1), (Var(), 1)])],
                       trail)


def test_select_dependent_orders_components_by_creation():
    # DEVIATIONS.md D4: ClassesUniq is an ordered set of component variables.
    trail = Trail()
    a = _bounded(trail, bounds_none())
    b = _bounded(trail, bounds_lower(ZERO))
    c = Var()
    components, chosen, new_variables = bv.select_dependent(
        [(b, ONE), (a, ONE), (c, ONE), (b, q(2))])
    assert components == [deref(state_of(a).component), deref(state_of(b).component)]
    assert components[0]._id < components[1]._id
    assert new_variables == [c]
    assert chosen[:2] == (2, a)          # category 2 (old, t_none) beats 3 and 4


def test_export_binding_of_two_variables_unifies_them():
    # bv.pl export_binding/2 clause 1: var(Y), Y = X, whatever X is
    trail = Trail()
    x, y = Var(), Var()
    assert bv.export_binding(x, y, trail)
    assert deref(x) is deref(y)
    z = Var()
    assert bv.export_binding(z, ZERO, trail) and deref(z) == 0


def test_decrease_evaluate_returns_unlimited_after_a_listed_term():
    # DEVIATIONS.md D10: 1.3.3 gives [Delta-Action|unlimited(V, T)] here
    trail = Trail()
    x = _bounded(trail, bounds_upper_active(q(5)))
    s = Var()
    assert bv.variable_with_definition_intern(
        bounds_lower(ZERO), s, LinearForm(q(5), ZERO, [(x, ONE)]), 0, trail)
    assert bv.basis_add(s, trail) is not False
    free = _bounded(trail, bounds_none())
    evaluated = bv.decrease_evaluate([(x, ONE)])
    assert type(evaluated) is list and len(evaluated) == 1
    status = bv.decrease_evaluate([(x, ONE), (free, ONE)])
    assert status == (bv.STATUS_UNLIMITED, free, bounds_none())


def test_float_of_is_rational_to_float():
    # bv.pl's float(X) in Q is arith.pl's rational_to_float/3, with its
    # limit_encoding_length/5; the port's _float_of is that function.
    from clausal.logic.clpq.arithmetic import rational_to_float
    huge = (10**400 + 1, 3 * 10**399)
    assert bv._float_of(huge) == rational_to_float(huge) == pytest.approx(10 / 3)
    assert bv._float_of((-7, 2)) == -3.5


def test_inf_2_passes_lists_for_vector_and_vertex():
    # inf/2 is inf(Expression, Inf, [], []), as bv.pl's inf/2 calls inf/4.
    from clausal.logic.clpq.normal_form import post_constraint
    from clausal.pythonic_ast.nodes import LtE
    seen = []
    original = bv.infimum_linear

    def spy(normal_form, argument, trail):
        seen.append(argument[1:])
        return original(normal_form, argument, trail)

    trail = Trail()
    x = Var()
    assert post_constraint(LtE(left=1, right=x), trail)
    bv.infimum_linear = spy
    try:
        assert bv.inf(x, Var(), trail)
    finally:
        bv.infimum_linear = original
    assert seen == [([], [])]
