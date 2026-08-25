"""Simple-mode to trampoline-mode bridge.

``_tramp_call`` lets a shallow / simple-mode code path (which uses
Python ``for``-loops over generators) invoke a trampoline-compiled
predicate.  Internally it drives the mini-trampoline — now
``_drive_until_yield``, i.e. the C loop in a built tree — over the
``StepGenerator`` protocol and surfaces each solution as a plain
``yield None`` for the enclosing ``for`` loop to pick up.

Used by: NAF, once, lambda-bodies, and any other compile path that
is itself simple-mode but whose inner goal resolved to a
trampoline-mode dispatch.
"""

from __future__ import annotations

from clausal.logic.trampoline import StepGenerator, _drive_until_yield


def _tramp_call(dispatch_fn, args, trail):
    """Call a trampoline-mode dispatch fn from simple-mode context.

    Yields ``None`` once per solution for the enclosing ``for`` loop.  Used
    by simple-mode code paths (lambda bodies, NAF, once) whose inner goal
    resolved to a trampoline-mode dispatch.

    Stepping and exception routing live in ``_drive_until_yield`` — the
    same driver (and, in a built tree, the same C loop) as the main query
    path, so a ``catch/3`` inside ``dispatch_fn`` sees exactly what it
    would see there: routable exceptions thrown back into the ``catcher``
    chain, mid-chain ``_TABLING_SUSPEND`` intercepted, exhaustion treated
    as exhaustion.  Anything unabsorbed propagates to the shallow caller,
    whose own ``try`` covers this loop.
    """
    sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
    while _drive_until_yield(sg):
        yield None


def _naf_has_solution(sg) -> bool:
    """True if the trampolined goal *sg* yields at least one solution.

    The ``not`` lowering used to emit this loop inline as generated AST —
    a drive-loop copy with no exception routing, so a ``catch/3`` inside a
    negated goal was inert (review finding, 2026-08-25).  Since then the
    loop lives at runtime; it is now ``_drive_until_yield`` itself, which
    stops at the first solution — negation needs existence, not
    enumeration.
    """
    return _drive_until_yield(sg) is True
