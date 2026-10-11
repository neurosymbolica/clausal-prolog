# tests/clpq_port/test_components.py
"""Task 7: class.pl (components.py) and geler.pl (delayed_goals.py)."""
import sys
import types

import pytest

from clausal.logic.clpq.attributes import (
    LaterWork, SolverState, put_state, state_of, with_changes)
from clausal.logic.clpq.components import (
    COMPONENT_KEY, ComponentRecord, ListCell, closed_list, component_all_variables,
    component_basis, component_basis_add, component_basis_drop,
    component_basis_pivot, component_drop, component_get_priority,
    component_new, component_put_priority, delete_first, list_elements,
    open_list, verify_component)
from clausal.logic.clpq.delayed_goals import (
    DelayedGoal, attach, attribute_goal, collect_nonlinear, geler,
    nonexhausted, project_nonlinear, run, translate, verify_delayed)
from clausal.logic.clpq.variable_ordering import (
    add_edges, arrangement, join_component)
from clausal.logic.variables import Trail, Var, deref, get_attr, unify


# ---------------------------------------------------------------- helpers

def _new(trail, *members, basis=()):
    """bv.pl get_or_add_component's call: component_new(Class, [X|Tail],
    Tail, []), here with any members and basis."""
    component = Var()
    head, tail = open_list(list(members))
    assert component_new(component, head, tail, closed_list(list(basis)), trail)
    return component


def _depth():
    frame, depth = sys._getframe(), 0
    while frame is not None:
        frame, depth = frame.f_back, depth + 1
    return depth


def _members(component):
    return list_elements(component_all_variables(component))


def _basis(component):
    return list_elements(component_basis(component))


# ---------------------------------------------------------------- the brief's three tests

def test_a_basis_add_is_undone_to_the_mark():
    trail = Trail()
    x, y = Var(), Var()
    component = _new(trail, x, y)
    mark = trail.mark()
    new_basis = component_basis_add(component, x, trail)
    assert list_elements(new_basis) == [x]
    assert _basis(component) == [x]
    trail.undo(mark)
    assert _basis(component) == []
    assert _members(component) == [x, y]
    assert component_get_priority(component) == []


def test_a_merge_through_verify_component_is_undone_to_two_components():
    trail = Trail()
    a1, a2, b1 = Var(), Var(), Var()
    component_a = _new(trail, a1, a2, basis=[a1])
    component_b = _new(trail, b1, basis=[b1])
    mark = trail.mark()
    assert unify(component_a, component_b, trail)
    # Merged: the engine binds the newer variable (component_b) to the older
    # one, and verify_component appends the bound one's members first
    # (class.pl: `Lat = Lb`, then put_atts(Y, component_attributes(La, ...))).
    assert deref(component_b) is component_a
    assert _members(component_a) == [b1, a1, a2]
    assert _basis(component_a) == [b1, a1]
    trail.undo(mark)
    assert not component_a.is_bound and not component_b.is_bound
    assert _members(component_a) == [a1, a2]
    assert _members(component_b) == [b1]
    assert _basis(component_a) == [a1]
    assert _basis(component_b) == [b1]


def test_dropping_from_a_fifty_thousand_member_component_needs_no_recursion():
    trail = Trail()
    members = [Var() for _ in range(50_000)]
    component = _new(trail, *members, basis=members)
    last = members[-1]
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(_depth() + 100)
    try:
        component_drop(component, last, trail)
        component_basis_drop(component, members[-2], trail)
        component_basis_pivot(component, last, members[-3], trail)
        merged = _new(trail, Var())
        assert unify(component, merged, trail)
        all_variables = _members(component)
    finally:
        sys.setrecursionlimit(limit)
    assert len(all_variables) == 50_000
    assert not any(variable is last for variable in all_variables)
    assert _basis(component)[0] is last
    assert len(_basis(component)) == 49_998


# ---------------------------------------------------------------- the open list

def test_open_list_and_list_elements_round_trip():
    a, b = Var(), Var()
    head, tail = open_list([a, b])
    assert type(head) is ListCell and tail.is_bound is False
    assert list_elements(head) == [a, b]
    head, tail = open_list([])
    assert head is tail
    assert list_elements(head) == []
    assert list_elements(closed_list([a])) == [a]
    assert closed_list([]) is None


# ---------------------------------------------------------------- delete_first

def test_delete_first_removes_only_the_first_occurrence():
    a, b = Var(), Var()
    items = closed_list([a, b, a])
    assert list_elements(delete_first(items, a)) == [b, a]


def test_delete_first_keeps_an_open_tail():
    a, b = Var(), Var()
    head, tail = open_list([a, b])
    result = delete_first(head, a)
    assert list_elements(result) == [b]
    node = result
    while type(node) is ListCell:
        node = deref(node.rest)
    assert node is tail


def test_delete_first_of_an_absent_element_gives_the_list_itself():
    # 1.3.3 rebuilds the prefix and component_basis_drop then tests
    # `Basis0 \== Basis`; the port returns the same list, so `is` answers the
    # structural question.
    a, b = Var(), Var()
    items = closed_list([a])
    assert delete_first(items, b) is items
    head, _tail = open_list([a])
    assert delete_first(head, b) is head
    assert delete_first(None, b) is None


def test_delete_first_matches_a_variable_through_its_bindings():
    # A hook runs after the binding (clausal.logic.variables): X is already
    # bound when itf3.pl's verify_linear calls component_drop(Class, X).
    # 1.3.3 runs before the binding, where `X == Y` is identity of X.
    trail = Trail()
    x, other = Var(), Var()
    items = closed_list([other, x])
    assert unify(x, 5, trail)
    assert list_elements(delete_first(items, x)) == [other]
    # An element bound to x earlier is x for ==/2 too.
    y, alias = Var(), Var()
    assert unify(alias, y, trail) and deref(alias) is y
    assert list_elements(delete_first(closed_list([alias]), y)) == []
    # Two variables bound to the same number are not identical.
    p, q = Var(), Var()
    assert unify(p, 7, trail) and unify(q, 7, trail)
    assert list_elements(delete_first(closed_list([q]), p)) == [q]


# ---------------------------------------------------------------- class.pl predicates

def test_component_new_puts_the_record_on_a_plain_variable():
    trail = Trail()
    x = Var()
    component = _new(trail, x)
    record = get_attr(component, COMPONENT_KEY)
    assert type(record) is ComponentRecord
    assert _members(component) == [x]
    assert component_basis(component) is None          # []
    assert component_get_priority(component) == []


def test_component_new_on_an_existing_component_merges():
    # bv.pl get_or_add_component on a shared Class: `Su = Class` meets a
    # Class that is already a component, so the hook merges.
    trail = Trail()
    x, y = Var(), Var()
    component = _new(trail, x)
    head, tail = open_list([y])
    assert component_new(component, head, tail, None, trail)
    assert _members(component) == [y, x]


def test_component_new_on_a_number_fails():
    trail = Trail()
    head, tail = open_list([Var()])
    assert component_new(3, head, tail, None, trail) is False


def test_get_and_put_priority():
    trail = Trail()
    a, b = Var(), Var()
    component = _new(trail, a, b)
    graph = add_edges([], [(a, b)])
    mark = trail.mark()
    component_put_priority(component, graph, trail)
    assert component_get_priority(component) == graph
    trail.undo(mark)
    assert component_get_priority(component) == []
    assert component_get_priority(Var()) is None


def test_put_priority_without_a_record_fails():
    assert component_put_priority(Var(), [], Trail()) is False


def test_component_drop_removes_from_members_and_basis():
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    component = _new(trail, a, b, c, basis=[b, c])
    component_drop(component, b, trail)
    assert _members(component) == [a, c]
    assert _basis(component) == [c]


def test_component_drop_keeps_the_tail_so_a_later_merge_appends():
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    component = _new(trail, a, b)
    component_drop(component, b, trail)
    other = _new(trail, c)
    assert unify(component, other, trail)
    assert _members(component) == [c, a]


def test_component_basis_drop_of_an_absent_variable_changes_nothing():
    trail = Trail()
    a, b = Var(), Var()
    component = _new(trail, a, basis=[a])
    record = get_attr(component, COMPONENT_KEY)
    mark = trail.mark()
    assert component_basis_drop(component, b, trail) is True
    assert get_attr(component, COMPONENT_KEY) is record
    assert trail.mark() == mark
    component_basis_drop(component, a, trail)
    assert _basis(component) == []


def test_component_basis_pivot_swaps_leave_for_enter_at_the_front():
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    component = _new(trail, a, b, c, basis=[a, b])
    component_basis_pivot(component, c, a, trail)
    assert _basis(component) == [c, b]


def test_reads_follow_a_merged_component():
    trail = Trail()
    a, b = Var(), Var()
    first = _new(trail, a)
    second = _new(trail, b)
    assert unify(first, second, trail)
    assert _members(second) == _members(first) == [b, a]


# ---------------------------------------------------------------- the hook

def test_verify_component_combines_the_priorities():
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    component_a = _new(trail, a, b)
    component_b = _new(trail, c)
    component_put_priority(component_a, add_edges([], [(a, b)]), trail)
    component_put_priority(component_b, add_edges([], [(b, c)]), trail)
    assert unify(component_a, component_b, trail)
    assert arrangement(component_a) == [a, b, c]


def test_verify_component_fails_against_a_number():
    trail = Trail()
    component = _new(trail, Var())
    assert unify(component, 3, trail) is False


def test_verify_component_fails_against_a_variable_with_other_attributes():
    # class.pl's first clause: `var(Y), get_atts(Y, component_attributes(..))`
    # fails for a Y that is attributed but not a component.
    trail = Trail()
    other = Var()
    put_state(other, SolverState(), trail)
    component = _new(trail, Var())
    assert unify(component, other, trail) is False


def test_verify_component_as_a_function():
    trail = Trail()
    a, b = Var(), Var()
    plain = Var()
    record = get_attr(_new(trail, a), COMPONENT_KEY)
    assert verify_component(record, plain, trail) is True
    assert _members(plain) == [a]
    assert verify_component(record, 1, trail) is False
    target = _new(trail, b)
    record_b = get_attr(_new(trail, Var()), COMPONENT_KEY)
    assert verify_component(record_b, target, trail) is True
    assert len(_members(target)) == 2


# ---------------------------------------------------------------- ordering.pl through real components

def _stub_variable_intern(monkeypatch):
    """bv.pl variable_intern/2 is Task 8's.  This stand-in does what its
    get_or_add_component part does, on the real components module."""
    def variable_intern(variable, trail):
        state = state_of(variable)
        if state is not None and state.component is not None:
            return state.component
        component = Var()
        head, tail = open_list([variable])
        put_state(variable, SolverState(component=component,
                                        variable_order=Var()), trail)
        assert component_new(component, head, tail, None, trail)
        return component
    stub = types.ModuleType("clausal.logic.clpq.bounded_simplex")
    stub.variable_intern = variable_intern
    monkeypatch.setitem(sys.modules, "clausal.logic.clpq.bounded_simplex", stub)


def test_join_component_merges_every_variable_into_one(monkeypatch):
    _stub_variable_intern(monkeypatch)
    trail = Trail()
    a, b, c = Var(), Var(), Var()
    component = join_component([a, 5, b, c], trail)
    assert component is not None
    for variable in (a, b, c):
        assert deref(state_of(variable).component) is deref(component)
    assert sorted(_members(component), key=lambda v: v._id) == [a, b, c]


def test_join_component_without_variables_is_none(monkeypatch):
    _stub_variable_intern(monkeypatch)
    assert join_component([1, 2], Trail()) is None


def test_join_component_is_undone_to_separate_components(monkeypatch):
    _stub_variable_intern(monkeypatch)
    trail = Trail()
    a, b = Var(), Var()
    join_component([a], trail)
    join_component([b], trail)
    mark = trail.mark()
    join_component([a, b], trail)
    assert deref(state_of(a).component) is deref(state_of(b).component)
    trail.undo(mark)
    assert deref(state_of(a).component) is not deref(state_of(b).component)
    assert _members(state_of(a).component) == [a]
    assert _members(state_of(b).component) == [b]


# ---------------------------------------------------------------- geler.pl

def _recorder(log):
    """A goal procedure: appends its argument and succeeds unless the
    argument says "fail"."""
    def procedure(argument, trail):
        log.append(argument)
        return argument != "fail"
    return procedure


def test_geler_attaches_one_goal_to_every_variable():
    trail = Trail()
    x, y = Var(), Var()
    log = []
    geler([x, y], _recorder(log), "g", trail)
    goals_x = state_of(x).delayed_goals
    goals_y = state_of(y).delayed_goals
    assert len(goals_x) == 1 and goals_x[0] is goals_y[0]
    assert type(goals_x[0]) is DelayedGoal


def test_attach_puts_the_new_goal_first():
    trail = Trail()
    x = Var()
    log = []
    geler([x], _recorder(log), "first", trail)
    geler([x], _recorder(log), "second", trail)
    goals = state_of(x).delayed_goals
    assert [goal.argument for goal in goals] == ["second", "first"]


def test_attach_keeps_the_other_fields():
    trail = Trail()
    x = Var()
    put_state(x, SolverState(nonzero=True), trail)
    geler([x], _recorder([]), "g", trail)
    assert state_of(x).nonzero is True


def test_attach_is_undone():
    trail = Trail()
    x = Var()
    mark = trail.mark()
    geler([x], _recorder([]), "g", trail)
    trail.undo(mark)
    assert state_of(x) is None


def test_run_calls_a_goal_once():
    trail = Trail()
    log = []
    goal = DelayedGoal(Var(), _recorder(log), "g")
    assert run(goal, trail) is True
    assert run(goal, trail) is True
    assert log == ["g"]


def test_run_reports_the_goals_failure():
    trail = Trail()
    goal = DelayedGoal(Var(), _recorder([]), "fail")
    assert run(goal, trail) is False


def test_run_is_undone_and_runs_again():
    trail = Trail()
    log = []
    goal = DelayedGoal(Var(), _recorder(log), "g")
    mark = trail.mark()
    run(goal, trail)
    trail.undo(mark)
    run(goal, trail)
    assert log == ["g", "g"]


def test_verify_delayed_against_a_value_queues_the_goals():
    trail = Trail()
    x = Var()
    log = []
    geler([x], _recorder(log), "g", trail)
    later = LaterWork()
    assert verify_delayed(state_of(x), 4, trail, later) is True
    assert log == []                     # queued, not nested
    assert later.drain() is True
    assert log == ["g"]


def test_verify_delayed_onto_a_plain_variable_moves_the_goals():
    trail = Trail()
    x, y = Var(), Var()
    log = []
    geler([x], _recorder(log), "g", trail)
    later = LaterWork()
    assert verify_delayed(state_of(x), y, trail, later) is True
    assert not later.queue
    assert state_of(y).delayed_goals == state_of(x).delayed_goals


def test_verify_delayed_onto_a_variable_with_goals_runs_both_and_clears_y():
    trail = Trail()
    x, y = Var(), Var()
    log = []
    geler([x], _recorder(log), "x goal", trail)
    geler([y], _recorder(log), "y goal", trail)
    put_state(y, with_changes(state_of(y), nonzero=True), trail)
    later = LaterWork()
    assert verify_delayed(state_of(x), y, trail, later) is True
    assert state_of(y).delayed_goals is None
    assert state_of(y).nonzero is True
    assert later.drain() is True
    assert log == ["x goal", "y goal"]


def test_verify_delayed_without_goals_does_nothing():
    trail = Trail()
    later = LaterWork()
    assert verify_delayed(SolverState(), 4, trail, later) is True
    assert verify_delayed(None, Var(), trail, later) is True
    assert not later.queue


def test_a_failing_later_goal_fails_the_drain():
    trail = Trail()
    x = Var()
    geler([x], _recorder([]), "fail", trail)
    later = LaterWork()
    verify_delayed(state_of(x), 0, trail, later)
    assert later.drain() is False


def test_a_goal_on_two_variables_runs_once():
    trail = Trail()
    x, y = Var(), Var()
    log = []
    geler([x, y], _recorder(log), "g", trail)
    later = LaterWork()
    verify_delayed(state_of(x), 1, trail, later)
    verify_delayed(state_of(y), 2, trail, later)
    assert later.drain() is True
    assert log == ["g"]


def test_nonexhausted_and_attribute_goal_skip_run_goals():
    trail = Trail()
    x = Var()
    log = []
    geler([x], _recorder(log), "first", trail)
    geler([x], _recorder(log), "second", trail)
    goals = state_of(x).delayed_goals
    run(goals[1], trail)
    assert [goal.argument for goal in nonexhausted(goals)] == ["second"]
    assert [argument for _, argument in attribute_goal(x)] == ["second"]
    run(goals[0], trail)
    assert attribute_goal(x) is None
    assert attribute_goal(Var()) is None


def test_collect_nonlinear_marks_the_goals_done():
    trail = Trail()
    x, y = Var(), Var()
    log = []
    procedure = _recorder(log)
    geler([x, y], procedure, "shared", trail)
    geler([y], procedure, "own", trail)
    collected = collect_nonlinear([x, Var(), y], trail)
    assert collected == [(procedure, "shared"), (procedure, "own")]
    assert collect_nonlinear([x, y], trail) == []
    later = LaterWork()
    verify_delayed(state_of(y), 1, trail, later)
    later.drain()
    assert log == []                      # translate set every Mutex


def test_translate_skips_finished_goals():
    trail = Trail()
    goal = DelayedGoal(Var(), _recorder([]), "g")
    run(goal, trail)
    assert translate((goal,), trail) == []


def test_project_nonlinear_gives_the_variables_the_goals_reach():
    trail = Trail()
    x, y, z = Var(), Var(), Var()
    geler([x], _recorder([]), ("argument", [y, 3, (z, y)]), trail)
    reachable = project_nonlinear([], [x], trail)
    assert sorted(reachable, key=lambda v: v._id) == [y, z]
    assert project_nonlinear([], [x], trail) == []


def test_project_nonlinear_walks_records_and_deep_arguments():
    from clausal.logic.clpq.linear_forms import LinearForm
    trail = Trail()
    x, y = Var(), Var()
    deep = [y]
    for _ in range(50_000):
        deep = [deep]
    form = LinearForm((0, 1), (0, 1), [(x, (1, 1))])
    holder = Var()
    geler([holder], _recorder([]), (form, deep), trail)
    reachable = project_nonlinear([], [holder], trail)
    assert sorted(reachable, key=lambda v: v._id) == [x, y]
