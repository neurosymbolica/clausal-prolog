"""
Generator-based trampoline.

Protocol
--------
Every participating generator yields **tuples** ``(target, value)`` to steer
the trampoline:

  (this_generator, v)  – resume *this* generator with value v
                         (iterative step / tail call — no stack growth)
  (child,          v)  – start a fresh nested computation; the child will
                         eventually yield (parent, result) to resume self
  (parent,         v)  – return v to the calling generator
  (None,           v)  – the root computation is done; v is the final answer

StepGenerator
-------------
A generator cannot normally refer to itself before it is fully constructed.
``StepGenerator`` solves this by acting as a thin wrapper: it is created
*first*, then calls the generator function passing itself as the
``this_generator`` parameter.  The compiled function signature is::

    def pred__N(this_generator, parent, arg0, …, argN, trail):
        …

No bootstrap ``self = yield`` is needed — ``this_generator`` is just a
regular parameter.

A C extension (_trampoline) provides optimised versions of StepGenerator
and trampoline() for production use.  This module is the pure-Python
reference implementation.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Generator

# ── Step (legacy) ─────────────────────────────────────────────────────────────
# Kept for backward compatibility with existing compiled code and tests.
# New code should yield plain tuples (gen, value) instead.

@dataclass
class Step:
    """Steering token yielded by every participating generator (legacy)."""
    gen: Generator | None
    value: Any = None


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


# ── C extension fast path ────────────────────────────────────────────────────
# _trampoline is a C extension providing optimised DONE, StepGenerator,
# trampoline, and solutions.  Fall back to pure-Python implementations below.

try:
    from clausal.logic.runtime._trampoline import DONE, FINAL, StepGenerator, trampoline, solutions, _drive_until_yield  # type: ignore[import-untyped]
except ImportError:
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

    class StepGenerator:  # type: ignore[no-redef]
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
            if self._started:
                return self._gen.send(value)
            self._started = True
            return next(self._gen)

        def throw(self, *args: Any) -> tuple:
            return self._gen.throw(*args)

        def close(self) -> None:
            self._gen.close()

    # ── Trampoline ────────────────────────────────────────────────────────

    def trampoline(root: StepGenerator) -> Any:  # type: ignore[no-redef]
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

    def solutions(root: StepGenerator, snapshot: Callable | None = None) -> list:  # type: ignore[no-redef]
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

    def _drive_until_yield(sg: StepGenerator) -> bool | None:  # type: ignore[no-redef]
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


# ── Minimal test problem: n! ─────────────────────────────────────────────────
#
# Uses all three targets in one small program:
#
#   factorial → validate    (child,  …)   new generator (sub-computation)
#   validate  → factorial   (parent, n)   return to caller
#   factorial → factorial   (self,   n-1) iterative step via trampoline
#   factorial → None        (None,   acc) root computation complete
#
# Trace for factorial(None, 4):
#
#   factorial  →  validate     [child]   validate(4) …
#   validate   →  factorial    [parent]  n = 4
#   factorial  →  factorial    [self]    n = 3, acc = 4
#   factorial  →  factorial    [self]    n = 2, acc = 12
#   factorial  →  factorial    [self]    n = 1, acc = 24
#   factorial  →  None         [done]    return 24

def validate(
    this_generator: StepGenerator,
    proceed: StepGenerator | None,
    fail: StepGenerator | None,
    catcher: StepGenerator | None,
    n: int,
) -> Generator:
    """
    Leaf sub-computation: assert n >= 0, then echo it back to proceed.
    Exists solely to demonstrate the 'new generator' (child) target.
    """
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}")
    yield (proceed, n)


def factorial(
    this_generator: StepGenerator,
    proceed: StepGenerator | None,
    fail: StepGenerator | None,
    catcher: StepGenerator | None,
    n: int,
) -> Generator:
    """Compute n! while exercising all three targets."""

    # ① (child, …) — delegate to a fresh generator for input validation
    n = yield (StepGenerator(validate, this_generator, this_generator, this_generator, n), None)

    acc = 1
    while n > 1:
        acc *= n
        # ② (this_generator, …) — the trampoline drives the loop; no recursion depth
        n = yield (this_generator, n - 1)

    # ③ (proceed, …) — surface the answer to whoever called us
    yield (proceed, acc)


# ── Tests ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [(0, 1), (1, 1), (2, 2), (5, 120), (10, 3_628_800)]
    for n, expected in cases:
        got = trampoline(StepGenerator(factorial, None, None, None, n))
        assert got == expected, f"factorial({n}) → {got}, expected {expected}"
        print(f"factorial({n:>2}) = {got}")

    # Error path through validate
    try:
        trampoline(StepGenerator(factorial, None, None, None, -1))
        assert False, "should have raised"
    except ValueError as exc:
        print(f"Caught expected error: {exc}")

    print("\nAll tests passed.")
