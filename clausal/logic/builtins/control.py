"""Control builtins: CallNth/2, CountAll/2, SetupCallCleanup/3, CallCleanup/2,
CurrentTime/1, Statistics/2.

The coroutining predicates (CallNth, CountAll, SetupCallCleanup, CallCleanup,
Freeze, When) are compiled as **compiler special forms** in ``compiler.py``.
This module registers their field names and also provides runtime builtins
for CurrentTime/1 and Statistics/2.
"""

from __future__ import annotations

import time as _time

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.builtins._registry import _BUILTIN_FIELDS, _builtin


# Register field names for class construction.
# The actual dispatch is handled by compiler special forms in compiler.py.
_BUILTIN_FIELDS[("CallNth", 2)] = ("goal", "n")
_BUILTIN_FIELDS[("CountAll", 2)] = ("goal", "count")
_BUILTIN_FIELDS[("SetupCallCleanup", 3)] = ("setup", "call", "cleanup")
_BUILTIN_FIELDS[("CallCleanup", 2)] = ("call", "cleanup")
_BUILTIN_FIELDS[("Freeze", 2)] = ("variable", "goal")
_BUILTIN_FIELDS[("When", 2)] = ("condition", "goal")


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
        stats.append(("memory", lambda: _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss * 1024))
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
