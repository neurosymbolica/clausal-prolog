"""Simple-mode to trampoline-mode bridge.

``_tramp_call`` lets a shallow / simple-mode code path (which uses
Python ``for``-loops over generators) invoke a trampoline-compiled
predicate.  Internally it drives a mini-trampoline over the
``StepGenerator`` protocol and surfaces each solution as a plain
``yield None`` for the enclosing ``for`` loop to pick up.

Used by: NAF, once, lambda-bodies, and any other compile path that
is itself simple-mode but whose inner goal resolved to a
trampoline-mode dispatch.
"""

from __future__ import annotations

from clausal.logic.trampoline import (
    DONE, StepGenerator, _is_routable, _unwind_to_catcher,
)


def _tramp_call(dispatch_fn, args, trail):
    """Call a trampoline-mode dispatch fn from simple-mode context.

    Drives a mini-trampoline internally and yields None per solution.
    Used by simple-mode code paths (lambda bodies, NAF, once) that need
    to call trampoline-mode predicates.

    Exception routing, exactly as in the top-level drive loops: a callee raises
    in *this* frame, not in the caller's ``try``, so a ``catch/3`` written
    inside ``dispatch_fn`` only ever sees an exception this loop throws back
    into the ``catcher`` chain.  Without that, every handler under a ``once`` /
    ``findall`` / ``not`` / lambda body was inert — for ``throw/1`` as much as
    for a Python exception.  Anything the chain does not absorb propagates on
    to the shallow caller, whose own ``try`` covers this loop.
    """
    sg = StepGenerator(dispatch_fn, None, None, None, *args, trail)
    gen, value = sg.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield None
            gen, value = sg.send(None)
        else:
            try:
                gen, value = gen.send(value)
            except Exception as exc:  # noqa: BLE001 — see _is_routable
                if not _is_routable(exc):
                    raise
                gen, value = _unwind_to_catcher(gen, exc)


def _naf_has_solution(sg) -> bool:
    """True if the mini-trampolined goal *sg* yields at least one solution.

    The ``not`` lowering used to emit this loop inline as generated AST — a
    fifth copy of the drive loop, and the only one with no exception routing
    at all, so a ``catch/3`` inside a negated goal was inert and its exception
    escaped the negation entirely (review finding, 2026-08-25).  Keeping the
    loop here instead of in codegen means there is one routing policy to
    change, not one per emitter.

    Stops at the first solution: negation needs existence, not enumeration.
    """
    gen, value = sg.send(None)
    while True:
        if gen is None:
            return value is not DONE
        try:
            gen, value = gen.send(value)
        except Exception as exc:  # noqa: BLE001 — see _is_routable
            if not _is_routable(exc):
                raise
            gen, value = _unwind_to_catcher(gen, exc)
