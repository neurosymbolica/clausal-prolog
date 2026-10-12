# tests/clpq_port/test_residuals.py
"""Task 12: fourmotz.pl, redund.pl, project.pl and dump.pl
(fourier_motzkin.py, redundancy.py, projection.py, residual_constraints.py).

Stores are built through nf.pl (normal_form.post_constraint) with compound
cells.  The oracle comparisons of residuals are in test_against_oracle.py.
"""
import random
import re
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import fourier_motzkin as fm
from clausal.logic.clpq.arithmetic import ONE, ZERO, make_rational, to_number
from clausal.logic.clpq.attributes import (
    BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE, BOUNDS_LOWER_ACTIVE_UPPER,
    BOUNDS_LOWER_UPPER, BOUNDS_LOWER_UPPER_ACTIVE, BOUNDS_NONE, BOUNDS_UPPER,
    BOUNDS_UPPER_ACTIVE, bounds_lower, bounds_lower_active,
    bounds_lower_active_upper, bounds_lower_upper, bounds_lower_upper_active,
    bounds_none, bounds_upper, bounds_upper_active, state_of)
from clausal.logic.clpq.components import COMPONENT_KEY, list_elements
from clausal.logic.clpq.linear_forms import (
    independent, normal_form_coefficient_of)
from clausal.logic.clpq.normal_form import post_constraint
from clausal.logic.variables import Trail, Var, deref, get_attr, is_var


def q(numerator, denominator=1):
    return make_rational(numerator, denominator)


def _post(trail, *constraints):
    for constraint in constraints:
        assert post_constraint(constraint, trail), constraint


def _form_term(form):
    """constant + sum K*X of a linear form, as a cell with engine numbers:
    the value the row's variable equals (the rest is the current value's
    bookkeeping, not part of the equation)."""
    term = to_number(form.constant)
    for variable, coefficient in form.terms:
        term = ("+", term, ("*", to_number(coefficient), variable))
    return term


def _implied(trail, negation):
    """The store makes *negation* unsatisfiable (and is left as it was)."""
    mark = trail.mark()
    try:
        return not post_constraint(negation, trail)
    finally:
        trail.undo(mark)


def _snapshot(variables):
    states = {}
    for x in variables:
        state = state_of(x)
        states[id(x)] = state
        if state is not None and state.component is not None:
            states[("component", id(x))] = get_attr(state.component, COMPONENT_KEY)
    return states


def _random_store(seed, trail):
    """The fuzz store: 2 to 6 variables, 4 to 12 constraints mixing <, =<
    and =.  Returns (variables, constraint cells), or None where the store
    is unsatisfiable."""
    rng = random.Random(seed)
    variables = [Var() for _ in range(rng.randint(2, 6))]
    constraints = []
    for _ in range(rng.randint(4, 12)):
        chosen = rng.sample(variables, rng.randint(1, min(3, len(variables))))
        term = None
        for variable in chosen:
            product = ("*", rng.choice([-3, -2, -1, 1, 2, 3]), variable)
            term = product if term is None else ("+", term, product)
        relation = rng.choice(["<", "=<", "=<", "<", "="])
        constraints.append((relation, term, rng.randint(-6, 6)))
    for constraint in constraints:
        if not post_constraint(constraint, trail):
            return None
    return variables, constraints


# ============================================================== fourmotz.pl

def test_lower_and_upper_read_the_bound_types():
    l, u = q(1), q(2)
    assert [fm.lower(b) for b in (bounds_lower(l), bounds_lower_upper(l, u),
                                  bounds_lower_active(l),
                                  bounds_lower_active_upper(l, u),
                                  bounds_lower_upper_active(l, u))] == [l] * 5
    assert [fm.upper(b) for b in (bounds_upper(u), bounds_lower_upper(l, u),
                                  bounds_upper_active(u),
                                  bounds_lower_active_upper(l, u),
                                  bounds_lower_upper_active(l, u))] == [u] * 5
    assert fm.lower(bounds_none()) is None and fm.lower(bounds_upper(u)) is None
    assert fm.upper(bounds_none()) is None and fm.upper(bounds_lower(l)) is None
    assert fm.lower(bounds_upper_active(u)) is None
    assert fm.upper(bounds_lower_active(l)) is None


def test_flip_follows_the_table():
    l, u = q(1), q(2)
    assert fm.flip(bounds_lower(l)) == bounds_upper(l)
    assert fm.flip(bounds_upper(u)) == bounds_lower(u)
    assert fm.flip(bounds_lower_upper(l, u)) == bounds_lower_upper(u, l)
    assert fm.flip(bounds_lower_active(l)) == bounds_upper(l)
    assert fm.flip(bounds_upper_active(u)) == bounds_lower(u)
    assert fm.flip(bounds_lower_upper_active(l, u)) == bounds_lower_upper(u, l)
    assert fm.flip(bounds_lower_active_upper(l, u)) == bounds_lower_upper(u, l)
    assert fm.flip(bounds_none()) is None                  # no clause


def test_flip_strict_swaps_the_two_bits():
    assert [fm.flip_strict(s) for s in (0b00, 0b01, 0b10, 0b11)] == \
        [0b00, 0b10, 0b01, 0b11]


def test_member_with_rest_and_select_nth():
    assert fm.member_with_rest(["a", "b", "c"]) == \
        [("a", ["b", "c"]), ("b", ["c"]), ("c", [])]
    assert fm.select_nth(["a", "b", "c"], 2) == ("b", ["a", "c"])
    assert fm.select_nth(["a", "b", "c"], 1) == ("a", ["b", "c"])
    assert fm.select_nth(["a"], 1) == ("a", [])


def test_occurrence_type_filter_excludes_only_bounds_none():
    assert not fm.occurrence_type_filter(bounds_none())
    for bounds in (bounds_lower(q(0)), bounds_upper(q(0)),
                   bounds_lower_upper(q(0), q(1)), bounds_lower_active(q(0)),
                   bounds_upper_active(q(0)),
                   bounds_lower_upper_active(q(0), q(1)),
                   bounds_lower_active_upper(q(0), q(1))):
        assert fm.occurrence_type_filter(bounds)


def test_occurences_lists_each_bounded_row_holding_the_variable():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 0), ("=<", ("+", x, y), 3), (">=", y, -1))
    for variable in (x, y):
        occurrences = fm.occurences(variable)
        members = [deref(m) for m in list_elements(bv.all_variables(variable))]
        expected = []
        for member in members:
            state = state_of(member)
            if state is None or state.linear_form is None \
                    or state.bounds.kind == BOUNDS_NONE:
                continue
            k = normal_form_coefficient_of(state.linear_form, variable)
            if k is not None:
                expected.append((member, k))
        assert [(deref(d), k) for d, k in occurrences] == expected
        assert fm.occurs(variable) == bool(expected)


def test_a_variable_without_bounded_rows_does_not_occur():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", x, ("+", y, 1)))            # one row, no bounds
    assert fm.occurences(y) == [] and not fm.occurs(y)
    assert fm.occurences(Var()) is None and not fm.occurs(Var())


def _independent_with_occurrences(trail, seed):
    found = _random_store(seed, trail)
    if found is None:
        return []
    result = []
    for variable in found[0]:
        variable = deref(variable)
        if not is_var(variable):
            continue
        state = state_of(variable)
        if state is None or state.linear_form is None:
            continue
        if independent(state.linear_form, variable):
            occurrences = fm.occurences(variable)
            if occurrences:
                result.append((variable, occurrences))
    return result


@pytest.mark.parametrize("seed", range(40))
def test_cross_product_cardinality_counts_the_cross_product(seed):
    trail = Trail()
    for _, occurrences in _independent_with_occurrences(trail, seed):
        assert fm.cross_product_cardinality(occurrences, 0) == \
            len(fm.crossproduct(occurrences))


@pytest.mark.parametrize("seed", range(40))
def test_every_cross_product_inequality_is_implied_by_the_store(seed):
    # Each less_or_equal_zero(Strict, Lin): Lin < 0 (strict) or Lin =< 0
    # holds wherever the store does, so its negation cannot be posted.
    trail = Trail()
    checked = 0
    for variable, occurrences in _independent_with_occurrences(trail, seed):
        for strict, form in fm.crossproduct(occurrences):
            assert normal_form_coefficient_of(form, variable) is None
            negation = (">=" if strict else ">", _form_term(form), 0)
            assert _implied(trail, negation), (strict, form)
            checked += 1
    assert checked >= 0


def test_the_cross_product_eliminates_between_a_lower_and_an_upper_bound():
    # X >= 1 (X's own row) and the slack row of X + Y =< 3 (Y bounded
    # first, so no unconstrained variable absorbs the slack) cross to
    # Y =< 2.
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 1), (">=", y, 0), ("=<", ("+", x, y), 3))
    pairs = fm.crossproduct(fm.occurences(x))
    assert len(pairs) == 1
    strict, form = pairs[0]
    assert strict == 0
    assert _implied(trail, (">", _form_term(form), 0))
    assert not _implied(trail, (">", ("+", _form_term(form), 1), 0))


def test_strictness_carries_through_the_cross_product():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">", x, 1), (">=", y, 0), ("=<", ("+", x, y), 3))
    ((strict, _),) = fm.crossproduct(fm.occurences(x))
    assert strict == 1
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 1), (">=", y, 0), ("<", ("+", x, y), 3))
    ((strict, _),) = fm.crossproduct(fm.occurences(x))
    assert strict == 1


def test_strictness_carries_through_cross_upper():
    # X < 1 and Y - X =< 2 (coefficients of opposite sign, both upper
    # bounds) cross to Y - 3 < 0, strict.
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", y, 0), ("<", x, 1), ("=<", ("-", y, x), 2))
    ((strict, form),) = fm.crossproduct(fm.occurences(x))
    assert strict == 1
    assert form.constant == q(-3) and form.terms == [(y, ONE)]


def test_prefilter_keeps_nontargets_that_occur_and_marks_them():
    trail = Trail()
    x, y, z, w = Var(), Var(), Var(), Var()
    _post(trail, (">=", x, 0), (">=", y, 0), ("=", z, ("+", x, y)))
    bv._put_attributes(y, trail, target=True)
    kept = fm.prefilter([x, y, z, w], trail)
    assert kept == [x]
    assert state_of(x).keep_independent
    assert not state_of(y).keep_independent


def test_best_takes_the_smallest_growth_first_in_list_order():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, (">=", x, 0), (">=", y, 0), ("=<", ("+", x, y), 4))
    found = fm.best([z, x, y])
    assert found is not None
    chosen, rest = found
    deltas = {}
    for variable in (x, y):
        occurrences = fm.occurences(variable)
        deltas[id(variable)] = (fm.cross_product_cardinality(occurrences, 0)
                                - len(occurrences))
    least = min(deltas.values())
    first = [v for v in (x, y) if deltas[id(v)] == least][0]
    assert chosen is first
    assert rest == [v for v in [z, x, y] if v is not first]
    assert fm.best([z]) is None


def test_fourier_motzkin_detach_drops_the_bounds_of_every_occurrence():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 0), ("=<", ("+", x, y), 3))
    occurrences = fm.occurences(x)
    assert fm.fourier_motzkin_detach(occurrences, trail)
    for dependent, _ in occurrences:
        assert state_of(dependent).bounds.kind == BOUNDS_NONE


def test_activate_crossproduct_adds_each_row_to_the_basis():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 1), (">=", y, 0), ("=<", ("+", x, y), 3))
    new = fm.crossproduct(fm.occurences(x))
    before = list_elements(bv.basis(x))
    assert fm.activate_crossproduct(new, trail)
    after = list_elements(bv.basis(x))
    assert len(after) == len(before) + len(new)
    added = deref(after[0])
    assert state_of(added).bounds == bounds_upper(ZERO)
    assert not _implied(trail, ("=", y, 2))       # Y =< 2 still allows 2
    assert _implied(trail, (">", y, 2))


def test_the_cross_product_property_tests_see_pairs():
    # The two seeded property tests above are not vacuous.
    pairs = 0
    for seed in range(40):
        trail = Trail()
        for _, occurrences in _independent_with_occurrences(trail, seed):
            pairs += len(fm.crossproduct(occurrences))
    assert pairs >= 10


# ============================================================== redund.pl

from clausal.logic.clpq import redundancy as rd  # noqa: E402


def test_strictness_parts_splits_the_bits():
    assert rd.strictness_parts(0b11) == (0b10, 0b01)
    assert rd.strictness_parts(0b10) == (0b10, 0)
    assert rd.strictness_parts(0b01) == (0, 0b01)


def test_negate_lower_is_true_where_the_store_implies_the_bound():
    # X - Y >= 0, Y >= 1: X >= 1 is implied, X >= 2 and X > 1 are not.
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", ("-", x, y), 0), (">=", y, 1))
    assert rd.negate_lower(0b00, q(1), x, trail)
    assert rd.negate_lower(0b01, q(1), x, trail)       # upper bit: still >=
    assert not rd.negate_lower(0b00, q(2), x, trail)
    assert not rd.negate_lower(0b10, q(1), x, trail)   # X > 1 is not implied
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", ("-", x, y), 0), (">", y, 1))
    assert rd.negate_lower(0b10, q(1), x, trail)       # X > 1 is implied


def test_negate_upper_is_true_where_the_store_implies_the_bound():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=<", ("-", x, y), 0), ("<", y, 3))
    assert rd.negate_upper(0b00, q(3), x, trail)
    assert rd.negate_upper(0b01, q(3), x, trail)       # X < 3 is implied
    assert not rd.negate_upper(0b01, q(2), x, trail)
    assert rd.negate_upper(0b10, q(3), x, trail)       # lower bit: =<


def test_negate_lower_leaves_the_store_as_it_was():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", ("-", x, y), 0), (">=", y, 1))
    before = _snapshot([x, y])
    length = len(trail)
    assert not rd.negate_lower(0b00, q(2), x, trail)   # the post succeeded
    assert rd.negate_lower(0b00, q(1), x, trail)       # the post failed
    assert len(trail) == length
    assert _snapshot([x, y]) == before


def test_a_redundant_lower_bound_is_dropped():
    # Z >= 1, X >= Z, X >= 0: X >= 0 is implied.
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">=", x, 0), (">=", z, 1), (">=", ("-", x, z), 0))
    assert state_of(x).bounds.kind in (BOUNDS_LOWER, BOUNDS_LOWER_ACTIVE)
    assert rd.redundancy_variable_list([x], trail)
    assert state_of(x).bounds.kind == BOUNDS_NONE
    assert _implied(trail, ("<", x, 1))                # still X >= 1


def test_a_bound_that_is_not_redundant_comes_back():
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">=", x, 2), (">=", z, 1), (">=", ("-", x, z), 0))
    before = state_of(x).bounds
    assert rd.redundancy_variable_list([x, z], trail)
    assert state_of(x).bounds.lower == before.lower
    assert _implied(trail, ("<", x, 2))


def test_of_two_bounds_only_the_redundant_one_goes():
    # 0 =< X < 5 with X >= Z >= 1: the lower bound goes, the strict upper
    # stays strict (strictness_parts/3).
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">=", x, 0), ("<", x, 5), (">=", z, 1),
          (">=", ("-", x, z), 0))
    bounds = state_of(x).bounds
    assert bounds.lower is not None and bounds.upper is not None
    assert rd.redundancy_variable_list([x], trail)
    state = state_of(x)
    assert state.bounds.lower is None and state.bounds.upper == q(5)
    assert state.upper_strict and not state.lower_strict
    assert _implied(trail, (">=", x, 5)) and _implied(trail, ("<", x, 1))


def test_t_lU_drops_the_lower_bound_and_keeps_the_strict_active_upper():
    # The intro-free branch of redundant(t_lU): put t_U(U), strictness Su.
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">=", x, 0), ("<", x, 5), (">=", z, 1),
          (">=", ("-", x, z), 0))
    assert state_of(x).bounds == bounds_lower_upper_active(q(0), q(5))
    assert rd.redundancy_variable_list([x], trail)
    state = state_of(x)
    assert state.bounds == bounds_upper_active(q(5))
    assert state.upper_strict and not state.lower_strict
    assert _implied(trail, (">=", x, 5))


def test_t_Lu_drops_the_upper_bound_and_keeps_the_strict_active_lower():
    # redundant(t_Lu): the first branch (intro_at to t_u(U)) finds the lower
    # bound needed and is undone; the second puts t_L(L), strictness Sl.
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">", x, 0), ("=<", x, 5), ("=<", z, 2),
          ("=<", ("-", x, z), 0))
    assert state_of(x).bounds == bounds_lower_active_upper(q(0), q(5))
    assert rd.redundancy_variable_list([x], trail)
    state = state_of(x)
    assert state.bounds == bounds_lower_active(q(0))
    assert state.lower_strict and not state.upper_strict
    assert _implied(trail, ("=<", x, 0)) and _implied(trail, (">", x, 2))


def test_t_Lu_with_a_redundant_lower_bound_keeps_the_upper_one():
    # redundant(t_Lu)'s first branch: intro_at(X, -L, t_u(U)) and Su.
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">", x, 0), ("<", x, 5), (">=", z, 1),
          (">=", ("-", x, z), 0))
    kind = state_of(x).bounds.kind
    assert kind in (BOUNDS_LOWER_ACTIVE_UPPER, BOUNDS_LOWER_UPPER_ACTIVE)
    assert rd.redundancy_variable_list([x], trail)
    state = state_of(x)
    assert state.bounds.lower is None and state.bounds.upper == q(5)
    assert state.upper_strict and not state.lower_strict
    assert _implied(trail, (">=", x, 5)) and _implied(trail, ("<", x, 1))


@pytest.mark.parametrize("seed", range(60))
def test_redundancy_keeps_the_solution_set(seed):
    # Dropping a redundant bound never changes what the store allows: each
    # original constraint is still implied, strictness included.
    trail = Trail()
    found = _random_store(seed, trail)
    if found is None:
        return
    variables, constraints = found
    members = []
    for variable in variables:
        variable = deref(variable)
        if is_var(variable) and bv.all_variables(variable) is not None:
            members.extend(list_elements(bv.all_variables(variable)))
    assert rd.redundancy_variable_list(members, trail)
    for relation, term, bound in constraints:
        negation = {"<": ">=", "=<": ">", "=": "=\\="}[relation]
        assert _implied(trail, (negation, term, bound)), (relation, term, bound)


def test_systems_lists_each_component_once_newest_first():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, (">=", x, 0), (">=", ("+", y, z), 1))
    found = rd.systems([x, y, z, Var(), 3], [])
    component_x = deref(state_of(x).component)
    component_y = deref(state_of(y).component)
    assert found == [component_y, component_x]
    assert rd.not_member_identical(found, deref(Var()))
    assert not rd.not_member_identical(found, component_x)


def test_redundancy_systems_walks_each_component():
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">=", x, 0), (">=", z, 1), (">=", ("-", x, z), 0))
    assert rd.redundancy_systems(rd.systems([x], []), trail)
    assert state_of(x).bounds.kind == BOUNDS_NONE


def test_the_profiling_markers_succeed():
    assert rd.redundant_bounds_lower() and rd.redundant_bounds_upper()
    assert rd.redundant_bounds_lower_active() and rd.redundant_bounds_upper_active()


# ============================================================== project.pl

from clausal.logic.clpq import projection as pj  # noqa: E402


def test_sort_variables():
    a, b, c = Var(), Var(), Var()
    assert pj.sort_variables([c, a, b, a, 7]) == [a, b, c, 7]


def test_mark_target_and_mark_keep():
    trail = Trail()
    x, y = Var(), Var()
    pj.mark_target([x], trail)
    pj.mark_keep([y], trail)
    assert state_of(x).target and not state_of(x).keep
    assert state_of(y).keep and not state_of(y).target


def test_nontarget_skips_targets_and_kept_independents():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    pj.mark_target([x], trail)
    bv._put_attributes(y, trail, keep_independent=True)
    bv._put_attributes(z, trail)
    terms = [(x, ONE), (y, ONE), (z, ONE)]
    assert pj.nontarget(terms) is z
    assert pj.nontarget(terms[:2]) is None


def test_make_target_independent_pivots_a_dependent_target():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, (">=", y, 0), (">=", z, 0), ("=", x, ("+", y, z)))
    assert not independent(state_of(x).linear_form, x)
    pj.mark_target([x], trail)
    pivots = pj.make_target_independent([x], trail)
    assert len(pivots) == 1 and pivots[0][0] is x
    partner = pivots[0][1]
    assert independent(state_of(x).linear_form, x)
    assert state_of(partner).keep
    assert not independent(state_of(partner).linear_form, partner)
    assert _implied(trail, ("=\\=", x, ("+", y, z)))   # same store


def _dependent_and_independent(variables):
    dependent = [v for v in variables
                 if not independent(state_of(v).linear_form, v)]
    others = [v for v in variables if v not in dependent]
    return dependent, others


def test_drop_dependent_one_needs_every_condition():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, ("=", x, ("+", y, z)))
    (dependent,), independents = _dependent_and_independent([x, y, z])
    pj.drop_dependent_one(independents[0], trail)      # independent: kept
    assert state_of(independents[0]).linear_form is not None
    for field in ("target", "keep", "nonzero"):
        mark = trail.mark()
        bv._put_attributes(dependent, trail, **{field: True})
        pj.drop_dependent_one(dependent, trail)
        assert state_of(dependent).linear_form is not None, field
        trail.undo(mark)
    pj.drop_dependent([x, y, z], trail)
    state = state_of(dependent)
    assert state.linear_form is None and state.bounds is None
    assert state.component is None and state.variable_order is None
    for variable in independents:
        assert state_of(variable).linear_form is not None


def test_drop_linear_attributes():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 1))
    pj.drop_linear_attributes([x, y], trail)
    assert state_of(x).linear_form is None and state_of(x).bounds is None
    assert state_of(y) is None


def test_variable_order_numbers_the_unnumbered():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, ("=", x, ("+", y, z)))
    assert pj.variable_order([z, x], 1, trail) == 3
    assert deref(state_of(z).variable_order) == 1
    assert deref(state_of(x).variable_order) == 2
    assert pj.variable_order([x, y], 3, trail) == 4     # x already numbered
    assert deref(state_of(y).variable_order) == 3


def test_arrange_pivots_rows_whose_first_variable_now_comes_first():
    # After numbering, a t_none row D whose first variable I has the
    # smaller number is pivoted: I becomes the dependent one.
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", x, ("+", ("*", 2, y), 1)))
    (dependent,), (other,) = _dependent_and_independent([x, y])
    component = deref(state_of(x).component)
    assert pj.arrange([other, dependent], component, trail)
    assert independent(state_of(dependent).linear_form, dependent)
    assert not independent(state_of(other).linear_form, other)
    assert _implied(trail, ("=\\=", x, ("+", ("*", 2, y), 1)))


def test_arrange_leaves_a_row_whose_first_variable_comes_after_it():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", x, ("+", ("*", 2, y), 1)))
    (dependent,), (other,) = _dependent_and_independent([x, y])
    component = deref(state_of(x).component)
    assert pj.arrange([dependent, other], component, trail)
    assert not independent(state_of(dependent).linear_form, dependent)


def test_renormalize_all_and_arrange_pivot_fail_on_a_closed_list():
    from clausal.logic.clpq.components import closed_list
    trail = Trail()
    assert not pj.renormalize_all(closed_list([]), trail)
    assert not pj.arrange_pivot(closed_list([]), trail)


def test_impose_ordering_follows_ordering_1():
    from clausal.logic.clpq.variable_ordering import ordering
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", x, ("+", ("*", 2, y), 1)))
    (dependent,), (other,) = _dependent_and_independent([x, y])
    assert ordering([other, dependent], trail)
    assert pj.impose_ordering([x, y], trail)
    assert independent(state_of(dependent).linear_form, dependent)
    assert not independent(state_of(other).linear_form, other)


def test_project_attributes_with_no_targets_drops_everything():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", ("+", x, y), 1))
    related = [deref(v) for v in list_elements(bv.all_variables(x))]
    assert pj.project_attributes([], related, trail)
    for variable in related:
        assert state_of(variable).linear_form is None


# ============================================================== dump.pl

from clausal.logic.clpq import residual_constraints as rc  # noqa: E402
from clausal.logic.clpq.delayed_goals import (  # noqa: E402
    _term_variables, delay_goal, project_nonlinear)
from clausal.logic.exceptions import LogicException  # noqa: E402
from tests.clpq_oracle import Answer, same_solution_sets  # noqa: E402


def _namer(names):
    """name_of for residual_strings: the given names, `_I1`, `_I2`, ... for
    the rest (internal, existentially closed by the oracle tool)."""
    table = {}
    for variable, name in names:
        table[deref(variable)._id] = name

    def name_of(variable):
        identity = variable._id
        if identity not in table:
            table[identity] = f"_I{len(table) + 1}"
        return table[identity]
    return name_of


def _residual(trail, named):
    return rc.residual_strings([v for v, _ in named], trail, _namer(named))


def _equivalent(residual, expected):
    ok, why = same_solution_sets([Answer({}, residual)], [Answer({}, expected)])
    return ok, why


def _engine_numbers_only(terms):
    stack = list(terms)
    while stack:
        item = deref(stack.pop())
        if type(item) is tuple:
            assert item and type(item[0]) is str, item
            stack.extend(item[1:])
        elif type(item) is list:
            stack.extend(item)


def test_two_multiples_of_one_equation_dump_as_one():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", ("+", x, y), 3),
          ("=", ("+", ("*", 2, x), ("*", 2, y)), 6))
    residual = _residual(trail, [(x, "X"), (y, "Y")])
    assert len(residual) == 1
    assert _equivalent(residual, ["X+Y=3"]) == (True, "")


def test_strict_bounds_stay_strict():
    trail = Trail()
    x = Var()
    _post(trail, (">", x, 1), ("<", x, 3))
    assert rc.dump([x], ["X"], trail) == [(">", "X", 1), ("<", "X", 3)]
    assert _residual(trail, [(x, "X")]) == ["{X > 1}", "{X < 3}"]


def test_a_strict_bound_projects_strict():
    # {X < Y, Y =< 3} onto X is X < 3 (the legacy solver gave X =< 3).
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("<", x, y), ("=<", y, 3))
    assert rc.dump([x], ["X"], trail) == [("<", "X", 3)]


def test_projection_eliminates_and_drops_redundant_bounds():
    trail = Trail()
    x, z = Var(), Var()
    _post(trail, (">=", z, 1), (">=", x, z), (">=", x, 0), ("=<", x, 5))
    assert sorted(_residual(trail, [(x, "X")])) == ["{X =< 5}", "{X >= 1}"]
    residual = _residual(trail, [(x, "X"), (z, "Z")])
    assert len(residual) == 3
    assert _equivalent(residual, ["X-Z>=0", "X=<5", "Z>=1"]) == (True, "")


def test_dump_leaves_the_store_as_it_was():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, (">=", ("+", x, y), 2), ("=<", ("-", x, z), 1), ("<", z, 4))
    members = [deref(v) for v in list_elements(bv.all_variables(x))]
    before = _snapshot(members)
    length = len(trail)
    first = _residual(trail, [(x, "X")])
    assert len(trail) == length
    assert _snapshot(members) == before
    assert _residual(trail, [(x, "X")]) == first


def test_dump_replaces_targets_by_names_and_copies_the_rest():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    _post(trail, (">=", ("+", x, y), 2), ("=<", ("-", x, z), 1), ("<", z, 4))
    name = Var()
    goals = rc.dump([x, y], [name, "Y"], trail)
    seen = _term_variables(goals)
    assert name in seen
    store = {id(deref(v)) for v in list_elements(bv.all_variables(x))}
    assert not any(id(v) in store for v in seen)
    _engine_numbers_only(goals)


def test_dump_raises_for_a_bound_target_and_fails_for_unequal_lengths():
    trail = Trail()
    x = Var()
    _post(trail, (">=", x, 1))
    with pytest.raises(LogicException) as raised:
        rc.dump([x, 3], ["X", "Y"], trail)
    assert raised.value.term[1][0] == "uninstantiation_error"
    assert rc.dump([x], ["X", "Y"], trail) is None


def test_dump_of_a_repeated_target_unifies_its_names():
    trail = Trail()
    x = Var()
    _post(trail, (">=", x, 1))
    assert rc.dump([x, x], ["A", "B"], trail) is None
    a, b = Var(), Var()
    assert rc.dump([x, x], [a, b], trail) == [(">=", a, 1)]
    assert deref(a) is deref(b)


def test_dump_emits_engine_numbers_never_rational_pairs():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", ("+", ("*", Fraction(1, 3), x), y), Fraction(2, 7)),
          ("=\\=", x, Fraction(5, 2)), ("=<", ("-", x, ("*", 3, y)), 4))
    goals = rc.dump([x, y], ["X", "Y"], trail)
    _engine_numbers_only(goals)
    assert any(type(v) is Fraction for g in goals for v in g[1:]
               if type(v) is not tuple)


def test_review_focus_5_a_delayed_goal_is_in_the_residual():
    # Ruling R8: checked against the 1.3.3 source, not the oracle (Scryer's
    # dump/3 drops it).  nfq.pl translate_goal//1 gives clpq:{Term = 0} for
    # resubmit_equal; nf2term writes -6 first, and p2term([X^1, Y^1]) is
    # Y*X; dump.pl nonlin_strip/3 takes off the clpq: and the braces.
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", ("*", x, y), 6))
    residual = _residual(trail, [(x, "X"), (y, "Y")])
    assert [re.sub(r"\s+", "", r) for r in residual] == ["{-6+Y*X=0}"]
    assert [re.sub(r"\s+", "", r) for r in _residual(trail, [(x, "X")])] == \
        ["{-6+_I2*X=0}"]


def test_a_delayed_goal_stays_delayed_after_the_dump():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, ("=", ("*", x, y), 6))
    _residual(trail, [(x, "X"), (y, "Y")])
    from clausal.logic.variables import unify
    assert unify(x, 2, trail)
    assert deref(y) == 3


def test_nonlinear_strip_keeps_the_solver_module_and_drops_others():
    goal = ("=", "X", 1)
    assert rc.nonlinear_strip([(":", "clpq", ("{}", goal)),
                               (":", "other", ("p", 1)),
                               (":", "clpq", ("q", 2))], "clpq") == \
        [goal, ("q", 2)]
    assert rc.nonlinear_strip([("p", 1)], "clpq") is None
    assert rc.nonlinear_strip([], "clpq") == []


def test_a_goal_of_another_module_is_stripped_yet_counts_as_reachable():
    # Task 7 carry: 1.3.3's nonlin_strip/3 drops M:What with M \== clpq,
    # while geler.pl project_nonlinear/3 takes the variables of every
    # translated goal.  Reproduced, not fixed.
    trail = Trail()
    x, w = Var(), Var()

    def translate(procedure, argument):
        return [(":", "other", ("p", w)), (":", "clpq", ("{}", ("=", x, 1)))]

    def never(argument, trail):
        return True

    assert delay_goal([x], never, None, trail)
    mark = trail.mark()
    from clausal.logic.clpq.delayed_goals import collect_nonlinear
    goals = collect_nonlinear([x], trail, translate)
    assert rc.nonlinear_strip(goals, "clpq") == [("=", x, 1)]
    trail.undo(mark)
    reachable = project_nonlinear([x], [x], trail, translate)
    assert w in reachable and x in reachable


def test_wait_linear_retry_s_goal_is_clpq_qualified_so_it_is_kept():
    # bv.pl is in module clpq (clpq.pl ensure_loads it), so the meta
    # argument of nfq:wait_linear/3 is clpq:infimum_linear(...): M == clpq
    # and nonlin_strip/3 keeps it, as it keeps {Term = Res}.
    trail = Trail()
    x, y, infimum = Var(), Var(), Var()
    _post(trail, (">=", x, 1))
    assert bv.inf(("*", x, y), infimum, trail)
    goals = rc.dump([x, y, infimum], ["X", "Y", "I"], trail)
    names = [g[0] for g in goals]
    assert "=" in names and "infimum_linear" in names
    residual = _residual(trail, [(x, "X"), (y, "Y"), (infimum, "I")])
    assert any(r.startswith("infimum_linear(") for r in residual)


def test_related_linear_variables_walks_each_component_in_creation_order():
    trail = Trail()
    x, y, z, w = Var(), Var(), Var(), Var()
    _post(trail, (">=", ("+", z, w), 1), (">=", ("+", x, y), 1))
    related = rc.related_linear_variables([x, z, x, Var()])
    first = deref(state_of(z).component)
    second = deref(state_of(x).component)
    expected = rc.copy_variables(component_all_variables_of(first)) + \
        rc.copy_variables(component_all_variables_of(second))
    assert first._id < second._id
    assert related == expected
    assert rc.related_linear_systems([x, z]) == [first, second]


def component_all_variables_of(component):
    from clausal.logic.clpq.components import component_all_variables
    return component_all_variables(component)


def test_copy_variables_keeps_unbound_elements_of_an_open_list():
    from clausal.logic.clpq.components import closed_list, open_list
    a, b = Var(), Var()
    items, _ = open_list([a, 3, b])
    assert rc.copy_variables(items) == [a, b]
    assert rc.copy_variables(closed_list([a])) is None


def test_nonempty_list_to_conjunction():
    assert rc.nonempty_list_to_conjunction([]) is None
    assert rc.nonempty_list_to_conjunction(["a"]) == "a"
    assert rc.nonempty_list_to_conjunction(["a", "b", "c"]) == \
        (",", "a", (",", "b", "c"))


def test_all_attribute_goals_gives_the_bounds_and_disequations():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 1), ("=\\=", y, 2))
    members = [deref(v) for v in list_elements(bv.all_variables(y))]
    goals = rc.all_attribute_goals([x, Var()] + members)
    assert (">=", x, 1) in goals
    assert [g for g in goals if g[0] == "=\\="]


def test_projecting_assert_puts_the_projection_first():
    trail = Trail()
    x, y = Var(), Var()
    _post(trail, (">=", x, 1), ("=<", ("+", x, y), 3))
    fact = rc.projecting_assert(("p", x), trail)
    assert fact[0] == ":-" and fact[1][0] == "p"
    head_variable = fact[1][1]
    assert head_variable is not x and is_var(head_variable)
    assert fact[2] == (":", "clpq", ("{}", (">=", head_variable, 1)))
    rule = rc.projecting_assert((":-", ("p", x), ("q", x)), trail)
    variable = rule[1][1]
    assert rule[2] == (",", (":", "clpq", ("{}", (">=", variable, 1))),
                       ("q", variable))
    plain = ("p", Var())
    assert rc.projecting_assert(plain, trail) is plain       # nothing to add


def test_a_frozen_goal_woken_in_a_trial_post_runs_inside_it():
    # {X < 1, X + W =< 1, W >= 0} with freeze(W, fail): the redundancy trial
    # for X < 1 posts {1 =< X}, which binds W = 0; the frozen goal fails
    # there (inside \\+ in 1.3.3), so X < 1 counts as implied and is
    # dropped, leaving X =< 1.  Under a driver dump/3 runs with defer off,
    # so the answer is the same (DEVIATIONS.md D3).
    from clausal.logic.coroutining import _freeze_var

    def fails():
        return iter(())

    for defer in (False, True):
        trail = Trail()
        x, w = Var(), Var()
        _freeze_var(w, fails, trail)
        _post(trail, ("<", x, 1), ("=<", ("+", x, w), 1), (">=", w, 0))
        trail.defer = defer
        try:
            assert rc.dump([x], ["X"], trail) == [("=<", "X", 1)]
            assert trail.defer is defer
        finally:
            trail.defer = False


def test_work_queued_before_dump_stays_queued():
    # A failing goal already on the queue when dump/3 starts is not dump's
    # to run: its trial posts must not run it (each bare binding runs the
    # whole queue), and the undo puts it back.  Without taking the queue,
    # the trial {1 =< X} fails on it, and so does the whole projection.
    def fails():
        return iter(())

    for defer in (False, True):
        for project in ("dump", "projecting_assert"):
            trail = Trail()
            x, w = Var(), Var()
            _post(trail, ("<", x, 1), ("=<", ("+", x, w), 1), (">=", w, 0))
            trail.defer = defer
            trail.push_pending(fails)
            try:
                if project == "dump":
                    assert rc.dump([x], ["X"], trail) == [("<", "X", 1)]
                else:
                    clause = rc.projecting_assert(("p", x), trail)
                    assert clause != ("p", x)
                assert trail.pending is not None
                assert trail.take_pending() == (fails,)
            finally:
                trail.defer = False


def test_dump_in_a_frozen_goal_sees_the_unification_s_bindings():
    # {X + Q = 3, Q >= 0}, freeze(Z, dump([Q], [Q1], C)), f(Z, X) = f(1, 2):
    # Z is bound first, but its goal runs after X's hook has bound Q = 1
    # (the engine runs woken goals after every hook of the unification), so
    # must_be/4 sees Q bound, and projecting_assert/1 projects nothing.
    from clausal.logic.coroutining import _freeze_var
    from clausal.logic.variables import unify
    trail = Trail()
    x, q_, z = Var(), Var(), Var()
    _post(trail, ("=", ("+", x, q_), 3), (">=", q_, 0))
    seen = []

    def goal():
        try:
            rc.dump([q_], ["Q1"], trail)
            seen.append("no error")
        except LogicException as error:
            seen.append(error.term[1])
        seen.append(rc.projecting_assert(("p", q_), trail))
        yield None

    _freeze_var(z, goal, trail)
    assert unify(("f", z, x), ("f", 1, 2), trail)
    assert seen[0] == ("uninstantiation_error", 1)
    assert seen[1] == ("p", q_) and deref(q_) == 1


def test_projecting_assert_in_a_frozen_goal_sees_the_unification_s_bindings():
    # As above, with projecting_assert/1 the first to read the store: Q is
    # bound when it collects the clause's variables.
    from clausal.logic.coroutining import _freeze_var
    from clausal.logic.variables import unify
    trail = Trail()
    x, q_, z = Var(), Var(), Var()
    _post(trail, ("=", ("+", x, q_), 3), (">=", q_, 0))
    seen = []

    def goal():
        seen.append(rc.projecting_assert(("p", q_), trail))
        yield None

    _freeze_var(z, goal, trail)
    assert unify(("f", z, x), ("f", 1, 2), trail)
    assert seen == [("p", q_)] and deref(q_) == 1


def test_a_delayed_goal_on_a_bound_base_translates_to_its_value():
    # Under a driver W = 2 leaves X*W = 3's goal queued, not yet re-posted;
    # its translation writes W's value (nf.pl pe2term/2 clause 2).
    from clausal.logic.variables import unify
    trail = Trail()
    x, w = Var(), Var()
    _post(trail, (">=", x, 0), (">=", w, 0), ("=", ("*", x, w), 3))
    trail.defer = True
    try:
        assert unify(w, 2, trail)
        residual = _residual(trail, [(x, "X")])
    finally:
        trail.defer = False
    assert residual == ["{X >= 0}", "{-3 + 2*X = 0}"]


@pytest.mark.parametrize("seed", range(60))
def test_dump_under_a_driver_matches_a_bare_dump(seed):
    trail = Trail()
    found = _random_store(seed, trail)
    if found is None:
        return
    variables = [deref(v) for v in found[0] if is_var(deref(v))]
    named = [(v, f"V{i}") for i, v in enumerate(variables)]
    for chosen in ([named[0]], named):
        bare = _residual(trail, chosen)
        trail.defer = True
        try:
            driven = _residual(trail, chosen)
            assert trail.defer is True
        finally:
            trail.defer = False
        assert driven == bare


def test_a_dump_of_a_long_sum_needs_no_recursion():
    xs = [Var() for _ in range(50_000)]
    term = xs[0]
    for v in xs[1:]:
        term = ("+", term, ("*", Fraction(1, 2), v))
    goal = ("=<", term, -3)
    (copy,) = rc._copy_terms([goal], {})
    text = rc.format_term(copy, _namer([]))
    assert text.count(" + ") == 49_999 and text.endswith(" =< -3")


def test_a_dump_of_a_sum_deeper_than_the_recursion_limit():
    trail = Trail()
    xs = [Var() for _ in range(1_500)]
    s = Var()
    term = xs[0]
    for v in xs[1:]:
        term = ("+", term, v)
    _post(trail, ("=", s, term), (">=", s, 0))
    assert 1_500 > sys.getrecursionlimit()
    residual = _residual(trail, [(s, "S")] + [(v, f"X{i}") for i, v in enumerate(xs)])
    assert len(residual) >= 1


def test_format_term_writes_prolog_text():
    x, y, z = Var(), Var(), Var()
    name_of = _namer([(x, "X"), (y, "Y"), (z, "Z")])
    cases = [
        (("=", x, ("+", 3, ("*", Fraction(1, 2), y))), "X = 3 + 1/2*Y"),
        (("<", ("-", x, ("*", 2, y)), Fraction(-7, 3)), "X - 2*Y < -7/3"),
        (("-", x), "-X"),
        (("*", -3, x), "-3*X"),
        (("*", x, -3), "X*(-3)"),
        (("/", x, Fraction(1, 2)), "X/(1/2)"),
        (("-", x, ("+", y, z)), "X - (Y + Z)"),
        (("*", ("+", x, y), z), "(X + Y)*Z"),
        (("^", x, 2), "X^2"),
        (("-", ("*", 2, x)), "-(2*X)"),
        (("-", 3), "-(3)"),
        (("infimum_linear", x, y), "infimum_linear(X, Y)"),
        ((":", "clpq", ("p", x)), "clpq:p(X)"),
        (("=\\=", x, 2), "X =\\= 2"),
    ]
    for term, text in cases:
        assert rc.format_term(term, name_of) == text


def test_residual_strings_without_a_store_is_empty():
    trail = Trail()
    x = Var()
    assert rc.residual_strings([x, 3, x], trail, _namer([(x, "X")])) == []
    _post(trail, (">=", x, 1))
    assert rc.residual_strings([x, 3, x], trail, _namer([(x, "X")])) == \
        ["{X >= 1}"]
