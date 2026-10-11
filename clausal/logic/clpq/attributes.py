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


# ---------------------------------------------------------------- the bound type
#
# 1.3.3's `type/1` attribute (bv.pl, lines 64-74): one of t_none, t_l(L),
# t_u(U), t_lu(L,U), and the same with the ACTIVE bound in capitals (NAMES.md,
# ruling R6).  The port keeps it as one record: an int kind and the bound
# values (rationals, None where the type has no such bound).

BOUNDS_NONE = 0
BOUNDS_LOWER = 1
BOUNDS_UPPER = 2
BOUNDS_LOWER_UPPER = 3
BOUNDS_LOWER_ACTIVE = 4
BOUNDS_UPPER_ACTIVE = 5
BOUNDS_LOWER_ACTIVE_UPPER = 6
BOUNDS_LOWER_UPPER_ACTIVE = 7

_BOUNDS_NAMES = ("bounds_none", "bounds_lower", "bounds_upper",
                 "bounds_lower_upper", "bounds_lower_active",
                 "bounds_upper_active", "bounds_lower_active_upper",
                 "bounds_lower_upper_active")


class Bounds:
    """The bound type `t_*`: `kind` is one of the BOUNDS_* ints; `lower` and
    `upper` are rationals, or None.  Immutable by convention."""
    __slots__ = ("kind", "lower", "upper")

    def __init__(self, kind, lower, upper):
        self.kind = kind
        self.lower = lower
        self.upper = upper

    def __eq__(self, other):
        return (type(other) is Bounds and self.kind == other.kind
                and self.lower == other.lower and self.upper == other.upper)

    def __hash__(self):
        return hash((self.kind, self.lower, self.upper))

    def __repr__(self):
        name = _BOUNDS_NAMES[self.kind]
        if self.lower is None and self.upper is None:
            return name
        if self.lower is None:
            return f"{name}({self.upper!r})"
        if self.upper is None:
            return f"{name}({self.lower!r})"
        return f"{name}({self.lower!r}, {self.upper!r})"


_NO_BOUNDS = Bounds(BOUNDS_NONE, None, None)


def bounds_none():
    """t_none."""
    return _NO_BOUNDS


def bounds_lower(lower):
    """t_l(L)."""
    return Bounds(BOUNDS_LOWER, lower, None)


def bounds_upper(upper):
    """t_u(U)."""
    return Bounds(BOUNDS_UPPER, None, upper)


def bounds_lower_upper(lower, upper):
    """t_lu(L, U)."""
    return Bounds(BOUNDS_LOWER_UPPER, lower, upper)


def bounds_lower_active(lower):
    """t_L(L)."""
    return Bounds(BOUNDS_LOWER_ACTIVE, lower, None)


def bounds_upper_active(upper):
    """t_U(U)."""
    return Bounds(BOUNDS_UPPER_ACTIVE, None, upper)


def bounds_lower_active_upper(lower, upper):
    """t_Lu(L, U)."""
    return Bounds(BOUNDS_LOWER_ACTIVE_UPPER, lower, upper)


def bounds_lower_upper_active(lower, upper):
    """t_lU(L, U)."""
    return Bounds(BOUNDS_LOWER_UPPER_ACTIVE, lower, upper)


# ---------------------------------------------------------------- strictness
#
# 1.3.3's `strictness/1` attribute is an int: bit 0b10 a strict lower bound,
# bit 0b01 a strict upper bound.  The state keeps the two bits as the fields
# lower_strict and upper_strict; these two functions convert.

def strictness(state):
    """The strictness/1 value of *state*: 0b10 lower | 0b01 upper."""
    bits = 0
    if state.lower_strict:
        bits |= 0b10
    if state.upper_strict:
        bits |= 0b01
    return bits


def strictness_fields(bits):
    """(lower_strict, upper_strict) for the strictness/1 value *bits*."""
    return (bits & 0b10) != 0, (bits & 0b01) != 0
