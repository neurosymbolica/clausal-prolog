# tests/clpq_port/test_branch_and_bound.py
"""Task 13: bb.pl (branch_and_bound.py), branch and bound for integer
optimisation: bb_inf/3 and bb_inf/5.

Constraints are posted as compound cells through normal_form.post_constraint;
bb_inf is called the way bv.pl's inf is, with a variable for Inf that the
answer binds.
"""
import itertools
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import arithmetic
from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import branch_and_bound as bb
from clausal.logic.clpq import normal_form as nf
from clausal.logic.clpq.delayed_goals import attribute_goal as delayed_goals_of
from clausal.logic.exceptions import LogicException
from clausal.logic.pending import run_first
from clausal.logic.variables import Trail, Var, deref, is_var, unify


def _post(trail, *constraints):
    for constraint in constraints:
        if not nf.post_constraint(constraint, trail):
            return False
    return True


def _value(term):
    term = deref(term)
    return None if is_var(term) else Fraction(term)


def _optimum(optimum, expression, trail):
    mark = trail.mark()
    result = Var()
    try:
        if not optimum(expression, result, trail):
            return None
        return Fraction(deref(result))
    finally:
        trail.undo(mark)


def _depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


def _sum(terms):
    """A sum of cells, left-associated."""
    total = terms[0]
    for term in terms[1:]:
        total = ("+", total, term)
    return total


# ---------------------------------------------------------------- the brief's cases

def test_a_strict_lower_bound_gives_the_next_integer():
    # {X > 0, X =< 2}, bb_inf([X], X, I) gives I = 1 (the legacy solver's
    # strict-bound bug); the store is as it was afterwards.
    trail = Trail()
    x, infimum = Var(), Var()
    assert _post(trail, (">", x, 0), ("=<", x, 2))
    assert bb.bb_inf([x], x, infimum, trail)
    assert _value(infimum) == 1
    assert is_var(deref(x))
    assert _optimum(bv.inf, x, trail) == 0 and _optimum(bv.sup, x, trail) == 2
    assert not _post(trail, ("=<", x, 0))                  # still strict


def test_bb_inf_5_gives_the_vertex():
    # {X + Y >= 3/2, X >= 0, Y >= 0}: the optimum 2 is reached at (1, 1),
    # (2, 0) and (0, 2); Scryer answers [1, 1] (test_against_oracle).
    trail = Trail()
    x, y, infimum, vertex = Var(), Var(), Var(), Var()
    assert _post(trail, (">=", ("+", x, y), Fraction(3, 2)), (">=", x, 0),
                 (">=", y, 0))
    assert bb.bb_inf([x, y], ("+", x, y), infimum, trail, vertex, 0)
    assert _value(infimum) == 2
    assert deref(vertex) == [1, 1]


_KNAPSACKS = [
    # (weights, values, capacity, largest count of each item)
    ([3, 4, 5], [4, 5, 6], 10, 3),
    ([5, 7, 4, 3], [8, 11, 6, 4], 17, 2),
    ([2, 3, 7, 9, 4, 6], [3, 5, 10, 14, 6, 7], 20, 2),
]


def _brute_force(weights, values, capacity, most):
    best = None
    for counts in itertools.product(range(most + 1), repeat=len(weights)):
        if sum(w * c for w, c in zip(weights, counts)) <= capacity:
            value = sum(v * c for v, c in zip(values, counts))
            if best is None or value > best:
                best = value
    return best


@pytest.mark.parametrize("weights, values, capacity, most", _KNAPSACKS)
def test_integer_knapsacks_against_brute_force(weights, values, capacity, most):
    trail = Trail()
    counts = [Var() for _ in weights]
    for count in counts:
        assert _post(trail, (">=", count, 0), ("=<", count, most))
    assert _post(trail, ("=<", _sum([("*", w, c) for w, c in zip(weights, counts)]),
                         capacity))
    infimum, vertex = Var(), Var()
    objective = ("-", 0, _sum([("*", v, c) for v, c in zip(values, counts)]))
    assert bb.bb_inf(counts, objective, infimum, trail, vertex)
    best = _brute_force(weights, values, capacity, most)
    assert _value(infimum) == -best
    chosen = deref(vertex)
    assert all(type(c) is int and 0 <= c <= most for c in chosen)
    assert sum(w * c for w, c in zip(weights, chosen)) <= capacity
    assert sum(v * c for v, c in zip(values, chosen)) == best
    assert all(is_var(deref(c)) for c in counts)           # the store is kept


def _chain(trail, size, upper):
    """2*X(i+1) = 2*X(i) - 1 for twelve variables in [0, upper]: no integer
    point, and each branch moves X1 or X2 up by one."""
    xs = [Var() for _ in range(size)]
    for x in xs:
        assert _post(trail, (">=", x, 0), ("=<", x, upper))
    for i in range(size - 1):
        assert _post(trail, ("=", ("*", 2, xs[i + 1]),
                             ("-", ("*", 2, xs[i]), 1)))
    return xs


def test_a_search_deeper_than_1000_branches_needs_no_recursion():
    # Every successful branch here is nested inside the one before (the
    # other alternative fails at once), so the successful posts count the
    # depth of the tree.
    trail = Trail()
    xs = _chain(trail, 12, 600)
    calls = []
    original = bb.branch_and_bound_branch

    def spy(variable, upper, lower, alternative, trail):
        result = original(variable, upper, lower, alternative, trail)
        calls.append(result)
        return result
    bb.branch_and_bound_branch = spy
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 200)
    try:
        assert not bb.bb_inf(xs, xs[0], Var(), trail)
    finally:
        sys.setrecursionlimit(limit)
        bb.branch_and_bound_branch = original
    assert len(calls) > 2000 and sum(calls) > 1000, (len(calls), sum(calls))


# ---------------------------------------------------------------- bb.pl clause by clause

def test_a_constant_in_the_list_must_be_integral():
    # branch_and_bound_intern/4 clause 2: [monomial(I, [])] is kept when it
    # is within Eps of an integer, else bb_inf fails; clause 1: 0.
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, Fraction(1, 2)))
    infimum, vertex = Var(), Var()
    assert bb.bb_inf([3, 0], x, infimum, trail, vertex)
    assert _value(infimum) == Fraction(1, 2) and deref(vertex) == [3, 0]
    assert not bb.bb_inf([Fraction(3, 2)], x, Var(), trail)


def test_a_term_that_is_not_a_variable_raises_an_instantiation_error():
    # branch_and_bound_intern/4 clause 4: illarg(var, bb_inf(Term,_,_), 1);
    # Scryer: error(instantiation_error, bb_inf(2*_, _, _)).
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, Fraction(1, 2)))
    term = ("*", 2, x)
    with pytest.raises(LogicException) as raised:
        bb.bb_inf([term], x, Var(), trail)
    error = raised.value.term
    assert error[1] == "instantiation_error"
    assert error[2][0] == "bb_inf" and error[2][1] is term


def test_narrowing_binds_and_the_objective_is_repaired():
    # {X >= 1/2, X =< 3/2}: branch_and_bound_narrow_lower/upper post X >= 1
    # and X =< 1, which binds X; repair/2 then reads Lin = 1.
    trail = Trail()
    x, infimum = Var(), Var()
    assert _post(trail, (">=", x, Fraction(1, 2)), ("=<", x, Fraction(3, 2)))
    assert bb.bb_inf([x], ("+", x, 1), infimum, trail)
    assert _value(infimum) == 2
    assert is_var(deref(x))


def test_narrowing_a_strict_bound_moves_past_the_integer():
    # branch_and_bound_narrow_lower: inf is 1 and X > 1 is entailed, so
    # X >= 2; narrow_upper: sup 4, X < 4, so X =< 3.
    trail = Trail()
    x, infimum, supremum = Var(), Var(), Var()
    assert _post(trail, (">", x, 1), ("<", x, 4))
    assert bb.bb_inf([x], x, infimum, trail)
    assert _value(infimum) == 2
    assert bb.bb_inf([x], ("-", 0, x), supremum, trail)
    assert _value(supremum) == -3


def test_no_integer_point_fails():
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, Fraction(1, 2)), ("=<", x, Fraction(2, 3)))
    assert not bb.bb_inf([x], x, Var(), trail)


def test_an_unbounded_objective_fails():
    trail = Trail()
    x = Var()
    assert _post(trail, ("=<", x, 3))
    assert not bb.bb_inf([x], x, Var(), trail)


def test_an_objective_bound_to_a_constant():
    # variable_with_definition_assign gives Dep = 5 (X = k);
    # branch_and_bound_reoptimize's nonvar clause.
    trail = Trail()
    x, infimum = Var(), Var()
    assert _post(trail, (">=", x, Fraction(1, 2)))
    assert bb.bb_inf([x], 5, infimum, trail)
    assert _value(infimum) == 5


def test_epsilon_decides_what_counts_as_integral():
    # Eps = 1/2: the relaxed optimum (0, 3/2) is within Eps of integers, so
    # it is a leaf with no branch; Inf is the relaxed 3/2 and the vertex is
    # round_values of it, [0, 2] (Scryer gives both).
    trail = Trail()
    x, y, infimum, vertex = Var(), Var(), Var(), Var()
    assert _post(trail, (">=", ("+", ("*", 2, x), ("*", 2, y)), 3),
                 (">=", x, 0), (">=", y, 0))
    assert bb.bb_inf([x, y], ("+", x, y), infimum, trail, vertex,
                     Fraction(1, 2))
    assert _value(infimum) == Fraction(3, 2)
    assert deref(vertex) == [0, 2]


def test_the_incumbent_prunes_worse_branches():
    # branch_and_bound_better_bound: once a leaf is found, a node whose
    # relaxed optimum is not below it is cut.  Min X + Y with
    # 2X + 2Y >= 3 in [0, 3]^2: the first leaf is the optimum 2, so the
    # later leaves of value 2 are cut before round_values.
    trail = Trail()
    x, y, infimum, vertex = Var(), Var(), Var(), Var()
    assert _post(trail, (">=", ("+", ("*", 2, x), ("*", 2, y)), 3),
                 (">=", x, 0), (">=", y, 0), ("=<", x, 3), ("=<", y, 3))
    leaves = []
    original = bb.round_values

    def spy(values):
        result = original(values)
        leaves.append(result)
        return result
    bb.round_values = spy
    try:
        assert bb.bb_inf([x, y], ("+", x, y), infimum, trail, vertex, 0)
    finally:
        bb.round_values = original
    assert _value(infimum) == 2
    assert deref(vertex) == [1, 1]                          # as Scryer
    assert len(leaves) == 1


def test_round_and_floor_and_ceiling_follow_arith_pl():
    # arith.pl: SICStus // truncates; round_rational/4 rounds half away
    # from zero, except that -1/2 gives 1 (I = 0 >= 0).
    def q(numerator, denominator=1):
        return arithmetic.make_rational(numerator, denominator)
    assert arithmetic.floor_rational(q(-3, 2)) == q(-2)
    assert arithmetic.floor_rational(q(3, 2)) == q(1)
    assert arithmetic.floor_rational(q(-4, 1)) == q(-4)
    assert arithmetic.ceiling_rational(q(-3, 2)) == q(-1)
    assert arithmetic.ceiling_rational(q(3, 2)) == q(2)
    assert arithmetic.truncate_rational(q(-3, 2)) == q(-1)
    assert arithmetic.round_rational(q(5, 2)) == q(3)
    assert arithmetic.round_rational(q(-5, 2)) == q(-3)
    assert arithmetic.round_rational(q(-1, 2)) == q(1)
    assert arithmetic.round_rational(q(7, 5)) == q(1)
    assert arithmetic.round_rational(q(-7, 5)) == q(-1)


def test_vertex_value_reads_the_right_hand_side():
    # bb.pl vertex_value/2, right_hand_side_value/2, as bv.pl's inf/4 calls
    # it: the vertex of the box LP's optimum, a number as itself.
    trail = Trail()
    x, y, infimum = Var(), Var(), Var()
    assert _post(trail, ("=<", 0, x), ("=<", x, 2), ("=<", 0, y), ("=<", y, 3),
                 ("=<", ("+", x, ("*", 2, y)), 6))
    vx, vy, vc = Var(), Var(), Var()
    assert bv.inf(("-", 0, ("+", x, ("*", 3, y))), infimum, trail, [x, y, 7],
                  [vx, vy, vc])
    assert (_value(infimum), _value(vx), _value(vy), _value(vc)) == (-9, 0, 3, 7)


# ---------------------------------------------------------------- the delayed goal

def test_a_non_linear_objective_waits_and_runs_once_linear():
    trail = Trail()
    x, y, infimum = Var(), Var(), Var()
    assert _post(trail, (">=", x, Fraction(1, 2)))
    assert bb.bb_inf([x], ("*", x, y), infimum, trail)
    assert is_var(deref(infimum))
    assert unify(y, 1, trail)
    assert _value(infimum) == 1


def test_the_delayed_goal_shows_nf_second():
    # bb.pl:22 wait_linear(Term, Nf, bb_inf_internal(Is, Nf, EpsN, Inf,
    # Vertex)): the residual goal has the normal form's variable second.
    trail = Trail()
    x, y, infimum, vertex = Var(), Var(), Var(), Var()
    assert bb.bb_inf([x], ("*", x, y), infimum, trail, vertex)
    (goal,) = delayed_goals_of(deref(x))
    shown = nf.translate_goal(*goal)
    assert len(shown) == 2
    equation, call = shown
    result = equation[2][1][2]
    assert call[0] == ":" and call[1] == "clpq"
    assert call[2] == ("branch_and_bound_infimum_internal", [x], result,
                       Fraction(1, 1000), infimum, vertex)
    assert call[2][2] is result


def test_the_delayed_goal_is_deterministic():
    # It runs once and leaves nothing to retry: a later failure fails the
    # binding outright, and the binding that succeeds runs it once.
    trail = Trail()
    x, y, infimum = Var(), Var(), Var()
    assert _post(trail, (">=", x, Fraction(1, 2)))
    runs = []
    original = bb.branch_and_bound_infimum_internal

    def spy(normal_form, argument, trail):
        runs.append(1)
        return original(normal_form, argument, trail)
    bb.branch_and_bound_infimum_internal = spy
    try:
        assert bb.bb_inf([x], ("*", x, y), infimum, trail)
        assert unify(y, 2, trail)
    finally:
        bb.branch_and_bound_infimum_internal = original
    assert runs == [1] and _value(infimum) == 2


# ---------------------------------------------------------------- entry catch-up (D3)

def _frozen_bb_inf(mode):
    """{X + Q = 3}, {W >= 1/2}, freeze(Z, bb_inf([Q - X], W, I)), then
    f(Z, X) = f(1, 2): outside a driver the frozen goal runs before X's
    hook, with X bound and Q not yet."""
    from clausal.logic.coroutining import _freeze_var
    trail = Trail()
    x, q, w, z, infimum = Var(), Var(), Var(), Var(), Var()
    assert _post(trail, ("=", ("+", x, q), 3), (">=", w, Fraction(1, 2)))

    def goal():
        if bb.bb_inf([("-", q, x)], w, infimum, trail):
            yield None
    _freeze_var(z, goal, trail)
    if mode == "bare":
        ok = unify(("f", z, x), ("f", 1, 2), trail)
    elif mode == "one at a time":
        ok = unify(x, 2, trail) and unify(z, 1, trail)
    else:
        trail.defer = True
        try:
            ok = unify(("f", z, x), ("f", 1, 2), trail) and run_first(trail)
        finally:
            trail.defer = False
    return ok, _value(infimum), _value(q)


@pytest.mark.parametrize("mode", ["bare", "one at a time", "driver"])
def test_bb_inf_catches_up_at_entry(mode):
    # Q - X is the constant -1 once Q's component has caught up with X = 2;
    # without the catch-up it is Q - 2, which branch_and_bound_intern/4
    # refuses with an instantiation error.
    assert _frozen_bb_inf(mode) == (True, Fraction(1, 2), 1)


def test_a_delayed_bb_inf_shows_in_the_residual():
    # The residual keeps the waiting goal with Is written as a list and the
    # normal form's variable second (Scryer's dump/3 throws on this store,
    # so there is no oracle text).
    from clausal.logic.clpq.residual_constraints import residual_strings
    trail = Trail()
    x, y, infimum = Var(), Var(), Var()
    assert _post(trail, (">=", x, Fraction(1, 2)))
    assert bb.bb_inf([x], ("*", x, y), infimum, trail)
    names = {x._id: "X", y._id: "Y", infimum._id: "I"}
    internal = []

    def name_of(variable):
        if variable._id not in names:
            internal.append(variable)
            names[variable._id] = f"_I{len(internal)}"
        return names[variable._id]
    residual = residual_strings([x, y, infimum], trail, name_of)
    assert residual == ["{X >= 1/2}", "{Y*X = _I1}",
                        "branch_and_bound_infimum_internal([X], _I1, 1/1000, I, _I2)"]


def test_a_nested_bb_inf_keeps_the_outer_incumbent():
    # DEVIATIONS.md D17.  The inner bb_inf waits on X; the outer search
    # binds X = 0, records the leaf Z = 1, then binds X = 1, which wakes
    # the inner one.  1.3.3's incumbent is one global record that the inner
    # bb_inf deletes, so the outer then records Z = 2 and answers 2 (Scryer
    # does, test_a_nested_bb_inf_differs_from_the_oracle); the port's
    # incumbent is local to each search and the minimum 1 comes back.
    trail = Trail()
    w, x, z, inner, outer, vertex = Var(), Var(), Var(), Var(), Var(), Var()
    assert _post(trail, (">=", w, Fraction(1, 2)))
    assert bb.bb_inf([w], ("*", w, x), inner, trail)
    assert _post(trail, (">=", x, 0), ("=<", x, 1),
                 (">=", ("+", z, ("*", 2, x)), 1),
                 (">=", ("-", z, ("*", 2, x)), 0))
    assert bb.bb_inf([x], z, outer, trail, vertex, 0)
    assert _value(outer) == 1 and deref(vertex) == [0]
