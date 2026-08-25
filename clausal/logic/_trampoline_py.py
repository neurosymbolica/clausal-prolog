"""Pure-Python twin of the C drive loops in ``runtime/_trampoline.c``.

Always importable; in a built tree ``logic/trampoline.py`` re-exports the
C implementations and this module is reached only by
``tests/test_trampoline_parity.py``, which runs the same behavioural
corpus against both.  The C side is canonical: fix divergences HERE.

``_is_routable`` / ``_unwind_to_catcher`` also serve the always-Python
drive-loop consumers (``runtime/tramp_call.py``) regardless of which
implementation is active.
"""

from __future__ import annotations
from typing import Any, Callable, Generator

# ── Which exceptions the drive loops route to catch/3 ────────────────────────
#
# A trampoline-compiled predicate does not *call* its callees: it yields
# ``(child, None)`` and the driver runs the child.  So a callee raises inside
# the driver's frame, never inside the ``try`` that a compiled ``catch/3`` put
# in the caller — the driver is the only place that can put the exception back
# where the author wrote the handler, which it does by throwing it into the
# failing generator's ``catcher`` chain.
#
# This used to be done for ``LogicException`` alone, which quietly made
# ``catch/3`` type-dependent: ``throw/1`` and the typed builtin errors were
# routed, while a ValueError out of a ``++`` escape or a NameError from an
# unimported predicate walked past every enclosing handler.  The shallow route
# has always caught both — ``_compile_catch_impl`` emits ``except Exception``
# and converts anything that is not a LogicException with ``python_error_term``
# — so routing every ``Exception`` is what makes the two routes agree.  It is
# also A09-D002's "typed exceptions" policy read the other way round: an error
# a builtin failed to type is still the author's to catch, not the driver's to
# leak.
#
# The exclusions are the exceptions that are *protocol*, not errors:
#
#   - ``BaseException``-only classes — ``GeneratorExit`` (an abandoned search),
#     ``KeyboardInterrupt`` / ``SystemExit`` (``halt/1``).  ``except Exception``
#     in the catch frame would decline these anyway; routing them would park a
#     shutdown signal in a handler that cannot act on it.
#   - ``StopIteration``, the generator protocol's own end-of-iteration marker.
#     A drive loop that treats exhaustion as exhaustion must see it first; a
#     ``catch/3`` that swallowed it would turn a finished search into a
#     recovery goal.  (The PEP-479 ``RuntimeError`` wrapper around one is
#     likewise consumed as exhaustion by ``_drive_until_yield`` *before* this
#     test — A04-F009.)
#
# KEEP IN SYNC with ``is_routable_exception`` in ``runtime/_trampoline.c``,
# which is the implementation that actually runs.


def _is_routable(exc: BaseException) -> bool:
    """True when *exc* is an error ``catch/3`` may handle, not a control signal."""
    if not isinstance(exc, Exception) or isinstance(exc, StopIteration):
        return False
    if isinstance(exc, RuntimeError):
        # The engine talking to itself: a PEP-479 wrapper (a converted
        # exhaustion) or the StepGen protocol error (a compiler bug).  Neither
        # is the author's to catch, and excluding them HERE — not only in
        # ``_drive_until_yield``, which tests the wrapper before it asks about
        # routing — keeps all four drive loops agreeing on what a handler sees.
        if isinstance(exc.__cause__, StopIteration):
            return False
        if getattr(exc, "__clausal_engine_protocol__", False):
            return False
    return True


def _unwind_to_catcher(failed_gen: Any, exc: Exception) -> tuple:
    """Throw *exc* into *failed_gen*'s ``catcher`` chain; return the resumed step.

    Walks up the chain until some frame's ``catch/3`` absorbs *exc* and yields,
    and returns that ``(gen, value)`` step so the drive loop can carry on.  A
    handler that declines re-raises (bare ``raise`` in the compiled ``else``
    branch), which continues the walk from that frame's own catcher.

    If nothing absorbs it, the exception is re-raised **unchanged and on its
    original traceback** — the enrichment seam in ``solve._drive_trampoline``
    and every embedding caller's ``except`` clause both match on the real type,
    so routing must be invisible when it finds no taker.
    """
    target = getattr(failed_gen, "catcher", None)
    while target is not None:
        try:
            return target.throw(exc)
        except Exception as new_exc:  # noqa: BLE001 — see _is_routable
            if not _is_routable(new_exc):
                raise
            exc = new_exc
            target = getattr(target, "catcher", None)
    raise exc


# ── DONE / FINAL sentinels ───────────────────────────────────────────
# ``FINAL`` is the third yield-action sentinel.  The three producer
# postures the protocol carries:
#
#   yield (proceed, None)   — here's a solution, pull again for more
#   yield (fail,    DONE)   — no solution, I'm exhausted
#   yield (proceed, FINAL)  — here's a solution AND I'm retiring;
#                             don't pull again.
#
# See ``implementation_plans/CONTINUATION_TCO_PLAN.md`` §4.1 / Phase 4
# (historically called the ``commit`` variant in design docs).
# Phase 4a (this commit) lands the sentinel and root-driver handling
# only; no producer emits ``FINAL`` yet, so the new branches are cold
# and existing call sites pay zero overhead.
DONE: object = object()
FINAL: object = object()

# ── StepGenerator ─────────────────────────────────────────────────────

class StepGenerator:
    """Wraps a generator function, providing ``this_generator`` automatically.

    Usage::

        sg = StepGenerator(pred_fn, proceed, fail, catcher, arg0, arg1, trail)

    The three continuation slots steer three independent dataflows:

    - ``proceed`` — where yielded solutions go (consumer frame).
    - ``fail``    — where to resume on child exhaustion (completion).
    - ``catcher`` — where thrown exceptions propagate (handler chain).

    For normal (non-TCO) call sites the caller passes the same frame for
    all three; continuation-level TCO later sets ``proceed`` to the
    caller's own ``proceed`` while keeping ``fail`` / ``catcher`` pointed
    at the caller.  See ``implementation_plans/CONTINUATION_TCO_PLAN.md``.

    The generator body receives the three continuation slots as its
    first three parameters after ``this_generator``:
    ``pred_fn(sg, proceed, fail, catcher, *args)``.

    ``send(value)`` handles first-call bootstrapping transparently: the
    first call does ``next(inner_gen)``; subsequent calls delegate to
    ``inner_gen.send(value)``.
    """
    __slots__ = ('_gen', '_started', 'proceed', 'fail', 'catcher')

    def __init__(
        self,
        func: Callable,
        proceed: Any,
        fail: Any,
        catcher: Any,
        *args: Any,
    ) -> None:
        self.proceed = proceed
        self.fail = fail
        self.catcher = catcher
        # Forward all three continuation slots to the generator body.
        # Compiled-predicate signature is
        # (this_generator, _proceed, _fail, _catcher, *args, trail).
        self._gen: Generator = func(self, proceed, fail, catcher, *args)
        self._started: bool = False

    def send(self, value: Any) -> tuple:
        try:
            if self._started:
                return self._gen.send(value)
            self._started = True
            return next(self._gen)
        except StopIteration:
            # C≡Py: StepGen_send converts a returning inner generator
            # (PYGEN_RETURN) into the marked engine-protocol error; a
            # compiled predicate always final-yields (fail, DONE), so a
            # bare return is an engine anomaly, not exhaustion.
            err = RuntimeError(
                "StepGenerator inner generator returned "
                "unexpectedly (no final yield)")
            err.__clausal_engine_protocol__ = True
            raise err

    def throw(self, *args: Any) -> tuple:
        return self._gen.throw(*args)

    def close(self) -> None:
        self._gen.close()

# ── Trampoline ────────────────────────────────────────────────────────

def trampoline(root: StepGenerator) -> Any:
    """
    Drive a chain of tuple-yielding generators without growing the call stack.

    Each generator yields ``(target, value)`` tuples.  The trampoline loop is
    just::

        step = root.send(None)
        while step[0] is not None:
            step = step[0].send(step[1])
        return step[1]

    No ``started`` set, no ``resume`` helper — StepGenerator handles
    bootstrapping internally.

    Exception routing: when a generator raises, the throwing generator is
    dead (its try/finally already ran trail.undo).  We unwind through the
    ``catcher`` chain using .throw() until a catch/3 handler catches it.
    See ``_is_routable`` for which exceptions take that path.
    """
    gen, value = root.send(None)
    while gen is not None:
        try:
            gen, value = gen.send(value)
        except Exception as exc:  # noqa: BLE001 — see _is_routable
            if not _is_routable(exc):
                raise
            gen, value = _unwind_to_catcher(gen, exc)
    return value

def solutions(root: StepGenerator, snapshot: Callable | None = None) -> list:
    """Collect all solution values from *root* until DONE.

    If *snapshot* is provided, it is called while bindings are live
    and its return value is collected instead of the raw solution value.

    Handles SLG tabling: ``_TABLING_SUSPEND`` is intercepted and converted
    to DONE so the parent's while-loop exits normally.  The consumer
    generator remains saved in the table entry's suspended list for later
    resumption by the leader's completion phase.

    Exception routing: same as trampoline() — unwind through the
    ``catcher`` chain via .throw() until caught or surface to Python.
    """
    from clausal.logic.tabling import _TABLING_SUSPEND

    results: list = []
    gen, value = root.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return results
            if value is _TABLING_SUSPEND:
                # A04-F008: a root/orphaned consumer yields
                # (None, _TABLING_SUSPEND) — a control sentinel, never a
                # solution. Treating it as one fabricates an unbound answer.
                return results
            if value is FINAL:
                # Producer is retiring with its last solution: deliver
                # it and stop — no further pull from the (now-retired)
                # root.  ``FINAL`` is a sentinel, not a payload, so
                # when *snapshot* is None there's no raw value to
                # record.
                if snapshot is not None:
                    results.append(snapshot())
                return results
            results.append(snapshot() if snapshot is not None else value)
            gen, value = root.send(None)
        else:
            try:
                # Intercept _TABLING_SUSPEND → send DONE to parent instead
                if value is _TABLING_SUSPEND:
                    gen, value = gen.send(DONE)
                else:
                    gen, value = gen.send(value)
            except Exception as exc:  # noqa: BLE001 — see _is_routable
                if not _is_routable(exc):
                    raise
                gen, value = _unwind_to_catcher(gen, exc)

def _drive_until_yield(sg: StepGenerator) -> bool | None:
    """Pure-Python fallback for C _drive_until_yield.

    Calls sg.send(None) and loops through the trampoline chain until a
    solution is found (returns True) or the search is exhausted (returns
    None).
    """
    from clausal.logic.tabling import _TABLING_SUSPEND

    try:
        gen, value = sg.send(None)
    except StopIteration:
        return None
    except RuntimeError as exc:
        # A04-F009 (C≡Py parity): a PEP-479 "generator raised
        # StopIteration" wrapper is a converted exhaustion; a genuine
        # RuntimeError (user ++ escape, protocol bug) must propagate.
        if isinstance(exc.__cause__, StopIteration):
            return None
        raise
    while True:
        if gen is None:
            if value is DONE or value is _TABLING_SUSPEND:
                return None   # A04-F008: suspend sentinel is not a solution
            return True
        try:
            if value is _TABLING_SUSPEND:
                gen, value = gen.send(DONE)
            else:
                gen, value = gen.send(value)
        except StopIteration:
            return None
        except Exception as exc:  # noqa: BLE001 — see _is_routable
            # A04-F009: mirror the narrowed C catch (PEP-479 → exhaustion).
            # This test comes FIRST so a converted exhaustion is never
            # offered to a catch/3 as an error.
            if isinstance(exc, RuntimeError) and isinstance(
                exc.__cause__, StopIteration
            ):
                return None
            if not _is_routable(exc):
                raise
            gen, value = _unwind_to_catcher(gen, exc)
