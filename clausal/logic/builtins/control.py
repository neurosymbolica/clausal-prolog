"""Control builtins: TimeGoal/1, TimeGoal/2, CallNth/2, CountAll/2,
SetupCallCleanup/3, CallCleanup/2, CurrentTime/1, Statistics/2.

The coroutining predicates (CallNth, CountAll, SetupCallCleanup, CallCleanup,
Freeze, When) are compiled as **compiler special forms** in ``compiler.py``.
This module registers their field names and also provides runtime builtins
for CurrentTime/1, Statistics/2, and TimeGoal/1,2.
"""

from __future__ import annotations

import sys as _sys

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.predicate import is_term_instance, term_field_names

from clausal.logic.builtins._registry import (
    _BUILTIN_FIELDS, _builtin,
    _trampoline_builtin, _ensure_trampoline_dispatch,
)


# Register field names for class construction.
# The actual dispatch is handled by compiler special forms in compiler.py.
_BUILTIN_FIELDS[("CallNth", 2)] = ("goal", "n")
_BUILTIN_FIELDS[("CountAll", 2)] = ("goal", "count")
_BUILTIN_FIELDS[("SetupCallCleanup", 3)] = ("setup", "call", "cleanup")
_BUILTIN_FIELDS[("CallCleanup", 2)] = ("call", "cleanup")
_BUILTIN_FIELDS[("Freeze", 2)] = ("variable", "goal")
_BUILTIN_FIELDS[("When", 2)] = ("condition", "goal")


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


# ── Runtime builtins ──────────────────────────────────────────────────────

_start_wall = _time.monotonic()


@_builtin("CurrentTime", 1)
def _current_time__1(t, trail, k):
    """CurrentTime(T) — unify T with the current Unix timestamp (float)."""
    if unify(t, _time.time(), trail):
        yield None


@_builtin("Statistics", 2)
def _statistics__2(key, value, trail, k):
    """Statistics(Key, Value) — query runtime statistics.

    Key bound → look up that stat. Key unbound → enumerate all stats.
    """
    key_val = deref(key)

    stats = [
        ("wall_time", lambda: _time.monotonic() - _start_wall),
        ("cpu_time", lambda: _time.process_time()),
    ]
    # Try to add memory stat (not available on all platforms)
    try:
        import resource as _resource
        import sys as _sys_res
        # ru_maxrss is in KB on Linux, bytes on macOS
        _rss_scale = 1024 if _sys_res.platform != "darwin" else 1
        stats.append(("memory", lambda: _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss * _rss_scale))
    except ImportError:
        pass

    if is_var(key_val):
        # Enumerate all stats
        for stat_name, stat_fn in stats:
            mark = trail.mark()
            if unify(key, stat_name, trail) and unify(value, stat_fn(), trail):
                yield None
            trail.undo(mark)
    elif isinstance(key_val, str):
        for stat_name, stat_fn in stats:
            if stat_name == key_val:
                if unify(value, stat_fn(), trail):
                    yield None
                return
        # Unknown key → fail
