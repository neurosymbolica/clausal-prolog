"""Control builtins: time_goal/1, time_goal/2, call_nth/2, count_all/2,
setup_call_cleanup/3, call_cleanup/2, current_time/1, statistics/2.

The coroutining predicates (call_nth, count_all, setup_call_cleanup, call_cleanup,
freeze, when) are compiled as **compiler special forms** in ``compiler.py``.
This module registers their field names and also provides runtime builtins
for current_time/1, statistics/2, and time_goal/1,2.
"""

from __future__ import annotations

import sys as _sys
import time as _time

from clausal.logic.atoms import is_atom as _term_is_atom, mint, spelling
from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.logic.predicate import (
    is_term_instance, term_field_names, _dispatch_at,
    is_declared_predicate_name, localize_goal,
)

from clausal.logic.builtins._registry import (
    _BUILTIN_FIELDS, _builtin, _DB_BUILTINS,
    _trampoline_builtin, _ensure_trampoline_dispatch,
)
from clausal.logic.cells import (
    compound_cell_shape, CELL_GOAL_CONTROL_FUNCTORS, QUALIFIED_GOAL_FUNCTOR,
)


# Register field names for class construction.
# The actual dispatch is handled by compiler special forms in compiler.py.
_BUILTIN_FIELDS[("call_nth", 2)] = ("goal", "n")
_BUILTIN_FIELDS[("count_all", 2)] = ("goal", "count")
_BUILTIN_FIELDS[("setup_call_cleanup", 3)] = ("setup", "call", "cleanup")
_BUILTIN_FIELDS[("call_cleanup", 2)] = ("call", "cleanup")
_BUILTIN_FIELDS[("freeze", 2)] = ("variable", "goal")
_BUILTIN_FIELDS[("when", 2)] = ("condition", "goal")


def _goal_dispatch_and_args(goal_val, db=None, context="time_goal/1"):
    """Return (dispatch_fn, args_tuple) for a goal value, or (None, None) on failure.

    Handles:
    - callable (Python function / lambda) → no extra args
    - object with _get_dispatch() (PredicateMeta class, BuiltinPredicate) → no extra args
    - PredicateMeta instance with compiled dispatch → dispatch from type, args from fields
    - a CELL, which NAMES a predicate and carries no class (P2)

    Both branches already know how many arguments they are about to supply — a
    bare name gets none, an instance gets one per field — so both pass that count
    down, and ``time_goal(citation)`` against ``citation/3`` names the arity
    instead of reporting three missing positional arguments.

    The cell arm is why *db* is here at all: a cell has only a name, and the
    only correct place to look a name up is the calling module (R-P2-2,
    module locality) -- the same reason call/N became db-receiving in P3-3
    Task 5, and phrase/2,3 in this sweep.  It is narrowed the same way: a
    control construct and a module-qualified goal are turned away, because
    the shared resolver RAISES for them where time_goal has always failed.

    That narrowing is NOT "time_goal never raises where the resolver does":
    a dangling predicate HANDLE (a mangled functor whose module never
    loaded, or whose loaded module lacks the predicate) RAISES here
    ``existence_error(procedure, Name/Arity)``, exactly as ``call/N`` does
    (ruling 2 extended, 2026-09-24).  It is a reference that was supposed to
    resolve, and failing silently is how that mistake stays invisible.
    """
    # W4b-3: ``is_declared_predicate_name`` admits the module-qualified
    # HANDLE a predicate name is bound to after the flip.
    if callable(goal_val) or hasattr(goal_val, '_get_dispatch') \
            or is_declared_predicate_name(goal_val, db=db):
        # Operator ruling 2026-09-24: an imported predicate reached through
        # an unqualified name resolves under that name in the calling module.
        return _ensure_trampoline_dispatch(localize_goal(db, goal_val), 0), ()
    is_cell, functor = compound_cell_shape(goal_val)
    if is_cell and functor not in CELL_GOAL_CONTROL_FUNCTORS and functor != QUALIFIED_GOAL_FUNCTOR:
        from clausal.logic.builtins.higher_order import _resolve_named_goal  # noqa: PLC0415
        resolved = _resolve_named_goal(db, goal_val, (), context)
        if resolved is not None:
            return resolved
        return None, None
    if is_term_instance(goal_val):
        cls = type(goal_val)
        # Only dispatch if the class has a compiled dispatch function.
        # This excludes AST nodes (And, Or, in_ as structural nodes, etc.) which
        # are PredicateMeta instances but do not have a compiled predicate body.
        # The ROW's dispatch (W2).  ``getattr``: ``is_term_instance`` is
        # also true of a ``@dataclass`` instance, whose class has no ``_row``
        # at all (roborev on 9028f9b3) -- that goal falls through to
        # ``(None, None)`` as it always did.  A predicate class on no row has
        # no dispatch, and the probe must not mint a row for an AST node.
        row = getattr(cls, "_row", None)
        if row is not None and row.dispatch_fn is not None:
            args = tuple(getattr(goal_val, f) for f in term_field_names(goal_val))
            return _dispatch_at(cls, len(args)), args
    return None, None


def _make_time_goal_factory(impl):
    """Bind the caller's database into a ``time_goal/N`` dispatch.

    Registered straight into ``_DB_BUILTINS`` rather than through
    ``@_db_builtin`` because that decorator wraps its product with
    ``_simple_to_trampoline`` and these are already trampoline-native --
    the same hand registration ``_make_call_goal_factory`` uses.
    ``_db_optional``: every goal shape that worked before is resolved
    without a database, so ``factory(None)`` is the pre-P2 time_goal.
    """
    def factory(db):
        def _time_goal_dispatch(*args):
            return impl(db, *args)
        _time_goal_dispatch.__name__ = impl.__name__
        return _time_goal_dispatch
    factory._db_optional = True
    return factory


def _time_goal__1(db, this_generator, _proceed, _fail, _catcher, goal, trail):
    """time_goal(Goal) — call Goal and print wall/CPU time after it completes.

    Analogous to SWI-Prolog time/1.  Each solution is forwarded to the _proceed;
    timing is printed (to stderr) once the goal is exhausted.

    Goal may be:
    - a Python callable / lambda (no extra args)
    - a PredicateMeta class or BuiltinPredicate (called with no args)
    - a predicate instance, e.g. in_(X_, [1,2,3]) — dispatched with its fields
    """
    goal_val = deref(goal)
    dispatch, goal_args = _goal_dispatch_and_args(goal_val, db, "time_goal/1")
    if dispatch is None:
        yield (_fail, DONE)
        return

    wall_start = _time.perf_counter()
    cpu_start = _time.process_time()

    sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *goal_args, trail)
    _st = yield (sg, None)
    solution_count = 0
    while _st is not DONE:
        solution_count += 1
        yield (_proceed, None)
        _st = yield (sg, None)

    wall_elapsed = _time.perf_counter() - wall_start
    cpu_elapsed = _time.process_time() - cpu_start
    print(
        f"# {solution_count} solution(s), "
        f"{wall_elapsed:.6f}s wall, {cpu_elapsed:.6f}s CPU",
        file=_sys.stderr,
    )
    yield (_fail, DONE)


def _time_goal__2(db, this_generator, _proceed, _fail, _catcher, goal, elapsed, trail):
    """time_goal(Goal, Elapsed) — run Goal; unify Elapsed with wall-clock seconds.

    Elapsed is unified after each solution of Goal.  If Goal fails, time_goal/2
    fails.  Backtracking into Goal is supported.

    Goal accepts the same forms as time_goal/1.
    """
    goal_val = deref(goal)
    dispatch, goal_args = _goal_dispatch_and_args(goal_val, db, "time_goal/2")
    if dispatch is None:
        yield (_fail, DONE)
        return

    wall_start = _time.perf_counter()

    sg = StepGenerator(dispatch, this_generator, this_generator, this_generator, *goal_args, trail)
    _st = yield (sg, None)
    while _st is not DONE:
        elapsed_val = _time.perf_counter() - wall_start
        save = trail.mark()
        if unify(elapsed, elapsed_val, trail):
            yield (_proceed, None)
        trail.undo(save)
        _st = yield (sg, None)

    yield (_fail, DONE)


_DB_BUILTINS[("time_goal", 1)] = _make_time_goal_factory(_time_goal__1)
_BUILTIN_FIELDS[("time_goal", 1)] = ("goal",)
_DB_BUILTINS[("time_goal", 2)] = _make_time_goal_factory(_time_goal__2)
_BUILTIN_FIELDS[("time_goal", 2)] = ("goal", "elapsed")


# ── Runtime builtins ──────────────────────────────────────────────────────

_start_wall = _time.monotonic()


@_builtin("current_time", 1)
def _current_time__1(t, trail, k):
    """current_time(T) — unify T with the current Unix timestamp (float)."""
    if unify(t, _time.time(), trail):
        yield None


@_builtin("statistics", 2)
def _statistics__2(key, value, trail, k):
    """statistics(Key, Value) — query runtime statistics.

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
        # Enumerate all stats.  THE FLIP (spec §6.4): a Key is an ATOM, so
        # the enumeration binds the minted atom, not the bare spelling.
        for stat_name, stat_fn in stats:
            mark = trail.mark()
            if unify(key, mint(stat_name), trail) \
                    and unify(value, stat_fn(), trail):
                yield None
            trail.undo(mark)
    elif _term_is_atom(key_val):
        spelt = spelling(key_val)
        for stat_name, stat_fn in stats:
            if stat_name == spelt:
                if unify(value, stat_fn(), trail):
                    yield None
                return
        # Unknown key → fail
