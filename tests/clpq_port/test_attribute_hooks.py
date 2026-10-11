# tests/clpq_port/test_attribute_hooks.py
"""Task 11: itf3.pl, the unification hook (attribute_hooks.py).

Every binding here is a real engine unify: the engine binds, then calls the
CLPQ_KEY hook (DEVIATIONS.md D3, the post-binding contract).
"""
import sys
from fractions import Fraction

import pytest

from clausal.logic.clpq import attribute_hooks as hooks
from clausal.logic.clpq import bounded_simplex as bv
from clausal.logic.clpq import normal_form as nf
from clausal.logic.clpq.attributes import CLPQ_KEY, state_of
from clausal.logic.clpq.delayed_goals import attribute_goal as delayed_goals_of
from clausal.logic.constraints import dif
from clausal.logic.exceptions import LogicException
from clausal.logic.pending import run_first
from clausal.logic.variables import PlainVar, Trail, Var, deref, is_var, unify


def _post(trail, *constraints):
    for constraint in constraints:
        if not nf.post_constraint(constraint, trail):
            return False
    return True


def _optimum(optimum, expression, trail):
    """inf/sup of *expression* as a Fraction, or None where it fails; the
    store is left as it was."""
    mark = trail.mark()
    result = Var()
    try:
        if not optimum(expression, result, trail):
            return None
        return Fraction(deref(result))
    finally:
        trail.undo(mark)


def _inf(expression, trail):
    return _optimum(bv.inf, expression, trail)


def _sup(expression, trail):
    return _optimum(bv.sup, expression, trail)


def _depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


def test_the_hook_is_registered_for_the_port_key():
    # Ruling R1: registered at import, whatever CLAUSAL_CLPQ says.
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, 1))
    assert unify(x, 0, trail) is False


# ---------------------------------------------------------------- binding to a number

def test_binding_to_a_number_inside_the_bounds_succeeds_and_outside_fails():
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, 1), ("=<", x, 5))
    for value, expected in ((3, True), (1, True), (5, True), (0, False),
                            (6, False), (Fraction(9, 2), True)):
        mark = trail.mark()
        assert unify(x, value, trail) is expected, value
        trail.undo(mark)
    assert _inf(x, trail) == 1 and _sup(x, trail) == 5


def test_the_strict_edge_fails():
    trail = Trail()
    x = Var()
    assert _post(trail, ("<", x, 3))
    assert unify(x, 3, trail) is False
    assert unify(x, Fraction(5, 2), trail) is True
    trail = Trail()
    y = Var()
    assert _post(trail, (">", y, 0))
    assert unify(y, 0, trail) is False


def test_a_binding_reaches_the_rows_of_the_other_variables():
    # {X + Y =< 3}, {X = 1}: Y =< 2 afterwards, unbounded below.
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, ("=<", ("+", x, y), 3))
    assert _post(trail, ("=", x, 1))
    assert deref(x) == 1
    assert _sup(y, trail) == 2
    assert _inf(y, trail) is None
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, ("=<", ("+", x, y), 3))
    assert unify(x, 1, trail)
    assert _sup(y, trail) == 2 and _inf(y, trail) is None


def test_x_less_than_y_then_x_is_3_fails():
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, ("<", x, y), ("=<", y, 3))
    assert unify(x, 3, trail) is False
    assert unify(x, 2, trail) is True
    assert _inf(y, trail) == 2 and _sup(y, trail) == 3


def test_a_non_linear_equation_binding_against_a_bound_fails():
    # {X >= 1}, {X*X = 0}: nf.pl's b3 binds X = 0, which X >= 1 refuses.
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, 1))
    assert _post(trail, ("=", ("*", x, x), 0)) is False
    assert is_var(deref(x))
    assert _inf(x, trail) == 1


def test_an_implied_binding_is_checked_against_a_disequation():
    # {X =\= 2}, {X + W = 3}, {W = 1}: solve/5 implies X = 2 (bv.pl's
    # nonzero variable becomes 0 and verify_nonzero refuses it).
    trail = Trail()
    x, w = Var(), Var()
    assert _post(trail, ("=\\=", x, 2), ("=", ("+", x, w), 3))
    assert _post(trail, ("=", w, 1)) is False
    assert _post(trail, ("=", w, 2)) is True
    assert deref(x) == 1


def test_a_disequation_refuses_a_binding_to_its_value():
    trail = Trail()
    x = Var()
    assert _post(trail, ("=\\=", x, 2))
    assert unify(x, 2, trail) is False
    assert unify(x, 1, trail) is True


def test_an_implied_binding_wakes_a_delayed_goal_on_another_variable():
    # {P*Q = 6}, {P + R = 3}, {R = 1}: P = 2 is implied, so Q = 3.
    trail = Trail()
    p, q, r = Var(), Var(), Var()
    assert _post(trail, ("=", ("*", p, q), 6), ("=", ("+", p, r), 3))
    assert _post(trail, ("=", r, 1))
    assert deref(p) == 2 and deref(q) == 3


def test_binding_wakes_the_delayed_goals_of_the_bound_variable():
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, ("=", ("*", x, y), 6))
    assert unify(x, 2, trail)
    assert deref(y) == 3
    trail = Trail()
    a = Var()
    assert _post(trail, ("=<", ("*", a, a), -1))
    assert unify(a, 1, trail) is False


def test_a_non_number_raises_a_type_error():
    # numbers_only/2: illarg(type(rational), X=Y, 2).
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, 0))
    with pytest.raises(LogicException) as caught:
        unify(x, "a", trail)
    assert "type_error" in str(caught.value.term)
    assert "rational" in str(caught.value.term)
    with pytest.raises(LogicException):
        unify(x, 1.5, trail)
    assert is_var(deref(x))


# ---------------------------------------------------------------- two constrained variables

def test_review_focus_2_unifying_disjoint_bounds_fails():
    for older_first in (True, False):
        trail = Trail()
        if older_first:
            x, y = Var(), Var()
        else:
            y, x = Var(), Var()
        assert _post(trail, (">=", x, 1), ("=<", y, 0))
        assert unify(x, y, trail) is False


def test_review_focus_2_a_merge_is_undone_on_backtracking():
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, (">=", x, 1), ("=<", y, 5))
    before = (state_of(x), state_of(y))
    mark = trail.mark()
    assert unify(x, y, trail)
    assert _inf(x, trail) == 1 and _sup(x, trail) == 5
    assert _inf(y, trail) == 1 and _sup(y, trail) == 5
    trail.undo(mark)
    assert (state_of(x), state_of(y)) == before
    assert _inf(x, trail) == 1 and _sup(x, trail) is None
    assert _inf(y, trail) is None and _sup(y, trail) == 5


def test_two_variables_in_one_component_unify():
    # {X + Y = 4}: X = Y gives X = Y = 2, whichever is older.
    for swap in (False, True):
        trail = Trail()
        x, y = Var(), Var()
        if swap:
            x, y = y, x
        assert _post(trail, ("=", ("+", x, y), 4))
        assert unify(x, y, trail)
        assert deref(x) == 2 and deref(y) == 2


def test_binding_to_a_variable_without_attributes_moves_the_bounds():
    # The plain variable older, so the engine binds the constrained one to it
    # and the hook runs: X's bounds come back on Y as Later goals.
    trail = Trail()
    y = Var()
    x = Var()
    assert _post(trail, (">=", x, 1), ("<", x, 4))
    assert unify(x, y, trail)
    assert _inf(y, trail) == 1 and _sup(y, trail) == 4
    assert state_of(y).upper_strict is True
    assert unify(y, 4, trail) is False


def test_a_variable_whose_row_holds_the_other_one():
    # {Y = X + Z, X >= 1}, X = Y: Z = 0 and inf(Y) = 1, as the oracle says.
    # Created Z, Y, X, the store makes X independent and Y's row hold it;
    # the engine binds X (the newer) and X - Y has no X (itf3.pl's "deep
    # shit" case).  The stand-in stays in Y's row, unbound (D3).
    for swap in (False, True):
        trail = Trail()
        z = Var()
        y = Var()
        x = Var()
        assert _post(trail, ("=", y, ("+", x, z)), (">=", x, 1))
        (stand_in_place,) = [v for v, _ in state_of(y).linear_form.terms
                             if v is x]
        if swap:
            assert unify(y, x, trail)
        else:
            assert unify(x, y, trail)
        assert deref(z) == 0
        assert _inf(y, trail) == 1 and _sup(y, trail) is None
        (term,) = state_of(deref(y)).linear_form.terms
        assert term[0] is not x and is_var(term[0]) and not term[0].is_bound
    for creation in ("xyz", "zxy"):
        trail = Trail()
        made = {}
        for name in creation:
            made[name] = Var()
        x, y, z = made["x"], made["y"], made["z"]
        assert _post(trail, ("=", y, ("+", x, z)), (">=", x, 1))
        assert unify(x, y, trail)
        assert deref(z) == 0
        assert _inf(y, trail) == 1 and _sup(y, trail) is None


def test_a_plain_var_cannot_take_the_constraint():
    trail = Trail()
    plain = PlainVar()
    x = Var()
    assert _post(trail, (">=", x, 1))
    assert unify(x, plain, trail) is False


# ---------------------------------------------------------------- several bindings at once

def test_one_unification_binding_two_constrained_variables():
    # The engine binds both, then calls both hooks; the first one must not
    # walk rows that still hold the second (DEVIATIONS.md D3).
    trail = Trail()
    x, y = Var(), Var()
    assert _post(trail, ("=", ("+", x, y), 3))
    mark = trail.mark()
    assert unify((x, y), (1, 2), trail) is True
    trail.undo(mark)
    assert unify((x, y), (1, 3), trail) is False
    assert unify((y, x), (2, 1), trail) is True


def test_one_unification_binding_three_with_bounds():
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    assert _post(trail, ("=", ("+", ("+", a, b), c), 6), (">=", a, 1),
                 ("=<", b, 2))
    mark = trail.mark()
    assert unify((a, b, c), (1, 2, 3), trail) is True
    trail.undo(mark)
    assert unify((a, b, c), (0, 3, 3), trail) is False
    assert unify((c, a), (5, 1), trail) is True
    assert deref(b) == 0


# ---------------------------------------------------------------- cascades

def test_a_chain_of_ten_thousand_implied_bindings_needs_no_recursion():
    trail = Trail()
    variables = [Var() for _ in range(10_001)]
    for i in range(10_000):
        assert _post(trail, ("=", variables[i + 1], variables[i]))
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 250)
    try:
        assert unify(variables[0], 5, trail)
    finally:
        sys.setrecursionlimit(limit)
    assert all(deref(v) == 5 for v in variables)


class _NestingSpy:
    """Wraps the CLPQ_KEY hook and records how deeply its calls nest."""

    def __init__(self):
        self.depth = 0
        self.deepest = 0
        self.calls = 0
        self.nested_work = 0        # nested calls that are not clause 2

    def __call__(self, state, other, trail):
        self.depth += 1
        self.calls += 1
        self.deepest = max(self.deepest, self.depth)
        if self.depth > 1 and state.forward is None:
            self.nested_work += 1
        try:
            return hooks.holzbaur_hook(state, other, trail)
        finally:
            self.depth -= 1


def test_implied_bindings_are_queued_not_nested():
    # Each implied binding is checked before it is made, so the hook it
    # wakes, inside the outer one, finds forward/1 and only dereferences it
    # (clause 2): the work never nests and the depth stays 2.
    from clausal.logic.variables import register_attr_hook
    trail = Trail()
    variables = [Var() for _ in range(200)]
    for i in range(199):
        assert _post(trail, ("=", variables[i + 1], ("+", variables[i], 1)))
    spy = _NestingSpy()
    register_attr_hook(CLPQ_KEY, spy)
    try:
        assert unify(variables[0], 0, trail)
    finally:
        register_attr_hook(CLPQ_KEY, hooks.holzbaur_hook)
    assert deref(variables[199]) == 199
    assert spy.calls == 200 and spy.deepest == 2 and spy.nested_work == 0


def test_the_chain_bound_from_the_far_end():
    trail = Trail()
    variables = [Var() for _ in range(2_001)]
    for i in range(2_000):
        assert _post(trail, ("=", variables[i + 1], ("+", variables[i], 1)))
    assert unify(variables[-1], 2_000, trail)
    assert deref(variables[0]) == 0 and deref(variables[1_000]) == 1_000


def test_a_cascade_of_delayed_goals_needs_no_recursion():
    # {X1 = X0*X0}, {X2 = X1*X1}, ...: each binding wakes the goal that
    # binds the next variable.  Outside a driver the outermost hook runs the
    # Later work of the hooks woken inside it in one loop.
    trail = Trail()
    variables = [Var() for _ in range(2_001)]
    for i in range(2_000):
        assert _post(trail, ("=", variables[i + 1],
                             ("*", variables[i], variables[i])))
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 250)
    try:
        assert unify(variables[0], 1, trail)
    finally:
        sys.setrecursionlimit(limit)
    assert all(deref(v) == 1 for v in variables)
    assert trail.pending is None
    trail = Trail()
    variables = [Var() for _ in range(301)]
    for i in range(300):
        assert _post(trail, ("=", variables[i + 1],
                             ("*", variables[i], variables[i])))
    assert _post(trail, ("=<", variables[300], 0))
    assert unify(variables[0], 1, trail) is False
    assert trail.pending is None and is_var(deref(variables[0]))


def test_later_work_goes_on_the_pending_queue_under_a_driver():
    trail = Trail()
    y = Var()
    x = Var()
    assert _post(trail, (">=", x, 1))
    trail.defer = True
    try:
        assert unify(x, y, trail)
        assert trail.pending is not None                    # {1 =< Y}, queued
        assert run_first(trail)
    finally:
        trail.defer = False
    assert _inf(y, trail) == 1


# ---------------------------------------------------------------- dif's trial unification

def test_dif_trial_unification_answers_z_is_4():
    # {Z >= 0, Z =< 10}, {X =< 3}, dif(X-Z, 3-5), {X >= 3}, Z = 4.
    trail = Trail()
    z, x = Var(), Var()
    assert _post(trail, (">=", z, 0), ("=<", z, 10), ("=<", x, 3))
    assert dif(("-", x, z), ("-", 3, 5), trail)
    assert _post(trail, (">=", x, 3))
    assert deref(x) == 3
    assert unify(z, 4, trail)
    assert deref(z) == 4
    trail = Trail()
    z, x = Var(), Var()
    assert _post(trail, (">=", z, 0), ("=<", z, 10), ("=<", x, 3))
    assert dif(("-", x, z), ("-", 3, 5), trail)
    assert _post(trail, (">=", x, 3))
    assert unify(z, 5, trail) is False


# ---------------------------------------------------------------- the predicates one by one

def test_forward_dereference_follows_forward_attributes():
    trail = Trail()
    a, b = Var(), Var()
    assert hooks.forward_dereference(3, 3, trail)
    assert not hooks.forward_dereference(3, 4, trail)
    from clausal.logic.clpq.attributes import SolverState, put_state
    put_state(a, SolverState(forward=b), trail)
    assert hooks.forward_dereference(a, 7, trail)
    assert deref(b) == 7 and is_var(deref(a))


def test_verify_type_nonvariable_reads_the_strictness_bits():
    from clausal.logic.clpq.attributes import (
        bounds_lower_upper, bounds_upper_active)
    one, three = (1, 1), (3, 1)
    assert hooks.verify_type_nonvariable(bounds_lower_upper(one, three), one, 0b00)
    assert not hooks.verify_type_nonvariable(bounds_lower_upper(one, three), one, 0b10)
    assert hooks.verify_type_nonvariable(bounds_lower_upper(one, three), three, 0b10)
    assert not hooks.verify_type_nonvariable(bounds_upper_active(three), three, 0b01)


def test_verify_type_variable_queues_the_bounds_as_later_goals():
    from clausal.logic.clpq.attributes import LaterWork, bounds_lower_upper
    trail = Trail()
    y = Var()
    later = LaterWork()
    hooks.verify_type_variable(bounds_lower_upper((1, 1), (3, 1)), y, 0b01,
                               later, trail)
    assert [(work.relation, work.left) for work in later.queue] == \
        [("=<", 1), ("<", y)]
    assert later.drain()
    assert _inf(y, trail) == 1 and _sup(y, trail) == 3
    assert state_of(y).upper_strict is True


def test_numbers_only():
    x = Var()
    assert hooks.numbers_only(Var(), x)
    assert hooks.numbers_only(3, x) and hooks.numbers_only(Fraction(1, 3), x)
    for value in ("a", 1.5, True, ("f", 1)):
        with pytest.raises(LogicException):
            hooks.numbers_only(value, x)


def test_attribute_goal_dumps_the_bounds_and_the_disequation():
    trail = Trail()
    x = Var()
    assert _post(trail, (">=", x, 1))
    assert hooks.attribute_goal(x) == ("{}", (">=", x, (1, 1)))
    y = Var()
    assert hooks.attribute_goal(y) == "true"
    z = Var()
    assert _post(trail, ("=\\=", z, 2))
    (nonzero,) = [v for v in _component_members(z) if state_of(v).nonzero]
    goal = hooks.attribute_goal(nonzero)
    assert goal[0] == "{}" and goal[1][0] == "=\\="


def _component_members(variable):
    from clausal.logic.clpq.components import (
        component_all_variables, list_elements)
    return [deref(v) for v in list_elements(
        component_all_variables(state_of(variable).component))]


def test_list_to_wrapped_conjunction():
    assert hooks.list_to_wrapped_conjunction([]) == "true"
    assert hooks.list_to_wrapped_conjunction(["a"]) == ("{}", "a")
    assert hooks.list_to_wrapped_conjunction(["a", "b", "c"]) == \
        (",", ("{}", "a"), (",", ("{}", "b"), ("{}", "c")))


def test_the_state_on_the_bound_variable_is_left_alone():
    # The hook never writes to X: put_attr on a variable bound to another
    # would write that one's attributes (DEVIATIONS.md D3).
    trail = Trail()
    y = Var()
    x = Var()
    assert _post(trail, (">=", x, 1))
    state = x.attrs[CLPQ_KEY]
    assert unify(x, y, trail)
    assert x.attrs[CLPQ_KEY] is state
    assert delayed_goals_of(y) is None


def _random_store(rng, variables, trail):
    for _ in range(rng.randint(2, 5)):
        chosen = rng.sample(variables, rng.randint(1, 3))
        term = 0
        for variable in chosen:
            term = ("+", term, ("*", rng.choice([-3, -2, -1, 1, 2, 3]), variable))
        relation = rng.choice(["=<", ">=", "<", ">", "="])
        if not nf.post_constraint((relation, term, rng.randint(-5, 5)), trail):
            return False
    return True


def _outcome(variables, trail, ok):
    if not ok:
        return None
    result = []
    for variable in variables:
        value = deref(variable)
        result.append(Fraction(value) if not is_var(value)
                      else (_inf(value, trail), _sup(value, trail)))
    return result


@pytest.mark.parametrize("seed", range(60))
def test_one_unification_agrees_with_binding_one_at_a_time(seed):
    # Scryer fails some of these (a multi-binding unification of related
    # constrained variables; see the Task 11 report), so the reference is
    # the port binding the same pairs one unify at a time.
    import random
    outcomes = []
    for at_once in (True, False):
        rng = random.Random(seed)
        trail = Trail()
        variables = [Var() for _ in range(4)]
        if not _random_store(rng, variables, trail):
            pytest.skip("the store itself fails")
        left, right = [], []
        for variable in rng.sample(variables, 3):
            left.append(variable)
            right.append(rng.choice([rng.randint(-3, 3), rng.choice(variables)]))
        if at_once:
            ok = unify(tuple(left), tuple(right), trail)
        else:
            ok = True
            for a, b in zip(left, right):
                if not unify(a, b, trail):
                    ok = False
                    break
        outcomes.append(_outcome(variables, trail, ok))
    assert outcomes[0] == outcomes[1]


# ---------------------------------------------------------------- fix round 1

def test_a_later_goal_reads_no_unhooked_binding():
    # One unification binds V3, V2, V0; V1*V3 >= V4 is a goal delayed across
    # two components.  V0 + V1 = V2 then gives V1 = 0, so 0 >= V4 >= 4: no.
    # Outside a driver the goal V3's hook wakes used to read V0's component
    # while V0 was bound and its hook still to come, and succeeded.
    def store():
        trail = Trail()
        v = [Var() for _ in range(5)]
        assert _post(trail, ("=", ("+", v[0], v[1]), v[2]), (">=", v[3], 0),
                     (">=", ("*", v[1], v[3]), v[4]), (">=", v[4], 4))
        return trail, v
    trail, v = store()
    assert unify((v[3], v[2], v[0]), (3, 0, 0), trail) is False
    trail, v = store()
    assert (unify(v[3], 3, trail) and unify(v[2], 0, trail)
            and unify(v[0], 0, trail)) is False


def test_a_later_goal_reads_no_unhooked_binding_the_other_way():
    # {Q = 3 - Z}, {X*Q = W}, f(X, Z) = f(2, 1): X = 2, Z = 1, Q = 2, W = 4,
    # in every creation order and both argument orders; it used to fail.
    import itertools
    for creation in itertools.permutations("xwzq"):
        for swap in (False, True):
            trail = Trail()
            made = {}
            for name in creation:
                made[name] = Var()
            x, w, z, q = made["x"], made["w"], made["z"], made["q"]
            assert _post(trail, ("=", q, ("-", 3, z)),
                         ("=", ("*", x, q), w))
            if swap:
                assert unify(("f", z, x), ("f", 1, 2), trail)
            else:
                assert unify(("f", x, z), ("f", 2, 1), trail)
            assert [deref(v) for v in (x, z, q, w)] == [2, 1, 2, 4]


def _two_answer_choice(z, trail):
    def choice():
        mark = trail.mark()
        for value in (1, 2):
            if unify(z, value, trail):
                yield None
            trail.undo(mark)
    return choice


def test_later_work_survives_a_retry_under_a_driver():
    # The engine's drain calls a queued goal's factory again when an earlier
    # goal gives a second answer; the Later work must run again then.
    from clausal.logic.pending import drain
    trail = Trail()
    y, x, z = Var(), Var(), Var()
    assert _post(trail, (">=", x, 1))
    trail.defer = True
    try:
        trail.push_pending(_two_answer_choice(z, trail))
        assert unify(x, y, trail)
        seen = [(deref(z), _inf(y, trail)) for _ in drain(trail)]
    finally:
        trail.defer = False
    assert seen == [(1, 1), (2, 1)]


def test_a_woken_non_linear_goal_survives_a_retry_under_a_driver():
    from clausal.logic.pending import drain
    trail = Trail()
    x, y, p, z = Var(), Var(), Var(), Var()
    assert _post(trail, ("=", p, ("*", x, y)), (">=", y, 0))
    trail.defer = True
    try:
        trail.push_pending(_two_answer_choice(z, trail))
        assert unify(x, 2, trail)
        seen = [(deref(z), _sup(("-", p, ("*", 2, y)), trail),
                 _inf(("-", p, ("*", 2, y)), trail)) for _ in drain(trail)]
    finally:
        trail.defer = False
    assert seen == [(1, 0, 0), (2, 0, 0)]


def _property_store(rng):
    """Five variables in two components, V0 + V1 = V2 + k and bounds on V3
    and V4, joined by a goal V_i * V3 (rel) V4 delayed across both."""
    trail = Trail()
    v = [Var() for _ in range(5)]
    ok = _post(trail,
               ("=", ("+", v[0], v[1]), ("+", v[2], rng.randint(0, 2))),
               (rng.choice(("=<", ">=")), v[3], rng.randint(0, 3)),
               (rng.choice(("=<", ">=", "=")),
                ("*", v[rng.randint(0, 2)], v[3]), v[4]),
               (rng.choice(("=<", ">=")), v[4], rng.randint(0, 6)))
    return trail, v, ok


def _property_outcome(variables, trail, ok):
    if not ok:
        return None
    result = []
    for variable in variables:
        value = deref(variable)
        result.append(Fraction(value) if not is_var(value)
                      else (_inf(value, trail), _sup(value, trail)))
    return tuple(result)


def test_one_unification_bare_one_at_a_time_and_under_a_driver_agree():
    # Ruling R21's property: 2,000 seeds by default
    # (CLPQ_PORT_PROPERTY_SEEDS=N for more).
    import os
    import random
    seeds = int(os.environ.get("CLPQ_PORT_PROPERTY_SEEDS", "2000"))
    disagreements = []
    for seed in range(seeds):
        rng = random.Random(seed)
        state = rng.getstate()
        outcomes = []
        for mode in ("bare", "one at a time", "driver"):
            rng.setstate(state)
            trail, v, ok = _property_store(rng)
            if not ok:
                break
            count = rng.randint(2, 3)
            chosen = rng.sample(range(5), count)
            values = [rng.randint(0, 3) for _ in range(count)]
            left = tuple(v[i] for i in chosen)
            if mode == "bare":
                result = unify(left, tuple(values), trail)
            elif mode == "one at a time":
                result = True
                for variable, value in zip(left, values):
                    if not unify(variable, value, trail):
                        result = False
                        break
            else:
                trail.defer = True
                try:
                    result = unify(left, tuple(values), trail) \
                        and run_first(trail)
                finally:
                    trail.defer = False
            outcomes.append(_property_outcome(v, trail, result))
        if outcomes and not (outcomes[0] == outcomes[1] == outcomes[2]):
            disagreements.append((seed, outcomes))
    assert disagreements == []
