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

from clausal.logic.trampoline import DONE, StepGenerator


def _tramp_call(dispatch_fn, args, trail):
    """Call a trampoline-mode dispatch fn from simple-mode context.

    Drives a mini-trampoline internally and yields None per solution.
    Used by simple-mode code paths (lambda bodies, NAF, once) that need
    to call trampoline-mode predicates.
    """
    sg = StepGenerator(dispatch_fn, None, *args, trail)
    gen, value = sg.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield None
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)
