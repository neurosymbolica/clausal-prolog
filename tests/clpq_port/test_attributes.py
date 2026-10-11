# tests/clpq_port/test_attributes.py
from clausal.logic.clpq.attributes import (
    LaterWork, SolverState, put_state, state_of, with_changes)
from clausal.logic.variables import Trail, Var
import pytest


def test_a_state_change_is_undone_on_backtracking():
    trail, x = Trail(), Var()
    put_state(x, SolverState(), trail)
    mark = trail.mark()
    put_state(x, with_changes(state_of(x), lower_strict=True), trail)
    assert state_of(x).lower_strict
    trail.undo(mark)
    assert state_of(x).lower_strict is False


def test_the_order_attribute_is_named_variable_order():
    # NAMES.md: `order` (the attribute) is `variable_order`.
    assert hasattr(SolverState(), "variable_order")
    with pytest.raises(TypeError):
        SolverState(ordering=1)
    state = with_changes(SolverState(), variable_order=7)
    assert state.variable_order == 7 and state.lower_strict is False


def test_later_work_runs_in_order_and_nests_no_frames():
    order = []
    work = LaterWork()

    def chain(i):
        def step():
            order.append(i)
            if i < 50_000:          # far past the recursion limit
                work.push(chain(i + 1))
            return True
        return step

    work.push(chain(0))
    assert work.drain()
    assert order == list(range(50_001))


def test_later_work_stops_at_the_first_failure():
    work = LaterWork()
    ran = []
    work.push(lambda: ran.append(1) or False)
    work.push(lambda: ran.append(2) or True)
    assert work.drain() is False and ran == [1]


def test_with_changes_rejects_an_unknown_field():
    with pytest.raises(TypeError):
        with_changes(SolverState(), ordering=1)


def test_an_exception_in_later_work_leaves_nothing_stale():
    work = LaterWork()
    ran = []

    def boom():
        raise ValueError("boom")

    work.push(boom)
    work.push(lambda: ran.append("stale") or True)
    with pytest.raises(ValueError):
        work.drain()
    assert work.drain() is True and ran == []
