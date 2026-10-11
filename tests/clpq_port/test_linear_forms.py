# tests/clpq_port/test_linear_forms.py
"""Task 6: ordering.pl (variable_ordering.py) and store.pl (linear_forms.py).

The references are Fraction-based dict arithmetic, written independently of
the port.  Where 1.3.3 keeps a zero-coefficient term (a product by a zero
factor that no merge touches), the reference keeps it too.
"""
import gc
import random
from fractions import Fraction
from functools import cmp_to_key

import pytest

from clausal.logic.clpq.arithmetic import ONE, ZERO, make_rational
from clausal.logic.clpq.attributes import (
    SolverState, bounds_none, put_state, state_of)
from clausal.logic.clpq.bounded_simplex import variable_intern
from clausal.logic.clpq.linear_forms import (
    LinearForm, add_homogeneous_parts, add_homogeneous_parts_first_scaled,
    add_homogeneous_parts_scaled, add_linear_forms,
    add_linear_forms_first_scaled, add_linear_forms_scaled, delete_factor,
    delete_factor_homogeneous, homogeneous_to_sum, independent, isolate,
    multiply_homogeneous_part, multiply_linear_factor,
    normal_form_coefficient_homogeneous, normal_form_coefficient_of,
    normal_form_right_hand_side, normal_form_substitute, normal_form_to_sum,
    normalize_scalar, renormalize, renormalize_balanced,
    renormalize_balanced_one)
from clausal.logic.clpq.variable_ordering import (
    add_edges, add_vertices, arrangement, combine, compare_order_values,
    compare_variable_order, generate_edges, graph_union, group,
    join_component, normalize, normalize_vertex, normalize_vertices,
    ordering, strip_nonvariable, top_sort)
from clausal.logic.variables import Trail, Var, deref, unify


# ---------------------------------------------------------------- helpers

def _constrained(count, trail):
    """Variables carrying a solver state whose variable_order is a fresh
    Var, as bv.pl's variable_intern gives them (`variable_order(_)`)."""
    xs = []
    for _ in range(count):
        x = Var()
        put_state(x, SolverState(variable_order=Var()), trail)
        xs.append(x)
    return xs


_BY_ORDER = cmp_to_key(compare_variable_order)


def _sorted_terms(pairs):
    return sorted(pairs, key=lambda p: _BY_ORDER(p[0]))


def _as_dict(form):
    d = {id(v): Fraction(*k) for v, k in form.terms}
    return Fraction(*form.constant), d


def _in_order(form):
    vs = [v for v, _ in form.terms]
    return vs == sorted(vs, key=_BY_ORDER)


def _random_form(rng, xs):
    chosen = rng.sample(xs, rng.randint(0, len(xs)))
    return LinearForm(make_rational(rng.randint(-9, 9), 1), ZERO,
                      _sorted_terms([(v, make_rational(rng.randint(-9, 9) or 1,
                                                       rng.randint(1, 5)))
                                     for v in chosen]))


def _reference_sum(da, fa, db, fb):
    """store.pl add_linear_ffh/7: a variable in both forms is summed and the
    term dropped when the sum is zero; a variable in one form only is scaled
    and kept, even when the factor is zero."""
    want = {}
    for k in set(da) | set(db):
        if k in da and k in db:
            s = fa * da[k] + fb * db[k]
            if s:
                want[k] = s
        elif k in da:
            want[k] = fa * da[k]
        else:
            want[k] = fb * db[k]
    return want


# ---------------------------------------------------------------- brief tests

@pytest.mark.parametrize("seed", range(100))
def test_scaled_addition_agrees_with_fraction_dicts(seed):
    rng = random.Random(seed)
    xs = _constrained(6, Trail())
    a, b = _random_form(rng, xs), _random_form(rng, xs)
    ka, kb = make_rational(rng.randint(-5, 5), 3), make_rational(rng.randint(-5, 5), 7)
    got = add_linear_forms_scaled(a, ka, b, kb)
    ca, da = _as_dict(a)
    cb, db = _as_dict(b)
    fa, fb = Fraction(*ka), Fraction(*kb)
    assert _as_dict(got) == (fa * ca + fb * cb, _reference_sum(da, fa, db, fb))
    assert _in_order(got)


def test_a_long_form_needs_no_recursion():
    xs = _constrained(50_000, Trail())
    big = LinearForm((0, 1), (0, 1), [(v, (1, 1)) for v in xs])
    assert len(add_linear_forms_scaled(big, (1, 1), big, (1, 1)).terms) == 50_000


# ---------------------------------------------------------------- ordering

def test_variable_order_follows_creation_and_is_an_identity():
    trail = Trail()
    xs = _constrained(50, trail)
    for i, x in enumerate(xs):
        assert compare_variable_order(x, x) == 0
        for y in xs[i + 1:]:
            assert compare_variable_order(x, y) == -1
            assert compare_variable_order(y, x) == 1


def test_variable_order_is_stable_across_backtracking_and_collection():
    trail = Trail()
    xs = _constrained(20, trail)
    before = sorted(xs, key=_BY_ORDER)
    mark = trail.mark()
    junk = _constrained(1000, trail)       # newer variables, then undone
    unify(Var(), 3, trail)
    trail.undo(mark)
    del junk
    gc.collect()
    rng = random.Random(1)
    shuffled = xs[:]
    rng.shuffle(shuffled)
    assert sorted(shuffled, key=_BY_ORDER) == before == xs


def test_a_variable_without_an_order_does_not_compare():
    # itf3.pl's nf_ordering expansion: get_atts(A, order(Oa)) fails.
    trail = Trail()
    (x,) = _constrained(1, trail)
    assert compare_variable_order(x, Var()) is None
    assert compare_variable_order(Var(), x) is None


def test_order_values_bound_by_projection_sort_after_unbound_ones_by_number():
    # project.pl order/3 binds the order value O = N; standard order puts
    # an unbound variable before any number, and numbers by value.
    trail = Trail()
    a, b, c, d = _constrained(4, trail)
    from clausal.logic.clpq.attributes import state_of
    assert unify(state_of(c).variable_order, 2, trail)
    assert unify(state_of(a).variable_order, 1, trail)
    # b, d stay unbound: they come first, in creation order; then a (1), c (2)
    assert sorted([a, b, c, d], key=_BY_ORDER) == [b, d, a, c]
    assert compare_order_values(2, 10) == -1 and compare_order_values(Var(), 0) == -1


def test_renormalize_follows_an_imposed_order():
    # The consistency ordering/1 needs: after project.pl binds order values,
    # renormalize (store.pl) re-sorts a form under the new order.
    trail = Trail()
    from clausal.logic.clpq.attributes import state_of
    x, y, z = _constrained(3, trail)
    form = LinearForm((5, 1), ZERO, [(x, (1, 1)), (y, (2, 1)), (z, (3, 1))])
    mark = trail.mark()
    assert unify(state_of(z).variable_order, 1, trail)
    assert unify(state_of(x).variable_order, 2, trail)
    got = renormalize(form)
    assert [v for v, _ in got.terms] == [y, z, x]
    assert got.terms == [(y, (2, 1)), (z, (3, 1)), (x, (1, 1))]
    assert got.constant == (5, 1)
    trail.undo(mark)
    assert [v for v, _ in renormalize(form).terms] == [x, y, z]


# ---------------------------------------------------------------- ugraphs + ordering.pl

def test_top_sort_pops_newly_free_vertices_last_in_first_out():
    # SICStus library(ugraphs) top_sort/2 keeps the free vertices on a stack:
    # a->b, a->c gives [a, c, b], not the queue order [a, b, c].
    a, b, c = Var(), Var(), Var()
    graph = add_edges([], [(a, b), (a, c)])
    assert top_sort(graph) == [a, c, b]


def test_top_sort_fails_on_a_cycle():
    a, b = Var(), Var()
    assert top_sort(add_edges([], [(a, b), (b, a)])) is None


@pytest.mark.parametrize("seed", range(30))
def test_top_sort_is_a_topological_order(seed):
    rng = random.Random(seed)
    vs = [Var() for _ in range(12)]
    edges = [(vs[i], vs[j]) for i in range(12) for j in range(i + 1, 12)
             if rng.random() < 0.2]
    rng.shuffle(edges)
    got = top_sort(add_vertices(add_edges([], edges), vs))
    assert sorted(got, key=lambda v: v._id) == vs
    position = {v._id: i for i, v in enumerate(got)}
    assert all(position[x._id] < position[y._id] for x, y in edges)


def test_add_edges_and_add_vertices_build_sorted_neighbour_lists():
    a, b, c = Var(), Var(), Var()
    g = add_edges([], [(c, a), (a, c), (a, b), (a, c)])
    assert g == [(a, [b, c]), (b, []), (c, [a])]
    assert add_vertices(g, [c, b]) == g
    assert add_vertices([], [b, a]) == [(a, []), (b, [])]


def test_graph_union_merges_neighbour_sets():
    a, b, c = Var(), Var(), Var()
    g1 = [(a, [b]), (b, [])]
    g2 = [(a, [c]), (c, [])]
    assert graph_union(g1, g2) == [(a, [b, c]), (b, []), (c, [])]
    assert graph_union(g1, []) is g1


def test_generate_edges_pairs_each_element_with_every_later_one():
    a, b, c = Var(), Var(), Var()
    assert generate_edges([a, b, c]) == [(a, b), (a, c), (b, c)]
    assert generate_edges([a]) == []


def test_group_joins_runs_of_identical_keys():
    a, b = Var(), Var()
    assert group([(a, [1]), (a, [2]), (b, [3])]) == [(a, [1, 2]), (b, [3])]
    assert group([]) == []


def test_strip_nonvariable_drops_self_and_everything_from_the_first_nonvar():
    a, b, c = Var(), Var(), Var()
    assert strip_nonvariable([a, b, c, 3, 4], b) == [a, c]


def test_normalize_after_bindings_and_aliasing():
    # ordering.pl normalize/2: drop bound vertices and edges to them,
    # merge aliased vertices, and turn V-[V] into V-[].
    trail = Trail()
    a, b, c, d = Var(), Var(), Var(), Var()
    g = add_edges([], [(a, b), (b, c), (c, d), (d, a)])
    assert unify(b, 7, trail)          # b is no longer a variable
    assert unify(d, a, trail)          # d aliases a
    assert normalize(g) == [(a, []), (c, [a])]
    assert normalize([]) == []
    assert normalize_vertex(7, [a]) is None
    assert normalize_vertices([(a, [a]), (7, [a])]) == [(a, [])]


def test_combine_is_the_union_of_two_normalized_graphs():
    a, b, c = Var(), Var(), Var()
    assert combine(add_edges([], [(a, b)]), add_edges([], [(b, c)])) == \
        [(a, [b]), (b, [c]), (c, [])]


def test_ordering_of_an_unbound_term_fails_and_of_a_non_constraint_succeeds():
    trail = Trail()
    assert ordering(Var(), trail) is False
    assert ordering(5, trail) is True
    # no variable joins a component, so there is no priority to read
    # (class.pl component_get_priority/2 fails on a fresh Class)
    assert ordering(("<", 1, 2), trail) is True
    assert ordering([1, 2, 3], trail) is True
    assert join_component([1, 2], trail) is None


def test_arrangement_needs_a_component():
    # arrangement/2's priority comes from class.pl (Task 7); without one,
    # component_get_priority fails and the second clause raises.
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException):
        arrangement(None)



def test_a_cyclic_ordering_raises_the_system_error():
    # DEVIATIONS.md D6 (ruling R13): 1.3.3's intent, system(unsatisfiable_
    # ordering), not the type_error(callable, 0) SICStus 4.10.1 raises.
    from clausal.logic.clpq.components import (
        component_new, component_put_priority, open_list)
    from clausal.logic.exceptions import LogicException
    trail = Trail()
    a, b = Var(), Var()
    component = Var()
    head, tail = open_list([a, b])
    assert component_new(component, head, tail, None, trail)
    component_put_priority(component, add_edges([], [(a, b), (b, a)]), trail)
    with pytest.raises(LogicException) as raised:
        arrangement(component)
    assert raised.value.term[1] == ("system_error", "unsatisfiable_ordering")
    component_put_priority(component, add_edges([], [(a, b)]), trail)
    assert arrangement(component) == [a, b]


# ---------------------------------------------------------------- ordering/1 through variable_intern/2

def test_ordering_of_two_variables_goes_through_variable_intern():
    trail = Trail()
    a, b = Var(), Var()
    assert ordering(("<", b, a), trail)
    component = state_of(a).component
    assert deref(state_of(b).component) is deref(component)
    assert state_of(a).bounds == bounds_none()
    assert arrangement(component) == [b, a]


def test_ordering_of_a_list_and_arrangement_of_an_interned_variable():
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    assert ordering([c, a, b], trail)
    assert arrangement(variable_intern(a, trail)) == [c, a, b]
    mark = trail.mark()
    assert ordering(("<", b, c), trail)
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException):
        arrangement(state_of(a).component)
    trail.undo(mark)
    assert arrangement(state_of(a).component) == [c, a, b]


# ---------------------------------------------------------------- store.pl units

def _forms(seed, count=6):
    rng = random.Random(seed)
    xs = _constrained(count, Trail())
    return rng, xs


def test_normalize_scalar_is_a_constant_form():
    form = normalize_scalar((3, 4))
    assert (form.constant, form.rest, form.terms) == ((3, 4), ZERO, [])


@pytest.mark.parametrize("seed", range(40))
def test_add_linear_forms_agrees_with_fraction_dicts(seed):
    rng, xs = _forms(seed)
    a, b = _random_form(rng, xs), _random_form(rng, xs)
    got = add_linear_forms(a, b)
    ca, da = _as_dict(a)
    cb, db = _as_dict(b)
    assert _as_dict(got) == (ca + cb, _reference_sum(da, 1, db, 1))
    assert _in_order(got)
    assert add_homogeneous_parts(a.terms, b.terms) == got.terms


@pytest.mark.parametrize("seed", range(40))
def test_first_scaled_addition_agrees_with_fraction_dicts(seed):
    rng, xs = _forms(seed)
    a, b = _random_form(rng, xs), _random_form(rng, xs)
    ka = make_rational(rng.randint(-4, 4), rng.randint(1, 3))
    got = add_linear_forms_first_scaled(a, ka, b)
    ca, da = _as_dict(a)
    cb, db = _as_dict(b)
    fa = Fraction(*ka)
    assert _as_dict(got) == (fa * ca + cb, _reference_sum(da, fa, db, 1))
    assert _in_order(got)
    assert add_homogeneous_parts_first_scaled(a.terms, ka, b.terms) == got.terms


def test_a_zero_factor_keeps_unmerged_terms_as_1_3_3_does():
    # store.pl add_linear_ffh/7, Rel = (<) and mult_hom/3 do not test for
    # zero; only the (=) branch drops a zero sum.
    x, y = _constrained(2, Trail())
    a = LinearForm(ZERO, ZERO, [(x, (2, 1))])
    b = LinearForm(ZERO, ZERO, [(x, (1, 1)), (y, (1, 1))])
    got = add_linear_forms_scaled(a, ZERO, b, ZERO)
    assert got.terms == [(y, ZERO)]           # x merged to 0 and dropped
    got = add_linear_forms_scaled(a, ZERO, b, ONE)
    assert got.terms == [(x, (1, 1)), (y, (1, 1))]
    got = add_linear_forms_scaled(b, ZERO, a, ONE)
    assert got.terms == [(x, (2, 1)), (y, ZERO)]
    assert add_homogeneous_parts_scaled([(y, (1, 1))], ZERO, [], ONE) == [(y, ZERO)]


def test_merging_cancels_equal_and_opposite_terms():
    x, y = _constrained(2, Trail())
    a = LinearForm((1, 1), ZERO, [(x, (1, 1)), (y, (2, 1))])
    b = LinearForm((1, 1), ZERO, [(x, (-1, 1))])
    assert add_linear_forms(a, b).terms == [(y, (2, 1))]


@pytest.mark.parametrize("k", [(1, 1), (0, 1), (-3, 2)])
def test_multiply_linear_factor(k):
    x, y = _constrained(2, Trail())
    form = LinearForm((2, 1), ZERO, [(x, (1, 2)), (y, (-1, 1))])
    got = multiply_linear_factor(form, k)
    if k == (1, 1):
        assert got is form                   # store.pl: "avoid copy"
    f = Fraction(*k)
    assert _as_dict(got) == (2 * f, {id(x): f / 2, id(y): -f})
    assert multiply_homogeneous_part(form.terms, k) == got.terms


def test_delete_factor_removes_one_variable():
    x, y, z = _constrained(3, Trail())
    form = LinearForm((4, 1), ZERO, [(x, (1, 1)), (y, (2, 1)), (z, (3, 1))])
    rest, k = delete_factor(y, form)
    assert k == (2, 1) and rest.terms == [(x, (1, 1)), (z, (3, 1))]
    assert rest.constant == (4, 1)
    assert delete_factor(Var(), form) is None
    assert delete_factor_homogeneous(z, form.terms) == ([(x, (1, 1)), (y, (2, 1))], (3, 1))


def test_coefficient_lookup_stops_once_past_the_variable():
    x, y, z = _constrained(3, Trail())
    form = LinearForm(ZERO, ZERO, [(x, (1, 1)), (z, (3, 1))])
    assert normal_form_coefficient_of(form, z) == (3, 1)
    assert normal_form_coefficient_of(form, y) is None
    assert normal_form_coefficient_of(form, Var()) is None
    from clausal.logic.clpq.attributes import state_of
    assert normal_form_coefficient_homogeneous(form.terms, state_of(x).variable_order) == (1, 1)


def test_right_hand_side():
    x, y = _constrained(2, Trail())
    form = LinearForm((3, 1), (1, 2), [(x, (1, 1)), (y, (5, 1))])
    assert normal_form_right_hand_side(form, y) == ((7, 2), (5, 1))
    assert normal_form_right_hand_side(LinearForm(ZERO, ZERO, [(x, ONE)]), y) is None


@pytest.mark.parametrize("seed", range(20))
def test_isolate_solves_for_the_variable(seed):
    # 0 = I + sum K_i X_i, solved for X_j: X_j = -(I + sum_{i!=j} K_i X_i)/K_j
    rng, xs = _forms(seed, 4)
    form = _random_form(rng, xs)
    if not form.terms:
        assert isolate(xs[0], form) is None
        return
    new, coeff = form.terms[rng.randrange(len(form.terms))]
    got = isolate(new, form)
    c, d = _as_dict(form)
    k = d.pop(id(new))
    assert _as_dict(got) == (-c / k, {v: -w / k for v, w in d.items()})


@pytest.mark.parametrize("seed", range(20))
def test_substitute_replaces_a_variable_by_its_definition(seed):
    rng, xs = _forms(seed, 5)
    v = xs[2]
    form_x = _random_form(rng, xs)
    form_v = _random_form(rng, [x for x in xs if x is not v])
    got = normal_form_substitute(v, form_v, form_x)
    cx, dx = _as_dict(form_x)
    if id(v) not in dx:
        assert got is None
        return
    k = dx.pop(id(v))
    cv, dv = _as_dict(form_v)
    assert _as_dict(got) == (k * cv + cx, _reference_sum(dv, k, dx, 1))
    assert _in_order(got)


def test_independent():
    x, y = _constrained(2, Trail())
    assert independent(LinearForm(ZERO, ZERO, [(x, ONE)]), x)
    assert not independent(LinearForm(ZERO, ZERO, [(x, ONE)]), y)
    assert not independent(LinearForm(ONE, ZERO, [(x, ONE)]), x)
    assert not independent(LinearForm(ZERO, ZERO, [(x, (2, 1))]), x)
    assert not independent(LinearForm(ZERO, ZERO, [(x, ONE), (y, ONE)]), x)


def test_normal_form_to_sum_builds_the_1_3_3_term():
    x, y, z = Var(), Var(), Var()
    assert normal_form_to_sum([], (3, 1)) == (3, 1)
    assert normal_form_to_sum([(x, ONE), (y, (-1, 1))], ZERO) == ("-", x, y)
    assert normal_form_to_sum([(x, (-1, 1))], ZERO) == ("-", x)
    assert normal_form_to_sum([(x, (2, 1)), (y, (-3, 1)), (z, (1, 2))], ZERO) == \
        ("+", ("-", ("*", (2, 1), x), ("*", (3, 1), y)), ("*", (1, 2), z))
    assert normal_form_to_sum([(x, ONE)], (5, 1)) == ("+", (5, 1), x)
    assert homogeneous_to_sum([], x) is x


def test_renormalize_folds_bound_variables_into_the_constant():
    trail = Trail()
    x, y, z = _constrained(3, trail)
    form = LinearForm((1, 1), ZERO, [(x, (2, 1)), (y, (3, 1)), (z, (5, 1))])
    assert unify(y, 4, trail)
    got = renormalize(form)
    assert got.constant == (13, 1) and got.terms == [(x, (2, 1)), (z, (5, 1))]
    one = renormalize_balanced_one(form.terms[1])
    assert (one.constant, one.terms) == ((12, 1), [])
    lin, nxt = renormalize_balanced(2, form.terms, 0)
    assert nxt == 2 and lin.constant == (12, 1) and lin.terms == [(x, (2, 1))]


def test_renormalize_merges_aliased_variables():
    trail = Trail()
    x, y = _constrained(2, trail)
    form = LinearForm(ZERO, ZERO, [(x, (2, 1)), (y, (3, 1))])
    assert unify(y, x, trail)
    got = renormalize(form)
    assert len(got.terms) == 1 and got.terms[0][1] == (5, 1)


def test_renormalize_of_an_empty_homogeneous_part_raises():
    # DEVIATIONS.md D5: 1.3.3's renormalize_log/4 recurses without end on 0.
    with pytest.raises(ValueError):
        renormalize(LinearForm((1, 1), ZERO, []))


def test_renormalize_recursion_is_logarithmic():
    # 50,000 terms, depth about log2(50,000) = 16.
    trail = Trail()
    xs = _constrained(50_000, trail)
    rng = random.Random(0)
    shuffled = [(v, (1, 1)) for v in xs]
    rng.shuffle(shuffled)
    got = renormalize(LinearForm(ZERO, ZERO, shuffled))
    assert [v for v, _ in got.terms] == xs


def test_the_other_long_operations_need_no_recursion():
    trail = Trail()
    xs = _constrained(50_000, trail)
    big = LinearForm(ZERO, ZERO, [(v, (1, 1)) for v in xs])
    assert len(add_linear_forms(big, big).terms) == 50_000
    assert len(add_linear_forms_first_scaled(big, (2, 1), big).terms) == 50_000
    assert len(multiply_linear_factor(big, (2, 1)).terms) == 50_000
    assert delete_factor(xs[-1], big)[1] == (1, 1)
    assert normal_form_coefficient_of(big, xs[-1]) == (1, 1)
    assert len(normal_form_to_sum(big.terms[:2], ZERO)) == 3
    term = normal_form_to_sum(big.terms, ZERO)
    depth = 0
    while type(term) is tuple and term and term[0] == "+":
        term = term[1]
        depth += 1
    assert depth == 49_999
    vs = xs[:3000]
    assert len(top_sort(add_edges([], generate_edges(vs)))) == 3000
    assert len(normalize(add_edges([], [(vs[i], vs[i + 1]) for i in range(2999)]))) == 3000

