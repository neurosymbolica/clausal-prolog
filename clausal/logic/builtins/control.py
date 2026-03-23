"""Control builtins: TimeGoal/1, TimeGoal/2."""

from __future__ import annotations

import time as _time
import sys as _sys

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.predicate import is_term_instance, term_field_names

from clausal.logic.builtins._registry import (
    _trampoline_builtin, _ensure_trampoline_dispatch,
)


def _goal_dispatch_and_args(goal_val):
    """Return (dispatch_fn, args_tuple) for a goal value, or (None, None) on failure.

    Handles:
    - callable (Python function / lambda) → no extra args
    - object with _get_dispatch() (PredicateMeta class, BuiltinPredicate) → no extra args
    - PredicateMeta instance with compiled dispatch → dispatch from type, args from fields
    """
    if callable(goal_val) or hasattr(goal_val, '_get_dispatch'):
        return _ensure_trampoline_dispatch(goal_val), ()
    if is_term_instance(goal_val):
        cls = type(goal_val)
        # Only dispatch if the class has a compiled dispatch function.
        # This excludes AST nodes (And, Or, In as structural nodes, etc.) which
        # are PredicateMeta instances but do not have a compiled predicate body.
        if getattr(cls, '_dispatch_fn', None) is not None:
            args = tuple(getattr(goal_val, f) for f in term_field_names(goal_val))
            return cls._get_dispatch(), args
    return None, None


@_trampoline_builtin("TimeGoal", 1)
def _time_goal__1(this_generator, parent, goal, trail):
    """TimeGoal(Goal) — call Goal and print wall/CPU time after it completes.

    Analogous to SWI-Prolog time/1.  Each solution is forwarded to the parent;
    timing is printed (to stderr) once the goal is exhausted.

    Goal may be:
    - a Python callable / lambda (no extra args)
    - a PredicateMeta class or BuiltinPredicate (called with no args)
    - a predicate instance, e.g. In(X_, [1,2,3]) — dispatched with its fields
    """
    goal_val = deref(goal)
    dispatch, goal_args = _goal_dispatch_and_args(goal_val)
    if dispatch is None:
        yield (parent, DONE)
        return

    wall_start = _time.perf_counter()
    cpu_start = _time.process_time()

    sg = StepGenerator(dispatch, this_generator, *goal_args, trail)
    _st = yield (sg, None)
    solution_count = 0
    while _st is not DONE:
        solution_count += 1
        yield (parent, None)
        _st = yield (sg, None)

    wall_elapsed = _time.perf_counter() - wall_start
    cpu_elapsed = _time.process_time() - cpu_start
    print(
        f"% {solution_count} solution(s), "
        f"{wall_elapsed:.6f}s wall, {cpu_elapsed:.6f}s CPU",
        file=_sys.stderr,
    )
    yield (parent, DONE)


@_trampoline_builtin("TimeGoal", 2)
def _time_goal__2(this_generator, parent, goal, elapsed, trail):
    """TimeGoal(Goal, Elapsed) — run Goal; unify Elapsed with wall-clock seconds.

    Elapsed is unified after each solution of Goal.  If Goal fails, TimeGoal/2
    fails.  Backtracking into Goal is supported.

    Goal accepts the same forms as TimeGoal/1.
    """
    goal_val = deref(goal)
    dispatch, goal_args = _goal_dispatch_and_args(goal_val)
    if dispatch is None:
        yield (parent, DONE)
        return

    wall_start = _time.perf_counter()

    sg = StepGenerator(dispatch, this_generator, *goal_args, trail)
    _st = yield (sg, None)
    while _st is not DONE:
        elapsed_val = _time.perf_counter() - wall_start
        save = trail.mark()
        if unify(elapsed, elapsed_val, trail):
            yield (parent, None)
        trail.undo(save)
        _st = yield (sg, None)

    yield (parent, DONE)
