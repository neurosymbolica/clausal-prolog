# clausal/logic/clpq/attributes.py
"""The per-variable solver state and the queue for follow-up work.

The state is one record per constrained variable, replaced (never mutated)
through put_attr, so the engine's trail undoes every change
(test_a_state_change_is_undone_on_backtracking).  The fields are
clp(q,r) 1.3.3's attributes in full words (NAMES.md).

Records are immutable by convention.  A collection field (delayed_goals, or
any list) is a value that is replaced, never edited in place: with_changes
copies shallowly, so an in-place edit would reach every copy and escape the
trail.
"""
from collections import deque

from clausal.logic.variables import get_attr, put_attr

CLPQ_KEY = "clpq_holzbaur"

_FIELDS = ("linear_form", "bounds", "lower_strict", "upper_strict",
           "component", "variable_order", "nonzero", "delayed_goals",
           "forward", "target", "keep_independent", "keep")


class SolverState:
    __slots__ = _FIELDS

    def __init__(self, linear_form=None, bounds=None, lower_strict=False,
                 upper_strict=False, component=None, variable_order=None,
                 nonzero=False, delayed_goals=None, forward=None,
                 target=False, keep_independent=False, keep=False):
        self.linear_form = linear_form
        self.bounds = bounds
        self.lower_strict = lower_strict
        self.upper_strict = upper_strict
        self.component = component
        self.variable_order = variable_order
        self.nonzero = nonzero
        self.delayed_goals = delayed_goals
        self.forward = forward
        self.target = target
        self.keep_independent = keep_independent
        self.keep = keep


def state_of(variable):
    return get_attr(variable, CLPQ_KEY)


def with_changes(state, **fields):
    values = {}
    for name in _FIELDS:
        values[name] = getattr(state, name)
    values.update(fields)
    return SolverState(**values)        # an unknown field raises TypeError


def put_state(variable, state, trail):
    put_attr(variable, CLPQ_KEY, state, trail)


class LaterWork:
    """Follow-up work (1.3.3's Later goals), run by one loop, never nested."""
    __slots__ = ("queue",)

    def __init__(self):
        self.queue = deque()

    def push(self, work):
        self.queue.append(work)

    def drain(self):
        queue = self.queue
        try:
            while queue:
                if not queue.popleft()():
                    queue.clear()
                    return False
        except BaseException:
            queue.clear()
            raise
        return True
